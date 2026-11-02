# Entscheidungen

Format: Datum, Entscheidung, Grund, verworfene Alternativen.

Die Einträge stammen aus der Referenzinstallation (ein Haushalt, Synology-NAS, Philips Android TV). Haushaltsdetails sind entfernt.

## 2026-10-27 – Phase 0

1. Frontends in Phase 0 ohne Build-Schritt: Vanilla-JS (ES2017), die Prüfseite /tv/check.html in ES5.
   Grund: Die TV-Plattform ist unbekannt; die Prüfseite muss auch auf dem schwächsten Browser laufen, und die Wahl eines Frameworks hängt am Testergebnis.
   Vorerst verworfen: Svelte 5 + Vite. Neu bewerten, sobald das TV-Ergebnis vorliegt.

2. Identität pro Person mit PIN (4–8 Ziffern, PBKDF2), Gerät per httpOnly-Cookie.
   Grund: Die Sichtbarkeit „nur ich“ im Profil wäre wertlos, wenn jedes Handy jede Person wählen könnte.
   Grenze: Wer Admin-Zugriff auf das NAS hat, kann die Datenbank technisch lesen. Die Sichtbarkeit ist app-seitig durchgesetzt und darüber hinaus eine Abmachung in der Familie; das offen so sagen.
   Vergessene PIN: `abend reset-pin <person>`.

3. Ein Raum (Wohnzimmer), kein Raumcode; der QR-Code enthält direkt die Controller-Adresse.
   Grund: ein Haushalt, ein Fernseher.
   Verworfen: Raumcodes; erst nötig, wenn es mehrere Bildschirme gibt.

4. TV-WebSocket ohne Authentifizierung.
   Grund: nur im LAN erreichbar, und der Fernseher hat keine sinnvolle PIN-Eingabe.
   Risiko: Jedes Gerät im WLAN kann „OK“ senden. Neu bewerten, falls Gäste-WLAN und Heimnetz dasselbe Netz sind.

5. Eine getrennte Verbindung bedeutet nicht „abgemeldet“.
   Grund: Handys sollen schlafen dürfen (Ruhemodus). Abmelden geht nur per „Bin weg“; offene Fragen lösen per Timeout auf.

6. Der Schätz-Regler zeigt keinen Startwert; Senden geht erst nach einer Bewegung.
   Grund: Ein vorgegebener Wert wirkt als Anker und verzerrt die Schätzung (Tversky & Kahneman 1974).

7. QR-Code dunkel auf hell.
   Grund: Invertierte Codes lesen nicht alle Kamera-Apps zuverlässig.

8. Port 8470; Daten im Docker-Volume `abend-data` statt in einem Bind-Mount.
   Grund: vermeidet Rechteprobleme mit uid 1000 auf Synology-Freigaben.

9. Der Tagesschau-Abruf ist in der Bauumgebung nicht live verifiziert, weil ihr Netzwerkfilter tagesschau.de blockiert.
   Die Auswertung ist mit einer nachgebauten Antwort getestet (tests/fixtures). Der erste echte Abruf passiert beim TV-Test im Heimnetz. find_media_urls sucht rekursiv jede .m3u8- und .mp4-URL und ist damit robust gegen Strukturänderungen; im schlechtesten Fall meldet der Test „kein Testvideo“.

10. End-to-End-Durchlauf im Headless-Chromium bestanden: TV und zwei Handys, ganze Testsendung, Profil speichern, keine JavaScript-Fehler.
    Das ersetzt nicht den Test auf dem echten Fernseher.

11. Abhängigkeiten gepinnt: uv.lock für die Entwicklung, requirements.lock mit Hashes für das Docker-Image (`make lock` erzeugt beides neu).
    Das Docker-Image wurde in der Bauumgebung nicht gebaut (kein Docker verfügbar); der erste Build passiert mit `make deploy-nas` auf dem Mac.

Offen für Phase 1: TV-Ergebnis hier eintragen, Router-Typ (Präsenz), Kalenderquellen, LLM-Tagesbudget.

## 2026-10-31 – Erster Test am echten Fernseher

12. Gerät: Philips UHD Android TV 2021/22 (TP Vision MT9970, Android 11). Eingebauter Browser Opera-basiert mit Chromium 77, Fensterbreite 1280 × 720 bei DPR 1,5.
    Befund: ES2017 ja, ES2020 nein; WebSocket 45 ms; Webfont geladen; YouTube-Einbettung spielt; 57 Bilder/s; HLS nicht nativ, MediaSource vorhanden; keine einzige Taste kam als Tastenereignis an.
    Das Urteil „B“ war ein Fehlurteil: Der Server fand kein Testvideo, weil die Tagesschau-API Pfade mit Schrägstrich per 308 umleitet und httpx Weiterleitungen standardmäßig nicht folgt. MP4 wurde also nie getestet. Behoben; ein ungetestetes Format zählt jetzt als „offen“, nicht als „fehlgeschlagen“. Neu bewertet: A, vorläufig (Regressionstest mit dem echten Bericht in tests/fixtures).

