# Abendausgabe – Spezifikation v0.2

Stand 01.11.2026 (v0.1 vom 27.10.2026; v0.2: offen für andere Haushalte, Quellenpolitik, §2.1). Statusmarker: [R] recherchiert, [S] synthetisiert/Annahme, [H x%] Hypothese mit geschätzter Belastbarkeit.

## 1 Vision

Ein privater Sender für einen Haushalt, also Familie, Freunde oder Verwandte im eigenen Netz: einmal am Abend eine endliche, für die anwesende Runde redigierte Sendung (Ziel 30–45 min) auf dem Smart-TV im Wohnzimmer. Interaktion über Handys, später optional über Buzzer. Die Sendung ersetzt unendliche Feeds (Reddit, YouTube-Autoplay, Late-Night-Clips) durch einen Sendeablauf mit Sendeschluss. Netflix und Prime bleiben nativ am TV; die Abendausgabe kann höchstens die Auswahl moderieren.

Das Projekt ist offen (AGPL-3.0). Jeder Haushalt betreibt seine eigene Instanz im eigenen Netz; es gibt keinen zentralen Dienst und keine Daten, die das Haus verlassen, außer den Abrufen bei den Quellen und optional beim LLM-Anbieter.

## 2 Zielfunktion

Maximieren: kognitive Aktivierung und Morgen-danach-Wert.

Nebenbedingung: Niemand schaltet ab, weil er genervt (Überforderung, Belehrung) oder gelangweilt (Unterforderung, Wiederholung) ist.

Dritter, schleichender Gegner: Bequemlichkeit, also passives Durchlaufenlassen. Dagegen arbeitet die Architektur (Invarianten, Regeln, Interaktionsdesign), nicht primär der Inhalt.

Messgrößen, pro Person, sichtbar in Statistik und Programmkonferenz:

- Morgen-danach-Rating 1–5 plus eine Abruffrage (Push gegen 08:30)
- Retention: Trefferquote der Wiederholungsfragen nach 3, 10, 30 Tagen
- Kalibrierung: Brier-Score aus Paper-Wette und Prognosebörse
- Pessimismus-Index aus dem Kurvenzeichnen (Phase 2)
- Skip- und Abbruchrate pro Blocktyp, Signale „zu leicht“/„zu zäh“
- Ist- vs. Soll-Dauer der Sendung

Verboten als Optimierungsziel: Verweildauer, Klickrate, Zahl der Sendungen. Diese Werte dürfen geloggt werden, fließen aber nie in Ranking oder Assembler ein.

### 2.1 Grundgedanke: gemeinsam vor dem Fernseher, und raus aus der Blase, ohne Zwang [S]

Die Abendausgabe will das gemeinsame Erlebnis „wie früher“: Alle sitzen zusammen vor dem Fernseher und erleben eine Mischung aus Unterhaltung, geistiger Anregung und Miteinander. Kein Abend gleicht dem anderen, denn jede Sendung mischt Tagesaktuelles, die Interessen der Anwesenden, Zufall und das, was Einzelne mitbringen (Wunschzettel, Spotlight, Moment des Tages).

Filterblasen arbeiten gegen den sozialen Kitt einer Gesellschaft; die Abendausgabe soll sie einreißen. Fühlt sich das aber wie Pflicht an, ist die eigene Blase mittelfristig wieder die angenehmere Wahl. Deshalb Nudging statt Quote: gezielte Reize und Provokationen, für jeden so dosiert, wie er oder sie es gerade braucht.

- Brücke statt Bruch: Fremdes kommt über einen eigenen Zugang herein, etwa ein Fremdthema über ein bekanntes Hobby, eine ferne Region über ein vertrautes Problem.
- Dosis pro Person: Wie weit ein Block vom Gewohnten wegführt und wie scharf er provoziert, lernt das System aus „zu leicht“/„zu zäh“, Skips und dem Morgen-danach-Wert, nie aus der Verweildauer. Manche brauchen einen sanften Einstieg, andere den Widerspruch.
- Spiel statt Predigt: Die fremde Perspektive kommt als Rätsel („Wo spielt diese Meldung?“, „Aus welchem Land kommt dieser Blick auf die US-Wahl?“, „Wer hat darüber nicht berichtet?“). Raten macht neugierig, Belehren macht trotzig.
- Freiwilligkeit bleibt sichtbar: Jeder Block lässt sich überspringen. Ein übersprungener Block ist ein Signal für die Dosis, kein Fehler, und wird nie vorgehalten.
- Der Tisch als Hebel: Die wirksamste fremde Perspektive sitzt oft auf dem Sofa. Spotlight-Blöcke lassen Einzelne ihr Thema mitbringen und erklären; Auflösungen sind Anlass zum Gespräch, nicht dessen Ende.
- Zufall: Ein kleiner Anteil echter Überraschung, damit der Abend nicht berechenbar wird.

