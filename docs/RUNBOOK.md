# DOLG Operations Runbook

Что делать, когда что-то сломалось в проде. Каждый сценарий — изолированный,
содержит проверку гипотезы, шаги восстановления и проверку «как понять, что
починилось».

## Содержание
- [Сайт недоступен (502/503)](#сайт-недоступен-502503)
- [База данных не отвечает](#база-данных-не-отвечает)
- [Миграция зависла или упала](#миграция-зависла-или-упала)
- [Восстановление БД из бэкапа](#восстановление-бд-из-бэкапа)
- [Закончилось место на диске](#закончилось-место-на-диске)
- [AI-ассистент возвращает 5xx](#ai-ассистент-возвращает-5xx)
- [Публичный Cloudflare-туннель оборвался](#публичный-cloudflare-туннель-оборвался)
- [Подозрение на ddos / spam-регистрации](#подозрение-на-ddos--spam-регистрации)

---

## Сайт недоступен (502/503)

**Проверь сначала:**
```bash
docker compose ps                          # все контейнеры Up?
docker compose logs --tail=50 web          # есть свежие ошибки?
curl -sS http://localhost/healthz/         # 200 OK?
```

**Сценарии:**

### web-контейнер упал
```bash
docker compose logs --tail=200 web > /tmp/dolg-web.log
docker compose restart web
sleep 5
docker compose ps
curl -sS http://localhost/healthz/
```
Если опять упал — смотри `/tmp/dolg-web.log` на исключение/traceback. Чаще всего:
- невалидный `SECRET_KEY` → `python manage.py check_prod_settings` подскажет
- БД недоступна → см. ниже
- collectstatic упал на dirty staticfiles → `COLLECTSTATIC_CLEAR=1 docker compose up -d web`

### nginx не пускает
```bash
docker compose logs nginx | tail -20
```
Чаще: web не отвечает upstream → перезапусти web (см. выше).

---

## База данных не отвечает

```bash
docker compose exec db pg_isready -U postgres
# Если "no response" — контейнер живой, но БД не принимает соединения
```

**Сценарии:**

### Postgres OOM-killed
```bash
docker compose logs db | grep -i 'killed\|oom'
free -h                  # сколько свободной памяти на хосте?
```
Если хост на пределе — увеличь swap или подними машину. Перезапуск:
```bash
docker compose restart db
sleep 10
docker compose exec db pg_isready -U postgres
```

### Volume повредился
Симптом: Postgres логирует «database files are incompatible» или «could not open file».
```bash
docker compose stop web
# Восстанавливаем из бэкапа — см. ниже
```

---

## Миграция зависла или упала

**Если ВО ВРЕМЯ старта** (entrypoint застрял на `python manage.py migrate`):
```bash
docker compose logs web | tail -50    # на каком файле?
# Прерви старт:
docker compose stop web
```

Зайди в БД руками:
```bash
docker compose exec db psql -U postgres -d "$POSTGRES_DB"
\dt                            # какие таблицы есть?
SELECT * FROM django_migrations ORDER BY id DESC LIMIT 10;
```

**Откат миграции вручную:**
```bash
# Узнаём предыдущую миграцию приложения:
docker compose run --rm web python manage.py showmigrations Dolg_APP
# Откат на конкретную:
docker compose run --rm web python manage.py migrate Dolg_APP 0008_previous
# Если откат не предусмотрен — придётся восстанавливать из бэкапа.
```

**Профилактика на будущее:** добавь миграцию-сэйфти-чек:
```bash
# Перед merge PR с миграцией:
docker compose run --rm web python manage.py migrate --plan
docker compose run --rm web python manage.py sqlmigrate Dolg_APP 0042
```

---

## Восстановление БД из бэкапа

### Локальный SQLite-режим дипломной демонстрации

```powershell
# Создать резервную копию текущей БД
powershell -ExecutionPolicy Bypass -File .\scripts\backup_db.ps1

# Восстановить вручную из нужной копии
Copy-Item -LiteralPath .\backups\db_sqlite_YYYYMMDD_HHMMSS.sqlite3 -Destination .\db.sqlite3 -Force

# Проверить данные после восстановления
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py check_data_integrity --json
```

Если нужно пересобрать демонстрационные данные после восстановления:

```powershell
.\.venv\Scripts\python.exe manage.py apply_curated_product_photos
.\.venv\Scripts\python.exe manage.py populate_knowledge
.\.venv\Scripts\python.exe manage.py populate_demo_projects
.\.venv\Scripts\python.exe manage.py check_demo_ready --json
```

Если товарные изображения не открываются в локальном демо при `DEBUG=False`, проверьте, что не выставлен `SERVE_MEDIA=0`. По умолчанию DOLG держит `SERVE_MEDIA=1` и сам отдаёт `/media/products/generated/*.png`; в docker/nginx `/media/` обслуживается nginx.

```bash
# 1. Стопаем web — никто не пишет в БД
docker compose stop web

# 2. Дропаем испорченную БД
docker compose exec db psql -U postgres -c "DROP DATABASE IF EXISTS $POSTGRES_DB;"
docker compose exec db psql -U postgres -c "CREATE DATABASE $POSTGRES_DB;"

# 3. Восстанавливаем из последнего бэкапа
ls -lh backups/dolg_*.sql.gz | tail -5      # какой выбрать?
gunzip -c backups/dolg_20260515_040000.sql.gz | \
    docker compose exec -T db psql -U postgres "$POSTGRES_DB"

# 4. Проверка
docker compose exec db psql -U postgres "$POSTGRES_DB" -c "SELECT count(*) FROM auth_user;"

# 5. Поднимаем web
docker compose up -d web
sleep 5
curl -sS http://localhost/healthz/
```

**Контроль потерь:** между временем последнего бэкапа и моментом падения данные потеряны. Если есть WAL-архивы Postgres — можно сделать point-in-time recovery (но это уже не runbook, а DR-план).

---

## Закончилось место на диске

```bash
df -h
docker system df               # сколько места занимает Docker?
du -sh ./backups               # старые бэкапы накопились?
docker compose logs db | wc -l # лог db переполнился?
```

**Очистка по приоритету (от самого безопасного):**
```bash
# 1. Дроп старых docker-образов (НЕ затрагивает данные):
docker image prune -a -f

# 2. Дроп старых бэкапов (если retention сработал):
find ./backups -name 'dolg_*.sql.gz' -mtime +30 -delete

# 3. Чистим логи (хостовые ротации не настроены):
truncate -s 0 $(docker inspect --format='{{.LogPath}}' $(docker compose ps -q web))
```

**Профилактика:** в `docker-compose.yml` поставь `logging.options.max-size=10m, max-file=3`.

---

## AI-ассистент возвращает 5xx

```bash
# Проверь, что ANTHROPIC_API_KEY задан:
docker compose exec web env | grep ANTHROPIC

# Логи AI-вызовов:
docker compose logs web | grep -i 'ai_assistant\|anthropic\|claude'
```

**Возможные причины:**

| Симптом в логах | Что делать |
|---|---|
| `Ollama unavailable` / timeout | Проверь, запущен ли Ollama: `ollama list` и `OLLAMA_BASE_URL=http://127.0.0.1:11434` |
| `local_ai` ушёл в fallback | Это безопасно: сайт отвечает rule-based подсказками без внешнего API |
| PyTorch model missing | Проверь `media/ml/tiny_circuit_ai.pt` или запусти rule-based режим |
| Нет логов вообще | Локальный AI не вызывается для этого сценария или используется кэш/fallback |

**Временно отключить live-AI** (если он сыпет ошибками всем):
```bash
docker compose exec web sh -c 'export OLLAMA_BASE_URL='
docker compose restart web
# UI останется на rule-based fallback без внешних запросов
```

---

## Публичный Cloudflare-туннель оборвался

Симптом: публичная ссылка `https://...trycloudflare.com` отдаёт timeout/ошибку, а локально
через `http://127.0.0.1:8000/healthz/` всё работает.

```bash
# Проверь процесс cloudflared
ps aux | grep cloudflared
# или (Windows-host):
Get-Process cloudflared
```

**Перезапуск публичного туннеля (start_public.bat):**
```cmd
taskkill /IM cloudflared.exe /F
.\start_public.bat
```

**Проверка без запуска долгого сервера:**
```cmd
.\.venv\Scripts\python.exe start_public_server.py --check-only
```

---

## Подозрение на DDoS / spam-регистрации

```bash
# Топ-10 IP по запросам за последние 5 минут:
docker compose logs --since=5m nginx | awk '{print $1}' | sort | uniq -c | sort -rn | head -10

# Подсчёт регистраций за час:
docker compose exec db psql -U postgres -d "$POSTGRES_DB" -c \
    "SELECT count(*) FROM auth_user WHERE date_joined > now() - interval '1 hour';"
```

**Меры:**
1. Включи Cloudflare «Under Attack Mode» (5 сек challenge для всех)
2. Забань IP через `iptables`:
   ```bash
   iptables -A INPUT -s 1.2.3.4 -j DROP
   ```
3. Включи реgistration captcha (если не включена)
4. Временно отключи регистрацию: в `accounts/urls.py` закомментируй `register` (если совсем плохо)

---

## Контакты и эскалация

| Что | Куда |
|---|---|
| Sentry alerts | `sentry.io/organizations/dolg/issues/` |
| Cloudflare dashboard | `dash.cloudflare.com` |
| Ollama local status | `http://127.0.0.1:11434/api/tags` |
| Postgres docs | `postgresql.org/docs/15/` |
