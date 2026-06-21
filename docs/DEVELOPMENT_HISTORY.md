# DOLG - история развития проекта

Этот файл заменяет старые roadmap/backlog/исследовательские черновики. Активный
фронт работ теперь ведётся отдельно в `docs/WORK_FRONT_20260619.md`.

Правило пополнения: сюда добавляются только закрытые этапы, принятые решения и
сжатые выводы после завершения задач. Новые незакрытые задачи не распылять по
отдельным Markdown-файлам, а сначала заносить в рабочий фронт.

## Текущее разделение документов

- `docs/WORK_FRONT_20260619.md` - единственный живой список работ.
- `docs/DEVELOPMENT_HISTORY.md` - история решений, закрытых этапов и поглощённых идей.
- `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/LOCAL_SETUP.md`, `docs/RUNBOOK.md`, `docs/DEPLOY.md` - справочники, которые обновляются по факту изменения системы.
- Дипломные файлы (`DIPLOMA_*`, `DEMO_SCENARIO.md`, `SCREENSHOT_GUIDE.md`) живут отдельно, потому что это не backlog, а материалы защиты.

## Хронология

### Апрель 2026 - базовый контур платформы

- Сформирован Django-проект с приложениями `shop`, `accounts`, `orders`, `knowledge`, `Dolg_APP`.
- Добавлены каталог, корзина, заказы, профили, базовые страницы магазина.
- Появились первые тесты для проектов схем, API, заказов, поиска, BOM и симуляционных квот.
- Схемный редактор получил сохранение проектов, версии, гостевой demo-режим, DRC, PDF/SVG export.
- Начат переход от "магазина компонентов" к платформе проектирования: схема, симуляция, BOM и заказ в одном маршруте.

### Май 2026 - инженерное ядро

- Добавлен scientific stack: NumPy, SciPy, Matplotlib, Pandas, FFT, Bode, Monte Carlo, signal quality, parameter sweep и серверный DC fallback.
- Сформирован expert-first review: правила, единицы, Z3 constraints, fuzzy-risk, fault library, derating, legal sources и PDF/HTML review.
- Добавлен импорт инженерных артефактов: LTspice/SPICE subset, KiCad subset, preview и learning-by-review.
- Создан self-hosted AI слой: rule-based assistant, intent modes, quick actions, context sources, session summary.
- Подключён tiny PyTorch backend как вероятностная подсказка, но final verdict остаётся за экспертными правилами.
- Создан legal knowledge corpus: открытые учебники, официальная документация, datasheet evidence, источники для правил и обучения.
- Каталог получил media quality gate, verified/generated images, запрет случайных Wikimedia/Commons fallback, datasheet intelligence baseline.
- Добавлены роли, тарифы Free/Pro/Enterprise, quota/entitlement слой, MLJob и staff ops dashboard.

### Конец мая - начало июня 2026 - качество, безопасность, данные

- Расширена ML-цепочка: `AITrainingExample`, curated schemes, normalize metadata, import/promote datasets, tiny model retraining.
- Добавлены staff/admin операции для ML, dataset curation и ops snapshot.
- HIGH-tier security backlog закрыт: основные CRUD/IDOR/secret/CSP/HSTS/axes/Sentry проблемы переведены в resolved baseline.
- Остаточный security фронт перенесён в medium/post-defense: rate limits, GDPR, upload validation, JSON body limits, log scrubbing, SBOM, K8s/Vault/Helm.
- Сформирован demo-ready слой: `check_demo_ready`, `check_data_integrity`, smoke tests, screenshot guide, demo scenario.

### Июнь 2026 - предзащита и консолидация

- Сформирован единый предзащитный приоритет: сначала документ, презентация, демо-маршрут и стабильность, затем low-risk вау-фичи.
- Подготовлены блоки для ВКР: объект, предмет, методы, формулы, глава 2, декларация ИИ, ответы комиссии.
- Собран текущий фронт работ `WORK_FRONT_20260619.md`, который заменяет старые scattered roadmap/backlog документы.
- Установлен и проверен pytest в `.venv`; корректная команда запуска: `.\.venv\Scripts\python.exe -m pytest`.
- Добавлен каталог серверных движков: Xyce, PySpice, GnuCap, OpenModelica, GNU Radio, Sigrok, OpenFPGA/OpenROAD, Zephyr, OpenWrt и другие.
- Сформирован router profile: Xyce как основной кандидат для серверной симуляции, PySpice как Python bridge, ngspice.wasm как интерактивный браузерный режим, NumPy/MNA как fallback.
- Настроен VS Code workspace-слой: рекомендованные расширения для Django/Python/Ruff/Docker/Kubernetes/YAML/SQL, tasks для pytest/Django/Docker/K8s/SQL/frontend, debug-конфиги, YAML schema associations и `scripts/check_vscode_stacks.ps1` для диагностики стеков с timeout.

