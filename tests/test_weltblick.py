"""Phase 1, Schritt 4: Quellenkatalog, Abruf und Weltblick (decisions.md Nr. 47–53)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import feedparser  # type: ignore[import-untyped]
import httpx
import pytest

from abendausgabe.core.config import PROJECT_ROOT
from abendausgabe.core.db import Database
from abendausgabe.core.models import RawItem
from abendausgabe.modules.weltblick import block as wb
from abendausgabe.modules.weltblick import fetch
from abendausgabe.modules.weltblick.catalog import Source, load_catalog
from abendausgabe.session.rundown import validate_rundown

FIXTURES = Path(__file__).parent / "fixtures"
RSS = (FIXTURES / "weltblick_rss.xml").read_bytes()
BSKY = json.loads((FIXTURES / "weltblick_bluesky.json").read_text("utf-8"))
NOW = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)

SERBIA = Source("zeitung-rs", "Beispielzeitung", "rss", "https://example.org", ("RS",), "sr",
                feed="https://example.org/feed")  # fmt: skip
AGENCY = Source("agentur", "Beispielagentur", "bluesky", "https://bsky.app", (), "en",
                actor="agentur.example")  # fmt: skip


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(f"sqlite:///{tmp_path / 'db.sqlite3'}")


def test_repo_catalog_is_valid() -> None:
    sources = load_catalog(PROJECT_ROOT / "catalog")
    assert len(sources) >= 20
    assert len({s.id for s in sources}) == len(sources)
    for s in sources:
        assert s.home_country == "" or s.home_country in wb.COUNTRY_DE, s.id


def test_rss_images_largest_upscaled_or_dropped() -> None:
    items = fetch.parse_rss(SERBIA, RSS, NOW)
    by_url = {i["url"]: i for i in items}
    assert by_url["https://example.org/vesti/1"]["image"] == "https://img.example.org/1-large.jpg"
    assert by_url["https://example.org/vesti/2"]["image"] is None
    assert by_url["https://example.org/vesti/3"]["image"] is None  # 100x80 ist zu klein
    assert "/ace/standard/976/" in by_url["https://example.org/vesti/4"]["image"]


def test_bluesky_video_image_no_reposts_no_text_only() -> None:
    items = fetch.parse_bluesky(AGENCY, BSKY, NOW)
    assert len(items) == 2
    video = items[0]["video"]
    assert video["src"].endswith(".m3u8") and video["vertical"] is True
    assert items[0]["url"] == "https://bsky.app/profile/agentur.example/post/aaa1"
    assert items[1]["image"].startswith("https://cdn.bsky.app/")


@pytest.mark.anyio
async def test_refresh_stores_once_and_survives_broken_source(db: Database) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example.org":
            return httpx.Response(200, content=RSS)
        if request.url.host == "public.api.bsky.app":
            return httpx.Response(200, json=BSKY)
        return httpx.Response(500)

    broken = Source("kaputt", "Kaputt", "rss", "", ("IN",), "en", feed="https://kaputt.example/f")
    transport = httpx.MockTransport(handler)
    # feste Zeit: Die Beiträge der Fixtures sind sonst nach drei Tagen abgelaufen
    result = await fetch.refresh_all(db, [SERBIA, AGENCY, broken], transport, now=NOW)
    assert result["kaputt"] == -1 and result["agentur"] == 2
    again = await fetch.refresh_all(db, [SERBIA, AGENCY], transport, now=NOW)
    assert again["zeitung-rs"] == 0  # nichts doppelt


def _store(db: Database) -> None:
    fetch.store(db, SERBIA, fetch.parse_rss(SERBIA, RSS, NOW), NOW)
    fetch.store(db, AGENCY, fetch.parse_bluesky(AGENCY, BSKY, NOW), NOW)
    india = Source("zeitung-in", "Beispiel Indien", "rss", "", ("IN",), "en", feed="https://x/f")
    fetch.store(
        db,
        india,
        [
            {
                "id": "in-1",
                "url": "https://example.in/1",
                "title": "Headline from India",
                "image": "https://img.example.in/1.jpg",
                "video": None,
                "published_at": NOW - timedelta(hours=2),
            }
        ],
        NOW,
    )


def test_weltblick_rounds_and_video(db: Database) -> None:
    _store(db)
    blocks = wb.weltblick_blocks(db, [SERBIA, AGENCY], NOW)
    # Ohne Redaktion keine Frage: Wo eine Meldung spielt, weiß erst sie (decisions.md Nr. 64)
    cards = [b for b in blocks if b["type"] == "info"]
    assert len(cards) == 2
    assert cards[0]["caption_lang"] == "sr"  # Fremdsprache zuerst
    for c in cards:
        assert c["media"]["src"].startswith("https://")
    assert {c["credit"].split(",")[0] for c in cards} == {
        "Beispielzeitung aus Serbien",
        "zeitung-in aus Indien",  # Quelle nicht übergeben: ihre ID
    }
    video = blocks[-1]
    assert video["type"] == "video" and video["muted"] is True
    validate_rundown([*blocks, {"id": "ende", "type": "end", "title": "Sendeschluss"}])
    assert blocks == wb.weltblick_blocks(db, [SERBIA, AGENCY], NOW)  # stabil am selben Tag


def test_shown_items_do_not_return_next_day(db: Database) -> None:
    _store(db)
    first = wb.weltblick_blocks(db, [SERBIA, AGENCY], NOW)
    wb.mark_shown(db, first, NOW.date())
    later = wb.weltblick_blocks(db, [SERBIA, AGENCY], NOW + timedelta(hours=20))
    shown = {b["raw_item_id"] for b in first}
    assert not shown & {b["raw_item_id"] for b in later}


def test_expired_items_are_purged(db: Database) -> None:
    _store(db)
    assert fetch.purge(db, NOW + timedelta(days=4)) > 0
    with db.session() as s:
        assert s.query(RawItem).count() == 0


def test_feedparser_handles_fixture() -> None:
    assert len(feedparser.parse(RSS).entries) == 4
