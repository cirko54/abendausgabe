"""TV-Fähigkeitstest (SPEC §11.2): Bericht speichern und Entscheidung ableiten."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from abendausgabe.api.deps import Identity, require_admin
from abendausgabe.core.models import TvCheckReport
from abendausgabe.modules.tagesschau.fetch import media_for_check

router = APIRouter(prefix="/api/tv-check")

MAX_REPORT_BYTES = 64_000


def _ok(report: dict[str, Any], *path: str) -> bool:
    node: Any = report
    for key in path:
        if not isinstance(node, dict):
            return False
        node = node.get(key)
    return bool(node)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def compute_verdict(report: dict[str, Any]) -> dict[str, Any]:
    notes: list[str] = []
    es2017 = _ok(report, "js", "es2017")
    ws_ok = _ok(report, "websocket", "ok")
    urls = _dict(report.get("mediaUrls"))
    mp4 = _dict(_dict(report.get("media")).get("mp4"))
    # Ältere Berichte kennen „tested“ nicht: dann zählt, ob es ein Testvideo gab.
    mp4_tested = bool(mp4.get("tested", bool(urls.get("mp4"))))
    mp4_ok = _ok(report, "media", "mp4", "ok")
    hls_native_ok = _ok(report, "media", "hls_native", "ok")
    mse = _ok(report, "media", "mse")
    hls_js = _dict(_dict(report.get("media")).get("hls_js"))
    hls_js_tested = bool(hls_js.get("tested"))
    hls_js_ok = _ok(report, "media", "hls_js", "ok")
    yt_ok = _ok(report, "youtube", "ok")
    try:
        fps = float(report.get("fps") or 0)
    except (TypeError, ValueError):
        fps = 0.0

    if not _ok(report, "js", "es2020"):
        notes.append("Kein ES2020: Build-Target es2017 beibehalten.")
    if hls_js_tested:
        notes.append(
            "Livestream über hls.js "
            + ("getestet: spielt." if hls_js_ok else "getestet: spielt nicht.")
        )
    elif not hls_native_ok and mse:
        notes.append("HLS nicht nativ, aber MediaSource vorhanden: hls.js nötig.")
    if not _ok(report, "font", "ok"):
        notes.append("Webfont nicht geladen: Darstellung mit Systemschrift prüfen.")
    keys = [k for k in (report.get("keys") or []) if isinstance(k, dict)]
    missed = [str(k.get("label")) for k in keys if k.get("missed")]
    pointer = _dict(report.get("pointer"))
    remote = "keys"
    if keys and len(missed) == len(keys):
        if (pointer.get("moves") or 0) > 0 or (pointer.get("clicks") or 0) > 0:
            remote = "cursor"
            notes.append(
                "Cursor-Modus: Die Pfeiltasten bewegen einen Mauszeiger, die Seite bekommt keine "
                "Tasten. Steuerung über Handys und große klickbare Flächen."
            )
        else:
            remote = "none"
            notes.append(
                "Keine Tastenereignisse auf der Seite. Steuerung über Handys; anderer Browser "
                "oder eigene TV-App würde das lösen."
            )
    elif missed:
        remote = "partial"
        notes.append("Nicht erkannte Tasten: " + ", ".join(missed) + ".")
    if not mp4_tested:
        notes.append("MP4 nicht getestet, weil kein Testvideo verfügbar war.")

    if not (es2017 and ws_ok):
        return {
            "code": "C",
            "label": "Streaming-Stick mit Kiosk-Browser: Der TV-Browser kann die Grundlagen nicht.",
            "notes": notes + ["JavaScript (ES2017) oder WebSocket fehlt."],
            "remote": remote,
        }
    failures = []
    if mp4_tested and not mp4_ok:
        failures.append("MP4-Wiedergabe")
    if hls_js_tested and not (hls_native_ok or hls_js_ok):
        failures.append("HLS-Livestream (weder nativ noch über hls.js)")
    elif not (hls_native_ok or mse):
        failures.append("HLS (weder nativ noch über MediaSource)")
    if not yt_ok:
        failures.append("YouTube-Einbettung")
    if failures:
        return {
            "code": "B",
            "label": (
                "Paketierte TV-Web-App prüfen (Tizen/webOS Developer Mode), sonst Streaming-Stick."
            ),
            "notes": notes + ["Fehlgeschlagen: " + ", ".join(failures) + "."],
            "remote": remote,
        }
    if fps < 30:
        return {
            "code": "A-",
            "label": "TV-Browser genügt, aber schwache Grafik: Animationen minimal halten.",
            "notes": notes + [f"Gemessen: {fps:.0f} Bilder/s."],
            "remote": remote,
        }
    label = "TV-Browser genügt." if mp4_tested else "TV-Browser genügt voraussichtlich (MP4 offen)."
    return {"code": "A", "label": label, "notes": notes, "remote": remote}


@router.get("/media")
async def media(request: Request) -> dict[str, Any]:
    result = await media_for_check()
    result["youtube_id"] = request.app.state.settings.youtube_test_id
    return result


async def _read_json_body(request: Request) -> dict[str, Any]:
    raw = await request.body()
    if len(raw) > MAX_REPORT_BYTES:
        raise HTTPException(status_code=413, detail="Bericht zu groß.")
    try:
        data = json.loads(raw or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Ungültiges JSON.") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail="Objekt erwartet.")
    return data


@router.post("")
async def submit_report(request: Request) -> dict[str, Any]:
    report = await _read_json_body(request)
    verdict = compute_verdict(report)
    with request.app.state.db.session() as s:
        row = TvCheckReport(
            user_agent=str(report.get("ua", ""))[:400],
            report_json=json.dumps(report, ensure_ascii=False),
            verdict_code=verdict["code"],
            verdict_json=json.dumps(verdict, ensure_ascii=False),
        )
        s.add(row)
        s.commit()
        return {"id": row.id, "verdict": verdict}


@router.post("/{report_id}/keys")
async def submit_keys(report_id: int, request: Request) -> dict[str, Any]:
    body = await _read_json_body(request)
    keys = body.get("keys")
    if not isinstance(keys, list):
        raise HTTPException(status_code=422, detail="keys muss eine Liste sein.")
    with request.app.state.db.session() as s:
        row = s.get(TvCheckReport, report_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Bericht nicht gefunden.")
        report = json.loads(row.report_json)
        report["keys"] = keys[:20]
        if isinstance(body.get("pointer"), dict):
            report["pointer"] = body["pointer"]
        verdict = compute_verdict(report)
        row.report_json = json.dumps(report, ensure_ascii=False)
        row.verdict_code = verdict["code"]
        row.verdict_json = json.dumps(verdict, ensure_ascii=False)
        s.commit()
        return {"id": row.id, "verdict": verdict}


@router.get("")
def list_reports(request: Request, _admin: Identity = Depends(require_admin)) -> dict[str, Any]:
    with request.app.state.db.session() as s:
        rows = s.scalars(select(TvCheckReport).order_by(TvCheckReport.id.desc()).limit(20)).all()
        return {
            "reports": [
                {
                    "id": r.id,
                    "created_at": r.created_at.isoformat(),
                    "user_agent": r.user_agent,
                    "verdict": json.loads(r.verdict_json),
                    "report": json.loads(r.report_json),
                }
                for r in rows
            ]
        }
