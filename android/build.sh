#!/usr/bin/env bash
# Baut die Android-TV-Hülle ohne Gradle/Android Studio (nur JDK 17 + Android-SDK-Teile).
#
# Benötigt:
#   BUILD_TOOLS  Ordner mit aapt2, d8, zipalign, apksigner (build-tools 34)
#   PLATFORM_JAR android.jar der Plattform 34
#   KEYSTORE / KEYSTORE_PASS  Signaturschlüssel (für Updates immer denselben verwenden!)
set -euo pipefail
cd "$(dirname "$0")"

BUILD_TOOLS="${BUILD_TOOLS:?BUILD_TOOLS setzen (Ordner mit aapt2, d8, zipalign, apksigner)}"
PLATFORM_JAR="${PLATFORM_JAR:?PLATFORM_JAR setzen (android.jar der Plattform 34)}"
KEYSTORE="${KEYSTORE:-keystore/abendausgabe.jks}"
KEYSTORE_PASS="${KEYSTORE_PASS:-abendausgabe}"
OUT="${OUT:-build/abendausgabe-tv.apk}"

rm -rf build && mkdir -p build/gen build/classes build/dex

"$BUILD_TOOLS/aapt2" compile --dir res -o build/res.zip
"$BUILD_TOOLS/aapt2" link -o build/unsigned.apk -I "$PLATFORM_JAR" \
  --manifest AndroidManifest.xml --java build/gen build/res.zip

javac -source 8 -target 8 -Xlint:-options -encoding UTF-8 \
  -bootclasspath "$PLATFORM_JAR:$BUILD_TOOLS/core-lambda-stubs.jar" -d build/classes \
  $(find src build/gen -name '*.java')

"$BUILD_TOOLS/d8" --release --min-api 21 --lib "$PLATFORM_JAR" --output build/dex \
  $(find build/classes -name '*.class')

(cd build/dex && zip -q ../unsigned.apk classes.dex)
"$BUILD_TOOLS/zipalign" -f -p 4 build/unsigned.apk build/aligned.apk

if [ ! -f "$KEYSTORE" ]; then
  mkdir -p "$(dirname "$KEYSTORE")"
  keytool -genkeypair -keystore "$KEYSTORE" -storepass "$KEYSTORE_PASS" -keypass "$KEYSTORE_PASS" \
    -alias abendausgabe -keyalg RSA -keysize 3072 -validity 36500 \
    -dname "CN=Abendausgabe, O=Familie" >/dev/null
fi

"$BUILD_TOOLS/apksigner" sign --ks "$KEYSTORE" --ks-pass "pass:$KEYSTORE_PASS" --out "$OUT" build/aligned.apk
"$BUILD_TOOLS/apksigner" verify --print-certs "$OUT" | head -3
echo "Fertig: $OUT"