Bausteine:

- Fenster: In der Regel ein Block pro Sendung von außerhalb der gemeinsamen Blase, gewählt nach Abstand in den Quellmetadaten (Land, Sprache, Perspektive, Träger). Wie weit er wegführt, richtet sich nach der Runde; nie nach erwarteter Klickrate.
- Blickwinkel: Dieselbe Geschichte über Quellen aus verschiedenen Ländern und Lagern clustern und zeigen, wer berichtet, wie, und wer schweigt (Idee wie Ground News, eigene Umsetzung ohne deren Daten).
- Ausgrabung: Der lange Schwanz zählt: kleine Blogs, Newsletter, Regional- und Auslandspresse, Preprints, Archive, Podcasts. Bonus für Neuheit und Belegtheit, nicht für Popularität.

Gegen die Dopamin-Konkurrenz gewinnt die Sendung nicht durch Reizdichte, sondern durch das, was ein Feed nicht kann: gemeinsam raten und gegeneinander spielen, die Neugierlücke vor jeder Auflösung, kurze Blöcke mit Tempo, Endlichkeit mit einem verdienten Dessert. Ob das reicht, zeigen Morgen-danach-Wert und Abbruchrate, nicht die Verweildauer [H 60%].

## 3 Designinvarianten

1. Endlich: Jede Sendung hat eine Soll-Dauer und einen Sendeschluss-Screen. Kein Autoplay, keine Endlosliste, kein „mehr davon“ nach Sendeschluss (Ausnahme: Joker, Abschnitt 6).
2. Erst raten, dann sehen: Hat ein Block eine Interaktion, erscheinen Zusammenfassung und Auflösung erst nach der Eingabe aller Anwesenden oder nach Timeout.
3. Regeln entstehen im kalten Zustand: Programmregeln sind nur in der Programmkonferenz (Admin-Ansicht) änderbar. Live gibt es überspringen, pausieren, Sendeschluss, aber keine Regeländerung.
4. Reibungsasymmetrie: Denkblöcke sind Default und starten automatisch. Dessert kostet einen Schritt mehr und folgt auf einen Denkblock.
5. Punkte nur, wo sie Information tragen (Distanz, Brier, Quiztreffer). Keine Abzeichen, Streaks, Teilnahmepunkte.
6. Adaptive Schwierigkeit pro Person und Domäne, Ziel 75–85 % Erfolg [H 55%, dass dies der optimale Bereich ist].
7. Claude kaut nicht vor: LLM-Text ist Material für Fragen und Auflösungen, kein Ersatz fürs eigene Denken.
8. Robust: Ohne Mac und ohne LLM läuft eine Notausgabe.

Die Invarianten sind im Kern fest verdrahtet und pro Haushalt nicht abschaltbar. Einstellbar sind Parameter (Dauer, Dessert-Zahl, Denkblock-Takt, Joker). Wer die Prinzipien anders will, forkt (decisions.md Nr. 32).

## 4 Personen, Rollen, Profile

config/people.yaml, angelegt mit `abend init` (Beispiel: config.example/people.yaml): Personen mit Rolle admin oder member, höchstens sechs. Gäste können ohne Profil beitreten.

Admins verwalten Programmregeln, Quellen, Personen und Geräte. Members pflegen ihr eigenes Profil, Wünsche und Joker.

Identität: Bei der ersten Anmeldung legt jede Person eine PIN fest; weitere Geräte brauchen diese PIN. Ohne PIN wäre die Sichtbarkeit „nur ich“ wertlos. Wer Admin-Zugriff auf das NAS hat, kann die Datenbank technisch trotzdem lesen; das wird offen gesagt (decisions.md Nr. 2).

### 4.1 Profilfragebogen

Alle, besonders Kinder und Jugendliche, können ihn auf dem Handy jederzeit und nach Bedarf ausfüllen oder ändern. Alles ist optional, es gibt keinen Onboarding-Zwang. Ton: kurz, nicht schulisch. Schema in config/profile_schema.yaml, Antworten versioniert.

Fragen (Entwurf):

1. Worüber könntest du stundenlang reden? (Freitext)
2. Kanäle und Creator, die du gern schaust (Links; eine YouTube-Kanal-URL genügt)
3. Was würdest du gern besser verstehen oder können? (Freitext)
4. Welche Spiele machen dir Spaß? (Rangfolge: Ort raten, Schätzen, Quiz, Schach, Kurve zeichnen, Abstimmen)
5. Wie sehr willst du gefordert werden? (Slider entspannt bis hart)
6. Was nervt dich an gemeinsamen TV-Abenden? (Freitext; die wichtigste Frage gegen Langeweile und Genervtsein)
7. Themen, die du nicht sehen willst (Tags und Freitext)
8. Ein Thema, das du den anderen mal erklären könntest (Spotlight, Reverse Mentoring)
9. An welchen Abenden bist du meistens da? (Wochentage)
10. Wer darf deine Antworten sehen? (nur ich / Admins / alle; Default für Members „nur ich“; das System nutzt die Antworten trotzdem)

