# Abendausgabe

Ein privater Sender für den eigenen Haushalt: einmal am Abend eine endliche, interaktive Sendung auf dem Fernseher, die Handys sind die Controller. Statt Endlos-Feed gibt es einen Sendeablauf mit Sendeschluss. Statt zuzuschauen rät, schätzt und tippt die Runde gemeinsam, und die Auflösung kommt erst danach.

Die Idee: gemeinsam vor dem Fernseher sitzen wie früher, mit einer Mischung aus Unterhaltung, Anregung und Miteinander, die jeden Abend anders ist. Sie entsteht aus Tagesaktuellem, den Interessen der Anwesenden, Zufall und dem, was Einzelne mitbringen.

Dabei bedient die Abendausgabe nicht den eigenen Filter, sie erweitert ihn, denn Filterblasen arbeiten gegen den sozialen Kitt. Das geschieht ohne Zwang: Fremde Perspektiven kommen als Rätsel und über Brücken aus den eigenen Interessen, für jeden so dosiert, wie er oder sie es braucht. Gegen die Dopamin-Konkurrenz setzt sie nicht auf mehr Reize, sondern auf gemeinsames Spielen, Neugier und ein klares Ende.

- Konzept, Ziele und Invarianten: [docs/SPEC.md](docs/SPEC.md)
- Entscheidungen mit Begründung: [docs/decisions.md](docs/decisions.md)
- Mitmachen, eigene Quellen und Module: [CONTRIBUTING.md](CONTRIBUTING.md)

Stand: Phase 0 fertig (Gerüst, TV-Fähigkeitstest, Android-TV-App, Beitritt per QR-Code, Testsendung, Profilfragebogen). Phase 1 (die ersten echten Sendungen) läuft. Die Oberfläche ist bisher deutsch.

## Was man braucht

- Einen Rechner im Heimnetz, der abends läuft und Docker kann: NAS, Raspberry Pi 4/5, Mini-PC (amd64 oder arm64).
- Einen Fernseher mit Browser, besser Android TV bzw. Google TV für die eigene App (android/).
- Handys im selben WLAN.
- Ab Phase 1 optional einen API-Schlüssel für ein LLM (Voreinstellung Claude), sonst gibt es die Notausgabe ohne LLM.

## Schnellstart mit Docker

```sh
mkdir abendausgabe && cd abendausgabe
curl -fsSLO https://raw.githubusercontent.com/cirko54/abendausgabe/main/deploy/docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/cirko54/abendausgabe/main/.env.example -o .env
docker compose up -d
```

Dann läuft ein Demo-Haushalt (Alex, Sam, Kim, Robin). Den eigenen Haushalt anlegen und neu starten:

```sh
mkdir -p config
docker compose run --rm --no-deps --user "$(id -u):$(id -g)" \
  -e ABEND_CONFIG_DIR=/out -v "$PWD/config:/out" app abend init
docker compose restart
```

`abend init` fragt nach den Namen; Admins kennzeichnet man mit `:admin` (zum Beispiel `Alex:admin`). Die Dateien landen in `./config` und lassen sich danach von Hand anpassen: `rules.yaml` für Programmregeln, `profile_schema.yaml` für den Fragebogen.

Im Heimnetz:

- Fernseher: `http://<Server-IP>:8470/tv/`, zum ersten Mal besser `http://<Server-IP>:8470/tv/check.html` (prüft in etwa zwei Minuten, was der Fernseher kann).
- Handy: den QR-Code auf dem Fernseher scannen oder `http://<Server-IP>:8470/c/` öffnen. Beim ersten Mal legt jede Person ihre PIN fest.
- Profil: `/p/`, Testberichte für Admins: `/admin/tvcheck.html`.

Dem Server in der Router-Oberfläche eine feste IP geben, sonst findet der Fernseher ihn irgendwann nicht mehr.

## Fernseher

