"""Mitbringsel speichern, auswählen und als Blöcke in die Sendung setzen (Nr. 56)."""

from __future__ import annotations

import json
import random
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from abendausgabe.core.db import Database
from abendausgabe.core.models import Mitbringsel
from abendausgabe.modules.mitbringsel.resolve import PROVIDER_NAMES, Resolved

TTL = timedelta(days=7)
MAX_OPEN = 10
MAX_PER_DAY = 20
MAX_PER_SHOW = 3
GUESS_MIN_PRESENT = 3
PREFIX = "mitbringsel-"
MAX_NOTE = 280
MAX_PHOTO_BYTES = 3_000_000
PHOTO_DIR = "mitbringsel"
PHOTO_NAME = re.compile(r"^[a-f0-9]{32}\.(jpg|png|webp)$")
# Dateikopf statt Dateiendung: Nur echte Bilder werden gespeichert
MAGIC = {b"\xff\xd8\xff": "jpg", b"\x89PNG\r\n\x1a\n": "png"}


class LimitError(ValueError):
    pass


@dataclass(frozen=True)
class Person:
    id: str
    name: str


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def photo_kind(data: bytes) -> str | None:
    for magic, ext in MAGIC.items():
        if data.startswith(magic):
            return ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def add_photo(
    db: Database, data_dir: Path, person_id: str, data: bytes, note: str, now: datetime
) -> dict[str, Any]:
    """Eigenes Foto oder Screenshot (z. B. aus Instagram oder WhatsApp); bleibt im Haus."""
    ext = photo_kind(data)
    if ext is None:
        raise ValueError("Nur Fotos als JPEG, PNG oder WebP.")
    if len(data) > MAX_PHOTO_BYTES:
        raise ValueError("Das Foto ist zu groß (höchstens 3 MB).")
    _check_limits(db, person_id, now)
    folder = data_dir / PHOTO_DIR
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    (folder / name).write_bytes(data)
    r = Resolved(
        url="", kind="image", provider="foto", title="", image=f"/api/mitbringsel/bild/{name}"
    )
    return add(db, person_id, r, note, now)


def add_text(db: Database, person_id: str, text: str, now: datetime) -> dict[str, Any]:
    """Ein Gedanke oder eine Frage an die Runde, ganz ohne Link."""
    text = " ".join(text.split())[:MAX_NOTE]
    if not text:
        raise ValueError("Ein Link, ein Foto oder ein Satz – irgendwas muss rein.")
    return add(db, person_id, Resolved(url="", kind="text", provider="notiz", title=text), "", now)


def _check_limits(db: Database, person_id: str, now: datetime) -> None:
    with db.session() as s:
        open_count = s.scalar(
            select(func.count(Mitbringsel.id)).where(
                Mitbringsel.person_id == person_id,
                Mitbringsel.shown_on.is_(None),
                Mitbringsel.expires_at > now,
            )
        )
        today_count = s.scalar(
            select(func.count(Mitbringsel.id)).where(
                Mitbringsel.person_id == person_id,
                Mitbringsel.created_at > now - timedelta(days=1),
            )
        )
        if (open_count or 0) >= MAX_OPEN:
            raise LimitError(f"Höchstens {MAX_OPEN} offene Mitbringsel. Erst eins zurücknehmen.")
        if (today_count or 0) >= MAX_PER_DAY:
            raise LimitError("Für heute ist genug geteilt. Morgen wieder.")


def add(db: Database, person_id: str, r: Resolved, note: str, now: datetime) -> dict[str, Any]:
    note = " ".join(note.split())[:MAX_NOTE]
    if r.provider != "foto":  # beim Foto schon geprüft, bevor die Datei geschrieben wird
        _check_limits(db, person_id, now)
    with db.session() as s:
        row = Mitbringsel(
            person_id=person_id,
            url=r.url[:600],
            note=note,
            kind=r.kind,
            provider=r.provider,
            title=r.title[:300],
            author=r.author[:120],
            image=r.image,
            embed_src=r.embed_src,
            video_json=json.dumps(r.video) if r.video else None,
            vertical=int(r.vertical),
            created_at=now,
            expires_at=now + TTL,
        )
        s.add(row)
        s.commit()
        return view(row)


def view(row: Mitbringsel) -> dict[str, Any]:
    return {
        "id": row.id,
        "url": row.url,
        "note": row.note,
        "kind": row.kind,
        "provider": PROVIDER_NAMES.get(row.provider, row.provider),
        "title": row.title,
        "image": row.image,
        "created_at": _aware(row.created_at).isoformat(),
    }


def pending(db: Database, person_id: str, now: datetime) -> list[dict[str, Any]]:
    with db.session() as s:
        rows = s.scalars(
            select(Mitbringsel)
            .where(
                Mitbringsel.person_id == person_id,
                Mitbringsel.shown_on.is_(None),
                Mitbringsel.expires_at > now,
            )
            .order_by(Mitbringsel.created_at)
        ).all()
        return [view(r) for r in rows]


def _photo_path(data_dir: Path, row: Mitbringsel) -> Path | None:
    if row.provider != "foto" or not row.image:
        return None
    name = row.image.rsplit("/", 1)[-1]
    return data_dir / PHOTO_DIR / name if PHOTO_NAME.match(name) else None


