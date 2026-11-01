"""QR-Code als SVG für den Beitritt per Handy."""

from __future__ import annotations

import io

import segno
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

router = APIRouter(prefix="/api")


@router.get("/qr.svg")
def qr_svg(data: str = Query(..., max_length=512)) -> Response:
    if not data.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="Nur http- oder https-Adressen.")
    buffer = io.BytesIO()
    segno.make(data, error="m").save(
        buffer, kind="svg", scale=10, border=3, dark="#0F1C2E", light="#E9EEF2"
    )
    return Response(content=buffer.getvalue(), media_type="image/svg+xml")