13. Konsequenzen:
    - Build-Target es2017 bleibt (Chromium 77).
    - Livestreams über hls.js, lokal ausgeliefert (keine CDN-Abhängigkeit).
    - Die TV-Seite setzt keine Tastenereignisse voraus: klickbarer „Weiter“-Knopf für den Cursor-Modus, Steuerung sonst über die Handys.
    - Die Prüfseite testet Tasten jetzt zuerst (vor dem YouTube-iframe, das den Fokus übernehmen kann), wertet auch keyup aus und erkennt den Cursor-Modus.
    - Zwei Hypothesen für die fehlenden Tasten: Der Browser bewegt mit den Pfeilen einen Mauszeiger (Cursor-Modus) oder das YouTube-iframe hatte den Fokus. Der nächste Testlauf trennt beides.
    - Falls Tasten weiterhin fehlen und das stört: Android TV erlaubt eine eigene kleine App (WebView-Hülle) oder einen Kiosk-Browser aus dem Play Store. Hypothese (70 %): Die System-WebView ist aktueller als der eingebaute Browser und liefert Tastenereignisse.

## 2026-11-01 – Zweiter Test am Fernseher (nach Update 1)

14. Ergebnis A. MP4 spielt, YouTube spielt, 58 Bilder/s, WebSocket 144 ms, Schrift geladen. Testvideos wurden gefunden (Livestream-URL und MP4).
    Cursor-Modus bestätigt: 179 Zeigerbewegungen, 11 Klicks, Start per Klick, keine einzige Taste. Der Opera-basierte Browser gibt die Fernbedienung nicht an Seiten weiter.

15. Steuerung: Die Handys sind die Fernbedienung. Am Fernseher genügt der klickbare „Weiter“-Knopf als Rückfallebene. Pfeiltasten-Navigation wird im TV-Frontend nicht gebaut.
    Zurückgestellt (Phase 3, Komfort): eigene Android-TV-App als WebView-Hülle (Autostart, keine URL-Eingabe, Tastenereignisse, aktuellere Engine).

16. Livestream: hls.js ist nötig (kein natives HLS, MediaSource vorhanden), auf dem Fernseher aber noch nicht getestet.
    Geprüft aus der Bauumgebung: Die Tagesschau-CDN (ard-mcdn.de → akamaized.net) sendet `Access-Control-Allow-Origin: *`; hls.js darf die Playlists also von unserer Seite laden. Außerhalb Deutschlands wird der Stream geoblockiert; im Heimnetz kein Problem.
    Hypothese (90 %): hls.js spielt auf Chromium 77 mit MediaSource. Test beim Bau des Tagesschau-Blocks in Phase 1; Rückfall ist die MP4 der 20-Uhr-Ausgabe kurz nach der Ausstrahlung.

17. Frontend-Strategie: Der TV-Browser genügt; kein Framework-Wechsel nötig, um ihn zu bedienen. Ob Svelte für Controller und Admin lohnt, entscheidet Phase 1 nach Aufwand, nicht nach TV-Fähigkeit. Build-Target für alles, was der Fernseher lädt: es2017.

## 2026-11-01 – Eigene Android-TV-App statt TV-Browser

18. Der Fernseher bekommt eine eigene kleine App (android/): eine WebView-Hülle mit Kachel auf dem Startbildschirm, die die TV-Seite im Vollbild zeigt.
    Grund: Der Browser funktioniert, ist im Alltag aber zu umständlich (Browser öffnen, Lesezeichen, Mauszeiger) und verletzt damit unsere eigene Reibungsregel (SPEC §3 Nr. 4): Die Abendausgabe muss so leicht zu starten sein wie Netflix. Außerdem ist der Browser auf Chromium 77 eingefroren.
    Erwartet: Fernbedienungstasten erreichen die Seite (Hypothese 85 %), aktuellere Engine über die System-WebView (Hypothese 75 %), Videos starten mit Ton (setMediaPlaybackRequiresUserGesture false).
    Gebaut ohne Gradle (nur JDK 17, aapt2, d8, apksigner), damit der Build schlank und auf dem Mac reproduzierbar bleibt. Updates brauchen denselben Signaturschlüssel. (Ursprünglich lag er im Repo; seit Nr. 30 hat jeder Haushalt seinen eigenen außerhalb des Repos.)
    „Zurück“ und „Menü“ öffnen in der App ein Menü und erreichen die Seite nicht; die Prüfseite überspringt den Zurück-Test in der App.
    Die Server-Adresse ist einstellbar (per adb-Intent oder im Menü), damit dieselbe App später als personalisierte Version verschenkt werden kann.

## 2026-11-01 – Phase 0 abgenommen

19. Die Android-TV-App läuft auf dem Philips-Fernseher. Die System-WebView ist per Play Store auf Chromium 156 aktualisiert (ab Werk 119), statt Chromium 77 im TV-Browser. OK und Pfeiltasten erreichen die Seite; „Zurück“ öffnet wie vorgesehen das App-Menü.
    Folge: Das TV-Frontend darf die Fernbedienung nutzen (OK = Weiter, Pfeile für Auswahl). Build-Target es2017 bleibt trotzdem, weil der TV-Browser als Rückfallebene und unbekannte Geräte (Geschenkversion) es brauchen und es ohne Build-Schritt nichts kostet.

