# DOLG CAD — План жёсткого апгрейда

2026-06-02 — большой roadmap всех знаний из Lithium ECAD + KiCad + EasyEDA +
Altium + текущее состояние DOLG. Цель: превратить CAD-часть DOLG из «3D рендер
платы» в полноценный PCB-инструмент уровня small KiCad/Altium-lite.

---

## Что есть в DOLG сейчас

| Часть CAD | Статус | Файл |
|---|---|---|
| Импорт KiCad netlist | ✓ работает | `Dolg_APP/services/cad_import.py` |
| A* autorouter | ✓ Block C1 (11 тестов) | `Dolg_APP/services/pcb_autoroute.py` |
| 3D рендер платы | ✓ Three.js | `shop/static/simulation/scheme-3d.js` (1600 LOC) |
| 3D компоненты | ✓ basic shapes | `scheme-3d-components.js` |
| 3D материалы | ✓ FR-4 + солдер | `scheme-3d-materials.js` |
| Cross-highlight Schema↔3D | ✓ pulse+focus (v22 A) | `scheme-3d.js + simulation.html` |
| Functional Blocks | ✓ (v22 D) | `views_blocks.py + simulation.html` |
| Уровни цепей 1-10 | ✓ (v22 B) | `simulation.html` |
| ЕСКД-рамка | ✓ (v22 C) | `simulation.html` |

**Чего НЕТ:**
- 2D PCB editor (top/bottom view)
- Footprint editor
- Layer stack manager
- Gerber 274X / NC Drill / PnP экспорт
- Differential pairs / length matching
- Polygon pours / power planes
- Via stitching
- Design rules per net class
- 3D STEP импорт для компонентов
- BOM с distributor lookup
- Component variants (DNP)
- Symbol editor (УГО)
- Multi-section components
- Семейства компонентов
- Hierarchical sheets
- Bus connections

---

## Структура улучшений по приоритету

### 🔥 Phase 1 — Production-ready PCB exports (3-4 дня)

**Цель:** научить DOLG генерировать **отправляемые на завод** файлы.

#### 1.1. Gerber 274X экспортёр (1 день)
- На основе текущих connections + autoroute traces
- Формат: ASCII текст с RS-274X кодами
- Слои: top copper, bottom copper, top silk, bottom silk, drill, outline
- 6 .gbr файлов в ZIP
- Reuse: схема трасс из autorouter, footprints из cad_import

#### 1.2. NC Drill (Excellon) (½ дня)
- ASCII формат для CNC-станков
- Список отверстий (через via, mounting holes, pad holes)
- Размер сверла + координаты + plated/non-plated

#### 1.3. Pick & Place (PnP / CPL) (½ дня)
- CSV для машин SMT-монтажа: designator, x, y, rotation, side, footprint
- Top side / bottom side в отдельных файлах
- Формат IPC-7351 или популярный «KiCad CPL»

#### 1.4. BOM с distributor lookup (1 день)
- Сейчас BOM есть, но без поиска в магазинах
- Добавить кнопку «Найти у поставщиков» → Mouser/DigiKey/ChipDip API
- Цены, наличие, MOQ → CSV экспорт для отдела закупок
- Для каждой строки: альтернативы (через AI find_analogs которая уже работает)

#### 1.5. Fabrication notes PDF (½ дня)
- Drill report, stack-up doc, rules summary
- Шаблон для отправки завода

**После Phase 1:** DOLG может реально **сделать плату** — экспорт идёт на JLCPCB, PCBWay, любой завод.

---

### 🚀 Phase 2 — 2D PCB editor (5-7 дней)

**Цель:** альтернатива 3D-просмотру — top/bottom 2D view как в KiCad.

#### 2.1. Канвас 2D PCB editor (2 дня)
- Отдельная страница `/pcb-editor/<project_id>/` или вкладка в simulation.html
- Top view / Bottom view / Both
- Слои: copper, silk, soldermask, paste, drill, outline (видимость toggle)
- Grid snap (0.05 / 0.1 / 0.25 / 0.5 mm)
- Pan/zoom как в схеме

