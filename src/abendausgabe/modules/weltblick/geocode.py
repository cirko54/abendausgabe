"""Geokodierung über Nominatim für die Redaktion (decisions.md Nr. 64).

Höchstens 1 Anfrage pro Sekunde, eigener User-Agent, Cache in der Redaktionsdatei auf
dem Mac (CLAUDE.md). Auch leere Antworten werden gemerkt.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from abendausgabe.core import ratelimit
from abendausgabe.modules.weltblick.fetch import USER_AGENT

NOMINATIM = "https://nominatim.openstreetmap.org/search"


@dataclass(frozen=True)
class Hit:
    country: str  # ISO-Alpha-2, groß
    lat: float
    lon: float


class Geocoder:
    def __init__(self, store: Path, client: httpx.Client | None = None) -> None:
        store.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(store)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS geocode_cache ("
            " query TEXT PRIMARY KEY, result TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        self.client = client or httpx.Client(timeout=20.0, headers={"User-Agent": USER_AGENT})

    def lookup(self, place: str) -> Hit | None:
        query = " ".join(place.split()).lower()
        row = self.conn.execute(
            "SELECT result FROM geocode_cache WHERE query = ?", (query,)
        ).fetchone()
        if row is not None:
            data = json.loads(row[0])
        else:
            ratelimit.wait("nominatim")
            response = self.client.get(
                NOMINATIM,
                params={"q": place, "format": "jsonv2", "limit": 1, "addressdetails": 1,
                        "accept-language": "de"},
            )  # fmt: skip
            response.raise_for_status()
            data = response.json()
            self.conn.execute(
                "INSERT OR REPLACE INTO geocode_cache (query, result, created_at) VALUES (?, ?, ?)",
                (query, json.dumps(data), datetime.now(UTC).isoformat()),
            )
            self.conn.commit()
        if not data:
            return None
        first = data[0]
        code = str((first.get("address") or {}).get("country_code", "")).upper()
        if len(code) != 2:
            return None
        return Hit(code, float(first["lat"]), float(first["lon"]))