Auf Android TV und Google TV läuft am besten die eigene App aus [android/](android/README.md): eine schlanke WebView-Hülle mit Kachel auf dem Startbildschirm. Die Fernbedienung erreicht damit die Seite. Jeder Haushalt baut die App selbst und signiert sie mit einem eigenen Schlüssel. Der eingebaute TV-Browser funktioniert als Rückfallebene, ist im Alltag aber umständlich.

Fernbedienung im Video: OK hält an, ◀ ▶ spulen, ▲ schaltet den Ton, ▼ geht zum nächsten Beitrag.

Andere Fernseher (Fire TV, Tizen, webOS): bitte `/tv/check.html` laufen lassen und das Ergebnis als Issue melden.

## Eigene Instanz neben dem Repo

Wer am Code arbeitet und zugleich eine eigene Installation betreibt, hält die Haushaltsdaten außerhalb des Repos, zum Beispiel in einem privaten Ordner `../abendausgabe-zuhause`:

```
abendausgabe-zuhause/
  config/          people.yaml, rules.yaml, …   (uv run abend init)
  android/         abendausgabe.jks             (Signaturschlüssel der TV-App)
  local.mk         NAS = mein-nas               (Werte für make)
```

Im Repo dann per Symlink einhängen. `.gitignore` hält `config`, `local.mk` und `android/keystore` heraus:

```sh
ln -s ../abendausgabe-zuhause/config config
ln -s ../abendausgabe-zuhause/local.mk local.mk
ln -s ../../abendausgabe-zuhause/android android/keystore
```

## Entwickeln

