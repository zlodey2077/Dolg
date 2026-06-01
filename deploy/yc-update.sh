#!/usr/bin/env bash
# DOLG update — git pull + rebuild + zero-downtime restart на YC VM.
# Запускать из /opt/dolg/

set -euo pipefail
PROJECT_DIR="${PROJECT_DIR:-/opt/dolg}"
cd "$PROJECT_DIR"

log() { printf "\n\033[1;36m▶ %s\033[0m\n" "$*"; }

log "[1/4] git pull"
git pull --rebase

log "[2/4] Сборка образа web (cached layers где возможно)"
sudo docker compose -f deploy/docker-compose.yml --env-file .env build web

log "[3/4] Запуск миграций"
sudo docker compose -f deploy/docker-compose.yml --env-file .env run --rm web python manage.py migrate --no-input

log "[4/4] Restart web (zero-downtime через --no-deps + up -d)"
sudo docker compose -f deploy/docker-compose.yml --env-file .env up -d --no-deps web

echo
log "✓ Обновление готово"
docker ps --filter "name=dolg_" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
