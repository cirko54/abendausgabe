"""Tabellen für Phase 0. Erweiterungen laut SPEC §12."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
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
