"""Tagesschau-API (www.tagesschau.de/api2u/): höchstens 60 Abrufe pro Stunde.

Phase 0 nutzt sie nur, um echte Video-URLs für den TV-Fähigkeitstest zu finden.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from abendausgabe import __version__
from abendausgabe.core import ratelimit

BASE_URL = "https://www.tagesschau.de/api2u/"
USER_AGENT = f"Abendausgabe/{__version__} (privater Haushalt)"
CACHE_TTL_S = 600.0

_cache: dict[str, tuple[float, Any]] = {}


def make_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    # follow_redirects: Die API leitet Pfade mit Schrägstrich am Ende per 308 um
    # (am echten Fernseher-Test vom 31.10.2026 aufgefallen).
    return httpx.AsyncClient(
        timeout=10.0,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        transport=transport,
    )


async def get_json(endpoint: str, transport: httpx.AsyncBaseTransport | None = None) -> Any:
    cached = _cache.get(endpoint)
    if cached and time.monotonic() - cached[0] < CACHE_TTL_S:
        return cached[1]
    ratelimit.acquire("tagesschau")
    async with make_client(transport) as client:
        response = await client.get(BASE_URL + endpoint)
        response.raise_for_status()
        data = response.json()
    _cache[endpoint] = (time.monotonic(), data)
    return data


def find_media_urls(obj: Any) -> dict[str, list[str]]:
    """Sammelt rekursiv alle HLS- (.m3u8) und MP4-URLs in einer API-Antwort."""
    found: dict[str, list[str]] = {"hls": [], "mp4": []}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str) and node.startswith(("http://", "https://")):
            path = node.split("?", 1)[0].lower()
            if path.endswith(".m3u8") and node not in found["hls"]:
                found["hls"].append(node)
            elif path.endswith(".mp4") and node not in found["mp4"]:
                found["mp4"].append(node)

    walk(obj)
    return found


async def media_for_check() -> dict[str, Any]:
    result: dict[str, Any] = {"hls": None, "mp4": None, "error": None}
    try:
        channels = find_media_urls(await get_json("channels"))
        result["hls"] = channels["hls"][0] if channels["hls"] else None
        if channels["mp4"]:
            result["mp4"] = channels["mp4"][0]
        if result["mp4"] is None or result["hls"] is None:
            homepage = find_media_urls(await get_json("homepage"))
            result["mp4"] = result["mp4"] or (homepage["mp4"][0] if homepage["mp4"] else None)
            result["hls"] = result["hls"] or (homepage["hls"][0] if homepage["hls"] else None)
    except (httpx.HTTPError, ratelimit.RateLimitedError, ValueError) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result
