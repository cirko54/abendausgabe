"""Wo spielt eine Meldung, ohne LLM (decisions.md Nr. 65).

Rückfall auf dem Server, wenn die Redaktion auf dem Mac nicht lief: Ortsnamen aus
Natural Earth (gemeinfrei) werden in der Schlagzeile gesucht, in jeder Schrift, die der
Datensatz kennt. Eine Antwort gibt es nur, wenn alle gefundenen Orte und Ländernamen in
genau ein Land fallen; sonst lieber keine Frage.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).with_name("data") / "places.json"
_SPLIT = re.compile(r"[\s.,:;!?\"'“”„‘’`()\[\]{}«»‹›،؛؟۔|/\\–—\-]+")
MAX_WORDS = 4


@dataclass(frozen=True)
class Found:
    country: str
    place: str
    lat: float | None
    lon: float | None


@dataclass(frozen=True)
class Gazetteer:
    places: dict[str, tuple[str, float, float]]
    country_names: dict[str, str]  # Name → ISO-Code
    names_by_country: dict[str, tuple[str, ...]]

    def _matches(self, text: str) -> list[tuple[str, str]]:
        """(Name, Land) für jeden gefundenen Orts- oder Ländernamen, längste zuerst."""
        words = [w for w in _SPLIT.split(text) if w]
        found: list[tuple[str, str]] = []
        used: set[int] = set()
        for n in range(MAX_WORDS, 0, -1):
            for i in range(len(words) - n + 1):
                if used & set(range(i, i + n)):
                    continue
                gram = " ".join(words[i : i + n])
                code = self.country_names.get(gram) or (self.places.get(gram) or ("",))[0]
                if code:
                    found.append((gram, code))
                    used |= set(range(i, i + n))
        return found

    def locate(self, text: str) -> Found | None:
        found = self._matches(text)
        countries = {code for _, code in found}
        if len(countries) != 1:
            return None
        cities = [name for name, _ in found if name in self.places]
        country = countries.pop()
        if not cities:
            return Found(country, found[0][0], None, None)
        name = cities[0]
        _, lat, lon = self.places[name]
        return Found(country, name, lat, lon)

    def names_country(self, text: str, country: str) -> bool:
        """Steht das Land (oder ein Wort davon abgeleitet) schon im Text?"""
        lowered = text.lower()
        for name in self.names_by_country.get(country, ()):
            low = name.lower()
            stem = low[:4] if name.isascii() and len(low) >= 5 else low
            if stem in lowered:
                return True
        return False


def _key(name: str) -> str:
    """Wie der Text zerlegt wird: „St. Petersburg“ → „St Petersburg“, „Ijebu-Ode“ → „Ijebu Ode“."""
    return " ".join(w for w in _SPLIT.split(name) if w)


@lru_cache(maxsize=1)
def load(path: Path = DATA) -> Gazetteer:
    data = json.loads(path.read_text(encoding="utf-8"))
    countries: dict[str, list[str]] = data["countries"]
    return Gazetteer(
        places={_key(name): (v[0], v[1], v[2]) for name, v in data["places"].items()},
        country_names={_key(n): code for code, names in countries.items() for n in names},
        names_by_country={code: tuple(names) for code, names in countries.items()},
    )
