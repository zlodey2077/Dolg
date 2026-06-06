# DOLG — Единый план по всем фронтам (2026-06-06)

Обновление [UNIFIED_ROADMAP_20260605.md](UNIFIED_ROADMAP_20260605.md) с учётом закрытого за
2026-06-05/06 и свежего git-лога. Сводит три источника:
[MASTER_BACKLOG_20260605.md](MASTER_BACKLOG_20260605.md) (код, ~130 пунктов) +
[FUNCTIONAL_BACKLOG_20260605.md](FUNCTIONAL_BACKLOG_20260605.md) (функционал/данные/защита) +
идеи юзера. Организовано **по фронтам (местам)**, с приоритетами и параллельностью.

> Легенда: `P0` defense-critical · `P1` высокий · `P2` средний · `P3` низко/фан ·
> `S/M/L/XL` объём · `∥` параллелизуемо · `→` зависимость · `⏸` post-defense · `💡` идея юзера

---

## ✅ Закрыто за последнюю серию сессий (вычёркиваем, не делаем дважды)

- **Запуск + dev-цикл:** `free_port()`, режим `--local`, hot-reload через jurigged (`--hot`),
  `-30%` cold-start (`DOLG_SKIP_ASGI`). Коммиты `1f087b5`, `10fcf3a`.
- **Wave 0 #1 — Авто-протокол `.md`** проверки схемы (`services/protocol_report.py` + view +
  ссылка в `project_review.html` + 3 теста). Коммит `a25a784`.
- **CAD полноэкранный режим + причёсанный CSS** (`27a5129`, `a9fdf5b`).
- **Симулятор полноэкранный режим** (`99545c7`) — проверено MCP context7/MDN 2026-06-06.
- **Security HIGH-волна:** H4 (bandit/gitleaks/pip-audit), H6 (SSRF guard), H7 (prompt-injection
  guard), H8 (sympify sandbox), H9 (CSP nonce). + CVE-патчи Django/urllib3/pyjwt/idna. + CI
  artifacts + GitHub hygiene (SECURITY.md/Dependabot/CODEOWNERS/CodeQL).
- **Инфра-автоматика:** paranoid auto-lint hook (ruff --fix + format) + scope-guard + dev
  allowlist + cleanup-рубильник + переиспользуемый Playwright-shot (`f1386cc`, `96d4bc0`).
- **(verify-подтверждено)** sim-dock перенос панелей, PNG/SVG export, Engineering Review V2.
- **Wave 0′ #1 — Glossary для нейронки + читаемый «живой» вывод** (идея #1, 2026-06-06):
  curated-глоссарий 16 базовых терминов (`knowledge/data/glossary.json`) + retrieval-grounding
  подключён в живой Claude-путь `api_ai_chat` (блок `### CONTEXT ###`, expert-first с цитированием,
  `context_sources` в ответе); typewriter переписан на читаемую постоянную скорость (~55 симв/с,
  потолок 6.5с) + `prefers-reduced-motion`. 5 тестов (`tests_ai_glossary.py`). Остаток (опц.):
  настоящий SSE token-by-token стриминг от Anthropic — отложен (трогает `call_claude`+фронт, риск).
- **Wave 0′ #2 — Шизо-тест: допуски + worst-case + Monte Carlo** (идея #6, 2026-06-06):
  `monte_carlo.py` расширен — per-component допуски (`tolerance_percent`, фикс бага «1% = 100%»),
  worst-case угловой анализ (полный перебор 2^k при ≤13 толер. компонентов, иначе выборка),
  «паранойя»-отчёт (вердикт ok/warning/critical + флаги: разброс >10/30%, смена знака),
  `run_tolerance_analysis`, потолок итераций 5000→10000. Эндпоинт `api_monte_carlo` принимает
  `component_tolerances`/`worst_case` и отдаёт огибающую+paranoia. Фронт: кнопка Monte Carlo
  переключена со старого «только делитель» на MNA по ЛЮБОЙ схеме + рендер отчёта надёжности.
  8 новых тестов (всего 19 в `tests_monte_carlo.py`). Остаток (опц.): UI-инпут допуска на компонент,
  matplotlib-гистограмма в отчёт.
