"""Ortsverzeichnis für den Weltblick ohne LLM bauen (decisions.md Nr. 65).

Quelle: Natural Earth 1:10m, „populated places“, „admin 0 countries“ und „admin 1 states
provinces“ (gemeinfrei), https://github.com/nvkelso/natural-earth-vector (Ordner geojson/).
Aufruf:

    uv run python scripts/build_places.py ne_10m_populated_places.geojson \
        ne_10m_admin_0_countries.geojson ne_10m_admin_1_states_provinces.geojson \
        src/abendausgabe/modules/weltblick/data/places.json

Ergebnis: je Name genau ein Land. Namen, die in mehreren Ländern vorkommen, fehlen. Kleine
Orte fehlen auch: Ihre Namen sind zu oft gewöhnliche Wörter (Urdu „گیا“, „ging“, ist auch
die Stadt Gaya) oder Personennamen.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from collections import defaultdict
from typing import Any

from abendausgabe.modules.weltblick.gazetteer import _key

FIELDS = [
    "NAME", "NAMEASCII", "NAME_EN", "NAME_DE", "NAME_HI", "NAME_UR", "NAME_BN", "NAME_RU",
    "NAME_UK", "NAME_AR", "NAME_FA", "NAME_ES", "NAME_FR", "NAME_PT", "NAME_TR",
]  # fmt: skip
COUNTRY_FIELDS = [*FIELDS, "NAME_LONG", "NAME_SORT", "NAME_CIAWF", "NAME_ALT", "FORMAL_EN"]
# Ortsnamen, die zugleich häufige Wörter oder Personennamen sind
STOP = {
    "Of", "Nice", "Split", "Mobile", "Reading", "Bath", "Hope", "Victoria", "Florence",
    "Jackson", "Lincoln", "Houston", "Austin", "Charlotte", "Madison", "Columbus", "Douglas",
    "Hamilton", "Eugene", "Lafayette", "Kingston", "Independence", "Concord", "Liberty",
    "Union", "Mercedes", "Lima", "Bar", "Ar", "Sale", "Most", "Bor", "Pula", "Tours",
    "Troy", "Orange", "Ontario", "Paris", "Santiago", "Cooper", "Price", "Nelson", "Marion",
    "Cleveland", "Jefferson", "Washington", "Trump", "Vance", "Georgia", "David",
    "Vladimir", "Duma", "Sabha", "Marka", "Sagar", "Alta", "Progress", "Brandon",
    "Jordan", "Chad", "Sharif", "Imran", "Ali", "Khan", "Modi", "Singh", "Kumar", "Lok Sabha",
    "Rajya Sabha", "Congress", "Kongres", "Senate", "Senat", "Delta", "Central", "Northern",
    "Southern", "Eastern", "Western", "North", "South", "East", "West", "Capital", "Federal",
    "Christmas", "Petersburg", "Bethlehem", "Nazareth", "Victory", "Unity", "Peace", "Hindi",
    "Urdu",
}  # fmt: skip
CITY_POP = 50_000  # lateinische Schrift
CITY_POP_OTHER = 100_000  # andere Schriften, dazu mindestens 5 Zeichen
CITY_POP_ANY = 1_000_000
MIN_LEN = 4
# Kürzel und gängige Kurzformen, die Natural Earth nicht als Namen führt
ALIASES = {
    "US": ["US", "USA", "U.S.", "U.S.A."], "GB": ["UK", "U.K.", "Britain", "Britannien"],
    "AE": ["UAE", "VAE"], "CD": ["DRC", "DR Kongo"], "KR": ["Südkorea"], "KP": ["Nordkorea"],
}  # fmt: skip


def _read(path: str) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def iso2(props: dict[str, object]) -> str:
    for key in ("ISO_A2", "ISO_A2_EH"):
        value = str(props.get(key) or "")
        if len(value) == 2 and value.isalpha():
            return value.upper()
    return ""


def latin(name: str) -> bool:
    return all(not c.isalpha() or "LATIN" in unicodedata.name(c, "") for c in name)


def variants(name: str) -> set[str]:
    """Wie gazetteer.py den Text zerlegt; „Saint“ und „St“ gelten als gleich."""
    key = _key(name)
    out = {key}
    for long, short in (("Saint ", "St "), ("Sainte ", "Ste "), ("Fort ", "Ft ")):
        if key.startswith(long):
            out.add(short + key[len(long) :])
        if key.startswith(short):
            out.add(long + key[len(short) :])
    return out


def names(props: dict[str, object], fields: list[str]) -> set[str]:
    out = set()
    for field in fields:
        for key in (field, field.lower()):
            for part in str(props.get(key) or "").split("|"):
                part = part.strip()
                # „Niš“: kurze Namen nur mit Sonderzeichen, sonst sind es oft gewöhnliche Wörter
                long_enough = len(part) >= MIN_LEN or (len(part) == 3 and not part.isascii())
                if long_enough and part not in STOP:
                    out |= {v for v in variants(part) if v not in STOP}
    return out


def big_enough(name: str, pop: int) -> bool:
    if latin(name):
        return pop >= CITY_POP
    # „रैली“ (Kundgebung) ist auch Raleigh: andere Schriften erst ab 5 Zeichen
    return len(name) >= 5 and (pop >= CITY_POP_ANY or pop >= CITY_POP_OTHER)


def main(places_path: str, countries_path: str, regions_path: str, out_path: str) -> None:
    owners: dict[str, set[str]] = defaultdict(set)
    where: dict[str, tuple[float, float, int]] = {}
    countries: dict[str, list[str]] = defaultdict(list)
    for feature in _read(countries_path)["features"]:
        props = feature["properties"]
        code = iso2(props)
        if code:
            countries[code] = sorted(names(props, COUNTRY_FIELDS) | set(countries[code]))
    for code, extra in ALIASES.items():
        countries[code] = sorted(set(countries[code]) | set(extra))
    country_names = {n: c for c, ns in countries.items() for n in ns}
    for feature in _read(regions_path)["features"]:
        props = feature["properties"]
        code = iso2(props)
        if not code or props.get("latitude") is None:
            continue
        for name in names(props, [*FIELDS, "NAME_LOCAL"]):
            if name in country_names or (not latin(name) and len(name) < 5):
                continue
            owners[name].add(code)
            where.setdefault(name, (round(float(props["latitude"]), 3),
                                    round(float(props["longitude"]), 3), 0))  # fmt: skip
    for feature in _read(places_path)["features"]:
        props = feature["properties"]
        code = iso2(props)
        if not code:
            continue
        pop = int(props.get("POP_MAX") or 0)
        for name in names(props, FIELDS):
            if name in country_names or not big_enough(name, pop):
                continue  # „Mexico“, „Djibouti“: der Ländername gewinnt
            owners[name].add(code)
            old = where.get(name)
            if old is None or pop > old[2]:
                where[name] = (round(float(props["LATITUDE"]), 3),
                               round(float(props["LONGITUDE"]), 3), pop)  # fmt: skip
    places = {
        name: [next(iter(codes)), where[name][0], where[name][1]]
        for name, codes in sorted(owners.items())
        if len(codes) == 1
    }
    data = {
        "source": "Natural Earth 1:10m populated places + admin 0 countries (public domain)",
        "countries": dict(sorted(countries.items())),
        "places": places,
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(countries)} Länder, {len(places)} Ortsnamen, verworfen (mehrdeutig): "
          f"{sum(1 for c in owners.values() if len(c) > 1)}")  # fmt: skip


if __name__ == "__main__":
    main(*sys.argv[1:5])
