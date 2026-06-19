# DOLG - фронт работ на 2026-06-19

Единый живой список проектных задач после ревизии кода, документации и последних
коммитов. Дипломная защита, допуск и организационные материалы остаются отдельно
в `docs/DEFENSE_PROJECT.md` и сейчас не управляют очередью разработки.

## Срез проекта

- Рабочее дерево проекта чистое; вне коммита остаётся только локальный файл
  `.claude/settings.local.json`.
- Последние ключевые коммиты:
  - `22c3fb3` - расширены админские действия, добавлен Data Console, профиль
    рабочей среды и локальный PostgreSQL dev-профиль.
  - `afa8c77` - улучшены CAD/simulation workspace.
  - `14fc898` - связан маршрут simulation -> PCB -> 3D.
- Django ORM использует SQL всегда; локально по умолчанию SQLite, PostgreSQL
  включается через `DATABASE_URL`. Для dev Postgres добавлены
  `scripts/postgres_dev.ps1` и `deploy/docker-compose.postgres-dev.yml`.
- Server engine gateway уже имеет каталог движков, API `/api/sim/server-engines/`,
  `/api/sim/jobs/`, модель `EngineJob`, локальный worker `dolg-numpy-mna` и VS Code
  tasks `Engine worker: once/watch`.
- Внешние SPICE/моделирующие движки пока adapter-ready: Xyce primary-candidate,
  PySpice bridge, GnuCap/OpenModelica/Sigrok и остальные ждут Docker/worker
  контура.
- Админка получила больше контроля: bulk-действия по проектам, jobs, reviews,
  товарам, заказам, модерации; Data Console даёт read-only обзор БД, моделей,
  таблиц, FileField и media.
- Профиль пользователя теперь хранит настройки рабочей среды: density, layout,
  AI backend, preferred sim engine, render mode, animations/reduced motion,
  advanced tools.
- `simulation.html` остаётся самым тяжёлым местом: около 982 KB. `cad.html` -
  около 315 KB. Это главный риск для будущих UX-правок.
- Static source of truth для симулятора сейчас находится в `shop/static/simulation`
  и `shop/static/lib`, хотя часть документации ещё говорит просто
  `static/simulation`.

## Проверки на момент ревизии

- `ruff check Dolg_APP accounts shop orders moderation` - OK.
- `manage.py check` - OK, но холодный запуск занял около 159 секунд.
- `manage.py makemigrations --check --dry-run` - `No changes detected`, но занял
  около 193 секунд.
- `scripts/profile_django_checks.py`:
  - `django.setup`: 167.0 s.
  - `check_url_namespaces_unique`: 52.1 s.
  - `Dolg_APP.checks.check_multi_line_django_comments`: 12.7 s.
  - `check_templates`: 2.4 s.

Вывод: функционально проект живой, но dev-loop уже слишком тяжёлый. Ускорение
старта теперь P0, потому что оно влияет на каждую следующую задачу. После
повторяющихся системных прерываний, таймаутов и перегруза памяти/процессора
стабильность рабочей машины поднимается выше P0.

## P-1 - аварийная стабилизация системы

Это приоритет выше любых продуктовых задач. Если память, CPU, диск, VS Code,
Docker/WSL, Python, Node или фоновые службы забивают машину так, что команды
зависают и работа прерывается, все P0/P1 задачи временно считаются
заблокированными.

1. Снять честный baseline нагрузки.
   - Зафиксировать RAM/CPU/Disk usage, top processes, количество Python/Node/Git
     процессов, состояние Docker Desktop/WSL, VS Code extension host и фоновых
     watchers.
   - Отдельно проверить тяжёлые процессы: Docker Desktop backend, WSL, VS Code,
     language servers, antivirus/indexer, npm/vite watchers, Django/test runs.
   - Сохранять снимки в `logs/`, чтобы видеть не ощущения, а конкретные причины.

2. Ввести "тихий режим разработки".
   - Перед тяжёлыми задачами останавливать Docker Desktop, лишние dev servers,
     Node watchers, старые Python/test processes и зависшие Git/pre-commit
     процессы.
   - Запускать проверки последовательно и точечно, пока машина не стабилизирована.
   - Для VS Code держать минимальный профиль расширений: Python/Pylance, Ruff,
     Django/templates, SQL, Docker/K8s только когда реально нужен этот слой.

