# Lithium ECAD 2.3.1 — Field Inspection Report

2026-06-02. Установлен и распакован дистрибутив `lithium_ecad-2.3.1.tar.xz` (68 MB) для legal observation (без декомпиляции бинарника — анализ файловой структуры, форматов данных, документации).

> **Метод**: download .tar.xz → распаковка → анализ XML data formats + Help/ HTML docs. Бинарник `bin/launcher` (Qt5/C++) НЕ исполнялся и НЕ декомпилировался.

## Структура дистрибутива

```
lithium_ecad-2.3.1/
├── bin/                  ← Qt5 launcher + libs (libicu, Qt5Xml etc)
├── Fonts/                ← GOST Type B + Simple (Vector + TrueType)
├── Help/                 ← HTML documentation
│   ├── content.html
│   ├── elements/         ← Pin, Pad, Vias, Wire, Net&Level, …
│   ├── interface/        ← UI описание: sch/pcb editor, P&P, DXF
│   ├── libraries/        ← Создание библиотек
│   ├── projects/         ← Function blocks, Net classes, Sync, Multi-channel
│   └── settings/         ← Настройки
├── Libraries/
│   └── DemoLib2.llb      ← Демо-библиотека компонентов (XML)
├── Projects/
│   ├── BluePill/         ← STM32F103 пример (.lpr/.lsc/.lbo)
│   └── NRF24L01/         ← Радиомодуль пример
└── Stacks/               ← Слои PCB: 2/4/6/8 core + foil
    ├── _2_Core.lt
    ├── _4_Core.lt / _Foil.lt
    ├── _6_Core.lt / _Foil.lt
    └── _8_Core.lt / _Foil.lt
```

**Размер чистый**: ~75 МБ. Для сравнения KiCad — 1+ ГБ. Lithium **в 15 раз компактнее** благодаря Qt5 shared libs и компактным XML-форматам.

## ⭐ ГЛАВНОЕ ОТКРЫТИЕ — формат файлов **полностью XML**

```xml
<?xml version="1.0" encoding="utf-8"?>
<lithium_ecad version="2.0.0"/>
<schematic format="2">  ← или <pcb format="1">, <stack format="1">, …
  ...
</schematic>
```

| Расширение | Корневой тег | Что хранит |
|---|---|---|
| `.lpr` | `<project>` | Полный проект (~1 МБ для BluePill) |
| `.lsc` | `<schematic format="2">` | Принципиальная схема (~41 КБ BluePill) |
| `.lbo` | `<pcb format="1">` | PCB layout (~57 КБ BluePill) |
| `.llb` | `<library>` | Библиотека компонентов |
| `.lt` | `<stack format="1">` | Стек слоёв |
| `.lbo`/`.lsc` | + cache | Кэш используемых компонентов |

**Это game-changer для DOLG**: можем сделать **импорт Lithium-проектов** без обращения к Lithium SDK — просто XSL-style парсинг XML. Сразу получаем доступ к экосистеме их юзеров.

## Найденные механики достойные DOLG

### 1. ⭐⭐⭐ **43 ERC правила** (2-буквенные коды Pin-Pin compatibility)

В `.lsc` каждого проекта хранится конфигурация ERC:

```xml
<erc>
  <rule param="BB" value="1"/>   ← Bidirectional ↔ Bidirectional
  <rule param="OO" value="2"/>   ← Output ↔ Output (error!)
  <rule param="BI" value="0"/>   ← Bidir ↔ Input (ok)
  <rule param="WW" value="0"/>   ← Wired-OR ↔ Wired-OR
  <rule param="NB" value="2"/>   ← NoConnect ↔ Bidir (error)
  ...
</erc>
```

**Типы пинов** (1 буква):
- `B` = Bidirectional
- `I` = Input
- `O` = Output
- `H` = HighZ (tri-state)
- `P` = Power
- `N` = NoConnect
- `W` = Wired-OR
- `C` = OpenCollector
- `U` = Undefined

**Значения**: 0 = ok, 1 = warning, 2 = error.

**В DOLG этого НЕТ.** У нас 103 правила (другого типа — логика, не pin-compat). Если добавить — **ERC на уровне индустрии**. ~1 день работы.

### 2. ⭐⭐⭐ **28 предопределённых PCB-слоёв**

В `.lbo` BluePill:

```xml
<layers>
  <layer id="63" name="Top_Courtyard"/>     ← Зона для placement
  <layer id="64" name="Top_Assembly"/>      ← Сборочный
  <layer id="62" name="Top_Keepout"/>       ← Зона запрета
  <layer id="60" name="Top_Finish"/>        ← Финишное покрытие
  <layer id="65" name="Top_Paste"/>         ← Паяльная паста
  <layer id="67" name="Top_Mask"/>          ← Маска
  <layer id="61" name="Top_Glue"/>          ← Клей
  <layer id="66" name="Top_Silk"/>          ← Шёлкография
  <layer id="68" name="Top"/>               ← Медь
  ... (Top mirror — 11 слоёв)
  ... (Bottom mirror — 11 слоёв)
  ... (8 пользовательских слоёв)
</layers>
```

