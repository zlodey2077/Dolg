# DOLG — Единый приоритизированный Roadmap (2026-06-05)

Сводит воедино три источника:
- [MASTER_BACKLOG_20260605.md](MASTER_BACKLOG_20260605.md) — ~130 код-пунктов.
- [FUNCTIONAL_BACKLOG_20260605.md](FUNCTIONAL_BACKLOG_20260605.md) — функционал/данные/защита/контент.
- Идеи юзера: 6 фич (1-я партия) + 14 датасетов + 5 мелких + 2 крупных (2-я партия).

Организовано **по трекам (местам)** и **приоритетам**, с пометкой что идёт
**последовательно**, а что можно **параллельно**, и что даёт **вау за 2-3 сессии**.

> Легенда: `P0` defense-critical · `P1` высокий · `P2` средний · `P3` низко/фан ·
> `S/M/L/XL` объём · `∥` параллелизуемо · `→` есть зависимость · `⏸` post-defense · `💡` идея юзера

---

## 🚨 WAVE −1 — БЛОКЕР (делать ПЕРЕД всем; запрос юзера 2026-06-05)

✅ **DONE 2026-06-05 — Запуск проекта починен, оба .bat надёжны.**
- `start_server.py`: добавлен `free_port()` — снимает **залипший python-сервер на :8000
  целиком (reloader+ребёнок, без респавна)** → гарантия свежего кода, не зомби. Проверено
  живым тестом: HTTP 200 → free_port убил PID [child, reloader] → порт свободен.
- Режим `--local` (без Cloudflare) — оба лаунчера теперь через один robust оркестратор:
  чистый порт + файл-лог (`.tmp_django.log`, переживает закрытие окна) + 120с-ожидание +
  авто-открытие браузера + graceful shutdown.
- `start_local.bat` → `python start_server.py --local`; `start_public.bat` → тот же + туннель.
- Коррекция: Django НЕ использует PyPI-`watchdog` (только StatReloader/Watchman) — ложное
  упоминание убрано; реальный фикс надёжности = `free_port`, не watchdog.
- Осталось опц.: log rotation, `__pycache__` cleanup-флаг (по желанию, не блокер).

✅ **DONE 2026-06-05 — Hot-reload dev-цикл (по выбору юзера).** Реальный cold-start
проекта = **~10-13с** (не 90с — те 90с были артефактом моей сессии: висел headroom-proxy
+ параллельные тесты; proxy убит). Ленивые импорты признаны малополезными (стоимость
размазана: `django.setup()` 6-9с + научный стек 3с). Радикальный рычаг = **не платить за
рестарт**: поставлен **jurigged** (reloadium НЕ поддерживает Py3.14, только ≤3.11; jurigged
работает — проверено HTTP 200 под хот-релоадом). `start_server.py --hot` запускает Django
через jurigged (`--watch` app-папки + `--noreload`); `start_local.bat` теперь `--local --hot`
по умолчанию. Правки тел функций → в живом процессе за <1с. Структурные (URL/model/settings)
→ рестарт окна. Fallback на обычный runserver если jurigged нет.
_Запуск надёжен + dev-цикл почти без рестартов → юзер тестирует и даёт фидбек по панелям._

## 🌊 WAVE 0 — «2-3 сессии → ВАУ» (делать первым)

Максимум видимого эффекта при минимуме затрат. Можно жать почти параллельно.