3. Добавить системные helper-скрипты.
   - `scripts/diagnose_system_load.ps1`: top CPU/RAM/Disk processes, свободная RAM,
     процессы Python/Node/Git/Docker/WSL/VS Code, краткий verdict.
   - `scripts/stop_heavy_dev_services.ps1`: мягко останавливает только dev-heavy
     процессы, которые безопасно завершать; без удаления данных и без reset.
   - VS Code task `System: diagnose load`, чтобы проверка была одним действием.

4. Радикально снизить нагрузку проекта.
   - Сначала ускорить `django.setup` и `manage.py check`, потому что они сейчас
     сами держат машину занятой минутами.
   - Разобрать тяжелые imports/URLConf до того, как снова запускать широкие тесты,
     Docker, K8s или Playwright.
   - Не запускать полный `pytest`, frontend build и Docker одновременно.

5. Критерий выхода из P-1.
   - `git status`, `ruff check` по изменённым файлам и лёгкие Django-команды
     проходят без зависаний.
   - После закрытия тяжёлых фоновых процессов остаётся заметный запас RAM/CPU.
   - Новые задачи снова можно делать без постоянных таймаутов и ручных рестартов.

## P0 - ближайший фронт после стабилизации системы

1. Ускорить Django/dev-loop.
   - Профилировать `django.setup`, а не только checks: найти тяжёлые imports в
     `views.py`, `admin.py`, URLConf, optional integrations и ML/scientific stack.
   - Вынести тяжёлые импорты из URL-level import path в lazy helpers.
   - Оптимизировать или сделать opt-in проверку `check_multi_line_django_comments`,
     чтобы она не сканировала проект на каждом обычном `manage.py check`.
   - Проверить, почему `check_url_namespaces_unique` занимает 52 s: вероятно,
     слишком тяжёлый URLConf из-за импортов views/templates.
   - Цель: `manage.py check` до 20-30 секунд на текущей машине, затем ниже.

2. Сделать браузерный asset-smoke для simulation/CAD.
   - Проверить, что `/simulation/` реально загружает `shop/static/simulation/*`,
     `shop/static/lib/*`, wasm worker и Vite bundle без 404.
   - Добавить тест или management smoke, который ловит missing static до ручной
     проверки браузером.
   - Синхронизировать README/docs: писать `shop/static/simulation`, если именно
     там лежит источник.

3. Начать декомпозицию `simulation.html` без большого переписывания.
   - Вынести один самодостаточный блок: server-engine modal или instrument
     animation/controller.
   - Оставить обратную совместимость через `window.*` namespace и существующие
     inline handlers.
   - Добавить минимум Vitest/pytest coverage на вынесенный контракт.
   - Не делать полную TS-миграцию одним прыжком.

4. Проверить Docker/PostgreSQL после стабилизации dev-loop.
   - Запустить `powershell -ExecutionPolicy Bypass -File scripts/postgres_dev.ps1 up`.
   - Получить `DATABASE_URL`, применить миграции, открыть Data Console на Postgres.
   - Если Docker снова зависает, фиксировать точный статус в `logs/` и продолжать
     без него через SQLite/local worker.

5. Обновить API/docs по факту новых функций.
   - `docs/API.md`: server engine jobs, Data Console/staff ops, profile workspace
     settings, local Postgres dev profile.
   - README: заменить устаревшие ссылки на новый фронт и уточнить static paths.
   - `docs/TESTS_AND_REPORTS.md`: добавить свежий срез проверок и заметку о
     медленном старте.

## P1 - продуктовый слой, который можно делать без Docker

1. CAD/simulation UX polish.
   - Исправлять проблемы интерфейса через маленькие, проверяемые блоки:
     overflow, панели, пустые состояния, ошибки, tooltips, mobile/tablet.
   - Довести настройки профиля до реального влияния на рабочие страницы:
     density/layout/render mode/animations должны менять CAD/simulation UI, а не
     только лежать в `body[data-*]`.
   - Сформировать стабильный contract для будущих приборов: scope, generator,
     multimeter, probes, state badges, reduced motion.

2. Server engine gateway MVP-2.
   - Добавить нормальный stale/retry flow для `EngineJob`: heartbeat, retry count,
     reason, audit log.
   - Сохранить единый result contract для всех будущих workers:
     `nodes`, `branches`, `waveforms`, `metrics`, `warnings`, `artifacts`.
   - Подготовить Xyce adapter interface без обязательного Docker runtime:
     command builder, parser contract, fixtures, tests.

