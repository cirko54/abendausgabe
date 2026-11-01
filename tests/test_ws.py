from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from abendausgabe.core.models import Interaction, SessionRecord
from tests.conftest import auth, register


def recv(ws: WebSocketTestSession) -> dict[str, Any]:
    data: dict[str, Any] = ws.receive_json()
    return data


def test_controller_requires_login(client: TestClient) -> None:
    with client.websocket_connect("/ws/c") as ws:
        try:
            ws.receive_text()
        except WebSocketDisconnect as exc:
            assert exc.code == 4401
        else:
            raise AssertionError("Verbindung hätte mit 4401 schließen müssen")


def test_echo(client: TestClient) -> None:
    with client.websocket_connect("/ws/echo") as ws:
        ws.send_text("ping")
        assert ws.receive_text() == "ping"


def test_full_test_broadcast(client: TestClient) -> None:
    papa = register(client, "alex")
    robin = register(client, "robin")
    with (
        client.websocket_connect("/ws/tv") as tv,
        client.websocket_connect("/ws/c", headers=auth(papa)) as c1,
        client.websocket_connect("/ws/c", headers=auth(robin)) as c2,
    ):
        assert recv(tv)["phase"] == "lobby"
        assert recv(c1)["you"]["present"] is False
        recv(c2)

        c1.send_json({"type": "checkin"})
        for ws in (tv, c1, c2):
            recv(ws)
        c2.send_json({"type": "checkin"})
        for ws in (tv, c1, c2):
            state = recv(ws)
        assert [m["present"] for m in state["members"]] == [True, True]

        tv.send_json({"type": "ok"})  # Start: Begrüßung
        for ws in (tv, c1, c2):
            state = recv(ws)
        assert state["block_phase"] == "show"

        tv.send_json({"type": "ok"})  # Schätzfrage
        for ws in (tv, c1, c2):
            state = recv(ws)
        assert state["block_phase"] == "ask" and "truth" not in state["block"]

        c2.send_json({"type": "answer", "value": 300000})
        for ws in (tv, c1, c2):
            recv(ws)
        c1.send_json({"type": "answer", "value": 384400})
        tv_state = recv(tv)
        assert tv_state["block_phase"] == "reveal"
        assert tv_state["block"]["truth"] == 384400
        mine = recv(c1)["you"]
        assert mine["points"] == 100
        recv(c2)

        c2.send_json({"type": "end_now"})  # Member darf nicht beenden
        c1.send_json({"type": "end_now"})
        for ws in (tv, c1, c2):
            state = recv(ws)
        assert state["phase"] == "ended"
        assert state["scores"][0]["person_id"] == "alex"

        tv.send_json({"type": "ok"})  # nach Sendeschluss: nichts
        c1.send_json({"type": "signal", "kind": "too_hard"})  # erzeugt keinen Broadcast
        c1.send_json({"type": "advance"})  # Admin: neue Testsendung
        assert recv(tv)["phase"] == "lobby"

    db = client.app.state.db  # type: ignore[attr-defined]
    with db.session() as s:
        kinds = [i.kind for i in s.scalars(select(Interaction))]
        assert {"checkin", "answer", "reveal", "session_start", "session_end", "signal"} <= set(
            kinds
        )
        record = s.scalars(select(SessionRecord)).one()
        assert record.ended_at is not None
