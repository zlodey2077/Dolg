# DOLG - фронт работ на 2026-06-16

Сводка после чтения Markdown-файлов репозитория: README, архитектура/API,
backlog/roadmap, безопасность, Docker/K8s, AI/ML, CAD/3D, исследовательские
заметки и knowledge notes.

На 16 июня 2026 главный режим - развивать сам продукт без распыления на
дипломные и организационные задачи.

## Политика документации

Этот файл - единственный живой фронт проектных работ. Старые
roadmap/backlog/research черновики сжаты в `docs/DEVELOPMENT_HISTORY.md` и
удалены, чтобы документация не расползалась. Защита и допуск вынесены в
`docs/DEFENSE_PROJECT.md` и сейчас не участвуют в выборе задач. После завершения
проектных задач сюда вносится текущий статус, а в историю - только краткая
запись о закрытом этапе и принятых решениях.

## Текущая база

Не переделывать без отдельной причины:

- Клиентская симуляция уже держится на `ngspice.wasm`, JS/NumPy fallback, DC/AC/TRAN, Monte Carlo, derating, thermal, probes, RF/scikit-rf backend и history-метриках.
- Инженерный review уже expert-first: правила, единицы, Z3, fuzzy-risk, legal sources, граф схемы, PDF/визуализация.
- Каталог уже расширен до полноценного demo-состояния: категории, параметры, media quality gate, generated/verified images, datasheet intelligence baseline.
- AI уже имеет rule/self-hosted слой, tiny PyTorch backend, dataset curation, MLJob/staff ops и RAG/TF-IDF baseline.
- 3D/PCB уже имеют основу: `scheme-3d.js`, авто-PCB/роутинг/3D-viewer, Gerber/Excellon/PnP/BOM части в разной степени готовности.
- HIGH-tier security по `SECURITY_BACKLOG.md` отмечен закрытым; текущий риск - medium/later.
- Pytest уже есть в `.venv`: запускать через `.\.venv\Scripts\python.exe -m pytest`.
- Из новой сессии 2026-06-16: добавлен каталог серверных движков и router profile с Xyce как primary-candidate, PySpice как bridge, ngspice.wasm как interactive, плюс API/UI для просмотра движков.

## Обновление 2026-06-17

- После перезагрузки VS Code CLI и рекомендованные расширения проверены: настройки не потерялись.
- Docker Desktop остается внешним системным блокером: службы `com.docker.service`, `vmcompute`, `LxssManager` не стартуют из обычной консоли, WSL-дистрибутивов Windows не видно, `docker info` зависает. После запуска Docker Desktop пришлось остановить его через `scripts/stop_docker_desktop_as_admin.cmd`, потому что обычные `tasklist/taskkill` тоже начали подвисать.
- Проектная работа продолжена без Docker: добавлен локальный worker для `EngineJob`, который обрабатывает `dolg-numpy-mna` jobs через внутренний NumPy MNA слой. Xyce/PySpice/GnuCap остаются в очереди до отдельного Docker/CLI worker.
- В VS Code добавлены задачи `Engine worker: once (local)` и `Engine worker: watch (local)`.
- Проверки: `Dolg_APP/tests_server_engines.py` - 14 passed; `manage.py check` - OK; `makemigrations --check --dry-run` - no changes.
- PR-проверка 2026-06-17: на GitHub открыт только Dependabot PR #3 (`pypdf 6.10.2 -> 6.12.0`), refs PR загружены локально, релевантные проверки прошли, изменение вынесено в отдельный commit `34f8d9e`.
- UI серверных движков доведен до первого end-to-end сценария: выбор engine/analysis, submit в `/api/sim/jobs/`, polling queued/running/success/error, компактный вывод `nodes`, `branches`, `metrics`, `warnings`.
- Успешный `EngineJob`, привязанный к проекту, теперь сохраняется в `SimulationRun` и пишет событие `ProjectEvent(simulation_run)`. Проверки после изменения: `Dolg_APP/tests_server_engines.py` - 15 passed; `manage.py check` - OK.

## Новый план после PR-проверки

1. Зафиксировать текущую проектную работу отдельными логическими commit'ами.
   - Сначала server-engine gateway: `EngineJob`, catalog/router, worker, tests, API/docs.
   - Затем VS Code/system tooling: `.vscode`, stack scripts, health-check tasks.
   - Потом документация: `WORK_FRONT`, `DEVELOPMENT_HISTORY`, `DEFENSE_PROJECT`, удаление старых черновиков.
   - Не смешивать `.claude/settings.local.json`, секреты, generated/static artifacts и unrelated правки.

2. Почистить commit-историю перед публикацией/merge.
   - Сначала сделать backup branch текущего состояния и убедиться, что рабочее дерево не содержит потерянных unstaged изменений.
   - Разделить накопленные изменения на понятные commits: dependency bumps, server engines, VS Code tooling, docs cleanup, UI/API changes.
   - Убрать шумовые/промежуточные commits через interactive rebase или squash только после того, как логические commits готовы и проверены.
   - Не переписывать историю опубликованной ветки без явного решения; если понадобится force-push, использовать `--force-with-lease`.

