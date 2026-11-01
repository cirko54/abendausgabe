from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from abendausgabe.core.config import PROJECT_ROOT, clear_caches


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    monkeypatch.setenv("ABEND_DATA_DIR", str(tmp_path / "data"))
    # Tests laufen immer gegen den Beispielhaushalt, nie gegen die eigene Konfiguration
    monkeypatch.setenv("ABEND_CONFIG_DIR", str(PROJECT_ROOT / "config.example"))
    monkeypatch.setenv("ABEND_EXAMPLE_CONFIG_DIR", str(PROJECT_ROOT / "config.example"))
    monkeypatch.setenv("ABEND_WEB_DIR", str(PROJECT_ROOT / "web"))
    # Testsendung statt Tagesablauf: keine Live-Abrufe in Tests
    monkeypatch.setenv("ABEND_PROGRAM", "test")
    monkeypatch.setenv("ABEND_MORNING_PUSH", "aus")
    clear_caches()
    from abendausgabe.app import create_app

    yield create_app()
    clear_caches()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def register(client: TestClient, person_id: str, pin: str | None = "1234") -> str:
    """Meldet ein Gerät an und gibt das Token zurück; entfernt das Cookie aus dem Client."""
    response = client.post("/api/devices", json={"person_id": person_id, "pin": pin})
    assert response.status_code == 200, response.text
    token = response.cookies["abend_device"]
    client.cookies.clear()
    return token


def auth(token: str) -> dict[str, str]:
    return {"cookie": f"abend_device={token}"}