- **Wave 0′ #3 — Verify-проход §9 либ** (2026-06-06): axes/csp/silk — подключены, env-gated
  (`ENABLE_*`, default off), НЕ dead-code; sentry — init по `SENTRY_DSN`; mypy/django-stubs —
  dev-CLI-тулзы (не runtime). **Найден и починен баг:** django-csp **4.0** читает только словарь
  `CONTENT_SECURITY_POLICY`, а в settings был legacy `CSP_*` (4.0 его игнорит) → при `ENABLE_CSP=1`
  политика не применялась. Мигрировано на 4.0 API, проверено: заголовок CSP отдаётся корректно
  (check проходит и off, и on). `csp_nonce` нигде в шаблонах — оставлен `'unsafe-inline'` (nonce
  взаимоисключим с ним). **scikit-rf — 0 использований** (dead dependency) → вынесено в фронт-задачу
  ниже (подключить RF/S-параметры или убрать из requirements).

✅ **Wave 0′ полностью закрыт** (авто-протокол · glossary+живой вывод · шизо-тест · verify-проход).

Дешёвые win-ы рядом: About/README цифры из БД (`check_demo_ready --json`); rembg-вырезки фото.

---

## 🧵 ФРОНТЫ (где живёт, приоритет, последовательность)

### 1. 🛒 КАТАЛОГ / данные `∥`
1. P1·M — **rembg вырезки фото** (U2Net): убрать фон/тени → решает media-quality V2 (РЭБ UGO).
2. ✅ **`catalog_schema.py` + `audit_catalog_schema`** (2026-06-06): per-category схема
   (required/recommended, ключи выверены по реальному каталогу) + команда `--json`/`--category`/
   `--strict`. Прогон на 227 REB-продуктах: все проходят required, среднее покрытие 83%. Команда
   даёт actionable-список пробелов для п.3 (capacitors 66%, ics 66%, transistors 74%). Тесты
   (`shop/tests_catalog_schema.py`).
3. P2·M — **дотянуть параметры по категориям** (теперь по отчёту audit_catalog_schema): capacitors
   (type×24, dielectric×14, max_temp×14, tolerance×13), ics (channels×29, family×27, supply_voltage×10),
   transistors (power×14, rds_on×11, ft×11, hfe×10), diodes (max_voltage×13), connectors (pitch/gender).
4. P2·M — **Media V2:** чистый UGO-PNG без текста/неона ИЛИ официальное фото; image-audit по
   категориям. No-Wikimedia policy.
5. P2·M — **Datasheet Intelligence** (PyMuPDF): pinout / absolute max / thermal / типовые схемы.
6. P3·S — **Smart-search Phase 1.5:** range-токены (`R<10k`), подсветка `<mark>`, facets в sidebar,
   autocomplete part_number.
7. P3·S — пустые карточки (category=tools) дефолтные параметры; чипы 3 класса (ресурсы/мета/параметры).

### 2. ⚡ СИМУЛЯТОР / редактор схем (высокий вау, pre-defense)
1. **Wave 0′ #2** — шизо-тест/допуски/MC10000 (P1-P2·M). ✅ сделано.
2. ✅ **scikit-rf RF-анализ** (2026-06-06): `services/rf_analysis.py` — S-параметры 2-портовых
   фильтров (rc_lowpass/rc_highpass/lc_lowpass) через skrf: S21 (insertion loss), S11 (return loss),
   частота среза −3 дБ + аналитический угол для сравнения, авто-диапазон частот. Эндпоинт
   `api_rf_analysis` (`/api/sim/rf_analysis/`) + 9 тестов (`tests_rf_analysis.py`). Закрыл
   verify-находку (skrf был установлен, 0 применений). Остаток: фронт-кнопка + график S21 (Plotly).
3. P1·M — **Интерактивные probes** (напряжение узла / ток ветви / перегрузка) — закрыть placeholder
   «планируется», иначе вопрос комиссии.
4. P2·S — быстрые фиксы `∥`:
   ✅ **Undo/Redo дыра** (2026-06-06): `setCompField` теперь фиксирует состояние ДО первой правки
   серии (idempotent snapshot) + обнуляет debounce-таймер при срабатывании → Ctrl+Z не схлопывает
   правку с предыдущим действием. Logic-review (JS, без браузер-теста).
   ✅ **DRC дедуп + локализация findings** (verify 2026-06-06): уже реализованы в `review_i18n.py`
   (`_dedup_messages` по семантическому ядру: GND/источник/floating/unconnected; `translate_review_text`
   exact + рекурсивный split `': '` + 8 regex-паттернов). GND-предупреждения из validation+graph
   схлопываются в одно, англ. фиксированные строки локализованы. Добавлена регрессия —
   7 тестов (`tests_review_i18n.py`). Backlog-записи были устаревшими.
