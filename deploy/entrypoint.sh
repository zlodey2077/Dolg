#!/bin/sh
# DOLG production entrypoint.
# 1. Ждём готовности Postgres (если задан DATABASE_URL — пинг через Django).
# 2. Прогоняем миграции (collectstatic — с ManifestStaticFilesStorage когда DEBUG=False).
# 3. Передаём управление CMD (gunicorn по умолчанию).
#
# `set -e` — любая ошибка останавливает контейнер. Это правильно для prod:
# плохое состояние выявляется при старте, а не silently деградирует.

set -e

if [ -n "$DATABASE_URL" ]; then
    echo "[entrypoint] Жду готовности БД из DATABASE_URL..."
    # Простой ретрай: до 30 попыток с интервалом 1 c (~30 c макс ожидание).
    for i in $(seq 1 30); do
        if python -c "import django; django.setup(); from django.db import connection; connection.ensure_connection()" 2>/dev/null; then
            echo "[entrypoint] БД доступна (попытка $i)."
            break
        fi
        if [ "$i" = "30" ]; then
            echo "[entrypoint] БД не отвечает после 30 c. Прерываю запуск."
            exit 1
        fi
        sleep 1
    done
fi

echo "[entrypoint] Проверяю prod-конфиг..."
# В DEBUG=True команда тихо проходит. В проде — exits 1, если найдены нарушения
# (SECRET_KEY=default, ALLOWED_HOSTS пуст, EMAIL_BACKEND=console, и т.п.).
python manage.py check_prod_settings

echo "[entrypoint] Применяю миграции..."
python manage.py migrate --noinput

echo "[entrypoint] Собираю статику..."
# --clear не используем по умолчанию: rolling-deploy с ManifestStaticFilesStorage
# может временно держать ссылки на старые хеш-имена. Чтобы насильно очистить —
# задайте COLLECTSTATIC_CLEAR=1 (например, при первом deploy).
if [ "$COLLECTSTATIC_CLEAR" = "1" ]; then
    python manage.py collectstatic --noinput --clear
else
    python manage.py collectstatic --noinput
fi

# Опционально создаём superuser-а из ENV-vars (для свежей БД в проде).
# Безопасно: если уже существует — пропускаем.
# КРИТИЧНО: значения env-vars читаем ИЗНУТРИ Python через os.environ.
# Прежняя версия интерполировала их прямо в исходник через '$VAR' — это
# давало shell-injection, если username содержал ' или ); RCE c правами
# контейнерного юзера. См. AUDIT_REPORT_2026-05-10_round2.md A1.
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "[entrypoint] Проверяю/создаю superuser-а..."
    python manage.py shell -c "
import os
from django.contrib.auth import get_user_model
U = get_user_model()
username = os.environ['DJANGO_SUPERUSER_USERNAME']
if not U.objects.filter(username=username).exists():
    U.objects.create_superuser(
        username,
        os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@dolg.local'),
        os.environ['DJANGO_SUPERUSER_PASSWORD'],
    )
    print('superuser', username, 'создан')
else:
    print('superuser', username, 'уже есть')
"
fi

echo "[entrypoint] Старт: $@"
exec "$@"
