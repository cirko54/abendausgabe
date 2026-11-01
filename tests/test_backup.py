from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from abendausgabe.cli import main
from abendausgabe.core.config import clear_caches
from abendausgabe.core.db import Database, backup_sqlite


def test_backup_copies_uncheckpointed_wal(tmp_path: Path) -> None:
    source = tmp_path / "live.sqlite3"
    db = Database(f"sqlite:///{source}")
    # Offene Verbindung mit Daten, die noch im WAL liegen (kein Checkpoint)
    live = sqlite3.connect(source)
    live.execute("PRAGMA wal_autocheckpoint=0")
    live.execute("CREATE TABLE t (x INTEGER)")
    live.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(100)])
    live.commit()
    assert (tmp_path / "live.sqlite3-wal").stat().st_size > 0

    dest = tmp_path / "out" / "backup.sqlite3"
    backup_sqlite(source, dest)
    live.close()
    db.engine.dispose()

    copy = sqlite3.connect(dest)
    assert copy.execute("SELECT count(*) FROM t").fetchone() == (100,)
    assert copy.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    copy.close()
    assert not (tmp_path / "out" / "backup.sqlite3.tmp").exists()


def test_backup_cli_missing_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ABEND_DATA_DIR", str(tmp_path / "leer"))
    clear_caches()
    try:
        assert main(["backup", str(tmp_path / "x.sqlite3")]) == 1
    finally:
        clear_caches()
