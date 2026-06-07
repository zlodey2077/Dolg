# WORKFRONT 2026-06-03: Admin Monitoring Center

## Краткий диагноз

DOLG уже имеет основу наблюдаемости, но она пока разложена по разным местам:

- `/metrics/` подключен через `django-prometheus`;
- `deploy/prometheus.yml` и `deploy/grafana/dashboards/dolg_overview.json` уже поднимают базовый Prometheus/Grafana stack;
- `/healthz/` не ходит в БД и подходит для liveness;
- `/readyz/` проверяет БД, каталог, статьи и demo-проекты;
- `/staff/ops/` показывает счетчики каталога, проектов, review, AITrainingExample, moderation и MLJob;
- отдельные changelist-экраны Django admin уже имеют мини-сводки: `Product`, `Order`, `SchematicProject`, `AITrainingExample`;
- `MLJob` хранит persistent progress, heartbeat, counters, stdout/error tail и статус training/import jobs.

Главный разрыв: нет единого monitoring service-layer, который одинаково питает Django admin, `/staff/ops/`, JSON API и Prometheus/Grafana. Также нет runtime-метрик процесса: память, CPU, диск, размер media/dataset/cache, состояние очередей, stale jobs и алерты.

## Внедрено 2026-06-03: P0/P1 baseline

- `deploy/nginx.conf`: публичные `/metrics` и `/metrics/` закрыты `403`; Prometheus по-прежнему собирает метрики напрямую с `web:8000/metrics/` внутри Docker network.
- `requirements.txt` и `requirements-prod.txt`: добавлен `psutil==7.2.2`.
- `Dolg_APP/services/ops_metrics.py`: общий service-layer для runtime, catalog, business, project, AI/ML, moderation и security metrics.
- `/staff/ops/`: пересобран как читаемый operational dashboard с health status, alerts, runtime, disk, business и AI/ML блоками.
- `GET /staff/ops/api/snapshot/`: staff-only JSON snapshot для live refresh и будущих виджетов.
- `check_demo_ready --json`: добавлен блок `admin_monitoring_stack` с проверкой `psutil`, snapshot sections, staff routes и nginx-защиты `/metrics/`.
- Tests: `Dolg_APP.tests_ml_admin` расширен проверками ops snapshot service и API.

Фактический срез локальной БД на момент аудита:

| Метрика | Значение |
|---|---:|
| Пользователи | 9 |
| Staff | 3 |
| Товары | 364 |
| Категории | 23 |
| Корзина | 6 |
| Заказы | 1 |
| Оплаченные заказы | 0 |
| Проекты | 28 |
| ProjectEvent | 33 |
| ProjectReview | 1 |
| ProjectMeasurement | 0 |
| SimulationRun | 0 |
| AITrainingExample | 72 |
| Валидированные AI examples | 72 |
| EngineeringArtifact | 0 |
| MLJob | 0 |
| DailyUsage за 7 дней | 8 |
| AuditLog за 7 дней | 0 |
| Подписки | 1 |
| Организации | 1 |
| Открытые moderation cases | 0 |

Вывод: каталог, проекты и AI dataset уже можно мониторить полноценно. Заказы, платежи, симуляции, измерения и артефакты пока нужно показывать с graceful-empty состоянием и демо-seed сценариями.

## P0: Безопасность и единый слой метрик

### 1. Защитить `/metrics/`

Проблема уже была зафиксирована в `docs/AUDIT_TOKENS_GRAFANA_ML_20260531.md`: nginx проксирует все запросы в Django, значит `/metrics/` может стать публичным.

Нужно:

- в `deploy/nginx.conf` закрыть `/metrics/` для внешнего доступа;
- разрешить scrape только из внутренней docker-сети или через отдельный internal endpoint;
- оставить Prometheus scrape на `web:8000/metrics/` внутри compose-сети;
- добавить deployment-smoke: публичный `/metrics/` закрыт, внутренний Prometheus scrape работает.

Acceptance:

- снаружи `/metrics/` не отдает Django/prometheus метрики;
- Prometheus продолжает собирать `django_http_*` и `django_db_*`;
- это отражено в `DEPLOY.md` и `RUNBOOK.md`.

### 2. Добавить `psutil` для runtime snapshot

Сейчас `psutil` не установлен, а значит админ не видит память/CPU/потоки/диск из Python-процесса.

Нужно добавить легкую зависимость:

- `psutil` в `requirements.txt` и `requirements-prod.txt`;
- lazy import только в service-layer;
- если `psutil` отсутствует, отдавать `status=unknown`, а не падать.

Runtime metrics V1:

- process RSS/USS memory;
- process CPU percent;
- thread count;
- open files/connections, если доступно на платформе;
- uptime процесса;
- disk usage для корня проекта, `media/`, `staticfiles/`, `Dolg_APP/ml/dataset/`;
- размер dataset cache и количество `.incomplete` файлов;
- размер search index и наличие `.stale`;
- DB ping latency;
- cache read/write smoke.

