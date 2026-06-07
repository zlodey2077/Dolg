# Audit 2026-05-31: tokens, Grafana, ML/dataset progress

## Scope

Проверены:

- Enterprise API tokens: `OrganizationApiToken`, `/orgs/<slug>/api-tokens/`.
- ML admin: `/staff/ml-training/`, training/import background flow.
- Dataset import: `import_external_datasets`, `train_tiny_circuit_ai`, tiny PyTorch backend.
- Observability: `django-prometheus`, `/metrics/`, `deploy/prometheus.yml`, `deploy/grafana/dashboards/dolg_overview.json`.

## Critical Findings

### AUD-ML-001: organization API tokens are stored in plaintext

Файлы:

- `Dolg_APP/models.py`: `OrganizationApiToken.token`
- `Dolg_APP/org_views.py`: `org_api_token_create`
- `Dolg_APP/templates/orgs/api_tokens.html`

Сейчас полный токен сохраняется в БД как `token = models.CharField(...)`.
При компрометации БД или доступе staff к модели токен можно использовать напрямую.
Правильная схема: показывать raw token только один раз, хранить только hash, prefix и last4.

План исправления:

- заменить поле `token` на `token_hash`, `token_prefix`, `token_last4`;
- hash: `sha256(server_pepper + raw_token)`;
- проверка через `secrets.compare_digest`;
- миграция: старые plaintext токены пометить revoked/rotate-required;
- в admin показывать только prefix/last4/status.

### AUD-ML-002: token feature exists as UI, but no API-token authentication layer found

Файлы:

- `Dolg_APP/models.py`: `OrganizationApiToken`
- `Dolg_APP/org_views.py`: create/revoke UI
- `Dolg_APP/urls.py`: no `/api/v1/...` token-auth endpoints found in current route list

Токены создаются, revoke работает, но в найденном коде нет middleware/auth backend,
который читает `Authorization: Bearer dolg_xxx`, проверяет scope и обновляет `last_used_at`.
Это делает фичу демо-оберткой, а не рабочей интеграцией.

План исправления:

- добавить `services/api_tokens.py`;
- добавить decorator/middleware для token-auth endpoints;
- scope checks: `projects.read`, `projects.write`, `bom.read`;
- писать `last_used_at`, audit event и Prometheus counter.

### AUD-ML-003: `/metrics/` is proxied publicly by nginx

Файлы:

- `Dolg_PR/urls.py`: `include('django_prometheus.urls')`
- `deploy/nginx.conf`: `location / { proxy_pass http://dolg_web; }`
- `deploy/prometheus.yml`: scrape `/metrics/`

Если Django опубликован через nginx/tunnel, `/metrics/` тоже становится публичным.
Метрики могут раскрывать view names, rate, latency, status codes and DB activity.

План исправления:

- закрыть `/metrics/` на nginx: allow internal docker subnet or deny all;
- отдельный internal metrics endpoint/token;
- Prometheus должен ходить напрямую к `web:8000` внутри Docker network;
- добавить smoke-check, что публичный `/metrics/` закрыт.

## High Findings

### AUD-ML-004: ML training/import runs inside gunicorn worker threads

Файлы:

- `Dolg_APP/ml_admin_views.py`: `_train_in_background`, `_import_in_background`
- `deploy/Dockerfile`: gunicorn `--workers 3 --timeout 60`

Training/import запускаются через `threading.Thread(..., daemon=True)` внутри web worker.
Если worker перезапустится, процесс потеряется. При нескольких worker прогресс и lock
могут оказаться в другом процессе. Это объясняет эффект "зависло и ничего не делает".

План исправления:

- вынести long-running jobs в отдельный process/management command runner;
- минимальный V1: `MLJob` model + subprocess + polling DB status;
- правильный V2: Celery/RQ/Django-Q + Redis;
- web request только создает job, worker выполняет.

### AUD-ML-005: default cache is not shared across gunicorn workers

Файлы:

- `Dolg_PR/settings.py`: no `CACHES` config found
- `Dolg_APP/ml_admin_views.py`: locks/progress stored in Django cache

