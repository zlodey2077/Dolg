# DOLG — Master Backlog (свод за всё время)

Составлено 2026-06-05 как единый реестр проблем, упущенного и давних просьб —
сведено из всех аудитов, бэклогов и заметок памяти проекта.

> ⚠️ **Дисклеймер.** Часть пунктов собрана из заметок 1–6-недельной давности —
> они point-in-time, не live-состояние. Помечено: `✅?` = судя по коду уже сделано,
> нужна проверка; `🔁` = просил неоднократно/давно; `P0..P3` = приоритет;
> `S/M/L` = объём. Перед работой над пунктом — сверять с текущим кодом.

Легенда статусов: `[ ]` открыто · `[~]` частично · `✅?` похоже закрыто (verify) · `🔁` давняя просьба юзера

---

## 0. 🗣️ ВСЕ незакрытые просьбы юзера (полный список, не выборка)

Все открытые пункты, исходящие напрямую от тебя (в т.ч. давние, где не хватало контекста).
`✅?` оставлены намеренно — они не закрыты окончательно, нужна проверка.

- 🔁 `[ ]` **P1 · L — Анти-AI чистка репозитория + scrub git history.** ~157 датированных
  меток `// YYYY-MM-DD …:` в 30 файлах (97 в `simulation.html`, 13 в `cad.html`,
  5 в `scheme-3d.js`, …) + декоративные `─────` + метки «Tier 0»/«R.11»/«Block A1».
  Плюс scrub commit-messages с self-attribution (BFG / git-filter-repo). Делать
  ТОЛЬКО по явной команде. Цель — «диплом выглядит как самостоятельная работа».
- 🔁 `[ ]` **P2 · L — CAD: режимы под сеткой** (просил 2026-04-24/25): ортогональный (ortho),
  snap-to-grid, snap-to-object, полярный режим с шагом угла. В `cad.html` уже есть
  следы `ortho/snap` (7 совпадений) — `[~]` частично, нужна доводка до рабочего UI.
- 🔁 `[~]` **P2 · M — ML-curation UI** (просил 2026-05-27 «чтобы вручную отсеивать спорное»):
  таблица `AITrainingExample` с превью-SVG, фильтры, soft-delete `is_validated`,
  bulk-actions, гистограммы распределения (топология/компоненты/размер),
  disagreement-viewer (предсказание vs лейбл), loss-curves, `MLTrainingRun`-история.
- 🔁 ✅ **DONE (verify 2026-06-05)** — Перенос боковых панелей симулятора наверх/вниз:
  закрыто sim-dock рефактором (162 совпадения sim-dock/dolg-lab/relocateLab).
- 🔁 ✅ **DONE (verify 2026-06-05)** — Schematic PNG/SVG export + раздельные кнопки:
  секция «Экспорт картинки» (PNG растр / SVG вектор) + BOM (Excel) + Netlist в меню «Файл».
- 🔁 ✅ **DONE (verify 2026-06-05)** — Engineering Review V2: modal в simulation.html (25 совпадений)
  + endpoints `api_engineering_review`/`api_project_review_*`/`project_review_pdf`.
- 🔁 `[ ]` **P3 · M — 3-cell AI-панель** (просил «3 ячейки вместо 6»). Сейчас 6 виджетов
  с пресетом «Мин». Реальной 3-cell композиции (Инструменты+Чат+Ввод) нет.

---

## 1. 🎓 Защита диплома (проверить ПЕРЕД защитой)

- `[ ]` **P0 · M — End-to-end demo dry-run.** `docs/DEMO_SCENARIO.md` ни разу не проигран
  целиком. 30-мин прогон руками + видеозапись + чинить что ломается.
- `[ ]` **P0 · S — Сверить цифры в тексте диплома** (.docx): товары (~363), категории (~23),
  тесты (263+), статьи (~22), демо-схемы (12), компоненты нейронки (340), AI-шаблоны (97).
