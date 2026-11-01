from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from abendausgabe.api.tvcheck import compute_verdict
from abendausgabe.core.ratelimit import TokenBucket
from abendausgabe.modules.tagesschau import fetch
from tests.conftest import auth, register

FIXTURES = Path(__file__).parent / "fixtures"

GOOD: dict[str, Any] = {
    "ua": "TestTV",
    "js": {"es2017": True, "es2020": True},
    "websocket": {"ok": True},
    "font": {"ok": True},
    "media": {"mp4": {"ok": True}, "hls_native": {"ok": False}, "mse": True},
    "youtube": {"ok": True},
    "fps": 58,
}


def test_verdict_a_with_hlsjs_note() -> None:
    verdict = compute_verdict(GOOD)
    assert verdict["code"] == "A"
    assert any("hls.js" in n for n in verdict["notes"])


def test_verdict_b_when_youtube_fails() -> None:
    report = json.loads(json.dumps(GOOD))
    report["youtube"]["ok"] = False
    assert compute_verdict(report)["code"] == "B"


def test_verdict_c_without_websocket() -> None:
    report = json.loads(json.dumps(GOOD))
    report["websocket"]["ok"] = False
    assert compute_verdict(report)["code"] == "C"


def test_verdict_weak_graphics() -> None:
    report = dict(GOOD, fps=20)
    assert compute_verdict(report)["code"] == "A-"


def test_find_media_urls_from_fixture() -> None:
    data = json.loads((FIXTURES / "tagesschau_channels.json").read_text())
    found = fetch.find_media_urls(data)
    assert found["hls"] == ["https://example.invalid/live/tagesschau24/master.m3u8?x=1"]
    assert found["mp4"] == ["https://example.invalid/video/clip_s.mp4"]


def test_token_bucket() -> None:
    bucket = TokenBucket(capacity=2, per_seconds=60)
    assert bucket.try_acquire(0) and bucket.try_acquire(0)
    assert bucket.try_acquire(0) is False
    assert bucket.try_acquire(30) is True  # nach 30 s ein Token nachgefüllt


def test_report_roundtrip_and_admin_only(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_get_json(endpoint: str) -> Any:
        return json.loads((FIXTURES / "tagesschau_channels.json").read_text())

    monkeypatch.setattr(fetch, "get_json", fake_get_json)
    media = client.get("/api/tv-check/media").json()
    assert media["mp4"].endswith(".mp4") and media["youtube_id"]

    posted = client.post("/api/tv-check", json=GOOD).json()
    assert posted["verdict"]["code"] == "A"
    keys = [{"label": "Zurück", "missed": True}]
    updated = client.post(f"/api/tv-check/{posted['id']}/keys", json={"keys": keys}).json()
    assert updated["verdict"]["remote"] == "none"

    assert client.get("/api/tv-check").status_code == 401
    member = register(client, "robin")
    assert client.get("/api/tv-check", headers=auth(member)).status_code == 403
    admin = register(client, "sam")
    reports = client.get("/api/tv-check", headers=auth(admin)).json()["reports"]
    assert reports[0]["verdict"]["code"] == "A"


FIXTURE_PHILIPS = FIXTURES / "tvcheck_philips_2026-10-31.json"


def test_real_philips_report_is_not_b_because_mp4_was_untested() -> None:
    """Regression: Am 31.10.2026 fehlte das Testvideo (308-Weiterleitung), nicht die Fähigkeit."""
    report = json.loads(FIXTURE_PHILIPS.read_text())
    verdict = compute_verdict(report)
    assert verdict["code"] == "A"
    assert "voraussichtlich" in verdict["label"]
    assert verdict["remote"] == "none"
    assert any("hls.js" in n for n in verdict["notes"])


def test_cursor_mode_detected() -> None:
    report = json.loads(FIXTURE_PHILIPS.read_text())
    report["pointer"] = {"moves": 42, "clicks": 1}
    assert compute_verdict(report)["remote"] == "cursor"


def test_partial_keys() -> None:
    report = dict(GOOD, keys=[{"label": "OK", "keyCode": 13}, {"label": "Zurück", "missed": True}])
    verdict = compute_verdict(report)
    assert verdict["remote"] == "partial"
    assert any("Zurück" in n for n in verdict["notes"])


def test_get_json_follows_308_redirect() -> None:
    import asyncio

    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/"):
            return httpx.Response(308, headers={"location": request.url.path.rstrip("/")})
        return httpx.Response(200, json={"ok": True})

    fetch._cache.clear()
    data = asyncio.run(fetch.get_json("channels/", transport=httpx.MockTransport(handler)))
    assert data == {"ok": True}
    fetch._cache.clear()


def test_second_philips_report_is_a_with_cursor_mode() -> None:
    report = json.loads((FIXTURES / "tvcheck_philips_2026-11-01.json").read_text())
    verdict = compute_verdict(report)
    assert verdict["code"] == "A" and verdict["remote"] == "cursor"
