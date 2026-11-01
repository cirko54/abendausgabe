"""FastAPI-Anwendung: API, WebSockets und statische Oberflächen."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from abendausgabe import __version__
from abendausgabe.api import devices, profile, qr, tvcheck, ws
from abendausgabe.core.config import get_people, get_settings
from abendausgabe.core.db import Database
from abendausgabe.core.security import AttemptLimiter
from abendausgabe.session.manager import RoomManager
from abendausgabe.session.room import Room
from abendausgabe.session.rundown import load_rundown

STATIC_MOUNTS = (
    ("/tv", "tv"),
    ("/c", "c"),
    ("/p", "p"),
    ("/admin", "admin"),
    ("/shared", "shared"),
)


def create_app() -> FastAPI:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(f"sqlite:///{settings.data_dir / 'abendausgabe.sqlite3'}")
    room = Room(load_rundown(), ask_timeout_s=settings.ask_timeout_s)
    manager = RoomManager(room, db)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await manager.start()
        yield
        await manager.stop()

    app = FastAPI(title="Abendausgabe", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db
    app.state.people = get_people()
    app.state.manager = manager
    app.state.pin_limiter = AttemptLimiter()

    for router in (devices.router, profile.router, tvcheck.router, qr.router, ws.router):
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
