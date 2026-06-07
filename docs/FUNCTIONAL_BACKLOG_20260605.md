# DOLG — Functional / Non-Code Backlog (свод за всё время)

Составлено 2026-06-05. Парный документ к [MASTER_BACKLOG_20260605.md](MASTER_BACKLOG_20260605.md)
(тот — про код). Здесь — **функционал, контент, данные, защита, идеи** и всё «менее
про код, но применимое к проекту», включая отложенное. Сведено из NEXT_PLAN,
DEFENSE_MATERIALS_REWORK, HF-alternatives, resource-driven workfront'ов и заметок памяти.

> Легенда: `P0..P3` приоритет · `S/M/L` объём · `🔁` давняя просьба · `💡` из нового списка идей юзера · `⏸` отложено/post-defense

---

## A. 🎓 Защитные материалы (диплом / презентация / речь)

Исторический defense-план консолидирован здесь и в `docs/UNIFIED_ROADMAP_20260606.md`.

- `[ ]` **P0 · L — Диплом: санитарная пересборка.** Чистое оглавление (убрать `TOC/PAGEREF`
  field-code мусор), строго **2 главы**, единые стили (Times 14pt, 1.5, отступ 1.25),
  главы с новой страницы, единая нумерация рисунков/таблиц.
- `[ ]` **P0 · L — Сократить таблицы в 2-3× (сейчас 110)** → лишнее в приложения.
  Историю радиоэлектроники → короткий подраздел/приложение.
- `[ ]` **P1 · L — Содержательная пересборка:** введение под текущий проект; гл.1 =
  предметная область→проблемы→аналоги→требования→проектирование; гл.2 = реализация
  (модели БД, сервисы, интерфейсы, AI/ML, админка, проверки); планы развития ОТДЕЛЬНО.
- `[ ]` **P1 · M — Раздел «Сеанс проектирования»** (гл.1) как проектная модель DOLG (см. §J).
- `[ ]` **P1 · M — UML/BPMN/ERD-диаграммы** как академические доказательства (приложение Б).
- `[ ]` **P1 · M — Таблица соответствия требований↔реализации** + таблица ограничений/развития.
- `[ ]` **P1 · S — Список источников → единый ГОСТ-стиль**, убрать дубли нумерации, даты обращения.
- `[ ]` **P1 · L — Презентация: 20 слайдов-витрина** (один объект на слайд, крупный текст
  ≥24pt, реальные скриншоты/метрики/код, без мелких 13pt сносок и декор-рамок).
  Добавить слайды: «сеанс проектирования», admin/monitoring, AI evidence. Финал «Спасибо».
- `[ ]` **P1 · M — Речь: 2 версии (7-8 мин / 10-12 мин)**, строго по слайдам, не читать
  со слайдов; блок по демо-схеме (10 вопросов: GND/floating/делитель/-3дБ/почему AI не verdict).
- `[ ]` **P1 · M — Готовые ответы комиссии** (Django vs SPA, SQLite→Postgres, браузерная
  симуляция, не полноценный PCB CAD, права Pro/Enterprise, AI без галлюцинаций, legal sources).
- `[ ]` **P0 · S — Факты из кода/БД перед каждой сборкой** (НЕ из головы): товары/категории/
  тесты/статьи/demo/learning/AITrainingExample/MLJob/moderation + `check_demo_ready --json`
  + `check_data_integrity --json`.

## B. 🗂️ Качество данных каталога (V3 по эталону карточки)

- `[ ]` **P1 · M — Per-category schema:** `shop/services/catalog_schema.py` (required/recommended
  поля на категорию/тип) + команда `audit_catalog_schema --json` (coverage, missing, англ-значения,
  weak image source, non-clickable chips).
- `[ ]` **P2 · M — Дотянуть параметры по категориям до эталона «диодов»:** resistors (+технология/
  max V/temp coef), ics (+назначение/pins/частота/interface), transistors (+hFE/Vce/Vgs/Rds),
  connectors (+orientation/gender/contact), diodes (русифицировать max_current, surge/leakage).