- `[ ]` **P1 · M — Пересъёмка скриншотов** в `docs/diploma_assets/screenshots/`: Mock D
  AI-панель, add-product форма, sim-dock layout, ☰-меню, PCB HV multi-layer.
- `[ ]` **P1 · M — HF dataset import до конца ОДИН раз** (с HF_TOKEN) — чтобы в БД был
  результат для демонстрации нейронки; иначе на защите может застрять на 90 МБ.
- `[ ]` **P1 · S — Обновить About-page цифры** (`shop/about.html`): «26+ компонентов / 9+
  статей / 17+ тестов» — устарело в десятки раз. Дешёвый win.
- `[ ]` **P1 · S — README цифры** («17+ тестов», «26+ товаров») — bump до актуальных.
- `[ ]` **P2 · — Презентация/речь** под новые фичи (R.11 multi-section, R.12 Lithium,
  security hardening, GNN/A*/CircuitPython/Monte Carlo). README-бейджи.
- `[ ]` **P2 · — Probes-таб**: либо реализовать (pinned live probe, ~4 ч), либо убрать
  placeholder «планируется», чтобы не ловить вопрос комиссии.
- `[ ]` **P2 · — Заготовить ответы комиссии:** Stripe = «mock for diploma»; неподключённые
  либы = «для production-ready setup»; probes = «backlog по запросу».
- `[ ]` **P1 · S — Verify крупных фич на сломанность** (после структурных правок):
  - ☰-меню открывается и все секции работают (толщина/render mode/запуск/Файл-сохранение);
  - sim-dock после refresh — лаб переезжает в нижнюю панель (`setTimeout(retry,200)` не падает);
  - PCB HV multi-layer в 3D — top-traces красные, bottom синие, vias-цилиндры;
  - AR-предпросмотр (📱) реально работает на устройстве (HTTPS + iOS/Android);
  - WebSocket org-chat live-update (`/orgs/<slug>/conversations/`), не только polling fallback.
- `[ ]` **P2 · M — ПКМ context-menu (Phase C) → интеграция с ☰** (просил «C + D»). Сейчас ПКМ
  на канвасе показывает старое меню (Удалить/Очистить/…), не связано с hamburger.

---

## 2. 🐞 Баги и качество кода

- `[~]` **P1 · M — `decimal.InvalidOperation` на больших ценах.** Clamp добавлен в
  `Product.save()`, но тот же риск в других DecimalField (orders/Subscription/Payment).
  Архитектурно: кастомный валидирующий `DecimalField` везде.
- `[ ]` **P2 · S — Undo/Redo дыра:** `setCompField()` меняет value без `snapshotScheme()`
  → Ctrl+Z откатывает шире нужного.
- `[ ]` **P2 · S — DRC дедуп:** «Отсутствует GND» репортится из 3 мест
  (`schematic_validation.py`, `services/schematic_graph.py`, `services/project_review.py`)
  → свести к единому источнику + `_dedup_findings()`.
- `[ ]` **P2 · S — Локализация findings:** проверить ВСЕ строки review на русский
  (`Floating fragment`, `default_rules.json` и т.п.) — могли остаться англ. строки.
- `[ ]` **P3 · S — AuditLog API:** `.log()` vs ошибочный `.create()` — добавить алиас
  или переименовать в `record()`, чтобы не путать.
- `[ ]` **P3 · S — `CARD_PARAM_EXCLUDE` deny-list растёт бесконтрольно** → перевернуть в
  allowlist или соглашение про префикс `_` для внутренних ключей.
- `[ ]` **P3 · S — UPPERCASE-имена (61 в БД):** добавить `_name_locked: true` маркер для
  намеренных all-caps (модели/SKU), чтобы enrich их молча не трогал.
- `[ ]` **P3 · S — Cache-bust для JS:** `?v=…` на `<script src>` (CSS уже есть; JS — нет).

---

## 3. 🏗️ Архитектурный долг