Das LLM leitet aus den Antworten Interessen-Tags und Quellenvorschläge ab. Die Vorschläge wirken erst, wenn der Profilinhaber sie bestätigt.

### 4.2 Wunschzettel

Jederzeit einen Link oder ein Thema einreichen: über „Wunsch“ in der Controller-PWA, auf Android per Web Share Target, auf iOS per Kurzbefehl, der an den Endpoint postet [H 85%: iOS Safari unterstützt Web Share Target weiterhin nicht]. Wünsche werden zu Kandidaten mit Bonus für den Einreicher.

## 5 Publikumsmodell

Drei Ebenen:

- Geplant: private ICS-Links der Kalender pro Person (Google oder iCloud, geheime Adresse). Fenster 19:30–22:30; ein Termin im Fenster bedeutet „nicht geplant“.
- Zu Hause: Router-Präsenz über ein Adapter-Interface; Implementierung FritzBox TR-064, falls vorhanden, sonst ARP-/Ping-Scan vom NAS. Das Mapping Gerät → Person steht in people.yaml. iPhones brauchen eine feste private WLAN-Adresse pro Netz [H 70%].
- Auf der Couch: Check-in per QR-Code, Controller oder Buzzer; Spätzugang jederzeit; Abmeldung „bin weg“.

Ablauf:

- 16:30 Planungslauf: Aus Kalender und Wochentagsprofil entsteht die erwartete Runde. Die Redaktion erzeugt einen Kandidatenpool, der alle plausiblen Teilrunden abdeckt.
- 17:30 optionaler Push: „Heute Abend voraussichtlich: …“. Optional eine Einladung an Einzelne („Geo-Duell um 20:15?“); höchstens eine Einladung pro Person und Abend, nie an laut Kalender Abwesende.
- Sendestart: Die endgültige Runde sind die Check-ins. Die Zusammenstellung erfolgt deterministisch aus dem Pool, ohne LLM-Call, in unter 2 s.
- Spätzugang: Folgeblöcke werden neu gewichtet, der laufende Block bleibt.

Gruppenlogik:

- Schnittmengen-Blöcke plus Spotlight-Rotation: Jeder Anwesende bekommt mindestens einen auf ihn zugeschnittenen Block pro Sendung.
- Handicap in Spielen aus den Ratings, sodass die erwartete Siegchance für alle ähnlich ist.
- Inhalte für Abwesende werden still geparkt (maximal 7 Tage), ohne FOMO-Push.
- Solo-Modus mit eigenen, strengeren Regeln; Solo-Abende gelten als Hochrisiko für Doomscrolling [H 60%].

## 6 Programmregeln

config/rules.yaml plus Admin-Ansicht. Beispiel:

```yaml
default:
  target_minutes: 40
  max_minutes: 55
  think_block_every_minutes: 10
  dessert_max: 1
  dessert_requires_preceding_think_block: true
  anchor: {module: tagesschau, at: "20:00"}
solo:
  target_minutes: 25
  dessert_max: 1
weekly:
  last_week_tonight_slot: {weekday: mon}
joker_per_person_per_week: 1
```

Joker: Einmal pro Woche darf jede Person eine Regel für den Abend aufheben, etwa für ein zweites Dessert. Autonomie senkt Reaktanz; die Knappheit verhindert, dass die Regeln ausgehöhlt werden.

Programmkonferenz: Admin-Ansicht, gedacht für sonntags. Sie zeigt die Wochenmetriken (Abschnitt 2) und vorgeschlagene Regeländerungen. Änderungen gelten ab der nächsten Sendung.

## 7 Blockmodell und Assembler

Jeder Kandidatenblock hat:

- module, title, est_minutes
- nutrition: demand 0–3, novelty 0–3, valence −1 bis +1, is_dessert
- domains (Tags), audience_fit {person: score}, difficulty
- interaction (Typ und Parameter), reveal (Inhalt der Auflösung)
- quiz_items für die Wiederholung, sources für die Attribution, expires_at

Der Assembler wählt aus dem Pool unter den Programmregeln aus; Greedy plus lokale Suche genügt. Optimiert wird der erwartete Morgen-danach-Wert der Runde (Abschnitt 9). Er garantiert Spotlight-Fairness und setzt den Anker (Tagesschau 20:00) fest.

## 8 Module

### 8.1 tagesschau (MVP)

