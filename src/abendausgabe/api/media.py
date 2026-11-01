"""Medien, die erst beim Start eines Blocks feststehen (docs/decisions.md Nr. 37)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from abendausgabe.assembly.notausgabe import SOURCE_ERRORS
from abendausgabe.modules.tagesschau import block as ts_block
from abendausgabe.modules.tagesschau import fetch as ts_fetch

router = APIRouter(prefix="/api/media")


@router.get("/{name}")
async def resolve(name: str) -> dict[str, Any]:
    if name != "tagesschau":
        raise HTTPException(status_code=404, detail="Unbekannte Medienquelle.")
    try:
        broadcasts = ts_block.parse_channels(await ts_fetch.channels())
    except SOURCE_ERRORS as exc:
        return {"media": None, "error": f"tagesschau nicht erreichbar ({type(exc).__name__})."}
    media = ts_block.choose_media(broadcasts, datetime.now(ts_block.BERLIN))
    if media is None:
        return {"media": None, "error": "Heute gibt es noch keine tagesschau-Aufzeichnung."}
    return {"media": media, "error": None}