Acceptance:

- `/staff/ops/` показывает блок `Runtime`;
- отдельный JSON endpoint отдает runtime snapshot;
- тесты проходят без `psutil`, если пакет недоступен.

### 3. Ввести `Dolg_APP/services/ops_metrics.py`

Это главный слой, который убирает дублирование счетчиков из views/admin/templates.

Функции:

- `collect_runtime_metrics()`;
- `collect_business_metrics(period_days=7)`;
- `collect_catalog_metrics()`;
- `collect_project_metrics()`;
- `collect_ai_ml_metrics()`;
- `collect_moderation_metrics()`;
- `collect_security_metrics()`;
- `collect_ops_snapshot()`;
- `classify_ops_health(snapshot)` -> `ok/warn/critical`.

Источники:

- `Product`, `Category`, media quality, datasheet_extracted;
- `Order`, `OrderItem`, `PaymentTransaction`, `CartItem`;
- `DailyUsage`, `Subscription`, `Organization`;
- `SchematicProject`, `ProjectEvent`, `ProjectReview`, `ProjectMeasurement`, `SimulationRun`;
- `AITrainingExample`, `EngineeringArtifact`, `MLJob`;
- `ModerationCase`, `ModerationReport`, `UserRestriction`;
- `AuditLog`, `OrganizationApiToken`.

Acceptance:

- `/staff/ops/` и admin mini-dashboards берут данные из одного сервиса;
- в сервисе есть unit tests на пустую БД и на заполненный демо-набор;
- тяжелые подсчеты кэшируются на 15-60 секунд.

## P1: Staff Admin Monitoring Center

### 4. Расширить `/staff/ops/` до полноценного центра

Текущий `/staff/ops/` полезный, но плоский. Нужно сделать вкладки:

- `Runtime`: память, CPU, uptime, disk, cache, DB latency;
- `Catalog`: товары, РЭБ, datasheet coverage, media quality, stock risks, EOL/NRND;
- `Business`: заказы, выручка, неоплаченные, pending orders, корзины, подписки, trial/pro/enterprise;
- `Projects`: проекты, версии, review, health-score distribution, critical findings, measurements;
- `AI/ML`: AITrainingExample, graph-ready, validation errors, MLJob, stale jobs, failed imports, model status;
- `Moderation`: open cases, reports, restrictions, hidden content;
- `Security`: staff users, API tokens, revoked/active tokens, recent audit events, 2FA policy warnings.

UI:

- сверху общий health badge: `OK / Warning / Critical`;
- карточки с порогами;
- таблица активных проблем: `severity`, `metric`, `value`, `recommendation`;
- кнопки действий: validate dataset, reset stale MLJob, open data-integrity, open demo-ready, open admin list.

Acceptance:

- админ видит “что сломано прямо сейчас” без запуска терминала;
- при пустых данных блок не выглядит сломанным, а показывает “данных пока нет”;
- страница остается staff-only.

### 5. JSON API для live refresh

Добавить:

- `GET /staff/ops/api/snapshot/`;
- `GET /staff/ops/api/runtime/`;
- `GET /staff/ops/api/ml-jobs/`;
- `GET /staff/ops/api/business/`.

Зачем:

- `/staff/ops/` может обновляться без F5;
- ML progress и runtime-memory видно сразу;
- потом этот же endpoint можно использовать для admin widgets.

Acceptance:

- endpoints staff-only;
- возвращают `generated_at`, `status`, `metrics`, `alerts`;
- не раскрывают secrets, tokens, tracebacks обычному staff, если это не superuser.

## P1: Prometheus and Grafana Domain Metrics

### 6. Custom Prometheus metrics

Сейчас Grafana видит generic Django metrics: RPS, 5xx, latency, SQL. Нужно добавить доменные gauges/counters.

Подход:

- отдельный module `Dolg_APP/services/prometheus_metrics.py`;
- использовать `prometheus_client`;
- метрики брать из cached `ops_metrics` snapshot, чтобы scrape не делал тяжелые запросы каждый раз;
- не добавлять labels с высокой кардинальностью: никаких username, email, project name.

Метрики V1:

```text
dolg_products_total
dolg_products_missing_datasheet_total
dolg_products_needing_review_total
dolg_orders_total
dolg_orders_pending_total
dolg_orders_paid_total
dolg_revenue_paid_total
dolg_projects_total
dolg_project_reviews_total
dolg_review_critical_findings_total
dolg_measurements_total
dolg_ai_training_examples_total
dolg_ai_training_graph_ready_total
dolg_ai_training_validation_errors_total
dolg_ml_jobs_total{status,job_type}
dolg_ml_job_active_total
dolg_ml_job_stale_total
dolg_moderation_cases_open_total
dolg_daily_usage_ai_requests_total
dolg_daily_usage_simulations_total
dolg_runtime_memory_rss_bytes
dolg_runtime_cpu_percent
dolg_runtime_disk_used_ratio{area}
```

