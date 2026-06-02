# WORKFRONT_20260602_RESOURCE_DRIVEN: фронт работы после анализа сторонних ресурсов

Дата: 2026-06-02.

Документ фиксирует текущее состояние DOLG и рабочий фронт после анализа Lithium ECAD, инженерных архивов, legal source map, Web-CAD/Qucs-подходов и текущей кодовой базы.

## 1. Что уже есть

### Продуктовые разделы

| Слой | Факт по текущей базе | Комментарий |
|---|---:|---|
| Каталог | 364 товара, 23 категории | Каталог уже достаточно широкий для демо; главная задача теперь не количество, а единое качество карточек и фильтров. |
| Knowledge | 22 статьи, 99 материалов | Хорошая база для AI evidence и обучения. |
| Обучение | 5 маршрутов, 16 уроков, 38 заданий | Практикум уже не пустой; нужно активнее связывать задания с review/симуляцией. |
| Проекты | 28 проектов | После AI-promote проектов стало больше, но все private/draft; нужен проектный кабинет и demo-public сценарии. |
| Reviews | 1 review | Главный недобор: ProjectReview есть как кодовое ядро, но почти не наполнен реальными снапшотами. |
| Измерения | 0 ProjectMeasurement | Measurement core реализован концептуально, но фактических данных нет. |
| SimulationRun | 0 запусков | Async/status/postprocess слой есть, но демо-БД его не показывает. |
| ProjectEvent | 33 события | Журнал сеанса живой, но его нужно насыщать review/simulation/measurement/artifact событиями. |
| AITrainingExample | 72 валидированных примера | Есть curated baseline, но половина примеров без структурной схемы. |
| EngineeringArtifact | 0 артефактов | Artifact ingestion реализован, но корпус пока пустой. |
| Комментарии/модерация | 0 комментариев, 0 cases | Модели и права есть, но demo-data и рабочие сценарии почти отсутствуют. |

### Реально существующие service-layer модули

| Модуль | Что закрывает |
|---|---|
| `Dolg_APP/services/project_review.py` | Connectivity, BOM risk, validity guard, derating, faults, measurements, reliability margin, manufacturing readiness. |
| `Dolg_APP/services/rule_ai.py` | Self AI V2/V3: история до 20 сообщений, session summary, intents, scheme context, evidence, deep hints, quick actions. |
| `Dolg_APP/services/ai_training.py` | Opt-in сбор схем, learning/review/artifact examples, validation, export, similarity, classification, promotion to projects. |
| `Dolg_APP/services/artifact_ingestion.py` | DOCX/PDF/PPTX/DXF/P-CAD net/drc/erc/OLE/DWG/MS14 parsing stubs и нормализация в engineering facts. |
| `Dolg_APP/services/cad_import.py` | SPICE/LTspice/KiCad subset import и preview. |
| `Dolg_APP/services/schematic_graph.py` | NetworkX topology: связность, GND, floating nodes, paths, topology metrics. |
| `knowledge/services/learning_grader.py` | Проверка `math_numeric`, `circuit_build`, `simulation_measure`. |
| `knowledge/services/formula_steps.py` | SymPy формулы и эквивалентность выражений. |
| `knowledge/services/circuit_svg.py` | Schemdraw SVG для учебных схем. |
| `moderation/*` | Cases/reports/actions/restrictions/rules/admin/API локальной и глобальной модерации. |
| `Dolg_APP/services/entitlements.py` | Feature gates Free/Pro/Enterprise/Unlimited. |

## 2. Что уже сильное

