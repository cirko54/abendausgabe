"""FastAPI-Anwendung: API, WebSockets und statische Oberflächen."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from abendausgabe import __version__
from abendausgabe.api import devices, media, morning, profile, qr, tvcheck, ws
from abendausgabe.assembly.notausgabe import build_program
from abendausgabe.core.config import Settings, get_people, get_settings
from abendausgabe.core.dates import BERLIN
from abendausgabe.core.db import Database
from abendausgabe.core.security import AttemptLimiter
from abendausgabe.learning.morning import morning_job
from abendausgabe.session.manager import ProgramBuilder, RoomManager
from abendausgabe.session.room import Room
from abendausgabe.session.rundown import load_rundown

STATIC_MOUNTS = (
    ("/tv", "tv"),
    ("/c", "c"),
    ("/p", "p"),
    ("/admin", "admin"),
    ("/shared", "shared"),
)


def _setup_logging() -> None:
    """App-Meldungen ab INFO ins Container-Log (z. B. Wiedergabe-Rückmeldungen des Fernsehers)."""
    logger = logging.getLogger("abendausgabe")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False


async def _morning_loop(db: Database, settings: Settings) -> None:
    """Einmal pro Minute: Morgen-Push fällig? (decisions.md Nr. 46, ohne APScheduler)"""
    log = logging.getLogger("abendausgabe.morning")
    while True:
        try:
            await morning_job(db, settings, datetime.now(BERLIN))
        except Exception:
            log.exception("Morgen-Push-Lauf fehlgeschlagen.")
        await asyncio.sleep(60)


def create_app() -> FastAPI:
    _setup_logging()
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(f"sqlite:///{settings.data_dir / 'abendausgabe.sqlite3'}")
    program: ProgramBuilder | None = None
    if settings.program == "test":
        rundown = load_rundown()
    elif settings.program == "heute":
        # Platzhalter, bis der Tagesablauf beim Start im Hintergrund fertig ist
        rundown = [
            {"id": "begruessung", "type": "info", "title": "Guten Abend", "est_minutes": 1},
            {"id": "ende", "type": "end", "title": "Sendeschluss", "est_minutes": 0},
        ]

        async def program_today() -> list[dict[str, Any]]:
            return await build_program(datetime.now(BERLIN))

        program = program_today
    else:
        raise ValueError(f"ABEND_PROGRAM={settings.program!r} unbekannt; erlaubt: heute, test.")
    room = Room(rundown, ask_timeout_s=settings.ask_timeout_s)
    manager = RoomManager(room, db, program=program)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await manager.start()
        warmup = asyncio.create_task(manager.refresh_program())
        planner = asyncio.create_task(_morning_loop(db, settings))
        yield
        warmup.cancel()
        planner.cancel()
        await manager.stop()

    app = FastAPI(title="Abendausgabe", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db
    app.state.people = get_people()
    app.state.manager = manager
    app.state.pin_limiter = AttemptLimiter()

    routers = (
        devices.router,
        profile.router,
        tvcheck.router,
        qr.router,
        media.router,
        morning.router,
        ws.router,
    )
    for router in routers:
        app.include_router(router)

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/tv/")

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    for prefix, folder in STATIC_MOUNTS:
        app.mount(prefix, StaticFiles(directory=settings.web_dir / folder, html=True), name=folder)
    return app
