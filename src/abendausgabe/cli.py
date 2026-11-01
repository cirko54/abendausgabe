"""Kommandozeile: abend init | serve | redaktion | reset-pin <person> | backup <ziel>."""

from __future__ import annotations

import argparse
import os
import sys


def _reset_pin(person_id: str) -> int:
    from sqlalchemy import delete

    from abendausgabe.core.config import get_people, get_settings
    from abendausgabe.core.db import Database
    from abendausgabe.core.models import Device, PersonClaim

    if get_people().get(person_id) is None:
        print(f"Unbekannte Person: {person_id}", file=sys.stderr)
        return 1
    settings = get_settings()
    db = Database(f"sqlite:///{settings.data_dir / 'abendausgabe.sqlite3'}")
    with db.session() as s:
        s.execute(delete(PersonClaim).where(PersonClaim.person_id == person_id))
        s.execute(delete(Device).where(Device.person_id == person_id))
        s.commit()
    print(
        f"PIN und Geräte von {person_id} gelöscht. Bei der nächsten Anmeldung neue PIN festlegen."
    )
    return 0


def _init(people_args: list[str], force: bool) -> int:
    from abendausgabe.core.config import get_settings
    from abendausgabe.core.init_config import PersonSpec, init_config, parse_person

    settings = get_settings()
    try:
        if people_args:
            persons = [parse_person(a) for a in people_args]
        else:
            print("Wer gehört zum Haushalt? Ein Name pro Zeile, leere Zeile beendet.")
            print("Admins verwalten Regeln und Quellen. Rolle anhängen, z. B. Alex:admin")
            persons = []
            while line := input("> ").strip():
                persons.append(parse_person(line))
            if persons and not any(p.role == "admin" for p in persons):
                first = persons[0]
                persons[0] = PersonSpec(first.name, "admin")
                print(f"{first.name} wird Admin (mindestens eine Person braucht die Rolle).")
        print(f"Schreibe nach {settings.config_dir}:")
        init_config(settings.config_dir, settings.example_config_dir, persons, force=force)
    except (ValueError, FileExistsError) as exc:
        print(exc, file=sys.stderr)
        return 1
    print("Fertig. Server neu starten, dann gilt die neue Konfiguration.")
    return 0


def _backup(dest: str) -> int:
    from pathlib import Path

    from abendausgabe.core.config import get_settings
    from abendausgabe.core.db import backup_sqlite

    source = get_settings().data_dir / "abendausgabe.sqlite3"
    try:
        backup_sqlite(source, Path(dest))
    except FileNotFoundError as exc:
        print(f"{exc}. Erst den Server einmal starten, dann erneut versuchen.", file=sys.stderr)
        return 1
    print(f"Backup geschrieben: {dest}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="abend", description="Abendausgabe")
    sub = parser.add_subparsers(dest="cmd", required=True)

    init = sub.add_parser("init", help="Haushaltskonfiguration anlegen")
    init.add_argument(
        "--person",
        action="append",
        default=[],
        metavar="NAME[:admin]",
        help="Person anlegen; mehrfach angeben. Ohne Angabe wird gefragt.",
    )
    init.add_argument("--force", action="store_true", help="vorhandene people.yaml überschreiben")

    serve = sub.add_parser("serve", help="Server starten")
    serve.add_argument("--host", default=os.environ.get("ABEND_HOST", "0.0.0.0"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("ABEND_PORT", "8470")))
    serve.add_argument("--reload", action="store_true")

    redaktion = sub.add_parser("redaktion", help="Redaktionslauf (ab Phase 1)")
    redaktion.add_argument("--date", default="today")

    reset = sub.add_parser("reset-pin", help="Vergessene PIN zurücksetzen")
    reset.add_argument("person_id")

    backup = sub.add_parser("backup", help="Konsistente Kopie der Datenbank schreiben")
    backup.add_argument("dest", help="Zieldatei, z. B. /data/backup/latest.sqlite3")

    args = parser.parse_args(argv)
    if args.cmd == "init":
        return _init(args.person, args.force)
    if args.cmd == "serve":
        import uvicorn

        uvicorn.run(
            "abendausgabe.app:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return 0
    if args.cmd == "redaktion":
        from abendausgabe.redaktion.main import run

        return run(args.date)
    if args.cmd == "reset-pin":
        return _reset_pin(args.person_id)
    if args.cmd == "backup":
        return _backup(args.dest)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
