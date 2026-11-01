"""Profilfragebogen (SPEC §4.1): versioniert, mit Sichtbarkeit pro Person."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select

from abendausgabe.api.deps import Identity, require_identity, require_member
from abendausgabe.core.config import load_yaml
from abendausgabe.core.db import Database
from abendausgabe.core.models import ProfileAnswer

router = APIRouter(prefix="/api/profile")

VISIBILITIES = {"self", "admins", "all"}
WEEKDAYS = {"mo", "di", "mi", "do", "fr", "sa", "so"}
MAX_TEXT = 2000
MAX_ITEMS = 30


class ProfileIn(BaseModel):
    answers: dict[str, Any]
    visibility: str


def load_schema() -> dict[str, Any]:
    schema: dict[str, Any] = load_yaml("profile_schema.yaml")
    return schema


def _fail(field_id: str, message: str) -> HTTPException:
    return HTTPException(status_code=422, detail=f"{field_id}: {message}")


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def validate_answers(schema: dict[str, Any], answers: dict[str, Any]) -> dict[str, Any]:
    fields = {f["id"]: f for f in schema.get("fields", [])}
    unknown = set(answers) - set(fields)
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unbekannte Felder: {sorted(unknown)}")
    clean: dict[str, Any] = {}
    for field_id, value in answers.items():
        field = fields[field_id]
        kind = field["type"]
        if value is None or value == "" or value == []:
            continue
        if kind in {"text", "textarea"}:
            if not isinstance(value, str) or len(value) > MAX_TEXT:
                raise _fail(field_id, f"Text bis {MAX_TEXT} Zeichen erwartet.")
            clean[field_id] = value.strip()
        elif kind == "links":
            if not _is_str_list(value) or len(value) > MAX_ITEMS:
                raise _fail(field_id, "Liste von Links erwartet.")
            if any(not v.startswith(("http://", "https://")) or len(v) > 500 for v in value):
                raise _fail(field_id, "Links müssen mit http:// oder https:// beginnen.")
            clean[field_id] = value
        elif kind == "tags":
            if not _is_str_list(value) or len(value) > MAX_ITEMS or any(len(v) > 60 for v in value):
                raise _fail(field_id, "Liste kurzer Begriffe erwartet.")
            clean[field_id] = [v.strip() for v in value if v.strip()]
        elif kind == "rank":
            options = field.get("options", [])
            if not _is_str_list(value) or len(set(value)) != len(value):
                raise _fail(field_id, "Rangfolge ohne Doppelte erwartet.")
            if any(v not in options for v in value):
                raise _fail(field_id, "Unbekannte Option in der Rangfolge.")
            clean[field_id] = value
        elif kind == "slider":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise _fail(field_id, "Zahl erwartet.")
            if not field.get("min", 0) <= value <= field.get("max", 10):
                raise _fail(field_id, "Wert außerhalb des Bereichs.")
            clean[field_id] = value
        elif kind == "weekdays":
            if not _is_str_list(value) or any(v not in WEEKDAYS for v in value):
                raise _fail(field_id, "Wochentage als mo, di, mi, do, fr, sa, so erwartet.")
            clean[field_id] = sorted(
                set(value), key=["mo", "di", "mi", "do", "fr", "sa", "so"].index
            )
        else:
            raise _fail(field_id, f"Unbekannter Feldtyp {kind}.")
    return clean


def _latest(request: Request, person_id: str) -> ProfileAnswer | None:
    db: Database = request.app.state.db
    with db.session() as s:
        stmt = (
            select(ProfileAnswer)
            .where(ProfileAnswer.person_id == person_id)
            .order_by(ProfileAnswer.version.desc())
            .limit(1)
        )
        return s.scalars(stmt).first()


def _as_dict(row: ProfileAnswer) -> dict[str, Any]:
    return {
        "person_id": row.person_id,
        "version": row.version,
        "answers": json.loads(row.answers_json),
        "visibility": row.visibility,
        "updated_at": row.created_at.isoformat(),
    }


@router.get("/schema")
def schema() -> dict[str, Any]:
    return load_schema()


@router.get("/me")
def my_profile(request: Request, identity: Identity = Depends(require_member)) -> dict[str, Any]:
    row = _latest(request, identity.person_id)
    if row is None:
        return {"person_id": identity.person_id, "version": 0, "answers": {}, "visibility": None}
    return _as_dict(row)


@router.post("")
def save_profile(
    body: ProfileIn, request: Request, identity: Identity = Depends(require_member)
) -> dict[str, Any]:
    if body.visibility not in VISIBILITIES:
        raise HTTPException(status_code=422, detail="Sichtbarkeit muss self, admins oder all sein.")
    clean = validate_answers(load_schema(), body.answers)
    with request.app.state.db.session() as s:
        current = s.scalar(
            select(func.max(ProfileAnswer.version)).where(
                ProfileAnswer.person_id == identity.person_id
            )
        )
        row = ProfileAnswer(
            person_id=identity.person_id,
            version=(current or 0) + 1,
            answers_json=json.dumps(clean, ensure_ascii=False),
            visibility=body.visibility,
        )
        s.add(row)
        s.commit()
        return _as_dict(row)


@router.get("/{person_id}")
def read_profile(
    person_id: str, request: Request, identity: Identity = Depends(require_identity)
) -> dict[str, Any]:
    row = _latest(request, person_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Noch kein Profil.")
    if identity.person_id != person_id:
        allowed = (row.visibility == "all" and identity.role != "guest") or (
            row.visibility == "admins" and identity.role == "admin"
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="Diese Antworten sind privat.")
    return _as_dict(row)