5. ✅ **stale CSS** (2026-06-06): удалены мёртвые правила `.components-list` / `.components-more` /
   `.component-search-input` (markup давно удалён, остался коммент-маркер). Backlog ошибался про
   `.stats-panel`/`.simulation-controls` — они ЖИВЫ (используются в markup/JS), не трогал. Шаблон
   компилируется, живые классы (`tools-list`/`sticky-add-toggle`/`search-hidden`) целы.
6. P3·M — Wire-router L-route (обход тел компонентов); Monaco для SPICE-netlist; KaTeX формулы;
   openpyxl XLSX-BOM.
7. ⏸ XL — **Split `simulation.html`** (~14k строк) на ES-модули + component registry + shared
   rule pack. Блокирует полный CSP-nonce. **После защиты** (риск регрессий перед демо).

### 3. 🧠 НЕЙРОНКА / AI / RAG (высокий вау, pre-defense)
1. **Wave 0′ #1** — glossary + typewriter-стриминг (P1·S-M).
2. ✅ **Expert-first** (verify+fix 2026-06-06): инфра была (rule_id/severity/evidence/recommendation/
   confidence в `expert_rules`/findings), но без регрессии и с двумя багами. Добавлены тесты
   (`tests_expert_rules`, валидность пака + expert-first поля); починено: `min_*_px` дефолт 0→+∞
   (ложные «провода близко»), evaluate пропускает правила без нужных фактов вместо error-спама.
3. P1·L — **GNN Neural Circuit Simulator (A1):** skeleton есть → нужен **train+bench**
   («80× speedup, <5% error» — pitch для защиты).
4. ✅ (частично) **RAG Phase A** — хук `### CONTEXT ###` в `/api/ai/chat/` уже сделан glossary-
   grounding'ом (Wave 0′ #1): retrieval из glossary/articles/learning/catalog/legal/training.
   Остаток: вынести в полноценный TF-IDF-индекс (сейчас substring-ранжирование).
5. P2·M — **расширить нейро-корпус** до 1000+ схем через opt-in `allow_ai_training` + dataset
   governance (validation/coverage/topology balance перед дообучением).
6. P2·M — **Корутины в AI-ассистенте (асинхронность «для себя»):** (a) async-вызов Anthropic
   через `httpx.AsyncClient` / async-SDK вместо блокирующего `requests` (TIMEOUT 30с держит worker)
   → `async def api_ai_chat` + `sync_to_async` для ORM; (b) **SSE token-streaming** ответа через
   async-генератор + `StreamingHttpResponse` — закрывает отложенный остаток Wave 0′ #1 (живой
   стриминг прямо от модели, не имитация typewriter); (c) **параллельный retrieval** —
   `build_retrieval_context` гонит глоссарий/статьи/каталог/практикумы через `asyncio.gather`
   вместо последовательных DB-запросов (быстрее grounding). Pitch: «асинхронная AI-подсистема».
7. ⏸ — RAG Phase B (sentence-transformers + pgvector `→` Postgres) → C (reranker+audit);
   AutoML topology search (NSGA-II+Z3); multimodal photo-to-schematic.

### 4. 🛠️ АДМИНКА / мониторинг `∥`
1. ✅ **Защита `/metrics/` + ops_metrics** (verify+fix 2026-06-06): `ops_metrics.py` (psutil runtime)
   и `/staff/ops/` дашборд УЖЕ были. Реальный gap — `/metrics/` был публичным; закрыт guard'ом
   (staff ИЛИ `METRICS_TOKEN`, fail-closed, +7 тестов). Опц. остаток: nginx allowlist в prod.
2. P2·M — **расширенный `/staff/ops/` cockpit** + custom `dolg_*` Prometheus + Grafana dashboards +
   alerts + snapshot для защиты.
3. P2·M — **ML-curation UI / dataset review queue** (🔁 давняя просьба): таблица `AITrainingExample`
   с превью-SVG, фильтры, soft-delete `is_validated`, bulk-actions, гистограммы распределения,
   disagreement-viewer, loss-curves, `MLTrainingRun`-история (вместо cache → теряется при рестарте).
