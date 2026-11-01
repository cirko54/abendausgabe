"""Push über ntfy (decisions.md Nr. 46): zufälliges Topic pro Person, minimaler Inhalt.

Veröffentlicht als JSON an die Wurzel des Servers, damit Umlaute im Titel sicher ankommen.
"""

from __future__ import annotations

import secrets

import httpx

from abendausgabe import __version__
from abendausgabe.core import ratelimit

USER_AGENT = f"Abendausgabe/{__version__} (privater Haushalt)"


def new_topic() -> str:
    """128 Bit Zufall; wer das Topic kennt, kann mitlesen, deshalb nie erratbar."""
    return "abend-" + secrets.token_hex(16)


def subscribe_links(server: str, topic: str) -> dict[str, str]:
    host = server.split("://", 1)[-1].rstrip("/")
    return {"app": f"ntfy://{host}/{topic}", "web": f"{server.rstrip('/')}/{topic}"}


async def publish(
    server: str,
    topic: str,
    title: str,
    message: str,
    click: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    ratelimit.acquire("ntfy")
    body: dict[str, object] = {"topic": topic, "title": title, "message": message, "tags": ["tv"]}
    if click:
        body["click"] = click
    async with httpx.AsyncClient(
        timeout=10.0, headers={"User-Agent": USER_AGENT}, transport=transport
    ) as client:
        response = await client.post(server.rstrip("/") + "/", json=body)
        response.raise_for_status()