Voraussetzung: [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run pytest
uv run abend serve          # Port 8470; ohne config/ als Demo-Haushalt
```

Lint: `uv run ruff check .` und `uv run mypy src`. Die Tests nutzen nur aufgezeichnete Antworten (tests/fixtures), keine Live-Abrufe.

Mit Claude Code: Im Projektordner starten. CLAUDE.md enthält die Arbeitsregeln, docs/SPEC.md das Ziel.

## Auf einem Synology-NAS (Referenzinstallation)

Statt das fertige Image zu ziehen, kann das NAS selbst bauen. Auf dem Entwicklungsrechner ist dann kein Docker nötig (docs/decisions.md Nr. 24).

Einmalig:

1. Container Manager installieren, SSH aktivieren, einen SSH-Host in `~/.ssh/config` anlegen und in `local.mk` eintragen (`NAS = …`).
2. `uv run abend init`, damit `config/people.yaml` existiert.
3. `make deploy-nas`: lädt Quelltext und Konfiguration hoch, baut auf dem NAS und startet. Fragt einmal nach dem sudo-Passwort des NAS.
4. Backup: DSM → Systemsteuerung → Aufgabenplaner → Geplante Aufgabe → Benutzerdefiniertes Skript, Benutzer root, täglich: `sh /volume1/docker/abendausgabe/backup.sh`. Die Kopien liegen in `/volume1/docker/abendausgabe/backups` (14 Tage). Hyper Backup sichert den freigegebenen Ordner `docker` mit; das Ziel verschlüsseln, weil `.env` API-Schlüssel enthält.

Danach bei jeder Änderung `make deploy-nas`, Log mit `make logs-nas`. Wer von einem lokalen Testbetrieb umzieht, übernimmt PINs und Testberichte einmalig mit `make migrate-db-nas`.

## Quellen aus aller Welt

Der Weltblick zeigt jeden Abend Bilder und Kurzvideos aus Quellen weltweit, zum Beispiel aus Indien, Pakistan, Serbien, der Ukraine, Afrika oder Australien, dazu Agenturvideos von Bluesky. Bei zwei Beiträgen raten alle, aus welchem Land die Meldung kommt. Die Quellen stehen im Katalog unter [catalog/](catalog/README.md); welche ein Haushalt nutzt, legt `config/feeds.yaml` fest. Es gibt nur offene Zugänge (RSS, offizielle APIs). Gespeichert werden nur Titel und Links, und das höchstens drei Tage. Neue Quellen für den Katalog gerne per Pull Request.

## Mitbringsel

Am Handy unter „Etwas mitbringen“ teilt jede Person, was sie den anderen zeigen will: einen Link (YouTube, TikTok, Instagram, Reddit, Vimeo, Bluesky, jede Nachrichtenseite, ein Bild), ein eigenes Foto oder einen Screenshot, oder einfach einen Gedanken für die Runde. In der nächsten Sendung, bei der die Person dabei ist, läuft es gleich nach der Begrüßung; ab drei Personen raten die anderen erst, wer es mitgebracht hat. Eingebettet wird nur über die offiziellen Player der Plattformen. Der Server ruft nur öffentliche Adressen ab, nie etwas im Heimnetz.

## Morgen danach

Am Morgen nach einer Sendung fragt das Handy unter `/c/`: Wie war es gestern (1–5)? Dazu kommt eine Frage zum Vorabend. Die Antworten sind die wichtigste Messgröße der Abendausgabe; Verweildauer zählt nicht. Fragen kommen nach 3, 10 und 30 Tagen als Wiederholung zurück, am Ende der Sendung.

Wer eine Erinnerung will, schaltet sie im Profil (`/p/`) ein und abonniert das angezeigte Thema in der App [ntfy](https://ntfy.sh). Um 08:30 (`ABEND_MORNING_PUSH`) kommt dann eine Nachricht ohne Namen und ohne Inhalte. Der Link darin öffnet die Seite nur im Heimnetz; von unterwegs wartet die Frage bis zum Abend. Ein eigener ntfy-Server geht über `ABEND_NTFY_URL`.

## Handy erreicht die Seite nicht

Erst `http://<Server-IP>:8470/healthz` im Handy-Browser öffnen. Kommt keine Antwort:

1. Ist das Handy im Heimnetz und nicht im Gäste-WLAN? Seine IP muss wie die des Servers beginnen (z. B. 192.168.178.).
2. Hat der Browser ein eigenes VPN (Opera) oder läuft er in einem Arbeitsprofil (Aktentaschen-Symbol)? Anderen Browser probieren.
3. iPhone mit Chrome oder anderem Browser: Einstellungen → Browser → „Lokales Netzwerk“ erlauben. Safari braucht das nicht.
4. Fehlertext beachten: `ERR_CONNECTION_REFUSED` heißt, der Server lehnt ab (Firewall am Server); `ERR_ADDRESS_UNREACHABLE` oder Zeitüberschreitung heißen, das Netz lässt nicht durch (Router: „WLAN-Geräte dürfen untereinander kommunizieren“).

Tipp: Die Controller-Seite einmal zum Startbildschirm hinzufügen, dann ist sie ohne QR-Code erreichbar.

## Vergessene PIN

```sh
uv run abend reset-pin <person>                                   # lokal
docker compose exec app abend reset-pin <person>                  # im Container
```

Löscht PIN und Geräte dieser Person; bei der nächsten Anmeldung wird eine neue PIN festgelegt.

## Privatsphäre

Alles bleibt im Heimnetz. Ausnahmen sind die Abrufe bei den Quellen, die freiwillige Morgen-Erinnerung über ntfy (zufälliges Thema, fester Text), optional das LLM und die später vorgesehenen Routen unter `/ext` (Foto-Upload, Morgen-danach-Frage über HTTPS mit Token pro Person). Profilantworten haben eine Sichtbarkeit (nur ich / Admins / alle). Wer Admin-Zugriff auf den Server hat, kann die Datenbank technisch trotzdem lesen; das sollte man im Haushalt offen sagen.

## Lizenz

Code: [GNU AGPL-3.0-or-later](LICENSE). Wer eine veränderte Fassung anderen als Dienst anbietet, muss den Quelltext offenlegen.
Schrift Atkinson Hyperlegible Next: SIL Open Font License 1.1 (web/shared/fonts/OFL.txt).