## Принятые архитектурные решения

### Симуляция

- До защиты основной пользовательский путь остаётся клиентским: `ngspice.wasm` + JS/NumPy fallback.
- Серверный слой развивать через job API и отдельные worker-процессы, а не через тяжёлые CLI-вызовы внутри Django request.
- Основной будущий серверный SPICE-кандидат - Xyce. PySpice использовать как Python adapter/bridge, GnuCap как лёгкий fallback для mixed-signal/educational cases.
- Для внешних движков целевая форма - Docker image + REST contract + async jobs + artifacts.

### AI/ML/RAG

- AI не должен быть финальным инженерным авторитетом: числа и verdict берутся из движков, правил и расчётов.
- Tiny PyTorch/GNN/semantic search дают подсказки и ранжирование, но не отменяют expert-first review.
- До Postgres миграции RAG держится на TF-IDF/hybrid retrieval. pgvector, GraphRAG и reranker - post-defense.
- Transformers.js/ONNX Runtime Web - хороший путь для браузерной семантики без Python wheel blockers.

### CAD/PCB/3D

- Ценность DOLG не в копировании KiCad/AutoCAD, а в учебном web-flow: схема -> проверка -> симуляция -> BOM -> PCB/3D -> отчёт.
- Сначала нужен one-click pipeline и headless PCB DRC, затем полноценный PCB editor.
- 3D остаётся view над данными проекта, а не отдельным источником истины.
- GLB подходит для ближайших 3D-компонентов; STEP/IDF/CadQuery/OpenCASCADE - post-defense server-worker слой.
- ЕСКД-активы должны быть registry-driven и валидируемыми, а не свободно генерируемыми AI.

### Инфраструктура

- Локальная защита может жить на SQLite/ngspice.wasm/Cloudflare Tunnel.
- Production path: PostgreSQL, Docker Compose, nginx/gunicorn, Redis/Celery, мониторинг, backups.
- Kubernetes нужен после стабилизации runtime: Deployments/Services/Ingress сначала, Helm/Vault/HPA позже.
- Docker/K8s для серверных движков должны быть отдельным контуром, чтобы не тащить Xyce/OpenModelica/GNU Radio в web image.

## Отложенные идеи, которые не потеряны

### Server engines

- Xyce/PySpice сделать первым реальным worker MVP.
- Дальше подключать GnuCap, OpenModelica, Sigrok, GNU Radio, OpenFPGA/OpenROAD, Zephyr/OpenWrt как task-specific workers.
- Для TINA-TI/MapleSim учитывать лицензии: не включать в основной open-source runtime, держать как optional registered worker.

### Simulator/editor

- Logic engine для AND/OR/NOT/NAND/NOR/XOR, truth table и СДНФ.
- Wire-router L-route с обходом компонентов и wire-merge.
- Undo/redo fix для `setCompField()`.
- DRC dedup: GND warning должен приходить из одного источника.
- Virtual scope polish: V/div, time/div, trigger.

### PCB/3D

- One-click схема -> PCB -> 3D.
- IPC-2221 DRC: clearance, current width, decoupling distance, ground split.
- Realistic board: copper, soldermask, silkscreen, 45-degree routing, env-map.
- GLTF/GLB components, enclosure, STL/STEP export.

### CAD/ECAD

- Arrays, blocks, ortho/snap/polar/object snap.
- ЕСКД asset registry and validator.
- Symbol/footprint editor, multi-section components, buses, hierarchical sheets.
- Bidirectional schematic<->PCB sync и functional blocks.

### AI/ML/Data

- GNN train+bench на Open Schematics/Masala-CHAI/AnalogGym с лицензионным фильтром.
- ML-curation UI: queue, soft-delete, quality flags, promote/exclude.
- DatasetSource registry.
- RAG Phase A: better chunking, hybrid retrieval, glossary, citations.
- Post-defense: pgvector, GraphRAG, reranker, multimodal photo-to-schematic, voice/TTS.

### Product/catalog

- Favorites/bookmarks.
- Project cart: заказ связан со схемой/BOM.
- Project export as zip.
- Comments + moderation.
- Datasheet intelligence: pinout, absolute max, thermal, typical circuits.
- `rembg`/U2Net для чистого фона изображений.

### Security/ops

