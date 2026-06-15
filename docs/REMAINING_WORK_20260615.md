# DOLG — что осталось доделать (ревизия 2026-06-15)

Свод недоделанного по **всем докам** (`MASTER_BACKLOG_20260605`, `FUNCTIONAL_BACKLOG_20260605`,
`PROJECT_IMPROVEMENTS_20260614`, `PRE_DEFENSE_REMAINING_20260614`, `UNIFIED_ROADMAP_20260606`,
`SECURITY_BACKLOG`, `CAD_HARD_UPGRADE_PLAN`, пайплайн/ассистент-планы). Это **навигатор**, а не
дубль: детали — в исходных доках по ссылкам. Помечено закрытое за последние сессии, чтобы не
перебирать заново.

Легенда: `🔴` блокер защиты · `🟢` код, могу делать сам · `⏸` post-defense · `[Ю]` за тобой/научруком.
Приоритет `P0..P3`, объём `S/M/L/XL`.

---

## ✅ Закрыто за последние сессии (в git — НЕ переделывать)

- **Движок симулятора:** нелинейный MNA (Newton/Shockley диод/LED) · **транзиент TRAN** (Backward
  Euler C/L) · derating-factor · линейный стабилизатор · T_j (темп. кристалла) · Monte Carlo + worst-case.
