# DOLG Deployment Guide

2026-06-01 — настройка облачного бэкапа и production-деплоя.

## Слои защиты от потери данных

| Слой | Частота | Куда | Защита от |
|------|---------|------|-----------|
| 1. **GitHub** | при каждом `git push` | `github.com/zlodey2077/Dolg` (private) | потеря локального диска |
| 2. **hourly-snapshot.bat** | каждый час | OneDrive / `backups/` | потеря между push'ами |
| 3. **Яндекс Compute Cloud** | по `./yc-update.sh` после push | `http://<VM-IP>/` | возможность работать без локалки |
| 4. **GitHub Actions** | каждый push/PR | CI отчёт | поломка кода |

**Production deployment**: см. отдельный гайд [YC_DEPLOY.md](YC_DEPLOY.md) — пошагово
от создания VM до HTTPS-домена.

---

## 1. GitHub repo

### Создать (один раз)

1. Зайти на https://github.com/new
2. Repository name: `dolg` (или другое)
3. Privacy: **Private** (диплом — не публичный)
4. **НЕ** добавлять README/.gitignore/license (у нас уже есть)
5. Create repository

### Подключить и push

```bash
git remote add origin https://github.com/<user>/dolg.git
git branch -M main
git push -u origin main
```

После этого каждый коммит:
```bash
git add .
git commit -m "feat: ..."
git push
```

---

## 2. Render.com web service

Render — бесплатный PaaS для Django (free tier: 512MB RAM, спит после 15 мин неактивности).

### Через render.yaml (рекомендуется)

В корне есть `render.yaml` — Blueprint. Шаги:

1. Зайти на https://dashboard.render.com/blueprints
2. **New Blueprint Instance** → выбрать GitHub репо `dolg`
3. Render автоматически прочитает `render.yaml` и создаст:
   - **dolg** (web-service, Python)
   - **dolg-db** (PostgreSQL free)
4. **Environment Variables** (в dashboard добавить вручную):
   - `HF_TOKEN` — для импорта датасетов
   - `STRIPE_PUBLIC_KEY` / `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET`
   - `ANTHROPIC_API_KEY` (опционально для AI)
   - `SENTRY_DSN` (опционально)
5. **Manual Deploy** → выбрать ветку → Deploy

### Что Render делает автоматически:
- `./build.sh` → `pip install` + `collectstatic` + `migrate`
- `daphne -b 0.0.0.0 -p $PORT Dolg_PR.asgi:application` → запуск ASGI
- `DATABASE_URL` инжектится в env
- `SECRET_KEY` генерируется первым деплоем
- HTTPS включается автоматически

### URL после деплоя
- Web: `https://dolg-XXXX.onrender.com`
- Admin: `https://dolg-XXXX.onrender.com/admin/`
- Создать superuser: Render Dashboard → **Shell** → `python manage.py createsuperuser`

### Free tier ограничения
- Засыпание после 15 мин (первый запрос будет ~30 сек)
- 512 MB RAM (Pixi.js + Three.js на клиенте, на сервере OK)
- БД 90 дней TTL потом удаляется (перенести на платный или backup)

---

## 3. hourly-snapshot (Windows Task Scheduler)

Защита между `git push`'ами — каждый час tar.gz в OneDrive.

### Настройка

```cmd
schtasks /create /sc hourly /tn "DOLG hourly backup" ^
    /tr "C:\Users\spieh\Desktop\DOLG_Diploma\scripts\hourly-snapshot.bat" ^
    /st 00:00
```

После этого:
- Каждый час `dolg-YYYY-MM-DD_HH-MM.tar.gz` сохраняется в `%USERPROFILE%\OneDrive\DOLG-backups\`
- Если OneDrive не настроен — fallback на `backups/` локально
- Старые архивы (>24ч) автоудаляются

### Проверка
```cmd
schtasks /query /tn "DOLG hourly backup"
```

### Удалить
```cmd
schtasks /delete /tn "DOLG hourly backup" /f
```

### Восстановление из снапшота
```cmd
mkdir restored-project
cd restored-project
tar -xzf "%USERPROFILE%\OneDrive\DOLG-backups\dolg-2026-06-01_14-00.tar.gz"
```

---

## 4. GitHub Actions CI

Уже работает: `.github/workflows/django.yml`.

При каждом push в любую ветку:
- **lint**: ruff check + format check
- **security**: pip-audit (CVE сканер)
- **test**: 263+ pytest на coverage ≥ 40%

PR не сольётся если CI красный (настраивается в branch protection rules GitHub).

---

## 5. Перед production-деплоем

### Чек-лист

- [ ] `DEBUG=False` в Render env
- [ ] `SECRET_KEY` — сгенерирован Render (auto)
- [ ] `ALLOWED_HOSTS` — `.onrender.com` + кастомный домен
- [ ] PostgreSQL подключён через `DATABASE_URL`
- [ ] `python manage.py check_prod_settings` — проходит
- [ ] Migrate отработал в `release:` фазе Procfile
- [ ] Static собран (`collectstatic` в build.sh)
- [ ] HTTPS работает (auto-Render)
- [ ] Stripe ключи production (sk_live_ а не sk_test_)
- [ ] Superuser создан через `Render Shell`
- [ ] Sentry DSN добавлен в env

### Тестирование локально с production-конфигом

```cmd
set DEBUG=False
set DATABASE_URL=postgres://...
set SECRET_KEY=...
python manage.py check_prod_settings
python manage.py collectstatic --no-input
daphne -b 0.0.0.0 -p 8000 Dolg_PR.asgi:application
```

---

## 6. Восстановление при крахе

### Локальный диск умер

1. Установить Python 3.13 + Git на новой машине
2. `git clone https://github.com/<user>/dolg.git`
3. `python -m venv .venv && .venv\Scripts\activate`
4. `pip install -r requirements.txt`
5. Создать `.env` из `.env.example`
6. `python manage.py migrate`
7. `python manage.py runserver` — должен работать

### GitHub репо потерян (например, аккаунт заблокирован)

1. Скачать последний snapshot из OneDrive
2. Распаковать в новую папку
3. `git init && git add . && git commit -m "restore"`
4. Создать новый GitHub репо, push

### Render упал

Render-данные backup'ятся автоматически (free tier — 7 дней). Для долгосрочного:
- Запустить cron job в Render: `pg_dump $DATABASE_URL > /tmp/backup.sql && curl --upload-file /tmp/backup.sql 'https://...'`

---

## Связано

- `deploy/nginx.conf` закрывает публичные `/metrics` и `/metrics/` через `403`. Prometheus должен собирать метрики напрямую с `web:8000/metrics/` внутри Docker network, как описано в `deploy/prometheus.yml`.
- Для production-мониторинга `/staff/ops/` использует `Dolg_APP/services/ops_metrics.py` и `psutil`: перед деплоем убедитесь, что `psutil==7.2.2` установлен из `requirements.txt` / `requirements-prod.txt`.
- `render.yaml` — Blueprint конфиг
- `Procfile` — запуск web/release
- `build.sh` — сборка на Render
- `runtime.txt` — Python версия
- `scripts/hourly-snapshot.bat` — локальный бэкап
- `.github/workflows/django.yml` — CI
- `.env.example` — шаблон env-vars