3. PCB/3D pipeline.
   - Укрепить one-click route scheme -> PCB -> 3D: понятные состояния, возврат,
     сохранение проекта, ошибки.
   - Расширить PCB DRC: net classes, keep-out zones, pours/via stitching,
     отдельный DRC export artifact.
   - Полировать 3D визуал: soldermask/copper/silkscreen, realistic board,
     стабильное framing на desktop/mobile.

4. Admin/Data Console v2.
   - Добавить безопасные фильтры/поиск по моделям и таблицам.
   - Добавить read-only preview для JSONField/project artifacts.
   - Добавить быстрые ссылки из Data Console в связанные admin changelist/change
     pages.
   - Не превращать Data Console в write-инструмент до отдельного permission audit.

## P2 - данные, AI и каталог

1. AI/ML curation.
   - ML curation UI lite: queue, quality flags, promote/exclude, soft-delete.
   - GNN train+bench на уже собранных датасетах.
   - RAG Phase A: расширить TF-IDF/hybrid retrieval на knowledge, expert rules,
     glossary и проекты; pgvector только после стабильного Postgres.

2. Catalog/product data.
   - Проверить текущие `catalog_schema.py`, audit/enrich commands и тесты перед
     новыми изменениями.
   - Дотянуть параметры по категориям до уровня demo-эталона.
   - Уменьшить N+1 в каталоге: prefetch/cache для `parameter_preview`,
     `brand_badge`, `delivery_hint`.
   - Связать project cart с BOM/схемой.

3. RF/front.
   - Если backend scikit-rf уже стабилен, вывести видимый front:
     S-параметры, Smith chart, matching hints.

## Later - крупные слои

- Полная TypeScript/Vite миграция `simulation.html` и `cad.html`.
- CSP без `unsafe-inline`.
- Redis/Celery для PDF, AI async, batch simulation.
- Docker/Kubernetes engine gateway: Xyce, PySpice/ngspice, GnuCap, OpenModelica,
  GNU Radio, Sigrok, OpenROAD/OpenFPGA.
- K8s Deployments/Services/Ingress, resource limits, HPA, Helm/Vault/monitoring.
- Production PCB exports: Gerber, NC drill, PnP, fab notes.
- Full PCB editor: placement, manual routing, pours, hierarchy, buses,
  bidirectional schematic<->PCB sync.
- Mechanical/3D workers: GLB library first, IDF/STEP/CadQuery/OpenCASCADE later.
- pgvector, GraphRAG, reranker, multimodal photo-to-schematic, voice/TTS.

## Рекомендуемый порядок ближайших сессий

0. Сессия 0: системная стабилизация P-1 - диагностика нагрузки, остановка
   лишних фоновых процессов, минимальный VS Code профиль, baseline в `logs/`.
1. Сессия 1: ускорить Django/dev-loop и зафиксировать профиль до/после.
2. Сессия 2: asset-smoke `/simulation/` + синхронизация README/API/docs.
3. Сессия 3: первый вынос блока из `simulation.html` в static/TS с тестом.
4. Сессия 4: Docker/Postgres dev run и Data Console на Postgres.
5. Сессия 5: EngineJob retry/stale/audit или Xyce adapter interface.
6. Сессия 6: CAD/simulation UX pass с реальным применением настроек профиля.

## Правила работы

- Не смешивать `.claude/settings.local.json`, secrets, generated env и unrelated
  local files с проектными коммитами.
- Перед крупной правкой UI сначала проверять размеры/границы `simulation.html` и
  `cad.html`, затем двигаться маленькими контрактами.
- Внешние движки запускать через worker/job, не внутри Django request.
- Docker/K8s не должны блокировать работу над продуктом: если daemon снова
  зависает, продолжаем SQLite + local worker и фиксируем blocker отдельно.
- Если система снова уходит в перегруз памяти/CPU и команды начинают зависать,
  возвращаться к P-1 без обсуждения: сначала стабилизировать машину, потом код.
- После завершения этапа кратко переносить итог в `docs/DEVELOPMENT_HISTORY.md`,
  а активные незакрытые задачи держать только здесь.
