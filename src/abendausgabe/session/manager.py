"""Verbindet die Ablauflogik (Room) mit WebSockets und Datenbank."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from fastapi import WebSocket

from abendausgabe.core.dates import BERLIN
from abendausgabe.core.db import Database
from abendausgabe.core.models import Interaction, SessionRecord, utcnow
from abendausgabe.learning import pool
from abendausgabe.session.room import Room

log = logging.getLogger(__name__)


ProgramBuilder = Callable[[], Awaitable[list[dict[str, Any]]]]

PROGRAM_MAX_AGE_S = 120.0
PROGRAM_TIMEOUT_S = 12.0


class RoomManager:
    def __init__(self, room: Room, db: Database, program: ProgramBuilder | None = None) -> None:
        self.room = room
        self.db = db
        self.program = program
        self._program_built_at: float | None = None
        self._program_lock = asyncio.Lock()
        self.tv_sockets: set[WebSocket] = set()
        self.controller_sockets: dict[WebSocket, str] = {}
        self._lock = asyncio.Lock()
        self._ticker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._ticker is None or self._ticker.done():
            self._ticker = asyncio.create_task(self._tick_loop())

    async def stop(self) -> None:
        if self._ticker is not None:
            self._ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ticker
            self._ticker = None

    async def _tick_loop(self) -> None:
        while True:
            await asyncio.sleep(0.5)
            await self.handle(lambda: self.room.tick(time.monotonic()))

    async def refresh_program(self, force: bool = False) -> None:
        """Tagesablauf neu zusammenstellen, solange die Sendung noch nicht läuft.

        Schlägt das fehl, bleibt der bisherige Ablauf; die Sendung startet trotzdem.
        """
        if self.program is None or self.room.phase != "lobby":
            return
        async with self._program_lock:
            fresh = (
                self._program_built_at is not None
                and time.monotonic() - self._program_built_at < PROGRAM_MAX_AGE_S
            )
            if fresh and not force:
                return
            try:
                rundown = await asyncio.wait_for(self.program(), PROGRAM_TIMEOUT_S)
            except Exception:  # Quelle oder Netz kaputt: alten Ablauf behalten
                log.exception("Tagesablauf konnte nicht zusammengestellt werden.")
                return
            self._program_built_at = time.monotonic()
        await self.handle(lambda: self.room.set_rundown(rundown))

    async def advance(self) -> bool:
        """OK bzw. „Weiter“. Vor dem Sendestart wird der Ablauf aufgefrischt."""
        if self.room.phase == "lobby":
            await self.refresh_program()
            await self.handle(self._add_reviews)
        return await self.handle(lambda: self.room.advance(time.monotonic()))

    def _add_reviews(self) -> bool:
        """Fällige Wiederholungen für die Anwesenden vor den Sendeschluss (decisions.md Nr. 44)."""
        if self.room.phase != "lobby" or not self.room.present_ids:
            return False
        planned = {
            str(b["quiz_item"]["id"])
            for b in self.room.rundown
            if isinstance(b.get("quiz_item"), dict) and not str(b["id"]).startswith("wiederholung-")
        }
        try:
            reviews = pool.review_blocks(
                self.db, self.room.present_ids, datetime.now(BERLIN).date(), planned
            )
        except Exception:  # Wiederholung ist Zugabe; die Sendung startet trotzdem
            log.exception("Wiederholungen konnten nicht geladen werden.")
            return False
        return self.room.set_rundown(pool.with_reviews(self.room.rundown, reviews))

    async def handle(self, action: Callable[[], bool]) -> bool:
        """Führt eine Room-Aktion aus, persistiert Ereignisse, sendet bei Änderung."""
        async with self._lock:
            changed = action()
            self._persist_events()
            if changed:
                await self._broadcast()
            return changed

    async def send_state(self, ws: WebSocket, viewer: str | None) -> None:
        async with self._lock:
            await ws.send_json(self.room.state(time.monotonic(), viewer=viewer))

    def _persist_events(self) -> None:
        events = self.room.pop_events()
        if not events:
            return
        session_id = self.room.session_id
        with self.db.session() as s:
            for ev in events:
                s.add(
                    Interaction(
                        session_id=session_id,
                        person_id=ev.person_id,
                        block_id=ev.block_id,
                        kind=ev.kind,
                        payload_json=json.dumps(ev.payload, ensure_ascii=False),
                    )
                )
                if ev.kind == "session_start" and session_id:
                    s.add(
                        SessionRecord(
                            id=session_id,
                            members_json=json.dumps(ev.payload.get("members", [])),
                        )
                    )
                elif ev.kind == "session_end" and session_id:
                    record = s.get(SessionRecord, session_id)
                    if record is not None:
                        record.ended_at = utcnow()
            s.commit()
        for ev in events:
            if ev.kind == "reveal":
                self._record_quiz(ev.block_id, ev.payload.get("answers", {}), session_id)

    def _record_quiz(self, block_id: str | None, answers: Any, session_id: str | None) -> None:
        block = next((b for b in self.room.rundown if b["id"] == block_id), None)
        if block is None or not isinstance(answers, dict):
            return
        try:
            pool.record_reveal(self.db, block, answers, session_id, datetime.now(BERLIN).date())
        except Exception:  # Fragenpool darf die Sendung nie aufhalten
            log.exception("Quizantwort für %s nicht gespeichert.", block_id)

    async def _broadcast(self) -> None:
        now = time.monotonic()
        tv_state = self.room.state(now)
        for ws in list(self.tv_sockets):
            try:
                await ws.send_json(tv_state)
            except Exception:  # Verbindung weg
                self.tv_sockets.discard(ws)
        for ws, person_id in list(self.controller_sockets.items()):
            try:
                await ws.send_json(self.room.state(now, viewer=person_id))
            except Exception:
                self.controller_sockets.pop(ws, None)
