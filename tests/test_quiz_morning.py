"""Phase 1, Schritt 3: Leitner, Wiederholung, Morgen danach, Push (decisions.md Nr. 44–46)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from abendausgabe.core.config import get_settings
from abendausgabe.core.dates import BERLIN
from abendausgabe.core.db import Database
from abendausgabe.core.models import (
    MorningRating,
    PushTopic,
    QuizItem,
    ReviewState,
    SessionRecord,
)
from abendausgabe.learning import leitner, morning, pool
from abendausgabe.session.manager import RoomManager
from abendausgabe.session.room import Room
from tests.conftest import auth, register

FIXTURES = Path(__file__).parent / "fixtures"
CHANNELS = json.loads((FIXTURES / "tagesschau_channels_2026-11-01.json").read_text("utf-8"))
DAY = date(2026, 10, 31)


def item_spec(item_id: str = "frage-1", aired: date = DAY) -> dict[str, Any]:
    return {
        "id": item_id,
        "question": "Welche Farbe hat der Himmel?",
        "options": ["Blau", "Grün", "Rot"],
        "correct": 0,
        "source": "Beispielquelle",
        "aired_on": aired,
    }


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(f"sqlite:///{tmp_path / 'db.sqlite3'}")


def add_session(
    db: Database, members: list[str], started: datetime, session_id: str = "s1"
) -> None:
    with db.session() as s:
        s.add(
            SessionRecord(
                id=session_id, started_at=started.astimezone(UTC), members_json=json.dumps(members)
            )
        )
        s.commit()


# ------------------------------------------------------------------- Leitner


def test_leitner_steps_3_10_30_then_learned() -> None:
    today = DAY
    box = leitner.first_encounter(today)
    assert box == leitner.Box(1, today + timedelta(days=3))
    box = leitner.review(box, True, box.due or today)
    assert box.box == 2 and box.due == DAY + timedelta(days=3 + 10)
    box = leitner.review(box, True, box.due or today)
    assert box.box == 3
    box = leitner.review(box, True, box.due or today)
    assert box == leitner.Box(leitner.LEARNED, None)


def test_leitner_early_correct_does_not_advance_wrong_resets() -> None:
    box = leitner.first_encounter(DAY)
    assert leitner.review(box, True, DAY + timedelta(days=1)) == box
    late = leitner.review(leitner.Box(3, DAY), False, DAY)
    assert late == leitner.Box(1, DAY + timedelta(days=3))


# ---------------------------------------------------------------------- Pool


def test_reveal_creates_item_and_states_but_not_for_guests(db: Database) -> None:
    block = {
        "id": "tagesschau-aufmacher",
        "type": "choice",
        "question": "Womit macht die tagesschau heute auf?",
        "options": ["A", "B", "C"],
        "correct": 2,
        "source": "Quelle",
        "quiz_item": {
            "id": "ts-1",
            "question": "Womit machte sie am Samstag auf?",
            "aired_on": DAY,
        },
    }
    pool.record_reveal(db, block, {"alex": 2, "sam": 0, "gast-1": 2}, "s1", DAY)
    with db.session() as s:
        item = s.get(QuizItem, "ts-1")
        assert item is not None and item.question.startswith("Womit machte")
        assert {r.person_id for r in s.query(ReviewState)} == {"alex", "sam"}
        assert all(r.due == DAY + timedelta(days=3) for r in s.query(ReviewState))


def test_reviews_pick_due_for_most_present_and_go_before_end(db: Database) -> None:
    with db.session() as s:
        for n in range(1, 4):
            pool.upsert_item(s, item_spec(f"frage-{n}"))
        pool.record_answer(s, "alex", "frage-1", True, DAY)
        pool.record_answer(s, "alex", "frage-2", True, DAY)
        pool.record_answer(s, "sam", "frage-2", True, DAY)
        pool.record_answer(s, "kim", "frage-3", True, DAY)
        s.commit()
    due_day = DAY + timedelta(days=3)
    assert pool.review_blocks(db, ["alex", "sam"], DAY, set()) == []  # noch nicht fällig
    blocks = pool.review_blocks(db, ["alex", "sam"], due_day, set())
    assert [b["quiz_item"]["id"] for b in blocks] == ["frage-2", "frage-1"]
    assert pool.review_blocks(db, ["alex", "sam"], due_day, {"frage-2"})[0]["quiz_item"] == {
        "id": "frage-1"
    }
    rundown = [{"id": "a", "type": "info"}, {"id": "ende", "type": "end"}]
    merged = pool.with_reviews(rundown, blocks)
    assert [b["id"] for b in merged] == ["a", "wiederholung-1", "wiederholung-2", "ende"]
    assert pool.with_reviews(merged, []) == rundown


@pytest.mark.anyio
async def test_manager_adds_reviews_at_start_and_records_answers(db: Database) -> None:
    with db.session() as s:
        pool.upsert_item(s, item_spec())
        state = ReviewState(person_id="alex", item_id="frage-1", box=1, due=date(2000, 1, 1))
        s.add(state)
        s.commit()
    room = Room(
        [{"id": "a", "type": "info", "title": "A"}, {"id": "e", "type": "end", "title": "E"}]
    )
    manager = RoomManager(room, db)
    room.checkin("alex", "Alex", "#000", "admin")
    await manager.advance()
    assert [b["id"] for b in room.rundown] == ["a", "wiederholung-1", "e"]
    await manager.advance()  # zur Wiederholung
    assert room.block_phase == "ask"
    await manager.handle(lambda: room.answer("alex", 0, 0.0))  # alle haben geantwortet
    with db.session() as s:
        after = s.get(ReviewState, ("alex", "frage-1"))
        assert after is not None and after.box == 2


# ------------------------------------------------------------- Morgen danach


def test_morning_card_and_submit(db: Database) -> None:
    evening = datetime(2026, 10, 31, 20, 30, tzinfo=BERLIN)
    add_session(db, ["alex", "sam"], evening)
    with db.session() as s:
        pool.upsert_item(s, {**item_spec(), "session_id": "s1"})
        s.commit()
    now = datetime(2026, 11, 1, 8, 31, tzinfo=BERLIN)
    assert morning.card(db, "kim", now) is None  # war nicht dabei
    card = morning.card(db, "alex", now)
    assert card is not None and card["day"] == "Samstag, 31. Oktober"
    assert card["question"] and "correct" not in card["question"]  # Auflösung erst danach
    result = morning.submit(db, "alex", "s1", 4, 1, now)
    assert result["question"] == {"correct": False, "answer": "Blau", "source": "Beispielquelle"}
    assert morning.card(db, "alex", now) is None
    with pytest.raises(LookupError):
        morning.submit(db, "alex", "s1", 5, None, now)
    with pytest.raises(ValueError):
        morning.submit(db, "sam", "s1", 9, None, now)
    with db.session() as s:
        assert s.query(MorningRating).count() == 1
        state = s.get(ReviewState, ("alex", "frage-1"))
        assert state is not None and state.box == 1
    # nach drei Tagen ist die Karte weg
    assert morning.card(db, "sam", now + timedelta(days=4)) is None


@pytest.mark.anyio
async def test_morning_job_backfills_question_and_pushes_once(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    from abendausgabe.modules.tagesschau import fetch as ts_fetch

    async def channels() -> Any:
        return CHANNELS

    monkeypatch.setattr(ts_fetch, "channels", channels)
    add_session(db, ["alex", "sam"], datetime(2026, 10, 31, 20, 5, tzinfo=BERLIN))
    with db.session() as s:
        s.add(PushTopic(person_id="alex", topic="abend-test", base_url="http://192.0.2.10:8470"))
        s.commit()
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "x"})

    transport = httpx.MockTransport(handler)
    settings = replace(get_settings(), morning_push=time(8, 30), ntfy_url="https://ntfy.example")
    early = datetime(2026, 11, 1, 8, 0, tzinfo=BERLIN)
    assert await morning.morning_job(db, settings, early, transport) == 0
    now = datetime(2026, 11, 1, 8, 30, tzinfo=BERLIN)
    assert await morning.morning_job(db, settings, now, transport) == 1
    assert await morning.morning_job(db, settings, now, transport) == 0  # nicht doppelt
    assert sent[0]["topic"] == "abend-test"
    assert sent[0]["click"] == "http://192.0.2.10:8470/c/#morgen"
    assert "Alex" not in json.dumps(sent[0])  # minimaler Inhalt, keine Namen
    with db.session() as s:
        item = s.get(QuizItem, "tagesschau-aufmacher-2026-10-31")
        assert item is not None and item.session_id == "s1"
    card = morning.card(db, "alex", now)
    assert card and card["question"]["item_id"] == "tagesschau-aufmacher-2026-10-31"


# ----------------------------------------------------------------------- API


def test_push_and_morning_api(client: TestClient) -> None:
    token = register(client, "alex")
    guest = register(client, "gast", None)
    assert client.get("/api/push", headers=auth(guest)).status_code == 403
    assert client.get("/api/push", headers=auth(token)).json()["enabled"] is False
    on = client.post("/api/push", headers=auth(token)).json()
    assert on["enabled"] and on["app"].startswith("ntfy://") and "abend-" in on["web"]
    calls: list[httpx.Request] = []
    client.app.state.push_transport = httpx.MockTransport(  # type: ignore[attr-defined]
        lambda r: calls.append(r) or httpx.Response(200)
    )
    assert client.post("/api/push/test", headers=auth(token)).status_code == 200
    assert len(calls) == 1
    assert client.delete("/api/push", headers=auth(token)).json()["enabled"] is False
    assert client.post("/api/push/test", headers=auth(token)).status_code == 409
    assert client.get("/api/morning", headers=auth(token)).json() == {"card": None}
    response = client.post(
        "/api/morning", headers=auth(token), json={"session_id": "x", "rating": 3}
    )
    assert response.status_code == 409
