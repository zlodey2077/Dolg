#!/bin/sh
# DOLG database backup script (Postgres only, для prod-Docker).
#
# Запускается на хосте, не внутри контейнера. Использует `docker compose exec`
# чтобы взять pg_dump из живого контейнера db. Бэкап сохраняется в ./backups/
# с retention 30 дней (старше — удаляются).
#
# Запуск:
#   ./scripts/backup_db.sh
#
# Cron (daily в 04:00):
#   0 4 * * * cd /opt/dolg && ./scripts/backup_db.sh >> backups/backup.log 2>&1
#
# Проверка восстановления (раз в месяц вручную):
#   gunzip -c backups/dolg_YYYYMMDD_HHMMSS.sql.gz | \
#     docker compose exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB"

set -eu

# Загружаем env (для POSTGRES_DB/USER/PASSWORD)
if [ -f .env ]; then
    set -a
    . ./.env
    set +a
fi

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
STAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT="$BACKUP_DIR/dolg_${STAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

if [ -z "${POSTGRES_DB:-}" ]; then
    echo "[backup] POSTGRES_DB не задан — backup только для prod-конфига"
    exit 1
fi

echo "[backup] Снимаю dump → $OUTPUT"
docker compose exec -T db pg_dump \
    -U "${POSTGRES_USER:-postgres}" \
    -d "$POSTGRES_DB" \
    --no-owner --no-acl \
    | gzip > "$OUTPUT"

SIZE=$(du -h "$OUTPUT" | cut -f1)
echo "[backup] ✓ Сохранено: $OUTPUT ($SIZE)"

# Удаляем старые бэкапы
DELETED=$(find "$BACKUP_DIR" -name 'dolg_*.sql.gz' -mtime "+$RETENTION_DAYS" -print -delete | wc -l)
if [ "$DELETED" -gt 0 ]; then
    echo "[backup] Удалено старых (>${RETENTION_DAYS} дней): $DELETED"
fi

echo "[backup] Всего бэкапов: $(ls -1 "$BACKUP_DIR"/dolg_*.sql.gz 2>/dev/null | wc -l)"
