"""Phase 1, Schritt 2: Tagesablauf aus tagesschau und Wetter vor acht (decisions.md Nr. 37)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from abendausgabe.assembly import notausgabe
from abendausgabe.core.db import Database
from abendausgabe.modules.tagesschau import block as tb
from abendausgabe.modules.wetter_himmel import block as wb
from abendausgabe.session.manager import RoomManager
from abendausgabe.session.room import Room
from abendausgabe.session.rundown import validate_rundown

FIXTURES = Path(__file__).parent / "fixtures"
CHANNELS = json.loads((FIXTURES / "tagesschau_channels_2026-11-01.json").read_text("utf-8"))
MVW = json.loads((FIXTURES / "mediathekviewweb_wetter_2026-11-01.json").read_text("utf-8"))
BROADCASTS = tb.parse_channels(CHANNELS)


def at(day: int, hour: int, minute: int = 0, month: int = 10) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=tb.BERLIN)


# ------------------------------------------------------------------ tagesschau


def test_parse_classifies_broadcasts() -> None:
    kinds = sorted(b.kind for b in BROADCASTS)
    assert kinds == ["100s", "20uhr", "live", "other"]
    twenty = next(b for b in BROADCASTS if b.kind == "20uhr")
    assert twenty.duration_s == 900
    assert twenty.mp4 and twenty.mp4.endswith(".mp4")
    assert twenty.topics[0] == "Thema 1 der Sendung"


def test_live_window_uses_hls_stream() -> None:
    media = tb.choose_media(BROADCASTS, at(1, 19, 59, month=11))
    assert media is not None
    assert media["format"] == "hls" and media["live"] is True
    assert media["src"].endswith(".m3u8")
    assert media["start_at"] is None  # vor 20 Uhr: an der Live-Kante einsteigen
    assert media["end_at"] == at(1, 20, 15, month=11).timestamp()
    # Rückfall, falls hls.js scheitert: die 100 Sekunden von heute
    assert media["fallback_src"] and media["fallback_src"].endswith(".mp4")


def test_late_start_rewinds_to_beginning_of_broadcast() -> None:
    media = tb.choose_media(BROADCASTS, at(1, 21, 30, month=11))
    assert media is not None and media["format"] == "hls"
    assert media["live"] is False and "zeitversetzt" in media["title"]
    assert media["start_at"] == at(1, 20, 0, month=11).timestamp()
    assert media["duration_s"] == 900
    # Anfang fällt bald aus dem Zwei-Stunden-Fenster: dann die Kurzfassung
    late = tb.choose_media(BROADCASTS, at(1, 21, 45, month=11))
    assert late is not None and late["title"].startswith("tagesschau in 100 Sekunden")


def test_current_broadcast_entry_sets_exact_window() -> None:
    start = int(at(1, 19, 59, month=11).timestamp()) + 57
    current = {
        "title": "Aktuelle Sendung: Tagesschau 20 Uhr",
        "streams": {"adaptivestreaming": "https://live.example/master.m3u8"},
        "start": start,
        "end": start + 903,
    }
    data = {"channels": [current, *CHANNELS["channels"]]}
    media = tb.choose_media(tb.parse_channels(data), at(1, 20, 5, month=11))
    assert media is not None
    assert media["start_at"] == start and media["end_at"] == start + 903
    assert media["src"] == "https://live.example/master.m3u8"


def test_after_broadcast_uses_todays_20uhr_recording() -> None:
    media = tb.choose_media(BROADCASTS, at(31, 21, 0))
    assert media is not None
    assert media["title"] == "tagesschau, 20 Uhr"
    assert media["format"] == "mp4" and media["duration_s"] == 900


def test_before_20uhr_falls_back_to_todays_100_seconds() -> None:
    media = tb.choose_media(BROADCASTS, at(1, 18, 0, month=11))
    assert media is not None
    assert media["title"].startswith("tagesschau in 100 Sekunden")


def test_nothing_from_today_means_no_media() -> None:
    assert tb.choose_media(BROADCASTS, at(5, 18, 0, month=11)) is None


def test_aufmacher_question_uses_verbatim_topics() -> None:
    question = tb.aufmacher_question(BROADCASTS, at(31, 21, 0))
    assert question is not None
    topics = next(b for b in BROADCASTS if b.kind == "20uhr").topics
    assert question["options"][question["correct"]] == topics[0]
    assert set(question["options"]) <= set(topics)
    assert len(set(question["options"])) == 3
    # stabil für dieselbe Sendung
    assert question == tb.aufmacher_question(BROADCASTS, at(31, 22, 0))
    # ohne heutige 20-Uhr-Ausgabe keine Frage
    assert tb.aufmacher_question(BROADCASTS, at(1, 18, 0, month=11)) is None


# --------------------------------------------------------------------- Wetter


def test_wetter_vor_acht_only_from_today() -> None:
    results = MVW["result"]["results"]
    block = wb.wetter_vor_acht_block(results, at(31, 21, 0))
    assert block is not None and block["type"] == "video"
    assert block["src"].startswith("https://") and block["est_minutes"] >= 1
    assert wb.wetter_vor_acht_block(results, at(5, 21, 0, month=11)) is None


# ------------------------------------------------------------------ Videoblock


@pytest.mark.parametrize(
    "video",
    [
        {"id": "v", "type": "video", "title": "x"},  # weder src noch media
        {"id": "v", "type": "video", "title": "x", "src": "https://a/b.mp4", "media": "t"},
        {"id": "v", "type": "video", "title": "x", "src": "http://a/b.mp4"},
        {"id": "v", "type": "video", "title": "x", "src": "https://a/b", "format": "avi"},
    ],
)
def test_invalid_video_blocks_are_rejected(video: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        validate_rundown([video, {"id": "e", "type": "end", "title": "Ende"}])


def test_rundown_changes_only_in_lobby() -> None:
    old = [{"id": "e", "type": "end", "title": "Ende"}]
    new = [{"id": "a", "type": "info", "title": "A"}, *old]
    room = Room(old)
    assert room.set_rundown(new) is True
    room.checkin("alex", "Alex", "#000", "admin")
    room.advance(0.0)
    assert room.set_rundown(old) is False
    assert room.rundown == new


# ---------------------------------------------------------------- Notausgabe


async def _channels() -> Any:
    return CHANNELS


async def _mvw(_query: str) -> Any:
    return MVW["result"]["results"]


@pytest.mark.anyio
async def test_program_with_all_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(notausgabe.ts_fetch, "channels", _channels)
    monkeypatch.setattr(notausgabe.wetter_fetch, "search", _mvw)
    program = await notausgabe.build_program(at(31, 21, 0))
    assert [b["id"] for b in program] == [
        "begruessung",
        "wetter-vor-acht",
        "tagesschau-aufmacher",
        "tagesschau",
        "ende",
    ]
    assert "Samstag, 31. Oktober" in program[0]["body"]


@pytest.mark.anyio
async def test_program_survives_source_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    async def broken(*_args: Any) -> Any:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(notausgabe.ts_fetch, "channels", broken)
    monkeypatch.setattr(notausgabe.wetter_fetch, "search", broken)
    program = await notausgabe.build_program(at(31, 21, 0))
    assert [b["type"] for b in program] == ["info", "end"]
    assert "keine Beiträge" in program[0]["body"]


@pytest.mark.anyio
async def test_start_refreshes_program_from_lobby(tmp_path: Path) -> None:
    calls = 0
    tonight = [
        {"id": "a", "type": "info", "title": "Heute"},
        {"id": "e", "type": "end", "title": "Ende"},
    ]

    async def program() -> list[dict[str, Any]]:
        nonlocal calls
        calls += 1
        return tonight

    room = Room([{"id": "e", "type": "end", "title": "Ende"}])
    manager = RoomManager(room, Database(f"sqlite:///{tmp_path / 'db.sqlite3'}"), program)
    room.checkin("alex", "Alex", "#000", "admin")
    assert await manager.advance() is True
    assert room.rundown == tonight and room.current_block == tonight[0]
    # Während der Sendung wird nicht neu zusammengestellt
    await manager.refresh_program(force=True)
    assert calls == 1


def test_media_route(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from abendausgabe.api import media

    monkeypatch.setattr(media.ts_fetch, "channels", _channels)
    response = client.get("/api/media/tagesschau")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"media", "error"}
    assert client.get("/api/media/unbekannt").status_code == 404


@pytest.mark.anyio
async def test_next_show_day_returns_to_lobby(tmp_path: Path) -> None:
    rundown = [
        {"id": "a", "type": "info", "title": "Heute"},
        {"id": "e", "type": "end", "title": "Ende"},
    ]
    room = Room(rundown)
    manager = RoomManager(room, Database(f"sqlite:///{tmp_path / 'db.sqlite3'}"))
    clock = [at(2, 20, 30, month=11)]
    manager.clock = lambda: clock[0]
    room.checkin("alex", "Alex", "#000", "admin")
    assert await manager.advance() is True
    await manager.advance()
    assert room.phase == "ended"
    # Kurz nach Mitternacht gehört alles noch zum Vorabend
    clock[0] = at(3, 1, 0, month=11)
    assert manager.roll_over() is False and room.phase == "ended"
    # Am nächsten Sendetag wartet die Lobby, alle melden sich neu an
    clock[0] = at(3, 4, 30, month=11)
    assert manager.roll_over() is True
    assert room.phase == "lobby" and room.present_ids == []
    assert manager.roll_over() is False


def test_unfinished_show_is_cleared_on_new_day() -> None:
    room = Room(
        [{"id": "a", "type": "info", "title": "A"}, {"id": "e", "type": "end", "title": "E"}]
    )
    room.checkin("alex", "Alex", "#000", "admin")
    room.advance(0.0)
    assert room.phase == "block"
    assert room.new_day() is True
    assert room.phase == "lobby" and room.block_index == -1
    assert room.new_day() is False


def test_restart_replays_same_rundown() -> None:
    rundown = [
        {"id": "a", "type": "info", "title": "A"},
        {"id": "b", "type": "info", "title": "B"},
        {"id": "e", "type": "end", "title": "E"},
    ]
    room = Room(rundown)
    assert room.restart(0.0) is False  # Lobby: nichts zu wiederholen
    room.checkin("alex", "Alex", "#000", "admin")
    room.checkin("sam", "Sam", "#111", "member")
    room.leave("sam")
    room.advance(0.0)
    room.advance(0.0)
    first = room.session_id
    room.pop_events()
    assert room.restart(1.0) is True
    assert room.phase == "block" and room.block_index == 0 and room.rundown == rundown
    assert room.present_ids == ["alex"] and room.session_id != first
    assert [e.kind for e in room.pop_events()] == ["session_start"]
    room.advance(2.0)
    room.advance(2.0)
    assert room.phase == "ended" and room.restart(3.0) is True