20. Handy-Browser: Das Heimnetz war erreichbar, aber Opera und Chrome auf einem Android-Handy nicht (Ecosia schon). Vermutlich Opera-VPN bzw. eine Chrome-Einstellung. Checkliste im README unter „Handy erreicht die Seite nicht“.

21. Abnahme Phase 0 erfüllt: TV-Ergebnis dokumentiert (Nr. 12–19), Testsendung mit zwei Handys und Fernbedienung vollständig durchgespielt.

22. Empfohlene Reihenfolge für Phase 1, damit früh ein täglich nutzbarer Abend entsteht:
    1. Server aufs NAS (make deploy-nas, feste IP für das NAS in der Fritz!Box, App-Adresse umstellen). Dann muss der Mac abends nicht laufen.
    2. Tagesschau-Block mit hls.js-Livetest am Fernseher, Wetter vor acht.
    3. Quiz mit Wiederholung nach 3/10/30 Tagen und Morgen-danach-Frage.
    4. Paper-Wette (PubMed + Claude-API, Faktenprüfung).
    5. Weltecke mit Ortsraten.
    6. Assembler mit Programmregeln, Kalender und Check-in.
    Schritte 1–3 ergeben bereits eine echte Sendung; ab dann täglich nutzen und die Morgen-danach-Werte sammeln.
    Danach (für Weihnachten): internetfähige Instanz pro Haushalt mit HTTPS und Kopplung des Fernsehers per Code.

## 2026-11-01 – Plan Phase 1

23. Reihenfolge wie Nr. 22, jeder Schritt mit eigener Abnahme, bevor der nächste beginnt:
    1. Server aufs NAS. Abnahme: /healthz vom Mac und vom Handy über die NAS-IP, App am Fernseher zeigt die Sendung vom NAS, Testsendung läuft bei ausgeschaltetem Mac, nächtliches Backup liegt in einem Hyper-Backup-fähigen Ordner.
    2. Tagesschau-Block (hls.js lokal, Rückfall MP4) und Wetter vor acht. Abnahme: Livestream am Fernseher getestet, Ergebnis hier eingetragen.
    3. Quiz mit Leitner 3/10/30 und Morgen-danach-Frage (dafür ntfy-Entscheidung, SPEC §11.4). Abnahme: eine echte Sendung aus 1–3 an einem Abend, Morgen-danach-Push am nächsten Morgen.
    4. Paper-Wette, 5. Weltecke, 6. Assembler mit Regeln, Kalender, Check-in und Notausgabe.
    Abnahme der ganzen Phase nach SPEC §14 (7 Abende, Dauer ±10 %, Redaktion unter 15 min, Kosten im Budget).

## 2026-11-01 – Phase 1, Schritt 1: Umzug aufs NAS

24. Das Image wird auf dem NAS gebaut, nicht per buildx auf dem Mac. **Annahme**, bitte bestätigen.
    Grund: Auf dem Mac ist kein Docker installiert; das NAS ist selbst x86-64 und baut nativ. Eine andere App auf demselben NAS wird genauso deployt. requirements.lock mit Hashes hält den Build reproduzierbar.
    Ablauf (`make deploy-nas`): Quelltext per tar nach /volume1/docker/abendausgabe/build, Konfiguration nach config/, danach eine einzige SSH-Sitzung mit sudo (eine Passworteingabe), die deploy/nas/up.sh ausführt: Image bauen, `compose up -d`, verwaiste Images löschen.
    `COPYFILE_DISABLE=1` und Ausschluss von `._*`: macOS-tar packt sonst AppleDouble-Dateien mit ein (Erfahrung aus einem anderen Projekt).
    Verworfen: Docker Desktop oder Colima auf dem Mac (zusätzliche Installation, Image doppelt übertragen); `make image-amd64` bleibt für einen Mac mit Docker erhalten. Verworfen auch: den SSH-Nutzer in eine docker-Gruppe aufnehmen oder sudo ohne Passwort; beides ist root-gleich und wäre eine Sicherheitsänderung am NAS.

25. Das NAS bekommt in der Fritz!Box eine feste IPv4-Adresse (die aktuelle). Es bezieht die Adresse per DHCP; ohne Reservierung kann sich die Adresse ändern, und die App am Fernseher findet den Server nicht mehr. Die Reservierung stellt der Nutzer in der Fritz!Box ein (Heimnetz → Netzwerk → NAS → „Diesem Netzwerkgerät immer die gleiche IPv4-Adresse zuweisen“).

26. Backup: Das Volume `abend-data` (Nr. 8) liegt unter /volume1/@docker und ist für Hyper Backup nicht wählbar. Deshalb zieht deploy/nas/backup.sh nachts eine konsistente Kopie (SQLite-Backup-API über `abend backup`) aus dem Container nach /volume1/docker/abendausgabe/backups und behält 14 Tage. Einrichtung einmalig im DSM-Aufgabenplaner als root. Hyper Backup sichert den Ordner docker mit.
    Verworfen: Bind-Mount statt Volume (Rechteprobleme, Nr. 8); Datei einfach kopieren (bei WAL nicht konsistent).

