# План фиксов схематического редактора

## 0. Wire interaction баги (2026-05-30 от юзера)

### 0.1. Hit-detection: «не все участки провода можно выбрать»

**Симптом:** клик по сегменту провода → выделяется не он, а соседний компонент/провод/ничего.

**Гипотезы:**
- `getConnectionAtPosition` (или аналог) — пороговое расстояние слишком маленькое (tolerance ~2-3px), мизерное на zoom < 1.0.
- Hit-priority: компоненты тестируются ДО проводов, и bbox компонента «съедает» близкий wire-сегмент.
- Сегменты построенные через `buildOrthogonalPath` хранятся как edge-list, а hit-test делается по серединам — крайние пиксели сегмента невыделяемы.

**Фикс (когда возьмёмся за router):**
- Расширить tolerance до `max(4, 6 / zoom)` — на мелком zoom больше padding.
- Делать hit-test проводов **раньше** компонентов, если клик НЕ внутри bbox компонента.
- Логировать выбранный сегмент в `console.debug` при `window._dolgDebugSelect = true`.

### 0.2. Wire не двигается drag'ом

**Симптом:** провод можно только редактировать через waypoints (Ctrl+Drag), а перетягивать целиком — нельзя. Юзер: «перемещение проводов осуществляется только через элементы».

