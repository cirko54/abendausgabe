# Mitmachen

Willkommen. Die Abendausgabe soll in vielen Haushalten laufen und von vielen weiterentwickelt werden, mit Claude Code, einem anderen Werkzeug oder von Hand. Diese Seite sagt, was feststeht, was erwünscht ist und wie ein Beitrag aussieht.

## Was feststeht

Die Designinvarianten (docs/SPEC.md §3) sind der Kern des Projekts. Pull Requests, die eine davon aufweichen, nehmen wir nicht an. Wer es anders will, forkt; die Lizenz erlaubt das ausdrücklich.

- Jede Sendung ist endlich und endet mit einem Sendeschluss-Screen. Kein Autoplay, keine Endloslisten.
- Erst raten, dann sehen: Auflösungen erst nach der Eingabe.
- Verweildauer und Klickrate fließen nie in Auswahl oder Ranking ein (loggen ist erlaubt).
- Keine Abzeichen, Streaks oder Teilnahmepunkte.
- Programmregeln sind live nicht änderbar (Ausnahme: Joker).
- Jede Zahl und jedes Zitat aus einem LLM wird gegen den Quelltext geprüft; bei Abweichung fliegt der Block raus.
- Eine Notausgabe funktioniert ohne LLM.

Parameter wie Dauer, Dessert-Zahl oder Denkblock-Takt sind dagegen pro Haushalt einstellbar (config/rules.yaml).

## Was besonders gebraucht wird

- **Quellen**, die Blasen sprengen: Nachrichtenseiten aus anderen Ländern und Sprachen, Lokal- und Exilmedien, Fachblogs, Newsletter, Preprints, Archive, Podcasts. Je obskurer und belegter, desto besser.
- **Spielformen**, die Denken anregen: Schätzen, Ort raten, Kurve zeichnen, Wetten mit Wahrscheinlichkeit, Quellen zuordnen.
- **Fernseher-Berichte**: `/tv/check.html` auf eurem Gerät laufen lassen und das Ergebnis als Issue melden.
- **Übersetzung** der Oberfläche (bisher nur Deutsch).

## Quellenpolitik

Im Kern nur offene oder offiziell angebotene Zugänge: RSS und Atom, offizielle APIs, offizielle Embeds. Kein Scraping von Plattformen, deren Nutzungsbedingungen es verbieten. X/Twitter, Instagram, TikTok und Reddit sind deshalb kein Kernmodul (docs/SPEC.md §8.13). Einzelne Beiträge von dort kommen über den Wunschzettel als Link in die Sendung. Ein Plugin außerhalb des Kern-Repos ist möglich und liegt in eurer Verantwortung.

Jede neue Quelle braucht:

- die Ratelimits der Quelle, über den zentralen Ratelimiter (core/ratelimit.py)
- eine sichtbare Attribution in der Sendung
- Metadaten für den Quellenkatalog: Land, Sprache, Träger und Finanzierung, Perspektive mit Beleg der Einordnung, Lizenz (catalog/README.md)
- Volltexte nur mit Ablaufzeit speichern, Videos nie herunterladen

## Ein Modul bauen

Ein Modul liefert Kandidatenblöcke für die Sendung. Es ist entweder Teil des Kerns (`src/abendausgabe/modules/<name>/`) oder ein eigenes Python-Paket.

- `fetch.py` läuft auf dem Server: nur HTTP, nutzt den zentralen Ratelimiter, schreibt raw_item.
- `edit.py` läuft in der Redaktion: LLM-Aufrufe mit versionierten Prompts unter `prompts/<modul>/`, Ausgabe als JSON mit Pydantic-Validierung, erzeugt candidate_block.
- `block.py`: Pydantic-Schema für Block, Interaktion, Auflösung und quiz_items.
- Tests mit aufgezeichneten Antworten unter `tests/fixtures`, keine Live-Abrufe.
- Ein neues Modul darf keine Änderung am Assembler erfordern.

Als eigenes Paket meldet sich ein Modul über einen Entry Point an:

```toml
# pyproject.toml des Plugins
[project.entry-points."abendausgabe.modules"]
mein_modul = "mein_paket.mein_modul"
```

Namen nur aus a–z, 0–9 und _. Eingebaute Module lassen sich nicht überschreiben.

## Ablauf eines Beitrags

1. Für Größeres erst ein Issue: Was soll es tun, für wen, welche Invariante berührt es?
2. Architektur- und Abhängigkeitsentscheidungen kommen in docs/decisions.md (Datum, Entscheidung, Grund, verworfene Alternativen). Neue Abhängigkeiten nur mit Begründung.
3. `uv run pytest`, `uv run ruff check .` und `uv run mypy src` müssen grün sein; CI prüft das.
4. Sprache: UI-Texte deutsch, kurz und aktiv. Code, Bezeichner und Commits englisch. Fehlermeldungen sagen, was passiert ist und was zu tun ist.
5. Zielgeräte sind schwach: Was der Fernseher lädt, bleibt ES2017, ohne WebGL, Animationen nur über transform und opacity.

## Mit Claude Code

CLAUDE.md enthält die Arbeitsregeln für Claude Code und gilt genauso für Menschen. Persönliche Daten (config/, Schlüssel, .env) gehören nie ins Repo, auch nicht in Beispiele, Tests oder Prompts.

## Lizenz

Beiträge stehen unter der Lizenz des Projekts, GNU AGPL-3.0-or-later. Es gibt kein CLA.