1. **Service-layer зрелый.** Формулы, review, AI, import, graph, units, training и moderation уже вынесены из шаблонов в Python-сервисы.
2. **Expert-first подход оформлен.** AI может отвечать не только текстом, но через findings, graph facts, sources, quick actions и session summary.
3. **Каталог стал большим.** 364 товара дают материал для поиска, BOM, карточек, фильтров и демонстрации.
4. **Legal source layer есть.** `knowledge/data/legal_sources.json` уже содержит источники, rule ids, learning topics и related articles.
5. **Инженерный корпус заложен.** Artifact ingestion и AI training services уже позволяют превратить внешние файлы в факты, но их нужно наполнить.
6. **Lithium ECAD дал ясный CAD-вектор.** Самые ценные идеи: pin-to-pin ERC, XML-import, net classes, levels/operator filter, functional blocks, stack-up, production artifacts.

## 3. Что сейчас недоделано

### Критично для демонстрации

- `ProjectReview` почти не используется фактическими demo-data: 1 review при 28 проектах.
- `ProjectMeasurement` пустой, поэтому expected vs measured пока трудно показать на живых данных.
- `SimulationRun` пустой, значит async/status/postprocess слой выглядит как “код есть, данных нет”.
- `EngineeringArtifact` пустой, хотя ingestion слой уже сделан.
- Комментарии и модерация пустые: модели есть, но живой активности нет.
- `manage.py check`, `check_demo_ready --json`, `check_data_integrity --json` не уложились в 60-120 секунд в этой попытке. Это не доказывает падение, но подтверждает проблему тяжелого startup/gate для оперативной работы.

### Критично для инженерности

- Нет pin-to-pin ERC compatibility matrix.
- Нет net classes как семантического слоя цепей.
- Уровни цепей есть в roadmap/частично в CAD-документах, но их нужно довести до понятного `NetInspector`.
- Не хватает real reference measurements/waveforms.
- Manufacturing readiness есть в review-service, но нужно вывести в UI и наполнить facts.
- Artifact ingestion пока не превращен в регулярный data pipeline.

### Критично для AI

- 72 AI examples валидированы, но распределение неровное:
  - `learning_task`: 36;
  - `auto_quality_scheme`: 14;
  - `review_rule`: 14;
  - `curated_demo_case`: 8.
- 36 примеров не имеют структурной схемы/graph-ish features. Для нейронки это слабая половина корпуса.
- `topology_label`, `scheme_family` в модели не заполнены отдельными полями; часть аналитики спрятана в `features`. Для админки и Grafana это неудобно.
- Нейронка уже может быть `deep_hint`, но ей нужен лучший dataset: реальные схемы, review snapshots, measurements, artifact reports.

## 4. Главный рабочий принцип

Каждую следующую фичу делать пакетом:

1. **Продуктовая функция** в CAD/review/lab/project.
2. **Данные и demo-snapshot**, чтобы она была видна не только в коде.
3. **AI/learning связь**, чтобы балабол и практикум использовали новый факт.
4. **Документация и защита**, чтобы фича попадала в диплом, речь и презентацию.

## 5. Приоритетный фронт работы

### P0. Оживить существующий project-session слой

Цель: сделать так, чтобы уже реализованные модели не были пустыми.

Задачи:

1. Создать management command `seed_project_session_demo`.
2. Для 5-7 demo-проектов создать:
   - `ProjectReview`;
   - `SimulationRun` с `success/error` статусами;
   - `ProjectMeasurement`;
   - `ProjectEvent`;
   - BOM snapshot;
   - один `EngineeringArtifact` или import summary.
3. В `/projects/` и review UI показать последний review, measurements и events.
4. Добавить browser/demo сценарий: проект -> симуляция -> измерение -> review -> AI explanation.

Acceptance:

- `ProjectReview >= 6`;
- `ProjectMeasurement >= 10`;
- `SimulationRun >= 5`;
- `EngineeringArtifact >= 3`;
- `ProjectEvent` содержит события `simulation_run`, `measurement_added`, `review_created`, `artifact_ingested`.

### P0. Быстрый gate/startup аудит

Цель: чтобы базовые проверки не висели по несколько минут без обратной связи.

Задачи:

1. Замерить `manage.py check --traceback` и импорт `Dolg_APP.views`.
2. Найти тяжелые импорты в startup: matplotlib/scipy/pandas/torch/pdf parsing/AI.
3. Перенести тяжелые импорты в lazy service functions.
4. Добавить `check_demo_ready --fast` или разделить gate на `--section`.
5. В Grafana/админку вывести длительность gate-команд и dataset jobs.

Acceptance:

- `manage.py check` целится в 10-30 секунд, а не минуты;
- demo/data gates имеют progress/sections;
- тяжелый AI/scientific stack не импортируется при обычном старте views.

### P1. PinERCMatrix

Источник вдохновения: Lithium ECAD 43 ERC pin-pin rules.

Задачи:

1. Добавить pin types: `input`, `output`, `bidirectional`, `power`, `passive`, `open_collector`, `tri_state`, `no_connect`, `undefined`.
2. Создать JSON rule pack `pin_erc_matrix.json`.
3. В graph/review строить соединенные pin pairs.
4. Добавить findings:
   - output-output;
   - power-output;
   - no-connect connected;
   - undefined pin connected;
   - power pins без питания.
5. Перевести findings на русский через `review_i18n`.
6. Добавить learning task “почему выход нельзя соединять с выходом”.

Acceptance:

- Review показывает pin-to-pin finding с `rule_id`, evidence, recommendation.
- AI объясняет ошибку через finding и источник.
- Тесты покрывают минимум 6 pin-pair случаев.

### P1. NetInspector: уровни, классы и фильтр

Источник вдохновения: Lithium levels 0-9 + operator filter, net classes.

Задачи:

1. В `scheme_data` хранить `nets`, `net_classes`, `level`.
2. UI-панель “Инспектор цепей”:
   - список цепей;
   - класс цепи;
   - уровень;
   - компоненты;
   - warnings;
   - быстрый фильтр `=`, `>=`, `<=`.
3. Быстрые presets: `POWER`, `SIGNAL`, `GND`, `MEASUREMENT`.
4. Использовать NetInspector в review, AI-панели и learning grader.

Acceptance:

- На сложной схеме можно скрыть/показать уровни.
- AI отвечает “покажи цепи питания” и опирается на net facts.
- Review снижает score при нарушениях net class constraints.

### P1. External Import Preview V2 / Lithium XML import preview

Источники: Lithium XML, P-CAD DRC/ERC из инженерных архивов, KiCad/LTspice subset.

Задачи:

1. Добавить `lithium_import.py`:
   - `.lsc`: schematic XML subset;
   - `.lbo`: layout preview subset;
   - `.lpr`: project wrapper.
2. Добавить parser для P-CAD DRC/ERC в import preview UI.
3. Unsupported elements не терять: сохранять warnings.
4. После импорта запускать review и сохранять artifact report.
5. AI quick action: “объясни внешний DRC report”.

Acceptance:

- Импорт внешнего XML/DRC создает preview, review findings и artifact evidence.
- Неподдержанные элементы показаны пользователю без 500.
- `EngineeringArtifact` перестает быть пустой таблицей.

### P1. Measurement Core как доказательство

Источники: Qucs/postprocessing, инженерные испытания, reference waveforms.

Задачи:

1. Seed demo measurements для делителя, RC, LED, стабилизатора.
2. Добавить тип `reference_waveform` или расширить `ProjectMeasurement`.
3. В review показывать expected vs measured.
4. В learning использовать сохраненное измерение как ответ.
5. AI команда: “что измерить дальше?” должна ссылаться на реальные measurement records.

Acceptance:

- В проекте есть сохраненные DC/AC/TRAN метрики.
- Review показывает совпадение/расхождение с expected.
- Learning task `simulation_measure` может брать measurement из проекта.

### P2. ManufacturingReadiness

Источники: инженерный архив, Lithium production artifacts, CAD roadmap.

Задачи:

1. Вывести уже существующую `evaluate_manufacturing_readiness` в review UI.
2. Checklist:
   - datasheet;
   - package;
   - footprint/CAD model;
   - SPICE model;
   - ratings;
   - BOM linked product;
   - stock/availability;
   - lifecycle.
3. Добавить “готовность к сборке” в PDF/HTML review.
4. AI command: “что мешает собрать проект?”.

Acceptance:

- Review имеет отдельный раздел “Готовность к сборке”.
- BOM risk и ManufacturingReadiness не дублируются, а дополняют друг друга.

### P2. RequirementsTrace

Источники: архив требований, FURPS+/UML/BPMN.

Задачи:

1. Создать `docs/REQUIREMENTS_TRACE_20260602.md`.
2. Таблица: requirement -> module -> service/view -> test -> demo step.
3. Добавить связи для:
   - каталог;
   - CAD/SIM;
   - review;
   - AI;
   - learning;
   - moderation;
   - subscriptions;
   - project session.
4. Использовать как материал диплома и защиты.

Acceptance:

- В дипломе можно сослаться на трассировку требований.
- Перед защитой проще видеть незакрытые дырки.

### P2. AI dataset cleanup

Цель: подготовить нейробалабола к нормальному росту, а не к хаотичному дообучению.

Задачи:

1. В `AITrainingExample.features` стандартизировать:
   - `scheme_family`;
   - `topology_label`;
   - `complexity_label`;
   - `quality_label`;
   - `source_ids`;
   - `teacher_rules`;
   - `project_origin`.
2. Примеры без структурной схемы пометить как `text_only` и не использовать для graph model.
3. Добавить admin/Grafana counters:
   - validated examples;
   - scheme-backed examples;
   - topology balance;
   - source coverage;
   - dataset import progress.
4. Команды:
   - `validate_ai_dataset --json`;
   - `export_ai_dataset --jsonl`;
   - `collect_good_schemes_for_ai --promote-projects`.

Acceptance:

- Нет смешивания text-only и scheme-backed examples.
- Tiny PyTorch обучается только на структурных схемах.
- Админ видит, что датасет не завис, а реально обрабатывается.

## 6. Что отложить

| Идея | Почему отложить |
|---|---|
| Полный PCB editor уровня KiCad | Большой риск распыления; сначала нужны net classes, layers, DRC и import preview. |
| Gerber/NC/PnP export | Звучит мощно, но без geometry/layer/DRC maturity можно получить опасно красивую заглушку. |
| OR-Tools BOM optimizer | Нужны более качественные supplier data и BOM linkage. |
| RDFLib ontology | Исследовательский слой, лучше после стабилизации компоненты -> схема -> BOM. |
| Большая GNN | Нужен корпус 200-500+ структурных схем, сейчас только 72 AI examples и часть text-only. |
| Автоматическое самообучение live | Нельзя: только opt-in -> validation -> batch training -> fallback на expert rules. |

## 7. Рекомендуемый порядок на 2 недели

### Неделя 1

1. `seed_project_session_demo`.
2. Review/measurement/simulation/artifact demo-data.
3. Gate/startup profiling и lazy imports.
4. Requirements trace markdown.
5. Review UI: ManufacturingReadiness выводить отдельным блоком.

### Неделя 2

1. PinERCMatrix V1.
2. NetInspector V1.
3. P-CAD DRC/ERC import preview -> EngineeringArtifact.
4. AI dataset cleanup и counters.
5. Обновить презентацию/речь: добавить “внешний CAD report -> DOLG review -> AI объяснение”.

## 8. Короткая формулировка для защиты

DOLG развивается как web-среда инженерного сеанса. В отличие от обычного магазина он связывает товар с расчетом, схемой, симуляцией, review, BOM и заказом. В отличие от обычного CAD он хранит evidence: источники, измерения, проектные события, внешние DRC/ERC отчеты, обучающие задания и AI-объяснения. Нейронный слой используется не как финальный арбитр, а как подсказка поверх экспертных правил и данных проекта.
