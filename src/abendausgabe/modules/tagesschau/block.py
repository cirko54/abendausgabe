"""Tagesschau-Blöcke ohne LLM: welche Sendung läuft, und die Aufmacher-Frage.

Grundlage ist der Endpunkt `channels` der Tagesschau-API (docs/decisions.md Nr. 37).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
LIVE_START = time(19, 58)
LIVE_END = time(20, 16)
ATTRIBUTION = "tagesschau (ARD-aktuell)"
MAX_OPTION_CHARS = 110


@dataclass(frozen=True)
class Broadcast:
    id: str
    kind: str  # 20uhr | 100s | live | other
    title: str
    date: datetime | None
    mp4: str | None
    hls: str | None
    duration_s: int | None
    topics: list[str] = field(default_factory=list)


def _kind(channel: dict[str, Any]) -> str:
    title = str(channel.get("title") or "")
    tracking = channel.get("tracking") or []
    sids = " ".join(str(t.get("sid", "")) for t in tracking if isinstance(t, dict))
    if title.startswith("Im Livestream"):
        return "live"
    if "tagesschau_20_uhr" in sids:
        return "20uhr"
    if title.startswith("tagesschau in 100 Sekunden"):
        return "100s"
    return "other"


def _duration(channel: dict[str, Any]) -> int | None:
    for entry in channel.get("tracking") or []:
        if isinstance(entry, dict) and str(entry.get("length", "")).isdigit():
            return int(entry["length"])
    return None


def parse_channels(data: Any) -> list[Broadcast]:
    result: list[Broadcast] = []
    for channel in (data or {}).get("channels") or []:
        if not isinstance(channel, dict):
            continue
        streams = channel.get("streams") or {}
        mp4 = streams.get("h264xl") or streams.get("h264m") or streams.get("h264s")
        hls = streams.get("adaptivestreaming")
        raw_date = channel.get("date")
        date = datetime.fromisoformat(raw_date) if isinstance(raw_date, str) else None
        topics = [
            str(c["value"]).strip()
            for c in channel.get("content") or []
            if isinstance(c, dict) and c.get("type") == "text" and str(c.get("value", "")).strip()
        ]
        result.append(
            Broadcast(
                id=str(channel.get("sophoraId") or channel.get("externalId") or ""),
                kind=_kind(channel),
                title=str(channel.get("title") or ""),
                date=date,
                mp4=mp4 if isinstance(mp4, str) and mp4.startswith("https://") else None,
                hls=hls if isinstance(hls, str) and hls.startswith("https://") else None,
                duration_s=_duration(channel),
                topics=topics,
            )
        )
    return result


def _newest_today(broadcasts: list[Broadcast], kind: str, today: Any) -> Broadcast | None:
    candidates = [
        b
        for b in broadcasts
        if b.kind == kind and b.date and b.date.astimezone(BERLIN).date() == today
    ]
    return max(candidates, key=lambda b: b.date.timestamp() if b.date else 0.0, default=None)


def todays_20uhr(broadcasts: list[Broadcast], now: datetime) -> Broadcast | None:
    b = _newest_today(broadcasts, "20uhr", now.astimezone(BERLIN).date())
    return b if b and b.mp4 else None


def choose_media(broadcasts: list[Broadcast], now: datetime) -> dict[str, Any] | None:
    """Was beim Start des Blocks läuft: live um 20 Uhr, sonst die heutige Aufzeichnung."""
    local = now.astimezone(BERLIN)
    hundred = _newest_today(broadcasts, "100s", local.date())
    if LIVE_START <= local.time() < LIVE_END:
        live = next((b for b in broadcasts if b.kind == "live" and b.hls), None)
        if live is not None:
            return {
                "format": "hls",
                "src": live.hls,
                "live": True,
                "title": "tagesschau live",
                "attribution": ATTRIBUTION + ", Livestream tagesschau24",
                "duration_s": 900,
                "fallback_src": hundred.mp4 if hundred else None,
            }
    today = todays_20uhr(broadcasts, now)
    if today is not None:
        return {
            "format": "mp4",
            "src": today.mp4,
            "live": False,
            "title": "tagesschau, 20 Uhr",
            "attribution": ATTRIBUTION,
            "duration_s": today.duration_s,
            "fallback_src": None,
        }
    if hundred is not None and hundred.mp4:
        aired = hundred.date.astimezone(BERLIN).strftime("%H:%M") if hundred.date else ""
        return {
            "format": "mp4",
            "src": hundred.mp4,
            "live": False,
            "title": f"tagesschau in 100 Sekunden ({aired} Uhr)".replace(" ( Uhr)", ""),
            "attribution": ATTRIBUTION,
            "duration_s": hundred.duration_s,
            "fallback_src": None,
        }
    return None


def aufmacher_question(broadcasts: list[Broadcast], now: datetime) -> dict[str, Any] | None:
    """Erst raten, dann sehen: Womit beginnt die heutige 20-Uhr-Ausgabe?

    Richtig ist das erste Thema der Themenliste, Ablenker sind zwei weitere Themen
    derselben Sendung, alles wörtlich aus der Quelle.
    """
    today = todays_20uhr(broadcasts, now)
    if today is None or not today.topics:
        return None
    lead = today.topics[0]
    others = [
        t for t in dict.fromkeys(today.topics[1:]) if t != lead and len(t) <= MAX_OPTION_CHARS
    ]
    if len(others) < 2:
        return None
    rng = random.Random(today.id)  # stabil für dieselbe Sendung
    options = [lead, *rng.sample(others, 2)]
    rng.shuffle(options)
    return {
        "id": "tagesschau-aufmacher",
        "type": "choice",
        "title": "Vorab",
        "question": "Womit macht die tagesschau heute auf?",
        "options": options,
        "correct": options.index(lead),
        "source": "tagesschau, 20 Uhr: Themen der Sendung",
        "timeout_s": 45,
        "est_minutes": 1,
    }


def video_block(broadcasts: list[Broadcast], now: datetime) -> dict[str, Any]:
    """Der Block selbst; welche Sendung läuft, entscheidet /api/media/tagesschau beim Start."""
    today = todays_20uhr(broadcasts, now)
    minutes = round((today.duration_s or 900) / 60) if today else 15
    return {
        "id": "tagesschau",
        "type": "video",
        "title": "tagesschau",
        "media": "tagesschau",
        "est_minutes": minutes,
    }
