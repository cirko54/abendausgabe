"""Identität über das Gerätetoken-Cookie."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from fastapi import HTTPException, Request

from abendausgabe.core.config import People
from abendausgabe.core.db import Database
from abendausgabe.core.models import Device, utcnow
from abendausgabe.core.security import hash_token

COOKIE_NAME = "abend_device"


@dataclass(frozen=True)
class Identity:
    person_id: str
    name: str
    color: str
    role: str  # admin | member | guest

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def identity_from_token(token: str | None, db: Database, people: People) -> Identity | None:
    if not token:
        return None
    with db.session() as s:
        device = s.get(Device, hash_token(token))
        if device is None:
            return None
        device.last_seen = utcnow()
        s.commit()
        person = people.get(device.person_id)
        if person is not None:
            return Identity(person.id, person.name, person.color, person.role)
        if device.person_id.startswith("gast-"):
            return Identity(device.person_id, device.display_name, people.guest_color, "guest")
    return None


def current_identity(request: Request) -> Identity | None:
    return identity_from_token(
        request.cookies.get(COOKIE_NAME), request.app.state.db, request.app.state.people
    )


def require_identity(request: Request) -> Identity:
    identity = current_identity(request)
    if identity is None:
        raise HTTPException(status_code=401, detail="Nicht angemeldet. Erst unter /c/ anmelden.")
    return identity


def require_member(request: Request) -> Identity:
    identity = require_identity(request)
    if identity.role == "guest":
        raise HTTPException(status_code=403, detail="Gäste haben kein Profil.")
    return identity


def require_admin(request: Request) -> Identity:
    identity = require_identity(request)
    if identity.role != "admin":
        raise HTTPException(status_code=403, detail="Nur für Admins.")
    return identity
