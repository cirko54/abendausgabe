"""Inhaltsmodule (SPEC §8).

Modulvertrag (CLAUDE.md, CONTRIBUTING.md): Jedes Modul hat
- fetch.py: läuft auf dem Server, nur HTTP, nutzt core.ratelimit, schreibt raw_item
- edit.py: läuft in der Redaktion, LLM-Aufrufe, erzeugt candidate_block
- block.py: Pydantic-Schema für Block, Interaktion, Auflösung, quiz_items

Eingebaute Module stehen in BUILTIN. Fremde Module kommen als eigenes Python-Paket
und melden sich über den Entry-Point-Bereich `abendausgabe.modules` an, z. B. in pyproject.toml:

    [project.entry-points."abendausgabe.modules"]
    mein_modul = "mein_paket.mein_modul"

Ein eingebautes Modul lässt sich so nicht überschreiben; dafür ist ein Fork der Weg.
"""

from __future__ import annotations

import logging
import re
from importlib.metadata import entry_points

log = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "abendausgabe.modules"
_NAME = re.compile(r"^[a-z][a-z0-9_]{1,40}$")

BUILTIN: dict[str, str] = {
    "tagesschau": "abendausgabe.modules.tagesschau",
}


def load_registry() -> dict[str, str]:
    """Modulname → importierbarer Paketpfad, eingebaute zuerst, dann Plugins."""
    registry = dict(BUILTIN)
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        if not _NAME.match(ep.name):
            log.warning("Plugin %r ignoriert: Name nur a-z, 0-9 und _.", ep.name)
            continue
        if ep.name in registry:
            log.warning("Plugin %r ignoriert: Name schon vergeben.", ep.name)
            continue
        registry[ep.name] = ep.value
    return registry


REGISTRY = load_registry()
