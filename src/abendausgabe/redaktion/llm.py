"""Schmale LLM-Schnittstelle der Redaktion (SPEC §11.3, decisions.md Nr. 54, 63).

Anbieter heute: Ollama auf dem Mac (lokal, kostenlos). Ein Anbieter für die Claude-API
kommt hinter dieselbe Schnittstelle, wenn der Haushalt das entscheidet.

Jeder Aufruf geht durch `LLM.complete`: Cache nach Hash aus Modell, Prompt-Version und
Eingabe, Tagesbudget mit hartem Stopp, Eintrag in llm_call_log. Beides liegt in einer
eigenen kleinen SQLite-Datei auf dem Mac, nicht in der Sendungsdatenbank.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx

from abendausgabe.core.dates import BERLIN

PROMPT_DIR = Path(__file__).resolve().parents[3] / "prompts"


class LLMError(RuntimeError):
    pass


class BudgetExceededError(LLMError):
    pass


@dataclass(frozen=True)
class Prompt:
    module: str
    name: str
    version: str
    text: str

    def render(self, **values: str) -> str:
        out = self.text
        for key, value in values.items():
            out = out.replace("{" + key + "}", value)
        return out


def load_prompt(module: str, name: str, prompt_dir: Path = PROMPT_DIR) -> Prompt:
    """Prompt-Datei mit Kopfzeilen `version: …` bis zur ersten Zeile `---`."""
    raw = (prompt_dir / module / f"{name}.md").read_text(encoding="utf-8")
    head, sep, body = raw.partition("\n---\n")
    if not sep:
        raise LLMError(f"prompts/{module}/{name}.md: Kopf mit „version:“ und „---“ fehlt.")
    meta = dict(
        line.split(":", 1) for line in head.splitlines() if ":" in line and not line.startswith("#")
    )
    version = meta.get("version", "").strip()
    if not version:
        raise LLMError(f"prompts/{module}/{name}.md: „version:“ fehlt.")
    return Prompt(module, name, version, body.strip("\n"))


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_eur: float = 0.0


class Provider(Protocol):
    @property
    def model(self) -> str: ...

    def complete(
        self, user: str, system: str | None = None, schema: dict[str, Any] | None = None
    ) -> Completion: ...


class OllamaProvider:
    """Ollama-HTTP-API (/api/chat), Temperatur 0, ohne Streaming."""

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        client: httpx.Client | None = None,
    ) -> None:
        self._model = model
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=300.0)

    @property
    def model(self) -> str:
        return f"ollama:{self._model}"

    def complete(
        self, user: str, system: str | None = None, schema: dict[str, Any] | None = None
    ) -> Completion:
        messages = [{"role": "system", "content": system}] if system else []
        messages.append({"role": "user", "content": user})
        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0},
        }
        if schema is not None:
            body["format"] = schema  # strukturierte Ausgabe nach JSON-Schema
        try:
            response = self.client.post(f"{self.base_url}/api/chat", json=body)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise LLMError(
                f"Ollama unter {self.base_url} antwortet nicht ({exc}). Läuft `ollama serve`, "
                f"ist das Modell {self._model} geladen (`ollama pull {self._model}`)?"
            ) from exc
        return Completion(
            text=str((data.get("message") or {}).get("content", "")),
            input_tokens=int(data.get("prompt_eval_count") or 0),
            output_tokens=int(data.get("eval_count") or 0),
        )


class LLM:
    """Cache, Budget und Protokoll um einen Anbieter."""

    def __init__(self, provider: Provider, store: Path, budget_eur: float) -> None:
        self.provider = provider
        self.budget_eur = budget_eur
        store.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(store)
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS llm_cache (
                key TEXT PRIMARY KEY, text TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS llm_call_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, day TEXT NOT NULL,
                module TEXT NOT NULL, prompt TEXT NOT NULL, prompt_version TEXT NOT NULL,
                model TEXT NOT NULL, cached INTEGER NOT NULL, ok INTEGER NOT NULL,
                input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL,
                cost_eur REAL NOT NULL, duration_ms INTEGER NOT NULL, error TEXT);
            """
        )

    @property
    def model(self) -> str:
        return self.provider.model

    def spent_today(self) -> float:
        day = datetime.now(BERLIN).date().isoformat()
        row = self.conn.execute(
            "SELECT COALESCE(SUM(cost_eur), 0) FROM llm_call_log WHERE day = ?", (day,)
        ).fetchone()
        return float(row[0])

    def _key(
        self, prompt: Prompt, user: str, system: str | None, schema: dict[str, Any] | None
    ) -> str:
        payload = json.dumps(
            [self.model, prompt.module, prompt.name, prompt.version, system, user, schema],
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def _log(self, prompt: Prompt, cached: bool, ok: bool, result: Completion | None,
             duration_ms: int, error: str | None = None) -> None:  # fmt: skip
        now = datetime.now(UTC)
        self.conn.execute(
            "INSERT INTO llm_call_log (ts, day, module, prompt, prompt_version, model, cached, ok,"
            " input_tokens, output_tokens, cost_eur, duration_ms, error)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                now.isoformat(), now.astimezone(BERLIN).date().isoformat(), prompt.module,
                prompt.name, prompt.version, self.model, int(cached), int(ok),
                result.input_tokens if result else 0, result.output_tokens if result else 0,
                result.cost_eur if result else 0.0, duration_ms, (error or "")[:500] or None,
            ),
        )  # fmt: skip
        self.conn.commit()

    def complete(
        self,
        prompt: Prompt,
        user: str,
        system: str | None = None,
        schema: dict[str, Any] | None = None,
    ) -> str:
        key = self._key(prompt, user, system, schema)
        row = self.conn.execute("SELECT text FROM llm_cache WHERE key = ?", (key,)).fetchone()
        if row is not None:
            self._log(prompt, cached=True, ok=True, result=None, duration_ms=0)
            return str(row[0])
        if self.spent_today() >= self.budget_eur:
            raise BudgetExceededError(
                f"Tagesbudget {self.budget_eur:.2f} € erreicht; weiter erst morgen "
                "(ABEND_LLM_BUDGET_EUR)."
            )
        start = time.monotonic()
        try:
            result = self.provider.complete(user, system, schema)
        except LLMError as exc:
            self._log(prompt, False, False, None, int((time.monotonic() - start) * 1000), str(exc))
            raise
        self._log(prompt, False, True, result, int((time.monotonic() - start) * 1000))
        self.conn.execute(
            "INSERT OR REPLACE INTO llm_cache (key, text, created_at) VALUES (?, ?, ?)",
            (key, result.text, datetime.now(UTC).isoformat()),
        )
        self.conn.commit()
        return result.text

    def stats(self, since: datetime) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT COUNT(*), SUM(cached), SUM(1 - ok), COALESCE(SUM(duration_ms), 0)"
            " FROM llm_call_log WHERE ts >= ?",
            (since.astimezone(UTC).isoformat(),),
        ).fetchone()
        return {
            "calls": int(row[0] or 0),
            "cached": int(row[1] or 0),
            "failed": int(row[2] or 0),
            "seconds": round(int(row[3] or 0) / 1000),
        }
