#!/bin/sh
# Läuft als root auf dem NAS; aufgerufen von `make deploy-nas` (eine sudo-Passworteingabe).
# Aufruf: sudo sh <NAS_DIR>/build/deploy/nas/up.sh <NAS_DIR>
set -eu

DIR=${1:?NAS-Verzeichnis fehlt, z. B. /volume1/docker/abendausgabe}
DOCKER=${DOCKER:-/usr/local/bin/docker}
IMAGE=${IMAGE:-abendausgabe:local}
# compose nimmt das selbst gebaute Image statt des fertigen aus der Registry
export ABEND_IMAGE="$IMAGE"
PORT=${ABEND_PORT:-8470}
OWNER=${SUDO_USER:-root}

cd "$DIR"

cp build/deploy/docker-compose.yml docker-compose.yml
cp build/deploy/nas/backup.sh backup.sh
if [ ! -f .env ]; then
  cp build/.env.example .env
  chmod 600 .env
  chown "$OWNER" .env
  echo "==> .env aus .env.example angelegt ($DIR/.env)."
fi
mkdir -p backups config

echo "==> Image bauen (dauert beim ersten Mal ein paar Minuten) ..."
$DOCKER build -t "$IMAGE" build

if [ -f import/abendausgabe.sqlite3 ]; then
  echo "==> Datenbank vom Mac übernehmen ..."
  $DOCKER compose stop app 2>/dev/null || true
  # Bricht mit Code 3 ab, wenn im Volume schon eine Datenbank liegt (FORCE=1 überschreibt).
  $DOCKER compose run --rm --no-deps --user root -e FORCE="${FORCE:-0}" \
    -v "$DIR/import:/import:ro" app sh -c '
      if [ -e /data/abendausgabe.sqlite3 ] && [ "$FORCE" != 1 ]; then
        echo "Auf dem NAS liegt schon eine Datenbank; nichts überschrieben." >&2
        echo "Import verwerfen: import/abendausgabe.sqlite3 löschen. Überschreiben: FORCE=1." >&2
        exit 3
      fi
      rm -f /data/abendausgabe.sqlite3-wal /data/abendausgabe.sqlite3-shm
      install -o abend -g abend -m 600 /import/abendausgabe.sqlite3 /data/abendausgabe.sqlite3'
  mv import/abendausgabe.sqlite3 "import/uebernommen-$(date +%Y%m%d-%H%M%S).sqlite3"
fi

echo "==> Container starten ..."
$DOCKER compose up -d --force-recreate
$DOCKER image prune -f >/dev/null

i=0
until curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 30 ]; then
    echo "Server antwortet nach 30 s nicht. Log:" >&2
    $DOCKER compose logs --tail 40 app >&2
    exit 1
  fi
  sleep 1
done
echo "==> Läuft auf Port $PORT. Fernseher: http://<NAS-IP>:$PORT/tv/"
