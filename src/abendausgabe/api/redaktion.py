"""Schnittstelle für die Redaktion auf dem Mac (SPEC §11.1, decisions.md Nr. 63).

Nur im Heimnetz und nur mit `ABEND_REDAKTION_TOKEN`; ohne Token gibt es die Routen nicht.
"""

from __future__ import annotations

import hmac
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from abendausgabe.core.db import Database
from abendausgabe.modules.weltblick import translations

router = APIRouter(prefix="/api/redaktion")


def require_redaktion(request: Request) -> Database:
    expected: str = request.app.state.settings.redaktion_token
    if not expected:
        raise HTTPException(status_code=404)
    given = request.headers.get("authorization", "")
    if not hmac.compare_digest(given.encode(), f"Bearer {expected}".encode()):
        raise HTTPException(
            status_code=401,
            detail="Redaktions-Token fehlt oder stimmt nicht. ABEND_REDAKTION_TOKEN prüfen.",
        )
    db: Database = request.app.state.db
    return db


class TranslationIn(BaseModel):
    raw_item_id: str = Field(max_length=40)
    text: str = Field(max_length=translations.MAX_TEXT)


class TranslationsIn(BaseModel):
    model: str = Field(max_length=80)
    prompt_version: str = Field(max_length=16)
    items: list[TranslationIn] = Field(max_length=500)


@router.get("/translations/pending")
def pending(prompt_version: str, db: Database = Depends(require_redaktion)) -> dict[str, Any]:
    rows = translations.pending(db, datetime.now(UTC), prompt_version[:16])
    return {"items": [{"id": r.id, "title": r.title, "language": r.language} for r in rows]}


@router.post("/translations")
def save(body: TranslationsIn, db: Database = Depends(require_redaktion)) -> dict[str, int]:
    pairs = [(i.raw_item_id, i.text) for i in body.items]
    return {"saved": translations.save(db, pairs, body.model, body.prompt_version)}
