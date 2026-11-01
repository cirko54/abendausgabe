"""Einstellungen aus Umgebungsvariablen und YAML-Konfiguration."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]

log = logging.getLogger(__name__)


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value) if value else default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "ja"}


@dataclass(frozen=True)
class Settings:
    config_dir: Path
    example_config_dir: Path
    data_dir: Path
    web_dir: Path
    ask_timeout_s: float
    youtube_test_id: str
    cookie_secure: bool


@lru_cache
def get_settings() -> Settings:
    return Settings(
        config_dir=_env_path("ABEND_CONFIG_DIR", PROJECT_ROOT / "config"),
        example_config_dir=_env_path("ABEND_EXAMPLE_CONFIG_DIR", PROJECT_ROOT / "config.example"),
        data_dir=_env_path("ABEND_DATA_DIR", PROJECT_ROOT / "data"),
        web_dir=_env_path("ABEND_WEB_DIR", PROJECT_ROOT / "web"),
        ask_timeout_s=float(os.environ.get("ABEND_ASK_TIMEOUT_S", "45")),
        youtube_test_id=os.environ.get("ABEND_YOUTUBE_TEST_ID", "jNQXAC9IVRw"),
        cookie_secure=_env_bool("ABEND_COOKIE_SECURE", False),
    )


def config_path(name: str) -> Path:
    """Datei aus dem Haushaltsordner; fehlt sie, die Beispieldatei aus config.example.

    So startet eine frische Installation ohne Konfiguration als Demo-Haushalt.
    """
    settings = get_settings()
    path = settings.config_dir / name
    if path.exists():
        return path
    example = settings.example_config_dir / name
    if example.exists():
        _warn_example(name, settings.config_dir)
        return example
    raise FileNotFoundError(
        f"{name} fehlt in {settings.config_dir} und in {settings.example_config_dir}. "
        "Mit `abend init` eine Konfiguration anlegen."
    )


@lru_cache
def _warn_example(name: str, config_dir: Path) -> None:
    log.warning("%s fehlt in %s; nutze die Beispieldatei (`abend init`).", name, config_dir)


def using_example_people() -> bool:
    return not (get_settings().config_dir / "people.yaml").exists()


def load_yaml(name: str) -> Any:
    path = config_path(name)
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@dataclass(frozen=True)
class Person:
    id: str
    name: str
    role: str
    color: str


@dataclass(frozen=True)
class People:
    persons: dict[str, Person]
    guest_color: str

    def get(self, person_id: str) -> Person | None:
        return self.persons.get(person_id)


VALID_ROLES = {"admin", "member"}


@lru_cache
def get_people() -> People:
    raw = load_yaml("people.yaml") or {}
    persons: dict[str, Person] = {}
    for entry in raw.get("people", []):
        person = Person(
            id=str(entry["id"]),
            name=str(entry["name"]),
            role=str(entry.get("role", "member")),
            color=str(entry.get("color", "#9FB0C2")),
        )
        if person.role not in VALID_ROLES:
            raise ValueError(f"Unbekannte Rolle für {person.id}: {person.role}")
        if person.id.startswith("gast"):
            raise ValueError("Personen-IDs dürfen nicht mit 'gast' beginnen.")
        persons[person.id] = person
    return People(persons=persons, guest_color=str(raw.get("guest_color", "#F0E442")))


def clear_caches() -> None:
    get_settings.cache_clear()
    get_people.cache_clear()
    _warn_example.cache_clear()
