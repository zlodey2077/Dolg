# План библиотеки проверенных ЕСКД-активов

Дата: 2026-06-10

Цель: перестроить генерацию схем так, чтобы рамки, основные надписи, УГО,
шрифты, линии и типовые элементы не рисовались моделью "с нуля", а выбирались
из заранее подготовленной, проверенной и версионированной библиотеки активов.

## Главный принцип

Для ЕСКД-режима генератор не рисует рамку, штамп, резистор, конденсатор,
транзистор, выключатель или вывод питания произвольными линиями.

Допустимый поток:

```text
запрос пользователя
  -> семантическая схема: элементы, связи, номиналы, тип документа
  -> подбор asset_id из утвержденного реестра
  -> размещение экземпляров на сетке
  -> ортогональная трассировка связей
  -> автоматический контроль ЕСКД/качества
  -> экспорт
```

Недопустимый поток:

```text
prompt -> SVG/path/line primitives -> "похоже на схему" -> экспорт
```

Если для элемента нет подходящего утвержденного актива, экспорт в ЕСКД-режиме
должен останавливаться с понятной ошибкой: `missing_certified_asset`.

## Что значит "сертифицированный" в проекте

В рамках DOLG слово `certified` означает внутренне утвержденный актив проекта:
геометрия проверена, привязана к источникам, имеет неизменяемый hash, порты,
версию, золотой рендер и отметку нормоконтроля.

Это не заменяет юридический внешний нормоконтроль. Для дипломного и инженерного
контура честная формулировка такая:

- `draft` - черновой актив, можно использовать только в dev-preview;
- `verified` - проверен автоматикой и вручную по источникам, но не подписан как
  проектный эталон;
- `certified` - внутренний эталон DOLG, разрешен для ЕСКД-экспорта;
- `deprecated` - старый актив, старые проекты открываются, новые не создаются.

## Нормативная база

Минимальный набор источников, на который должен ссылаться реестр:

| Зона | Стандарт | Зачем нужен |
|---|---|---|
| Форматы листов | ГОСТ 2.301-68 | A0-A4, внешняя рамка, размеры листов |
| Основная надпись | ГОСТ 2.104-2006 | формы, размеры и реквизиты штампа |
| Линии | ГОСТ 2.303-68 | типы линий, толщина основной линии, единообразие |
| Шрифты | ГОСТ 2.304-81 | чертежные шрифты, размеры, типы |
| Общие правила схем | ГОСТ 2.701-2008 | виды и типы схем, общие требования |
| Электрические схемы | ГОСТ 2.702-2011 | правила выполнения электрических схем |
| Обозначения элементов | ГОСТ 2.710-81 | буквенно-цифровые обозначения: R, C, VT, DA и т.д. |
| УГО общего применения | ГОСТ 2.721-74 | общие графические обозначения и направления |
| Размеры УГО | ГОСТ 2.747-68 | размеры условных графических обозначений |
| R/C | ГОСТ 2.728-74 | резисторы и конденсаторы |
| Полупроводники | ГОСТ 2.730-73 | диоды, светодиоды, транзисторы |
| Коммутационные устройства | ГОСТ 2.755-87 | выключатели, контакты, переключатели |

## Категории активов

Реестр должен разделять активы по назначению. Это важно, потому что к рамке,
штампу, УГО и тексту разные требования.

```text
assets/eskd/
  registry.yml
  frames/gost_2_301/
  title_blocks/gost_2_104/
  line_styles/gost_2_303/
  fonts/gost_2_304/
  symbols/gost_2_721/
  symbols/gost_2_728/
  symbols/gost_2_730/
  symbols/gost_2_755/
  sheet_templates/
  golden/
```

### `frame`

Рамка листа: A4/A3/A2/A1/A0, ориентация, поля, внешняя рамка, рабочая зона,
точки привязки основной надписи.

Требование: генератор может выбрать формат и ориентацию, но не может рисовать
рамку линиями на лету.

### `title_block`

Основная надпись и дополнительные графы. Актив хранит геометрию, поля,
допустимые типы текста, обязательность реквизитов.

Требование: штамп заполняется данными проекта, но его геометрия не меняется.

### `line_style`

Типы линий: основная, тонкая, штриховая, штрихпунктирная, линии связи схемы,
рамка, таблицы.

Требование: элемент не задает stroke напрямую. Он ссылается на `line_style_id`.

### `font`

Набор чертежных шрифтов/метрик. В браузере это может быть приближение, но для
экспорта нужен контролируемый renderer с известными высотами, отступами и
масштабом.

### `electrical_symbol`

УГО с портами, anchoring, допустимыми поворотами, минимальными отступами для
обозначения и номинала.

Примеры для NE555-схемы:

- `resistor.fixed`;
- `resistor.variable`;
- `capacitor.non_polar`;
- `capacitor.polar`;
- `diode.led`;
- `transistor.npn`;
- `switch.no`;
- `ic.timer.ne555.block`;
- `power.vcc`;
- `power.gnd`;
- `terminal.output`;
- `junction.dot`;
- `wire.orthogonal_segment`.

### `sheet_template`

Готовый лист: формат + рамка + основная надпись + зона схемы + правила
заполнения. Это удобно для экспорта "Э3, лист 1" без ручной сборки.

## Схема записи в реестре

Пример для резистора:

```yaml
id: eskd.symbol.resistor.fixed.gost_2_728.v1
category: electrical_symbol
kind: resistor.fixed
status: certified
version: 1
units: mm
source_refs:
  - standard: "ГОСТ 2.728-74"
    section: "резисторы общего применения"
geometry:
  file: assets/eskd/symbols/gost_2_728/resistor_fixed.v1.svg
  sha256: "TO_BE_FILLED_BY_TOOL"
  bbox_mm: {width: 10.0, height: 4.0}
  origin: center
ports:
  - {id: "1", x_mm: -7.5, y_mm: 0.0, direction: left}
  - {id: "2", x_mm: 7.5, y_mm: 0.0, direction: right}
text_anchors:
  refdes: {x_mm: 0.0, y_mm: -5.0, align: center}
  value: {x_mm: 0.0, y_mm: 5.0, align: center}
style:
  line_style_id: eskd.line.signal.main.v1
  font_id: eskd.font.gost_2_304.type_b.v1
transforms:
  allowed: [translate, rotate_0, rotate_90, rotate_180, rotate_270, mirror_x]
  forbidden: [free_scale, skew, recolor, stroke_override]
placement:
  grid_mm: 2.5
  keepout_mm: {left: 2.5, right: 2.5, top: 2.5, bottom: 2.5}
labels:
  allowed_refdes_prefixes: ["R"]
  required_fields: ["refdes", "value"]
approval:
  reviewer: "norm_control"
  approved_at: "2026-06-10"
tests:
  - geometry_hash
  - ports_inside_or_on_bbox
  - allowed_styles_only
  - golden_snapshot_match
```

Пример для листа A4:

```yaml
id: eskd.sheet.a4.portrait.e3.gost_2_301_2_104.v1
category: sheet_template
status: certified
format:
  standard: "ГОСТ 2.301-68"
  code: A4
  width_mm: 210
  height_mm: 297
frame_asset_id: eskd.frame.a4.portrait.gost_2_301.v1
title_block_asset_id: eskd.title_block.form1.gost_2_104.v1
drawing_area_mm:
  x: 20
  y: 5
  width: 185
  height: 252
required_title_fields:
  - designation
  - name
  - document_type
  - scale
  - sheet
  - sheets
  - developer
  - checker
```

## Запреты для генератора

В ЕСКД-режиме валидатор должен блокировать:

- компонент без `asset_id`;
- актив со статусом `draft` или `deprecated`;
- asset hash, который не совпал с реестром;
- SVG/path, которого нет в реестре;
- свободное масштабирование УГО;
- произвольный stroke/color/fill;
- диагональные провода без отдельного утвержденного символа/правила;
- подписи вне допустимых anchors;
- refdes с неправильным префиксом по типу элемента;
- лист без `sheet_template_id`;
- экспорт без основной надписи;
- смешивание внутренней структуры микросхемы и внешней обвязки на одном листе,
  если для этого не создана иерархическая структура листов.

## Алгоритм генерации схемы

### 1. Семантическая модель

Модель/пользователь описывает не рисунок, а состав:

```json
{
  "document_type": "Э3",
  "components": [
    {"id": "R1", "kind": "resistor.variable", "value": "5M"},
    {"id": "C1", "kind": "capacitor.polar", "value": "47uF"},
    {"id": "DA1", "kind": "ic.timer.ne555", "value": "NE555"}
  ],
  "nets": [
    {"name": "TRIG_THR", "pins": [["DA1", "2"], ["DA1", "6"], ["C1", "+"]]}
  ]
}
```

### 2. Resolver активов

`kind + document_type + target_standard_profile` превращается в конкретный
`asset_id`. Если подходящего актива нет, resolver не придумывает замену.

### 3. Sheet planner

Планировщик выбирает `sheet_template_id`, оценивает плотность, решает, нужен ли
один лист или иерархия:

- лист 1: внешняя схема NE555 с обвязкой;
- лист 2: функциональная внутренняя структура NE555;
- parent-symbol связывает оба листа одинаковым списком портов.

### 4. Placement

Размещение работает на сетке. Экземпляр знает:

- `asset_id`;
- `x_mm`, `y_mm`;
- `rotation`;
- `mirror`;
- `ports_global`;
- `label_positions`.