3. Довести EngineJob до видимого пользовательского сценария.
   - Готово: UI polling в `simulation.html`: submit -> queued/running/success/error.
   - Готово: отображение нормализованного результата: `nodes`, `branches`, `metrics`, `warnings`; `waveforms`/`artifacts` оставить для следующих worker'ов.
   - Готово: сохранение успешного результата в историю `SimulationRun`, если job привязан к проекту.
   - Осталось: отдельный удобный режим запуска локального `dolg-numpy-mna` worker через dev task/management command; не запускать процессы из web request.

4. Закрыть системные блокеры без остановки разработки.
   - Docker Desktop не запускать во время обычной работы, пока он снова не начинает стабильно отвечать.
   - Для остановки зависшего Docker держать task `Docker: stop stuck Desktop (admin)`.
   - Отдельно решить Windows WSL/Docker reset/repair: сначала backup/rename Docker WSL data, только после явного решения.
   - Kubernetes включать после живого Docker daemon и kube context.

5. Следующий технический слой движков.
   - Xyce Docker worker: netlist -> CLI -> parser -> общий result contract.
   - PySpice bridge: Python adapter к ngspice/shared lib.
   - GnuCap/OpenModelica/Sigrok оставить как adapter-ready entries до рабочего Docker контура.
   - Добавить retry/stale handling и audit-log для долгих задач.

6. После стабилизации core flow.
   - Авто-протокол `.md`/PDF из схемы, симуляции, review, BOM и графиков.
   - One-click схема -> PCB -> 3D: связать существующие страницы в один маршрут.
   - RF front polish: видимые S-параметры/Smith chart/matching подсказки.

## P0 - ближайшие проектные шаги

1. VS Code stack visibility.
   - Базовая настройка 2026-06-16 добавлена: `.vscode` рекомендации и задачи для Python/Django, pytest, Ruff, Docker, Kubernetes, YAML и SQL.
   - Health-check добавлен: `scripts/check_vscode_stacks.ps1` и task `Stacks: health check`.
   - Сейчас PASS: VS Code extensions, Python/Django/Pytest/Ruff, frontend install/type-check/build, SQLTools/SQLite Viewer, Docker Compose config, Kubernetes YAML/kustomize render.
   - Сейчас внешние блокеры: Docker Desktop backend не отвечает на `docker info`; kubeconfig/current-context отсутствует; `sqlite3.exe` CLI не установлен, но VS Code SQL работает через расширения.
   - Проверять, что VS Code видит `deploy/docker-compose.yml`, `deploy/k8s/*.yaml`, `db.sqlite3`, `.env.example`, Django templates и Python interpreter из `.venv`.
   - Держать в репо только безопасные workspace-файлы: `extensions.json`, `settings.json`, `tasks.json`, `launch.json`; локальные секреты и пользовательские настройки не коммитить.

2. Документация/API синхронизация.
   - Обновить `docs/API.md`: server-engine endpoints, Engineering Review, ML training/staff ops, AI tools, catalog/add endpoints.
   - Обновить README/About цифры и команды pytest.
   - Снять stale-пункты из старых roadmap, чтобы не чинить уже закрытое.

3. Server engine gateway - первый вертикальный слой.
   - Текущий статус: каталог движков, REST-информация, `EngineJob` model, `/api/sim/jobs/` submit/list/status/result, UI runner в симуляторе и локальный worker для `dolg-numpy-mna` уже есть.
   - Команды: `python manage.py run_engine_worker --once --limit 5` для разового прохода и `python manage.py run_engine_worker --limit 5 --sleep 2` для локального watch-режима. В VS Code есть такие же tasks.
   - Вынести запуск внешних движков в отдельный worker/process, не внутрь web request.
   - Следующий внешний worker: Xyce CLI в Docker; PySpice - adapter/bridge; ngspice.wasm остается быстрым интерактивным режимом.
   - Result payload уже нормализуется для локального worker и сохраняется в историю проекта: `nodes`, `branches`, `waveforms`, `metrics`, `warnings`, `artifacts`; расширить этот контракт на Xyce/PySpice после восстановления Docker.

4. Авто-протокол `.md`/PDF.
   - Собрать из схемы, параметров, симуляции, review, графиков, BOM и sources.
   - Это инженерный отчёт проекта, который полезен пользователю и может переиспользоваться любым экспортом.

5. Вау-пайплайн схема -> PCB -> 3D.
   - Один клик из схемы в плату и 3D без ощущения "три разные страницы".
   - Серверный PCB DRC по IPC-2221: clearance, ширина дорожки по току, decoupling distance, ground split.
   - Полировка визуала: медь, soldermask, шелкография, 45-градусные дорожки, realistic board.

