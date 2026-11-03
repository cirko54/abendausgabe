"""Mitbringsel teilen und zurücknehmen (decisions.md Nr. 56). Nur im LAN."""

from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from abendausgabe.api.deps import Identity, require_identity
from abendausgabe.core.db import Database
from abendausgabe.core.ratelimit import RateLimitedError
from abendausgabe.core.safefetch import UnsafeURLError
from abendausgabe.modules.mitbringsel import resolve, store

router = APIRouter(prefix="/api/mitbringsel")


class ShareIn(BaseModel):
    url: str = ""
    note: str = ""
    photo: str = ""  # data:image/...;base64,… (das Handy verkleinert vorher)


MAX_PHOTO_FIELD = 4_200_000


def _db(request: Request) -> Database:
    db: Database = request.app.state.db
    return db


@router.get("")
def mine(request: Request, identity: Identity = Depends(require_identity)) -> dict[str, Any]:
    return {"items": store.pending(_db(request), identity.person_id, datetime.now(UTC))}


@router.post("")
async def share(
    body: ShareIn, request: Request, identity: Identity = Depends(require_identity)
) -> dict[str, Any]:
    if len(body.url) > 600:
        raise HTTPException(status_code=422, detail="Der Link ist zu lang.")
    db, now = _db(request), datetime.now(UTC)
    settings = request.app.state.settings
    try:
        if body.photo:
            if len(body.photo) > MAX_PHOTO_FIELD:
                raise ValueError("Das Foto ist zu groß (höchstens 3 MB).")
            data = base64.b64decode(body.photo.split(",", 1)[-1], validate=True)
            return {"item": store.add_photo(db, settings.data_dir, identity.person_id, data,
                                            body.note, now)}  # fmt: skip
        if not body.url.strip():
            return {"item": store.add_text(db, identity.person_id, body.note, now)}
    except store.LimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    transport = getattr(request.app.state, "mitbringsel_transport", None)
    try:
        async with resolve.make_client(transport) as client:
            resolved = await resolve.resolve(body.url, client)
    except UnsafeURLError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RateLimitedError as exc:
        raise HTTPException(status_code=429, detail="Gerade zu viele Links. Später.") from exc
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=422,
            detail="Der Link lässt sich nicht öffnen. Ist er öffentlich und richtig kopiert?",
        ) from exc
    try:
        item = store.add(db, identity.person_id, resolved, body.note, now)
    except store.LimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return {"item": item}


@router.delete("/{item_id}")
def take_back(
    item_id: int, request: Request, identity: Identity = Depends(require_identity)
) -> dict[str, bool]:
    data_dir = request.app.state.settings.data_dir
    if not store.remove(_db(request), data_dir, identity.person_id, item_id):
        raise HTTPException(status_code=404, detail="Nicht gefunden oder schon gezeigt.")
    return {"removed": True}


@router.get("/bild/{name}")
def photo(name: str, request: Request) -> FileResponse:
    """Für den Fernseher (ohne Anmeldung, nur im LAN); der Name ist zufällig (128 Bit)."""
    if not store.PHOTO_NAME.match(name):
        raise HTTPException(status_code=404, detail="Kein Bild.")
    path = request.app.state.settings.data_dir / store.PHOTO_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Bild nicht mehr da.")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=86400"})
