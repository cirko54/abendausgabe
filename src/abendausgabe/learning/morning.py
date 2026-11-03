"""Morgen danach (decisions.md Nr. 45, 46): Bewertung 1–5, eine Abruffrage, Push um 08:30.

Die Karte gilt für die letzte Sendung und bleibt offen, bis die Person antwortet oder die
nächste Sendung beginnt (höchstens drei Tage).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, time, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from abendausgabe.core import push
from abendausgabe.core.config import Settings
from abendausgabe.core.dates import BERLIN, date_de, local_date
from abendausgabe.core.db import Database
from abendausgabe.core.models import (
    MorningRating,
    PushSent,
    PushTopic,
    QuizItem,
    ReviewState,
    SessionRecord,
)
from abendausgabe.learning import pool

log = logging.getLogger(__name__)

MAX_AGE = timedelta(days=3)
PUSH_WINDOW = timedelta(hours=4)
EVENING = time(19, 58)  # ab hier kann die tagesschau in der Sendung gelaufen sein
PUSH_TITLE = "Abendausgabe"
PUSH_MESSAGE = "Wie war die Abendausgabe gestern? Eine Frage wartet."


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def latest_session(s: Session) -> SessionRecord | None:
    return s.scalars(
        select(SessionRecord).order_by(SessionRecord.started_at.desc()).limit(1)
    ).first()


def _members(record: SessionRecord) -> list[str]:
    try:
        members = json.loads(record.members_json or "[]")
    except json.JSONDecodeError:
        return []
    return [str(m) for m in members if isinstance(m, str)]


def open_session(s: Session, person_id: str, now: datetime) -> SessionRecord | None:
    """Letzte Sendung, bei der die Person dabei war und noch nicht bewertet hat."""
    record = latest_session(s)
    if record is None or person_id not in _members(record):
        return None
    if now - _aware(record.started_at) > MAX_AGE:
        return None
    rated = s.scalars(
        select(MorningRating).where(
            MorningRating.person_id == person_id, MorningRating.session_id == record.id
        )
    ).first()
    return None if rated else record


def recall_item(s: Session, record: SessionRecord, person_id: str) -> QuizItem | None:
    """Frage aus der Sendung von gestern, sonst die älteste fällige Wiederholung."""
    day = local_date(record.started_at)
    item = s.scalars(
        select(QuizItem)
        .where((QuizItem.session_id == record.id) | (QuizItem.aired_on == day))
        .order_by(QuizItem.created_at)
        .limit(1)
    ).first()
    if item is not None:
        return item
    state = s.scalars(
        select(ReviewState)
        .where(
            ReviewState.person_id == person_id,
            ReviewState.due.is_not(None),
            ReviewState.due <= local_date(datetime.now(UTC)),
        )
        .order_by(ReviewState.due)
        .limit(1)
    ).first()
    return s.get(QuizItem, state.item_id) if state else None


def card(db: Database, person_id: str, now: datetime) -> dict[str, Any] | None:
    if pool.is_guest(person_id):
        return None
    with db.session() as s:
        record = open_session(s, person_id, now)
        if record is None:
            return None
        item = recall_item(s, record, person_id)
        question = None
        if item is not None:
            question = {
                "item_id": item.id,
                "question": item.question,
                "options": pool.item_options(item),
            }
        return {
            "session_id": record.id,
            "day": date_de(local_date(record.started_at)),
            "question": question,
        }


def submit(
    db: Database,
    person_id: str,
    session_id: str,
    rating: int,
    answer: int | None,
    now: datetime,
) -> dict[str, Any]:
    """Bewertung speichern; Auflösung der Abruffrage erst nach der Antwort (SPEC §3)."""
    if not 1 <= rating <= 5:
        raise ValueError("Bewertung 1 bis 5 erwartet.")
    with db.session() as s:
        record = open_session(s, person_id, now)
        if record is None or record.id != session_id:
            raise LookupError("Für diese Sendung ist keine Bewertung offen.")
        item = recall_item(s, record, person_id)
        result: dict[str, Any] = {"rating": rating, "question": None}
        row = MorningRating(person_id=person_id, session_id=session_id, rating=rating)
        if item is not None and answer is not None:
            options = pool.item_options(item)
            if not 0 <= answer < len(options):
                raise ValueError("Diese Antwort gibt es nicht.")
            correct = answer == item.correct
            pool.record_answer(s, person_id, item.id, correct, local_date(now))
            row.item_id, row.answer, row.correct = item.id, answer, int(correct)
            result["question"] = {
                "correct": correct,
                "answer": options[item.correct],
                "source": item.source,
            }
        s.add(row)
        s.commit()
        return result


# ------------------------------------------------------------------ Frage nachlegen


async def ensure_tagesschau_item(db: Database) -> None:
    """Lief abends die tagesschau ohne Vorab-Frage, die Aufmacher-Frage nachlegen (Nr. 44).

    Die API führt die 20-Uhr-Ausgabe bis zur nächsten, morgens ist sie also noch da.
    """
    from abendausgabe.assembly.notausgabe import SOURCE_ERRORS
    from abendausgabe.modules.tagesschau import block as ts_block
    from abendausgabe.modules.tagesschau import fetch as ts_fetch

    with db.session() as s:
        record = latest_session(s)
        if record is None:
            return
        started = _aware(record.started_at).astimezone(BERLIN)
        day = started.date()
        if started.time() < EVENING:
            return
        if s.get(QuizItem, ts_block.aufmacher_item_id(day)) is not None:
            return
        session_id = record.id
    try:
        broadcasts = ts_block.parse_channels(await ts_fetch.channels())
    except SOURCE_ERRORS as exc:
        log.warning("Aufmacher-Frage nicht nachgelegt: %s", exc)
        return
    question = ts_block.aufmacher_question(broadcasts, datetime.combine(day, time(21, 0), BERLIN))
    if question is None:
        return
    spec = question["quiz_item"]
    with db.session() as s:
        pool.upsert_item(
            s,
            {
                **spec,
                "options": question["options"],
                "correct": question["correct"],
                "source": question["source"],
                "session_id": session_id,
            },
        )
        s.commit()


# --------------------------------------------------------------------------- Push


async def morning_job(
    db: Database,
    settings: Settings,
    now: datetime,
    transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    """Einmal pro Minute aufgerufen. Gibt die Zahl der verschickten Nachrichten zurück."""
    if settings.morning_push is None:
        return 0
    local = now.astimezone(BERLIN)
    start = datetime.combine(local.date(), settings.morning_push, BERLIN)
    if not start <= local < start + PUSH_WINDOW:
        return 0
    with db.session() as s:
        record = latest_session(s)
        if record is None or local_date(record.started_at) != local.date() - timedelta(days=1):
            return 0
    await ensure_tagesschau_item(db)
    sent = 0
    with db.session() as s:
        record = latest_session(s)
        if record is None:
            return 0
        for person_id in _members(record):
            topic = s.get(PushTopic, person_id)
            if topic is None or s.get(PushSent, (person_id, record.id)) is not None:
                continue
            if open_session(s, person_id, now) is None:
                continue  # schon beantwortet
            try:
                await push.publish(
                    settings.ntfy_url,
                    topic.topic,
                    PUSH_TITLE,
                    PUSH_MESSAGE,
                    click=topic.base_url.rstrip("/") + "/c/#morgen",
                    transport=transport,
                )
            except Exception as exc:  # Netz, ntfy, Ratelimit: beim nächsten Lauf erneut
                log.warning("Morgen-Push an %s fehlgeschlagen: %s", person_id, exc)
                continue
            s.add(PushSent(person_id=person_id, session_id=record.id))
            s.commit()
            sent += 1
    if sent:
        log.info("Morgen-Push verschickt: %d", sent)
    return sent
