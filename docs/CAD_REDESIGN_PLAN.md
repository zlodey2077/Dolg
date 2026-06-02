# CAD Redesign + Multi-section + Import — План переделки

2026-06-02. Юзер недоволен текущим CAD-дизайном (хаотичный тулбар, смесь
рисования и PCB-логики, узкие колонки). Запрос: переделать.

Плюс из Lithium-инспекции:
- **Multi-section components** — детальные docs в Help/unplaced-parts.html
- **Import** через P-CAD 2002 ASCII — docs в Help/interface/import-pcad-project.html
  + import-diptrace-project.html (тоже через P-CAD ASCII)

---

## Часть 1. Redesign CAD UI (R.1 – R.10)

### Проблемы текущего дизайна

1. **Тулбар верха хаотичный** — 18 разных кнопок без иерархии
2. **«Шаблоны ГОСТ / Тест-сценарии / Компоненты»** modal-кнопки смешаны с action-кнопками
3. **Левая панель** очень узкая (76px), подписи мелкие, mix of drawing primitives и PCB tools
4. **Канвас зажат** — много места занимают панели
5. **Стиль кнопок неоднородный** — старые plain без emoji, новые с emoji + cyan
6. **2D рисование** примитивов смешано с PCB-семантикой
7. **Status bar** почти пустой
8. **Layout не как в реальных CAD** — KiCad/Altium/Lithium имеют чёткое разделение:
   - Левая колонка PCB-tools (Trace/Via/Pad/Pour)
   - Top menubar (File/Edit/View/Place/Route)
   - Right panel — Properties / Layers / Nets (вкладки)

### R.1. Mode separation (2 режима)

**«Чертёж» mode** — для технических чертежей, ЕСКД:
- Линии, прямоугольники, эллипсы, текст, размеры
- ГОСТ-рамка, штриховка, шаблоны
- Толщина линий, цвет, шрифт

**«PCB Editor» mode** — для печатных плат:
- Trace / Via / Pad / Copper Pour / Board Outline
- Слои PCB активные
- Footprint library
- Net rendering с net classes

Tab переключатель сверху над тулбаром.

### R.2. Real PCB toolbar (левая колонка, как в KiCad)

- 🔌 **Trace** (T) — провод между pad'ами
- ⭕ **Via** (V) — переходное отверстие
- ⬜ **Pad** (P) — контактная площадка
- 🟧 **Copper Pour** (C) — медная заливка
- 🟦 **Board Outline** (B) — граница платы
- 📦 **Footprint** (F) — менеджер посадочных мест
- 🔢 **Measure** (M) — линейка
- 📍 **Probe** — измерение в Spice-сцепке
- ✖ **Delete** (Del)

Каждая кнопка с тултипом и горячей клавишей.

### R.3. Top menubar полноценный

```
Файл  Правка  Вид  Поместить  Маршрутизация  Инструменты  Справка
```

Как в KiCad — каждое меню разворачивается. **Action-кнопки уходят в menubar**, top bar становится compact.

### R.4. Right panel — 3 вкладки

- 🔧 **Свойства** — выделенный объект (component / trace / pad)
- 📐 **Слои** — 28 PCB layer'ов (расширить с 8)
- 🌐 **Цепи** — список net'ов с цветом, фильтр, click → highlight
- 📚 **Стек слоёв** (отдельная кнопка)
- 🎨 **Net Classes** (отдельная кнопка)

### R.5. Canvas full-width

Убрать всё лишнее с боков. Большая рабочая зона:
- Left 60px PCB toolbar
- Center canvas (flex 1)
- Right 280px properties tabs

### R.6. Status bar расширенный (как в симуляторе)

```
X: 12.5mm Y: 24.3mm | Layer: Top Copper ● | Snap: 0.25mm | Grid: 0.5mm
| Selected: 1 trace | DRC: 0/0 | ✓ Сохранено
```

### R.7. Theme cohesion

- Все кнопки одного стиля: cyan-glow border, emoji в начале
- Размер шрифтов consistent: 0.85rem buttons, 0.78rem hints
- Padding 8px 14px стандарт

### R.8. Onboarding overlay для CAD

При первом заходе — overlay с 3 опциями:
1. 📥 **Импорт из симулятора** (DOLG schema → CAD)
2. 📂 **Импорт KiCad / Lithium / P-CAD** (.kicad_pcb / .lpr / .sch)
3. 🆕 **Создать с нуля** (выбрать шаблон: 2-layer / 4-layer / прототипный)

### R.9. Footprint library drawer

Как Functional Blocks drawer в симуляторе:
- 📦 SMD: 0402, 0603, 0805, 1206, SOIC-8, SOIC-16, TSSOP, QFN-16, QFN-32
- 📦 Through-hole: DIP-8, DIP-14, DIP-16, DIP-28, Header-2pin, Header-4pin
- 📦 Connectors: USB-A, USB-B, USB-C, Micro-USB, RJ45, Audio-3.5mm
- Drag-n-drop на канвас

### R.10. Embedded 3D mini-view

В правом нижнем углу 300×200 окно с 3D-сценой синхронной с 2D.
Hover на компонент в 2D → highlight в 3D. Click 3D → разворот full-screen.

---

## Часть 2. Multi-section components (R.11)

На основе Lithium Help/projects/unplaced-parts.html.

### Концепция

