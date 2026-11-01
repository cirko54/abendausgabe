"""Fragenpool und Leitner-Zustand in der Datenbank (decisions.md Nr. 44)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from abendausgabe.core.db import Database
from abendausgabe.core.models import QuizItem, ReviewState, utcnow
from abendausgabe.learning import leitner

MAX_REVIEWS = 2
REVIEW_PREFIX = "wiederholung-"


def is_guest(person_id: str) -> bool:
    return person_id.startswith("gast-")


def upsert_item(s: Session, spec: dict[str, Any]) -> QuizItem:
    """Legt eine Frage an, falls es sie noch nicht gibt. Bestehende bleiben unverändert."""
    item = s.get(QuizItem, spec["id"])
    if item is not None:
        return item
    options = [str(o) for o in spec["options"]]
    correct = int(spec["correct"])
    if not 0 <= correct < len(options) or len(options) < 2:
        raise ValueError(f"Frage {spec['id']!r}: ungültige Optionen.")
    aired = spec["aired_on"]
    item = QuizItem(
        id=str(spec["id"]),
        aired_on=aired if isinstance(aired, date) else date.fromisoformat(str(aired)),
        session_id=spec.get("session_id"),
        question=str(spec["question"]),
        options_json=json.dumps(options, ensure_ascii=False),
        correct=correct,
        source=str(spec.get("source", "")),
    )
    s.add(item)
    s.flush()
    return item


def record_answer(
    s: Session, person_id: str, item_id: str, correct: bool, today: date
) -> leitner.Box | None:
    """Antwort einer Person fortschreiben. Gäste bekommen keinen Zustand."""
    if is_guest(person_id):
        return None
    state = s.get(ReviewState, (person_id, item_id))
    if state is None:
        box = leitner.first_encounter(today)
        state = ReviewState(person_id=person_id, item_id=item_id, box=box.box, due=box.due)
        s.add(state)
    else:
        box = leitner.review(leitner.Box(state.box, state.due), correct, today)
        state.box, state.due = box.box, box.due
    state.last_correct = int(correct)
    state.updated_at = utcnow()
    return box


def item_options(item: QuizItem) -> list[str]:
    options: list[str] = json.loads(item.options_json)
    return options


def review_block(item: QuizItem, n: int) -> dict[str, Any]:
    return {
        "id": f"{REVIEW_PREFIX}{n}",
        "type": "choice",
        "title": "Wiederholung",
        "question": item.question,
        "options": item_options(item),
        "correct": item.correct,
        "source": item.source,
        "quiz_item": {"id": item.id},
        "timeout_s": 45,
        "est_minutes": 1,
    }


def due_items(
    s: Session, people: list[str], today: date, exclude: set[str], limit: int
) -> list[QuizItem]:
    """Fragen, die für die meisten der genannten Personen fällig sind, die ältesten zuerst."""
    if not people or limit <= 0:
        return []
    count = func.count(ReviewState.person_id)
    rows = s.execute(
        select(ReviewState.item_id, count, func.min(ReviewState.due))
        .where(
            ReviewState.person_id.in_(people),
            ReviewState.due.is_not(None),
            ReviewState.due <= today,
        )
        .group_by(ReviewState.item_id)
        .order_by(count.desc(), func.min(ReviewState.due))
    ).all()
    items: list[QuizItem] = []
    for item_id, _n, _due in rows:
        if item_id in exclude:
            continue
        item = s.get(QuizItem, item_id)
        if item is not None:
            items.append(item)
        if len(items) >= limit:
            break
    return items


def review_blocks(
    db: Database, present: list[str], today: date, exclude: set[str]
) -> list[dict[str, Any]]:
    people = [p for p in present if not is_guest(p)]
    with db.session() as s:
        items = due_items(s, people, today, exclude, MAX_REVIEWS)
        return [review_block(item, n) for n, item in enumerate(items, start=1)]


def with_reviews(
    rundown: list[dict[str, Any]], reviews: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Wiederholungen vor den Sendeschluss setzen; alte Wiederholungsblöcke ersetzen."""
    body = [b for b in rundown if not str(b["id"]).startswith(REVIEW_PREFIX)]
    end = body[-1:] if body and body[-1]["type"] == "end" else []
    head = body[:-1] if end else body
    return [*head, *reviews, *end]


def record_reveal(
    db: Database,
    block: dict[str, Any],
    answers: dict[str, Any],
    session_id: str | None,
    today: date,
) -> None:
    """Nach der Auflösung eines Quizblocks: Frage anlegen und Boxen fortschreiben."""
    spec = block.get("quiz_item")
    if not isinstance(spec, dict) or block.get("type") != "choice":
        return
    with db.session() as s:
        item = upsert_item(
            s,
            {
                "id": spec["id"],
                "question": spec.get("question", block["question"]),
                "options": block["options"],
                "correct": block["correct"],
                "source": block.get("source", ""),
                "aired_on": spec.get("aired_on", today),
                "session_id": session_id,
            },
        )
        for person_id, value in answers.items():
            record_answer(s, person_id, item.id, int(value) == item.correct, today)
        s.commit()