- `[ ]` **P2 · S — enrich через словари** `CATEGORY_TYPE_SCHEMAS`/`SLUG_OVERRIDES`/`VALUE_TRANSLATIONS`
  (не разовыми патчами).
- `[ ]` **P2 · S — Чипы: 3 класса** (ресурсы/мета/параметры), убрать невнятные labels («Данные»→
  «Параметры»/«Из datasheet»), backend-фильтры для новых полей (protocol/series/pinout/thermal).
- `[ ]` **P2 · M — Media V2:** РЭБ — чистый UGO-style PNG без текста/неона/дуг ИЛИ официальное фото;
  image audit по категориям (real/official/generated/placeholder coverage). No-Wikimedia policy.
- `[ ]` **P2 · M — Datasheet Intelligence** (PyMuPDF/pdfplumber/pandas): извлечение pinout,
  absolute max ratings, thermal, типовых схем включения → `datasheet_extracted`.

## C. 📚 Обучение / база знаний

- `[ ]` **P2 · M — Learning-by-review:** создавать учебную задачу из конкретного finding review
  (не только предлагать готовый урок).
- `[ ]` **P2 · M — Связать `/knowledge/lab/` с текущей схемой:** расчёт→ожидаемое→сравнение с
  фактической метрикой; брать `scheme_data` + последний `simulation_result` без ручного JSON.
- `[ ]` **P2 · M — Задания на стеке:** NetworkX в `circuit_build` (связность/GND/output/изоляция),
  SymPy в `math_numeric` (эквив. формулы + шаги вывода), probes-автозамеры (DC/ток/RMS/-3дБ).
- `[ ]` **P3 · M — Новые области лаборатории:** диагностика неисправностей, проектное review,
  derating/надёжность, контроль сборки. Частичные баллы + диагностика ошибок сборки.
- `[ ]` **P2 · S — `knowledge_sources.json`** curated + связать источники с rule findings,
  learning tracks, AI evidence (legal-first corpus).
- `[ ]` **P3 · S — KaTeX** формулы в уроках/AI-объяснениях (дубль из код-бэклога §6).

## D. 🛒 Продуктовый слой (сообщество / коммерция)

- `[ ]` **P2 · M — Избранное/закладки** для товаров, статей, схем, уроков, задач.
- `[ ]` **P2 · L — Комментарии** (зарегистрированные): к статьям/урокам/товарам/demo-схемам/
  ProjectReview + модерация (`visible/hidden/pending`, жалобы, rate-limit, антиспам).
- `[ ]` **P3 · M — Контекстные комментарии** на инженерных страницах: привязка к компоненту/
  узлу/fault-сценарию/пункту review.
- `[ ]` **P2 · M — Проектная корзина:** заказ привязан к конкретной схеме/BOM.
- `[ ]` **P2 · M — Экспорт проекта архивом:** JSON-схема + BOM + netlist + PDF + изображения (zip).

## E. 🔌 Связность CAD/SIM (функциональная)

- `[ ]` **P1 · M — CAD→SIM общий semantic JSON:** компоненты/pins/wires/nets/labels/GND/BOM.
- `[ ]` **P1 · M — Интерактивные probes в симуляции:** напряжение узла, ток ветви, перегрузка.
- `[ ]` **P2 · M — Import preview V2:** интерактивная карта узлов — подсветка GND/источников/
  output/floating/неподдержанных элементов ПЕРЕД сохранением.
- `[ ]` **P2 · M — DRC уровни:** ошибка/предупреждение/рекомендация (частично есть — дотянуть).
- `[ ]` **P2 · M — Resource-driven фронт:** `ProjectSession`, `PinERCMatrix`, `NetInspector`
  (уровни + operator filter), `ManufacturingReadiness`, `RequirementsTrace`, `Measurement Core`.
