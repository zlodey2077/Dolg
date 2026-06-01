#!/usr/bin/env bash
# DOLG build script для Render.com
set -o errexit

echo "🔧 [1/4] Установка зависимостей..."
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn whitenoise dj-database-url psycopg2-binary

echo "🎨 [2/4] Сбор статических файлов..."
python manage.py collectstatic --no-input --clear || echo "⚠ collectstatic warning (ok при первом деплое)"

echo "🗄  [3/4] Применение миграций..."
python manage.py migrate --no-input

echo "✅ [4/4] Build готов!"
