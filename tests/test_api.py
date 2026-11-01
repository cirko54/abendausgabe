from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import auth, register


def test_first_login_sets_pin_and_second_device_needs_it(client: TestClient) -> None:
    register(client, "robin", "4711")
    wrong = client.post("/api/devices", json={"person_id": "robin", "pin": "0000"})
    assert wrong.status_code == 403
    register(client, "robin", "4711")
    people = client.get("/api/people").json()["people"]
    assert {p["id"]: p["claimed"] for p in people}["robin"] is True


def test_pin_format_and_attempt_limit(client: TestClient) -> None:
    assert client.post("/api/devices", json={"person_id": "kim", "pin": "12"}).status_code == 422
    register(client, "kim", "2468")
    for _ in range(5):
        assert (
            client.post("/api/devices", json={"person_id": "kim", "pin": "1111"}).status_code
            == 403
        )
    blocked = client.post("/api/devices", json={"person_id": "kim", "pin": "2468"})
    assert blocked.status_code == 429


def test_guest_and_me(client: TestClient) -> None:
    token = register(client, "gast", None)
    me = client.get("/api/me", headers=auth(token)).json()
    assert me["role"] == "guest" and me["person_id"].startswith("gast-")
    assert client.get("/api/profile/me", headers=auth(token)).status_code == 403
    assert client.get("/api/me").status_code == 401


def test_profile_versions_and_visibility(client: TestClient) -> None:
    robin = register(client, "robin")
    papa = register(client, "alex")
    kim = register(client, "kim")
    guest = register(client, "gast", None)

    body = {
        "answers": {"talk_for_hours": "Formel 1", "evenings": ["fr", "mo"]},
        "visibility": "self",
    }
    first = client.post("/api/profile", json=body, headers=auth(robin))
    assert first.status_code == 200 and first.json()["version"] == 1
    assert first.json()["answers"]["evenings"] == ["mo", "fr"]

    assert client.get("/api/profile/robin", headers=auth(papa)).status_code == 403
    assert client.get("/api/profile/robin", headers=auth(robin)).status_code == 200

    body["visibility"] = "admins"
    assert client.post("/api/profile", json=body, headers=auth(robin)).json()["version"] == 2
    assert client.get("/api/profile/robin", headers=auth(papa)).status_code == 200
    assert client.get("/api/profile/robin", headers=auth(kim)).status_code == 403

    body["visibility"] = "all"
    client.post("/api/profile", json=body, headers=auth(robin))
    assert client.get("/api/profile/robin", headers=auth(kim)).status_code == 200
    assert client.get("/api/profile/robin", headers=auth(guest)).status_code == 403


def test_profile_validation(client: TestClient) -> None:
    token = register(client, "kim")
    bad_field = {"answers": {"unbekannt": "x"}, "visibility": "self"}
    assert client.post("/api/profile", json=bad_field, headers=auth(token)).status_code == 422
    bad_rank = {"answers": {"games": ["Schach", "Tanzen"]}, "visibility": "self"}
    assert client.post("/api/profile", json=bad_rank, headers=auth(token)).status_code == 422
    bad_link = {"answers": {"creators": ["youtube.com/@vsauce"]}, "visibility": "self"}
    assert client.post("/api/profile", json=bad_link, headers=auth(token)).status_code == 422
    bad_vis = {"answers": {}, "visibility": "nachbarn"}
    assert client.post("/api/profile", json=bad_vis, headers=auth(token)).status_code == 422


def test_qr_and_static_pages(client: TestClient) -> None:
    svg = client.get("/api/qr.svg", params={"data": "http://192.168.1.10:8470/c/"})
    assert svg.status_code == 200 and svg.text.lstrip().startswith("<?xml")
    assert client.get("/api/qr.svg", params={"data": "javascript:alert(1)"}).status_code == 422
    for path in ("/tv/", "/tv/check.html", "/c/", "/p/", "/admin/tvcheck.html", "/shared/base.css"):
        assert client.get(path).status_code == 200, path
    assert client.get("/healthz").json()["status"] == "ok"
