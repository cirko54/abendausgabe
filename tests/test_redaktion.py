"""Redaktion: Übersetzung der Weltblick-Schlagzeilen (decisions.md Nr. 63). Ohne echtes LLM."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from abendausgabe.core.db import Database
from abendausgabe.core.models import Translation
from abendausgabe.modules.weltblick import block as wb
from abendausgabe.modules.weltblick import edit, fetch, translations
from abendausgabe.modules.weltblick.catalog import Source
from abendausgabe.redaktion import main as redaktion
from abendausgabe.redaktion.llm import LLM, BudgetExceededError, Completion

NOW = datetime.now(UTC).replace(microsecond=0)
SERBIA = Source("zeitung-rs", "Beispielzeitung", "rss", "https://example.org", ("RS",), "sr",
                feed="https://example.org/feed")  # fmt: skip
GERMAN = Source("zeitung-de", "Beispielblatt", "rss", "https://example.de", ("DE",), "de",
                feed="https://example.de/feed")  # fmt: skip


def _item(n: str, title: str, image: bool = True, hours: int = 2) -> dict[str, object]:
    return {
        "id": n,
        "url": f"https://example.org/{n}",
        "title": title,
        "image": f"https://img.example.org/{n}.jpg" if image else None,
        "video": None,
        "published_at": NOW - timedelta(hours=hours),
    }


def _store(db: Database) -> None:
    fetch.store(
        db,
        SERBIA,
        [
            _item("rs-1", "Studenti blokirali most u Novom Sadu"),
            _item("rs-2", "Cena struje raste 12 odsto od januara"),
            _item("rs-3", "Bez slike", image=False),
            _item("rs-old", "Stara vest", hours=60),
        ],
        NOW,
    )
    fetch.store(db, GERMAN, [_item("de-1", "Schon deutsch")], NOW)


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(f"sqlite:///{tmp_path / 'db.sqlite3'}")


class FakeProvider:
    def __init__(self, answers: dict[str, str], cost: float = 0.0) -> None:
        self.answers = answers
        self.cost = cost
        self.calls = 0

    @property
    def model(self) -> str:
        return "fake:1"

    def complete(self, user: str, system: str | None = None) -> Completion:
        self.calls += 1
        text = next((v for k, v in self.answers.items() if k in user), "")
        return Completion(text, 10, 5, self.cost)


# ------------------------------------------------------------------ Prüfung


def test_digits_of_any_script_count_as_numbers() -> None:
    assert edit.digit_runs("१२ लोग, 2026") == {"12", "2026"}
    assert edit.digit_runs("۱۰ روپے") == {"10"}
    assert edit.digit_runs("1,5 Millionen") == edit.digit_runs("1.5 million")


def test_check_rejects_invented_numbers_and_commentary() -> None:
    assert edit.check("Cena raste 12 odsto", "„Preis steigt um 12 Prozent“").text == (
        "Preis steigt um 12 Prozent"
    )
    assert edit.check("'Osveta': otac za BBC", '"Rache", sagt der Vater').text == (
        '"Rache", sagt der Vater'
    )  # Zitat am Anfang bleibt vollständig
    assert edit.check("Cena raste 12 odsto", "Preis steigt um 13 Prozent").text is None
    assert edit.check("Rs 500 crore", "5 Milliarden Rupien").text is None  # keine Umrechnung
    assert edit.check("Kratko", "Kurz\n\nHinweis: wörtlich übersetzt").text is None
    assert edit.check("Kratko", "   ").text is None
    assert edit.check("Kratko", "x" * 200).text is None


def test_prompt_file_has_version_and_placeholders() -> None:
    prompt = edit.prompt()
    assert prompt.version
    rendered = prompt.render(source_lang="Serbian", source_code="sr", text="Naslov")
    assert "Serbian (sr)" in rendered and rendered.endswith("Naslov")
    assert "{" not in rendered


# ------------------------------------------------------------- Speicherung


def test_pending_only_what_the_show_can_use(db: Database) -> None:
    _store(db)
    ids = {p.id for p in translations.pending(db, NOW, "1")}
    rs1 = "rs-1"
    assert len(ids) == 2 and rs1 in ids  # ohne Bild, zu alt und Deutsch fehlen
    assert translations.save(db, [(rs1, "Studierende blockieren Brücke"), ("gibt-es-nicht", "x")],
                             "fake:1", "1") == 1  # fmt: skip
    assert rs1 not in {p.id for p in translations.pending(db, NOW, "1")}
    assert rs1 in {p.id for p in translations.pending(db, NOW, "2")}  # neue Prompt-Version


def test_block_shows_translation_with_original(db: Database) -> None:
    _store(db)
    for p in translations.pending(db, NOW, "1"):
        translations.save(db, [(p.id, f"Übersetzt: {p.id}")], "fake:1", "1")
    rounds = [b for b in wb.weltblick_blocks(db, [SERBIA, GERMAN], NOW) if b["type"] == "choice"]
    serbian = [b for b in rounds if b.get("caption_original_lang") == "sr"]
    assert serbian
    for b in serbian:
        assert b["caption"].startswith("Übersetzt:") and b["caption_lang"] == "de"
        assert b["caption_original"] in {"Studenti blokirali most u Novom Sadu",
                                          "Cena struje raste 12 odsto od januara"}  # fmt: skip


def test_translations_are_purged_with_their_items(db: Database) -> None:
    _store(db)
    for p in translations.pending(db, NOW, "1"):
        translations.save(db, [(p.id, "x")], "fake:1", "1")
    fetch.purge(db, NOW + timedelta(days=4))
    with db.session() as s:
        assert s.query(Translation).count() == 0


# -------------------------------------------------------------------- LLM


def test_llm_cache_log_and_budget(tmp_path: Path) -> None:
    prompt = edit.prompt()
    provider = FakeProvider({"A": "eins"}, cost=0.4)
    llm = LLM(provider, tmp_path / "r.sqlite3", budget_eur=0.5)
    assert llm.complete(prompt, "A") == "eins"
    assert llm.complete(prompt, "A") == "eins"
    assert provider.calls == 1  # zweites Mal aus dem Cache
    llm.complete(prompt, "B")
    assert llm.spent_today() == pytest.approx(0.8)
    with pytest.raises(BudgetExceededError):
        llm.complete(prompt, "C")
    stats = llm.stats(NOW - timedelta(minutes=1))
    assert stats["calls"] == 3 and stats["cached"] == 1


# --------------------------------------------------------- Server und Mac


@pytest.fixture
def server_app(app: FastAPI) -> FastAPI:
    app.state.settings = dataclasses.replace(app.state.settings, redaktion_token="geheim")
    return app


def test_api_needs_token(app: FastAPI) -> None:
    with TestClient(app) as c:
        assert c.get("/api/redaktion/translations/pending?prompt_version=1").status_code == 404
    app.state.settings = dataclasses.replace(app.state.settings, redaktion_token="geheim")
    with TestClient(app) as c:
        url = "/api/redaktion/translations/pending?prompt_version=1"
        assert c.get(url).status_code == 401
        assert c.get(url, headers={"Authorization": "Bearer falsch"}).status_code == 401
        assert c.get(url, headers={"Authorization": "Bearer geheim"}).status_code == 200


def test_worker_translates_checks_and_writes_back(server_app: FastAPI, tmp_path: Path) -> None:
    _store(server_app.state.db)
    config = dataclasses.replace(
        redaktion.Config.from_env(), token="geheim", store=tmp_path / "r.sqlite3"
    )
    provider = FakeProvider({
        "Studenti": "Studierende blockieren Brücke in Novi Sad",
        "Cena struje": "Strompreis steigt ab Januar um 15 Prozent",  # falsche Zahl
    })  # fmt: skip
    llm = LLM(provider, config.store, config.budget_eur)
    with TestClient(server_app, headers={"Authorization": "Bearer geheim"}) as c:
        counts = redaktion.translate_headlines(config, redaktion.Server(config, client=c), llm)
    assert counts == {"offen": 2, "übersetzt": 1, "verworfen": 1, "gespeichert": 1}
    with server_app.state.db.session() as s:
        rows = s.query(Translation).all()
        assert [r.text for r in rows] == ["Studierende blockieren Brücke in Novi Sad"]
        assert rows[0].model == "fake:1" and rows[0].prompt_version == edit.prompt().version


def test_env_file_does_not_override_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / ".env"
    env.write_text("# Kommentar\nABEND_X_TEST=aus-datei\nABEND_Y_TEST='zitiert'\n", "utf-8")
    monkeypatch.setenv("ABEND_X_TEST", "aus-umgebung")
    monkeypatch.delenv("ABEND_Y_TEST", raising=False)
    redaktion.load_env_file(env)
    import os

    assert os.environ["ABEND_X_TEST"] == "aus-umgebung"
    assert os.environ["ABEND_Y_TEST"] == "zitiert"
    monkeypatch.delenv("ABEND_Y_TEST")