- Quelle: inoffiziell dokumentierte, öffentlich nutzbare JSON-API www.tagesschau.de/api2u/ mit den Endpunkten homepage, news, channels und search; höchstens 60 Abrufe pro Stunde [R]. Nutzungsbedingungen von tagesschau.de beachten.
- Inhalt: 20-Uhr-Ausgabe aus channels, Alternative „tagesschau in 100 Sekunden“.
- Interaktion: während der Sendung keine. Danach 1–2 Fragen in den Quizpool; optional eine Vorab-Frage („Was wird heute Aufmacher?“).

### 8.2 wetter_himmel (MVP)

- Wetter vor acht über die MediathekViewWeb-API (Community-Projekt) [H 75%, dass die Sendung dort zuverlässig gelistet ist]. Fallback: Link in die ARD-Mediathek.
- Eigene Wetterkachel aus Open-Meteo für die Orte aus der Haushaltskonfiguration (etwa Wohnort und Ferienort); optional Bright Sky (DWD, nur Deutschland).
- Heute am Himmel:
  - Planeten und Mond mit Skyfield
  - ISS-Überflüge über dem Wohnort aus Celestrak-TLEs
  - Beobachtungsfenster aus der Bewölkung von Open-Meteo
- Interaktion: gelegentlich eine Schätzfrage, etwa „Wann geht heute der Mond auf?“.

### 8.3 weltecke (MVP)

Quellen in config/feeds.yaml, RSS wo verfügbar; die Feeds bei der Implementierung prüfen.

- Serbien: N1, Danas, Vreme, Balkan Insight, Balkan Green Energy News
- Afghanistan: Amu TV, Hasht-e Subh, Rukhshana Media, Afghanistan International (Exilmedien); TOLOnews, Pajhwok (Inland, unter Taliban-Bedingungen). Beide Perspektiven mischen und die Herkunft kennzeichnen.
- Indien: Down To Earth, Mongabay India, IndiaSpend, Scroll; konstruktiv: The Better India

Redaktion:

- Triage auf Umwelt und Gesellschaft, Dubletten-Clustering über Quellen hinweg
- Übersetzung ins Deutsche, Originalschlagzeile bleibt erhalten
- Ort extrahieren und über Nominatim geokodieren (höchstens 1 Anfrage/s, eigener User-Agent, Cache)

Interaktion:

- Ort raten auf der Handykarte. Kartenbasis: Protomaps-PMTiles-Datei lokal auf dem NAS, so bleibt die Tile-Nutzung unabhängig von fremden Servern.
- Punkte als Funktion der Distanz, Handicap aus dem Rating.
- Optional ein Straßenbild nahe dem Ort als Hinweis (Mapillary-API, Token, CC-BY-SA-Attribution).
- Auf dem TV erscheint die Auflösung als leichte SVG-Karte (Natural Earth, serverseitig projiziert) mit allen Tipps in Personenfarben, ohne WebGL.

### 8.4 paper_wette (MVP)

- Quellen: PubMed E-utilities (API-Key, höchstens 10 Anfragen/s) mit gespeicherten Suchen je Domäne, dazu Journal-TOC-Feeds aus der Konfiguration.
- Domänen pro Haushalt konfigurierbar, je mit gespeicherten Suchen. Beispiel: augenheilkunde (refraktiv, Linse, Hornhaut) und strahlentherapie; die Schwerpunkte verfeinert die jeweilige Fachperson im Profil.
- Auswahl: RCTs oder große Kohorten mit klar definiertem primärem Endpunkt und berichtetem Effektmaß; höchstens 2 pro Sendung.
- Redaktion:
  - extrahiert PICO, primären Endpunkt, Effektmaß mit KI, p-Wert und Richtung
  - Faktenprüfung: Jede Zahl muss wörtlich im Abstract vorkommen, sonst wird das Paper verworfen
- Interaktion:
  - Angezeigt wird nur PICO.
  - Jeder tippt die Richtung (besser/gleich/schlechter), die Effektgröße (Slider auf passender Skala) und die Wahrscheinlichkeit für Signifikanz (0–100 %).
  - Auflösung, dann Brier-Score und Abweichung pro Person.
- Fachfremd-Modus: Das Paper der eigenen Domäne zählt für die jeweils andere Person als Hauptwertung. Die Fachperson darf nach der Auflösung einen Satz Kontext geben.
- Members: optional eine Laienvariante, bei der nur die Richtung getippt wird.

### 8.5 moment_des_tages (MVP)

- Upload von Foto plus einer Zeile über die Controller-PWA, tagsüber auch unterwegs. Siehe Abschnitt 11.4 für die externe Erreichbarkeit.
- In der Sendung als Eröffnungsblock, höchstens ein Moment pro Person.
- Phase 2: „Heute vor n Jahren“ aus Synology Photos [H 80%: über die inoffizielle Web-API ansprechbar]; Fallback EXIF-Scan des Fotoordners.

### 8.6 quiz (MVP)