27. Die lokale Datenbank vom Mac wird einmalig übernommen (`make migrate-db-nas`): eine PIN und die 4 TV-Testberichte. Gerätecookies gelten pro Adresse, die Handys melden sich also am NAS neu an (PIN bleibt). Das Skript bricht ab, wenn auf dem NAS schon eine Datenbank liegt.

28. Speichergrenze für den Container: 512 MB (`mem_limit`). Das NAS hat 6 GB, davon etwa 3 GB frei; die App braucht heute unter 100 MB.

## 2026-11-01 – Öffnung: offenes Projekt für andere Haushalte

29. Die Abendausgabe wird ein offenes GitHub-Projekt. Andere sollen sie für ihre Familie, Freunde oder Verwandten im eigenen Netz betreiben, forken und weiterentwickeln können, auch mit Claude Code oder ohne.
    Das öffentliche Repo startet mit neuer Historie. Die alte Historie enthielt den Signaturschlüssel der TV-App und Haushaltsdaten; sie bleibt als privates Archiv beim ursprünglichen Haushalt.
    Verworfen: die alte Historie mit git filter-repo bereinigen (ein übersehener Rest wäre dauerhaft öffentlich).

30. Kern und Instanz sind getrennt. Im Repo liegt nur, was für alle gilt; jeder Haushalt hält seine Daten in einem eigenen, privaten Ordner:
    - config.example/ mit einem erfundenen Beispielhaushalt (Alex, Sam, Kim, Robin). Fehlt eine Datei in config/, gilt die Beispieldatei; eine frische Installation startet so als Demo.
    - `abend init` legt config/people.yaml an (Namen, Rollen, Farben aus Okabe-Ito) und kopiert die übrigen Beispieldateien.
    - Nicht im Repo (.gitignore): config/, local.mk (NAS-Host für make), android/keystore/. Bequem als Symlinks auf den Instanzordner (README: Eigene Instanz).
    - Signaturschlüssel der TV-App pro Haushalt; build.sh erzeugt ihn beim ersten Bau.
    - Tests laufen immer gegen den Beispielhaushalt, nie gegen die eigene Konfiguration.

31. Quellenpolitik (SPEC §8.13): Im Kern nur offene oder offiziell angebotene Zugänge. Geschlossene Plattformen (X, Instagram, TikTok, Reddit) kommen nicht als Modul in den Kern, sondern als einzelner Link über den Wunschzettel, eingebettet über den offiziellen Embed, oder als Plugin außerhalb des Kern-Repos. Die Invariante „Kein Reddit-Modul“ bleibt und gilt jetzt für alle geschlossenen Plattformen sinngemäß.
    Grund: Scraping verstößt gegen die Nutzungsbedingungen, bricht laufend und würde jeden Haushalt, der das Projekt nutzt, mit hineinziehen.
    Verworfen: Scraper-Module im Kern; nur die Reddit-Invariante streichen.

32. Die Designinvarianten (SPEC §3) sind im Kern fest verdrahtet, nicht pro Haushalt abschaltbar. Einstellbar sind Parameter (Dauer, Dessert-Zahl, Denkblock-Takt, Joker).
    Grund: Die Prinzipien sind die Identität des Projekts und gerade das, was es von den Feeds unterscheidet, die es ersetzen soll. Wer sie anders will, forkt.
    Verworfen: alles abschaltbar (die App könnte dann zu dem werden, was sie ersetzen soll).

33. Lizenz AGPL-3.0-or-later. Die Schrift bleibt unter SIL OFL 1.1.
    Grund: Forks bleiben offen, auch wenn jemand die Abendausgabe als Dienst anbietet. Das schützt die Idee davor, als geschlossene, auf Verweildauer optimierte Familien-App weiterverkauft zu werden. Beiträge stehen unter derselben Lizenz (kein CLA).
    Verworfen: MIT oder Apache-2.0 (Forks dürfen geschlossen werden); GPL-3.0 (keine Netzwerkklausel).

34. Erweiterbarkeit ohne Fork:
    - Inhaltsmodule als Plugins: eigenes Python-Paket, Anmeldung über den Entry-Point-Bereich `abendausgabe.modules`. Eingebaute Module lassen sich so nicht überschreiben.
    - LLM-Anbieter hinter einer schmalen Schnittstelle (kommt mit dem ersten edit.py in Schritt 4); Claude ist Voreinstellung.
    - Fertiges Image für amd64 und arm64 aus GitHub Actions in der GitHub Container Registry; `ABEND_IMAGE` wählt ein anderes (Fork, selbst gebaut). Selbst bauen bleibt möglich (`make deploy-nas`).
    **Annahme:** Registry-Pfad ghcr.io/cirko54/abendausgabe; Forks setzen ihren eigenen.

