"""Phase 1, Schritt 4: Mitbringsel (decisions.md Nr. 56)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from abendausgabe.core import safefetch
from abendausgabe.core.db import Database
from abendausgabe.modules.mitbringsel import resolve, store
from abendausgabe.session.room import Room
from abendausgabe.session.rundown import validate_rundown
from tests.conftest import auth, register

NOW = datetime(2026, 11, 3, 18, 0, tzinfo=UTC)
BSKY = json.loads(
    (Path(__file__).parent / "fixtures" / "weltblick_bluesky.json").read_text("utf-8")
)


def oembed_handler(request: httpx.Request) -> httpx.Response:
    host = request.url.host
    if host in ("www.youtube.com", "www.tiktok.com", "vimeo.com", "www.reddit.com"):
        return httpx.Response(
            200,
            json={
                "title": "Ein &amp; Titel",
                "author_name": "Kanal",
                "thumbnail_url": "https://img.example.org/t.jpg",
                "html": "<script>alert(1)</script>",
            },
        )
    if host == "public.api.bsky.app":
        if request.url.path.endswith("resolveHandle"):
            return httpx.Response(200, json={"did": "did:plc:beispiel"})
        return httpx.Response(200, json={"posts": [BSKY["feed"][0]["post"]]})
    return httpx.Response(404)


async def resolved(url: str) -> resolve.Resolved:
    async with resolve.make_client(httpx.MockTransport(oembed_handler)) as client:
        return await resolve.resolve(url, client)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("url", "provider", "embed"),
    [
        ("https://www.youtube.com/watch?v=jNQXAC9IVRw&t=3", "youtube",
         "https://www.youtube-nocookie.com/embed/jNQXAC9IVRw?"),
        ("https://youtube.com/shorts/jNQXAC9IVRw", "youtube",
         "https://www.youtube-nocookie.com/embed/jNQXAC9IVRw?"),
        ("https://www.tiktok.com/@konto/video/6718335390845095173?lang=de", "tiktok",
         "https://www.tiktok.com/player/v1/6718335390845095173?"),
        ("https://www.instagram.com/reel/C3n6t4qSjzF/?igsh=x", "instagram",
         "https://www.instagram.com/reel/C3n6t4qSjzF/embed/captioned/"),
        ("https://www.reddit.com/r/pics/comments/92dd8/test_post/", "reddit",
         "https://embed.reddit.com/r/pics/comments/92dd8/?embed=true"),
        ("https://vimeo.com/76979871", "vimeo", "https://player.vimeo.com/video/76979871?"),
    ],
)  # fmt: skip
async def test_known_platforms_embed_from_id_only(url: str, provider: str, embed: str) -> None:
    r = await resolved(url)
    assert r.provider == provider and r.kind == "embed"
    assert r.embed_src and r.embed_src.startswith(embed)
    assert "<script" not in json.dumps(r.__dict__)  # oEmbed-HTML wird nie übernommen
    if provider not in ("instagram",):
        assert r.title in ("Ein & Titel", "r/pics") or r.title == "Ein & Titel"
    validate_rundown(
        [{"id": "m", "type": "embed", "title": "M", "src": r.embed_src},
         {"id": "e", "type": "end", "title": "E"}]
    )  # fmt: skip


@pytest.mark.anyio
async def test_bluesky_post_becomes_video() -> None:
    r = await resolved("https://bsky.app/profile/agentur.example/post/aaa1aaa1aa")
    assert r.kind == "video" and r.video and r.video["src"].endswith(".m3u8")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "url",
    [
        "http://example.org/x",
        "https://192.168.178.1/admin",
        "https://127.0.0.1/",
        "https://10.0.0.5/",
        "https://[::1]/",
        "https://example.org:8443/",
        "https://user:pw@example.org/",
        "https://localhost/",
    ],
)
async def test_unsafe_urls_are_rejected(url: str) -> None:
    with pytest.raises(safefetch.UnsafeURLError):
        async with httpx.AsyncClient(transport=httpx.MockTransport(oembed_handler)) as c:
            await safefetch.fetch_public(url, c)


@pytest.mark.anyio
async def test_redirect_into_lan_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    async def public(_host: str) -> None:
        if _host.startswith("192.168."):
            raise safefetch.UnsafeURLError("privat")

    monkeypatch.setattr(safefetch, "check_public", public)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://192.168.178.1/"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(safefetch.UnsafeURLError):
            await safefetch.fetch_public("https://example.org/kurz", c)


def test_og_tags_in_any_order() -> None:
    page = (
        '<head><meta content="https://img.example.org/a.jpg" property="og:image">'
        '<meta property="og:title" content="Ein Artikel"><title>Fallback</title></head>'
    )
    meta = resolve.parse_page(page)
    assert meta["og:image"] == "https://img.example.org/a.jpg"
    assert meta["og:title"] == "Ein Artikel"


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(f"sqlite:///{tmp_path / 'db.sqlite3'}")


def _r(n: int = 1) -> resolve.Resolved:
    return resolve.Resolved(
        url=f"https://www.youtube.com/watch?v=jNQXAC9IVR{n}",
        kind="embed",
        provider="youtube",
        title=f"Video {n}",
        image="https://img.example.org/t.jpg",
        embed_src=f"https://www.youtube-nocookie.com/embed/jNQXAC9IVR{n}?autoplay=1",
    )


PEOPLE = [store.Person("alex", "Alex"), store.Person("sam", "Sam"), store.Person("kim", "Kim")]


def test_show_blocks_guess_one_per_person_only_present(db: Database) -> None:
    store.add(db, "alex", _r(1), "Musste ich an euch denken", NOW)
    store.add(db, "alex", _r(2), "", NOW + timedelta(minutes=1))
    store.add(db, "robin", _r(3), "", NOW)  # nicht da
    blocks = store.show_blocks(db, PEOPLE, NOW + timedelta(hours=1))
    assert [b["type"] for b in blocks] == ["embed", "choice"]
    shown, guess = blocks
    assert shown["credit"] == ""  # Name erst in der Auflösung
    assert guess["exempt"] == ["alex"]
    assert guess["options"][guess["correct"]] == "Alex"
    assert "Musste ich an euch denken" in guess["source"]
    rundown = [
        {"id": "begruessung", "type": "info", "title": "G"},
        {"id": "e", "type": "end", "title": "E"},
    ]
    merged = store.with_mitbringsel(rundown, blocks)
    assert [b["id"] for b in merged][:2] == ["begruessung", shown["id"]]
    validate_rundown(merged)
    store.mark_shown(db, merged, NOW.date())
    assert [i["title"] for i in store.pending(db, "alex", NOW)] == ["Video 2"]


def test_two_present_shows_name_without_guess(db: Database) -> None:
    store.add(db, "sam", _r(1), "", NOW)
    blocks = store.show_blocks(db, PEOPLE[:2], NOW)
    assert len(blocks) == 1 and blocks[0]["credit"] == "Mitgebracht von Sam"


def test_limits_and_take_back(db: Database) -> None:
    ids = [store.add(db, "kim", _r(n), "", NOW)["id"] for n in range(store.MAX_OPEN)]
    with pytest.raises(store.LimitError):
        store.add(db, "kim", _r(99), "", NOW)
    assert store.remove(db, Path("/nirgends"), "kim", ids[0]) is True
    assert store.remove(db, Path("/nirgends"), "sam", ids[1]) is False  # fremdes Mitbringsel


def test_exempt_person_cannot_answer_and_is_not_waited_for() -> None:
    guess: dict[str, Any] = {
        "id": "g", "type": "choice", "title": "M", "question": "Wer?",
        "options": ["Alex", "Sam", "Kim"], "correct": 0, "exempt": ["alex"],
    }  # fmt: skip
    room = Room([guess, {"id": "e", "type": "end", "title": "E"}])
    for pid in ("alex", "sam", "kim"):
        room.checkin(pid, pid, "#000", "member")
    room.advance(0.0)
    assert room.answer("alex", 0, 1.0) is False
    room.answer("sam", 0, 1.0)
    room.answer("kim", 1, 1.0)
    assert room.block_phase == "reveal"


def test_share_api(client: TestClient) -> None:
    token = register(client, "alex")
    client.app.state.mitbringsel_transport = httpx.MockTransport(oembed_handler)  # type: ignore[attr-defined]
    bad = client.post("/api/mitbringsel", headers=auth(token), json={"url": "http://x.example"})
    assert bad.status_code == 422 and "https" in bad.json()["detail"]
    ok = client.post(
        "/api/mitbringsel",
        headers=auth(token),
        json={"url": "https://youtu.be/jNQXAC9IVRw", "note": "  Schaut mal  "},
    )
    assert ok.status_code == 200, ok.text
    item = ok.json()["item"]
    assert item["provider"] == "YouTube" and item["note"] == "Schaut mal"
    assert len(client.get("/api/mitbringsel", headers=auth(token)).json()["items"]) == 1
    assert client.delete(f"/api/mitbringsel/{item['id']}", headers=auth(token)).status_code == 200


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def test_photo_text_and_purge(db: Database, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        store.add_photo(db, tmp_path, "sam", b"<svg onload=alert(1)>", "", NOW)
    item = store.add_photo(db, tmp_path, "sam", PNG, "Vom Ausflug", NOW)
    name = item["image"].rsplit("/", 1)[-1]
    assert (tmp_path / "mitbringsel" / name).exists()
    store.add_text(db, "kim", "Sollten wir mal wieder wandern?", NOW)
    blocks = store.show_blocks(db, PEOPLE, NOW)
    kinds = {b["id"]: b for b in blocks}
    photo = next(b for b in blocks if b.get("media") and b["type"] == "info")
    assert photo["link"] is None
    text = next(b for b in blocks if b["type"] == "info" and not b.get("media"))
    assert text["body"] == "Sollten wir mal wieder wandern?"
    assert len(kinds) == 4  # je Person Beitrag und Raterunde
    assert store.purge(db, tmp_path, NOW + timedelta(days=8)) == 2
    assert not (tmp_path / "mitbringsel" / name).exists()


def test_share_photo_and_text_api(client: TestClient) -> None:
    import base64

    token = register(client, "kim")
    data = "data:image/png;base64," + base64.b64encode(PNG).decode()
    photo = client.post("/api/mitbringsel", headers=auth(token), json={"photo": data})
    assert photo.status_code == 200, photo.text
    src = photo.json()["item"]["image"]
    assert client.get(src).status_code == 200  # der Fernseher braucht keine Anmeldung
    assert client.get("/api/mitbringsel/bild/..%2Fabendausgabe.sqlite3").status_code == 404
    text = client.post("/api/mitbringsel", headers=auth(token), json={"note": "Eine Frage"})
    assert text.json()["item"]["provider"] == "Gedanke"
    empty = client.post("/api/mitbringsel", headers=auth(token), json={})
    assert empty.status_code == 422
