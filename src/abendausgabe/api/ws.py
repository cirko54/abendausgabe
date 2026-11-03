"""WebSockets: /ws/tv (Bühne), /ws/c (Handy-Controller), /ws/echo (Fähigkeitstest).

Der TV-Kanal hat in Phase 0 keine Authentifizierung (nur LAN, siehe decisions.md).
"""

from __future__ import annotations

import json
import logging
import time
from functools import partial
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from abendausgabe.api.deps import COOKIE_NAME, identity_from_token
from abendausgabe.session.manager import RoomManager

router = APIRouter()
log = logging.getLogger(__name__)


def _parse(raw: str) -> dict[str, Any] | None:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


@router.websocket("/ws/echo")
async def ws_echo(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            await ws.send_text(await ws.receive_text())
    except WebSocketDisconnect:
        return


@router.websocket("/ws/tv")
async def ws_tv(ws: WebSocket) -> None:
    manager: RoomManager = ws.app.state.manager
    await ws.accept()
    manager.tv_sockets.add(ws)
    await manager.send_state(ws, viewer=None)
    await manager.refresh_program()
    try:
        while True:
            msg = _parse(await ws.receive_text())
            if not msg:
                continue
            if msg.get("type") == "ok":
                # Nach dem Sendeschluss bewirkt OK nichts: kein „mehr davon“.
                await manager.advance()
            elif msg.get("type") == "media":
                # Wiedergabe-Rückmeldung des Fernsehers, nur fürs Log (Livestream-Test)
                detail = {k: str(msg.get(k, ""))[:200] for k in ("block", "status", "via", "error")}
                log.info("TV-Wiedergabe: %s", detail)
    except WebSocketDisconnect:
        pass
    finally:
        manager.tv_sockets.discard(ws)


@router.websocket("/ws/c")
async def ws_controller(ws: WebSocket) -> None:
    identity = identity_from_token(
        ws.cookies.get(COOKIE_NAME), ws.app.state.db, ws.app.state.people
    )
    if identity is None:
        # Erst annehmen, dann schließen: Nur so sieht der Browser den Code 4401
        # (ein Schließen vor accept() kommt dort als 1006 an).
        await ws.accept()
        await ws.close(code=4401)
        return
    manager: RoomManager = ws.app.state.manager
    room = manager.room
    pid = identity.person_id
    is_admin = identity.role == "admin"
    await ws.accept()
    manager.controller_sockets[ws] = pid
    await manager.send_state(ws, viewer=pid)
    try:
        while True:
            msg = _parse(await ws.receive_text())
            if not msg:
                continue
            kind = msg.get("type")
            if kind == "checkin":
                await manager.handle(
                    lambda: room.checkin(pid, identity.name, identity.color, identity.role)
                )
            elif kind == "leave":
                await manager.handle(lambda: room.leave(pid))
            elif kind == "answer":
                value = msg.get("value")
                await manager.handle(partial(room.answer, pid, value, time.monotonic()))
            elif kind == "skip_vote":
                await manager.handle(lambda: room.skip_vote(pid, time.monotonic()))
            elif kind == "signal":
                signal_kind = str(msg.get("kind", ""))
                await manager.handle(partial(room.signal, pid, signal_kind))
            elif kind == "advance" and is_admin:
                if room.phase == "ended":
                    await manager.handle(room.reset)
                else:
                    await manager.advance()
            elif kind == "restart" and is_admin:
                await manager.handle(lambda: room.restart(time.monotonic()))
            elif kind == "end_now" and is_admin:
                await manager.handle(lambda: room.end_now(time.monotonic()))
    except WebSocketDisconnect:
        pass
    finally:
        # Eine getrennte Verbindung heißt nicht „bin weg“: Das Handy darf schlafen.
        manager.controller_sockets.pop(ws, None)