- `[ ]` **P1 · XL — Split `simulation.html` (~14k строк).** Один файл: canvas, SPICE-runner,
  AI-панель, 3D, лаб, экспорт, status-bar. Разнести на ES-модули
  (`canvas.js`/`spice-runner.js`/`ai-panel.js`/`lab.js`/`export.js`). Блокирует полный
  CSP-nonce (см. §5). Post-defense.
- `[ ]` **P2 · L — Split `cosmic_theme.css` (~2550 строк, 23 секции, дубли селекторов)**
  на 6–8 partial-файлов.
- `[ ]` **P2 · L — Component registry (data-driven типы).** Типы компонентов захардкожены
  в switch'ах (`drawComponent`/`getComponentPorts`/`getComponentLabel` — правки в 5–6
  местах на новый компонент). Нужен единый `COMPONENT_REGISTRY` (frontend) +
  `components/registry.py` (backend).
- `[ ]` **P2 · L — Shared rule pack frontend↔backend.** `runQuickDRC` (JS) и
  `collect_topology_evidence` (Py) дублируют логику. Единый JSON-pack с
  `condition_dsl`, eval и в JS (`expr-eval`), и в Py (`rule_engine`).
- `[ ]` **P2 · M — Единое хранилище ML-датасетов.** 3 источника (DB `AITrainingExample` +
  `ml/dataset/*.json` + `external/*.json`) → модель `DatasetSource(kind, count, last_synced)`.
- `[ ]` **P2 · M — AI-tools whitelist дублируется** backend (`ai_tools.py`) + frontend
  (`AI_TOOLS_WHITELIST`) → отдавать через `/api/ai-tools/`.
- `[ ]` **P2 · M — ML-progress в Django cache, не в DB** → теряется при рестарте.
  Модель `MLTrainingRun` с heartbeat'ами.
- `[ ]` **P3 · M — Permission-система выкачена наполовину** (`org_permissions.py`):
  асимметрия read vs write. Table-driven ROLE_PERMISSIONS audit-тест.
- `[ ]` **P3 · S — Inline `<style>` в категорийных шаблонах** перебивает глобал по
  специфичности → вынести в файлы или scope через `.page-*` на body.
- `[ ]` **P3 · S — Daphne ASGI + `static()` gotcha** — вынести dev-urls в отдельный модуль
  + smoke-тест.
- `[ ]` **P2 · — (future) CAD↔Schematic bidirectional sync**, component placement helper,
  annotation propagation (designator/value/footprint).

---

## 4. 🔒 Безопасность (осталось; HIGH в основном закрыты коммитами H4/H6/H7/H8/H9)

Полный список — `docs/SECURITY_BACKLOG.md` (16 категорий). CRITICAL = нет.

- `[~]` **P1 · M — Permission audit** на ML/admin/API views (`staff_required` /
  `permission_required`) — частично; добить.
- `[~]` **P1 · M — IDOR / org-isolation:** `owner_required` + явный ownership-check на
  `/projects/<id>/`, `/reviews/<id>/`, `/orgs/<id>/…`.
- `[ ]` **P2 · S — Stripe webhook signature verification** (mock не проверяет `stripe-signature`).
- `[ ]` **P2 · M — Rate-limit per-minute** tier-aware (AI/search/BOM) — anti-DoS на кошелёк Anthropic.
- `[ ]` **P2 · M — GDPR cascading delete** + PII inventory + DSR + cookie consent.
- `[ ]` **P2 · S — Log scrubbing** (PII/secret из логов).
- `[ ]` **P2 · S — `.dockerignore` + container scan (Trivy/Grype) + `/healthz`** + django-health-check.
- `[ ]` **P2 · S — nginx hardening** + Grafana metrics expose review.
- `[ ]` **P2 · S — axes за пределами login** (2FA/API).
- `[ ]` **P2 · S — Privacy Policy + ToS** страницы (есть заготовки terms/privacy — проверить).
- `[ ]` **P2 · S — Lithium import XSS** на render-side (экранирование metadata).
- `[ ]` **P2 · S — Path-traversal в media-serving** (`Dolg_PR/urls.py` `serve(...)`) — nginx в prod
  или django-storages с whitelisted-path.