- `[ ]` **P2 · S — Связать товары каталога с CAD-шаблонами и статьями.**
- `[ ]` **P3 · M — Fault library расширить:** перепутанный номинал, обрыв, КЗ, неверный LED-резистор,
  перегрев стабилизатора.

## F. 🛠️ Админка / мониторинг / ops

Фронт консолидирован здесь и в `docs/UNIFIED_ROADMAP_20260606.md`.

- `[ ]` **P2 · M — Защитить `/metrics/`** (nginx) + runtime metrics через `psutil` + общий
  `ops_metrics` service-layer.
- `[ ]` **P2 · M — Расширенный `/staff/ops/`** cockpit + custom `dolg_*` Prometheus metrics +
  Grafana dashboards + alerts + export snapshot для защиты.
- `[ ]` **P2 · M — Dataset review queue** для `AITrainingExample`: actions «исправить metadata /
  исключить из graph training / promote» (см. ML-curation в код-бэклоге §0).
- `[ ]` **P3 · S — Бизнес-метрики/счётчики** ML/dataset/moderation в дашборде.

## G. 🤖 AI/ML данные и pipeline (стратегия, не код)

- `[ ]` **P1 · — Expert-first позиционирование** (закрепить везде): любой вывод review/AI имеет
  `rule_id`/severity/evidence/recommendation/confidence + ссылку на расчёт/статью/задание.
  Нейронка — подсказка, НЕ финальный verdict. (Сильная дипломная рамка.)
- `[ ]` **P2 · M — Расширить нейро-корпус до 200-500→1000+ схем** через opt-in `allow_ai_training`,
  импортированные SPICE/KiCad, ProjectReview snapshots, demo_projects. Команды
  `collect_ai_training_examples` + `train_tiny_circuit_ai --include-curated`.
- `[ ]` **P2 · — Dataset governance:** перед дообучением проверять validation errors/warnings,
  coverage (`scheme_data/source_ids/teacher_rules`), topology balance, metadata модели.
- `[ ]` **P3 · — GNN bibliography** (IEEE Xplore): «GNN for circuit analysis», «schematic DRC»,
  «graph embeddings for circuits» — для диплома (не runtime-зависимость).
- `[ ]` **P3 · — structured deep hint:** «похожие случаи + teacher rule + legal source + почему
  модель так решила» в AI-панели.

## H. 📥 Стратегия добычи датасетов (вкл. идеи юзера #7-14)

**Контекст:** HF import зависает (~6 КБ/с, Cloudflare-фильтр). Рекомендация памяти —
**procedural-only** как основной безопасный путь (`python manage.py collect_ai_training_examples --source curated` →3000-5000 схем,
«balanced procedural dataset» как аргумент в дипломе). Внешние датасеты — страховка/будущее.

- `[ ]` **P2 · S — Доработать `import_external_datasets`:** `--mirror`/`HF_ENDPOINT=hf-mirror.com`,
  fallback при <50 КБ/с, поле `license`, curation-gate (см. ML-curation), `aria2c` multi-connection.

**💡 14 источников юзера — куда ложатся** (легальность = legal-first policy проекта обязательна):

| # | Источник | Что даёт | Для чего в DOLG | Когда |
|---|---|---|---|---|
| 7 | Google Dataset Search | мета-поиск тысяч архивов (SPICE, PCB-разметка) | поиск schematic/SPICE-корпуса | ⏸ post-defense |
| 8 | Papers with Code | датасеты статей (CV для электроники, дефекты пайки) | multimodal: детекция деталей/дефектов | ⏸ post-defense |
| 9 | Zenodo | осциллограммы, снимки плат, open-license | schematic/measurement корпус | ⏸ post-defense |
| 10 | **Roboflow Universe** | **готовая YOLO-разметка компонентов** | 🎯 photo-to-schematic / component detection | ⏸ post-defense (топ для multimodal) |
| 11 | Kaggle Datasets | «EDA of Circuit Components» + BOM (фильтр по апвоутам) | каталог/BOM/schematic | ⏸ post-defense |
| 12 | **GitHub EDA** (CircuitNet, OpenROAD) | **git clone — без Cloudflare**, датасеты+скрипты генерации | PCB/schematic, генерация своих данных | 🟡 можно частично до защиты |
| 13 | Mendeley Data | измерения/тесты компонентов (материаловедение) | measurement корпус | ⏸ post-defense |
| 14 | Госархивы (data.gov, opendata.su) | тесты электроники, советские справочники | каталог/справочники РЭБ | ⏸ post-defense (осторожно с лицензией) |