### 5. Routing

Провода строятся ортогонально. Узлы соединения получают `junction.dot`, только
если там есть электрическое соединение. Пересечение без точки считается
визуальным пересечением и требует bridge/разнесения.

### 6. Validation

Перед рендером запускается несколько ворот:

```text
semantic_schema_validation
  -> asset_registry_validation
  -> refdes_validation
  -> placement_validation
  -> routing_validation
  -> eskd_sheet_validation
  -> golden_visual_validation
  -> export_manifest_validation
```

### 7. Renderer

Renderer не рисует УГО сам. Он вставляет геометрию активов, применяет только
разрешенные трансформации и добавляет провода/текст по утвержденным стилям.

### 8. Export manifest

Каждый экспорт должен сохранять manifest:

```json
{
  "sheet_template_id": "eskd.sheet.a4.portrait.e3.gost_2_301_2_104.v1",
  "assets": [
    {
      "asset_id": "eskd.symbol.resistor.fixed.gost_2_728.v1",
      "sha256": "..."
    }
  ],
  "validators": {
    "asset_registry": "pass",
    "eskd_profile": "pass",
    "layout_quality": "pass"
  }
}
```

## Как утверждать новый актив

1. Найти нормативный источник и зафиксировать ссылку/раздел.
2. Создать черновой SVG/DXF в миллиметрах, без CSS-зависимостей и произвольных
   цветов.
3. Задать `bbox`, `origin`, ports, text anchors, keepout.
4. Привязать стили линий и шрифта через id, не через inline-стили.
5. Прогнать автоматическую нормализацию SVG: порядок атрибутов, viewBox,
   округление координат, удаление мусора.
6. Посчитать SHA-256 нормализованной геометрии.
7. Создать golden PNG/SVG snapshot.
8. Прогнать тесты: hash, bbox, ports, стили, snapshot diff.
9. Провести ручной review по чек-листу.
10. Перевести статус `draft -> verified -> certified`.

## Проверки качества до "условного максимума"

### Asset integrity

- Все экземпляры ссылаются на существующий `asset_id`.
- Файл геометрии существует.
- Hash совпадает с реестром.
- Версия актива не плавающая: `v1`, `v2`, но не `latest`.
- Нельзя экспортировать чертеж, где есть `draft`.

### Geometry checks

- Размеры bbox совпадают с метаданными.
- Порты находятся на допустимых точках.
- Точки подключения лежат на сетке.
- Нет скрытых path/clip/filter/mask, которые ломают печать.
- Нет stroke шириной вне разрешенных line styles.
- Нет заливки там, где символ должен быть линейным.

### Text checks

- Обозначение элемента имеет допустимый префикс.
- Номинал не пересекается с УГО и проводами.
- Текст не выходит за рабочую область листа.
- Высота текста соответствует допустимым размерам профиля.
- Основная надпись заполнена обязательными реквизитами.

### Schematic checks

- Нет висячих обязательных выводов.
- Нет неименованных power-net.
- Нет пересечения проводов без явного решения: junction dot, bridge или
  разнесение.
- Нет диагонального "графового" рисования.
- Внутренние блоки микросхемы вынесены в отдельный лист/subcircuit.
- Внешняя обвязка не залезает в корпус микросхемы.

### Sheet checks

- Лист выбран из `sheet_template`.
- Формат, ориентация, рамка и основная надпись согласованы.
- Рабочая область не пересекается со штампом.
- Масштаб и тип документа указаны.
- Номер листа и количество листов валидны.

### Visual regression

- Каждый актив имеет golden snapshot.
- Каждый шаблон листа имеет golden snapshot.
- Для итоговой схемы строится preview, затем считаются:
  - плотность проводов;
  - число пересечений;
  - число label-overlap;
  - доля диагональных сегментов;
  - расстояние от элементов до рамки/штампа.

## Изменение текущего CAD-плана

Старое правило "Symbol editor создает УГО" нужно уточнить:

```text
Symbol editor создает только draft-активы.
ЕСКД-экспорт использует только verified/certified-активы из registry.
Переход draft -> certified проходит через автоматические тесты и нормоконтроль.
```

Текущую ЕСКД-рамку в интерфейсе следует считать prototype/baseline, пока она
не будет вынесена в `assets/eskd/frames` и не получит registry entry, hash,
golden snapshot и validation tests.

## Ближайшие задачи

### P0 - Реестр и валидатор

1. Добавить `assets/eskd/registry.yml`.
2. Добавить JSON/YAML schema для asset entry.
3. Реализовать `Dolg_APP/services/eskd_assets.py`:
   - загрузка реестра;
   - поиск по `kind`;
   - проверка статуса;
   - проверка SHA-256.
