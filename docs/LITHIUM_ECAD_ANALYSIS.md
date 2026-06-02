# Анализ Lithium ECAD vs DOLG — Killer Features Roadmap

2026-06-02 — анализ российского ECAD от ООО «Литиум» как референс для DOLG.

**Источники:**
- [lecad.ru](https://www.lecad.ru/)
- [lecad.ru/features](https://www.lecad.ru/features/)
- [lecad.ru/sync-in-lithium-ecad](https://www.lecad.ru/sync-in-lithium-ecad/)
- [lecad.ru/shop](https://www.lecad.ru/shop/)
- [YouTube обзор](https://www.youtube.com/watch?v=gaI_U5GYfwM)

## Что такое Lithium ECAD

Российский кроссплатформенный (Win + Linux **без Wine**) САПР для разработки печатных плат. Позиционируется как **легковесная альтернатива KiCad/Altium с упором на russian-locale и ГОСТ-оформление**.

**Состоит из 2 приложений:**
1. **Library Creator** — редактор компонентов и библиотек
2. **Project Creator** — редактор схемы + редактор PCB (sync между ними)

**Цены (perpetual, per machine):**
| Тип | Цена | Лимит |
|---|---|---|
| Home-1 | 9 000 ₽ | 200 компонентов, 2 слоя |
| Home-2 | 12 000 ₽ | 350 компонентов, 4 слоя |
| Home-3 | 15 000 ₽ | 8 слоёв |
| Standard | 50 000 ₽ | 200 комп, 2 слоя, коммерческое |
| Extended | 65 000 ₽ | 350 комп, 4 слоя |
| Professional | 80 000 ₽ | 8 слоёв, ∞ компонентов |

**Free версия:** ограничения — нет PnP экспорта, нет ГОСТ-печати, функциональные блоки ограничены.

---

## Главные фишки Lithium ECAD

### 1. **Real-time двусторонняя синхронизация Schematic ↔ PCB** ⭐⭐⭐

**Главный USP** Lithium ECAD. Без неё бы он не отличался от любого ECAD.

Как работает:
- Открыты ОБА окна одновременно (или F4 переключение)
- Клик компонент/цепь на схеме → подсветка того же на PCB
- Клик цепь на PCB → подсветка на схеме
- **Back-annotation**: Shift+End проводника на pad → автоматически создаётся цепь на схеме

### 2. **Уровни цепей (10 levels)** ⭐⭐

Каждой цепи присваивается level. По уточненному inspection-отчету Lithium использует диапазон **0-9** и оператор сравнения в фильтре видимости, например «показать level >= 3». Пользователь фокусируется на одном узле или группе цепей при трассировке.

Пример для адаптации в DOLG: power-цепи level 1, signal цепи level 2, GND level 3. При работе с DC-DC можно показать только power-цепи или скрыть все служебные уровни.

### 3. **Functional blocks** ⭐⭐⭐

Переиспользуемые «макроблоки» — субсхема + готовая трассировка в одном файле. Например «DC-DC 5V→3.3V на LM2596» сохраняется как блок, потом drag-n-drop в новый проект → схема и трассировка появляются сразу.

### 4. **Multi-channel** ⭐⭐

Если в схеме 4 одинаковых канала (например 4 аудио-входа) — трассируешь один, остальные **автоматически копируются** на PCB.

### 5. **Multi-section components (УГО)** ⭐

Один чип = несколько символов на схеме (op-amp dual A/B, логические гейты x4). На PCB это один корпус.

### 6. **Семейства компонентов** ⭐

Базовый компонент + виртуальные копии с перенумерацией = семья (R0603 → R0603-10K, R0603-100K).

### 7. **ЕСКД оформление** ⭐⭐

Принципиальная схема автоматически оформляется по российским ГОСТ (рамка, основная надпись, форматы A4/A3/A2 etc).

---

## Сравнение с DOLG

| Фича | Lithium ECAD | DOLG (сейчас) | Gap |
|---|---|---|---|
| Schematic editor | ✓ | ✓ (mature) | 0 |
| PCB editor | ✓ | частично (CAD import + Three.js 3D) | M |
| **Sync schema↔PCB realtime** | ✓ | ❌ | **L** |
| **Cross-highlight** | ✓ | ❌ | **M** |
| **Back-annotation PCB→schema** | ✓ | ❌ | M |
| **Уровни цепей** | ✓ (0-9 + operator filter) | ❌ | S |
| Net labels | ✓ | ✓ (KiCad-style v17) | 0 |
| **Functional blocks** | ✓ | ❌ | L |
| **Multi-channel copy** | ✓ | ❌ | M |
| **Multi-section components** | ✓ | ❌ | M |
| **Семейства компонентов** | ✓ | ❌ | S |
| **ЕСКД оформление** | ✓ | частично (ГОСТ компоненты есть) | S |
| 3D STEP в компоненте | ✓ | частично (ezdxf, 3D рендер сцены) | M |
| Symbol editor (УГО) | ✓ | ❌ | M |
| Footprint editor | ✓ | ❌ | L |
| Library Creator standalone | ✓ | ❌ (всё в каталоге товаров) | M |
| **Симуляция (ngspice)** | ❌ | ✓ ⭐ | DOLG win |
| **Engineering Review (DRC++)** | базовый ERC/DRC | ✓ 103 правил | DOLG win |
| **Magic Catalog с ML-поиском** | ❌ | ✓ ⭐ | DOLG win |
| **AI-чат** | ❌ | ✓ | DOLG win |
| **Веб-доступ** | ❌ (desktop only) | ✓ | DOLG win |
| **Multi-sheet** | ✓ | ✓ (v17 recovery) | 0 |
| **Autorouter (A*)** | базовый | ✓ (Block C1 A*) | 0 |
| Gerber/NC Drill экспорт | ✓ | ❌ | L |
| Цена | 9k-80k ₽ | бесплатно | DOLG win |

**S** (Small) = 1-2 дня. **M** (Medium) = 3-7 дней. **L** (Large) = 1-3 недели.

---

## Где DOLG **сильнее** Lithium

1. **Симуляция ngspice** (DC/AC/TRAN/Monte Carlo) — Lithium её **не имеет вообще**. У них только ERC.
2. **Engineering Review с 103 правилами** — у них базовый ERC, у нас ML-driven анализ + рекомендации
3. **Magic Catalog с TF-IDF поиском компонентов** — у Lithium статичная библиотека, у нас каталог с ML-поиском по характеристикам
4. **AI-ассистент** — у них нет, у нас Claude/self-hosted чат с контекстом схемы
5. **Веб-приложение** — у них desktop binary, у нас работает в любом браузере включая мобильный
6. **Открытый GitHub** — у них закрытый source, у нас всё под капотом

DOLG **уже впереди по AI/ML/симуляции**. Lithium впереди по **PCB sync и library management**.

---

## Killer-Feature Roadmap для DOLG

### Tier 0 — БЛОКИРУЮЩИЙ приоритет до защиты (killer-фичи)

#### A. Cross-highlight Schema → 3D-сцена (3 дня) ⭐⭐⭐

**Идея:** клик по компоненту в `simulation.html` → автоматическая подсветка соответствующего объекта в `scheme-3d.js` overlay (если 3D открыт). И наоборот.

**Реализация:**
- В `scheme-3d.js` уже есть Three.js рендер компонентов с их IDs
- Добавить `window.SchemeBus` — EventEmitter:
  ```js
  window.SchemeBus.emit('component-selected', { id, source: 'schema' });
  ```
- В `scheme-3d.js` слушать → `highlightById(id)` (изменить material на cyan glow)
- В `selectComponent(id)` simulation.html — emit события
- Reverse: 3D click → emit → simulation.html подсвечивает component на канвасе

**Что юзер увидит на защите:** клик R1 на схеме → R1 на 3D-плате моргает. Wow-эффект.

#### B. Уровни цепей (level 1-10) (1 день) ⭐⭐

**Идея:** каждый wire получает поле `level` (default 1). В сайдбаре «фильтр уровней» — toggle уровней и оператор сравнения (`=`, `>=`, `<=`) по аналогии с Lithium, но в web-first интерфейсе DOLG.

**Реализация:**
- В connection model добавить `level: 1`
- ПКМ на провод → «Уровень цепи» → 1-10
- В header analysis-panel или в hamburger ☰ menu — toggle visibility levels и operator filter
- В `drawConnectionPath` — пропускать если level не в видимом set

**Что юзер увидит:** на сложной схеме скрывает GND/Power линии, видит только signal flow.

#### C. ЕСКД-рамка для PNG/SVG/PDF экспорта (2 дня) ⭐⭐

**Идея:** при экспорте схемы добавлять **рамку по ГОСТ 2.104-2006**:
- A4/A3/A2 размер
- Основная надпись внизу-справа (название, разработчик, дата, номер документа)
- Координатные метки

**Реализация:**
- Уже есть `scheme-export.js` для PNG/SVG/PDF
- Добавить функцию `_drawEskdFrame(ctx, size, meta)` (расширения уже есть для simulation.html PNG)
- В meta — поле `currentProject.eskd_meta` (разработчик, дата, номер) — настраивается в свойствах проекта

**Что юзер увидит на защите:** экспортированная схема **выглядит как настоящий конструкторский документ**.

#### D. Functional blocks lite (3 дня) ⭐⭐⭐

**Идея:** выделить группу компонентов на схеме → **«Сохранить как функциональный блок»** → JSON в библиотеку. Потом из палитры компонентов **drag-n-drop блока** → разворачивается полная подсхема.

**Реализация:**
- Уже есть multi-select (Ctrl+A, Ctrl+C) и `_multiClipboard` (v17)
- Расширить: «Сохранить в библиотеку как блок»
- В user-data Django модель `FunctionalBlock(name, schema_json, preview_svg, user)`
- В components-panel добавить категорию «📦 Мои блоки»
- При drag-n-drop блока — `applySchemeData(block.schema_json, { mergeAtCursor: true })`

**Что юзер увидит на защите:** «Делитель напряжения 5В→3.3В на R1+R2» — drag из библиотеки → схема готова за 1 секунду.

### Tier 1 — После защиты (post-defense roadmap)

#### E. Полноценный PCB editor с трассировкой (3-4 недели)

Сейчас у DOLG есть A* autorouter (Block C1) + 3D Three.js render. Нужно добавить:
- 2D layout editor (top/bottom view)
- Layer stack (2/4/8 layers configurable)
- Footprint editor
- Gerber 274X / NC Drill / PnP экспорт (для отправки на завод)

Это **большой кусок** работы. Покрывает целый раздел диплома (Block C2 или новый Block E1).

#### F. Library Creator standalone (2-3 недели)

Сейчас компоненты живут в Django Catalog. Сделать **отдельный UI** для создания/редактирования компонентов:
- Symbol editor (drag pins, draw shapes)
- Footprint editor (pads, drill holes, silkscreen)
- 3D model attach (.step upload)
- Версионирование (как Library Creator у Lithium)

#### G. Multi-section components (2 дня)

Например op-amp LM358 = 2 секции (A и B). На схеме это 2 отдельных символа с meta `section: A`, `section: B`. На PCB — один корпус. ERC проверяет что секции из одного chip соединены правильно.

---

## Что НЕ делать (антипаттерны)

- ❌ **Копировать UI Lithium 1-в-1** — это плагиат. DOLG имеет свою web-first идентичность.
- ❌ **Реализовать ВСЕ фичи** — это 1-2 года работы для 1 человека. До защиты реалистично только Tier 0 (Killer A+B+C+D = 9 дней).
- ❌ **Лезть в reverse-engineering установщика** — EULA Lithium это запрещает. Только публичная документация + поведение в trial-версии.

---

## Рекомендация

**До защиты делаем Tier 0 целиком** (~9 дней работы):
1. **A — Cross-highlight schema↔3D** (wow-фактор на демо)
2. **B — Уровни цепей** (видимая функция в UI)
3. **C — ЕСКД-рамка экспорта** (диплом-документ выглядит профессионально)
4. **D — Functional blocks lite** (productivity-фича, юзер сразу видит value)

**На защите можно сказать:**
> «Мы анализировали российский Lithium ECAD как референс — у них есть real-time sync schema↔PCB. Мы реализовали аналог как cross-highlight schema↔3D с упрощённой моделью. Дополнительно добавили уровни цепей и функциональные блоки. Чего у Lithium нет — у нас есть симуляция ngspice, AI-ассистент, и веб-доступ.»

**После защиты** — Tier 1 как long-term roadmap (Library Creator, Gerber, footprint editor).

---

## Связано

- [[project-lithium-ecad-reverse]] — original backlog note
- [[project-future-architecture-notes]] — CAD bidirectional sync уже был в backlog'е
- [[project-master-plan-3weeks]] — добавить Block E (Lithium-vs-DOLG) после Block D2
- [[project-post-defense-ai-roadmap]] — Tier 1 идёт сюда
