"""SQLite-Datenbank (WAL) über SQLAlchemy 2."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, url: str) -> None:
        self.engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def _set_pragmas(dbapi_conn: Any, _record: Any) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        from abendausgabe.core import models  # noqa: F401  (registriert Tabellen)

        Base.metadata.create_all(self.engine)
        self._sessionmaker = sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> Session:
        return self._sessionmaker()


def backup_sqlite(source: Path, dest: Path) -> None:
    """Konsistente Kopie einer laufenden SQLite-Datenbank (auch im WAL-Modus).

    Schreibt erst in eine temporäre Datei und benennt dann um, damit dest nie halb fertig ist.
    """
    if not source.exists():
        raise FileNotFoundError(f"Keine Datenbank unter {source}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.unlink(missing_ok=True)
    src_conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        dst_conn = sqlite3.connect(tmp)
        try:
            src_conn.backup(dst_conn)
            dst_conn.execute("PRAGMA journal_mode=DELETE")
        finally:
            dst_conn.close()
    finally:
        src_conn.close()
    tmp.replace(dest)