- Abschlussquiz: 3–5 Fragen aus der heutigen Sendung plus 2 Wiederholungsfragen. Intervalle 3, 10, 30 Tage nach Leitner-Art; eine falsche Antwort setzt die Frage auf 3 Tage zurück.
- Der Morgen-danach-Push enthält eine Abruffrage; sie ist zugleich Wiederholung.
- Gleiche Frage, angepasste Schwierigkeit pro Person über Antwortoptionen oder Toleranz.

### 8.7 youtube (Phase 2)

- Quellen: Kanäle aus Profilen und Wunschzettel. Abruf über das Kanal-RSS (feeds/videos.xml) [H 85%, dass es weiterhin verfügbar ist], Fallback YouTube Data API v3.
- Redaktion: Transkript aus verfügbaren Untertiteln oder per lokalem Whisper auf dem Mac. Das LLM liefert:
  - eine Kurzbewertung „lohnt sich für wen“
  - 1–2 Pause-Fragen mit Zeitstempel direkt vor einer Auflösung
  - Quizfragen
- Wiedergabe:
  - IFrame Player API (pause und seek bei Pause-Fragen)
  - Autoplay aus; nach Videoende den Block sofort verlassen, weil rel=0 Kanal-eigene Empfehlungen nicht vollständig unterdrückt
  - Werbung und Overlays nicht unterdrücken (YouTube-ToS)
- Abstimmung: 2–3 neue Videos zur Wahl, eines läuft, der Rest geht in die Wochenend-Warteschlange.
- Startliste: Vsauce, Vsauce2, Vsauce3, PBS Space Time (eher Wochenende oder Solo, oder mit Vorab-Frage).
- Vorschläge (Aktivität prüfen): 3Blue1Brown, Veritasium, Steve Mould, Stand-up Maths, Primer, minutephysics, Kurzgesagt, Terra X Lesch & Co, Fermilab.

### 8.8 late_night (Phase 2, Dessert)

- Late Night with Seth Meyers (vor allem „A Closer Look“) und Jimmy Kimmel Live: höchstens ein Segment als Dessert am Schluss. Bevorzugt wird ein Segment mit Themenbezug zur heutigen Sendung (Embedding-Ähnlichkeit zu den Tagesschau-Themen).
- Last Week Tonight (Main Story): eigener Wochenslot; zählt als Hauptgang, nicht als Dessert.
- Gelegentlich, höchstens einmal pro Woche, „Pointe oder Fakt?“: zwei Behauptungen aus dem Segment, die Runde tippt, die Auflösung kommt mit Quelle.

### 8.9 lichess (Phase 2)

- Tagesrätsel über die lichess-Puzzle-API, Züge per Abstimmung.
- „Fehler des Tages“ aus den eigenen Rapid-Partien: Export-API mit Evals, größter Eval-Verlust der letzten 24 h; die Runde rät den besseren Zug.
- Account-Namen stehen in people.yaml.

### 8.10 gute_nachricht_daten (Phase 2)

- Quellen: Our World in Data, Grapher-Charts mit CSV-Download je Chart [H 80%: stabil abrufbar]. Dazu eine kuratierte Liste langfristiger Trends und ein LLM-Klassifikator für konstruktive Nachrichten (Kriterium: messbare Verbesserung mit belegter Quelle).
- Interaktion: Jeder zeichnet die Kurve selbst (Canvas auf dem Handy). Die Auflösung legt alle Kurven übereinander; die Abweichung ergibt den Pessimismus-Index pro Person.

### 8.11 prognoseboerse (Phase 2)

- Wöchentlich 3 Fragen nach dem Muster „Passiert X bis Datum?“, getippt als Wahrscheinlichkeit 0–100 %.
- Auflösung: LLM-Vorschlag plus Admin-Bestätigung; Brier-Score pro Person.

### 8.12 film_abstimmung (Phase 3)

- TMDB (watch/providers für DE, eigene Abos konfiguriert): 3 Vorschläge passend zur Runde.
- Nach der Wahl folgt der Sendeschluss-Screen mit „Weiter in Netflix/Prime“.

### 8.13 Quellenpolitik

Im Kern nur offene oder offiziell angebotene Zugänge: RSS und Atom (Nachrichtenseiten weltweit, Blogs, Substack, Podcasts), YouTube-Kanal-RSS und IFrame-Player, Bluesky und Mastodon (offene APIs), Hacker News, Wikipedia, PubMed, Open-Data-Quellen, öffentlich-rechtliche APIs wie die Tagesschau.

Quellenkatalog: config/feeds.yaml mit Metadaten pro Quelle (Land, Sprache, Träger und Finanzierung, Perspektive mit Beleg der Einordnung, Lizenz). Kataloge lassen sich zwischen Haushalten teilen (catalog/ im Repo, per Pull Request erweiterbar); jeder Haushalt wählt aus.