#### 2.2. Footprint placement (1 день)
- Drag-n-drop компонентов из BOM на PCB
- Auto-place по группам (схематические group ↔ PCB clusters)
- Rotate 90° / mirror to bottom

#### 2.3. Manual routing (2 дня)
- Click-and-drag прокладка trace
- Layer switching (Tab)
- Snap to grid / snap to pad
- Width per net (default 0.2 mm)
- Via auto-insert при смене слоя

#### 2.4. Polygon pours / power planes (1 день)
- Залить выбранную область медью с привязкой к net
- Thermal relief connections к pads того же net
- Recompute при move/route

#### 2.5. Via stitching (½ дня)
- Заполнить ground polygon виями для лучшей экранизации
- Auto или manual

#### 2.6. Real-time DRC (½ дня)
- Clearance check (расстояния между разными net)
- Min trace width / min hole
- Подсветка violations cyan/red

**После Phase 2:** в DOLG можно полностью развести плату не выходя из браузера.

---

### 🎯 Phase 3 — Advanced routing (4-5 дней)

#### 3.1. Net classes (1 день)
- Группы net'ов с общими constraints: trace_width, clearance, via_size
- Например «POWER», «SIGNAL», «DIFF_PAIR», «RF»
- ПКМ на net → присвоить class

#### 3.2. Differential pairs (1½ дня)
- Парные net'ы (D+/D-, CLK_P/CLK_N)
- Route как пара — параллельно с фикс. gap
- Auto-skew compensation

#### 3.3. Length matching (1½ дня)
- Constraint: «эти 5 net'ов одной длины ±50µm»
- Serpentine добавляется автоматически
- Поддержка high-speed (DDR, USB, MIPI)

#### 3.4. Auto-router улучшения (1 день)
- Текущий A* — basic. Усилить:
  - Multi-layer planning
  - Rip-up и retry
  - Constraint-aware (net classes)
  - Параллельно для multiple nets

**После Phase 3:** DOLG может разводить high-speed схемы (DDR4, USB 3.0, RF).

---

### 🔧 Phase 4 — Library system (5-6 дней)

#### 4.1. Symbol editor (УГО) (2 дня)
- Создание новых УГО (graphic + pins) только как `draft`-активов
- ГОСТ 2.728-74 примитивы (резистор-прямоугольник, индуктор-зигзаг и т.д.)
- Сохранение не как произвольный `symbol_svg`, а через `assets/eskd/registry.yml`
  с `asset_id`, версией, портами, bbox, hash и golden snapshot
- ЕСКД-экспорт разрешает только `verified`/`certified` активы после проверок и
  ручного review; подробный план: `docs/ESKD_CERTIFIED_ASSET_PLAN.md`

#### 4.2. Footprint editor (2 дня)
- Pad placement (SMD/through-hole)
- Silkscreen drawing
- 3D model attach (.step upload)
- IPC-7351 наименование

#### 4.3. Multi-section components (1 день)
- Один chip = несколько символов (LM358 = 2 op-amp + power pins)
- На схеме разные subсимволы, на PCB один корпус

#### 4.4. Семейства компонентов (½ дня)
- Базовый компонент → virtual copies с разными values
- R0603 → R0603-10K, R0603-100K автогенерация

#### 4.5. Standalone Library Creator UI (½ дня)
- Отдельная страница `/library/` для создания компонентов
- Не в каталоге магазина а отдельный инструмент

**После Phase 4:** DOLG имеет свою библиотеку компонентов, не зависит от внешних.

---

### 🌐 Phase 5 — Manufacturing integrations (3-4 дня)

#### 5.1. JLCPCB integration (1 день)
- Кнопка «Заказать плату на JLCPCB»
- Auto-fill: gerbers ZIP, размер, материал, цвет, количество
- Открыть JLCPCB checkout с готовым проектом

