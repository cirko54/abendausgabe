"""`abend init`: legt die Haushaltskonfiguration aus config.example an."""

from __future__ import annotations

import re
import shutil
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

# Okabe-Ito, sicher bei Farbsehschwäche; Gelb ist für Gäste reserviert
PERSON_COLORS = ["#E69F00", "#56B4E9", "#009E73", "#CC79A7", "#D55E00", "#0072B2"]
GUEST_COLOR = "#F0E442"


@dataclass(frozen=True)
class PersonSpec:
    name: str
    role: str  # admin | member


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    if not slug:
        raise ValueError(f"Aus „{name}“ lässt sich keine ID bilden; bitte lateinische Buchstaben.")
    if slug.startswith("gast"):
        slug = "p-" + slug
    return slug


def parse_person(arg: str) -> PersonSpec:
    """„Name“ oder „Name:admin“ bzw. „Name:member“."""
    name, _, role = arg.partition(":")
    role = role.strip().lower() or "member"
    if role not in {"admin", "member"}:
        raise ValueError(f"Rolle „{role}“ unbekannt; erlaubt sind admin und member.")
    if not name.strip():
        raise ValueError("Name fehlt.")
    return PersonSpec(name=name.strip(), role=role)


def people_yaml(persons: list[PersonSpec]) -> str:
    if not persons:
        raise ValueError("Mindestens eine Person angeben.")
    if not any(p.role == "admin" for p in persons):
        raise ValueError("Mindestens eine Person braucht die Rolle admin.")
    if len(persons) > len(PERSON_COLORS):
        raise ValueError(f"Höchstens {len(PERSON_COLORS)} Personen; Gäste brauchen kein Profil.")
    entries = []
    seen: set[str] = set()
    for spec, color in zip(persons, PERSON_COLORS, strict=False):
        pid = slugify(spec.name)
        if pid in seen:
            raise ValueError(f"Zwei Personen ergeben dieselbe ID „{pid}“; Namen unterscheiden.")
        seen.add(pid)
        entries.append({"id": pid, "name": spec.name, "role": spec.role, "color": color})
    header = (
        "# Personen des Haushalts (angelegt mit `abend init`).\n"
        "# Rollen: admin (Programmregeln, Quellen, Personen) | member (eigenes Profil, Wünsche)\n"
    )
    body = yaml.safe_dump(
        {"people": entries, "guest_color": GUEST_COLOR}, allow_unicode=True, sort_keys=False
    )
    return header + body


def init_config(
    target: Path,
    example_dir: Path,
    persons: list[PersonSpec],
    force: bool = False,
    out: Callable[[str], None] = print,
) -> None:
    people_file = target / "people.yaml"
    if people_file.exists() and not force:
        raise FileExistsError(f"{people_file} gibt es schon; mit --force überschreiben.")
    content = people_yaml(persons)
    target.mkdir(parents=True, exist_ok=True)
    for example in sorted(example_dir.glob("*.yaml")):
        if example.name == "people.yaml":
            continue
        dest = target / example.name
        if not dest.exists():
            shutil.copyfile(example, dest)
            out(f"  {dest} (aus Beispiel)")
    people_file.write_text(content, encoding="utf-8")
    out(f"  {people_file}")
