"""Übersetzungen der Schlagzeilen auf dem Server speichern (decisions.md Nr. 63).

Die Redaktion auf dem Mac holt offene Schlagzeilen und schreibt Übersetzungen zurück.
Übersetzt wird nur, was in der Sendung vorkommen kann: frisch, mit Bild oder Video.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from abendausgabe.core.db import Database
from abendausgabe.core.models import RawItem, Translation

WINDOW = timedelta(hours=48)
MAX_TEXT = 400


@dataclass(frozen=True)
class Pending:
    id: str
    title: str
    language: str


def pending(
    db: Database, now: datetime, prompt_version: str, target: str = "de", limit: int = 300
) -> list[Pending]:
    with db.session() as s:
        done = select(Translation.raw_item_id).where(
            Translation.language == target, Translation.prompt_version == prompt_version
        )
        rows = s.scalars(
            select(RawItem)
            .where(
                RawItem.published_at >= (now - WINDOW).astimezone(UTC),
                RawItem.language != target,
                RawItem.language != "",
                (RawItem.image.is_not(None)) | (RawItem.video_json.is_not(None)),
                RawItem.id.not_in(done),
            )
            .order_by(RawItem.published_at.desc())
            .limit(limit)
        ).all()
        return [Pending(r.id, r.title, r.language) for r in rows]


def save(
    db: Database,
    items: list[tuple[str, str]],
    model: str,
    prompt_version: str,
    target: str = "de",
) -> int:
    """(raw_item_id, Text); unbekannte oder abgelaufene Beiträge werden übergangen."""
    saved = 0
    with db.session() as s:
        for raw_item_id, text in items:
            text = " ".join(text.split())[:MAX_TEXT]
            if not text or s.get(RawItem, raw_item_id) is None:
                continue
            row = s.get(Translation, (raw_item_id, target))
            if row is None:
                row = Translation(raw_item_id=raw_item_id, language=target)
                s.add(row)
            row.text, row.model, row.prompt_version = text, model[:80], prompt_version[:16]
            row.created_at = datetime.now(UTC)
            saved += 1
        s.commit()
    return saved