Geschlossene Plattformen (X/Twitter, Instagram, TikTok, Reddit) sind kein Modul im Kern (decisions.md Nr. 31):

- Reddit beendet RSS am 13.11.2026, nimmt seit 31.10.2026 keine neuen Anträge auf API-Zugang an und schließt den öffentlichen API-Zugang bis März 2027 [R]. Ersatz bei Bedarf: Hacker News API, Lemmy, Primärquellen.
- X verlangt bezahlten API-Zugang; Instagram und TikTok bieten keine offene Feed-API. Scraping verstößt gegen die Nutzungsbedingungen und bricht laufend.
- Einzelne Beiträge kommen trotzdem in die Sendung: als Link über den Wunschzettel (§4.2), eingebettet über den offiziellen Embed bzw. oEmbed der Plattform, wo es ihn gibt, sonst als Screenshot mit Quelle.
- Wer mehr will, baut ein Plugin als eigenes Paket außerhalb des Kern-Repos (CONTRIBUTING.md) und verantwortet dessen Nutzungsbedingungen selbst.

## 9 Personalisierung und Schwierigkeit

- Glicko-2 pro Kombination aus Person, Domäne und Spieltyp. Fragen tragen eine Schwierigkeitsschätzung, initial vom LLM, danach empirisch nachkalibriert.
- Zielerfolgsrate anfangs 85 %. Sie sinkt schrittweise (etwa 0,5 Prozentpunkte pro Woche) bis 75 %, solange die Abbruchrate nicht steigt. Das ist progressive Überlastung als bewusstes Hintertreiben der Bequemlichkeit.
- Ebenso steigt die Länge ununterbrochener Denkphasen langsam [H 50%, dass das die Aufmerksamkeitsspanne trainiert].
- Interessenmodell:
  - explizit: Tags mit Gewichten aus dem Profil
  - implizit: Morgen-danach-Rating, Skips, „zu leicht“/„zu zäh“
  - Die Verweildauer geht nie ein.
- Langeweile-Erkennung live: Skip, Antwortlatenz oder ausbleibende Interaktion bei mehr als 2 Fragen führen dazu, dass der nächste Block kürzer wird oder das Register wechselt.

## 10 UI

### 10.1 TV (10-Fuß-UI)

- Logische Auflösung 1920×1080 (4K-TVs skalieren), Safe Area 5 % rundum.
- Mindestschrift 32 px für Fließtext, Titel ab 56 px, höchstens etwa 50 Zeichen pro Zeile.
- Bedienung per D-Pad: Pfeile, OK, Zurück. Die Keycodes sind plattformabhängig (Tizen Zurück 10009, webOS 461); die Mapping-Tabelle füllt der Fähigkeitstest. Kein Hover.
- Performance: TV-Browser sind schwach. Kein schweres Framework-Runtime im Live-Pfad, Animationen nur über transform und opacity.

Gestaltung (Vorschlag):

- Typografie: Atkinson Hyperlegible Next, eine Familie, lokal gehostet. Das Braille Institute hat sie für Lesbarkeit unter erschwerten Sehbedingungen entwickelt, was auf Distanz passt.
- Farben für den abgedunkelten Raum: Grund Nachtblau #0F1C2E, Fläche #1C2E45, Text #E9EEF2, gedämpft #9FB0C2.
- Personenfarben aus der Okabe-Ito-Palette (sicher bei Farbsehschwäche): #E69F00, #56B4E9, #009E73, #CC79A7; Gäste #F0E442.
- Ein einziger inszenierter Moment ist die Auflösung: Alle Tipps erscheinen in Personenfarbe, dann die Wahrheit. Übergänge zwischen Blöcken sind ein kurzer Ident (höchstens 2 s), sonst bleibt alles ruhig.
- Der Sendeablauf ist am Rand dauerhaft sichtbar (wo wir stehen, wie viel noch kommt), damit die Endlichkeit sichtbar bleibt.

### 10.2 Controller (Handy-PWA)

- Beitritt über den QR-Code auf dem TV, der direkt die Controller-Adresse enthält (ein Raum, kein Raumcode). Die Identität bleibt pro Gerät gespeichert; Personenwahl und PIN nur beim ersten Mal.
- Schätz-Regler ohne sichtbaren Startwert; Senden erst nach einer Bewegung, damit kein Anker entsteht.
- Eingabetypen:
  - Buzz, Auswahl, Slider, Wahrscheinlichkeit
  - Karte, Zeichnen, Rating
  - „zu leicht“/„zu zäh“, Skip-Vorschlag (übersprungen wird bei Mehrheit)
  - Spätzugang, „bin weg“
