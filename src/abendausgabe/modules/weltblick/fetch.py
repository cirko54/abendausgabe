"""Abruf der Katalogquellen auf dem Server (decisions.md Nr. 48, 51).

RSS/Atom über feedparser, Bluesky über die öffentliche API ohne Konto. Gespeichert werden
nur Titel, Links und Medien-URLs mit Ablaufzeit; Bilder und Videos werden nie geladen.
"""

from __future__ import annotations

import asyncio
import calendar
import hashlib
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import feedparser  # type: ignore[import-untyped]
import httpx
from sqlalchemy import select

from abendausgabe import __version__
from abendausgabe.core import ratelimit
from abendausgabe.core.db import Database
from abendausgabe.core.models import ItemPlace, RawItem, Translation
from abendausgabe.modules.weltblick.catalog import Source

log = logging.getLogger(__name__)

USER_AGENT = f"Abendausgabe/{__version__} (privater Haushalt)"
BLUESKY_FEED = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
TTL = timedelta(days=3)
MIN_IMAGE_WIDTH = 400
CONCURRENCY = 4
MAX_TITLE = 300


def _id(source_id: str, url: str) -> str:
    return hashlib.sha1(f"{source_id}|{url}".encode()).hexdigest()


def _https(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("http://"):
        url = "https://" + url[len("http://") :]
    return url if url.startswith("https://") else None


def _upscale(url: str) -> str:
    # BBC liefert im Feed 240 px; dieselbe Datei gibt es in 976 px (geprüft 2.11.2026)
    return re.sub(r"ichef\.bbci\.co\.uk/ace/ws/240/", "ichef.bbci.co.uk/ace/standard/976/", url)


def _width(entry: dict[str, Any]) -> int:
    try:
        return int(entry.get("width") or 0)
    except (TypeError, ValueError):
        return 0


def rss_image(entry: Any) -> str | None:
    """Größtes Bild aus media:content, sonst Vorschaubild oder Bild-Enclosure."""
    candidates: list[tuple[int, str]] = []
    for media in entry.get("media_content") or []:
        if str(media.get("medium", "image")) == "image" and media.get("url"):
            candidates.append((_width(media), str(media["url"])))
    for thumb in entry.get("media_thumbnail") or []:
        if thumb.get("url"):
            candidates.append((_width(thumb), str(thumb["url"])))
    for enc in entry.get("enclosures") or []:
        if str(enc.get("type", "")).startswith("image") and enc.get("href"):
            candidates.append((_width(enc), str(enc["href"])))
    if not candidates:
        return None
    width, url = max(candidates, key=lambda c: c[0])
    url = _upscale(url)
    known_small = 0 < width < MIN_IMAGE_WIDTH and "ichef.bbci.co.uk/ace/standard/976" not in url
    if known_small or re.search(r"/\d{2,3}x\d{2,3}/", url):
        return None
    return _https(url)


def _published(entry: Any, now: datetime) -> datetime:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime.fromtimestamp(calendar.timegm(parsed), UTC)
    return now


def parse_rss(source: Source, content: bytes, now: datetime) -> list[dict[str, Any]]:
    feed = feedparser.parse(content)
    items = []
    for entry in feed.entries:
        url = _https(entry.get("link"))
        title = re.sub(r"\s+", " ", str(entry.get("title") or "")).strip()
        if not url or not title:
            continue
        items.append(
            {
                "id": _id(source.id, url),
                "url": url,
                "title": title[:MAX_TITLE],
                "image": rss_image(entry),
                "video": None,
                "published_at": _published(entry, now),
            }
        )
    return items


def parse_bluesky(source: Source, data: Any, now: datetime) -> list[dict[str, Any]]:
    items = []
    for row in (data or {}).get("feed") or []:
        post = row.get("post") or {}
        if row.get("reason"):  # Reposts fremder Konten auslassen
            continue
        record = post.get("record") or {}
        text = re.sub(r"\s+", " ", str(record.get("text") or "")).strip()
        embed = post.get("embed") or {}
        if "recordWithMedia" in str(embed.get("$type", "")):
            embed = embed.get("media") or {}
        kind = str(embed.get("$type", ""))
        image = video = None
        if kind.startswith("app.bsky.embed.images"):
            images = embed.get("images") or []
            image = _https(images[0].get("fullsize")) if images else None
        elif kind.startswith("app.bsky.embed.video"):
            playlist = _https(embed.get("playlist"))
            if playlist:
                ratio = embed.get("aspectRatio") or {}
                video = {
                    "format": "hls",
                    "src": playlist,
                    "poster": _https(embed.get("thumbnail")),
                    "alt": str(embed.get("alt") or "")[:300],
                    "vertical": int(ratio.get("height") or 0) > int(ratio.get("width") or 0),
                }
        elif kind.startswith("app.bsky.embed.external"):
            image = _https((embed.get("external") or {}).get("thumb"))
        uri = str(post.get("uri") or "")
        handle = str((post.get("author") or {}).get("handle") or source.actor)
        if not text or not uri or not (image or video):
            continue
        url = f"https://bsky.app/profile/{handle}/post/{uri.rsplit('/', 1)[-1]}"
        try:
            created = str(record.get("createdAt")).replace("Z", "+00:00")
            published = datetime.fromisoformat(created).astimezone(UTC)
        except ValueError:
            published = now
        items.append(
            {
                "id": _id(source.id, url),
                "url": url,
                "title": text[:MAX_TITLE],
                "image": image,
                "video": video,
                "published_at": published,
            }
        )
    return items


async def fetch_source(
    source: Source, client: httpx.AsyncClient, now: datetime
) -> list[dict[str, Any]]:
    if source.kind == "rss":
        ratelimit.acquire("rss")
        response = await client.get(source.feed)
        response.raise_for_status()
        return parse_rss(source, response.content, now)
    if source.kind == "bluesky":
        ratelimit.acquire("bluesky")
        response = await client.get(
            BLUESKY_FEED,
            params={"actor": source.actor, "limit": 40, "filter": "posts_with_media"},
        )
        response.raise_for_status()
        return parse_bluesky(source, response.json(), now)
    return []  # youtube: erst mit ABEND_YOUTUBE_API_KEY (Nr. 49)


def store(db: Database, source: Source, items: list[dict[str, Any]], now: datetime) -> int:
    new = 0
    with db.session() as s:
        for item in items:
            if now - item["published_at"] > TTL:
                continue
            if s.get(RawItem, item["id"]) is not None:
                continue
            s.add(
                RawItem(
                    id=item["id"],
                    source_id=source.id,
                    url=item["url"],
                    title=item["title"],
                    language=source.language,
                    country=source.home_country,
                    image=item["image"],
                    video_json=json.dumps(item["video"]) if item["video"] else None,
                    published_at=item["published_at"],
                    fetched_at=now,
                    expires_at=item["published_at"] + TTL,
                )
            )
            new += 1
        s.commit()
    return new


def purge(db: Database, now: datetime) -> int:
    with db.session() as s:
        count = s.query(RawItem).filter(RawItem.expires_at < now).delete()
        alive = select(RawItem.id)
        for table in (Translation, ItemPlace):
            s.query(table).filter(table.raw_item_id.not_in(alive)).delete(synchronize_session=False)
        s.commit()
        return count


async def refresh_all(
    db: Database,
    sources: list[Source],
    transport: httpx.AsyncBaseTransport | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    """Alle Quellen abrufen; eine kaputte Quelle hält die anderen nicht auf."""
    now = now or datetime.now(UTC)
    result: dict[str, int] = {}
    gate = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(
        timeout=15.0,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        transport=transport,
    ) as client:

        async def one(source: Source) -> None:
            async with gate:
                try:
                    items = await fetch_source(source, client, now)
                except Exception as exc:  # Netz, Format, Ratelimit
                    log.warning("Quelle %s nicht abrufbar: %s", source.id, exc)
                    result[source.id] = -1
                    return
                result[source.id] = store(db, source, items, now)

        await asyncio.gather(*(one(s) for s in sources))
    purge(db, now)
    return result
