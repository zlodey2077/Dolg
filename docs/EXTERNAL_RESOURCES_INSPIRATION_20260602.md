# EXTERNAL_RESOURCES_INSPIRATION_20260602: идеи из сторонних ресурсов

Дата: 2026-06-02.

Цель документа: собрать не просто список ссылок, а практический слой вдохновения для DOLG: что можно превратить в код, что использовать в дипломе и презентации, а что оставить только как ориентир из-за лицензий, трудоемкости или риска.

## Рассмотренные группы источников

| Группа | Локальная фиксация | Что дала DOLG |
|---|---|---|
| Lithium ECAD / LECAD | [LITHIUM_INSPECTION_REPORT.md](LITHIUM_INSPECTION_REPORT.md), [LITHIUM_ECAD_ANALYSIS.md](LITHIUM_ECAD_ANALYSIS.md) | Синхронизация представлений, XML-форматы, ERC pin-to-pin, net classes, уровни цепей, функциональные блоки, stack-up, production artifacts. |
| Архив инженерных работ | [ENGINEERING_NOTES.md](ENGINEERING_NOTES.md) | Сеанс проектирования, требования, испытания, reliability/derating, карта отказов, DRC/ERC как внешний evidence. |
| Легальные учебные и технические источники | [LEGAL_RESOURCE_MAP_20260526.md](LEGAL_RESOURCE_MAP_20260526.md), `knowledge/data/legal_sources.json` | Evidence для AI/review/learning: All About Circuits, OpenStax, ngspice, LTspice, KiCad, Django, NetworkX, SymPy, Pint, Lark, Z3, PyTorch. |
| Web-CAD и симуляторы | [UNIFIED_ROADMAP_20260606.md](UNIFIED_ROADMAP_20260606.md), `DEMO_SCENARIO.md` | Qucs-подход к postprocessing: результат симуляции как dataset; WebSocket/async flow; project session вместо разрозненных страниц. |
| KiCad / Altium / EasyEDA / CircuitLab / Flux | roadmap-документы и речь защиты | Разделение ниш: DOLG не копирует промышленный PCB CAD, а связывает каталог, расчет, схему, симуляцию, review, обучение и заказ. |
| Открытые ML-ориентиры | [LEGAL_RESOURCE_MAP_20260526.md](LEGAL_RESOURCE_MAP_20260526.md), [UNIFIED_ROADMAP_20260606.md](UNIFIED_ROADMAP_20260606.md) | PyTorch использовать как deep-hint слой поверх экспертного baseline; датасет строить из собственных схем, review, измерений и opt-in проектов. |

## Главный вывод

DOLG стоит развивать не как "копию KiCad в браузере", а как web-ориентированную среду инженерного сеанса:

`требование -> компонент -> схема -> расчет -> симуляция -> измерение -> review -> BOM -> заказ -> отчет -> обучение`

Сторонние CAD сильны в отдельных частях: PCB, правила, библиотеки, производство. DOLG сильнее там, где эти части связываются с каталогом, обучением, AI-объяснением и коммерческим контуром.

## Идеи, которые можно брать в код

### 1. Импорт Lithium ECAD XML

В инспекции найдено, что `.lpr`, `.lsc`, `.lbo`, `.llb`, `.lt` являются XML-структурами. Это делает импорт гораздо реалистичнее, чем полноценный reverse engineering бинарника.

Что сделать:

- добавить `Dolg_APP/services/lithium_import.py`;
- парсить `.lsc` как schematic subset: components, pins, wires, nets, ports, cache;
- парсить `.lbo` как layout preview: board outline, layers, footprints, traces;
- переводить результат в `scheme_data` + `layout_data`;
- показывать import preview: распознано, неподдержано, warnings;
- запускать `ProjectReview` после импорта.

Почему перспективно:

- сильная demo-фича: "открываем внешний ECAD-проект и прогоняем через DOLG review";
- питает AI и learning реальными структурированными схемами;
- не требует копирования UI Lithium и не требует декомпиляции.

Ограничение:

- использовать только легально доступные файлы и публично наблюдаемые форматы; не копировать код, UI или закрытую документацию.

### 2. Pin-to-pin ERC compatibility

Lithium хранит ERC как матрицу совместимости типов пинов: input, output, power, no-connect, open collector, tri-state и т.д. У DOLG уже есть много логических review-правил, но не хватает именно электрической совместимости выводов.

Что сделать:

- добавить типы пинов в component/symbol metadata;
- завести матрицу совместимости в rule pack;
- при построении графа проверять пары соединенных pin types;
- находить ошибки вроде `Output -> Output`, `Power -> Output`, `NoConnect -> Bidir`;
- выводить finding на русском: правило, evidence, рекомендация.

Эффект:

- Engineering Review становится ближе к промышленному ERC;
- AI может объяснять не "провод плохой", а "выход соединен с выходом";
- learning получает задания по типовым ошибкам подключения.

### 3. Net classes и constraints

Почти все серьезные CAD используют классы цепей. Это не обязательно полноценный PCB-редактор, но уже полезный слой проектной семантики.

Что сделать:

- добавить в `scheme_data` поле `net_classes`;
- параметры класса: `trace_width`, `clearance`, `via_size`, `current_limit`, `voltage_class`;
- в review учитывать constraints при оценке риска;
- в 3D/PCB preview подсвечивать power/signal/RF/differential nets разными стилями;
- добавить фильтры в UI: показать только `POWER`, `SIGNAL`, `GND`, `DIFF_PAIR`.

Эффект:

- мост между схемой, 3D-платой, review и будущим PCB;
- база для routing advisor и manufacturing readiness;
- хорошая тема для диплома: "семантические классы цепей".

### 4. Уровни цепей и operator filter

Lithium использует уровни `0-9` и оператор сравнения. Для DOLG удобнее оставить человекочитаемую адаптацию `1-10`, но добавить оператор: `=`, `>=`, `<=`.

Что сделать:

- у wires/nets хранить `level`;
- добавить режим видимости уровней;
- добавить operator filter в панель анализа;
- быстрые preset-кнопки: power, signal, ground, measurement;
- использовать уровни в AI-панели: "покажи только цепи питания".

Эффект:

- пользователь может разбирать сложную схему постепенно;
- удобно для защиты: одна кнопка меняет визуальную сложность схемы;
- помогает обучению: "найди ошибку только в цепях питания".

### 5. Функциональные блоки с трассировкой

Сейчас функциональные блоки можно использовать как подсхемы. Следующий уровень - хранить не только schematic fragment, но и placement/layout hints.

Что сделать:

- расширить блок: `scheme_fragment`, `bom_fragment`, `default_measurements`, `layout_hint`;
- для повторяемых узлов хранить anchors и suggested placement;
- добавить команду "создать учебное задание из блока";
- для AI использовать блоки как reusable patterns: divider, RC, LED, regulator, NE555.

Эффект:

- DOLG получает "инженерные шаблоны", а не просто компоненты;
- ускоряется сборка схем;
- AI может рекомендовать следующий блок, а не только один компонент.

### 6. Production readiness вместо "просто 3D"

Из Lithium и CAD-roadmap видно, что настоящая сила PCB-среды - не только визуализация, а производство: слои, stack-up, отверстия, Gerber/NC/PnP, DFM.

Что сделать поэтапно:

- добавить `BoardStackup`: материал, медь, толщина, число слоев;
- добавить расширенные PCB layers: copper, mask, paste, silk, courtyard, assembly, keepout, drill;
- формировать drill table и hole list;
- экспортировать fabrication notes PDF;
- позже добавить Gerber/NC/PnP ZIP.

Эффект:

- 3D-визуализация становится инженерной, а не декоративной;
- появляется сильный слайд для диплома: "готовность к производству";
- BOM и заказ платы можно связать с одним проектом.

### 7. Постобработка симуляции как dataset

Qucs-подход важен тем, что график - это не финальная картинка, а набор данных, над которым можно считать формулы.

Что развить:

- markers на графиках;
- формулы `V/I`, `I*V`, RMS, average, peak-to-peak;
- FFT из TRAN;
- Bode из AC;
- CSV export;
- сохранение результата в `ProjectMeasurement`;
- сравнение с reference waveform.

Эффект:

- "симуляция" становится доказательством для review;
- обучение получает задания на измерение;
- AI может отвечать по фактам измерений.

### 8. Artifact ingestion для реальных инженерных файлов

Архивы с дипломными/курсовыми материалами полезны не как текстовый мусор для нейронки, а как структурированные инженерные факты.

Нормализация:

`raw file -> metadata -> extracted entities -> engineering facts -> review/fault/learning dataset`

Что поддерживать:

- DOCX/PDF/PPTX: summary, sections, requirements, formulas;
- DXF: layers, blocks, polylines, dimensions;
- P-CAD netlist: components, packages, nets;
- DRC/ERC reports: violation type, severity, nets, coordinates;
- DWG/MS14: metadata + warning "нужна конвертация".

Эффект:

- DOLG получает корпус инженерных кейсов;
- AI учится на структурированных примерах, а не на случайных фразах;
- review может учитывать внешние CAD-проверки.

### 9. Requirements trace

Инженерные материалы показывают, что хорошая работа всегда связывает требования, реализацию и проверку.

Что сделать минимально:

- markdown/JSON матрица `requirement -> module -> service/view -> test -> demo step`;
- показывать в docs и demo-ready;
- использовать в дипломе как доказательство проектного подхода.

Эффект:

- защита выглядит взрослее: есть не только код, но и трассировка требований;
- проще искать пробелы перед сдачей.

### 10. AI как объясняющий инженерный слой

Лучшие источники подсказывают: AI должен не фантазировать, а работать с evidence.

Что развить:

- AI answer trace: review finding, graph facts, formula result, measurement, BOM fact, legal source;
- похожие случаи из `AITrainingExample`;
- `deep_hint` с confidence и disagreement warning;
- команда "план поиска неисправности";
- команда "создать учебное задание из ошибки";
- запрет на live-self-training без валидации.

Эффект:

- нейробалабол становится полезным формошлепом-инженером;
- финальный verdict остается за expert rules и человеком;
- данные пользователя используются только через opt-in.

## Что использовать в дипломе

### Формулировка новой научно-практической линии

DOLG реализует web-ориентированную информационную модель сеанса проектирования, в которой торговые данные, схема, расчет, симуляция, измерение, экспертная проверка, BOM, заказ и обучение связаны через единый проектный контекст.

### Что вставить в обзор аналогов

- KiCad/Altium: сильны как промышленный CAD, но не являются интернет-магазином и учебным практикумом.
- EasyEDA/LCSC: ближе к связке CAD + каталог, но зависит от конкретной экосистемы поставщика.
- CircuitLab/Qucs: сильны как расчетно-симуляционный слой, но не дают полного коммерческого контура.
- Lithium ECAD: сильная компактная ECAD-среда с синхронизацией, XML-форматами, net classes, ERC и производственными артефактами; для DOLG это источник идей по CAD/PCB-связности.
- Flux/Copilot-подход: AI полезен как слой подсказок, но инженерные факты должны идти из проверяемой модели проекта.

### Что вынести на презентацию

- "DOLG как сеанс проектирования": цепочка от требования до отчета.
- "Источник идей: Lithium ECAD": уровни цепей, pin-to-pin ERC, XML-import, net classes.
- "Источник доказательности: legal sources": AI/review/learning ссылаются на официальные документы и открытые учебники.
- "Источник данных для нейронки": собственные схемы, opt-in проекты, review snapshots, измерения, DRC/ERC, fault cases.

## Что не делать

- Не скачивать и не использовать пиратские книги/архивы из VK/Telegram.
- Не копировать UI Lithium ECAD один-в-один.
- Не декомпилировать бинарники и не тащить чужой код.
- Не обучать нейронку на сырых документах без нормализации и разрешения.
- Не делать нейронку финальным инженерным арбитром.
- Не начинать production PCB-экспорт без минимальных проверок geometry/layers/DRC.

## Приоритеты на ближайший месяц

| Приоритет | Фича | Польза | Сложность | Почему сейчас |
|---|---|---:|---:|---|
| 1 | Pin-to-pin ERC compatibility | 5/5 | 2/5 | Быстро усиливает Engineering Review и AI. |
| 2 | Net inspector + уровни/operator filter | 5/5 | 2/5 | Дает заметный UI-эффект и помогает разбору схем. |
| 3 | Lithium XML import preview | 5/5 | 4/5 | Самая интересная новая CAD-фича и источник данных. |
| 4 | Requirements trace matrix | 4/5 | 1/5 | Быстро усиливает диплом и аудит проекта. |
| 5 | Reference measurements/waveforms | 4/5 | 3/5 | Связывает лабораторию, симуляцию, review и обучение. |
| 6 | Manufacturing readiness checklist | 4/5 | 2/5 | Выгодно для диплома, BOM и review. |
| 7 | Stack-up + расширенные PCB layers | 4/5 | 3/5 | Подготовка к Gerber/NC/PnP и 3D-инженерности. |
| 8 | Artifact ingestion V2 | 4/5 | 4/5 | Нужен корпус данных для AI и обучения. |
| 9 | FaultScenario + план диагностики | 4/5 | 3/5 | Делает AI и обучение практическими. |
| 10 | Gerber/NC/PnP export V1 | 3/5 | 5/5 | Сильно звучит, но требует аккуратного DRC и геометрии. |

## Конкретный следующий пакет

Самый рациональный пакет после анализа ресурсов:

1. `PinERCMatrix`: pin types + матрица совместимости + русские findings.
2. `NetInspector`: классы/уровни/фильтр видимости + facts для AI.
3. `ExternalImportPreview V2`: Lithium XML skeleton + P-CAD DRC/ERC report parser.
4. `ManufacturingReadiness`: checklist datasheet/package/footprint/model/rating/BOM/source.
5. `RequirementsTrace`: markdown/JSON матрица требований, модулей, тестов и demo-шагов.

Этот пакет маленькими шагами приближает DOLG к профессиональному CAD-workflow, но не ломает текущую архитектуру и не требует тяжелой нейронки как основы.
