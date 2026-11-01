# Quellenkatalog

Gemeinsame Sammlung von Quellen, aus der jeder Haushalt für seine config/feeds.yaml auswählt (docs/SPEC.md §2.1 und §8.13). Das Format entsteht mit der Weltecke (Phase 1, Schritt 5); bis dahin ist dies der Entwurf.

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

Regeln:

- Nur offene Zugänge (RSS, offizielle APIs). Kein Scraping.
- Perspektive nie ohne Beleg; lieber Selbstbeschreibung als Fremdurteil.
- `checked` beim Prüfen des Feeds aktualisieren; tote Feeds entfernen.
