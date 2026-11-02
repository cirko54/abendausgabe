FROM python:3.12-slim

LABEL org.opencontainers.image.title="Abendausgabe" \
      org.opencontainers.image.description="Endliche, interaktive Abendsendung fürs Wohnzimmer" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ABEND_CONFIG_DIR=/app/config \
    ABEND_EXAMPLE_CONFIG_DIR=/app/config.example \
    ABEND_DATA_DIR=/data \
    ABEND_WEB_DIR=/app/web \
    ABEND_CATALOG_DIR=/app/catalog

WORKDIR /app
# Abhängigkeiten aus dem Lockfile, mit Hash-Prüfung (requirements.lock via `make lock`)
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --no-deps .
COPY web ./web
# Nur das Beispiel; die eigene Konfiguration wird nach /app/config eingehängt
COPY config.example ./config.example
COPY catalog ./catalog

RUN useradd --create-home --uid 1000 abend && mkdir -p /data && chown abend /data
USER abend

EXPOSE 8470
HEALTHCHECK --interval=60s --timeout=5s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8470/healthz', timeout=3)" || exit 1
CMD ["abend", "serve", "--host", "0.0.0.0", "--port", "8470"]