6. AI/ML короткий пакет.
   - GNN train+bench на уже собранных датасетах.
   - ML-curation UI lite: очередь `AITrainingExample`, soft-delete, quality flags, promote/exclude.
   - RAG Phase A: расширить TF-IDF/hybrid retrieval на knowledge, expert rules, projects, glossary.
   - Transformers.js довести до офлайна: ONNX model + `ort-*.wasm` в static.

7. RF/front polish.
   - Если backend scikit-rf уже работает, вывести видимый front: S-параметры, Smith chart, matching подсказки.

## P2 - качество редактора и симулятора

1. Logic engine.
   - Отдельный boolean solver для AND/OR/NOT/NAND/NOR/XOR.
   - Truth table, СДНФ, routing intent `logic_eval`, без смешивания с MNA.

2. Провода и UX редактора.
   - L-route с обходом тел компонентов.
   - Merge wires при пересечении.
   - Починить undo/redo для `setCompField()` через `snapshotScheme()`.
   - Дедуп DRC "Отсутствует GND" в один источник.

3. Архитектурная подготовка.
   - Component registry: data-driven компоненты вместо switch в нескольких местах.
   - Shared rule pack frontend/backend.
   - KaTeX/Monaco/Cytoscape - только если они закрывают конкретный demo/use-case.

## P2 - каталог, продукт и данные

1. Сначала сверить факт с кодом.
   - В roadmap есть stale-пункты по per-category schema и datasheet intelligence; перед работой проверить текущие `catalog_schema.py`, команды audit/enrich и тесты.

2. Данные.
   - Дотянуть параметры по категориям до эталона "диоды".
   - Datasheet intelligence: pinout, absolute max, thermal, typical circuits.
   - `rembg`/U2Net для чистого фона фото - низкий риск, хороший визуальный эффект.
   - N+1 в каталоге: prefetch/cache для `parameter_preview`, `brand_badge`, `delivery_hint`.

3. Продуктовый слой.
   - Favorites/bookmarks.
   - Project cart: заказ связан со схемой/BOM.
   - Export project as zip.
   - Comments для статей/уроков/товаров/review + moderation.

## P2 - безопасность и эксплуатация

Не мешает локальной разработке, но важно до публичного production.

- Permission audit для ML/admin/API, IDOR/org isolation.
- Stripe webhook signature.
- Tier-aware rate limits для AI/search/BOM/import.
- JSON body-size limits.
- File upload MIME/size validation.
- Log scrubbing для PII/secrets.
- GDPR cascade delete, PII inventory, export/delete request.
- GitHub security settings: branch protection, CodeQL, Dependabot, Actions permissions.
- SBOM/license audit, container scan, lockfile discipline.

## Later - крупные слои

1. Архитектура frontend.
   - Split `simulation.html` на ES modules.
   - Split `cosmic_theme.css`.
   - Vite/TypeScript миграция по `frontend/README.md`.
   - CSP без `unsafe-inline`.

2. Docker/Kubernetes/server engines.
   - Postgres migration.
   - Redis/Celery для PDF, AI async, batch simulation.
   - `engine-gateway` + worker images: Xyce, PySpice/ngspice, GnuCap, OpenModelica, GNU Radio, Sigrok, OpenROAD/OpenFPGA.
   - K8s: Deployments, Services, resource limits, HPA, Ingress, secrets, artifact volume/object storage.
   - Helm/Vault/monitoring после стабилизации.

3. CAD/ECAD.
   - Production PCB exports: Gerber, NC drill, PnP, fab notes.
   - Full 2D PCB editor, placement, manual routing, pours, via stitching.
   - ESKD certified asset registry and validator.
   - Library creator: symbols, footprints, multi-section components.
   - Bidirectional schematic<->PCB sync, functional blocks, net classes, hierarchy, buses.

4. 3D/mechanical.
   - Split `scheme-3d.js`.
   - GLB component library, IDF/STEP later.
   - Enclosure/STL/STEP via CadQuery/OpenCASCADE/FreeCAD workers.
   - OffscreenCanvas only for render-heavy low-interaction scenes.

5. AI/RAG.
   - pgvector after Postgres.
   - GraphRAG/entity graph for knowledge/rules/schemes.
   - Reranker/citation validation.
   - Multimodal photo-to-schematic and voice/TTS only after core demo is stable.

## Рекомендуемый порядок ближайших сессий

1. Сессия 1: закрыть VS Code stack visibility и P0-doc sync - `API.md`, README/About цифры, команды pytest, ссылки на новые server-engine endpoint'ы.
2. Сессия 2: авто-протокол `.md`/PDF или server-engine job API skeleton - выбрать одно, чтобы не смешивать риски.
3. Сессия 3: one-click схема->PCB->3D + PCB DRC headless.
4. Сессия 4: GNN train+bench + ML curation UI lite.
5. Сессия 5: RF front или Transformers.js offline assets.

Правило текущего режима: брать только то, что улучшает продукт, код, API, данные,
тесты или инфраструктуру. Организационные и дипломные задачи лежат отдельно в
`docs/DEFENSE_PROJECT.md`.