- Zwischen Interaktionen schaltet der Controller in einen Ruhemodus: fast schwarzer Screen mit „Handy kann weg“ [H 55%, dass das Nebenbei-Scrollen senkt].
- Außerdem: Profilfragebogen, Wunschzettel und eigene Statistiken (Retention, Kalibrierung, Pessimismus-Index).

### 10.3 Admin

- Programmkonferenz, Quellenverwaltung, Personen und Geräte, LLM-Budget, Logs.

## 11 Architektur

### 11.1 Komponenten

Jeder Docker-Host im Heimnetz genügt (NAS, Raspberry Pi 4/5, Mini-PC); das Image gibt es für amd64 und arm64. Die Redaktion kann auf demselben Host laufen, solange das LLM per API kommt. Referenzinstallation:

- NAS Synology DS720+ (x86-64, Container Manager, läuft 24/7):
  - Container app: FastAPI, WebSocket, Scheduler, Fetcher, Assembler, statische Frontends
  - Container ntfy für Push
  - SQLite (WAL) auf einem Volume, Backup über Hyper Backup
- Mac mini M4 Pro (WLAN): redaktion, aus demselben Python-Paket.
  - Start per launchd um 16:30, Weckzeit per pmset.
  - Holt Rohdaten per API vom NAS, schreibt Kandidatenblöcke zurück, schläft danach.
  - Optional lokales Whisper (Phase 2) und ein lokales MLX-Modell für die Triage.
- Fernseher: eigene Android-TV-App (WebView-Hülle, android/), die http://<nas>:<port>/tv/ lädt; Rückfallebene ist der TV-Browser.
  - Videos (Tagesschau, YouTube) laufen direkt vom CDN zum TV.
  - Server und Redaktion liefern nur UI und JSON; eine WLAN-Anbindung ist deshalb unkritisch.
- Handys: Controller-PWA im LAN; nur die Routen unter /ext sind von außen erreichbar (11.4).

### 11.2 Phase 0: TV-Fähigkeitstest (zuerst bauen)

Die Seite /tv/check prüft folgende Punkte und meldet sie an den Server:

- User-Agent und Plattform, Auflösung, unterstützte JS-Features
- WebSocket
- HLS nativ oder über hls.js/MSE, MP4-Wiedergabe
- Wiedergabe im YouTube-IFrame
- Webfonts
- Keycodes über einen interaktiven Tastentest
- FPS bei einer transform-Animation

Entscheidungsbaum:

1. Der TV-Browser genügt: fertig.
2. YouTube oder HLS scheitert: eine paketierte TV-Web-App über den Developer Mode von Tizen oder webOS prüfen.
3. Sonst: ein günstiger Streaming-Stick mit Kiosk-Browser.

Das Ergebnis kommt in docs/decisions.md.

### 11.3 LLM

- Voreinstellung: Anthropic API über das offizielle Python-SDK. Der Anbieter steckt hinter einer schmalen Schnittstelle, damit Forks andere oder lokale Modelle einsetzen können; ohne LLM läuft die Notausgabe.
- Modelle per .env; Defaults: Triage claude-haiku-5-5, Redaktion und Übersetzung claude-sonnet-5-5. Die Modellnamen vor der Implementierung unter docs.claude.com prüfen.
- Strukturierte JSON-Ausgaben mit Pydantic-Validierung; Prompt-Dateien sind versioniert.
- Cache nach Inhalts-Hash; Tagesbudget mit hartem Stopp; jeder Aufruf wird geloggt (Tokens, Kosten).
- Faktentreue: Zahlen, Effektmaße und Zitate werden per String-Match gegen den Quelltext geprüft; bei einem Mismatch wird der Block verworfen.

### 11.4 Externe Erreichbarkeit