**Фикс:**
- В onCanvasMouseDown — если попали в wire-сегмент и нет Ctrl: начать `draggedConnection = conn`, запомнить offset.
- В onMouseMove с draggedConnection — сдвигать **все waypoints + endpoints** (если они не привязаны к pad'у). Endpoints на pad'ах должны быть **resnap'нуты** к ближайшему porty компонента в drop-зоне.
- В onMouseUp — pre-snap к grid, snapshot для undo.

**Acceptance:** клик на середину провода → drag → весь провод перемещается; endpoints резинятся к pad'ам ближайших компонентов.

---



**Создано:** 2026-05-30 (до защиты ~3 недели).
**Цель:** убрать визуальные баги и шум в консоли, расширить набор правил рисования схем без новой ambition.
**Скоуп:** только `simulation.html` редактор. PCB-view, 3D, CAD — не трогаем.

---

## 1. Router проводов (`buildOrthogonalPath`)

### 1.1. Симптом

На скриншоте 2026-05-30: путь C6 → R9 получает 3-4 поворота вместо одного-двух. Лишний «step» — линия идёт вниз, потом вправо, потом коротко вверх, потом снова вправо.

### 1.2. Гипотезы причин

| # | Гипотеза | Файл / функция | Как проверить |
|---|---|---|---|
| 1 | `pickFreeAxisY` обходит препятствие слишком близко, создавая S-петлю | `simulation.html:5478` | Логировать `(initialY, midY)` для конкретного wire'а |
| 2 | `getPortExitDirection` для C6 возвращает «вниз» вместо «вверх» (порт у конденсатора рисуется снизу, а exit — направление от тела к pad) | `simulation.html:5385` | Проверить port-meta для capacitor.SVG |
| 3 | Один из portов уже имеет `waypoints` от перетаскивания — но waypoints не пересчитываются после move компонента | `simulation.html:~4772` | Логировать `conn.waypoints.length` |
| 4 | STUB (20px) слишком большой относительно расстояния до угла, создаёт «вторую полку» | `simulation.html:5501` | Уменьшить до 12 или сделать адаптивным |

### 1.3. Фиксы

- **A.** Логирование (включить через `window._dolgDebugRoute = true`) — добавить `console.debug` в `buildOrthogonalPath` с дампом `pts` массива. Без юзерского репро невозможно угадать конкретную ветку.
- **B.** ✅ Симплификация пост-фактум сделана: collinear-HV + micro-segments < 8px (см. `buildOrthogonalPath` финальный блок 2026-05-30). **НО ЮЗЕР ЗАМЕТИЛ:** правило может быть слишком жёстким — оно «съедает» wp(1470,420) при R9.y=430 и тем самым меняет геометрию проводов так, что они выглядят неестественно. **Решение:** при следующей итерации router'а понизить агрессивность — `MICRO_EPS` сделать настраиваемой (8 → 4 или 0 по флагу), или симплифицировать только если все waypoints внутри тонкого коридора. Заодно: показывать кастомные waypoints как dots на канвасе, чтобы юзер понимал что он «съел» grid-snap'ом.
- **C.** Уменьшить STUB до **12px** для коротких сегментов (если `|fromPos - toPos| < 60px`).
- **D.** Если waypoints пустой И сегмент имеет ровно один поворот — никогда не вставлять промежуточные точки (это L-роут, не Z).

### 1.4. Acceptance

- Сценарий из скриншота: C6 (тело сверху-слева) → R9 (тело снизу-справа) должен дать **2 поворота, 3 сегмента**, а не 4.
- Не сломать существующие положительные кейсы (демо-схемы из `seed_ml_dataset.py`).

---

## 2. Правила рисования схем (DRC расширение)

Сейчас в `Dolg_APP/expert_rules/default_rules.json` ~8 правил. Добавить минимум 5 «школьных» правил которые должен ловить любой schematic editor.

### 2.1. Список

| # | Правило | Severity | Detector |
|---|---|---|---|
| 1 | Wire не должен пересекать тело компонента (overlap) | error | Geometry: для каждого wire-сегмента проверить пересечение с bbox каждого компонента (кроме endpoints) |
| 2 | T-junction (3+ проводов в точке) должен иметь видимый dot | warning | `_renderRouteJoints` уже строит joints — проверить что их 100% покрытие |
| 3 | Два провода не должны пересекаться без junction-dot (crossing != connection) | warning | Сегменты которые пересекаются под 90° без зарегистрированного net-merge |
| 4 | Wire-сегмент длиной < 5px — лишний (микро-стаб от плохого роутинга) | warning | Простая проверка длины |
| 5 | Параллельные провода с расстоянием < 4px (визуально сливаются) | warning | Проход по парам wire'ов с одинаковой ориентацией |
| 6 | Open-end wire (один конец не подключён к компоненту/junction) | error | Уже частично ловится netlist'ом, но не визуализируется на канвасе |
| 7 | Порт компонента используется в 0 wire'ов (висячий пин) | warning | Каждый port должен иметь хотя бы один wire (кроме no-connect маркера) |

### 2.2. Где живёт

- Backend detector: `Dolg_APP/services/expert_detectors.py` (если файл существует, иначе создать).
- Каждое правило — функция `detect_<name>(scheme_data, graph)` возвращает `list[finding]`.
- Frontend визуализация: красные кружки на `_renderRouteJoints` для error, жёлтые для warning.

### 2.3. Acceptance

- Каждое правило срабатывает на минимальной test-схеме (1 баг → 1 finding).
- Чистая демо-схема делителя напряжения — 0 findings.
- В `default_rules.json` все 5 новых правил с russian title/recommendation.

---

## 3. ngspice WASM — `incomplete result` warning

### 3.1. Симптом

В консоли при каждой симуляции схемы с транзистором Q1/Q2 (BJT):
```
[ngspice.wasm returned incomplete result, falling back to JS MNA]
Error: DC-анализ не вернул напряжения узлов: stdout ngspice
не содержит таблицу Node/Voltage.
```

### 3.2. Корень

Наш ngspice.wasm build (см. `shop/static/simulation/ngspice.wasm`) **не содержит BJT-модели** (Q1/Q2 транзисторы из скриншота). Когда netlist имеет `.MODEL QNPN NPN`, WASM пишет ошибку парсинга в stdout, **не печатает таблицу `.op`** — наш `parseDcOutput` (`ngspice-worker.js:173`) возвращает пустой `nodeVoltages`. Дальше `getSimulationResultProblem` ловит `nonGroundNodes.length === 0` и формирует warning. JS-MNA подхватывает.

### 3.3. Фиксы (по приоритету)

| # | Фикс | Трудозатраты |
|---|---|---|
| **A** ✅ Сделано | Снизить severity `console.warn` → `console.info`, убрать `showNotification('⚠')` | 5 мин |
| B | Перед вызовом `runOnNgspice` проверить, есть ли в netlist BJT/MOSFET/JFET — если да, **сразу идти JS-MNA** минуя WASM | 20 мин |
| C | Перекомпилировать ngspice.wasm с включёнными BJT-моделями (требует ngspice 38 + Emscripten setup) | 1-2 дня, риск |
| D | В `parseDcOutput` принимать **именованные узлы** (`out`, `vcc`) — не только цифровые | 30 мин |

### 3.4. Acceptance

После фикса B: схема с Q1/Q2 — **0 warnings в консоли**, симуляция идёт через JS-MNA, результат отображается.

---

## 4. Прочие визуальные фиксы редактора

### 4.1. Engineering Review кнопка

✅ Уже сделано 2026-05-30: «🔍 Анализ» из top-toolbar убрана, теперь «🔍 Review» в analysis-bottom-header рядом с Monte Carlo.

### 4.2. Border-рамки 2-3px

✅ Уже сделано 2026-05-30 (v4 layout): 4 неоновые рамки → одна общая на outer wrapper. Inner-секции разделяются gap'ом и subtle 1px-divider'ами.

### 4.3. Analysis-bottom panel высота по умолчанию

✅ Уже сделано 2026-05-30: дефолт `36px` (только title) → `clamp(180px, 22vh, 260px)`.

### 4.4. Open: «hover-glow» компонентов

Сейчас при hover компонент получает яркую cyan-подсветку через filter. Это контрастирует с новым lightweight стилем. Рассмотреть: subtle outline + scale 1.02 вместо glow.

### 4.5. Open: курсор в режиме «Провод»

Сейчас стандартный crosshair. Хорошо бы — кастомный SVG с иконкой провода (как в KiCad/Eagle).

---

## 5. Порядок работ (предложение)

| Этап | Что | Размер | Acceptance |
|---|---|---|---|
| ✅ Done | Убрать «🔍 Анализ» из top-toolbar, перенести вниз | S | Кнопка ниже |
| ✅ Done | Понизить severity ngspice warning'а до info | S | Консоль чистая на типовых сценариях |
| 1 | Router debug-логирование + сценарий C6→R9 → найти ветку | S | Воспроизведение в коде |
| 2 | Router фикс по выявленной ветке (probably STUB или pickFreeAxisY) | M | Acceptance §1.4 |
| 3 | Detector skip для BJT в netlist → JS-MNA сразу (фикс 3.3.B) | S | Acceptance §3.4 |
| 4 | 5 новых DRC-правил (§2.1 №1, 4, 6, 7 — простые; №2, 3, 5 — посложнее) | M | Acceptance §2.3 |
| 5 | hover-glow refactor (§4.4) — если есть время после остального | S | Subjective |

---

## 6. Что НЕ делаем

- ❌ Не перекомпилируем ngspice.wasm с BJT (риск 1-2 дня, мало profit'а).
- ❌ Не вводим новые компоненты (op-amp, multiplexer и т.д.) — фокус на router/DRC.
- ❌ Не меняем общую тему/цвета — только проблемные места.
- ❌ Не делаем undo/redo переработку — это уже Phase 2.

---

## 7. Связано

- `Dolg_APP/templates/tools/simulation.html` — основной файл редактора (~14000 строк)
- `shop/static/simulation/ngspice-worker.js` — парсер ngspice stdout
- `Dolg_APP/services/expert_rules.py` — runtime для DRC правил
- `Dolg_APP/expert_rules/default_rules.json` — конфиг 8 базовых правил
- `Dolg_APP/services/schematic_graph.py` — graph-validation, T-junction поиск
