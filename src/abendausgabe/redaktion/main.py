"""Redaktionslauf auf dem Mac (SPEC §11.1, decisions.md Nr. 63).

Holt offene Arbeit per API vom Server, lässt das LLM sie bearbeiten, prüft und schreibt
das Ergebnis zurück. Heute: Schlagzeilen im Weltblick übersetzen (Nr. 63), danach
bestimmen, wo die Meldung spielt (Nr. 64).

Einstellungen aus der Umgebung oder aus `.env` neben dem Repo (ABEND_ENV_FILE):
ABEND_SERVER_URL, ABEND_REDAKTION_TOKEN, ABEND_LLM_PROVIDER, ABEND_OLLAMA_URL,
ABEND_MODEL_TRANSLATE, ABEND_MODEL_LOCATE, ABEND_LLM_BUDGET_EUR, ABEND_REDAKTION_MAX_MIN,
ABEND_REDAKTION_SLEEP_AFTER (Minuten ohne Eingabe, danach Ruhezustand; leer: nie).
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from abendausgabe.core.config import PROJECT_ROOT
from abendausgabe.modules.weltblick import edit as weltblick_edit
from abendausgabe.modules.weltblick.geocode import Geocoder
from abendausgabe.modules.weltblick.translations import Pending, PendingPlace, Place
from abendausgabe.redaktion.llm import LLM, BudgetExceededError, LLMError, OllamaProvider

log = logging.getLogger("abendausgabe.redaktion")
PUSH_EVERY = 10


def load_env_file(path: Path) -> None:
    """KEY=VALUE-Zeilen; was schon in der Umgebung steht, gewinnt."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


@dataclass(frozen=True)
class Config:
    server_url: str
    token: str
    provider: str
    ollama_url: str
    model_translate: str
    model_locate: str
    budget_eur: float
    max_seconds: float
    store: Path
    sleep_after_min: float | None

    @classmethod
    def from_env(cls) -> Config:
        data_dir = Path(os.environ.get("ABEND_DATA_DIR", PROJECT_ROOT / "data"))
        return cls(
            server_url=os.environ.get("ABEND_SERVER_URL", "http://localhost:8470").rstrip("/"),
            token=os.environ.get("ABEND_REDAKTION_TOKEN", "").strip(),
            provider=os.environ.get("ABEND_LLM_PROVIDER", "ollama").strip().lower(),
            ollama_url=os.environ.get("ABEND_OLLAMA_URL", "http://localhost:11434"),
            model_translate=os.environ.get("ABEND_MODEL_TRANSLATE", "translategemma:12b"),
            model_locate=os.environ.get("ABEND_MODEL_LOCATE", "qwen2.5:14b"),
            budget_eur=float(os.environ.get("ABEND_LLM_BUDGET_EUR", "1.00")),
            max_seconds=60 * float(os.environ.get("ABEND_REDAKTION_MAX_MIN", "15")),
            store=data_dir / "redaktion.sqlite3",
            sleep_after_min=_minutes(os.environ.get("ABEND_REDAKTION_SLEEP_AFTER", "")),
        )


def _minutes(value: str) -> float | None:
    value = value.strip().lower()
    if value in {"", "aus", "off", "0"}:
        return None
    return float(value)


def _run(*cmd: str) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False).stdout


def idle_seconds(ioreg: str) -> float | None:
    """Sekunden seit der letzten Maus- oder Tastatureingabe (ioreg -c IOHIDSystem)."""
    match = re.search(r'"HIDIdleTime" = (\d+)', ioreg)
    return int(match.group(1)) / 1e9 if match else None


def display_kept_awake(assertions: str) -> bool:
    """Spielt ein Video oder läuft eine Präsentation? (pmset -g assertions)

    PreventUserIdleSystemSleep zählt nicht: Das halten manche Apps dauerhaft.
    """
    match = re.search(r"^\s*PreventUserIdleDisplaySleep\s+(\d+)", assertions, re.M)
    return bool(match and int(match.group(1)) > 0)


