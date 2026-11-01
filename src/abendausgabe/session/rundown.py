"""Laden und Prüfen des Sendeablaufs (Phase 0: config/dummy_rundown.yaml)."""

from __future__ import annotations

from typing import Any

from abendausgabe.core.config import load_yaml

REQUIRED = {
    "info": {"id", "title"},
    "estimate": {"id", "title", "question", "unit", "min", "max", "truth"},
    "choice": {"id", "title", "question", "options", "correct"},
    "video": {"id", "title"},
    "end": {"id", "title"},
}
VIDEO_FORMATS = {"mp4", "hls"}


def validate_rundown(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    for block in blocks:
        kind = block.get("type")
        if kind not in REQUIRED:
            raise ValueError(f"Unbekannter Blocktyp: {kind!r}")
        missing = REQUIRED[kind] - block.keys()
        if missing:
            raise ValueError(f"Block {block.get('id')!r} fehlt: {sorted(missing)}")
        if block["id"] in seen:
            raise ValueError(f"Doppelte Block-ID: {block['id']!r}")
        seen.add(str(block["id"]))
        if kind == "estimate" and not float(block["min"]) <= float(block["truth"]) <= float(
            block["max"]
        ):
            raise ValueError(f"Block {block['id']!r}: truth liegt außerhalb von min/max.")
        if kind == "choice" and not 0 <= int(block["correct"]) < len(block["options"]):
            raise ValueError(f"Block {block['id']!r}: correct verweist auf keine Option.")
        if kind == "video":
            _validate_video(block)
    if not blocks or blocks[-1]["type"] != "end":
        raise ValueError("Der Ablauf muss mit einem end-Block enden (Sendeschluss).")
    return blocks


def _validate_video(block: dict[str, Any]) -> None:
    """Ein Video hat entweder eine feste Quelle (src) oder wird beim Start aufgelöst (media)."""
    has_src = "src" in block
    if has_src == ("media" in block):
        raise ValueError(f"Block {block['id']!r}: genau eines von src oder media angeben.")
    if has_src:
        if not str(block["src"]).startswith("https://"):
            raise ValueError(f"Block {block['id']!r}: src muss mit https:// beginnen.")
        if block.get("format", "mp4") not in VIDEO_FORMATS:
            raise ValueError(f"Block {block['id']!r}: format muss mp4 oder hls sein.")


def load_rundown(name: str = "dummy_rundown.yaml") -> list[dict[str, Any]]:
    raw = load_yaml(name) or {}
    blocks = raw.get("blocks", [])
    if not isinstance(blocks, list):
        raise ValueError("blocks muss eine Liste sein.")
    return validate_rundown(blocks)