- `[ ]` **P2 · S — AI-tool actions без secondary backend-auth.** Frontend проверяет whitelist+confirm,
  но бэк не verify tier/permission на destructive (`scheme.clear_all`) → `@require_permission('ai.tool.<name>')`.
- `[ ]` **P2 · S — SPICE netlist eval audit** + `tmp_path = Path(tempfile.mkdtemp())` в `views.py`.
- `[ ]` **P3 · — Runtime IDS/anomaly** (§14): circuit breakers, kill switches, alerting.

---

## 5. ⚡ Производительность / dev-сервер («правило 99%»)

- `[ ]` **P2 · S — `start_fast.bat` + `FAST_DEV=1`** — отрезать тяжёлые импорты
  (prometheus/sentry/torch/datasets), старт 3–5 сек.
- `[ ]` **P2 · S — Pre-start cleanup в `start_local.bat`:** kill порта 8000, ожидание,
  опц. чистка `__pycache__`, single-instance lock, log rotation (5+ зомби python.exe).
- `[ ]` **P2 · S — `watchdog`** → надёжный autoreload `urls.py`/`settings.py` на Windows/MSYS.
- `[ ]` **P3 · M — uvicorn `--reload-include "*.py"`** вместо runserver; WhiteNoise для static в dev.
- `[ ]` **P2 · S — N+1 в каталоге** (`parameter_preview`/`brand_badge`/`delivery_hint` per-Product)
  → `select_related`/`prefetch` + `lru_cache`/`cached_property`.
- `[ ]` **P3 · M — AJAX polling 1.5с → Channels WebSocket** (Channels уже стоит) для ml_training/AI-chat.
- `[ ]` **P3 · — pytest-xdist / `--reuse-db`** ускорение сюиты; docs-консолидация (52→10), scripts-архив.

---

## 6. 🧩 Симулятор / редактор схем (фичи)

- `[ ]` **P2 · M — Wire-router L-route с обходом тел компонентов** (R_C.b → Q1.c) —
  отдельный кейс в schema-editor.
- `[ ]` **P3 · M — Wire-merge graph-split** при пересечении проводов.
- `[ ]` **P3 · L — Lithium import geometry reconstruction** (сейчас metadata-only).
- `[ ]` **P3 · M — Monaco Editor** для SPICE-netlist (вместо textarea): syntax/autocomplete/errors.
- `[ ]` **P3 · M — Cytoscape.js граф связности** схемы как отдельная вьюшка.
- `[ ]` **P3 · S — KaTeX** для формул в knowledge/AI-объяснениях.
- `[ ]` **P3 · S — openpyxl** XLSX-экспорт BOM (инженеры просят).
- `[ ]` **P3 · S — Smart-search Phase 1.5:** range-токены (`R<10k`/`P>0.25`), подсветка `<mark>`,
  рендер facets в sidebar (сейчас только в context), autocomplete part_number (AJAX top-5).
- `[ ]` **P3 · S — Reviews-модель** сейчас seeded в `shop_extras.py` без БД — вынести в модель.

---

## 7. 📐 CAD (kicad/altium + компас/autocad совмещение)

AutoCAD-parity (`project_cad_autocad_gap`):
- `[ ]` **P2 · M — Массив (Array)** прямоуг.+круговой (болты/радиаторы).
- `[ ]` **P2 · M — Блоки user-defined** (выделил → сохранил → переиспользуй).
- `[~]` **P3 · S — Штрих-пунктир/осевая (типы линий ЕСКД)** — частично (dash есть в коде).
- `[~]` **P3 · S — Offset (подобие)** + Trim/Extend как явные tool-режимы (следы есть).

