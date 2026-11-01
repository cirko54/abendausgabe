"""Redaktionslauf auf dem Mac (SPEC §11.1). Wird in Phase 1 implementiert.

Geplanter Ablauf: Rohdaten per API vom NAS holen, je Modul edit.py ausführen
(LLM, Faktenprüfung, Budget), Kandidatenblöcke zurückschreiben.
"""

from __future__ import annotations


def run(date: str) -> int:
    print(f"Redaktion für {date}: in Phase 0 noch nicht implementiert (siehe SPEC §14).")
    return 0