4. P3·S — бизнес-метрики ML/dataset/moderation в дашборде.

### 5. 🔒 БЕЗОПАСНОСТЬ / гигиена кода `∥`
HIGH-волна закрыта (H4/H6/H7/H8/H9). Осталось:
1. ✅ **IDOR/org-isolation** (verify+test 2026-06-06): аудит показал — уже защищено
   (`_project_for_read/write`, `_review_for_read`, `@require_org_permission`, org-фильтры в
   lookup'ах). `owner_required`-декоратора нет, но helper'ы его заменяют. Не хватало регрессии —
   добавил 5 IDOR-тестов (чужой не читает/пишет/обновляет проект и не открывает review → 404).
   `api_comments_delete` post-fetch проверка корректна (владелец ИЛИ staff-модерация). Остаток:
   permission audit ML/admin-вьюх (отдельная мелкая проверка).
2. ✅ **verify 2026-06-06 — все 4 уже закрыты:** Stripe webhook sig ver(`construct_event` в обоих
   handler'ах + demo-gate); AI-tools frontend-only (нет backend-эндпоинта на destructive, tier-gate
   на уровне чата); media через безопасный Django `serve()` (нет custom path); Lithium import →
   JSON-ответ, без `|safe`/template-XSS. Backlog был перестрахован.
3. P2·M — rate-limit per-minute tier-aware (anti-DoS; `_ai_rate_limit` per-sec уже есть); GDPR
   cascading delete; log scrubbing; `.dockerignore`+Trivy; nginx hardening.
   ✅ **`/healthz`** (2026-06-06): анонимная liveness/readiness-проба (БД+кеш, 200/503). +2 теста.
4. P2·S — **авто-чистка кода** (ruff `✅`/autoflake unused/vulture dead-code/orphan templates).
5. ⏸ — анти-AI чистка ~157 датированных меток + scrub git history — **только по явной команде**.

### 6. 📐 CAD (P2-P3, не основная фича ВКР) `∥`
1. P2·M — **Массив (Array)** прямоуг.+круговой; **Блоки user-defined** (выделил→сохранил→реюз).
2. P3·S — штрих-пунктир/осевая (ЕСКД); Offset/Trim/Extend как явные режимы; quick-fixes (дубль
   «Спецификация», группировка тулбара, скрыть «Свойства линии» при выделенном компоненте).
3. P2·L — **CAD режимы под сеткой** (🔁 просил 2026-04-24): ortho/snap-grid/snap-object/полярный —
   следы есть, доводка до рабочего UI.
4. ⏸ — CAD total-upgrade (Tier A/B/C, Net Inspector, measure, cross-probe); Mechanical CAD шаблоны
   + ezdxf реальный DXF/DWG; ECAD-импорт; 💡 генератор корпусов→STL; 💡 3D-CAD концепт (Three.js +
   OpenCascade.js/replicad, STEP/STL) — «новый продукт внутри продукта», отдельный Phase.

### 7. 🎓 ЗАЩИТНЫЕ МАТЕРИАЛЫ `∥` (P0-P1, отдельная «мышца», не блокирует код)
1. P0·L — **Диплом санитарный:** чистое оглавление (убрать TOC/PAGEREF мусор), строго 2 главы,
   единые стили, сократить таблицы 2-3× (сейчас 110) → в приложения.
2. P1·L — **Диплом содержательный:** введение/гл.1 (предметка→проблемы→аналоги→требования→
   проектирование)/гл.2 (реализация) + раздел **«Сеанс проектирования»** + UML/ERD (приложение).
3. P1·L — **Презентация 20 слайдов-витрина** (один объект/слайд, ≥24pt, реальные скрины/метрики).
4. P1·M — **Речь 7-8 / 10-12 мин** + готовые ответы комиссии (Django vs SPA, SQLite→Postgres,
   Stripe=mock, неподключённые либы=production-ready, AI без галлюцинаций, legal sources).
5. P0·S — **сверить цифры из БД** (`check_demo_ready --json`): товары/категории/тесты/статьи/демо/
   компоненты нейронки/AI-шаблоны. + About-page/README bump. + пересъёмка скриншотов (после Wave 0′).
6. P0·M — **end-to-end demo dry-run** (`docs/DEMO_SCENARIO.md` ни разу не проигран целиком) +
   pytest-прогон + HF dataset import ОДИН раз с токеном (чтобы на защите не застряло на 90 МБ).

### 8. 🛒 ПРОДУКТОВЫЙ СЛОЙ `∥` (P2-P3, не блокер защиты)
Избранное/закладки → комментарии+модерация → контекстные комменты → проектная корзина (заказ к
схеме/BOM) → экспорт проекта архивом (JSON+BOM+netlist+PDF+изображения zip).

### 9. 🔗 СВЯЗНОСТЬ CAD/SIM/обучение (функциональная)
CAD→SIM общий semantic JSON → import preview V2 (карта узлов: GND/источники/output/floating) →
DRC уровни (ошибка/предупр/рекомендация) → связать `/knowledge/lab/` с текущей схемой (расчёт→
ожидаемое→сравнение с метрикой) → learning-by-review (задача из конкретного finding) → fault
library расширить (перепутанный номинал/обрыв/КЗ/перегрев).

### 10. ⏸ АРХИТЕКТУРА / инфра (post-defense, дорого)
Split simulation.html → component registry → shared rule pack → split cosmic_theme.css → единое
ML-хранилище `DatasetSource` → **Postgres-миграция** (чек-лист готов, разблокирует pgvector/JSONB/
FTS) → Celery+Redis (async PDF/AI/batch-sim) → DRF+Swagger → K8s/Helm/Vault.

**Async / корутины проекта (asyncio).** ASGI уже есть (daphne + Channels). План перевода I/O-bound
на корутины: (1) `async def` вьюхи для сетевых ручек (AI-чат, SSRF-guarded fetch, HF-import) +
`asgiref.sync_to_async` для ORM; (2) внешние HTTP — `httpx.AsyncClient` вместо `requests`
(не блокирует worker); (3) заменить AJAX-polling 1.5с (ml_training/AI-chat) на async-консьюмеры
Channels (пересекается с §5/§8); (4) `asyncio.gather` для параллельных независимых запросов
(retrieval, batch-проверки). **Не корутинами:** CPU-bound (Monte Carlo, GNN) → multiprocessing/
NumPy-вектоориз., корутины тут не ускоряют. Риск: миграция ORM/middleware на async — основная
часть post-defense; до защиты безопасно взять только streaming AI (фронт «Нейронка» #6).

### 11. 🎭 «Личность» / easter-eggs `∥` (P3, ОДИН toggle-слой, default off)
TTS-озвучка действий (edge-tts, + accessibility-реюз) · инженерные тосты · авто-названия графиков
«Радио» · дедлайн-виджет (ядро = top нерешённых findings, юмор опционально) · OLED-виджет SSD1306.

---

## 🔀 Карта параллельности

- **Поток 1 (фичи-вау, pre-defense):** Нейронка(3) → Симулятор(2) — основной «человеко-поток» кода.
- **Поток 2 (данные/гигиена) `∥`:** Каталог(1) + Безопасность(5) + Админка(4) — независимы, чередовать.
- **Поток 3 (защита) `∥`:** Защитные материалы(7) — отдельная сессия, не блокирует код.
- **Не трогать до защиты:** Архитектура(10), multimodal/3D-CAD, анти-AI чистка. Продуктовый(8)/
  личность(11) — по остаточному времени.

Зависимости-блокеры: RAG-B `→` Postgres · 3D-from-photo `→` сегментация · ECAD-импорт/pgvector/FTS
`→` Postgres.

---

## ✅ Критический путь до защиты (коротко)

- **Обязательно (P0):** Защитные материалы(7) — диплом/презентация/речь/скрины/цифры + demo
  dry-run + pytest-прогон + HF import один раз.
- **Вау за 2-3 сессии (P1):** Wave 0′ — glossary+стриминг, шизо-тест/MC10000, verify-проход либ.
- **Дотянуть (P2):** security-остаток (permission/IDOR/Stripe/path-traversal), probes,
  catalog schema-audit, GNN train+bench.
- **После защиты:** архитектура(10), multimodal-флагман, CAD total-upgrade + 3D-CAD,
  анти-AI чистка+git, Postgres→RAG-B.

> Делать **сверху вниз внутри фронта**, **между Поток-1 / Поток-2 / Поток-3 — параллельно**.
> Скажи номер фронта или конкретный пункт — возьму в работу.