- Один **корпус** (chip) = несколько **символов** на схеме
- Пример: LM358 = 2 op-amp секции (A, B) + 1 power section
- На PCB: один корпус SOIC-8

### Реализация

```javascript
// В schemaJson каждый component имеет:
{
    id: 5,
    type: 'opamp',
    refdes: 'U1',           // общий идентификатор для всех секций
    section: 1,              // 1, 2, 3, ...
    section_name: 'OpAmp_A', // человеко-читаемое
    ports: [...]             // только для этой секции
}
```

Компонент `U1@1`, `U1@2`, `U1@3` — три секции одного chip'а.

### UI

1. **«Неустановленные секции»** меню (как в Lithium):
   - Если компонент имеет 3 секции, а на схеме размещены 2 → 1 unplaced
   - Меню: Схема → Неустановленные секции
   - Таблица: refdes / value / section_name / status
   - Double-click → размещает секцию на текущей странице

2. **ПКМ на компонент → «Добавить секцию»** — для chip'ов с multi-section.

3. **На PCB**: все секции одного refdes → один footprint.

### Кодинг

- Расширить component model с `refdes` + `section` + `section_name`
- В library: компонент описывает `sections: [...]` массив
- ERC: проверять что все pin'ы из всех секций подключены

---

## Часть 3. Импорт из других ECAD (R.12)

На основе Lithium Help/interface/import-pcad-project.html и import-diptrace-project.html.

### Стратегия Lithium

Lithium **не делает прямой импорт** KiCad/Altium/Eagle. Вместо этого:
- **P-CAD 2002 ASCII** — текстовый формат
- Diptrace экспортирует в P-CAD ASCII
- P-CAD сам экспортирует в свой ASCII

Юзер должен сначала **экспортировать в P-CAD ASCII** из своего CAD, потом импортировать в Lithium.

### Что делаем мы

**Вариант А — повторить Lithium стратегию (1 день):**
- Парсер P-CAD 2002 ASCII (.sch + .pcb)
- Импорт через **Файл → Импорт → P-CAD ASCII**
- Открывает оба файла (схема + плата)
- Сопоставляет слои автоматически + ручное mapping для unknown
- Параметры:
  - Ширина линий символов
  - Проверять соответствие имён (только P-CAD оригинал)
  - Игнорировать отсутствие компонентов
  - Объединять в multi-section (для Diptrace)

**Вариант B — прямые парсеры (3-4 дня):**
- KiCad: парсер `.kicad_pcb` (S-expression)
- Lithium: парсер `.lpr/.lsc/.lbo` (XML, мы уже знаем формат!)
- Eagle: парсер `.brd/.sch` (XML)
- Altium: пропустить (binary, сложно)

**Рекомендация:** делать **Lithium import первым** (мы знаем XML формат). 2-3 дня.

### Lithium-импорт алгоритм

1. Файл → Импорт → Lithium ECAD project (.lpr)
2. Прочитать `<lithium_ecad version="2.0.0"/>` тег — проверить версию
3. Парсить `.lsc` → компоненты + соединения → DOLG schema_json
4. Парсить `.lbo` → footprints + traces + layers → DOLG PCB
5. Map Lithium pin types → DOLG pin types (наш v22 ERC)
6. Map Lithium net classes → DOLG net classes (мы сделали)
7. Map Lithium layers → DOLG layers (с возможностью ручного mapping)
8. Open project

На защите: «Откройте Lithium-проект BluePill в DOLG — компоненты, схема, layout, net classes — всё работает».

---

## Roadmap по времени

| Часть | Срок | До защиты? |
|---|---|---|
| R.1 Mode separation | 1 день | ДА |
| R.2 Real PCB toolbar | ½ дня | ДА |
| R.3 Top menubar | 1 день | можно |
| R.4 Right panel вкладки | 1 день | ДА |
| R.5 Canvas full-width | ½ дня | ДА |
| R.6 Status bar | ½ дня | ДА |
| R.7 Theme cohesion | ½ дня | ДА |
| R.8 Onboarding | ½ дня | можно |
| R.9 Footprint library | 1 день | возможно |
| R.10 Embedded 3D | 1 день | после A+B |
| **R.11 Multi-section** | 1½ дня | ДА (приоритет 2) |
| **R.12 Lithium import** | 2-3 дня | ДА (приоритет 4 — WOW для защиты) |
| **Итого** | ~12-14 дней | реалистично 7-8 дней |

## Реалистичный план до защиты

1. **R.1 Mode separation** (1 день) — самое визибельное изменение
2. **R.4 + R.5 + R.6 + R.7** (1½ дня) — right panel + canvas + status bar + theme
3. **R.2 Real PCB toolbar** (½ дня)
4. **R.11 Multi-section** (1½ дня)
5. **R.12 Lithium import** (2-3 дня) — главный wow

**Итого**: 6-7 дней до защиты. DOLG CAD = professional level + can import Lithium projects.

---

## Связано

- [docs/LITHIUM_INSPECTION_REPORT.md](LITHIUM_INSPECTION_REPORT.md) — 20 механик инспекции
- [docs/CAD_HARD_UPGRADE_PLAN.md](CAD_HARD_UPGRADE_PLAN.md) — общий roadmap
- [docs/LITHIUM_ECAD_ANALYSIS.md](LITHIUM_ECAD_ANALYSIS.md) — публичный анализ
- [[project-cad-total-upgrade]] — memory
- [[project-lithium-ecad-reverse]] — memory, status ✅