def remove(db: Database, data_dir: Path, person_id: str, item_id: int) -> bool:
    with db.session() as s:
        row = s.get(Mitbringsel, item_id)
        if row is None or row.person_id != person_id or row.shown_on is not None:
            return False
        path = _photo_path(data_dir, row)
        s.delete(row)
        s.commit()
    if path is not None:
        path.unlink(missing_ok=True)
    return True


def purge(db: Database, data_dir: Path, now: datetime) -> int:
    """Abgelaufenes löschen, Fotos eingeschlossen (7 Tage nach dem Teilen)."""
    with db.session() as s:
        rows = s.scalars(select(Mitbringsel).where(Mitbringsel.expires_at < now)).all()
        paths = [_photo_path(data_dir, r) for r in rows]
        for row in rows:
            s.delete(row)
        s.commit()
    for path in paths:
        if path is not None:
            path.unlink(missing_ok=True)
    return len(rows)


# ------------------------------------------------------------------ Sendung


def _present_blocks(row: Mitbringsel, by: Person | None) -> dict[str, Any]:
    """Der Beitrag selbst; ohne Raterunde steht der Name gleich dabei."""
    provider = PROVIDER_NAMES.get(row.provider, row.provider)
    credit = ""
    if by is not None:
        credit = f"Mitgebracht von {by.name}" + (f": „{row.note}“" if row.note else "")
    base: dict[str, Any] = {
        "id": f"{PREFIX}{row.id}",
        "title": "Mitbringsel",
        "caption": row.title,
        "credit": credit,
        "attribution": provider + (f" · {row.author}" if row.author else ""),
        "link": row.url or None,
        "mitbringsel_id": row.id,
        "est_minutes": 2,
    }
    if row.kind == "text":
        return {**base, "type": "info", "caption": "", "body": row.title, "attribution": "",
                "est_minutes": 1}  # fmt: skip
    if row.kind == "embed" and row.embed_src:
        return {**base, "type": "embed", "src": row.embed_src, "vertical": bool(row.vertical)}
    if row.kind == "video" and row.video_json:
        video = json.loads(row.video_json)
        return {
            **base,
            "type": "video",
            "src": video["src"],
            "format": video.get("format", "hls"),
            "poster": video.get("poster"),
            "vertical": bool(row.vertical),
            "muted": False,
        }
    body = row.author or ("" if row.provider == "foto" else provider)
    block = {**base, "type": "info", "body": body, "est_minutes": 1}
    if row.image:
        # eigene Fotos groß, Artikel mit Bild und Text daneben
        block["media"] = {"kind": "image", "src": row.image, "large": row.provider == "foto"}
    return block


def _guess_block(
    row: Mitbringsel, by: Person, present: list[Person], rng: random.Random
) -> dict[str, Any]:
    names = [p.name for p in present]
    rng.shuffle(names)
    source = f"Mitgebracht von {by.name}" + (f": „{row.note}“" if row.note else "")
    block: dict[str, Any] = {
        "id": f"{PREFIX}{row.id}-wer",
        "type": "choice",
        "title": "Mitbringsel",
        "question": "Wer hat das mitgebracht?",
        "options": names,
        "correct": names.index(by.name),
        "exempt": [by.id],  # wer es mitgebracht hat, rät nicht mit
        "source": source,
        "source_label": "",  # keine „Quelle:“, sondern die Person
        "link": row.url or None,
        "timeout_s": 30,
        "est_minutes": 1,
    }
    if row.image:
        block["media"] = {"kind": "image", "src": row.image}
        block["caption"] = row.title
    elif row.kind == "text":
        block["caption"] = row.title
    return block


def show_blocks(db: Database, present: list[Person], now: datetime) -> list[dict[str, Any]]:
    """Höchstens eins pro anwesender Person, höchstens drei, die ältesten zuerst."""
    ids = {p.id: p for p in present}
    if not ids:
        return []
    with db.session() as s:
        rows = s.scalars(
            select(Mitbringsel)
            .where(
                Mitbringsel.person_id.in_(list(ids)),
                Mitbringsel.shown_on.is_(None),
                Mitbringsel.expires_at > now,
            )
            .order_by(Mitbringsel.created_at)
        ).all()
    chosen: list[Mitbringsel] = []
    for row in rows:
        if row.person_id not in {c.person_id for c in chosen}:
            chosen.append(row)
        if len(chosen) == MAX_PER_SHOW:
            break
    rng = random.Random(now.date().isoformat())
    guess = len(present) >= GUESS_MIN_PRESENT
    blocks: list[dict[str, Any]] = []
    for row in chosen:
        by = ids[row.person_id]
        blocks.append(_present_blocks(row, None if guess else by))
        if guess:
            blocks.append(_guess_block(row, by, present, rng))
    return blocks


def with_mitbringsel(
    rundown: list[dict[str, Any]], blocks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Gleich nach der Begrüßung; frühere Mitbringsel-Blöcke werden ersetzt."""
    body = [b for b in rundown if not str(b["id"]).startswith(PREFIX)]
    at = 1 if body and body[0].get("id") == "begruessung" else 0
    return [*body[:at], *blocks, *body[at:]]


def mark_shown(db: Database, rundown: list[dict[str, Any]], today: date) -> None:
    ids = {int(b["mitbringsel_id"]) for b in rundown if b.get("mitbringsel_id")}
    if not ids:
        return
    with db.session() as s:
        for row in s.scalars(select(Mitbringsel).where(Mitbringsel.id.in_(ids))):
            row.shown_on = today
        s.commit()
