# DOLG — локальная установка

Пошаговая инструкция для нового разработчика. Время на полное поднятие: **~10 минут**.

## Требования

- **Python 3.14** (минимум 3.11)
- **git**
- **2 ГБ свободного места** (зависимости + БД + demo-картинки)
- Опционально: Node.js 20+ (только для TS-frontend разработки)
- Опционально: Docker — для prod-режима

## Windows (быстрый путь)

В корне репо есть два launcher-скрипта:
- `start_local.bat` — локальный запуск на `127.0.0.1:8000` (для своей работы)
- `start_public.bat` — локальный + ngrok tunnel (для защиты / телефона / ревью)

Первый запуск (вручную, один раз):
```cmd
git clone <repo-url> dolg
cd dolg
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py populate_demo_projects
python manage.py createsuperuser
```

После установки — двойной клик на `start_local.bat`:
- проверит что `.venv\Scripts\python.exe` или `python` доступны
- проверит, не занят ли порт 8000 (если занят — просто откроет браузер вместо запуска второго)
- запустит `runserver 127.0.0.1:8000` в отдельном окне
- дождётся HTTP-ответа и откроет браузер на http://127.0.0.1:8000/

## Linux / macOS / Windows-вручную

```bash
git clone <repo-url> dolg
cd dolg

# venv
python3.14 -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows PowerShell

pip install -r requirements.txt

# Конфиг
cp .env.example .env
# Открыть .env, при необходимости поменять SECRET_KEY и ANTHROPIC_API_KEY

# Миграции (SQLite, появится db.sqlite3)
python manage.py migrate

# Создаём суперюзера для админки
python manage.py createsuperuser

# Загружаем demo-схемы (опционально, для проверки симулятора)
python manage.py populate_demo_projects --owner=<your-username>

# Старт
python manage.py runserver
```

Открой http://localhost:8000 — должна загрузиться главная.

## Что попробовать сразу

1. http://localhost:8000/ → каталог товаров
2. http://localhost:8000/tools/simulation/ → симулятор (демо-режим без логина)
3. http://localhost:8000/projects/ → список проектов (требует логина)
4. http://localhost:8000/admin/ → Django admin

## Тесты

```bash
# Все тесты с быстрым режимом (пропуск миграций — ~2 минуты)
FAST_TESTS=1 python manage.py test

# Только конкретный app
python manage.py test shop
python manage.py test Dolg_APP

# Coverage отчёт
pip install coverage
coverage run manage.py test
coverage report -m
coverage html       # → htmlcov/index.html
```

## Линтер

```bash
pip install ruff
ruff check .                    # найти проблемы
ruff check --fix .              # авто-исправить (~109 фиксов было найдено)
ruff format .                   # автоформат как у black

# Или через pre-commit (рекомендуется):
pip install pre-commit
pre-commit install              # хук при каждом commit
pre-commit run --all-files      # прогнать сразу всё
```

## Docker (prod-режим локально)

```bash
cp .env.example .env
# Отредактируй .env:
#   DEBUG=False
#   SECRET_KEY=<уникальный, не дефолт>
#   POSTGRES_DB=dolg, POSTGRES_USER=dolg, POSTGRES_PASSWORD=...

docker compose up -d
docker compose logs -f web

# Открой http://localhost (порт 80 → nginx → gunicorn)
```

Полная документация по prod-деплою — [DEPLOY.md](DEPLOY.md).

## PostgreSQL для локальной разработки

По умолчанию локальный Django использует SQLite (`db.sqlite3`), чтобы проект
стартовал без внешних сервисов. Для проверки будущего production-поведения
можно поднять только PostgreSQL, не запуская весь Docker-стек DOLG:

```powershell
# Создаст deploy/.env.postgres.local и поднимет Postgres на 127.0.0.1:5432
powershell -ExecutionPolicy Bypass -File scripts/postgres_dev.ps1 up

# Показать строку подключения
powershell -ExecutionPolicy Bypass -File scripts/postgres_dev.ps1 url

# Переключить текущую shell-сессию Django на Postgres и применить миграции
$env:DATABASE_URL="postgresql://dolg:<password>@127.0.0.1:5432/dolg"
.\.venv\Scripts\python.exe manage.py migrate
```

