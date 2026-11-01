"""Konfiguration für fremde Haushalte: Beispiel-Fallback, abend init, Modul-Plugins."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from abendausgabe.cli import main
from abendausgabe.core import config
from abendausgabe.core.init_config import parse_person, people_yaml, slugify

EXAMPLE = config.PROJECT_ROOT / "config.example"


@pytest.fixture
def empty_household(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "config"
    monkeypatch.setenv("ABEND_CONFIG_DIR", str(target))
    monkeypatch.setenv("ABEND_EXAMPLE_CONFIG_DIR", str(EXAMPLE))
    config.clear_caches()
    yield target
    config.clear_caches()


def test_missing_config_falls_back_to_example(empty_household: Path) -> None:
    assert config.using_example_people()
    assert set(config.get_people().persons) == {"alex", "sam", "kim", "robin"}


def test_init_writes_people_and_copies_examples(empty_household: Path) -> None:
    assert main(["init", "--person", "Zoë:admin", "--person", "Jürgen"]) == 0
    raw = yaml.safe_load((empty_household / "people.yaml").read_text(encoding="utf-8"))
    assert [p["id"] for p in raw["people"]] == ["zoe", "jurgen"]
    assert [p["role"] for p in raw["people"]] == ["admin", "member"]
    assert (empty_household / "rules.yaml").exists()
    config.clear_caches()
    assert not config.using_example_people()
    assert config.get_people().get("zoe") is not None
    # zweiter Aufruf überschreibt nicht
    assert main(["init", "--person", "X:admin"]) == 1


def test_people_yaml_validation() -> None:
    with pytest.raises(ValueError, match="admin"):
        people_yaml([parse_person("Kim")])
    with pytest.raises(ValueError, match="dieselbe ID"):
        people_yaml([parse_person("Ana:admin"), parse_person("Aña")])
    with pytest.raises(ValueError, match="Rolle"):
        parse_person("Kim:chef")
    assert slugify("Gast") == "p-gast"


def test_plugin_modules_register_without_overriding_builtins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import abendausgabe.modules as modules

    fake = [
        SimpleNamespace(name="hackernews", value="hn_plugin.module"),
        SimpleNamespace(name="tagesschau", value="evil.override"),
        SimpleNamespace(name="Bad-Name", value="x"),
    ]
    monkeypatch.setattr(modules, "entry_points", lambda group: fake)
    registry = modules.load_registry()
    assert registry["hackernews"] == "hn_plugin.module"
    assert registry["tagesschau"] == "abendausgabe.modules.tagesschau"
    assert "Bad-Name" not in registry