CAD total-upgrade (`project_cad_total_upgrade`), post-defense:
- `[ ]` **P3 · L — Tier A:** Layer Manager, Top/Bottom view tabs, Bottom DRC panel.
- `[ ]` **P3 · L — Tier B:** Net Inspector, Measure tool, Component Properties, Footprint Library drawer.
- `[ ]` **P3 · L — Tier C:** embedded 3D mini-view, cross-probe Schema↔CAD, анимации, onboarding, status bar.
- `[ ]` **P3 · XL — Mechanical CAD:** шаблоны устройств (Arduino/ESP/DIN/wearable/drone), 2D drafting, STEP export.
- `[ ]` **P3 · XL — PCB pro-анализ:** DRC Engineering Review модал (50+ правил), impedance/crosstalk/PI/SI, AI-PCB, live cost (JLCPCB/PCBWay).
- `[ ]` **P3 · XL — Импорт чужих ECAD:** KiCad/EasyEDA/EAGLE/PCAD/Altium; мехСАПР через STEP.
- `[ ]` **P3 · L — `ezdxf` реальный DXF/DWG** (сейчас `dwg_stub`).
- `[ ]` **P3 · S — CAD quick-fixes:** дубль «Спецификация», группировка тулбара дивайдерами, скрыть «Свойства линии» когда выделен компонент.
- `[ ]` **P3 · S — TO-220/SMD-конденсатор/трансформатор** в палитру компонентов.
- `[ ]` **P3 · S — ГОСТ 2.104 штамп «поехал»** — проверить на 3–4 ширинах окна, текст не налезает на линии.
- `[ ]` **P3 · — WebGL в CAD** (сейчас Canvas2D держит 60fps на 50–100 элементах) — опционально.

---

## 8. 🤖 AI / ML / RAG

- `[~]` **P1 · L — GNN Neural Circuit Simulator (A1):** skeleton есть, нужен train+bench
  («80× speedup, <5% error» — pitch для защиты).
- `[ ]` **P2 · M — RAG Phase A** (½ дня, без либ): расширить TF-IDF индекс на knowledge/
  expert_rules/projects/training; хук `### CONTEXT ###` в `/api/ai/chat/`.
- `[ ]` **P3 · L — RAG Phase B** (sentence-transformers + pgvector, нужен Postgres) → C (reranker + citation + audit).
- `[ ]` **P3 · — AI-чат расширение контекстом** (scheme_data/selected/last sim/DRC findings)
  + welcome-prompt с примерами + `/learn/ai-assistant.md`. БЕЗ новых кнопок.
- `[ ]` **P3 · L — AutoML topology search (A2, NSGA-II + Z3)** — «VCO 100 МГц, <10 мА» → Pareto-front.
- `[ ]` **P3 · — Anthropic prompt-caching аудит** (~15 мин).
- `[ ]` **P3 · XL — Multimodal (post-defense):** photo-to-schematic (PaddleOCR-VL),
  datasheet parsing, CLIP shop-search, Whisper voice→schematic.
- `[ ]` **P3 · S — Arduino export (B2)** — тот же парсер схемы в Arduino IDE формат (бонус к CircuitPython).
- `[ ]` **P3 · M — PGlite offline-mode (D1)** — `/demo-offline/`, Postgres в WASM 3.7 МБ,
  работа без сети (pitch «гибридная архитектура SQLite/Postgres/PGlite»).
- `[ ]` **P3 · S — TTS статей (E)** через edge-tts → mp3 (accessibility-балл).

---

## 9. 📚 Библиотеки: installed-but-unwired / отсутствуют

> ⚠️ Источники конфликтуют по времени — обязательно **verify wired vs installed**.

- `[ ]` **P1 · S — scikit-rf** установлен, но **0 применений** — RF/S-параметры/Smith
  (killer для РЭБ-уклона). Подключить хотя бы один анализ.
- `[~]` **verify — axes / csp / silk / sentry / mypy+django-stubs:** по старым заметкам
  «установлены, не подключены»; по новым — частично wired. Проверить каждую: реально
  работает или dead-code. Комиссия может поймать.
