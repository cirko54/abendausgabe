# Abendausgabe – Hinweise für Claude Code

Offenes Projekt (AGPL-3.0): ein privater „Sender“ für den eigenen Haushalt, eine endliche, interaktive Abendsendung am Smart-TV, Handys als Controller. Jeder Haushalt betreibt seine eigene Instanz. Maßgeblich ist docs/SPEC.md; Beitragsregeln in CONTRIBUTING.md. Architektur- und Abhängigkeitsentscheidungen kommen in docs/decisions.md (Datum, Entscheidung, Grund, verworfene Alternativen).

## Unverhandelbare Invarianten (SPEC §3)

Änderungen nur nach ausdrücklicher Zustimmung des Nutzers.

- Kein Autoplay, keine Endloslisten; jede Sendung endet mit einem Sendeschluss-Screen.
- Verweildauer und Klickrate sind nie Ranking- oder Assembler-Signal (loggen ist erlaubt).
- Auflösungen und Zusammenfassungen erscheinen erst nach der Eingabe der Runde.
- Programmregeln sind live nicht änderbar; der Joker ist die einzige Ausnahme.
- Keine Abzeichen, Streaks oder Teilnahmepunkte.
- Kein Reddit-Modul (RSS- und API-Ende) und sinngemäß kein Kernmodul für andere geschlossene Plattformen (SPEC §8.13, decisions.md Nr. 31).
- Die Invarianten sind im Kern fest und pro Haushalt nicht abschaltbar (decisions.md Nr. 32).
- Jede Zahl und jedes Zitat aus dem LLM wird gegen den Quelltext geprüft; bei einem Mismatch wird der Block verworfen.
- Die Notausgabe funktioniert ohne Mac und ohne LLM.

## Zielumgebung

Jeder Docker-Host im Heimnetz (amd64 oder arm64). Referenzinstallation, an der die Grenzen unten gemessen sind:

- NAS Synology DS720+: x86-64 (Celeron J4125), Docker über Container Manager, wenig RAM. Schlanke Container, kein Node-Server zur Laufzeit; Frontends werden statisch gebaut und von FastAPI ausgeliefert.
- Mac Mini M4 Pro (arm64, WLAN): Redaktions-Worker per launchd. Das Image baut das NAS selbst (docs/decisions.md Nr. 24); auf dem Mac ist kein Docker installiert.
- Fernseher: eigene Android-TV-App (android/, WebView Chromium 156, Fernbedienung erreicht die Seite). Rückfallebene TV-Browser (Chromium 77, Cursor-Modus). Deshalb weiterhin konservativ:
  - Phase 0 ohne Build-Schritt: Vanilla-JS ES2017, /tv/check.html in ES5
  - falls später ein Build eingeführt wird: `build.target: 'es2017'`, kein Top-Level-Await
  - im TV-Pfad kein WebGL, Animationen nur über transform und opacity
- Zeitzone überall Europe/Berlin.

## Stack

- Python 3.12, uv, FastAPI, Pydantic v2, SQLAlchemy 2 mit SQLite (WAL), APScheduler, httpx, feedparser, skyfield, anthropic-SDK.
- Frontend: in Phase 0 Vanilla-JS ohne Build (docs/decisions.md Nr. 1). Svelte 5 und Vite erst nach dem TV-Test neu bewerten.
  - Controller-Karte (ab Phase 1): MapLibre GL mit lokaler PMTiles-Datei.
  - TV-Karte (ab Phase 1): serverseitig projizierte SVG-Karte (Natural Earth).
- Push: ntfy, Variante ntfy.sh mit zufälligem Topic (docs/decisions.md Nr. 46); Planer als asyncio-Schleife im Server.
- Qualität:
  - pytest; Tests nutzen aufgezeichnete Antworten unter tests/fixtures, keine Live-Calls
  - ruff, mypy (strict für core und session)

## Struktur

```
CLAUDE.md
docs/SPEC.md, docs/decisions.md
config/        people.yaml, rules.yaml, feeds.yaml, profile_schema.yaml (+ *.example)
src/abendausgabe/
  core/        Modelle, DB, Ratelimiter, Sicherheit, Konfiguration
  session/     Ablauflogik (room.py, rein und testbar), WebSocket-Manager, Ablauf laden
  modules/<name>/  fetch.py, edit.py, block.py
  audience/    (Phase 1) Kalender (ICS), Präsenz-Adapter
  assembly/    (Phase 1) Assembler, Regeln, Notausgabe
  learning/    Leitner, Fragenpool, Morgen danach; ab Phase 2 Glicko, Interessenmodell
  api/         HTTP- und WebSocket-Routen, /ext-Routen
  redaktion/   Worker-Einstieg für den Mac
prompts/<module>/<name>.md
web/           tv/ (Bühne, check.html), c/ (Controller), p/ (Profil), admin/, shared/ (Tokens, Schrift)
deploy/        docker-compose.yml, launchd/*.plist, Makefile-Ziele
tests/
```