35. Folgen für den Phase-1-Plan (Nr. 23): Die Reihenfolge bleibt. Schritt 5 (Weltecke) baut den Quellenkatalog mit Metadaten und den Blickwinkel-Vergleich (SPEC §2.1); Schritt 6 (Assembler) bekommt den Fenster-Block (seit Nr. 40 dosiert, keine Quote). Die Oberfläche bleibt deutsch; die Übersetzbarkeit der UI-Texte ist offen (SPEC §15).

## 2026-11-01 – Stand Abnahme Schritt 1 (NAS)

36. Abgenommen: Server läuft auf dem NAS (selbst gebaut, Nr. 24), Haushaltskonfiguration aktiv, Datenbank übernommen (Nr. 27), feste IP und Backup-Aufgabe eingerichtet. App am Fernseher und Handys laufen über die NAS-IP, die Testsendung läuft ohne Mac.
    Offen bleibt nur die Sichtprüfung des ersten nächtlichen Backups im Ordner backups.

## 2026-11-01 – Plan Phase 1, Schritt 2: Tagesschau und Wetter vor acht

37. Ab jetzt stellt der Server bei jedem Sendestart einen Tagesablauf zusammen, statt die Testsendung abzuspielen: Begrüßung, Wetter vor acht, Aufmacher-Frage, tagesschau, Sendeschluss. Das ist die erste Fassung der Notausgabe (SPEC §11.5, ohne LLM, unter assembly/); der Assembler mit Regeln folgt in Schritt 6. `ABEND_PROGRAM=test` spielt weiter die Testsendung.
    Neuer Blocktyp `video`. OK an der Fernbedienung pausiert bzw. spielt weiter; „Weiter“ erst nach dem Ende, mit Pfeil rechts oder über das Handy. Ein versehentliches OK soll die Nachrichten nicht überspringen. Nach dem Ende startet nichts automatisch (SPEC §3 Nr. 1).
    Welche tagesschau läuft, entscheidet der Server erst beim Start des Blocks (GET /api/media/tagesschau), nicht beim Zusammenstellen. So passt die Wahl auch, wenn die Sendung früher beginnt: 19:58–20:16 Uhr der Livestream von tagesschau24 [H 80 %, dass tagesschau24 die 20-Uhr-Ausgabe zeitgleich sendet], sonst die 20-Uhr-Ausgabe von heute als MP4, sonst die neueste „tagesschau in 100 Sekunden“ von heute.
    Aufmacher-Frage („Womit macht die tagesschau heute auf?“) nur, wenn die heutige 20-Uhr-Ausgabe schon vorliegt: richtige Antwort ist das erste Thema der Themenliste aus der API [H 85 %, dass die Liste in Sendereihenfolge steht], Ablenker sind zwei weitere Themen derselben Sendung. Wörtlich aus der Quelle, ohne LLM.
    Wetter vor acht über MediathekViewWeb, nur wenn die Sendung von heute ist (gestriges Wetter hilft niemandem). Fehlt sie, entfällt der Block; die eigene Wetterkachel aus Open-Meteo folgt mit dem Modul wetter_himmel.
    Abnahme: Livestream (hls.js) und MP4 am Fernseher getestet, Ergebnis hier eingetragen.

38. Neue Abhängigkeit hls.js 1.7.3 (Apache-2.0), lokal ausgeliefert unter web/shared/vendor/ (Nr. 13: keine CDN-Abhängigkeit), Integrität gegen den npm-Hash geprüft. Nur für HLS ohne native Unterstützung; spielt der Browser HLS selbst, bleibt hls.js ungenutzt.
    Version: neueste, die älter als zwei Wochen ist (1.7.4 erschien am 28.10.2026).
    Verworfen: Video.js oder Shaka Player (größer, für einen Livestream unnötig).

39. Neue Quelle MediathekViewWeb (Community-Projekt): höchstens 30 Abfragen pro Stunde über den zentralen Ratelimiter, 10 Minuten Cache, eigener User-Agent.

40. Blasen einreißen per Nudging, nicht per Quote (SPEC §2.1, auf Hinweis des Projektinhabers neu gefasst). Der Fenster-Block ist ein weiches Ziel („in der Regel einer“); wie weit er vom Gewohnten wegführt und wie scharf er provoziert, wird pro Runde dosiert und aus „zu leicht“/„zu zäh“, Skips und Morgen-danach-Wert gelernt. Fremdes kommt bevorzugt über eine Brücke aus eigenen Interessen und als Rätsel, nicht als Belehrung. Übersprungene Fenster-Blöcke senken die Dosis, ohne Vorwurf.
    Grund: Fühlt sich der Blick über den Tellerrand wie Pflicht an, wird die eigene Blase mittelfristig wieder die angenehmere Wahl. Ziel ist sozialer Kitt, nicht Erziehung.
    Verworfen: feste Quote („mindestens ein Block“).
    Offen für Schritt 6: eine Profilfrage, wie gern jemand provoziert werden will (ergänzt Frage 5 „Wie sehr willst du gefordert werden?“).

## 2026-11-01 – Schritt 2: Test am Fernseher