Если нужен визуальный SQL-инструмент:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/postgres_dev.ps1 up -WithPgAdmin
```

pgAdmin будет доступен на `http://127.0.0.1:5050/`, пароль лежит в
`deploy/.env.postgres.local`. Остановить контейнеры:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/postgres_dev.ps1 down
```

Удалять volume с данными нужно только осознанно:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/postgres_dev.ps1 down -RemoveVolumes
```

## Структура проекта

```
dolg/
├── Dolg_PR/                # Django project settings
│   ├── settings.py
│   ├── settings_prod.py
│   └── urls.py
├── Dolg_APP/               # Симулятор + CAD + AI (ядро)
│   ├── views.py
│   ├── ai_assistant.py
│   ├── pcb_layout.py
│   ├── models.py
│   ├── templates/tools/
│   │   ├── simulation.html
│   │   ├── cad.html
│   │   └── projects.html
│   └── management/commands/
│       ├── populate_demo_projects.py
│       └── check_prod_settings.py
├── shop/                   # E-commerce
├── accounts/               # Auth / профиль
├── orders/                 # Заказы
├── knowledge/              # Туториалы
├── docs/                   # Документация
│   ├── ARCHITECTURE.md
│   ├── DEPLOY.md
│   ├── PROJECT_KNOWLEDGE_BASE.md
│   ├── RUNBOOK.md
│   └── LOCAL_SETUP.md (это)
├── scripts/                # Утилиты
│   ├── bootstrap_docker_desktop.ps1
│   ├── docker_compose_up.ps1
│   ├── docker_compose_down.ps1
│   ├── check_docker_static.py
│   └── check_k8s_static.py
├── shop/static/            # CSS, JS, картинки
├── manage.py
├── requirements.txt
├── pyproject.toml          # ruff config
├── .pre-commit-config.yaml
└── .env.example
```

## Частые ошибки

### `ModuleNotFoundError: No module named 'Django'`
Не активирован venv. На Windows:
```cmd
.venv\Scripts\activate
```

### `OperationalError: no such table`
Не применены миграции:
```bash
python manage.py migrate
```

### `CommandError: You have X unapplied migration(s)`
То же — `python manage.py migrate`. Если миграции конфликтуют (после `git pull`), сначала backup БД, потом `python manage.py migrate --fake-initial`.

### `psycopg2.OperationalError: connection refused`
Активирован Postgres-конфиг, но контейнер не запущен. Либо:
- закомментируй `DATABASE_URL` в `.env` (вернёт SQLite),
- либо `docker compose up -d db`.

### Тесты в WSL/Docker очень медленные
Используй `FAST_TESTS=1`:
```bash
FAST_TESTS=1 python manage.py test
```
Это отключает миграции — Django создаёт схему напрямую из моделей (на порядок быстрее).

### `Did you remember to install all the dependencies?`
Возможно, requirements обновились:
```bash
pip install -r requirements.txt --upgrade
```

## Полезные команды

```bash
# Очистить и пере-создать БД (DEV ONLY!)
rm db.sqlite3
python manage.py migrate

# Django shell
python manage.py shell

# Создать миграцию после изменения моделей
python manage.py makemigrations

# Посмотреть SQL миграции
python manage.py sqlmigrate Dolg_APP 0001

# Сбросить демо-проекты
python manage.py populate_demo_projects --reset

# Проверить prod-конфиг локально
DEBUG=False SECRET_KEY=secret123 python manage.py check_prod_settings
```

## Что почитать дальше

- [ARCHITECTURE.md](ARCHITECTURE.md) — карта системы
- [DEPLOY.md](DEPLOY.md) — prod-деплой через Docker + Cloudflare
- [RUNBOOK.md](RUNBOOK.md) — что делать если что-то сломалось
- `pyproject.toml` — конфиг линтера
