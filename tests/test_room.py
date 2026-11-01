from __future__ import annotations

import pytest

from abendausgabe.session.room import Room, score_answer
from abendausgabe.session.rundown import validate_rundown

RUNDOWN = [
    {"id": "hallo", "type": "info", "title": "Hallo", "body": "x"},
    {
        "id": "mond",
        "type": "estimate",
        "title": "Schätzen",
        "question": "?",
        "unit": "km",
        "min": 1000,
        "max": 10_000_000,
        "log": True,
        "truth": 384_400,
        "timeout_s": 30,
    },
    {
        "id": "wahl",
        "type": "choice",
        "title": "Wahl",
        "question": "?",
        "options": ["A", "B"],
        "correct": 1,
    },
    {"id": "ende", "type": "end", "title": "Sendeschluss"},
]


def make_room() -> Room:
    room = Room(validate_rundown([dict(b) for b in RUNDOWN]), ask_timeout_s=45)
    room.checkin("alex", "Alex", "#E69F00", "admin")
    room.checkin("robin", "Robin", "#CC79A7", "member")
    return room


def test_lobby_needs_someone_present() -> None:
    room = Room(validate_rundown([dict(b) for b in RUNDOWN]))
    assert room.advance(0) is False
    room.checkin("kim", "Kim", "#009E73", "member")
    assert room.advance(0) is True
    assert room.phase == "block" and room.block_phase == "show"


def test_truth_hidden_until_reveal_and_reveal_after_all_answers() -> None:
    room = make_room()
    room.advance(0)
    room.advance(0)  # zur Schätzfrage
    state = room.state(1)
    assert state["block_phase"] == "ask"
    assert "truth" not in state["block"]
    assert room.answer("alex", 400_000, 1)
    assert room.block_phase == "ask"  # Robin fehlt noch
    tv_state = room.state(2)
    assert all("value" not in m for m in tv_state["members"])  # keine fremden Antworten
    assert room.answer("robin", 38_440, 2)
    assert room.block_phase == "reveal"
    state = room.state(3)
    assert state["block"]["truth"] == 384_400
    points = {a["person_id"]: a["points"] for a in state["reveal"]["answers"]}
    assert points["alex"] > 90
    assert points["robin"] == 0  # Faktor 10 daneben


def test_timeout_reveals() -> None:
    room = make_room()
    room.advance(0)
    room.advance(0)
    assert room.tick(29) is False
    assert room.tick(30) is True
    assert room.block_phase == "reveal"


def test_invalid_answers_rejected() -> None:
    room = make_room()
    room.advance(0)
    room.advance(0)
    assert room.answer("alex", 1, 0) is False  # unter min
    assert room.answer("alex", "abc", 0) is False
    assert room.answer("fremd", 400_000, 0) is False


def test_skip_needs_majority() -> None:
    room = make_room()
    room.checkin("kim", "Kim", "#009E73", "member")
    room.advance(0)
    assert room.skip_vote("robin", 0)
    assert room.block_index == 0  # 1 von 3
    assert room.skip_vote("kim", 0)
    assert room.block_index == 1  # 2 von 3


def test_leave_triggers_reveal_when_rest_answered() -> None:
    room = make_room()
    room.advance(0)
    room.advance(0)
    room.answer("alex", 384_400, 0)
    assert room.block_phase == "ask"
    room.leave("robin")
    assert room.block_phase == "reveal"


def test_end_is_final_until_reset() -> None:
    room = make_room()
    for _ in range(10):
        room.advance(0)
    assert room.phase == "ended"
    assert room.advance(0) is False  # kein „mehr davon“
    assert room.reset() is True
    assert room.phase == "lobby"


def test_signals_are_logged_not_state() -> None:
    room = make_room()
    room.advance(0)
    room.pop_events()
    assert room.signal("robin", "too_hard") is False
    events = room.pop_events()
    assert events[0].kind == "signal" and events[0].payload == {"kind": "too_hard"}


def test_choice_scoring() -> None:
    block = RUNDOWN[2]
    assert score_answer(block, 1) == 100
    assert score_answer(block, 0) == 0


def test_rundown_must_end_with_end_block() -> None:
    with pytest.raises(ValueError):
        validate_rundown([{"id": "a", "type": "info", "title": "A"}])
