"""Morgen danach und Push-Einstellung (decisions.md Nr. 45, 46). Nur im LAN."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from abendausgabe.api.deps import Identity, require_member
from abendausgabe.core import push
from abendausgabe.core.dates import BERLIN
from abendausgabe.core.db import Database
from abendausgabe.core.models import PushTopic
from abendausgabe.learning import morning

router = APIRouter(prefix="/api")


class MorningIn(BaseModel):
    session_id: str
    rating: int
    answer: int | None = None


def _db(request: Request) -> Database:
    db: Database = request.app.state.db
    return db


@router.get("/morning")
async def get_morning(
    request: Request, identity: Identity = Depends(require_member)
) -> dict[str, Any]:
    db = _db(request)
    now = datetime.now(BERLIN)
    if morning.card(db, identity.person_id, now) is not None:
        await morning.ensure_tagesschau_item(db)
    return {"card": morning.card(db, identity.person_id, now)}


@router.post("/morning")
def post_morning(
    body: MorningIn, request: Request, identity: Identity = Depends(require_member)
) -> dict[str, Any]:
    try:
        return morning.submit(
            _db(request),
            identity.person_id,
            body.session_id,
            body.rating,
            body.answer,
            datetime.now(BERLIN),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _push_view(request: Request, topic: PushTopic | None) -> dict[str, Any]:
    server: str = request.app.state.settings.ntfy_url
    morning_push = request.app.state.settings.morning_push
    view: dict[str, Any] = {
        "enabled": topic is not None,
        "server": server,
        "time": morning_push.strftime("%H:%M") if morning_push else None,
    }
    if topic is not None:
        view.update(push.subscribe_links(server, topic.topic))
    return view


@router.get("/push")
def get_push(request: Request, identity: Identity = Depends(require_member)) -> dict[str, Any]:
    with _db(request).session() as s:
        return _push_view(request, s.get(PushTopic, identity.person_id))


@router.post("/push")
def enable_push(request: Request, identity: Identity = Depends(require_member)) -> dict[str, Any]:
    """Einschalten. Die Adresse, unter der das Handy den Server erreicht, wird der Link im Push."""
    base_url = str(request.base_url).rstrip("/")
    with _db(request).session() as s:
        topic = s.get(PushTopic, identity.person_id)
        if topic is None:
            topic = PushTopic(
                person_id=identity.person_id, topic=push.new_topic(), base_url=base_url
            )
            s.add(topic)
        else:
            topic.base_url = base_url
        s.commit()
        return _push_view(request, topic)


@router.delete("/push")
def disable_push(request: Request, identity: Identity = Depends(require_member)) -> dict[str, Any]:
    with _db(request).session() as s:
        topic = s.get(PushTopic, identity.person_id)
        if topic is not None:
            s.delete(topic)
            s.commit()
    return _push_view(request, None)


@router.post("/push/test")
async def test_push(
    request: Request, identity: Identity = Depends(require_member)
) -> dict[str, str]:
    with _db(request).session() as s:
        topic = s.get(PushTopic, identity.person_id)
        if topic is None:
            raise HTTPException(status_code=409, detail="Morgenfrage ist aus. Erst einschalten.")
        topic_name, base_url = topic.topic, topic.base_url
    try:
        await push.publish(
            request.app.state.settings.ntfy_url,
            topic_name,
            morning.PUSH_TITLE,
            "Testnachricht. So sieht die Morgenfrage aus.",
            click=base_url + "/c/#morgen",
            transport=getattr(request.app.state, "push_transport", None),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Testnachricht nicht verschickt. Server offline? Später erneut probieren.",
        ) from exc
    return {"status": "sent"}
