"""Tagesschau-Blöcke ohne LLM: welche Sendung läuft, und die Aufmacher-Frage.

Grundlage ist der Endpunkt `channels` der Tagesschau-API (docs/decisions.md Nr. 37).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any

from abendausgabe.core.dates import BERLIN, date_de

LIVE_START = time(19, 58)
BROADCAST_START = time(20, 0)
BROADCAST_SECONDS = 900
# tagesschau24 hält im Livestream zwei Stunden vor (EXT-X-PROGRAM-DATE-TIME, decisions.md Nr. 42).
# Zeitversetzt starten, solange der Anfang sicher noch im Fenster liegt.
TIMESHIFT_LIMIT = timedelta(minutes=100)
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
    start: int | None = None  # Unix-Zeit, nur bei „Aktuelle Sendung“
    end: int | None = None


def _kind(channel: dict[str, Any]) -> str:
    title = str(channel.get("title") or "")
    tracking = channel.get("tracking") or []
    sids = " ".join(str(t.get("sid", "")) for t in tracking if isinstance(t, dict))
    if title.startswith("Im Livestream"):
        return "live"
    if title.startswith("Aktuelle Sendung") and "20 Uhr" in title:
        return "live20"
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


def _epoch(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) and value > 0 else None


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
                start=_epoch(channel.get("start")),
                end=_epoch(channel.get("end")),
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


def broadcast_window(broadcasts: list[Broadcast], now: datetime) -> tuple[int, int]:
    """Beginn und Ende der heutigen 20-Uhr-Ausgabe als Unix-Zeit.

    Während der Sendung nennt die API beides („Aktuelle Sendung“), sonst gilt 20:00 plus 15 min.
    """
    local = now.astimezone(BERLIN)
    for b in broadcasts:
        if (
            b.kind == "live20"
            and b.start
            and b.end
            and datetime.fromtimestamp(b.start, BERLIN).date() == local.date()
        ):
            return b.start, b.end
    start = int(datetime.combine(local.date(), BROADCAST_START, BERLIN).timestamp())
    return start, start + BROADCAST_SECONDS


def choose_media(broadcasts: list[Broadcast], now: datetime) -> dict[str, Any] | None:
    """Was beim Start des Blocks läuft.

    1. die heutige Aufzeichnung, sobald sie veröffentlicht ist
    2. sonst ab 19:58 der Livestream; nach 20 Uhr springt der Fernseher an den Anfang
       der Sendung (zeitversetzt) und hält am Ende an
    3. sonst die neuesten 100 Sekunden von heute
    """
    local = now.astimezone(BERLIN)
    hundred = _newest_today(broadcasts, "100s", local.date())
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
    start, end = broadcast_window(broadcasts, now)
    stream = next((b for b in broadcasts if b.kind in ("live20", "live") and b.hls), None)
    started = datetime.fromtimestamp(start, BERLIN)
    in_reach = local.time() >= LIVE_START and local - started < TIMESHIFT_LIMIT
    if stream is not None and in_reach:
        shifted = local.timestamp() - start > 60
        return {
            "format": "hls",
            "src": stream.hls,
            "live": not shifted,
            "title": "tagesschau, 20 Uhr (zeitversetzt)" if shifted else "tagesschau live",
            "attribution": ATTRIBUTION + ", Livestream tagesschau24",
            "duration_s": end - start,
            "start_at": start if local.timestamp() >= start else None,
            "end_at": end,
            "fallback_src": hundred.mp4 if hundred else None,
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
        # Für die Wiederholung (decisions.md Nr. 44): dieselbe Frage, später mit Datum
        "quiz_item": aufmacher_item_spec(today),
        "timeout_s": 45,
        "est_minutes": 1,
    }


def aufmacher_item_id(day: Any) -> str:
    return f"tagesschau-aufmacher-{day.isoformat()}"


def aufmacher_item_spec(broadcast: Broadcast) -> dict[str, Any]:
    day = (broadcast.date or datetime.now(BERLIN)).astimezone(BERLIN).date()
    return {
        "id": aufmacher_item_id(day),
        "question": f"Womit machte die tagesschau am {date_de(day)} auf?",
        "aired_on": day.isoformat(),
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
