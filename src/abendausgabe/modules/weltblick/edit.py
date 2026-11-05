"""Redaktion für den Weltblick: Schlagzeilen übersetzen, Orte bestimmen (Nr. 63, 64).

Läuft auf dem Mac. Die Faktenprüfung (SPEC §3) ist hier eine Zahlenprüfung: Jede
Ziffernfolge der Übersetzung muss im Original stehen, sonst wird die Übersetzung
verworfen und die Sendung zeigt die Originalschlagzeile.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, Field, ValidationError

from abendausgabe.modules.weltblick.geocode import Geocoder
from abendausgabe.modules.weltblick.translations import MAX_TEXT, Pending, PendingPlace, Place
from abendausgabe.redaktion.llm import LLM, Prompt, load_prompt

log = logging.getLogger(__name__)

LANGUAGE_NAMES = {
    "en": "English", "sr": "Serbian", "hi": "Hindi", "ur": "Urdu", "ru": "Russian",
    "uk": "Ukrainian", "es": "Spanish", "pt": "Portuguese", "fr": "French", "ar": "Arabic",
    "fa": "Persian", "ps": "Pashto", "bn": "Bengali", "hr": "Croatian", "bs": "Bosnian",
    "sq": "Albanian", "mk": "Macedonian", "pl": "Polish", "tr": "Turkish", "sw": "Swahili",
    "id": "Indonesian", "ja": "Japanese", "zh": "Chinese", "it": "Italian", "nl": "Dutch",
}  # fmt: skip
_RUN = re.compile(r"\d+")


def prompt() -> Prompt:
    return load_prompt("weltblick", "translate")


def digit_runs(text: str) -> set[str]:
    """Ziffernfolgen, Ziffern jeder Schrift als 0–9 (Devanagari, Arabisch-Indisch …)."""
    ascii_digits = "".join(
        str(unicodedata.decimal(ch)) if unicodedata.decimal(ch, None) is not None else ch
        for ch in text
    )
    return {m.lstrip("0") or "0" for m in _RUN.findall(ascii_digits)}


QUOTES = "\"'„“”«»‚‘’"


def _unwrap(text: str, original: str) -> str:
    """Anführungszeichen um die ganze Übersetzung weg, Zitate darin bleiben."""
    if (
        len(text) > 1
        and text[0] in QUOTES
        and text[-1] in QUOTES
        and original.strip()[:1] not in QUOTES
        and not any(q in text[1:-1] for q in QUOTES)
    ):
        return text[1:-1].strip()
    return text


@dataclass(frozen=True)
class Checked:
    text: str | None
    reason: str = ""


def check(original: str, translation: str) -> Checked:
    text = _unwrap(translation.strip(), original)
    if "\n" in text:
        # Erläuterungen statt nur der Übersetzung: lieber das Original zeigen
        return Checked(None, "mehrzeilig")
    if not text:
        return Checked(None, "leer")
    if len(text) > min(MAX_TEXT, 3 * len(original) + 40):
        return Checked(None, "zu lang")
    extra = digit_runs(text) - digit_runs(original)
    if extra:
        return Checked(None, f"Zahl nicht im Original: {', '.join(sorted(extra))}")
    return Checked(text)


def translate(item: Pending, llm: LLM, template: Prompt) -> str | None:
    """Geprüfte Übersetzung oder None (Sprache unbekannt, Prüfung nicht bestanden)."""
    name = LANGUAGE_NAMES.get(item.language)
    if name is None:
        log.info("Sprache %r unbekannt, %s bleibt im Original.", item.language, item.id)
        return None
    user = template.render(source_lang=name, source_code=item.language, text=item.title)
    raw = llm.complete(template, user)
    result = check(item.title, raw)
    if result.text is None:
        log.info("Übersetzung verworfen (%s): %s → %s", result.reason, item.title, raw)
    return result.text


# ------------------------------------------------------------- Orte (Nr. 64)


class Located(BaseModel):
    place: str = Field(default="", max_length=200)
    country: str = Field(default="", max_length=2)


LOCATE_SCHEMA = Located.model_json_schema()


def locate_prompt() -> Prompt:
    return load_prompt("weltblick", "locate")


def locate(item: PendingPlace, llm: LLM, template: Prompt, geocoder: Geocoder) -> Place | None:
    """Ort und Land, doppelt geprüft; sonst ein leerer Eintrag (zählt als erledigt).

    None: Nominatim nicht erreichbar, beim nächsten Lauf noch einmal.

    1. Der Ort steht wörtlich im deutschen Text, den der Fernseher zeigt.
    2. Nominatim ordnet ihn demselben Land zu wie das Modell.
    """
    empty = Place(item.id, "", "", None, None)
    raw = llm.complete(template, template.render(text=item.text), schema=LOCATE_SCHEMA)
    try:
        found = Located.model_validate(json.loads(raw))
    except (ValueError, ValidationError):
        log.info("Ort: keine gültige Antwort für %s: %s", item.id, raw[:200])
        return empty
    place, country = found.place.strip(), found.country.strip().upper()
    if not place or len(country) != 2:
        return empty
    if place.lower() not in item.text.lower():
        log.info("Ort verworfen (nicht im Text): %s in %s", place, item.text)
        return empty
    try:
        hit = geocoder.lookup(place)
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Nominatim nicht erreichbar (%s), %s später noch einmal.", exc, place)
        return None
    if hit is None or hit.country != country:
        log.info("Ort verworfen (Nominatim: %s, Modell: %s): %s", hit and hit.country, country,
                 place)  # fmt: skip
        return empty
    return Place(item.id, country, place, hit.lat, hit.lon)
