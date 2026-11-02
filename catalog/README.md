# Quellenkatalog

Gemeinsame Sammlung von Quellen, aus der jeder Haushalt für seine config/feeds.yaml auswählt (docs/SPEC.md §2.1 und §8.13). Erstausstattung seit Phase 1, Schritt 4 (docs/decisions.md Nr. 52). Welche Quellen ein Haushalt nutzt, steht in config/feeds.yaml.

Eine Datei pro Region oder Thema, zum Beispiel `serbien.yaml`, `umwelt-indien.yaml`. Pro Quelle (Beispiel, Angaben noch ungeprüft):

```yaml
- id: balkan-insight
  name: Balkan Insight
  url: https://balkaninsight.com
  feed: https://balkaninsight.com/feed/          # RSS/Atom; vor dem Eintrag prüfen
  country: [RS, BA, XK, MK, AL, ME]             # ISO 3166, Berichtsgebiet
  language: en
  publisher: BIRN (Balkan Investigative Reporting Network)
  funding: Stiftungen und Projektförderung      # mit Beleg, wo möglich
  perspective: investigativ, regional           # Selbstbeschreibung oder belegte Einordnung
  perspective_source: https://balkaninsight.com/about-us/
  license: Nutzungsbedingungen der Seite; nur Schlagzeile, Anriss und Link
  checked: 2026-11-01
```

Weitere Felder: `kind` (rss | bluesky | youtube), `actor` (Bluesky-Handle), `channel_id` (YouTube, nur mit `ABEND_YOUTUBE_API_KEY`), `images`/`video` (liefert die Quelle Bilder bzw. Videos), `topics`, `note`, `review: offen` (Träger oder Perspektive noch ohne Beleg). `country: []` heißt: berichtet weltweit, kein Herkunftsland fürs Länderraten.

Regeln:

- Nur offene Zugänge (RSS, offizielle APIs). Kein Scraping.
- Perspektive nie ohne Beleg; lieber Selbstbeschreibung als Fremdurteil.
- `checked` beim Prüfen des Feeds aktualisieren; tote Feeds entfernen.
