"""Weltblick-Blöcke ohne LLM (decisions.md Nr. 52).

Zwei Raterunden „Aus welchem Land kommt diese Meldung?“ mit Bild und Originalschlagzeile,
dazu ein Kurzvideo. Alles aus der Datenbank (raw_item), damit der Sendestart nicht wartet.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select

from abendausgabe.core.db import Database
from abendausgabe.core.models import RawItem
from abendausgabe.modules.weltblick.catalog import Source

FRESH = timedelta(hours=36)
ROUNDS = 2

COUNTRY_DE = {
    "AF": "Afghanistan", "AL": "Albanien", "AR": "Argentinien", "AU": "Australien",
    "BA": "Bosnien und Herzegowina", "BD": "Bangladesch", "BR": "Brasilien", "CG": "Kongo",
    "CL": "Chile", "EG": "Ägypten", "ET": "Äthiopien", "GB": "Großbritannien", "GH": "Ghana",
    "HR": "Kroatien", "ID": "Indonesien", "IN": "Indien", "IR": "Iran", "JP": "Japan",
    "KE": "Kenia", "LK": "Sri Lanka", "ME": "Montenegro", "MK": "Nordmazedonien",
    "MX": "Mexiko", "NG": "Nigeria", "NP": "Nepal", "NZ": "Neuseeland", "PH": "Philippinen",
    "PK": "Pakistan", "PL": "Polen", "QA": "Katar", "RS": "Serbien", "RU": "Russland",
    "SN": "Senegal", "UA": "Ukraine", "US": "USA", "UY": "Uruguay", "XK": "Kosovo",
    "ZA": "Südafrika",
}  # fmt: skip
# Ablenker aus der Nachbarschaft machen das Raten interessanter als Zufallsländer
NEIGHBOURS = {
    "IN": ["PK", "BD", "NP", "LK"], "PK": ["IN", "AF", "IR", "BD"], "AF": ["PK", "IR", "IN"],
    "RS": ["HR", "BA", "MK", "ME", "XK"], "UA": ["RU", "PL"], "RU": ["UA", "PL"],
    "AU": ["NZ", "PH", "ID"], "NG": ["GH", "KE", "SN"], "CG": ["NG", "KE", "SN"],
    "UY": ["AR", "BR", "CL"],
}  # fmt: skip


def _fresh_items(db: Database, now: datetime, today: date) -> list[RawItem]:
    with db.session() as s:
        rows = s.scalars(
            select(RawItem).where(
                RawItem.published_at >= (now - FRESH).astimezone(UTC),
                (RawItem.shown_on.is_(None)) | (RawItem.shown_on == today),
            )
        ).all()
        return list(rows)


def _distractors(country: str, pool: list[str], rng: random.Random) -> list[str]:
    near = [c for c in NEIGHBOURS.get(country, []) if c in COUNTRY_DE and c != country]
    rest = [c for c in pool if c != country and c not in near]
    rng.shuffle(near)
    rng.shuffle(rest)
    return (near + rest)[:2]


def _source_line(item: RawItem, sources: dict[str, Source]) -> str:
    source = sources.get(item.source_id)
    name = source.name if source else item.source_id
    day = item.published_at.replace(tzinfo=item.published_at.tzinfo or UTC)
    return f"{name}, {day.astimezone(UTC).strftime('%d.%m.%Y')}"


def guess_rounds(
    items: list[RawItem], sources: dict[str, Source], rng: random.Random
) -> list[dict[str, Any]]:
    candidates = [i for i in items if i.country in COUNTRY_DE and i.image]
    rng.shuffle(candidates)
    pool = sorted({i.country for i in candidates} | set(NEIGHBOURS))
    # eine Runde in einer Sprache außer Englisch, falls vorhanden; sonst bunt gemischt
    foreign = [i for i in candidates if i.language != "en"]
    ordered = foreign[:1] + [i for i in candidates if i not in foreign[:1]]
    chosen: list[RawItem] = []
    for item in ordered:
        if item.country not in {c.country for c in chosen}:
            chosen.append(item)
        if len(chosen) == ROUNDS:
            break
    blocks = []
    for n, item in enumerate(chosen, start=1):
        options = [item.country, *_distractors(item.country, pool, rng)]
        rng.shuffle(options)
        blocks.append(
            {
                "id": f"weltblick-{n}",
                "type": "choice",
                "title": "Weltblick",
                "question": "Aus welchem Land kommt diese Meldung?",
                "caption": item.title,
                "caption_lang": item.language,
                "media": {"kind": "image", "src": item.image},
                "options": [COUNTRY_DE[c] for c in options],
                "correct": options.index(item.country),
                "source": _source_line(item, sources),
                "link": item.url,
                "raw_item_id": item.id,
                "timeout_s": 45,
                "est_minutes": 1,
            }
        )
    return blocks


def video_round(
    items: list[RawItem], sources: dict[str, Source], rng: random.Random
) -> dict[str, Any] | None:
    videos = [i for i in items if i.video_json]
    if not videos:
        return None
    item = rng.choice(sorted(videos, key=lambda i: i.id))
    video = json.loads(item.video_json or "{}")
    return {
        "id": "weltblick-video",
        "type": "video",
        "title": "Weltblick",
        "src": video["src"],
        "format": "hls",
        "poster": video.get("poster"),
        "vertical": bool(video.get("vertical")),
        "muted": True,  # startet stumm mit Text; ▲ schaltet den Ton ein (Nr. 48)
        "caption": item.title,
        "caption_lang": item.language,
        "attribution": _source_line(item, sources),
        "link": item.url,
        "raw_item_id": item.id,
        "est_minutes": 1,
    }


def weltblick_blocks(
    db: Database, sources: list[Source], now: datetime
) -> list[dict[str, Any]]:
    """Stabil für denselben Tag: Ein erneutes Zusammenstellen in der Lobby ändert nichts."""
    today = now.date()
    rng = random.Random(today.isoformat())
    by_id = {s.id: s for s in sources}
    items = sorted(_fresh_items(db, now, today), key=lambda i: i.id)
    blocks = guess_rounds(items, by_id, rng)
    video = video_round(items, by_id, rng)
    if video:
        blocks.append(video)
    return blocks


def mark_shown(db: Database, rundown: list[dict[str, Any]], today: date) -> None:
    """Beim Sendestart: Gezeigtes kommt an späteren Tagen nicht wieder."""
    ids = [str(b["raw_item_id"]) for b in rundown if b.get("raw_item_id")]
    if not ids:
        return
    with db.session() as s:
        for item in s.scalars(select(RawItem).where(RawItem.id.in_(ids))):
            item.shown_on = today
        s.commit()
