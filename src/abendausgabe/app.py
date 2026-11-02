"""FastAPI-Anwendung: API, WebSockets und statische Oberflächen."""

from __future__ import annotations

import asyncio
import logging
import time
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
from abendausgabe.modules.weltblick.block import mark_shown
from abendausgabe.modules.weltblick.catalog import Source, selected_sources
from abendausgabe.modules.weltblick.fetch import refresh_all
from abendausgabe.session.manager import ProgramBuilder, RoomManager
from abendausgabe.session.room import Room
from abendausgabe.session.rundown import load_rundown

FETCH_EVERY_S = 2 * 3600

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


def _sources(settings: Settings) -> list[Source]:
    try:
        return selected_sources(settings.catalog_dir)
    except (OSError, ValueError, KeyError) as exc:
        logging.getLogger("abendausgabe").warning("Quellenkatalog fehlerhaft: %s", exc)
        return []


async def _background_loop(db: Database, settings: Settings) -> None:
    """Einmal pro Minute: Morgen-Push fällig? Alle 2 Stunden: Quellen abrufen.

    Eine schlanke Schleife statt APScheduler (decisions.md Nr. 46, 51).
    """
    log = logging.getLogger("abendausgabe.planer")
    last_fetch = -float(FETCH_EVERY_S)
    while True:
        try:
            await morning_job(db, settings, datetime.now(BERLIN))
        except Exception:
            log.exception("Morgen-Push-Lauf fehlgeschlagen.")
        if settings.program == "heute" and time.monotonic() - last_fetch >= FETCH_EVERY_S:
            last_fetch = time.monotonic()
            try:
                result = await refresh_all(db, _sources(settings))
                new = sum(n for n in result.values() if n > 0)
                failed = [k for k, n in result.items() if n < 0]
                log.info("Quellen abgerufen: %d neu, nicht erreichbar: %s", new, failed or "keine")
            except Exception:
                log.exception("Quellenabruf fehlgeschlagen.")
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
            return await build_program(datetime.now(BERLIN), db, _sources(settings))

        program = program_today
    else:
        raise ValueError(f"ABEND_PROGRAM={settings.program!r} unbekannt; erlaubt: heute, test.")
    room = Room(rundown, ask_timeout_s=settings.ask_timeout_s)

    def on_start(started: list[dict[str, Any]]) -> None:
        mark_shown(db, started, datetime.now(BERLIN).date())

    manager = RoomManager(room, db, program=program, on_start=on_start)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await manager.start()
        warmup = asyncio.create_task(manager.refresh_program())
        planner = asyncio.create_task(_background_loop(db, settings))
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
