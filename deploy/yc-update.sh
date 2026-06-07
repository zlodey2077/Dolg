#!/usr/bin/env bash
# DOLG update for a YC VM: pull, build app images, run release commands once,
# then restart the runtime services.

set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/dolg}"
COMPOSE=(sudo docker compose -f deploy/docker-compose.yml --env-file .env)

cd "$PROJECT_DIR"

log() { printf "\n\033[1;36m> %s\033[0m\n" "$*"; }

log "[1/5] git pull"
git pull --rebase

log "[2/5] build Django images"
"${COMPOSE[@]}" build web asgi worker

log "[3/5] run database migrations once"
"${COMPOSE[@]}" run --rm \
  -e RUN_MIGRATIONS=0 \
  -e RUN_COLLECTSTATIC=0 \
  -e RUN_CREATE_SUPERUSER=0 \
  web python manage.py migrate --no-input

log "[4/5] collect static files once"
"${COMPOSE[@]}" run --rm \
  -e RUN_MIGRATIONS=0 \
  -e RUN_COLLECTSTATIC=0 \
  -e RUN_CREATE_SUPERUSER=0 \
  web python manage.py collectstatic --no-input --verbosity 0

log "[5/5] restart runtime services"
"${COMPOSE[@]}" up -d --no-deps web asgi worker nginx

echo
log "Update complete"
sudo docker ps --filter "name=dolg" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
