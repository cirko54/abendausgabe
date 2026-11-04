# Eigene Werte (NAS-Host usw.) in local.mk; die Datei wird nicht committet
-include local.mk
# SSH-Host des NAS (Port und Schlüssel in ~/.ssh/config)
NAS ?= nas
NAS_DIR ?= /volume1/docker/abendausgabe
IMAGE ?= abendausgabe:local
# Was das NAS zum Bauen braucht; alles andere (android/ mit Signaturschlüssel, data/, .env) bleibt auf dem Mac
BUILD_FILES = Dockerfile .dockerignore pyproject.toml README.md requirements.lock .env.example \
              src web config.example catalog deploy
TAR_EXCLUDES = --no-xattrs --no-mac-metadata --exclude='._*' --exclude='.DS_Store' --exclude='__pycache__' --exclude='*.pyc'

.PHONY: dev test lint lock image-amd64 upload-nas deploy-nas migrate-db-nas logs-nas \
        install-redaktion uninstall-redaktion

dev:
	uv run abend serve --reload

test:
	uv run pytest

lint:
	uv run ruff check . && uv run mypy src

lock:
	uv lock && uv export --frozen --no-dev --no-emit-project -o requirements.lock

# Nur für einen Mac mit Docker; das NAS baut sonst selbst (docs/decisions.md Nr. 24)
image-amd64:
	docker buildx build --platform linux/amd64 -t $(IMAGE) --load .

# Quelltext und Konfiguration hochladen (ohne sudo)
upload-nas:
	ssh $(NAS) 'mkdir -p $(NAS_DIR)/config && rm -rf $(NAS_DIR)/build.neu && mkdir $(NAS_DIR)/build.neu'
	COPYFILE_DISABLE=1 tar $(TAR_EXCLUDES) -czf - $(BUILD_FILES) \
	  | ssh $(NAS) 'tar -xzf - -C $(NAS_DIR)/build.neu && rm -rf $(NAS_DIR)/build && mv $(NAS_DIR)/build.neu $(NAS_DIR)/build'
	@test -f config/people.yaml || { echo "config/people.yaml fehlt: erst \`uv run abend init\`."; exit 1; }
	COPYFILE_DISABLE=1 tar $(TAR_EXCLUDES) -C config/ -cf - . | ssh $(NAS) 'tar -xf - -C $(NAS_DIR)/config'

# Hochladen, dann auf dem NAS bauen und starten; fragt einmal nach dem sudo-Passwort
deploy-nas: upload-nas
	ssh -t $(NAS) 'sudo sh $(NAS_DIR)/build/deploy/nas/up.sh $(NAS_DIR)'

# Einmalig: Datenbank vom Mac aufs NAS übernehmen (bricht ab, wenn dort schon eine liegt)
migrate-db-nas:
	uv run abend backup data/export.sqlite3
	ssh $(NAS) 'mkdir -p $(NAS_DIR)/import && cat > $(NAS_DIR)/import/abendausgabe.sqlite3' < data/export.sqlite3
	rm data/export.sqlite3
	$(MAKE) deploy-nas

logs-nas:
	ssh -t $(NAS) 'cd $(NAS_DIR) && sudo /usr/local/bin/docker compose logs --tail 100 -f app'

# Redaktion auf dem Mac per launchd (16:30, 18:30, 19:40); Einstellungen in .env
AGENT = $(HOME)/Library/LaunchAgents/app.abendausgabe.redaktion.plist
install-redaktion:
	@test -f .env || { echo ".env fehlt: ABEND_SERVER_URL und ABEND_REDAKTION_TOKEN eintragen (.env.example)."; exit 1; }
	mkdir -p data
	sed -e "s|@REPO@|$(CURDIR)|g" -e "s|@UV@|$$(command -v uv)|g" \
	  deploy/launchd/app.abendausgabe.redaktion.plist > $(AGENT)
	launchctl bootout gui/$$(id -u) $(AGENT) 2>/dev/null || true
	launchctl bootstrap gui/$$(id -u) $(AGENT)
	@echo "Redaktion eingerichtet. Sofort testen: launchctl kickstart gui/$$(id -u)/app.abendausgabe.redaktion; Log: data/redaktion.log"

uninstall-redaktion:
	launchctl bootout gui/$$(id -u) $(AGENT) 2>/dev/null || true
	rm -f $(AGENT)
