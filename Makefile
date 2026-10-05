# Z6III AI Studio — common tasks.
#   Deployment targets wrap `docker compose` (run them next to compose.yaml).
#   Development targets use a local Python venv + npm (see README "Development").

SHELL   := /bin/bash
COMPOSE ?= docker compose
PYTHON  ?= python3
VENV    ?= .venv
NPM     ?= npm
BACKUP_DIR ?= ./backups

BE  := backend
FE  := frontend
VPY := $(abspath $(BE)/$(VENV))/bin/python
CLI := $(COMPOSE) exec backend python -m app.cli

.DEFAULT_GOAL := help
.PHONY: help env config build pull up down restart ps logs logs-% health \
        migrate scan rescan rebuild-thumbnails reanalyze verify-files stats shell psql \
        backup-db restore-db \
        dev-install lint lint-backend lint-frontend typecheck format test test-backend \
        test-frontend build-frontend check samples

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z0-9_%-]+:.*?## / {printf "  \033[33m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---------------------------------------------------------------- deployment

env: ## Create .env from .env.example (never overwrites)
	@if [ -f .env ]; then echo ".env already exists — leaving it alone"; \
	else cp .env.example .env && echo "Created .env — edit POSTGRES_PASSWORD and paths before 'make up'"; fi

config: ## Validate compose.yaml + .env
	$(COMPOSE) config --quiet && echo "compose config OK"

build: ## Build backend + frontend images
	$(COMPOSE) build

pull: ## Pull postgres/redis base images
	$(COMPOSE) pull postgres redis

up: ## Start (or update) the stack in the background
	$(COMPOSE) up -d --build

down: ## Stop the stack (data in APP_DATA_DIR is kept)
	$(COMPOSE) down

restart: ## Restart app containers (not postgres/redis)
	$(COMPOSE) restart backend worker watcher frontend

ps: ## Container status + health
	$(COMPOSE) ps

logs: ## Follow logs of all services
	$(COMPOSE) logs -f --tail=200

logs-%: ## Follow one service, e.g. make logs-worker
	$(COMPOSE) logs -f --tail=200 $*

health: ## Print backend /health
	@$(COMPOSE) exec backend curl -fsS http://localhost:8000/health | $(PYTHON) -m json.tool

migrate: ## Apply database migrations (also runs automatically on backend start)
	$(COMPOSE) exec backend alembic upgrade head

scan: ## Queue an import/reconcile of all existing files (ARGS="--inline" or "--force")
	$(CLI) scan $(ARGS)

rescan: ## Queue a background rescan via the worker
	$(COMPOSE) exec backend curl -fsS -X POST http://localhost:8000/api/v1/system/rescan \
	  $${API_TOKEN:+-H "Authorization: Bearer $$API_TOKEN"}

rebuild-thumbnails: ## Regenerate stale previews/thumbnails (ARGS=--all for every photo)
	$(CLI) rebuild-thumbnails $(ARGS)

reanalyze: ## Re-run technical analysis (ARGS="--ai" to include AI critique)
	$(CLI) reanalyze $(ARGS)

verify-files: ## Check every tracked original still exists (never deletes)
	$(CLI) verify-files

stats: ## Print library statistics
	$(CLI) stats

shell: ## Shell inside the backend container
	$(COMPOSE) exec backend /bin/sh

psql: ## psql inside the postgres container
	$(COMPOSE) exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

backup-db: ## pg_dump the app database to $(BACKUP_DIR)
	@mkdir -p $(BACKUP_DIR)
	$(COMPOSE) exec -T postgres sh -c 'pg_dump -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -Fc' \
	  > $(BACKUP_DIR)/z6iii-$$(date +%Y%m%d-%H%M%S).dump
	@ls -lh $(BACKUP_DIR) | tail -n 3

restore-db: ## Restore a dump: make restore-db FILE=backups/z6iii-....dump
	@test -n "$(FILE)" || (echo "usage: make restore-db FILE=path/to/dump" && exit 1)
	$(COMPOSE) stop backend worker watcher
	$(COMPOSE) exec -T postgres sh -c 'pg_restore -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" --clean --if-exists' < $(FILE)
	$(COMPOSE) start backend worker watcher

# --------------------------------------------------------------- development

dev-install: ## Create backend venv + install frontend deps
	cd $(BE) && $(PYTHON) -m venv $(VENV) && $(VPY) -m pip install -U pip && $(VPY) -m pip install -r requirements-dev.txt
	cd $(FE) && $(NPM) ci

lint: lint-backend lint-frontend ## Lint everything

lint-backend:
	cd $(BE) && $(VPY) -m ruff check app tests && $(VPY) -m ruff format --check app tests

lint-frontend:
	cd $(FE) && $(NPM) run -s lint && npx prettier --check src

typecheck: ## TypeScript typecheck
	cd $(FE) && $(NPM) run -s typecheck

format: ## Auto-format backend + frontend
	cd $(BE) && $(VPY) -m ruff check --fix app tests && $(VPY) -m ruff format app tests
	cd $(FE) && $(NPM) run -s format

test: test-backend test-frontend ## Run all tests

test-backend: ## pytest (SQLite + fakeredis; set TEST_DATABASE_URL for Postgres)
	cd $(BE) && $(VPY) -m pytest -q

test-frontend: ## vitest component + proxy tests
	cd $(FE) && $(NPM) test -s

build-frontend: ## Production Next.js build
	cd $(FE) && $(NPM) run -s build

check: lint typecheck test build-frontend ## Everything CI would run

samples: ## Write synthetic captures into ./samples for local demos
	cd $(BE) && $(VPY) -m app.cli generate-samples ../samples