#### 5.2. PCBWay integration (1 день)
- Аналогично JLCPCB
- Free DFM-check report через их API

#### 5.3. SeeedStudio / OSHPark / etc (½ дня)
- Universal gerber export → подходит везде

#### 5.4. STEP экспорт для механики (1 день)
- Текущая 3D-сцена → STEP file
- Для интеграции с SolidWorks/Fusion 360 (механический дизайн корпуса)

**После Phase 5:** DOLG — единая точка от идеи до готовой коробки.

---

### 🤖 Phase 6 — AI/ML enhancement (3-4 дня)

Существующий AI-чат расширяется CAD-контекстом:

#### 6.1. AI Component placer (1½ дня)
- Дать AI описание «5В, 3 регулятора питания, LED индикатор» → автогенерация placement
- Reasoning: density, thermal, EMI
- Использует существующий ai_assistant.py

#### 6.2. AI Route assistant (1½ дня)
- «Эта схема high-current» → AI предлагает widening traces
- «Анализ EMI» → подсветка проблемных участков
- Suggest differential pairs из netlist'а

#### 6.3. AI BOM optimizer (1 день)
- «Оптимизируй BOM для серии 10 шт» → консолидация компонентов
- «Найди аналоги дешевле» → через Mouser/DigiKey
- Уже есть find_analogs — переиспользовать

**После Phase 6:** AI — это «копайлот PCB-разработчика», а не просто чат.

---

### 📐 Phase 7 — Hierarchical schematics (2-3 дня)

#### 7.1. Hierarchical sheets (1½ дня)
- Sheet = subschema с входами/выходами (ports)
- На parent sheet — symbol с pins вместо инлайн-компонентов
- Расширить multi-sheet который уже есть

#### 7.2. Bus connections (1 день)
- Группа сигналов одним толстым проводом (DATA[0..7])
- Bus rip → отдельные net'ы

**После Phase 7:** DOLG может работать с большими схемами (микропроцессоры с десятками шин).

---

## Roadmap по времени

| Phase | Срок | Кто и что |
|---|---|---|
| **Phase 1** (Gerber/NC/PnP/BOM/Fab) | 3-4 дня | Я + ты |
| **Phase 2** (2D PCB editor) | 5-7 дней | Я + ты |
| **Phase 3** (Advanced routing) | 4-5 дней | После Phase 2 |
| **Phase 4** (Library system) | 5-6 дней | Параллельно с 3 |
| **Phase 5** (Manufacturing integrations) | 3-4 дня | После Phase 1 |
| **Phase 6** (AI enhancement) | 3-4 дня | Параллельно |
| **Phase 7** (Hierarchical) | 2-3 дня | Финал |
| **Итого** | ~25-30 дней | До защиты успеем 1-3 + 5 (10-12 дней реалистично) |

---

## Рекомендация — что в первую очередь

Перед защитой реалистично сделать:

1. **Phase 1.1-1.4** — Gerber + NC + PnP + BOM lookup (3 дня)
2. **Phase 2.1-2.2** — 2D PCB editor с placement (3 дня)
3. **Phase 5.1** — JLCPCB integration (1 день)

**Это 7 дней.** На защите можно сказать:

> «DOLG генерирует production-ready Gerber/NC/PnP файлы. Через кнопку «Заказать на JLCPCB» — сразу попадаешь на их checkout с готовым проектом. Полный цикл от схемы до заказа платы — внутри браузера за минуту.»

После защиты — Phase 3-4-6-7 как master's roadmap.

---

## Связано

- [[project-lithium-killer-roadmap]] — Tier 0 закрыт
- [[project-lithium-ecad-reverse]] — оригинальный source
- [[project-master-plan-3weeks]] — пересмотреть с учётом этого
- [[project-future-architecture-notes]] — registry pattern для компонентов
- [[project-post-defense-ai-roadmap]] — Phase 6 продолжается там