41. Prüfseite in der Android-TV-App (Chromium 156) gegen den NAS-Server: MP4 spielt, HLS nativ spielt, HLS über hls.js 1.7.3 spielt (tagesschau24-Livestream), YouTube spielt, 78 Bilder/s, WebSocket 36 ms. Hypothese aus Nr. 16 bestätigt.
    Folge: In der App spielt der Fernseher HLS selbst; hls.js ist Rückfallebene für den TV-Browser (Chromium 77) und fremde Geräte. tv.js wählt deshalb zuerst den nativen Weg.
    Vorher im Headless-Chrome durchgespielt: Videoblock spielt, Zustandsmeldungen unterbrechen ihn nicht, OK pausiert, Pfeil rechts schaltet weiter.
    Offen: echte Sendung um 20 Uhr mit dem Livestream; dabei klären, ob tagesschau24 die 20-Uhr-Ausgabe zeitgleich zeigt (Nr. 37, H 80 %). Das Server-Log zeigt die Rückmeldung „TV-Wiedergabe“ mit dem Weg (hls-nativ, hls.js, mp4).

## 2026-11-01 – Schritt 2: erste echte Sendung, Vollbild, zeitversetzt

42. Erste Sendung live um 20:08 am Fernseher: Der Livestream lief über den nativen Player („hls-nativ“) und zeigte die 20-Uhr-tagesschau. Nr. 37 ist damit bestätigt: tagesschau24 sendet sie zeitgleich. Die API führt dazu einen eigenen Eintrag „Aktuelle Sendung: Tagesschau 20 Uhr“ mit Beginn und Ende als Unix-Zeit, auch nach der Sendung. Um 20:08:24 meldete der native Player einmal Fehler 4 (Quelle nicht abspielbar); die Ursache ist offen.
    Rückmeldung aus dem Haushalt: (a) Das Video soll Vollbild sein. (b) Niemand soll um Punkt 20 Uhr vor dem Fernseher sitzen müssen.
    Entscheidung (a): Der Videoblock füllt den Bildschirm. Titel und Bedienhinweis blenden nach 5 s aus und kommen bei Taste, Pause und Ende zurück. Die Quelle bleibt oben links klein sichtbar, unten liegt der Nachrichtenticker der tagesschau. Untertitel des Streams sind aus (später als Haushaltsoption denkbar).
    Entscheidung (b): Der tagesschau24-Stream hält zwei Stunden vor (3600 Segmente à 2 s mit EXT-X-PROGRAM-DATE-TIME). Die Reihenfolge ist deshalb: (1) die veröffentlichte Aufzeichnung von heute; (2) sonst ab 19:58 bis 100 Minuten nach Beginn der Livestream. Nach Beginn springt hls.js an den Sendebeginn, bei 20:08 also zeitversetzt von vorn, und hält am Sendeende an, statt ins nächste tagesschau24-Programm zu laufen (kein Autoplay). (3) Sonst kommen die neuesten 100 Sekunden. Für Anfang und Ende braucht es die Sendezeit je Segment, deshalb nimmt tv.js für den Livestream hls.js statt des nativen Players; der native Weg bleibt Rückfall mit geschätzter Position.
    Geprüft im Headless-Chrome um 20:40: Der Sprung landet auf 0,0 s genau beim Sendebeginn (Gong), der Videoblock ist Vollbild, die Leiste blendet aus.
    Offen: Wann die Aufzeichnung erscheint (bisher geschätzt 20:20 bis 20:30), Test der Halt-Logik am echten Sendeende, Test am Fernseher mit hls.js. Vor 19:58 gibt es weiterhin nur die 100 Sekunden; eine frühere Ausgabe (z. B. 17 Uhr) führt der Endpunkt `channels` nicht.

## 2026-11-02 – Abnahme Schritt 2

43. Abgenommen: Am Fernseher läuft die tagesschau im Vollbild, auch zeitversetzt von vorn (Rückmeldung des Haushalts am 1.11. abends). Offen bleiben nur Beobachtungen: wann die Aufzeichnung erscheint, und ob die Halt-Logik am echten Sendeende greift.

## 2026-11-02 – Plan Phase 1, Schritt 3: Wiederholung und Morgen danach

