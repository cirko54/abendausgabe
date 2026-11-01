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

35. Folgen für den Phase-1-Plan (Nr. 23): Die Reihenfolge bleibt. Schritt 5 (Weltecke) baut den Quellenkatalog mit Metadaten und den Blickwinkel-Vergleich (SPEC §2.1); Schritt 6 (Assembler) bekommt den Fenster-Block als feste Regel. Die Oberfläche bleibt deutsch; die Übersetzbarkeit der UI-Texte ist offen (SPEC §15).