def maybe_sleep(config: Config) -> None:
    """Nach dem Lauf in den Ruhezustand, wenn niemand den Mac benutzt (Nr. 65)."""
    if config.sleep_after_min is None or sys.platform != "darwin":
        return
    idle = idle_seconds(_run("ioreg", "-c", "IOHIDSystem", "-d", "4"))
    if idle is None or idle < 60 * config.sleep_after_min:
        log.info("Mac wird benutzt (%s s ohne Eingabe), bleibt wach.", idle and round(idle))
        return
    if display_kept_awake(_run("pmset", "-g", "assertions")):
        log.info("Ein Video oder eine Präsentation läuft, Mac bleibt wach.")
        return
    log.info("Niemand am Mac seit %d min: Ruhezustand.", idle // 60)
    result = subprocess.run(["pmset", "sleepnow"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        log.warning("Ruhezustand ging nicht: %s", (result.stderr or result.stdout).strip())


class Server:
    def __init__(self, config: Config, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(
            base_url=config.server_url,
            timeout=30.0,
            headers={"Authorization": f"Bearer {config.token}"},
        )

    def pending_translations(self, prompt_version: str) -> list[Pending]:
        response = self.client.get(
            "/api/redaktion/translations/pending", params={"prompt_version": prompt_version}
        )
        response.raise_for_status()
        return [Pending(i["id"], i["title"], i["language"]) for i in response.json()["items"]]

    def save_translations(self, model: str, version: str, pairs: list[tuple[str, str]]) -> int:
        if not pairs:
            return 0
        response = self.client.post(
            "/api/redaktion/translations",
            json={
                "model": model,
                "prompt_version": version,
                "items": [{"raw_item_id": i, "text": t} for i, t in pairs],
            },
        )
        response.raise_for_status()
        return int(response.json()["saved"])

    def pending_places(self, prompt_version: str) -> list[PendingPlace]:
        response = self.client.get(
            "/api/redaktion/places/pending", params={"prompt_version": prompt_version}
        )
        response.raise_for_status()
        return [
            PendingPlace(i["id"], i["title"], i["text"], i["language"])
            for i in response.json()["items"]
        ]

    def save_places(self, model: str, version: str, places: list[Place]) -> int:
        if not places:
            return 0
        response = self.client.post(
            "/api/redaktion/places",
            json={
                "model": model,
                "prompt_version": version,
                "items": [
                    {"raw_item_id": p.raw_item_id, "country": p.country, "place": p.place,
                     "lat": p.lat, "lon": p.lon}
                    for p in places
                ],
            },
        )  # fmt: skip
        response.raise_for_status()
        return int(response.json()["saved"])


def make_llm(config: Config, model: str) -> LLM:
    if config.provider != "ollama":
        raise LLMError(
            f"ABEND_LLM_PROVIDER={config.provider!r} gibt es noch nicht; heute nur „ollama“ "
            "(decisions.md Nr. 54)."
        )
    provider = OllamaProvider(model, config.ollama_url)
    return LLM(provider, config.store, config.budget_eur)


def translate_headlines(
    config: Config, server: Server, llm: LLM, deadline: float | None = None
) -> dict[str, int]:
    template = weltblick_edit.prompt()
    items = server.pending_translations(template.version)
    deadline = deadline or time.monotonic() + config.max_seconds
    done: list[tuple[str, str]] = []
    counts = {"offen": len(items), "übersetzt": 0, "verworfen": 0, "gespeichert": 0}
    for n, item in enumerate(items, start=1):
        if time.monotonic() > deadline:
            log.warning("Zeit um (ABEND_REDAKTION_MAX_MIN): %d bleiben offen.", len(items) - n + 1)
            break
        text = weltblick_edit.translate(item, llm, template)
        if text is None:
            counts["verworfen"] += 1
        else:
            counts["übersetzt"] += 1
            done.append((item.id, text))
        if len(done) >= PUSH_EVERY:
            counts["gespeichert"] += server.save_translations(llm.model, template.version, done)
            done = []
    counts["gespeichert"] += server.save_translations(llm.model, template.version, done)
    return counts


def locate_headlines(
    config: Config, server: Server, llm: LLM, geocoder: Geocoder, deadline: float | None = None
) -> dict[str, int]:
    template = weltblick_edit.locate_prompt()
    items = server.pending_places(template.version)
    deadline = deadline or time.monotonic() + config.max_seconds
    done: list[Place] = []
    counts = {"offen": len(items), "verortet": 0, "ohne Ort": 0, "gespeichert": 0}
    for n, item in enumerate(items, start=1):
        if time.monotonic() > deadline:
            log.warning("Zeit um (ABEND_REDAKTION_MAX_MIN): %d bleiben offen.", len(items) - n + 1)
            break
        place = weltblick_edit.locate(item, llm, template, geocoder)
        if place is None:
            continue
        counts["verortet" if place.country else "ohne Ort"] += 1
        done.append(place)
        if len(done) >= PUSH_EVERY:
            counts["gespeichert"] += server.save_places(llm.model, template.version, done)
            done = []
    counts["gespeichert"] += server.save_places(llm.model, template.version, done)
    return counts


def run(date: str) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_env_file(Path(os.environ.get("ABEND_ENV_FILE", PROJECT_ROOT / ".env")))
    config = Config.from_env()
    try:
        return _work(config, date)
    finally:
        maybe_sleep(config)  # auch nach einem Fehler, sonst bleibt der Mac die Nacht wach


def _work(config: Config, date: str) -> int:
    if not config.token:
        log.error("ABEND_REDAKTION_TOKEN fehlt. Denselben Wert in .env auf Server und Mac setzen.")
        return 2
    if date != "today":
        log.warning("--date %s: Die Redaktion arbeitet immer mit dem heutigen Stand.", date)
    started = datetime.now(UTC)
    deadline = time.monotonic() + config.max_seconds
    try:
        server = Server(config)
        llm = make_llm(config, config.model_translate)
        counts = translate_headlines(config, server, llm, deadline)
        locator = make_llm(config, config.model_locate)
        places = locate_headlines(config, server, locator, Geocoder(config.store), deadline)
    except BudgetExceededError as exc:
        log.error("%s", exc)
        return 3
    except LLMError as exc:
        log.error("%s", exc)
        return 4
    except httpx.HTTPError as exc:
        log.error(
            "Server %s nicht erreichbar oder lehnt ab (%s). Adresse (ABEND_SERVER_URL) und "
            "Token prüfen.",
            config.server_url,
            exc,
        )
        return 5
    stats = llm.stats(started)
    log.info(
        "Übersetzung: %s. Orte: %s. LLM: %d Aufrufe (%d aus dem Cache, %d fehlgeschlagen), "
        "%d s, heute %.2f €.",
        ", ".join(f"{v} {k}" for k, v in counts.items()),
        ", ".join(f"{v} {k}" for k, v in places.items()),
        stats["calls"],
        stats["cached"],
        stats["failed"],
        stats["seconds"],
        llm.spent_today(),
    )
    return 0