- `[ ]` **P2 · M — Celery + Redis** — async для PDF-review/AI-async/batch-sim (сейчас
  `threading.Thread`, нет персистентности/retry, риск request-timeout на больших PDF).
- `[ ]` **P3 · M — WeasyPrint** — review-PDF через HTML/CSS (DRY с web) вместо reportlab.
- `[ ]` **P3 · L — DRF** — миграция raw `JsonResponse` endpoints → serializers + Swagger.
- `[ ]` **P3 · M — PySpice (D2 расширение)** — server-side batch (Monte Carlo есть на NumPy).
- `[ ]` **P3 · — Octopart/LCSC/DigiKey API** — реальные datasheet/цены/наличие в карточке.

---

## 10. 🧪 Тесты

- `[ ]` **P1 · M — 0 тестов** у: ML-admin views, Enterprise add-product, `enrich_catalog`,
  Mock D layout (нужен Playwright), `ai_tools.py`.
- `[ ]` **P1 · S — Прогнать pytest** после структурных правок (sim-dock/hamburger/PCB) +
  починить fallout.
- `[ ]` **P2 · S — Coverage в CI** + обновить устаревшую цифру (README ~71%).
- `[ ]` **P2 · S — Playwright E2E** сейчас opt-in (`RUN_BROWSER_E2E=1`), в CI не идёт.
- `[ ]` **P3 · S — pre-commit для `check_django_comments.py`** (multi-line `{# #}` — 4-я наступка).

---

## 11. 📖 Документация

- `[ ]` **P2 · S — `docs/API.md`** устарел: Engineering Review, ml-training, catalog/add,
  AI-tool endpoints не описаны.
- `[ ]` **P2 · S — ML-admin (`/staff/ml-training/`)** не упомянут в README.
- `[ ]` **P3 · S — docs-консолидация** (52 файла → ~10), архив `scripts/`.

---

## 12. 🎨 UI/UX мелочи

- `[ ]` **P3 · S — Пустые карточки** (category=tools) — дефолтные параметры в enrich.
- `[ ]` **P3 · S — Native `<select>` на тёмной теме** — Safari игнорит `option{}`; нужен Choices.js.
- `[ ]` **P3 · S — AI-панель toolbar overflow** на mobile <480px → схлопывать в «☰ Раскладка».
- `[ ]` **P3 · S — Shortcut'ы:** `Esc` закрывает ☰, `Ctrl+,` открывает; авто-раскрытие лаба при первом sim.
- `[ ]` **P3 · S — Favicon** (сейчас `data:,` заглушка в обоих base.html) — реальный перед production.
- `[ ]` **P3 · S — Stale CSS в `simulation.html`** — legacy-правила удалённых блоков
  (`.stats-panel`/`.simulation-controls`/старая `.components-list`) — почистить.

---

## 13. 🚀 Инфраструктура / deploy / post-defense

- `[ ]` **P2 · M — Postgres-миграция** (чек-лист готов, ~30 мин) — разблокирует pgvector/JSONB/FTS.
- `[ ]` **P3 · L — K8s/Helm/Vault/Falco/Cosign** (`SECURITY_BACKLOG §16`).
- `[ ]` **P3 · M — Postgres FTS** (русская морфология, GIN) — Smart-search Phase 2.
- `[ ]` **P3 · — Real billing/SSO/2FA** дотянуть до production (mock → live).
- `[ ]` **P3 · — 3D advanced:** cross-section, measure tool, STL export, ток-анимация, WebXR.

---

### Итог
~130 незакрытых пунктов (всё открытое, не выборка). Защитный минимум — §1 (+ verify-
помеченные: многое из §0 уже закрыто, но требует подтверждения). Крупные архитектурные
(§3 split simulation.html / component registry / shared rule pack) и §0 анти-AI чистка
+ git scrub — после защиты, по явной команде.

**Что сделать дальше:** скажи номер раздела или конкретный пункт — возьму в работу.
Рекомендую начать с verify-прохода по `✅?` (§0), чтобы вычеркнуть реально закрытое,
и §1 (defense-blocking).
