"""Abruf vom Nutzer genannter Adressen, nur ins öffentliche Internet (decisions.md Nr. 56).

Schutz vor SSRF: nur https, nur Hosts mit ausschließlich öffentlichen IP-Adressen,
jede Weiterleitung wird neu geprüft, Antworten sind in der Größe begrenzt.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

MAX_BYTES = 512_000
MAX_REDIRECTS = 3


class UnsafeURLError(ValueError):
    pass


@dataclass(frozen=True)
class Fetched:
    url: str
    content_type: str
    body: bytes


def check_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme != "https" or not parts.hostname:
        raise UnsafeURLError("Nur https-Links sind erlaubt.")
    if parts.username or parts.password:
        raise UnsafeURLError("Links mit Zugangsdaten sind nicht erlaubt.")
    if parts.port not in (None, 443):
        raise UnsafeURLError("Nur der Standard-Port 443 ist erlaubt.")
    return parts.hostname


async def check_public(host: str) -> None:
    """Alle Adressen des Hosts müssen öffentlich sein, sonst kein Abruf."""
    try:
        ip = ipaddress.ip_address(host)
        addresses = [ip]
    except ValueError:
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise UnsafeURLError("Diese Adresse gibt es nicht.") from exc
        addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
    if not addresses or not all(a.is_global for a in addresses):
        raise UnsafeURLError("Adressen im Heimnetz oder privaten Netzen sind nicht erlaubt.")


async def fetch_public(url: str, client: httpx.AsyncClient) -> Fetched:
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        await check_public(check_url(current))
        async with client.stream("GET", current, follow_redirects=False) as response:
            if response.is_redirect:
                location = response.headers.get("location", "")
                current = urljoin(current, location)
                continue
            response.raise_for_status()
            body = b""
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > MAX_BYTES:
                    break
            return Fetched(current, response.headers.get("content-type", ""), body[:MAX_BYTES])
    raise UnsafeURLError("Zu viele Weiterleitungen.")
