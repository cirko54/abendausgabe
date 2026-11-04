"""Redaktion für den Weltblick: Schlagzeilen übersetzen (decisions.md Nr. 63).

Läuft auf dem Mac. Die Faktenprüfung (SPEC §3) ist hier eine Zahlenprüfung: Jede
Ziffernfolge der Übersetzung muss im Original stehen, sonst wird die Übersetzung
verworfen und die Sendung zeigt die Originalschlagzeile.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass

from abendausgabe.modules.weltblick.translations import MAX_TEXT, Pending
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