- **Ассистент:** Plan-then-Execute (Фаза 1) · IDF-retrieval (Фаза 2) · реестр движков `ai_algorithms`.
- **PCB:** A* автотрассировщик · 45°-chamfer · **rip-up & reroute** (#11).
- **3D:** реалистичные модели корпусов · env-map (PMREM) · медные дорожки.
- **ML-данные:** устойчивый импорт (битый parquet/image-колонка не роняют) · **KiCad-8 парсер 710×**
  (0→корректные компоненты) · `--start-shard` · **curl-загрузчик HF** (requests стопорился) ·
  мультитренировка `--all-datasets` · полный импорт 78 шардов запущен.
- **Прочее:** RF-анализ (scikit-rf S21/S11) · интерактивные Probes (V/I) · единый светлый стиль.

---

## 🔴 P0 — блокеры ДОПУСКА/ЗАЩИТЫ (в основном [Ю]/научрук)

Детали и счёт — в [PRE_DEFENSE_REMAINING_20260614.md](PRE_DEFENSE_REMAINING_20260614.md). Кратко:

- `[Ю]` 6 формул (2.1–2.6) в Word · титул/задание/подписи · антиплагиат ≥40% · декларация ИИ ·
  сверка дедлайнов (работа/отзыв/ЭБС/ГЭК от 26.06 назад).
- `[Ю]` Речь 7–10 мин + ответы комиссии (конспект `DIPLOMA_DEFENSE_PREP.md` готов).
- 🟢 могу взять: объём ≥40 стр (посчитать/добить), вычитка ИИ-текста «под живого», **каркас
  презентации** (≈20 слайдов), **demo dry-run** по `DEMO_SCENARIO.md` (ни разу не игран end-to-end).
- 🟢 P0·S — **сверить цифры** в дипломе/README/About (товары ~363, тесты 263+, AI-шаблоны 97,
  нейро-корпус — теперь вырастет после импорта 78 шардов).

> По твоему указанию диплом-текст/защиту сейчас не трогаю активно — это раздел-напоминание.

---

## 🟢 Код/проект — что доделать (по областям)

### 1. AI / ML / RAG
- `[~]` **GNN-предиктор напряжений (A1):** skeleton есть, нужен train+bench (pitch «80× speedup,
  <5% error»). Теперь есть большой корпус (78 шардов) → можно `train_gnn_voltage_predictor --all-datasets`.
- `[ ]` P1·M — **RAG Phase A** (без либ): расширить TF-IDF индекс на knowledge/expert_rules/projects,
  хук `### CONTEXT ###` в `/api/ai/chat/`.
- `[ ]` P1·S-M — **Glossary + «живой» стриминг** ответа (анти-галлюцинации, FUNCTIONAL §K.1).
- `[ ]` P1·M — **Авто-протокол .md/PDF** (схема+параметры+sim+review+графики) — закрывает приложения
  диплома + вау (FUNCTIONAL §K.3).
- `[ ]` P2·M — **ML-curation UI** (давняя просьба 🔁): очередь `AITrainingExample`, soft-delete
  `is_validated`, гистограммы, disagreement-viewer.
- `[ ]` P2·M — **Единое хранилище датасетов** `DatasetSource(kind,count,last_synced)` (сейчас 3
  источника: DB + `ml/dataset/*.json` + `external/*.json`).
- `⏸` Multimodal (photo-to-schematic/CLIP/Whisper), AutoML topology search, RAG Phase B (pgvector).

### 2. Симулятор / редактор схем
- `[ ]` P2·M — **Logic-движок** (§AN): AND/OR/NOT, таблицы истинности, СДНФ — нужны логические
  компоненты в редакторе (новые UI-элементы → спросить).
- `[ ]` P2·M — **Wire-router L-route с обходом тел** компонентов; wire-merge при пересечении.
- `[ ]` P2·S — **Undo/Redo дыра:** `setCompField()` без `snapshotScheme()` → Ctrl+Z откатывает шире.
- `[ ]` P2·S — **DRC дедуп** «Отсутствует GND» (репорт из 3 мест → единый источник).
- `[ ]` P3·S — KaTeX формулы · Monaco для SPICE-netlist · Cytoscape граф связности.

### 3. Пайплайн схема→PCB→3D (вау)
- `[ ]` 🟡 P1·M — **Один клик «схема→плата→3D»** — бесшовный переход (сейчас разные страницы).
  Требует UI/браузер-верификации.
- `[ ]` P2·M — **DRC PCB-слоя** (IPC-2221): clearance, ширина по току, сигнал над разрывом земли,
  близость decoupling-капа. **Серверно, тестируемо headless — хороший следующий код-пункт.**
- `[ ]` P3·M — медь с толщиной + soldermask поверх (частично есть).

### 4. CAD (AutoCAD/КОМПАС parity)
- `[ ]` P2·M — **Массив (Array)** прямоуг.+круговой · **Блоки** user-defined.
- `[~]` P2·L — **Режимы под сеткой** (ortho/snap-grid/snap-object/полярный) — следы есть, доводка.
- `[ ]` P3·S — тулбар-группировка (съедает экран), дубль «Спецификация», TO-220/SMD в палитру.
- `⏸` Tier A/B/C (Layer Manager, Net Inspector, embedded 3D), Mechanical CAD, ECAD-импорт, `ezdxf`.

### 5. Архитектурный долг (в осн. ⏸ post-defense)
- `[ ]` P1·XL — **Split `simulation.html` (~14k строк)** на ES-модули (блокирует полный CSP-nonce).
- `[ ]` P2·L — **Component registry** (data-driven типы вместо switch'ей в 5-6 местах).
- `[ ]` P2·L — **Shared rule pack** frontend↔backend (дублирование DRC-логики JS/Py).
- `[ ]` P2·L — split `cosmic_theme.css` (~2550 строк).

### 6. Безопасность (CRITICAL нет; детали — `SECURITY_BACKLOG.md`)
- `[~]` P1·M — **Permission audit** на ML/admin/API + IDOR/org-isolation (`owner_required`).
- `[ ]` P2·S — Stripe webhook signature · rate-limit tier-aware (анти-DoS на Anthropic) ·
  log scrubbing · path-traversal в media-serving · AI-tool secondary backend-auth.
- `[ ]` P2·M — GDPR cascading delete + PII inventory + cookie consent.

### 7. Производительность / dev-сервер
- `[ ]` P2·S — `start_fast.bat`+`FAST_DEV=1` (старт 3-5с) · pre-start cleanup (kill 8000, зомби
  python.exe, log rotation) · `watchdog` autoreload urls/settings.
- `[ ]` P2·S — N+1 в каталоге (`parameter_preview`/`brand_badge` per-Product) → prefetch+cache.

### 8. Тесты
- `[ ]` P1·M — **0 тестов** у: ML-admin views, Enterprise add-product, `enrich_catalog`, `ai_tools.py`.
- `[ ]` P2·S — Coverage в CI · Playwright E2E в CI (сейчас opt-in `RUN_BROWSER_E2E=1`).

### 9. Данные / каталог
- `[ ]` P1·M — **Per-category schema** (`catalog_schema.py`) + `audit_catalog_schema --json`.
- `[ ]` P2·M — дотянуть параметры по категориям до эталона «диодов» · Datasheet Intelligence (PyMuPDF).
- `[ ]` P2·M — rembg вырезки фото (чистый фон).

### 10. Продуктовый слой
- `[ ]` P2·M — Избранное/закладки · проектная корзина (заказ↔схема/BOM) · экспорт проекта архивом (zip).
- `[ ]` P2·L — Комментарии (статьи/уроки/товары/review) + модерация.

### 11. Доки / UI-мелочи
- `[ ]` P2·S — `API.md` устарел (Engineering Review/ml-training/AI-tool endpoints) · README/About цифры.
- `[ ]` P3·S — favicon (заглушка `data:,`) · cache-bust `?v=` на `<script>` · stale CSS в simulation.html.
- 🔁 `⏸` P1·L — **анти-AI чистка** (~157 датированных меток) + git scrub — ТОЛЬКО по явной команде.

### 12. Инфра / deploy (⏸ post-defense)
- Postgres-миграция (чек-лист готов, ~30 мин) → pgvector/JSONB/FTS · K8s/Helm/Vault · real billing/SSO/2FA.

---

## Рекомендация: ближайшие код-шаги (высокий ROI, низкий риск, не блокер защиты)

1. 🟢 **DRC PCB-слоя (IPC-2221)** — серверно, тестируемо headless, добивает вау-пайплайн (раздел 3).
2. 🟢 **Авто-протокол .md/PDF** (FUNCTIONAL §K.3) — магия на демо + закрывает приложения диплома.
3. 🟢 **GNN train+bench** на свежем корпусе 78 шардов — pitch «нейро-ускоритель» для защиты.
4. 🟢 **Glossary + живой стриминг** ассистента — анти-галлюцинации, сильно для защиты.
5. 🟢 (если решишь по серверу) **demo dry-run** + каркас презентации — это уже P0-защита.

> Крупное (split simulation.html, component registry, Mechanical CAD, multimodal, Postgres) —
> сознательно **после защиты**. Logic-движок и «один клик» требуют твоего «да» на новые
> UI-элементы/навигацию.
