# Abendausgabe für Android TV

Dünne Hülle: zeigt die TV-Seite des Servers im Vollbild, mit eigener Kachel auf dem Startbildschirm. Die Fernbedienung geht an die Seite; „Zurück“ und „Menü“ öffnen das App-Menü (Neu laden, Server-Adresse ändern, Beenden).

## Einmalig am Fernseher

1. Einstellungen → Geräteeinstellungen → Info: siebenmal auf „Build“ klicken. Die Entwickleroptionen erscheinen.
2. In den Entwickleroptionen „USB-Debugging“ einschalten. Auf Android TV öffnet das meist auch den Netzwerkzugang über Port 5555.
3. IP-Adresse des Fernsehers notieren: Einstellungen → Netzwerk und Internet → WLAN-Netz.

## Installation vom Mac

```sh
brew install --cask android-platform-tools      # einmalig; ohne Homebrew: platform-tools von developer.android.com
adb connect <TV-IP>:5555                         # am Fernseher „Immer zulassen“ ankreuzen, OK
adb devices                                      # muss „device“ zeigen, nicht „unauthorized“
adb install -r abendausgabe-tv.apk
adb shell am start -n app.abendausgabe.tv/.MainActivity --es url "<Server-IP>:8470"
```

Die Adresse wird gespeichert; danach reicht die Kachel. `/tv/` wird automatisch ergänzt, wenn nur Host und Port angegeben sind.

Prüfseite in der App öffnen:

```sh
adb shell am start -n app.abendausgabe.tv/.MainActivity --es url "<Server-IP>:8470/tv/check.html"
```

Zurück zur Sendung: dasselbe mit `--es url "<Server-IP>:8470"`.

Plan B, falls `adb connect` abgelehnt wird: APK auf einen USB-Stick kopieren, am Fernseher einen Dateimanager aus dem Play Store installieren, ihm „Unbekannte Apps installieren“ erlauben und die APK öffnen.

## Bauen

Ohne Android Studio und Gradle, nur JDK 17 und zwei SDK-Pakete (build-tools 34, platform 34):

```sh
BUILD_TOOLS=<…>/build-tools/34.0.0 PLATFORM_JAR=<…>/platforms/android-34/android.jar ./build.sh
```

Signaturschlüssel: Jeder Haushalt hat seinen eigenen. Beim ersten Bau erzeugt build.sh ihn unter `keystore/abendausgabe.jks`; der Ordner ist nicht im Repo (.gitignore). Ein eigenes Passwort mit `KEYSTORE_PASS=…` setzen, den Schlüssel sichern (am besten im privaten Instanzordner, README: Eigene Instanz) und nie committen.

Updates müssen mit demselben Schlüssel signiert sein. Geht er verloren, muss die App vor einer Neuinstallation deinstalliert werden.

Personalisierte Version (z. B. als Geschenk): `package` im Manifest ändern, damit beide Apps nebeneinander existieren können, App-Name in res/values/strings.xml, Kachel in res/drawable-xhdpi/banner.png.