У нас в Tier A было 8 слоёв. Lithium имеет **28**. На защите можно расширить до 16-20 (Courtyard/Assembly/Keepout/Finish/Glue добавить).

### 3. ⭐⭐ **Physical Stack-up model** (toлщины + материалы)

```xml
<stack format="1">
  <description>Standart dual-layer PCB</description>
  <layer type="Signal" thickness="0.018"/>   ← 18µm медь
  <layer type="Core" thickness="1.5"/>       ← 1.5mm FR-4
  <layer type="Signal" thickness="0.018"/>   ← 18µm медь
</stack>
```

Lithium поставляет 7 готовых stack-up'ов: 2/4/6/8 Core + Foil варианты. **У DOLG нет stack-up model вообще** — это нужно для:
- Импеданса трасс
- Тепловых расчётов
- 3D-визуализации с реалистичной толщиной
- Cost estimator

### 4. ⭐⭐⭐ **Net Classes** (минимальные параметры на класс)

Каждая цепь принадлежит классу (default = `Default`). Параметры:
- Ширина проводника по умолчанию
- Минимальная ширина проводника
- Минимальный зазор
- Минимальный диаметр отверстия

DRC использует **минимум** из net class и общих rules. У DOLG net classes **нет**. Это **Tier B** уровень.

### 5. ⭐⭐ **Уровни цепей 0-9 + оператор сравнения**

Я был не прав — у Lithium **10 уровней (0-9), не 1-10**. Плюс **оператор сравнения** ("показать только level >= 3"). У нас в Tier 0 B сделано 1-10 с прямым toggle visibility. Можно улучшить добавив оператор.

### 6. ⭐⭐⭐ **Function Blocks с трассировкой по умолчанию**

Lithium FB содержит:
1. Схема (страница)
2. Символ блока (для главной схемы)
3. **Трассировка по умолчанию** ← *этого у DOLG нет*

При drag-n-drop блока — **PCB-трассировка тоже копируется**, не только компоненты. Plus FB обновляется по reference: если изменил исходный, все instance'ы обновятся.

В DOLG (D Tier 0) у нас только схема. Можно расширить.

### 7. ⭐⭐ **Multi-section components**

`2N7002@1`, `CRYSTAL@3`, `LED@3` — суффикс `@N` обозначает **вариант секции**. Один корпус, разные символы на схеме. Например LM358 = 2 op-amp секции (A, B) + power section.

```xml
<cmp name="LM358@1" pkg="SOIC-8"/>  ← op-amp A
<cmp name="LM358@2" pkg="SOIC-8"/>  ← op-amp B  
<cmp name="LM358@3" pkg="SOIC-8"/>  ← power
```

### 8. ⭐⭐ **Multi-channel + copy tracing**

Lithium имеет inструмент «копирование трассировки одинаковых каналов». Раз развёл USB-D+, второй канал получает идентичную геометрию автоматически.

### 9. ⭐⭐ **Buses**

```
DATA[0..7] на схеме → одна толстая линия → расширяется в 8 net'ов через метки
```

В DOLG нет. Нужно для микропроцессорных схем.

### 10. ⭐⭐ **2 типа текста: Vector + TrueType**

- **Vector** (GOST Type B, Simple) — для PCB silkscreen (экспорт в Gerber)
- **TrueType** — для схемы (читаемость)

Это правильное разделение. У нас в CAD только canvas-native font (browser TrueType). Для production-Gerber придётся добавить Vector.

### 11. ⭐ **Sync schematic↔PCB toggle**

Sync **можно выключить**. При выключенной — независимая работа со схемой и платой. При включении обратно — отличия применяются. Это компромисс между real-time sync и свободой.

### 12. ⭐ **Component cache в .lsc**

```xml
<cache>
  <cmp name="2N7002@1" pkg="SOT23@1"/>
  <cmp name="LD3985MXXR" pkg="SOT23-5"/>
  ...
</cache>
```

Кэш всех использованных компонентов внутри проекта. **Double-click** в panel «Cache» = быстрое добавление ещё одного экземпляра. UX-фишка которой нет у нас.

### 13. ⭐ **Ports питания/земли/сигналов** для cross-page связи

Когда страниц много — порты создают invisible-cross-page net'ы. Имя порта = имя net'а. Список существующих портов в выпадающем — защита от typo.

### 14. ⭐ **Auto-increment имени** (USB_D0, USB_D1, USB_D2…)

При создании net'а с числовым суффиксом — автоматический инкремент. Удобно для параллельных интерфейсов.

### 15. ⭐ **Selection filter panel**

Боковая панель «Выделение» с галочками что разрешено выделять (только цепи / только компоненты / только графика). Удобно для batch-операций.

### 16. ⭐ **2 типа Snap-to-grid**