- Permission audit для ML/admin/API.
- Stripe webhook signature.
- Tier-aware rate limits.
- JSON body-size limits.
- Upload MIME/size validation.
- Log scrubbing, PII inventory, GDPR export/delete.
- SBOM/license audit, Dependabot/CodeQL, container scan.

## Поглощённые документы

Смысл этих файлов перенесён сюда и в `WORK_FRONT_20260619.md`; сами файлы можно не восстанавливать:

- `docs/AI_ASSISTANT_UPGRADE_PLAN.md`
- `docs/ARTIFACT_INGESTION_DEMO.md`
- `docs/AUTOCAD_AI_CODEGEN_PLAN.md`
- `docs/CAD_HARD_UPGRADE_PLAN.md`
- `docs/CHANGELOG.md`
- `docs/ENGINEERING_NOTES.md`
- `docs/ESKD_CERTIFIED_ASSET_PLAN.md`
- `docs/EXTERNAL_RESOURCES_INSPIRATION_20260602.md`
- `docs/FUNCTIONAL_BACKLOG_20260605.md`
- `docs/LECAD_LITHIUM_ECAD_RESEARCH_TODO_20260531.md`
- `docs/LITHIUM_ECAD_ANALYSIS.md`
- `docs/LITHIUM_INSPECTION_REPORT.md`
- `docs/MASTER_BACKLOG_20260605.md`
- `docs/PIPELINE_SCHEMATIC_TO_3D_PLAN.md`
- `docs/PRE_DEFENSE_REMAINING_20260614.md`
- `docs/PRE_DEFENSE_WOW_20260613.md`
- `docs/PROJECT_IMPROVEMENTS_20260614.md`
- `docs/REMAINING_WORK_20260615.md`
- `docs/RESTART_HANDOFF_20260609.md`
- `docs/SIM_3D_MODELS_PLAN.md`
- `docs/SERVER_ENGINE_ROUTER_PLAN.md`
- `docs/TRANSFORMERS_JS_SEMANTIC_PLAN.md`
- `docs/UNIFIED_ROADMAP_20260606.md`
- `docs/VIDEO_BACKLOG.md`
- `knowledge/notes/3d_priorities.md`
- `knowledge/notes/3d_research.md`
- `knowledge/notes/3d_roadmap.md`
- `knowledge/notes/ai_panel_rewrite.md`
- `knowledge/notes/circuit_datasets.md`
- `knowledge/notes/eda_toolbar_settings.md`

### 2026-06-20 - Django dev-loop acceleration

- Project URLConfs moved heavy view modules to lazy URL callbacks, so URL checks no longer import simulation, ML/admin, org, SSO, 2FA, chat, shop, accounts, orders, knowledge and moderation views during ordinary Django startup.
- The multi-line Django-template comment check is now opt-in through `DOLG_CHECK_DJANGO_COMMENTS=1` or active in CI, instead of scanning all HTML files on every local `manage.py check`.
- CLI-only checks can set `DOLG_SKIP_SOCIALACCOUNT_PROVIDERS=1` to avoid importing heavy OAuth provider stacks; normal site startup keeps Google/Microsoft/GitHub providers enabled.
- VS Code Python/Django tasks now pass fast local env flags for checks, migrations, focused pytest, engine worker and SQL inspect.
- Verification: `.venv\Scripts\python.exe -m ruff check Dolg_APP\urls.py Dolg_APP\checks.py`, `manage.py check`, URL reverse/resolve smoke, `/simulation/` and `/cad/` smoke, Stripe webhook CSRF smoke.
- Current light profile with ASGI, optional app probes and social providers skipped: `django.setup` ~8s, Django checks ~3-4s. Remaining startup weight is mostly Django core/admin/forms/model loading, so further cuts should be feature-specific rather than global.

### 2026-06-20 - Simulation/CAD asset smoke

- Added `Dolg_APP/tests_tool_asset_smoke.py` for fast `/simulation/` and `/cad/` smoke coverage without Playwright-heavy browser runs.
- The smoke renders both workspaces, checks rendered `/static/...` references through Django staticfiles, verifies critical simulation worker/wasm/lib/AI assets, and confirms the server-engine catalog/recommend APIs.
- During verification, stale ML training and VS Code `pytest --collect-only Dolg_APP` processes were stopped; VS Code Test Explorer now points at focused smoke/core test files instead of collecting the whole app by default.
- Verification: `ruff check Dolg_APP\tests_tool_asset_smoke.py`, `pytest Dolg_APP\tests_tool_asset_smoke.py -q`, `.vscode/settings.json` JSON parse.
- Next active item in `WORK_FRONT_20260619.md`: Session 2, first small extraction from `simulation.html` into `shop/static/simulation`.

