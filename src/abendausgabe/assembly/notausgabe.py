"""Notausgabe (SPEC §11.5): Tagesablauf ohne LLM und ohne Mac.

Seit Phase 1, Schritt 2 (docs/decisions.md Nr. 37): Begrüßung, Wetter vor acht,
Aufmacher-Frage, tagesschau, ab Schritt 4 Weltblick (Nr. 52), Sendeschluss.
Fällt eine Quelle aus, entfällt ihr Block; Begrüßung und Sendeschluss gibt es immer.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from abendausgabe.core import ratelimit
from abendausgabe.core.dates import BERLIN, date_de
from abendausgabe.core.db import Database
from abendausgabe.modules.tagesschau import block as ts_block
from abendausgabe.modules.tagesschau import fetch as ts_fetch
from abendausgabe.modules.weltblick import block as weltblick_block
from abendausgabe.modules.weltblick.catalog import Source
from abendausgabe.modules.wetter_himmel import block as wetter_block
from abendausgabe.modules.wetter_himmel import fetch as wetter_fetch
from abendausgabe.session.rundown import validate_rundown

log = logging.getLogger(__name__)

SOURCE_ERRORS = (httpx.HTTPError, ratelimit.RateLimitedError, ValueError, KeyError, TypeError)
def _date_de(now: datetime) -> str:
    return date_de(now.astimezone(BERLIN).date())


async def build_program(
    now: datetime, db: Database | None = None, sources: list[Source] | None = None
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    parts: list[str] = []

    try:
        weather = wetter_block.wetter_vor_acht_block(
            await wetter_fetch.search(wetter_block.TOPIC), now
        )
    except SOURCE_ERRORS as exc:
        log.warning("Wetter vor acht nicht verfügbar: %s", exc)
        weather = None
    if weather:
        blocks.append(weather)
        parts.append("Wetter")

    try:
        broadcasts = ts_block.parse_channels(await ts_fetch.channels())
    except SOURCE_ERRORS as exc:
        log.warning("tagesschau nicht verfügbar: %s", exc)
        broadcasts = None
    if broadcasts is not None:
        question = ts_block.aufmacher_question(broadcasts, now)
        if question:
            blocks.append(question)
        blocks.append(ts_block.video_block(broadcasts, now))
        parts.append("tagesschau")

    # Weltblick aus der Datenbank (Abruf im Hintergrund, decisions.md Nr. 51)
    if db is not None and sources:
        world = weltblick_block.weltblick_blocks(db, sources, now.astimezone(BERLIN))
        if world:
            blocks.extend(world)
            parts.append("Weltblick")

    listed = ", ".join(parts[:-1]) + " und " + parts[-1] if len(parts) > 1 else "".join(parts)
    intro = f"Heute: {listed}." if parts else (
        "Heute sind keine Beiträge erreichbar. Prüft die Internetverbindung des Servers."
    )
    greeting = {
        "id": "begruessung",
        "type": "info",
        "title": "Guten Abend",
        "body": f"Die Abendausgabe vom {_date_de(now)}. {intro}",
        "est_minutes": 1,
    }
    end = {"id": "ende", "type": "end", "title": "Sendeschluss", "est_minutes": 0}
    return validate_rundown([greeting, *blocks, end])
