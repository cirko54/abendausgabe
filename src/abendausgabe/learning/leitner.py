"""Leitner-Wiederholung mit den Abständen 3, 10 und 30 Tage (SPEC §8.6, decisions.md Nr. 44).

Rein und testbar: keine Datenbank, nur Box und Fälligkeit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

INTERVAL_DAYS = {1: 3, 2: 10, 3: 30}
LEARNED = 4


@dataclass(frozen=True)
class Box:
    box: int
    due: date | None  # None, wenn gelernt


def _box(box: int, today: date) -> Box:
    if box >= LEARNED:
        return Box(LEARNED, None)
    return Box(box, today + timedelta(days=INTERVAL_DAYS[box]))


def first_encounter(today: date) -> Box:
    """Erste Begegnung, richtig oder falsch: Box 1, in 3 Tagen wieder."""
    return _box(1, today)


def review(current: Box, correct: bool, today: date) -> Box:
    """Antwort auf eine Wiederholung.

    Richtig rückt nur vor, wenn die Frage fällig war; zu früh wiederholt bringt nichts.
    Falsch setzt immer auf Box 1 zurück.
    """
    if not correct:
        return _box(1, today)
    if current.due is None or current.due > today:
        return current
    return _box(current.box + 1, today)
