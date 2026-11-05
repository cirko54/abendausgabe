"""Ergebnisse der Redaktion zu Schlagzeilen speichern (decisions.md Nr. 63, 64).

Die Redaktion auf dem Mac holt offene Schlagzeilen und schreibt Übersetzungen zurück.
Übersetzt wird nur, was in der Sendung vorkommen kann: frisch, mit Bild oder Video.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from abendausgabe.core.db import Database
from abendausgabe.core.models import ItemPlace, RawItem, Translation

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


# ------------------------------------------------------------------- Orte (Nr. 64)


@dataclass(frozen=True)
class PendingPlace:
    id: str
    title: str  # Original
    text: str  # deutsch: Übersetzung oder das Original, wenn es schon deutsch ist
    language: str


@dataclass(frozen=True)
class Place:
    raw_item_id: str
    country: str
    place: str
    lat: float | None
    lon: float | None


def pending_places(
    db: Database, now: datetime, prompt_version: str, limit: int = 300
) -> list[PendingPlace]:
    """Nur Beiträge mit Bild (Raterunde) und mit deutschem Text."""
    with db.session() as s:
        done = select(ItemPlace.raw_item_id).where(ItemPlace.prompt_version == prompt_version)
        rows = s.execute(
            select(RawItem, Translation.text)
            .outerjoin(
                Translation,
                (Translation.raw_item_id == RawItem.id) & (Translation.language == "de"),
            )
            .where(
                RawItem.published_at >= (now - WINDOW).astimezone(UTC),
                RawItem.image.is_not(None),
                RawItem.id.not_in(done),
                (RawItem.language == "de") | Translation.text.is_not(None),
            )
            .order_by(RawItem.published_at.desc())
            .limit(limit)
        ).all()
        return [PendingPlace(r.id, r.title, text or r.title, r.language) for r, text in rows]


def save_places(db: Database, places: list[Place], model: str, prompt_version: str) -> int:
    saved = 0
    with db.session() as s:
        for p in places:
            if s.get(RawItem, p.raw_item_id) is None:
                continue
            row = s.get(ItemPlace, p.raw_item_id)
            if row is None:
                row = ItemPlace(raw_item_id=p.raw_item_id)
                s.add(row)
            country = p.country.upper() if len(p.country) == 2 and p.country.isalpha() else ""
            row.country, row.place = country, p.place[:200]
            row.lat, row.lon = p.lat, p.lon
            row.model, row.prompt_version = model[:80], prompt_version[:16]
            row.created_at = datetime.now(UTC)
            saved += 1
        s.commit()
    return saved
