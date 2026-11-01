#!/bin/sh
# Nächtliches Backup der Datenbank in einen Ordner, den Hyper Backup sichern kann.
# DSM → Systemsteuerung → Aufgabenplaner → Erstellen → Geplante Aufgabe → Benutzerdefiniertes Skript,
# Benutzer root, täglich 04:00, Befehl:
#   sh /volume1/docker/abendausgabe/backup.sh
set -eu

DIR=${ABEND_NAS_DIR:-/volume1/docker/abendausgabe}
DOCKER=${DOCKER:-/usr/local/bin/docker}
KEEP_DAYS=${KEEP_DAYS:-14}
DEST="$DIR/backups/abendausgabe-$(date +%F).sqlite3"

mkdir -p "$DIR/backups"
$DOCKER exec abendausgabe abend backup /data/backup/latest.sqlite3
$DOCKER cp abendausgabe:/data/backup/latest.sqlite3 "$DEST.tmp"
mv "$DEST.tmp" "$DEST"
find "$DIR/backups" -name 'abendausgabe-*.sqlite3' -mtime "+$KEEP_DAYS" -delete
echo "Backup: $DEST"
