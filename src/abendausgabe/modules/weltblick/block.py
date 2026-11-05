"""Weltblick-Blöcke (decisions.md Nr. 52, 63, 64).

Zwei Raterunden „Wo spielt diese Meldung?“ mit Bild und Schlagzeile, dazu ein Kurzvideo.
Ort und Übersetzung kommen aus der Redaktion; ohne sie findet das Ortsverzeichnis den Ort.
Alles aus der Datenbank, damit der Sendestart nicht wartet.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select

from abendausgabe.core.db import Database
from abendausgabe.core.models import ItemPlace, RawItem, Translation
from abendausgabe.modules.weltblick import gazetteer
from abendausgabe.modules.weltblick.catalog import Source

FRESH = timedelta(hours=36)
ROUNDS = 2

COUNTRY_DE = {
    "AE": "Vereinigte Arabische Emirate", "AF": "Afghanistan", "AL": "Albanien",
    "AM": "Armenien", "AR": "Argentinien", "AT": "Österreich", "AU": "Australien",
    "AZ": "Aserbaidschan", "BA": "Bosnien und Herzegowina", "BD": "Bangladesch",
    "BE": "Belgien", "BG": "Bulgarien", "BO": "Bolivien", "BR": "Brasilien", "BY": "Belarus",
    "CA": "Kanada", "CD": "DR Kongo", "CG": "Kongo", "CH": "Schweiz", "CL": "Chile",
    "CM": "Kamerun", "CN": "China", "CO": "Kolumbien", "CU": "Kuba", "CZ": "Tschechien",
    "DE": "Deutschland", "DK": "Dänemark", "DZ": "Algerien", "EC": "Ecuador", "EG": "Ägypten",
    "ES": "Spanien", "ET": "Äthiopien", "FI": "Finnland", "FR": "Frankreich",
    "GB": "Großbritannien", "GE": "Georgien", "GH": "Ghana", "GR": "Griechenland",
    "HR": "Kroatien", "HU": "Ungarn", "ID": "Indonesien", "IE": "Irland", "IL": "Israel",
    "IN": "Indien", "IQ": "Irak", "IR": "Iran", "IT": "Italien", "JO": "Jordanien",
    "JP": "Japan", "KE": "Kenia", "KP": "Nordkorea", "KR": "Südkorea", "KZ": "Kasachstan",
    "LB": "Libanon", "LK": "Sri Lanka", "LY": "Libyen", "MA": "Marokko", "MD": "Moldau",
    "ME": "Montenegro", "MK": "Nordmazedonien", "ML": "Mali", "MM": "Myanmar", "MX": "Mexiko",
    "MY": "Malaysia", "NE": "Niger", "NG": "Nigeria", "NL": "Niederlande", "NO": "Norwegen",
    "NP": "Nepal", "NZ": "Neuseeland", "PE": "Peru", "PH": "Philippinen", "PK": "Pakistan",
    "PL": "Polen", "PS": "Palästinensische Gebiete", "PT": "Portugal", "PY": "Paraguay",
    "QA": "Katar", "RO": "Rumänien", "RS": "Serbien", "RU": "Russland", "RW": "Ruanda",
    "SA": "Saudi-Arabien", "SD": "Sudan", "SE": "Schweden", "SI": "Slowenien",
    "SK": "Slowakei", "SN": "Senegal", "SO": "Somalia", "SS": "Südsudan", "SY": "Syrien",
    "TD": "Tschad", "TH": "Thailand", "TN": "Tunesien", "TR": "Türkei", "TW": "Taiwan",
    "TZ": "Tansania", "UA": "Ukraine", "UG": "Uganda", "US": "USA", "UY": "Uruguay",
    "VE": "Venezuela", "VN": "Vietnam", "XK": "Kosovo", "YE": "Jemen", "ZA": "Südafrika",
    "ZW": "Simbabwe",
}  # fmt: skip
# Ablenker aus der Nachbarschaft machen das Raten interessanter als Zufallsländer
NEIGHBOURS = {
    "IN": ["PK", "BD", "NP", "LK"], "PK": ["IN", "AF", "IR", "BD"], "AF": ["PK", "IR", "IN"],
    "RS": ["HR", "BA", "MK", "ME", "XK"], "HR": ["RS", "BA", "SI"], "BA": ["RS", "HR", "ME"],
    "UA": ["RU", "PL", "BY", "MD"], "RU": ["UA", "BY", "KZ"], "BY": ["UA", "RU", "PL"],
    "AU": ["NZ", "PH", "ID"], "NZ": ["AU"], "NG": ["GH", "CM", "NE"], "GH": ["NG", "SN"],
    "CG": ["CD", "CM"], "CD": ["CG", "RW", "UG"], "KE": ["TZ", "UG", "ET", "SO"],
    "ET": ["KE", "SO", "SD"], "SD": ["SS", "EG", "TD"], "UY": ["AR", "BR", "PY"],
    "AR": ["UY", "CL", "BR"], "BR": ["AR", "CO", "PE"], "US": ["CA", "MX"], "CA": ["US"],
    "MX": ["US", "CU"], "VE": ["CO", "BR", "CU"], "IL": ["LB", "SY", "JO", "EG"],
    "PS": ["IL", "JO", "EG"], "LB": ["SY", "IL", "JO"], "SY": ["LB", "IQ", "TR"],
    "IR": ["IQ", "AF", "TR"], "IQ": ["IR", "SY", "SA"], "SA": ["YE", "QA", "AE"],
    "YE": ["SA", "SO"], "EG": ["LY", "SD", "IL"], "LY": ["EG", "TN", "DZ", "TD"],
    "CN": ["TW", "JP", "KR"], "TW": ["CN", "JP", "PH"], "JP": ["KR", "CN", "TW"],
    "KR": ["KP", "JP", "CN"], "KP": ["KR", "CN"], "GB": ["IE", "FR"], "FR": ["BE", "ES", "IT"],
    "DE": ["AT", "CH", "PL"], "ES": ["PT", "FR", "IT"], "IT": ["FR", "AT", "SI"],
    "TR": ["GR", "SY", "BG"], "GR": ["TR", "BG", "AL"], "GE": ["AM", "AZ", "RU"],
    "MM": ["TH", "BD", "IN"], "TH": ["MM", "VN", "MY"], "VN": ["TH", "CN"],
    "ID": ["MY", "PH", "AU"], "PH": ["ID", "VN", "TW"], "BD": ["IN", "MM", "NP"],
    "NP": ["IN", "BD"], "LK": ["IN", "BD"], "ZA": ["ZW", "KE"], "SN": ["ML", "GH"],
}  # fmt: skip
# Steht das Land schon in der Schlagzeile, ist die Frage keine (decisions.md Nr. 64)
COUNTRY_HINTS = {
    "US": ("usa", "us-", "amerika", "vereinigte staaten", "washington"),
    "GB": ("brit", "großbritannien", "england", "vereinigtes königreich", "london"),
    "NL": ("niederl", "holl"), "CZ": ("tschech",), "KR": ("südkorea", "korea"),
    "KP": ("nordkorea", "korea"), "PS": ("paläst", "gaza", "westjordan"),
    "AE": ("emirat",), "CD": ("kongo",), "CG": ("kongo",), "SS": ("südsudan", "sudan"),
    "BA": ("bosni",), "MK": ("mazedon",), "XK": ("kosov",), "CH": ("schweiz",),
    "DE": ("deutsch",), "SA": ("saudi",), "ZA": ("südafrika",),
}  # fmt: skip


def _fresh_items(db: Database, now: datetime, today: date) -> list[RawItem]:
    with db.session() as s:
        rows = s.scalars(
            select(RawItem).where(
                RawItem.published_at >= (now - FRESH).astimezone(UTC),
                (RawItem.shown_on.is_(None)) | (RawItem.shown_on == today),
            )
        ).all()
        return list(rows)


def _distractors(country: str, pool: list[str], rng: random.Random) -> list[str]:
    near = [c for c in NEIGHBOURS.get(country, []) if c in COUNTRY_DE and c != country]
    rest = [c for c in pool if c != country and c not in near]
    rng.shuffle(near)
    rng.shuffle(rest)
    return (near + rest)[:2]


def _source_line(item: RawItem, sources: dict[str, Source]) -> str:
    source = sources.get(item.source_id)
    name = source.name if source else item.source_id
    day = item.published_at.replace(tzinfo=item.published_at.tzinfo or UTC)
    return f"{name}, {day.astimezone(UTC).strftime('%d.%m.%Y')}"


def _translations(db: Database, items: list[RawItem]) -> dict[str, str]:
    ids = [i.id for i in items]
    if not ids:
        return {}
    with db.session() as s:
        rows = s.scalars(
            select(Translation).where(
                Translation.raw_item_id.in_(ids), Translation.language == "de"
            )
        ).all()
        return {t.raw_item_id: t.text for t in rows}


@dataclass(frozen=True)
class Where:
    country: str
    place: str
    checked: bool  # von der Redaktion geprüft (Nr. 64), sonst aus dem Ortsverzeichnis (Nr. 65)


def _places(db: Database, items: list[RawItem], translated: dict[str, str]) -> dict[str, Where]:
    """Wo eine Meldung spielt. Was die Redaktion geprüft hat, gilt, auch „kein Ort“."""
    ids = [i.id for i in items]
    if not ids:
        return {}
    with db.session() as s:
        rows = s.scalars(select(ItemPlace).where(ItemPlace.raw_item_id.in_(ids))).all()
        done = {p.raw_item_id: p for p in rows}
    out: dict[str, Where] = {}
    names = gazetteer.load()
    for item in items:
        if item.id in done:
            row = done[item.id]
            if row.country:
                out[item.id] = Where(row.country, row.place, True)
            continue
        found = names.locate(translated.get(item.id, "")) or names.locate(item.title)
        if found is not None:
            out[item.id] = Where(found.country, found.place, False)
    return out


def _caption(item: RawItem, translated: dict[str, str]) -> dict[str, Any]:
    """Übersetzung groß, Original klein darunter; die Schrift bleibt ein Hinweis (Nr. 63)."""
    text = translated.get(item.id)
    if not text or item.language == "de":
        return {"caption": item.title, "caption_lang": item.language}
    return {
        "caption": text,
        "caption_lang": "de",
        "caption_original": item.title,
        "caption_original_lang": item.language,
    }


def _names_country(texts: list[str], country: str) -> bool:
    """Steht das Land schon auf dem Bildschirm, in der Übersetzung oder im Original?"""
    names = gazetteer.load()
    for caption in texts:
        text = caption.lower()
        stem = COUNTRY_DE[country].lower()[:4]
        if stem in text or any(h in text for h in COUNTRY_HINTS.get(country, ())):
            return True
        if names.names_country(caption, country):
            return True
    return False


def _source_with_home(item: RawItem, sources: dict[str, Source]) -> str:
    home = COUNTRY_DE.get(item.country)
    line = _source_line(item, sources)
    return line.replace(", ", f" aus {home}, ", 1) if home else line


def guess_rounds(
    items: list[RawItem],
    sources: dict[str, Source],
    rng: random.Random,
    translated: dict[str, str] | None = None,
    places: dict[str, Where] | None = None,
) -> list[dict[str, Any]]:
    """„Wo spielt diese Meldung?“ (decisions.md Nr. 64).

    Gefragt wird nach dem Land, um das es geht, nicht nach dem Land der Zeitung. Das weiß
    die Redaktion (Nr. 64) oder, ohne Mac, das Ortsverzeichnis (Nr. 65). Findet keins von
    beiden etwas Brauchbares, kommen die Schlagzeilen ohne Frage (headline_cards).
    """
    translated, places = translated or {}, places or {}

    def shown(i: RawItem) -> list[str]:
        return [translated[i.id], i.title] if i.id in translated else [i.title]

    candidates = [
        i for i in items
        if i.image and i.id in places and places[i.id].country in COUNTRY_DE
        and not _names_country(shown(i), places[i.id].country)
    ]  # fmt: skip
    rng.shuffle(candidates)
    # Von der Redaktion geprüfte Orte zuerst, das Ortsverzeichnis nur als Rückfall
    candidates.sort(key=lambda i: not places[i.id].checked)
    pool = sorted({places[i.id].country for i in candidates} | set(NEIGHBOURS))
    # eine Runde aus einer Quelle in fremder Sprache, falls vorhanden; sonst bunt gemischt
    foreign = [i for i in candidates if i.language != "en"]
    ordered = foreign[:1] + [i for i in candidates if i not in foreign[:1]]
    chosen: list[RawItem] = []
    for item in ordered:
        if places[item.id].country not in {places[c.id].country for c in chosen}:
            chosen.append(item)
        if len(chosen) == ROUNDS:
            break
    blocks = []
    for n, item in enumerate(chosen, start=1):
        where = places[item.id]
        options = [where.country, *_distractors(where.country, pool, rng)]
        rng.shuffle(options)
        blocks.append(
            {
                "id": f"weltblick-{n}",
                "type": "choice",
                "title": "Weltblick",
                "question": "Wo spielt diese Meldung?",
                **_caption(item, translated),
                "media": {"kind": "image", "src": item.image},
                "options": [COUNTRY_DE[c] for c in options],
                "correct": options.index(where.country),
                "source": f"{_source_with_home(item, sources)} · Ort: {where.place}",
                "link": item.url,
                "raw_item_id": item.id,
                "timeout_s": 45,
                "est_minutes": 1,
            }
        )
    return blocks


def headline_cards(
    items: list[RawItem],
    sources: dict[str, Source],
    rng: random.Random,
    translated: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Ohne Redaktion: Schlagzeilen mit Bild und Quelle, ohne Frage (Notausgabe)."""
    candidates = [i for i in items if i.image]
    rng.shuffle(candidates)
    foreign = [i for i in candidates if i.language != "en"]
    ordered = foreign[:1] + [i for i in candidates if i not in foreign[:1]]
    chosen: list[RawItem] = []
    for item in ordered:
        if item.source_id not in {c.source_id for c in chosen}:
            chosen.append(item)
        if len(chosen) == ROUNDS:
            break
    return [
        {
            "id": f"weltblick-{n}",
            "type": "info",
            "title": "Weltblick",
            **_caption(item, translated or {}),
            "media": {"kind": "image", "src": item.image},
            "body": "",
            "credit": _source_with_home(item, sources),
            "link": item.url,
            "raw_item_id": item.id,
            "est_minutes": 1,
        }
        for n, item in enumerate(chosen, start=1)
    ]