Acceptance:

- `/metrics/` содержит доменные `dolg_*` метрики;
- Grafana dashboard использует эти метрики;
- tests проверяют наличие ключевых строк в Prometheus output.

### 7. Grafana dashboards

Оставить `dolg_overview.json` как общий Django dashboard и добавить новые:

- `dolg_runtime.json`: memory, CPU, disk, DB latency, cache, process uptime;
- `dolg_business.json`: orders, revenue, subscriptions, carts, user activity;
- `dolg_ai_ml.json`: MLJob progress, stale jobs, import/training duration, dataset quality, model status;
- `dolg_engineering.json`: projects, review health score, critical findings, measurements, simulation runs;
- `dolg_catalog_quality.json`: datasheet coverage, media quality, stock/EOL/data-review.

Для Docker:

- Phase 1: Python runtime metrics через `psutil`;
- Phase 2: добавить `node-exporter` и `cadvisor`, чтобы Grafana видела контейнеры, CPU/RAM/IO на уровне Docker.

Acceptance:

- `docker compose -f deploy/docker-compose.yml up -d` поднимает Grafana с новыми dashboards;
- staff docs объясняют, какие панели показывать на защите;
- нет secrets в dashboard JSON.

## P2: Alerts and Operational Runbook

### 8. Alert rules

Добавить `deploy/prometheus_rules.yml`:

- 5xx rate > threshold;
- p95 latency > threshold;
- memory RSS > threshold;
- disk usage > 85%;
- DB ping latency > threshold;
- `MLJob` running без heartbeat > 120 секунд;
- failed ML imports за последние N минут;
- dataset validation errors > 0;
- catalog missing datasheet/media warnings > 0;
- moderation queue > N;
- pending orders > N часов;
- AI fallback/error rate вырос;
- public metrics endpoint accidentally open.

Acceptance:

- Prometheus загружает rules;
- Grafana показывает alert states;
- `RUNBOOK.md` содержит “что делать при каждом alert”.

### 9. Admin audit trail for monitoring actions

Все ручные действия из monitoring center писать в `AuditLog`:

- reset stale job;
- mark MLJob stale/cancelled/success;
- validate dataset;
- run data integrity;
- run demo-ready;
- rebuild search index;
- enrich datasheets batch;
- export monitoring snapshot.

Acceptance:

- после действия есть `AuditLog`;
- staff видит последние действия в `/staff/ops/`;
- Enterprise org audit остается отдельным, глобальный monitoring audit не смешивается с командным.

## P2: Offline defense and reports

### 10. Monitoring snapshot export

Для диплома и защиты полезен export:

- HTML/JSON snapshot текущего состояния;
- PNG/CSV по ключевым метрикам;
- “состояние демо на дату защиты”: demo-ready/data-integrity, catalog, AI/ML, review, subscriptions, moderation.

Acceptance:

- `/staff/ops/export.json`;
- `/staff/ops/report/` HTML;
- документируем в `DEMO_SCENARIO.md` как показать операционный контроль.

## Что не делать сразу

- Не тащить полноценный ELK/Loki в V1: это отдельный стек логов и он раздут для текущей задачи.
- Не хранить каждую runtime-секунду в БД: историей занимается Prometheus.
- Не делать бизнес-выводы по одному заказу: показывать метрики, но не строить аналитику конверсии без данных.
- Не выводить raw traceback/tokens/secrets в staff UI. Подробный traceback только superuser или sanitized tail.

## Test Plan

- `manage.py check`;
- `makemigrations --check --dry-run`;
- unit tests для `ops_metrics` на пустой и заполненной БД;
- API tests: staff-only, JSON shape, no secrets;
- Prometheus tests: `dolg_*` метрики присутствуют;
- nginx/config smoke: external `/metrics/` закрыт;
- dashboard JSON validation: Grafana dashboards валидный JSON;
- `check_demo_ready --json`: добавить блок `admin_monitoring_stack`;
- `check_data_integrity --json`: проверить, что metrics endpoint не помечен публичным в deploy config.

## Recommended order

1. P0 security: закрыть публичный `/metrics/`.
2. Добавить `psutil` + `ops_metrics.py`.
3. Перевести `/staff/ops/` на общий snapshot и добавить runtime/business tabs.
4. Добавить JSON endpoints для live refresh.
5. Добавить custom `dolg_*` Prometheus metrics.
6. Расширить Grafana dashboards.
7. Добавить alert rules и runbook.
8. Добавить export snapshot для диплома/защиты.