44. Fragenpool und Leitner (SPEC §8.6). Neue Tabellen `quiz_item` (Frage, Optionen, richtige Antwort, Quelle, Sendetag) und `review_state` (Person, Frage, Box, fällig am). Ablauf je Person:
    - Erste Begegnung (in der Sendung oder morgens): Box 1, fällig nach 3 Tagen, egal ob richtig.
    - Richtig bei Fälligkeit: Box 2 (10 Tage), dann Box 3 (30 Tage), danach gilt die Frage als gelernt und kommt nicht wieder.
    - Falsch: zurück in Box 1, fällig nach 3 Tagen.
    - Wer eine Wiederholungsfrage beantwortet, obwohl sie für ihn noch nicht fällig ist, rückt nicht vor (Abstand ist der Sinn). Falsch setzt trotzdem zurück.
    Die Wiederholung kommt als eigene Auswahlblöcke vor dem Sendeschluss: höchstens 2 Fragen, die für die meisten Anwesenden fällig sind, die ältesten zuerst. Gewählt wird beim Sendestart, wenn feststeht, wer da ist. Die Room-Logik bleibt rein; Fragen anlegen und Boxen fortschreiben macht der RoomManager beim Persistieren der Auflösung.
    Woher die Fragen kommen, solange es kein LLM gibt: die Aufmacher-Frage zur 20-Uhr-tagesschau, wörtlich aus der Themenliste (Nr. 37). Lief in der Sendung die tagesschau, ohne dass die Vorab-Frage möglich war (Start vor Erscheinen der Aufzeichnung, Nr. 42), legt der Server die Frage am nächsten Morgen nach: Die API führt die 20-Uhr-Ausgabe bis zum nächsten Abend.
    **Annahme:** Das Abschlussquiz mit 3–5 Fragen aus der heutigen Sendung (SPEC §8.6) braucht Fragen zum Inhalt, also das LLM mit Faktenprüfung. Es kommt mit der Redaktion in Schritt 4 (tagesschau-`edit.py` neben der Paper-Wette). Schritt 3 baut Pool, Leitner, Wiederholungsblöcke und den Morgen danach.

45. Morgen danach (SPEC §2, §8.6). Auf dem Handy unter /c/ eine Karte „Wie war die Abendausgabe gestern?“ mit Bewertung 1–5 und einer Abruffrage. Die Auflösung kommt erst nach der Antwort. Gezeigt wird die Karte jeder Person, die bei der letzten Sendung dabei war, bis zur nächsten Sendung. Wer morgens nicht antwortet, sieht sie abends beim Einchecken noch einmal. Neue Tabelle `morning_rating`.
    Die Abruffrage ist eine Frage aus der Sendung von gestern, sonst eine fällige Wiederholung. Sie zählt als Begegnung bzw. Wiederholung nach Nr. 44: Richtig rückt nur vor, wenn die Frage fällig war; falsch setzt zurück.

