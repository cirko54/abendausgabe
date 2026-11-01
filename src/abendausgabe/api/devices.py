"""Anmeldung von Geräten: Person wählen, PIN beim ersten Mal festlegen."""

from __future__ import annotations

import re
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import delete, select

from abendausgabe.api.deps import COOKIE_NAME, Identity, require_identity
from abendausgabe.core.models import Device, PersonClaim
from abendausgabe.core.security import hash_pin, hash_token, new_salt, new_token, verify_pin

router = APIRouter(prefix="/api")

PIN_PATTERN = re.compile(r"\d{4,8}")
COOKIE_MAX_AGE = 365 * 24 * 3600


class DeviceIn(BaseModel):
    person_id: str
    pin: str | None = None


@router.get("/people")
def list_people(request: Request) -> dict[str, Any]:
    people = request.app.state.people
    with request.app.state.db.session() as s:
        claimed = set(s.scalars(select(PersonClaim.person_id)))
    return {
        "people": [
            {
                "id": p.id,
                "name": p.name,
                "color": p.color,
                "role": p.role,
                "claimed": p.id in claimed,
            }
            for p in people.persons.values()
        ],
        "guest_color": people.guest_color,
    }


@router.post("/devices")
def register_device(body: DeviceIn, request: Request, response: Response) -> dict[str, str]:
    people = request.app.state.people
    db = request.app.state.db
    limiter = request.app.state.pin_limiter
    if body.person_id == "gast":
        person_id = f"gast-{secrets.token_hex(2)}"
        identity = Identity(
            person_id, f"Gast {person_id[-4:].upper()}", people.guest_color, "guest"
        )
    else:
        person = people.get(body.person_id)
        if person is None:
            raise HTTPException(status_code=404, detail="Diese Person gibt es nicht.")
        pin = body.pin or ""
        if not PIN_PATTERN.fullmatch(pin):
            raise HTTPException(status_code=422, detail="Die PIN muss 4 bis 8 Ziffern haben.")
        if not limiter.allowed(person.id):
            raise HTTPException(
                status_code=429, detail="Zu viele Fehlversuche. In 10 Minuten erneut versuchen."
            )
        with db.session() as s:
            claim = s.get(PersonClaim, person.id)
            if claim is None:
                salt = new_salt()
                s.add(PersonClaim(person_id=person.id, pin_hash=hash_pin(pin, salt), salt=salt))
                s.commit()
            elif not verify_pin(pin, claim.salt, claim.pin_hash):
                limiter.record_failure(person.id)
                raise HTTPException(status_code=403, detail="Die PIN stimmt nicht.")
        limiter.reset(person.id)
        identity = Identity(person.id, person.name, person.color, person.role)

    token = new_token()
    with db.session() as s:
        s.add(
            Device(
                token_hash=hash_token(token),
                person_id=identity.person_id,
                display_name=identity.name,
                user_agent=request.headers.get("user-agent", "")[:400],
            )
        )
        s.commit()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=request.app.state.settings.cookie_secure,
    )
    return identity.as_dict()


@router.get("/me")
def me(identity: Identity = Depends(require_identity)) -> dict[str, str]:
    return identity.as_dict()


@router.post("/devices/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        with request.app.state.db.session() as s:
            s.execute(delete(Device).where(Device.token_hash == hash_token(token)))
            s.commit()
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}