### 2026-06-20 - Simulation server-engine UI extraction

- Extracted pure server-engine render helpers from `simulation.html` into `shop/static/simulation/server-engine-ui.js`.
- Kept the old global function names and inline handler contract in `simulation.html`; they now delegate to `window.DolgServerEngineUI`, so the current UI keeps working while the template gets smaller.
- Extended `Dolg_APP/tests_tool_asset_smoke.py` to verify the new static asset and run a Node VM contract smoke for result rendering, escaping, job counts and engine cards.
- Verification: `ruff check Dolg_APP\tests_tool_asset_smoke.py`, `pytest Dolg_APP\tests_tool_asset_smoke.py -q`, Node syntax check for `server-engine-ui.js`, and `git diff --check` for touched files.
- Next active item in `WORK_FRONT_20260619.md`: Session 3, EngineJob MVP-2.

### 2026-06-21 - EngineJob MVP-2 and first server engine

- Added `dolg-engine-router` to the server-engine catalog as the first real server-side engine entrypoint. Its worker adapter currently delegates to `dolg-numpy-mna`, records the route in result metrics/artifacts, and gives us a stable place to attach Xyce/PySpice/GnuCap/GNN workers later.
- Extended `EngineJob` with `reason`, `retry_count`, `max_retries`, `result_contract_version` and `audit_log`; added migration `0021_enginejob_mvp2`.
- Added lifecycle helpers for retry, stale heartbeat detection and audit events. `run_engine_worker --mark-stale --stale-after N` can now clean orphaned running jobs before processing the queue.
- Added API retry endpoint `/api/sim/jobs/<id>/retry/`, richer job serialization, terminal result status handling, and admin visibility for retry/reason/audit fields.
- Result payloads now normalize to `dolg.engine.result` contract v1, so future external workers can return the same shape.
- Verification: focused ruff, `manage.py check`, `makemigrations --check --dry-run`, and `pytest Dolg_APP/tests_server_engines.py Dolg_APP/tests_tool_asset_smoke.py -q` (`23 passed`).
- Next active item in `WORK_FRONT_20260619.md`: Session 4, security/data-protection report for targeted attacks.

### 2026-06-21 - Targeted attack data-protection report

- Added a full targeted-attack data-protection report to `docs/SECURITY_BACKLOG.md` instead of creating another standalone document.
- Mapped DOLG's real assets and trust boundaries against OWASP ASVS 5.0, OWASP Cheat Sheets/Top 10 themes, and NIST CSF 2.0.
- Documented current controls in code: production settings guardrails, CSRF/security headers, Stripe webhook signatures, SSRF guard, hashed organization API tokens, audit logs, project event logs and `EngineJob` audit/result boundaries.
- Prioritized the remaining gaps: strict CSP migration, hardened upload pipeline, admin/Data Console hardening, Stripe demo fail-closed behavior, proxy trust checks, future Docker/K8s worker sandboxing and incident monitoring.
- Corrected the security backlog status for CSP: it is still partial because `settings.py` keeps `'unsafe-inline'` until the heavy simulation UI is decomposed.
- Verification: documentation diff review and `git diff --check` for the touched markdown files.
- Next active item in `WORK_FRONT_20260619.md`: Session 5, Admin/Data Console v2.

### 2026-06-21 - Admin/Data Console v2

- Extended the staff Data Console with read-only filters for Django models, SQL tables, FileField entries and JSONField entries.
- Added JSONField inventory and compact sample previews with safe admin change links, so staff can inspect project/engine/audit payloads without writing custom SQL.
- Replaced hard-coded admin paths with reverse-resolved changelist/change URLs where the model is registered in Django admin.
- Kept media browsing read-only and bounded the recursive media scan to avoid freezing the console on large artifact directories.
- Added focused coverage for Data Console loading, filters and JSON preview.
- Verification: `ruff check Dolg_APP\ml_admin_views.py Dolg_APP\tests_ml_admin.py`, `py_compile Dolg_APP\ml_admin_views.py`, `manage.py check`, `pytest Dolg_APP\tests_ml_admin.py -q` (`11 passed`), and `git diff --check`.
- Next active item in `WORK_FRONT_20260619.md`: Session 6, CAD/simulation UX pass.

## Шаблон новой записи

```markdown
### YYYY-MM-DD - название этапа

- Что изменилось.
- Почему принято такое решение.
- Какие проверки прошли.
- Что стало следующим активным пунктом в `WORK_FRONT_20260619.md`.
```
