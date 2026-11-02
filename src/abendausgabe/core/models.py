"""Tabellen für Phase 0. Erweiterungen laut SPEC §12."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from abendausgabe.core.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class PersonClaim(Base):
    """PIN einer Person; gesetzt bei der ersten Anmeldung."""

    __tablename__ = "person_claim"
    person_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pin_hash: Mapped[str] = mapped_column(String(128))
    salt: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Device(Base):
    __tablename__ = "device"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    person_id: Mapped[str] = mapped_column(String(64), index=True)
    display_name: Mapped[str] = mapped_column(String(64))
    user_agent: Mapped[str] = mapped_column(String(400), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProfileAnswer(Base):
    __tablename__ = "profile_answer"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer)
    answers_json: Mapped[str] = mapped_column(Text)
    visibility: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TvCheckReport(Base):
    __tablename__ = "tv_check_report"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user_agent: Mapped[str] = mapped_column(String(400), default="")
    report_json: Mapped[str] = mapped_column(Text)
    verdict_code: Mapped[str] = mapped_column(String(4))
    verdict_json: Mapped[str] = mapped_column(Text)


class SessionRecord(Base):
    """Eine Sendung."""

    __tablename__ = "session_record"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    members_json: Mapped[str] = mapped_column(Text, default="[]")


class Interaction(Base):
    """Jede Eingabe und jedes Ereignis der Sendung, Grundlage der Metriken (SPEC §2)."""

    __tablename__ = "interaction"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    session_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    person_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    block_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kind: Mapped[str] = mapped_column(String(32))
    payload_json: Mapped[str] = mapped_column(Text, default="{}")


class QuizItem(Base):
    """Eine Frage im Wiederholungspool (SPEC §8.6). Wortlaut und Optionen stammen aus der Quelle."""

    __tablename__ = "quiz_item"
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    aired_on: Mapped[date] = mapped_column(Date, index=True)
    session_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    question: Mapped[str] = mapped_column(Text)
    options_json: Mapped[str] = mapped_column(Text)
    correct: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(300), default="")


class ReviewState(Base):
    """Leitner-Box einer Person für eine Frage; box 4 heißt gelernt (decisions.md Nr. 44)."""

    __tablename__ = "review_state"
    person_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    box: Mapped[int] = mapped_column(Integer)
    due: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    last_correct: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MorningRating(Base):
    """Morgen danach: Bewertung 1–5 und Abruffrage zu einer Sendung (SPEC §2)."""

    __tablename__ = "morning_rating"
    __table_args__ = (UniqueConstraint("person_id", "session_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str] = mapped_column(String(32), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    item_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    answer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PushTopic(Base):
    """ntfy-Topic einer Person; freiwillig, im Profil eingeschaltet (decisions.md Nr. 46)."""

    __tablename__ = "push_topic"
    person_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    topic: Mapped[str] = mapped_column(String(64))
    base_url: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PushSent(Base):
    """Verschickte Morgen-Nachricht, damit ein Neustart keine doppelten sendet."""

    __tablename__ = "push_sent"
    person_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RawItem(Base):
    """Abgerufener Beitrag einer Quelle (SPEC §12). Nur Metadaten und Links, mit Ablaufzeit."""

    __tablename__ = "raw_item"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    url: Mapped[str] = mapped_column(String(600))
    title: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(16), default="")
    country: Mapped[str] = mapped_column(String(8), default="")  # leer: weltweit
    image: Mapped[str | None] = mapped_column(String(600), nullable=True)
    video_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    shown_on: Mapped[date | None] = mapped_column(Date, nullable=True)