def video_round(
    items: list[RawItem],
    sources: dict[str, Source],
    rng: random.Random,
    translated: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    videos = [i for i in items if i.video_json]
    if not videos:
        return None
    item = rng.choice(sorted(videos, key=lambda i: i.id))
    video = json.loads(item.video_json or "{}")
    return {
        "id": "weltblick-video",
        "type": "video",
        "title": "Weltblick",
        "src": video["src"],
        "format": "hls",
        "poster": video.get("poster"),
        "vertical": bool(video.get("vertical")),
        "muted": True,  # startet stumm mit Text; ▲ schaltet den Ton ein (Nr. 48)
        **_caption(item, translated or {}),
        "attribution": _source_line(item, sources),
        "link": item.url,
        "raw_item_id": item.id,
        "est_minutes": 1,
    }


def weltblick_blocks(db: Database, sources: list[Source], now: datetime) -> list[dict[str, Any]]:
    """Stabil für denselben Tag: Ein erneutes Zusammenstellen in der Lobby ändert nichts."""
    today = now.date()
    rng = random.Random(today.isoformat())
    by_id = {s.id: s for s in sources}
    items = sorted(_fresh_items(db, now, today), key=lambda i: i.id)
    translated = _translations(db, items)
    blocks = guess_rounds(items, by_id, rng, translated, _places(db, items, translated))
    if not blocks:
        blocks = headline_cards(items, by_id, rng, translated)
    video = video_round(items, by_id, rng, translated)
    if video:
        blocks.append(video)
    return blocks


def mark_shown(db: Database, rundown: list[dict[str, Any]], today: date) -> None:
    """Beim Sendestart: Gezeigtes kommt an späteren Tagen nicht wieder."""
    ids = [str(b["raw_item_id"]) for b in rundown if b.get("raw_item_id")]
    if not ids:
        return
    with db.session() as s:
        for item in s.scalars(select(RawItem).where(RawItem.id.in_(ids))):
            item.shown_on = today
        s.commit()