Без явного `CACHES` Django использует local memory cache per process.
При `gunicorn --workers 3` lock/progress не являются глобальными.
Страница может стартовать job в worker A, а `/status/` попасть в worker B и увидеть `idle`.

План исправления:

- для progress/locks использовать DB model или Redis cache;
- до Redis лучше хранить `MLJob` в Postgres;
- добавить heartbeat `updated_at` и stale detector.

### AUD-ML-006: dataset list page loads entire JSON datasets to count schemes

Файлы:

- `Dolg_APP/ml_admin_views.py`: `_count_schemes_in_json`, `_collect_datasets`

Каждый заход на `/staff/ml-training/` делает `json.loads(path.read_text(...))`
для каждого dataset JSON. После импорта external dataset это может быть десятки/сотни МБ
и сама админ-страница будет "зависать".

План исправления:

- хранить sidecar metadata `.meta.json` при импорте;
- для больших JSON не читать весь файл на page load;
- считать только size/mtime + cached count;
- вынести recount в отдельную команду.

### AUD-ML-007: DB stats scan all `AITrainingExample.features`

Файлы:

- `Dolg_APP/ml_admin_views.py`: `_count_db_examples`

Админ-страница проходит по всем `AITrainingExample.objects.all().only('features')`
и читает JSON features в Python. На тысячах записей это станет медленно.

План исправления:

- добавить поле `evidence_kind` в модель или денормализованный индекс;
- минимум: cache stats на 30-60 секунд;
- использовать aggregation по `kind/is_validated`, а не Python scan JSON.

### AUD-ML-008: import persist path appears broken against `AITrainingExample` model

Файлы:

- `Dolg_APP/management/commands/import_external_datasets.py`: `_persist_to_db`
- `Dolg_APP/models.py`: `AITrainingExample`

`_persist_to_db` вызывает `AITrainingExample.objects.update_or_create(name=...)`,
но у модели нет поля `name`, зато обязательны `kind`, `prompt`, `target`.
Исключение ловится и печатается как warning, поэтому UI может показать "import done",
но в БД фактически ничего не добавится.

План исправления:

- исправить mapping: `kind='review_hint'` or `artifact_summary`;
- заполнить `prompt`, `target`, `features`;
- добавить unique key через checksum/source id, не через отсутствующее `name`;
- в progress возвращать `persisted_count`.

### AUD-ML-009: template injects Python dict into JavaScript instead of JSON

Файл:

- `Dolg_APP/templates/admin/ml_training.html`: `updateProgress({{ progress|safe|default:"null" }})`

Если progress содержит `None`, `True`, кавычки или traceback, прямой Python repr
может сломать JS. Использовать `json_script` или `|json_script`.

План исправления:

- `{{ progress|json_script:"ml-progress-initial" }}`;
- JS читает `JSON.parse(...)`;
- не выводить traceback в DOM по умолчанию.

## Grafana Gap

Сейчас есть Grafana + Prometheus provisioning:

- `deploy/prometheus.yml`
- `deploy/grafana/provisioning/...`
- `deploy/grafana/dashboards/dolg_overview.json`

Но dashboard покрывает только generic Django:

- requests/sec;
- 5xx;
- p50/p95/p99 latency;
- status codes;
- SQL queries;
- model mutations.

Не хватает доменных метрик:

- admin actions;
- API token created/revoked/used/failed;
- moderation reports/cases/actions;
- ML training jobs, epochs, loss, duration, result;
- dataset import progress, downloaded bytes, imported/skipped/persisted;
- AI requests, token usage, backend mode, fallback count, neural deep_hint count;
- Engineering Review score distribution and critical findings count.

## Recommended Fix Order

1. Fix token storage: hash-only + rotate existing tokens.
2. Protect `/metrics/` from public access.
3. Replace ML background threads/cache locks with persistent `MLJob`.
4. Fix dataset page hanging: no full JSON read on page load.
5. Fix broken `_persist_to_db`.
6. Add Prometheus custom metrics service.
7. Extend Grafana dashboard: Admin, ML, AI, Review panels.
8. Add tests: token hash/auth, metrics protection, ML job state, dataset import persist.