## Modulvertrag

Ein Modul liegt unter `src/abendausgabe/modules/<name>/`:

- `fetch.py` läuft auf dem NAS: nur HTTP, nutzt den zentralen Ratelimiter, schreibt raw_item.
- `edit.py` läuft in der Redaktion: LLM-Aufrufe, erzeugt candidate_block.
- `block.py` enthält das Pydantic-Schema für Block, Interaktion, Auflösung und quiz_items.
- Dazu Fixtures und Tests.

Eingebaute Module stehen in `BUILTIN` in `modules/__init__.py`; Plugins melden sich über den Entry-Point-Bereich `abendausgabe.modules` an. Ein neues Modul darf keine Änderung am Assembler erfordern.

## LLM-Regeln

- Nur in der Redaktion (`edit.py`), nie im Live-Pfad.
- Prompts als Dateien unter prompts/, versioniert; Ausgabe als JSON mit Pydantic-Validierung.
- Modelle aus .env: heute lokal `ABEND_MODEL_TRANSLATE` über Ollama (decisions.md Nr. 54, 63); für die Claude-API später `ABEND_MODEL_TRIAGE`, `ABEND_MODEL_EDITOR`, die Namen vorher unter docs.claude.com prüfen.
- Cache nach Hash aus Input und Prompt-Version.
- Tagesbudget `ABEND_LLM_BUDGET_EUR` mit hartem Stopp; jeder Aufruf wird in llm_call_log protokolliert.

## Externe Quellen – Grenzen

- Tagesschau höchstens 60 Abrufe pro Stunde.
- Nominatim höchstens 1 Anfrage pro Sekunde, mit eigenem User-Agent und Cache.
- PubMed mit Key höchstens 10 Anfragen pro Sekunde.
- YouTube nur über den offiziellen IFrame-Player, keine Werbeunterdrückung.
- Attributionen sichtbar anzeigen; Volltexte nur mit TTL speichern, Videos nie herunterladen.

## Sicherheit und Privatsphäre

- Haushaltsdaten gehören nie ins Repo: config/, local.mk, android/keystore/ und .env sind ignoriert und liegen im privaten Instanzordner (README: Eigene Instanz). Beispiele, Tests und Prompts nutzen nur den erfundenen Beispielhaushalt aus config.example/.
- Alles ist LAN-only außer /ext/* (Reverse Proxy, HTTPS, Token pro Person, Größen- und Ratelimit).
- Secrets nur in .env; .env ist nie committet, .env.example wird gepflegt.
- Die visibility der Profilantworten wird überall respektiert. Default für Members ist „nur ich“.
- Abgeleitete Interessenvorschläge wirken erst nach Bestätigung durch den Profilinhaber.

## Sprache und Copy

- UI-Texte auf Deutsch; Code, Identifier und Commits auf Englisch.
- UI-Copy kurz, aktiv, ohne Füllwörter.
- Fehlermeldungen sagen, was passiert ist und was zu tun ist.

## Befehle

- `uv run pytest`, `uv run ruff check .`, `uv run mypy src`
- `uv run abend serve` (lokal, Port 8470), `uv run abend redaktion` (auf dem Mac: Übersetzungen über Ollama, decisions.md Nr. 63; `make install-redaktion` für launchd)
- `uv run abend reset-pin <person>`, `uv run abend backup <zieldatei>` (konsistente SQLite-Kopie)
- `uv run abend init` legt config/people.yaml an; ohne config/ gilt der Beispielhaushalt aus config.example/.
- `make deploy-nas`: Quelltext per tar aufs NAS (Host aus local.mk), dort per sudo deploy/nas/up.sh: Image bauen, `compose up -d`. Auf Synology braucht Docker sudo mit Passwort, also läuft dieser Schritt nur im Terminal des Nutzers.
- `make upload-nas` (ohne sudo), `make logs-nas`, einmalig `make migrate-db-nas`

## Arbeitsweise

- Phase 0 ist abgenommen (docs/decisions.md Nr. 21). Phase 1 läuft nach dem Plan in docs/decisions.md Nr. 23 und Nr. 35; Schritt 1 (NAS) ab Nr. 24, Öffnung ab Nr. 29.
- Vor jeder Phase einen kurzen Plan in docs/decisions.md schreiben. Nach jeder Phase die Abnahmekriterien prüfen und das Ergebnis dokumentieren.
- Neue Abhängigkeiten nur mit Begründung in docs/decisions.md.
- Bei Unklarheit eine sinnvolle Annahme treffen, in docs/decisions.md markieren und weiterarbeiten. Nachfragen nur, wenn eine Invariante, Kosten oder Sicherheit betroffen sind.