1. ✅ **DONE 2026-06-05 — Авто-протокол `.md`** (идея #3) — P1·M. `services/protocol_report.py`
   (`render_review_markdown`, реюз `_review_to_dict`/`build_design_review`) + view `project_review_md`
   + URL `projects/review/<id>.md` + ссылка «Протокол .md» в project_review.html + 3 теста.
   Собирает: проект/score/метрики/измерения/findings/рекомендации/обучение → `.md` для диплома и демо.
   _Дальше (опц.): графики в протокол + in-memory вариант из api_engineering_review + PDF из того же .md._
2. **💡 Glossary для нейронки + живой стриминг** (идея #1) — P1·S-M. На «что такое резистор» НН
   тянет из knowledge/glossary (анти-галлюцинация, expert-first), текст печатается читаемой
   скоростью. Надёжность AI = сильный аргумент защиты.
3. **💡 Шизо-тест: допуски + worst-case + Monte Carlo 10000** (идея #6) — P1-P2·M. Реюз
   **Monte Carlo D2 (готов)** + corner-анализ + UI допусков + «паранойя-отчёт» (стыкуется с #1 выше).
   РЭБ/reliability-вау.
4. **Verify-проход §0+§9** код-бэклога — P1·S. Прогнать «✅?» (перенос панелей, PNG-export,
   Engineering Review V2) и installed-but-unwired либы (scikit-rf/axes/csp/sentry) — **вычеркнуть
   реально сделанное**, не делать работу дважды.
5. **💡 Авто-чистка кода** (идея #1 малая) — P2·S. `ruff --fix` + `autoflake` (unused imports/vars)
   + `vulture` (dead code) + orphan templates/static finder. Гигиена + чуть-чуть security. Дёшево.
6. **About/README/диплом цифры** — P1·S. Сверить из БД (`check_demo_ready --json`). Дешёвый win.
7. **💡 Каталог: чистые вырезки фото** (часть Big-1) — P1·M. `rembg` (U2Net, лёгкий) → фон/тени
   убраны → решает **существующую проблему media-quality V2** (РЭБ UGO-изображения). Без NeRF.

**Итого Wave 0:** 4 фичи-вау + 3 гигиены/верификации. Реально 2-3 сессии, заметный демо-эффект.

---

## 🧵 ТРЕКИ ПО МЕСТАМ (что где живёт, приоритет, последовательность, параллельность)

### Track A — 🎓 Защитные материалы `∥` (идёт ПАРАЛЛЕЛЬНО коду, другая «мышца»)
Pre-defense, P0-P1. Последовательно внутри трека:
1. P0 Диплом санитарный (2 главы, чистое оглавление, −таблицы) →
2. P1 Диплом содержательный (введение/гл.1/гл.2, «сеанс проектирования», UML/ERD) →
3. P1 Презентация 20 слайдов-витрина →
4. P1 Речь 7-8 / 10-12 мин + ответы комиссии →
5. P0 Скриншоты + сверка цифр (после фич Wave 0, чтобы скрины были свежими).
> Можно вести как отдельную сессию/делегировать — не блокирует код.

### Track B — 🤖 AI-чат / RAG (высокий вау, pre-defense)
1. **Wave 0 #2** glossary + стриминг (P1) →
2. RAG Phase A (TF-IDF expand на knowledge/rules/projects, `### CONTEXT ###`) — P2·M →
3. Expert-first закрепить (rule_id/evidence/confidence везде) — P1 →
4. structured deep hint («похожие случаи + teacher rule + источник») — P3 →
5. ⏸ RAG Phase B (sentence-transformers + pgvector `→` Postgres), Phase C (reranker+audit).

### Track C — ⚡ Симулятор / reliability (высокий вау, pre-defense)
1. **Wave 0 #3** шизо-тест/допуски/MC10000 (P1-P2) →
2. Probes интерактивные (узел/ток/перегрузка) — P1·M →
3. Undo/redo фикс + DRC дедуп + локализация findings — P2·S (быстрые) `∥` →
4. ⏸ Split `simulation.html` (XL) + component registry + shared rule pack (архитектура).

### Track D — 🗂️ Каталог / данные `∥` (можно параллельно B/C)
1. **Wave 0 #7** rembg вырезки (P1) →
2. `catalog_schema.py` + `audit_catalog_schema --json` — P1·M →
3. Дотянуть параметры по категориям (resistors/ics/transistors/connectors) — P2·M →
4. Datasheet Intelligence (PyMuPDF) — P2·M →
5. Smart-search Phase 1.5 (range-токены/подсветка/facets-sidebar/autocomplete) — P3·S.

### Track E — 🔒 Гигиена кода и безопасность `∥`
1. **Wave 0 #5** авто-чистка (ruff/autoflake/vulture) — P2·S →
2. Security доделать: permission audit + IDOR/org-isolation + Stripe sig + path-traversal +
   AI-tool backend-auth — P1-P2 (HIGH H4/H6/H7/H8/H9 уже закрыты) →
3. rate-limit per-minute, log scrubbing, .dockerignore+Trivy, /healthz — P2 →
4. ⏸ Анти-AI чистка ~157 меток + git scrub — **только по явной команде**, post-defense.

### Track F — 🏗️ Архитектура `⏸` (post-defense, дорого)
Split simulation.html (14k) → component registry (data-driven типы) → shared rule pack
(frontend↔backend один JSON) → split cosmic_theme.css → единое ML-хранилище `DatasetSource`.
> Делать ПОСЛЕ защиты — высокий риск регрессий перед демо.

### Track G — 🛠️ Админка / мониторинг `∥`
Защита `/metrics` (nginx) → psutil runtime metrics + `ops_metrics` → `/staff/ops/` cockpit +
`dolg_*` Prometheus + Grafana + alerts → dataset review queue + ML-curation UI (гистограммы/
soft-delete/disagreement-viewer) → `MLTrainingRun` история.

### Track H — 🛒 Продуктовый слой `∥` (P2-P3, не блокер защиты)
Избранное/закладки → комментарии+модерация → контекстные комменты → проектная корзина →
экспорт проекта архивом (zip).

### Track I — 📐 CAD (P2-P3, не основная фича ВКР)
AutoCAD-parity: Array → Blocks user-defined → offset/trim/extend → штрих-пунктир `∥` →
⏸ CAD total-upgrade (Tier A/B/C, Net Inspector, measure, cross-probe) →
⏸ **💡 Генератор корпусов** (параметрический box+вырезы → STL через trimesh/numpy-stl; sketch-CV = стретч) →
⏸ Mechanical CAD шаблоны + ezdxf + ECAD-импорт →
⏸ **💡 3D-CAD концепт (как AutoCAD 3D / Компас-3D)** — XL, post-defense, отдельное направление:
  полноценное твердотельное/объёмное моделирование (не только 2D-черчение + PCB-3D-viewer что есть
  сейчас). Стек-кандидаты: WebGL/Three.js фронт + ядро геометрии (`OpenCascade.js`/`replicad` для
  B-rep, или `manifold`/CSG для проще), экспорт STEP/STL. Связать с генератором корпусов и
  Mechanical-шаблонами. Это «новый продукт внутри продукта» — планировать как Phase после защиты.

### Track J — 🧠 Multimodal / ML-флагман `⏸` (post-defense, research)
Зависимость: датасеты (Track-data) + torch/YOLO (Windows+py3.14 wheels-риск).
1. **💡 Big-1 Сегментация+3D**: rembg/SAM/YOLOv8 cutout (часть в Wave 0) → перспектива/выравнивание →
   `→` 3D: сперва **матч к существующим параметрическим 3D-корпусам** (9 типов уже есть!),
   InstantNeRF/Point-E/TripoSR — research-tier,低 качество на мелочи → батч + API (Enterprise-питч).
2. **💡 Big-2 Реверсивный цифровой двойник** (фото платы → схема+BOM+SPICE, «Археолог электроники»):
   полный pipeline = patent/IEEE-уровень, **post-defense флагман**. Прототип до защиты — максимум
   узкий: YOLO-детект компонентов + OCR маркировки → черновой BOM (без реконструкции нетлиста).
   Отличный ответ на «а что дальше?».
3. Датасеты (#7-14): до защиты — procedural-only + опц. git-clone #12 (CircuitNet/OpenROAD, без
   Cloudflare); #10 Roboflow (YOLO-разметка) — топ для Big-1/Big-2 после защиты. Legal-first везде.

### Track K — 🎭 «Личность»/easter-eggs `∥` (P3, один toggle-слой)
Собрать в ОДИН переключаемый «характер»-слой (default off, чтобы тон не вредил защите):
- 💡 голосовая TTS-озвучка действий (eSpeak/edge-tts) [+ accessibility-реюз TTS статей] ·
- 💡 рандомные инженерные тосты при запуске sim ·
- 💡 авто-названия графиков в стиле журнала «Радио» (template/LLM) ·
- 💡 дедлайн-виджет с пассивной агрессией — **полезное ядро:** показывать топ нерешённых review-findings
  на дашборде проекта (юмор = опция) ·
- 💡 OLED-виджет с мемами (симулируемый SSD1306) ·
- 💡 умный чайник (idle>15мин → webhook на розетку) — чистый гэг, generic «idle→webhook» хук ·
- 💡 голос робота-археолога (часть Big-2).

---

## 🔀 Карта параллельности (что жать одновременно)

Один «человеко-поток» кода + защита-материалы идут раздельно:

- **Поток 1 (фичи-вау, pre-defense):** Track B → Track C → (Wave 0 распределён сюда).
- **Поток 2 (данные/гигиена, pre-defense) `∥`:** Track D + Track E + Track G — независимы от B/C,
  можно чередовать/жать параллельно в рамках сессии.
- **Поток 3 (защита) `∥`:** Track A — отдельная сессия, не блокирует код.
- **Не трогать до защиты:** Track F (архитектура), Track J (multimodal), большая часть I,
  анти-AI чистка (E.4). Track H/K — по остаточному времени.

Зависимости-блокеры: RAG-B `→` Postgres-миграция · 3D-from-photo `→` сегментация ·
реверс-двойник `→` (сегментация+OCR+GNN) · ECAD-импорт/pgvector/FTS `→` Postgres.

---

## 🗺️ Размещение всех новых идей (2-я партия)

| Идея | Вердикт | Трек | Когда |
|------|---------|------|-------|
| Малая-1 авто-чистка кода/файлов | 🟢 P2·S (ruff/autoflake/vulture) | E (Wave 0) | до защиты |
| Малая-2 авто-названия графиков «Радио» | 🟡 P3·S (template/LLM, toggle) | K | по времени |
| Малая-3 рандомные инженерные тосты | 🟡 P3·S (JSON quips) | K | по времени |
| Малая-4 дедлайн-виджет (пассив-агрессия) | 🟡 P3·S — ядро (top findings) полезно | K + G | по времени |
| Малая-5 умный чайник (idle→розетка) | 🔴 гэг, generic idle→webhook | K | easter-egg |
| **Big-1 Сегментация + 3D-превью** | 🟢 cutout (rembg) до защиты / 🔴 NeRF ⏸ | D (cutout) + J (3D) | split |
| **Big-2 Реверсивный цифровой двойник** | 🔴 флагман patent/IEEE; прототип узкий | J | ⏸ post-defense |
| Big-2 fallback Генератор корпусов→STL | 🟡 параметрический MVP реален | I | ⏸ post-defense |

---

## ✅ Критический путь до защиты (если коротко)

**Обязательно (P0):** Track A (диплом/презентация/речь/скрины/цифры) + demo dry-run + pytest-прогон.
**Вау за 2-3 сессии (P1):** Wave 0 (авто-протокол, glossary+стриминг, шизо-тест, rembg-вырезки) + verify-проход.
**Дотянуть (P2):** security-остаток (permission/IDOR/Stripe/path-traversal), probes, catalog schema-audit.
**После защиты:** архитектура (F), multimodal-флагман (J: сегментация-3D, реверс-двойник, корпуса), CAD-upgrade, анти-AI чистка+git, Postgres→RAG-B.

> Делать **сверху вниз внутри трека**, **между Track A / Поток-2 / Поток-1 — параллельно**.
