"""Quellenkatalog (catalog/*.yaml) und Auswahl des Haushalts (config/feeds.yaml)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from abendausgabe.core.config import load_yaml

log = logging.getLogger(__name__)

KINDS = {"rss", "bluesky", "youtube"}


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    kind: str
    url: str
    country: tuple[str, ...]
    language: str
    feed: str = ""
    actor: str = ""
    channel_id: str = ""
    group: str = ""  # Katalogdatei, z. B. balkan
    topics: tuple[str, ...] = field(default_factory=tuple)

    @property
    def home_country(self) -> str:
        """Herkunftsland fürs Länderraten; leer bei weltweit berichtenden Medien."""
        return self.country[0] if len(self.country) == 1 else ""


def _source(raw: dict[str, Any], group: str) -> Source:
    kind = str(raw.get("kind", "rss"))
    if kind not in KINDS:
        raise ValueError(f"Quelle {raw.get('id')!r}: kind {kind!r} unbekannt.")
    source = Source(
        id=str(raw["id"]),
        name=str(raw["name"]),
        kind=kind,
        url=str(raw.get("url", "")),
        country=tuple(str(c).upper() for c in raw.get("country") or []),
        language=str(raw.get("language", "")),
        feed=str(raw.get("feed", "")),
        actor=str(raw.get("actor", "")),
        channel_id=str(raw.get("channel_id", "")),
        group=group,
        topics=tuple(str(t) for t in raw.get("topics") or []),
    )
    needed = {"rss": source.feed, "bluesky": source.actor, "youtube": source.channel_id}[kind]
    if not needed:
        raise ValueError(f"Quelle {source.id!r}: Feed bzw. Konto fehlt.")
    if kind == "rss" and not needed.startswith("https://"):
        raise ValueError(f"Quelle {source.id!r}: Feed muss mit https:// beginnen.")
    return source


def load_catalog(catalog_dir: Path) -> list[Source]:
    sources: list[Source] = []
    seen: set[str] = set()
    for path in sorted(catalog_dir.glob("*.yaml")):
        entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        for raw in entries:
            source = _source(raw, path.stem)
            if source.id in seen:
                raise ValueError(f"Quelle {source.id!r} doppelt im Katalog ({path.name}).")
            seen.add(source.id)
            sources.append(source)
    return sources


def selected_sources(catalog_dir: Path) -> list[Source]:
    """Katalog gefiltert nach config/feeds.yaml, plus eigene Quellen unter `extra`."""
    catalog = load_catalog(catalog_dir) if catalog_dir.is_dir() else []
    try:
        choice = load_yaml("feeds.yaml") or {}
    except FileNotFoundError:
        choice = {}
    wanted = choice.get("sources", "alle")
    exclude = {str(x) for x in choice.get("exclude") or []}
    if wanted in ("alle", "all", None):
        picked = list(catalog)
    else:
        names = {str(x) for x in wanted}
        picked = [s for s in catalog if s.id in names or s.group in names]
    picked += [_source(raw, "eigene") for raw in choice.get("extra") or []]
    return [s for s in picked if s.id not in exclude and s.group not in exclude]