**Вывод по датасетам:** до защиты — procedural + (опц.) одна git-clone выборка (#12, без
Cloudflare). Тяжёлые CV-наборы (#8/#10) и torch/paddle/YOLO упираются в Windows+py3.14 wheels
([[project-semantic-search]] прецедент) → **post-defense, под multimodal-roadmap**. Везде:
проверять лицензию (open/CC), нормализовать перед обучением, не тащить сырьё в training без
очистки (legal-first). Roboflow (#10) — главный кандидат для photo-to-schematic после защиты.

## I. 🔬 Research / конкуренты / вдохновение

- `[ ]` **P3 · — Lithium ECAD / LECAD research** (`LECAD_LITHIUM_ECAD_RESEARCH_TODO`): legal-first
  black-box — UI/сохранения/import-export/логи. Выход: sync-режим CAD/SIM, review поверх схемы,
  compatibility pack. (Import R.12 уже сделан.)
- `[ ]` **P3 · — External resources inspiration** банк идей (`EXTERNAL_RESOURCES_INSPIRATION`):
  Qucs/Web-CAD, KiCad/Altium/EasyEDA/CircuitLab/Flux ориентиры. Не копировать UI/код.

## J. 🧩 «Сеанс проектирования» — академическая рамка (сквозная)

Главная концепция для диплома и защиты:
`проект → схема → симуляция → измерение → review → AI evidence → обучение → BOM → заказ → история`.
DOLG = web-ориентированная среда инженерного сеанса, **не** копия промышленного PCB CAD.
Использовать как нить и в гл.1 диплома, и в речи, и в презентации.

---

## K. 💡 АНАЛИЗ НОВЫХ ИДЕЙ ЮЗЕРА (#1-6, фичи)

Вердикт по соотношению вау/трудозатраты/риск + куда ложится.

### 1. Пояснялка на простом языке для нейронки + «живость» (медленнее текст)
- **Куда:** AI-чат (Self AI V2 / `ai_assistant`). Прямо ложится в **expert-first** (§G) и **RAG Phase A**.
- **Две части:** (a) glossary/FAQ-retrieval — на «что такое резистор» нейронка не выдумывает, а
  тянет из knowledge/glossary (TF-IDF + curated `knowledge_sources.json`); (b) typewriter-стриминг
  с читаемой скоростью (UI-твик). Юзер: «помню, были моменты про это».
- **Вердикт:** 🟢 **HIGH value / LOW-MED effort.** Glossary = маленький curated-датасет + хук
  retrieval; стриминг = JS/CSS. Повышает надёжность (анти-галлюцинации) — сильно для защиты.
- **Приоритет:** P1. Размер: S-M. Сделать рано (пара сессий, заметный эффект).

### 2. Голосовая озвучка действий через TTS (eSpeak/edge-tts offline)
- **Куда:** симулятор; инфраструктура переиспользуется с **TTS статей** (accessibility, код-бэклог §8).
- **Вердикт:** 🟡 Дёшево и запоминается, НО пафосные/мемные реплики рискуют тоном на защите.
  Сделать **toggle «Озвучка действий»** (default off) + два набора реплик: «профессиональный»
  (для защиты) и «весёлый» (1 апреля/easter-egg). Двойная польза: тот же TTS = accessibility-балл.
- **Приоритет:** P3 (фан) / P2 (как accessibility-TTS). Размер: S.

### 3. Авто-генерация протокола (.md/PDF: параметры + графики + визуализация)
- **Куда:** симулятор/review → экспорт. Переиспользует ProjectReview + `simulation_analysis` + matplotlib.
- **Вердикт:** 🟢 **HIGH value / MED effort, выглядит как магия.** Кнопка «📋 Сгенерировать
  протокол» собирает: схема + параметры + sim-результаты + review findings + измерения + графики
  → `.md` (и PDF). Закрывает приложения диплома (Г/Д) И даёт вау на демо. Дёшево-сердито.
- **Приоритет:** P1. Размер: M. Высокий ROI — делать рано.

### 4. OLED-матрица с визуализацией/мемами (каталог/симулятор)
- **Куда:** виртуальный OLED-компонент (SSD1306) в симуляторе — рендер текста/картинок на «экранчике».
  Ложится в component-library + embedded-демо (CircuitPython).
- **Вердикт:** 🟡 Фан, нишево. Как **симулируемый дисплей-виджет** = MED effort, расширяет палитру
  и «device demo». Мемы — easter-egg toggle (тон на защите). Реальное железо — вне web-скоупа.
- **Приоритет:** P3. Размер: M.

### 5. Интерактивный Wi-Fi web-интерфейс с live-ползунками (железо → Python пересчёт)
- **Куда:** частично **уже есть** в симуляторе (what-if слайдеры + live re-run). Новое = **hardware-in-the-loop**:
  реальная ESP32 на Wi-Fi отдаёт страницу со слайдерами → Python пересчитывает.
- **Вердикт:** 🟡 Высокий вау («как в фильмах про хакеров»), но hardware-часть = L + нужно железо.
  В web — отполировать live-телеметрию (WebSocket dashboard). Hardware-демо — стретч/post-defense,
  стыкуется с CircuitPython/ESP32-export (B1 сделан).
- **Приоритет:** P3 (железо) / P2 (in-app телеметрия). Размер: L / M.

### 6. «Инженерное проклятие» / шизо-тестирование (допуски + Monte Carlo 10000)
- **Куда:** симулятор. **Monte Carlo УЖЕ сделан** (D2, 3657 iter/s, NumPy) — идея его **расширяет**.
- **Вердикт:** 🟢 **HIGH value / MED effort.** Добавить worst-case/corner-анализ (стек допусков,
  температурные крайности), UI допусков на компонент, MC до 10000 и «паранойя-отчёт» (стыкуется с
  идеей #3). Сильнейший **РЭБ/reliability**-питч (надёжность при критических данных). Реюзает D2.
- **Приоритет:** P1-P2. Размер: M. Высокий вау.

### Сводка «пара сессий → вау» (по твоему критерию «самое быстрое и важное»)
1. **#3 Авто-протокол** (P1, M) — магия + закрывает приложения диплома.
2. **#1 Glossary + живой стриминг** (P1, S-M) — надёжность AI, анти-галлюцинации.
3. **#6 Шизо-тест/допуски + MC 10000** (P1-P2, M) — reliability-вау, реюз D2.
4. **#2 TTS-toggle** (P3/P2, S) — дёшево, + accessibility-балл.
Это 4 фичи, реально за 2-3 сессии, с заметным демо-эффектом.

---

## L. ⏸ Отложенное / post-defense (cross-ref)

- Multimodal AI (photo-to-schematic/PaddleOCR-VL, CLIP shop-search, Whisper) — код-бэклог §8, датасеты §H.
- K8s/Helm/Vault/Falco/Cosign, real billing/SSO/2FA, Postgres+pgvector+FTS — код-бэклог §13.
- CAD total-upgrade (Mechanical CAD, ECAD-импорт), анти-AI чистка+git scrub — код-бэклог §0/§7.

---

> **Финальный огромный приоритизированный список (по местам + параллельность) — придержан:**
> юзер обещал ещё пару крупных идей. Склею код-бэклог + этот функциональный + все идеи
> в единый roadmap ПОСЛЕ них.
