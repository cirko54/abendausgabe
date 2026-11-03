"""Aus einem geteilten Link wird ein abspielbarer Beitrag (decisions.md Nr. 56).

Einbettungen baut der Server selbst aus der erkannten ID; HTML aus oEmbed wird nie
übernommen. Fremde Adressen ruft er nur über core.safefetch ab.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx

from abendausgabe.core import ratelimit
from abendausgabe.core.safefetch import UnsafeURLError, check_url, fetch_public
from abendausgabe.modules.weltblick import fetch as wfetch
from abendausgabe.modules.weltblick.catalog import Source

YOUTUBE = re.compile(
    r"^https://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?(?:[^#]*&)?v=|shorts/|live/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})"
)
TIKTOK = re.compile(r"^https://(?:www\.|m\.)?tiktok\.com/@[^/?#]+/video/(\d{8,25})")
INSTAGRAM = re.compile(r"^https://(?:www\.)?instagram\.com/(p|reel|reels|tv)/([A-Za-z0-9_-]{5,40})")
REDDIT = re.compile(
    r"^https://(?:www\.|old\.|new\.|m\.)?reddit\.com/r/([A-Za-z0-9_]{2,30})/comments/([a-z0-9]{3,12})"
    r"(?:/([A-Za-z0-9_%-]*))?"
)
VIMEO = re.compile(r"^https://(?:www\.)?vimeo\.com/(\d{5,12})")
BLUESKY = re.compile(r"^https://bsky\.app/profile/([A-Za-z0-9.:_-]{3,100})/post/([a-z0-9]{8,20})")
# Kurzlinks führen per Weiterleitung zur eigentlichen Adresse
SHORT = re.compile(
    r"^https://(?:vm\.tiktok\.com|vt\.tiktok\.com|redd\.it|(?:www\.)?reddit\.com/r/[^/]+/s/)"
)

PROVIDER_NAMES = {
    "youtube": "YouTube", "tiktok": "TikTok", "instagram": "Instagram", "reddit": "Reddit",
    "vimeo": "Vimeo", "bluesky": "Bluesky", "web": "Web", "foto": "Foto", "notiz": "Gedanke",
}  # fmt: skip
DEFAULT_TITLES = {
    "youtube": "YouTube-Video", "tiktok": "TikTok-Video", "reddit": "Reddit-Beitrag",
    "vimeo": "Vimeo-Video",
}  # fmt: skip
USER_AGENT = wfetch.USER_AGENT
MAX_TITLE = 300


@dataclass
class Resolved:
    url: str
    kind: str  # embed | video | image | link
    provider: str
    title: str = ""
    author: str = ""
    image: str | None = None
    embed_src: str | None = None
    video: dict[str, Any] | None = None
    vertical: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def _clean(text: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(text or ""))).strip()[:MAX_TITLE]


# YouTube-oEmbed antwortet mit 401, wenn der Uploader das Einbetten verboten hat,
# und mit 404 bei privaten oder gelöschten Videos (decisions.md Nr. 60).
NOT_EMBEDDABLE = "not_embeddable"


async def _oembed(client: httpx.AsyncClient, endpoint: str, url: str) -> dict[str, Any]:
    """Nur Titel, Autor, Vorschaubild; Fehler sind kein Grund, den Link abzulehnen."""
    try:
        ratelimit.acquire("mitbringsel")
        response = await client.get(
            endpoint, params={"url": url, "format": "json"}, follow_redirects=True
        )
        if response.status_code in (401, 403, 404):
            return {NOT_EMBEDDABLE: True}
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError, ratelimit.RateLimitedError):
        return {}
    return data if isinstance(data, dict) else {}


def _meta(data: dict[str, Any], r: Resolved) -> Resolved:
    r.title = _clean(data.get("title")) or r.title or DEFAULT_TITLES.get(r.provider, "")
    r.author = _clean(data.get("author_name"))[:120]
    thumb = wfetch._https(str(data.get("thumbnail_url") or "")) if data else None
    r.image = thumb or r.image
    return r


OG = re.compile(
    r"<meta[^>]+(?:property|name)=[\"'](og:title|og:image|og:site_name|twitter:image)[\"'][^>]*"
    r"content=[\"']([^\"']*)[\"']",
    re.I,
)
OG_REVERSED = re.compile(
    r"<meta[^>]+content=[\"']([^\"']*)[\"'][^>]*(?:property|name)="
    r"[\"'](og:title|og:image|og:site_name|twitter:image)[\"']",
    re.I,
)
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def parse_page(page: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for key, value in OG.findall(page):
        found.setdefault(key.lower(), value)
    for value, key in OG_REVERSED.findall(page):
        found.setdefault(key.lower(), value)
    if "og:title" not in found:
        match = TITLE.search(page)
        if match:
            found["og:title"] = match.group(1)
    return found


async def resolve(url: str, client: httpx.AsyncClient) -> Resolved:
    url = url.strip()
    check_url(url)
    if SHORT.match(url):
        fetched = await fetch_public(url, client)
        url = fetched.url
    if m := YOUTUBE.match(url):
        vid = m.group(1)
        r = Resolved(
            url=f"https://www.youtube.com/watch?v={vid}",
            kind="embed",
            provider="youtube",
            embed_src=f"https://www.youtube-nocookie.com/embed/{vid}?autoplay=1&rel=0&playsinline=1",
            vertical="/shorts/" in url,
        )
        data = await _oembed(client, "https://www.youtube.com/oembed", r.url)
        if data.get(NOT_EMBEDDABLE):
            # Der Player bliebe am Fernseher schwarz: Karte mit Vorschaubild statt Einbettung
            r.kind, r.embed_src = "link", None
            r.image = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
            r.extra["notice"] = (
                "YouTube erlaubt für dieses Video kein Abspielen außerhalb von YouTube. "
                "Der Fernseher zeigt Vorschaubild und Titel."
            )
        return _meta(data, r)
    if m := TIKTOK.match(url):
        vid = m.group(1)
        r = Resolved(
            url=url.split("?", 1)[0],
            kind="embed",
            provider="tiktok",
            embed_src=f"https://www.tiktok.com/player/v1/{vid}?autoplay=1&loop=0&rel=0&description=1",
            vertical=True,
        )
        return _meta(await _oembed(client, "https://www.tiktok.com/oembed", r.url), r)
    if m := INSTAGRAM.match(url):
        kind, code = m.group(1), m.group(2)
        path = "reel" if kind in ("reel", "reels") else kind
        return Resolved(
            url=f"https://www.instagram.com/{path}/{code}/",
            kind="embed",
            provider="instagram",
            title="Instagram-Beitrag",
            embed_src=f"https://www.instagram.com/{path}/{code}/embed/captioned/",
            vertical=path == "reel",
        )
    if m := REDDIT.match(url):
        sub, post, slug = m.group(1), m.group(2), m.group(3) or ""
        canonical = f"https://www.reddit.com/r/{sub}/comments/{post}/{quote(slug, safe='%-_')}/"
        r = Resolved(
            url=canonical,
            kind="embed",
            provider="reddit",
            title=f"r/{sub}",
            embed_src=f"https://embed.reddit.com/r/{sub}/comments/{post}/?embed=true&theme=dark",
        )
        return _meta(await _oembed(client, "https://www.reddit.com/oembed", canonical), r)
    if m := VIMEO.match(url):
        vid = m.group(1)
        r = Resolved(
            url=f"https://vimeo.com/{vid}",
            kind="embed",
            provider="vimeo",
            embed_src=f"https://player.vimeo.com/video/{vid}?autoplay=1",
        )
        return _meta(await _oembed(client, "https://vimeo.com/api/oembed.json", r.url), r)
    if m := BLUESKY.match(url):
        return await _bluesky(client, url, m.group(1), m.group(2))
    return await _web(client, url)


async def _bluesky(client: httpx.AsyncClient, url: str, actor: str, rkey: str) -> Resolved:
    ratelimit.acquire("bluesky")
    did = actor
    if not actor.startswith("did:"):
        response = await client.get(
            "https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle",
            params={"handle": actor},
        )
        response.raise_for_status()
        did = str(response.json().get("did", ""))
    response = await client.get(
        "https://public.api.bsky.app/xrpc/app.bsky.feed.getPosts",
        params={"uris": f"at://{did}/app.bsky.feed.post/{rkey}"},
    )
    response.raise_for_status()
    posts = response.json().get("posts") or []
    stub = Source("bluesky", "Bluesky", "bluesky", url, (), "", actor=actor)
    items = wfetch.parse_bluesky(stub, {"feed": [{"post": p} for p in posts]}, _now())
    if not items:
        text = _clean(((posts or [{}])[0].get("record") or {}).get("text"))
        return Resolved(url=url, kind="link", provider="bluesky", title=text or "Bluesky-Beitrag")
    item = items[0]
    video = item["video"]
    return Resolved(
        url=url,
        kind="video" if video else "image",
        provider="bluesky",
        title=_clean(item["title"]),
        author=actor,
        image=item["image"] or (video or {}).get("poster"),
        video=video,
        vertical=bool(video and video.get("vertical")),
    )


async def _web(client: httpx.AsyncClient, url: str) -> Resolved:
    ratelimit.acquire("mitbringsel")
    fetched = await fetch_public(url, client)
    if fetched.content_type.startswith(("image/jpeg", "image/png", "image/webp", "image/gif")):
        # Direkter Bildlink: Das Bild lädt der Fernseher selbst von der Quelle
        name = fetched.url.rsplit("/", 1)[-1].split("?", 1)[0]
        host = fetched.url.split("/")[2]
        return Resolved(
            url=fetched.url,
            kind="image",
            provider="web",
            title=_clean(name),
            author=host,
            image=fetched.url,
        )
    if "html" not in fetched.content_type:
        raise UnsafeURLError("Der Link führt weder zu einer Webseite noch zu einem Bild.")
    page = fetched.body.decode("utf-8", errors="replace")
    meta = parse_page(page)
    image = wfetch._https(html.unescape(meta.get("og:image") or meta.get("twitter:image") or ""))
    return Resolved(
        url=fetched.url,
        kind="image" if image else "link",
        provider="web",
        title=_clean(meta.get("og:title")) or fetched.url,
        author=_clean(meta.get("og:site_name"))[:120],
        image=image,
    )


def _now() -> datetime:
    return datetime.now(UTC)


def make_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=10.0, headers={"User-Agent": USER_AGENT}, transport=transport)
