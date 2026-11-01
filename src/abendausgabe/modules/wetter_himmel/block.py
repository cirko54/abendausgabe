"""Wetter vor acht als Videoblock; nur die Ausgabe von heute (docs/decisions.md Nr. 37)."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
TOPIC = "wetter vor acht"


def wetter_vor_acht_block(results: list[dict[str, Any]], now: datetime) -> dict[str, Any] | None:
    today = now.astimezone(BERLIN).date()
    for entry in results:
        if str(entry.get("topic", "")).strip().lower() != TOPIC:
            continue
        if entry.get("channel") != "ARD":
            continue
        try:
            aired = datetime.fromtimestamp(int(entry["timestamp"]), BERLIN)
        except (KeyError, TypeError, ValueError):
            continue
        if aired.date() != today:
            continue
        src = entry.get("url_video_hd") or entry.get("url_video")
        if not isinstance(src, str) or not src.startswith("https://"):
            continue
        duration = int(entry.get("duration") or 180)
        return {
            "id": "wetter-vor-acht",
            "type": "video",
            "title": "Wetter vor acht",
            "src": src,
            "format": "mp4",
            "duration_s": duration,
            "attribution": "Das Erste (ARD), gefunden über MediathekViewWeb",
            "est_minutes": max(1, math.ceil(duration / 60)),
        }
    return None