«Привязать узлы» vs «Привязать центр». Геометрия примитива может измениться или сохраниться. Тонкая UX-деталь.

### 17. ⭐ **Footprint/Symbol manager** только при отключенной sync

При **включённой** sync — менеджер корпусов **недоступен** на плате (компоненты добавляются ТОЛЬКО через схему). При **выключенной** — доступен. Это защита от inconsistency.

### 18. ⭐ **Net Connector** (объединение AGND/DGND)

Spec инструмент — соединитель цепей. На плате выглядит как 2 pad + перемычка. Семантически: «здесь AGND и DGND электрически соединены». DRC учитывает.

### 19. ⭐ **Drill table** + **Hole list** + **Via stitching**

Lithium делает полную таблицу отверстий (drill report). Phase 1.2 нашего CAD-roadmap.

### 20. ⭐ **Импорт DXF + DipTrace + PCAD**

Lithium **уже умеет импорт DipTrace и PCAD** (есть Help/interface/import-pcad-project.html и import-diptrace-project.html). Если есть Help-документация — формат публичный, можно повторить.

## Что у DOLG **сильнее**, подтверждено

- ✅ **Симуляция ngspice** — Lithium вообще не имеет
- ✅ **Engineering Review 103 правила** — Lithium имеет 43 ERC (правда более глубокие per-pin)
- ✅ **Magic Catalog с ML** — Lithium имеет только статичную DemoLib2.llb (1 файл!)
- ✅ **Web-доступ** — Lithium только desktop Qt5
- ✅ **AI** — у Lithium нет
- ✅ **Open source** — Lithium закрытый
- ✅ **Бесплатно** — Lithium от 9 000₽ home / 50 000₽ commercial
- ✅ **Functional Blocks lite** — у нас уже сделано (Tier 0 D)
- ✅ **Уровни цепей** — у нас 1-10 (vs их 0-9), сопоставимо
- ✅ **ЕСКД-рамка** — у нас сделано (Tier 0 C)
- ✅ **Cross-highlight** — у нас Schema↔3D (vs их Schema↔PCB)

## Updated roadmap для CAD upgrade

После инспекции получаем **20 новых идей**. Приоритизация:

### Tier B (1-2 дня каждое)

- **B.1** Pin-Pin ERC compatibility (43 правила) — 1 день
- **B.2** Net Classes (width/clearance/via per class) — 1 день
- **B.3** Расширить PCB-слои до 16-20 (добавить Courtyard/Keepout/Assembly) — ½ дня
- **B.4** Physical Stack-up model (.lt-like XML) — 1 день
- **B.5** Net Inspector panel (с фильтром Selection) — 1 день
- **B.6** Net Connector tool (AGND↔DGND объединение) — ½ дня

### Tier C — wow (2-3 дня каждое)

- **C.1** **Импорт Lithium ECAD проектов** (.lpr/.lsc/.lbo) ⭐⭐⭐ — 2-3 дня. Game-changer.
- **C.2** Multi-section components (`@N` суффиксы) — 1½ дня
- **C.3** Buses + bus-rip — 2 дня
- **C.4** Function Blocks с трассировкой PCB по умолчанию (extension Tier 0 D) — 2 дня
- **C.5** Auto-increment имени net'а — ½ дня

### Tier D — для production / post-defense

- **D.1** Импорт DipTrace + PCAD
- **D.2** Vector font (GOST Type B) для Gerber-экспорта
- **D.3** Component cache panel с double-click добавлением
- **D.4** 2 типа snap-to-grid
- **D.5** Multi-channel + copy tracing для одинаковых блоков

## **Рекомендация для защиты**

Самое впечатляющее для научника:

1. **C.1 — Импорт Lithium проектов** (2-3 дня). На защите: «Открываем готовый Lithium-проект BluePill в DOLG — все компоненты, схема, layout импортированы». Wow-факт.
2. **B.1 — Pin-Pin ERC** (1 день). 43 правила pin-compat = «industry-standard ERC».
3. **B.2 — Net Classes** (1 день). Тоже professional CAD feature.

Итого **4-5 дней до защиты** — DOLG становится **полноценный конкурент Lithium**.

## Связано

- [docs/LITHIUM_ECAD_ANALYSIS.md](LITHIUM_ECAD_ANALYSIS.md) — первичный анализ по публичным источникам
- [docs/CAD_HARD_UPGRADE_PLAN.md](CAD_HARD_UPGRADE_PLAN.md) — общий roadmap
- [[project-lithium-killer-roadmap]] — Tier 0 закрыт
- [[project-cad-total-upgrade]] — общий план
- Распаковано в `/tmp/lithium-inspect/lithium_ecad-2.3.1/` (только для чтения, не используется в проекте)

## EULA

Анализ публично доступного дистрибутива и documentation. Бинарник `bin/launcher` НЕ запускался и НЕ декомпилировался. Формат файлов изучен через анализ XML — open format, не reverse-engineering.