Nur die Routengruppe /ext/* ist erreichbar, über den Synology-Reverse-Proxy mit HTTPS auf der vorhandenen Synology-DDNS-Domain (eigene Subdomain oder eigener Pfad):

- POST /ext/moment: Upload Moment des Tages
- GET/POST /ext/morning: Morgen-danach-Rating und Abruffrage

Absicherung: Token pro Person, Größenlimit, Ratelimit.

Push über eine von zwei Varianten, Entscheidung in Phase 1: ntfy selbst gehostet hinter demselben Reverse Proxy (Auth aktiv; für iOS die upstream-base-url setzen) oder ntfy.sh mit zufälligen Topic-Namen und minimalem Nachrichteninhalt.

Alles andere bleibt LAN-only.

### 11.5 Ausfallsicherheit

Liefert die Redaktion bis 19:15 nichts, baut der Assembler eine Notausgabe ohne LLM: Tagesschau, Wetter und Himmel, Wiederholungsquiz aus dem Bestand, Moment des Tages.

## 12 Datenmodell (Skizze)

- person, device
- profile_answer (versioniert, mit visibility), wish
- calendar_source, presence_event
- session (eine Sendung) und session_member
- raw_item (Quelle, Hash, Rohinhalt mit TTL)
- candidate_block (JSON, nutrition, audience_fit, expires_at)
- rundown (geordnete Block-IDs, Soll- und Ist-Dauer)
- interaction (person, block, payload, ts)
- prediction (Brier-fähig)
- quiz_item und review_state (Leitner-Box, due)
- rating (Morgen danach)
- glicko_rating (person, domain, game)
- rules (versioniert), joker_use, llm_call_log

## 13 Rechtliches und Etikette

- Nutzung privat im Haushalt; jede Instanz verantwortet ihre Quellen selbst. Das Projekt betreibt keinen Dienst und verteilt keine Inhalte.
- Attribution sichtbar: OSM/Protomaps, Mapillary (CC-BY-SA), OWID (CC-BY), TMDB.
- Ratelimits: Tagesschau 60/h, Nominatim 1/s, PubMed mit Key 10/s.
- YouTube nur über den offiziellen Player, keine Werbeunterdrückung.
- Volltexte nur mit TTL cachen, Videos nie herunterladen.

## 14 Phasen und Abnahmekriterien

Phase 0: Gerüst, TV-Fähigkeitstest, Beitritt per QR, Dummy-Ablauf, Profilfragebogen.
Abnahme: Testergebnis des echten TVs ist dokumentiert; zwei Handys steuern eine Dummy-Sendung live.

Phase 1 (MVP): Module 8.1–8.6, Publikumsmodell (Kalender und Check-in), Programmregeln, Assembler, Morgen-danach-Push, Notausgabe.
Abnahme:
- 7 Abende am Stück ohne manuellen Eingriff
- Sendedauer im Soll ±10 %
- Redaktionslauf unter 15 min, LLM-Kosten im Budget

Phase 2: Module 8.7–8.11, Router-Präsenz, Glicko und Interessenmodell, Spotlight-Rotation, Joker, Statistikansichten.

Phase 3: Filmabstimmung, Buzzer, optionale TTS-Moderation, Programmkonferenz mit Regelvorschlägen.
- Buzzer: Flic mit Hub und HTTP-Aktionen, oder Hue Smart Button, falls eine Hue-Bridge vorhanden ist.

## 15 Offene Punkte

- TV-Plattform: Referenzgerät geklärt (Android TV, eigene App; decisions.md Nr. 12–19). Andere Plattformen (Fire TV, Google TV, Tizen, webOS) melden ihr Ergebnis über /tv/check.html.
- Präsenzadapter: Fritz!Box TR-064 zuerst, weitere per Adapter-Interface.
- Sprache der Oberfläche: bisher nur Deutsch. Übersetzbarkeit (UI-Texte aus Dateien) für Haushalte anderswo vorsehen.
- LLM-Tagesbudget: pro Haushalt in .env.

## Anhang: Evidenzbasis der Designentscheidungen

Aus Wissen zusammengestellt, nicht nachrecherchiert; Studientyp in Klammern.

- Regeln im kalten Zustand: Loewenstein 2005, Health Psychol (Theorie/Review, Hot-cold Empathy Gap); Ariely & Wertenbroch 2002, Psychol Sci (Experimente zu selbstgesetzten Deadlines).
- Reibungsasymmetrie und Defaults: Johnson & Goldstein 2003, Science (Länderdaten und Online-Experiment).
- Erst raten, dann sehen:
  - Kang et al. 2009, Psychol Sci (fMRI und Verhalten, Neugier fördert das Behalten)
  - Gruber, Gelman & Ranganath 2014, Neuron (fMRI)
  - Brod 2021, Psychon Bull Rev (Review, Vorhersagen als Lernstrategie)
- Dessert nach Denkblock: Milkman, Minson & Volpp 2014, Management Science (Feld-RCT zu Temptation Bundling; der Effekt verblasste nach einer Unterbrechung).
- Quiz und Wiederholung: Roediger & Karpicke 2006, Psychol Sci (Experimente, Testing-Effekt); Cepeda et al. 2006, Psychol Bull (Metaanalyse, Spacing).
- Erklären statt empfangen: Fiorella & Mayer 2013, Contemp Educ Psychol (Experiment, Learning by Teaching).
- Keine Abzeichen: Deci, Koestner & Ryan 1999, Psychol Bull (Metaanalyse, Untergrabung intrinsischer Motivation durch erwartete Belohnung).
- Claude kaut nicht vor: Risko & Gilbert 2016, Trends Cogn Sci (Review, kognitives Offloading).
- Zielerfolgsrate: Wilson et al. 2019, Nat Commun (theoretisch/ML, 85-%-Regel; Übertragung auf Menschen ist eine Hypothese).
- Paper-Wette: DellaVigna, Pope & Vivalt 2019, Science (Policy Forum zu Forecasting wissenschaftlicher Ergebnisse).
