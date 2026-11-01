"""Datumsangaben auf Deutsch, Zeitzone Europe/Berlin."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONTHS = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]  # fmt: skip


def local_date(moment: datetime) -> date:
    """Kalendertag in Berlin; naive Zeitpunkte (SQLite) gelten als UTC."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(BERLIN).date()


def date_de(day: date) -> str:
    """„Sonntag, 1. November“."""
    return f"{WEEKDAYS[day.weekday()]}, {day.day}. {MONTHS[day.month - 1]}"