4. Реализовать `Dolg_APP/services/eskd_asset_validation.py`.
5. Добавить management command `validate_eskd_assets`.

### P1 - Лист и оформление

1. Вынести A4 portrait frame в `assets/eskd/frames/gost_2_301/`.
2. Вынести основную надпись формы 1 в `assets/eskd/title_blocks/gost_2_104/`.
3. Сделать `sheet_template` для электрической принципиальной схемы Э3.
4. Добавить golden snapshot для A4+штамп.
5. Запретить ЕСКД-export без `sheet_template_id`.

### P2 - Библиотека УГО для NE555-demo

Первый набор должен закрыть именно тот пример, на котором мы уже поймали
плохое "графовое" рисование:

| Kind | Refdes | Стандарт |
|---|---|---|
| `ic.timer.ne555.block` | DA | ГОСТ 2.721/2.702 profile |
| `resistor.fixed` | R | ГОСТ 2.728-74 |
| `resistor.variable` | R | ГОСТ 2.728-74 |
| `capacitor.non_polar` | C | ГОСТ 2.728-74 |
| `capacitor.polar` | C | ГОСТ 2.728-74 |
| `diode.led` | HL | ГОСТ 2.730-73 + project profile |
| `transistor.npn` | VT | ГОСТ 2.730-73 |
| `switch.no` | SB/SA | ГОСТ 2.755-87 |
| `power.vcc` | - | ГОСТ 2.721-74 profile |
| `power.gnd` | - | ГОСТ 2.721-74 profile |
| `terminal.output` | X/XP | ГОСТ 2.721/2.710 profile |

### P3 - Renderer только из активов

1. Запретить ручное создание УГО в ЕСКД-режиме renderer'а.
2. Ввести `asset_instance` вместо свободных `component.shape`.
3. Провода оставить процедурными, но только по утвержденным line styles.
4. Все labels размещать через anchors и collision resolver.

### P4 - Жесткий quality gate

1. Подключить asset validation к `schematic_layout_quality`.
2. Разделить ошибки:
   - `fatal`: нельзя экспортировать;
   - `error`: нельзя считать схему готовой;
   - `warning`: можно показать preview, но нужен review.
3. Добавить отдельный профиль `eskd_strict`.
4. В отчете писать не только "что плохо", но и "какой актив/правило нарушено".

### P5 - DXF/AutoCAD export

1. Экспортировать УГО как blocks с фиксированными именами.
2. Сохранять manifest с `asset_id` и hash.
3. Проверять round-trip через ezdxf: открыть DXF, найти blocks, layers, text.
4. Для AutoCAD runner проверять, что blocks не превратились в произвольные
   exploded primitives без metadata.

### P6 - UI для библиотеки

1. Страница библиотеки активов: статус, стандарт, версия, preview.
2. Режим добавления draft-актива.
3. Режим review: сравнение с golden snapshot и чек-лист.
4. Кнопка "promote to verified/certified" только после прохождения тестов.

## Критерий готовности

Схема считается готовой к ЕСКД-export только если:

```text
all_components_have_certified_assets = true
sheet_template_certified = true
asset_hashes_match = true
refdes_valid = true
layout_quality.errors = 0
eskd_profile.errors = 0
visual_regression.critical_diff = 0
export_manifest_written = true
```

Если хотя бы одно условие не выполнено, система может показать preview, но
должна явно маркировать его как `not_for_eskd_export`.

## Источники

- ГОСТ 2.301-68, форматы: https://www.spds.ru/info/standarts/2.301-68.html
- ГОСТ 2.104-2006, основные надписи: https://files.stroyinf.ru/Data1/47/47608/index.htm
- ГОСТ 2.303-68, линии: https://docs.cntd.ru/document/1200003502
- ГОСТ 2.304-81, шрифты чертежные: https://docs.cntd.ru/document/1200003503
- ГОСТ 2.701-2008, схемы: https://docs.cntd.ru/document/1200069439
- ГОСТ 2.702-2011, электрические схемы: https://docs.cntd.ru/document/1200086241
- ГОСТ 2.710-81, буквенно-цифровые обозначения: https://docs.cntd.ru/document/1200001985/titles
- ГОСТ 2.721-74, УГО общего применения: https://docs.cntd.ru/document/1200007058
- ГОСТ 2.728-74, резисторы и конденсаторы: https://meganorm.ru/Data2/1/4294847/4294847788.htm
- ГОСТ 2.730-73, полупроводниковые приборы: https://meganorm.ru/Data2/1/4294848/4294848038.htm
- ГОСТ 2.747-68, размеры УГО: https://files.stroyinf.ru/Data2/1/4294849/4294849503.pdf
- ГОСТ 2.755-87, коммутационные устройства: https://docs.cntd.ru/document/1200007014
