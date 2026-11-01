"""Wetter vor acht über die MediathekViewWeb-API (Community-Projekt, docs/decisions.md Nr. 39)."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from abendausgabe import __version__
from abendausgabe.core import ratelimit

QUERY_URL = "https://mediathekviewweb.de/api/query"
USER_AGENT = f"Abendausgabe/{__version__} (privater Haushalt)"
CACHE_TTL_S = 600.0

_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


async def search(
    query: str, size: int = 5, transport: httpx.AsyncBaseTransport | None = None
) -> list[dict[str, Any]]:
    """Neueste Einträge zu Titel oder Thema, nur bereits ausgestrahlte."""
    cached = _cache.get(query)
    if cached and time.monotonic() - cached[0] < CACHE_TTL_S:
        return cached[1]
    body = {
        "queries": [{"fields": ["title", "topic"], "query": query}],
        "sortBy": "timestamp",
        "sortOrder": "desc",
        "future": False,
        "offset": 0,
        "size": size,
    }
    ratelimit.acquire("mediathekviewweb")
    async with httpx.AsyncClient(
        timeout=10.0, headers={"User-Agent": USER_AGENT}, transport=transport
    ) as client:
        # Die API erwartet JSON als text/plain
        response = await client.post(
            QUERY_URL, content=json.dumps(body), headers={"Content-Type": "text/plain"}
        )
        response.raise_for_status()
        data = response.json()
    if data.get("err"):
        raise ValueError(f"MediathekViewWeb: {data['err']}")
    results = list((data.get("result") or {}).get("results") or [])
    _cache[query] = (time.monotonic(), results)
    return results