46. Push: ntfy, Variante „ntfy.sh mit zufälligem Topic und minimalem Inhalt“ (SPEC §11.4). **Annahme**, bitte bestätigen.
    - Pro Person freiwillig: Im Profil (/p/) schaltet jede Person die Morgenfrage selbst ein. Der Server erzeugt ein zufälliges Topic (128 Bit) und zeigt einen Link bzw. QR-Code für die ntfy-App (Android, iOS) sowie eine Testnachricht.
    - Um 08:30 (`ABEND_MORNING_PUSH`) geht an jede Person, die gestern dabei war und noch nicht geantwortet hat, genau eine Nachricht: „Wie war die Abendausgabe gestern? Eine Frage wartet.“ Die Nachricht enthält keine Namen und keine Inhalte. Sie verlinkt auf die LAN-Adresse des Servers; die Adresse merkt sich der Server beim Einschalten. Versandte Nachrichten werden in der Datenbank vermerkt, damit ein Neustart keine doppelten verschickt.
    - Ein eigener ntfy-Server geht über `ABEND_NTFY_URL` (Voreinstellung https://ntfy.sh).
    - Grund: ntfy.sh braucht keinen weiteren Container, keinen Reverse Proxy und keine Freigabe nach außen. ntfy.sh sieht nur ein zufälliges Topic, den festen Text und eine private IP-Adresse.
    - Verworfen für jetzt: ntfy selbst hosten (zweiter Container, Reverse Proxy mit Auth, für iOS upstream-base-url); Web Push (braucht HTTPS und einen Service Worker, im LAN über http nicht möglich).
    - Folge: Die Antwortseite liegt im LAN. Von unterwegs öffnet der Link nichts; die Karte wartet dann bis zum Abend (Nr. 45). /ext/morning kommt mit der internetfähigen Instanz (Nr. 22).
    Planer: eine schlanke asyncio-Schleife im Server, die einmal pro Minute prüft. APScheduler (CLAUDE.md, Stack) bleibt draußen, bis mehrere zeitgesteuerte Aufgaben ihn rechtfertigen; keine neue Abhängigkeit.
    Abnahme Schritt 3 (Nr. 23): Eine echte Sendung mit tagesschau; am nächsten Morgen kommt der Push, und Bewertung und Abruffrage landen in der Datenbank. Nach 3 Tagen erscheint die Frage als Wiederholung.

## 2026-11-02 – Neue Reihenfolge: die Welt zuerst

47. Auf Wunsch des Projektinhabers kommt die Welt vor der Paper-Wette. Sie ist der Kern der Idee (SPEC §2.1); die Paper-Wette ist ein Spezialthema des Referenzhaushalts. Neue Reihenfolge ab Schritt 4:
    4. Welt I, ohne LLM: Quellenkatalog mit Metadaten, Abruf im Hintergrund, Block „Weltblick“ mit Bildern und Kurzvideos, dazu „Mitbringsel“: Links, die Personen per Handy einreichen (auch TikTok, Instagram, Reddit, eingebettet über den offiziellen oEmbed).
    5. Redaktion mit LLM: Übersetzung, Untertitel, gleiche Geschichte über Quellen hinweg (Blickwinkel), Ort und Karte (Weltecke), Inhaltsfragen zur tagesschau fürs Abschlussquiz (Nr. 44).
    6. Paper-Wette. 7. Assembler mit Regeln, Kalender, Check-in und dosiertem Fenster.

48. Bilder und Kurzvideos. Zum Abend gehört Bewegtbild; Text allein verliert gegen den Feed. Woher sie kommen:
    - Bilder liefern viele Nachrichten-Feeds gleich mit (media:content bzw. enclosure). Stand 2.11.2026 bei über 20 von 30 geprüften Feeds, darunter Hindi, Urdu und Serbisch.
    - Kurzvideos kommen von Bluesky. Die öffentliche API ist offen, ohne Konto. Medienhäuser posten dort Videos als HLS (geprüft: Reuters 14 und AP 24 von je 30 Posts), und die spielt derselbe Player wie die tagesschau.
    - Alles wird nur verlinkt, nie heruntergeladen (CLAUDE.md). Gespeichert werden Titel, Links und Metadaten mit Ablaufzeit.
    - Ton: Kurzvideos starten stumm, wenn der Beitrag Untertitel oder eine Bildunterschrift hat. OK schaltet den Ton ein. Jeder Weltblick hat eine feste Zahl von Beiträgen und endet; nichts läuft automatisch weiter (SPEC §3 Nr. 1).

49. YouTube: Der Kanal-Feed (feeds/videos.xml) antwortet vom Mac aus 8 von 8 Mal mit 404. Seit Ende 2025 wird das häufig gemeldet; eine offizielle Abschaltung gibt es nicht. Deshalb ist der YouTube-Abruf nur optional: über die offizielle Data API v3 mit `ABEND_YOUTUBE_API_KEY`. Die API ist kostenlos, Kontingent 10.000 Einheiten pro Tag, eine Kanalabfrage kostet 1 Einheit. Ohne Schlüssel fehlen YouTube-Kanäle, sonst nichts. Abgespielt wird nur über den offiziellen IFrame-Player.

50. Geschlossene Plattformen bleiben ohne Kernmodul (Invariante, Nr. 31). Ein Abruf von TikTok, Instagram oder Reddit nach Konto oder Hashtag findet nicht statt. Einzelne Beiträge kommen als Mitbringsel: Eine Person teilt einen Link, der Server holt die offizielle oEmbed-Einbettung. Geprüft am 2.11.2026: TikTok, Instagram und Reddit antworten. Klappt die Einbettung am Fernseher nicht, kommt eine Karte mit Vorschaubild, Quelle und QR-Code zum Original.

51. Neue Abhängigkeit feedparser 6.0 (BSD-2-Clause, in CLAUDE.md als Stack vorgesehen) für RSS und Atom. Neue Tabelle `raw_item` (SPEC §12): Abruf alle 2 Stunden im Server. Der Tagesablauf wählt beim Sendestart aus der Datenbank, damit der Start nicht auf 30 Feeds wartet.

52. Quellenkatalog (catalog/, Format nach catalog/README.md): Erstausstattung mit geprüften Feeds aus Südasien (Indien, Pakistan, Afghanistan), Balkan, Afrika, Osteuropa, Asien-Pazifik, Lateinamerika und globalen Medien. Je Quelle ist der Feed geprüft (Datum in `checked`). Den Träger trage ich nur ein, wo er allgemein bekannt ist. Die Perspektive bleibt leer, bis ein Beleg vorliegt (Regel im Katalog); `review: offen` markiert das.
    Weltblick ohne LLM: Drei Beiträge aus verschiedenen Ländern, je mit Bild oder Video und Originalschlagzeile. Die Frage lautet „Aus welchem Land kommt diese Meldung?“, mit drei Ländern zur Auswahl, Auflösung mit Quelle und Link. Bis zur Übersetzung (Schritt 5) bleiben fremdsprachige Schlagzeilen im Original; die Sprache ist dann selbst ein Hinweis.

53. HLS spielt jetzt immer zuerst über hls.js, der eingebaute Player ist nur Rückfall. Grund: Am Fernseher meldete der eingebaute Player am 1.11. um 20:08 Fehler 4 (Nr. 42). Im Desktop-Chrome scheiterte er am 2.11. reproduzierbar an einem Bluesky-Video, ebenfalls mit Fehler 4; hls.js spielte dasselbe Video. Nr. 41 („nativ zuerst“) ist damit überholt.
    Stand Weltblick, Teil 1 (2.11.2026): Katalog mit 28 Quellen; alle waren beim ersten Abruf erreichbar. Im Headless-Chrome geprüft: Raterunde mit Bild und serbischer Originalschlagzeile, Auflösung mit Quelle, am Handy der Link „Zum Original“, Kurzvideo von Reuters hochkant, stumm mit Text, ▲ schaltet den Ton ein.
    Reihenfolge im Ablauf: Begrüßung, Wetter, tagesschau, Weltblick, Wiederholung, Sendeschluss. Erst die eigene Nachrichtensicht, dann die der anderen.
    Offen in Schritt 4: Mitbringsel (Nr. 50), Test am Fernseher.
