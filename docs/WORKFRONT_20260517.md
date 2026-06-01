# WORKFRONT_20260517: следующий фронт работ

Цель итерации: закрепить demo-ready состояние после очистки media-слоя и перевести фокус на инженерную связность CAD/SIM, не расползаясь в новые крупные фичи.

## 2026-05-17 update: новый пакет фичи + обучалка + документация

В итерацию добавлен первый "широкий" пакет развития: Engineering Review как ядро, CAD-import как вход внешних схем, measurement core как мост лаборатории и симуляции, self-hosted AI как объясняющий слой.

- Backend: `ProjectReview`, `ProjectMeasurement`, `Dolg_APP/services/project_review.py`, `cad_import.py`, `rule_ai.py`.
- UI/API: кнопка Review в `/projects/`, HTML/PDF-отчет, `/cad/api/import/`, сохранение измерений.
- Learning: track `diagnostika-prostyh-shem` с задачами на GND, перегрев и simulation_measure.
- Search/demo-ready: глобальный поиск находит `Engineering Review`, `CAD Import to Review`, `LTspice`, `KiCad`, `derating`; `check_demo_ready` проверяет новые service-файлы.
- Тесты: targeted suite на review/import/measurements/self-AI/lab sweep/search проходит.

## 2026-05-17 update: scientific stack для Pro-лаборатории

Без пересмотра архитектуры добавлен численный слой для симуляции и лаборатории:

- Dependencies: `numpy`, `scipy`, `matplotlib`, `pandas`, `python-engineering`.
- Backend: `Dolg_APP/services/simulation_analysis.py` с FFT, Bode plot, Monte Carlo tolerance, THD/SINAD/ENOB signal quality, parameter sweep, NumPy MNA fallback и Pandas-статистикой запусков.
- UI/API: быстрые действия под результатом симуляции плюс endpoints `/simulation/api/pro/fft/`, `/simulation/api/pro/bode/`, `/simulation/api/pro/monte-carlo/`, `/simulation/api/pro/signal-quality/`, `/simulation/api/pro/parameter-sweep/`, `/simulation/api/fallback-solve/`, `/projects/api/<id>/simulation-runs/stats/`; ключевые Pro-метрики сохраняются в `ProjectMeasurement`, глобальный поиск находит FFT/Bode/Monte Carlo/SciPy/THD/sweep.
- Knowledge lab: `python-engineering` используется как validation backend; формулы электроники остаются в собственном service-layer.
- Phase 2: PyTorch + GOLEM не ставятся в основной runtime, а уходят в отдельный ML-sprint для GNN/DRC++.

## 2026-05-18 update: lightweight graph/formula/SVG stack перед нейронкой

Перед примитивной нейронкой добавлен легкий слой библиотек, который сразу усиливает review, learning и demo-отчеты, но не тянет тяжелый ML runtime.

- Dependencies: `networkx`, `sympy`, `schemdraw`; PyTorch/GOLEM/scikit-learn пока не добавляются.
- Backend: `Dolg_APP/services/schematic_graph.py` строит граф схемы, проверяет связность, floating nodes, путь до GND, изолированные компоненты, циклы и базовый topology type.
- Learning: `knowledge/services/formula_steps.py` дает SymPy-объяснения и проверку эквивалентных выражений; `knowledge/services/circuit_svg.py` генерирует Schemdraw SVG для LED, делителя, RC, NE555 и транзисторного ключа.
- Reuse: Engineering Review, `rule_ai` и `LearningTask` grader используют один service-layer, поэтому будущая нейронка получит готовые graph/formula признаки.
- Demo-ready: `check_demo_ready --json` проверяет `graph_stack`, `formula_stack`, `circuit_svg_stack`; startup-smoke контролирует, что импорт `Dolg_APP.views` не тянет тяжелые scientific-библиотеки.
- Tests: targeted suites `Dolg_APP.tests.LightweightLibraryIntegrationTests`, `Dolg_APP.tests.EngineeringReviewTests`, `knowledge.tests.LightweightLearningLibraryTests`, `knowledge.tests.LearningModelAndGraderTests` проходят.

## 2026-05-18 update: expert-first stack

После graph/formula слоя добавлен объяснимый экспертный контур. Новый порядок развития: сначала экспертные правила и факты, затем constraint/optimization, и только после этого нейронный deep analysis.

- Dependencies: `jsonschema`, `rule-engine`, `pint`, `lark`, `z3-solver`, `scikit-fuzzy`; OR-Tools/RDFLib/PyTorch/GOLEM в основной runtime не добавлены.
- Rule core: `Dolg_APP/expert_rules/default_rules.json` + `Dolg_APP/services/expert_rules.py`; каждый finding хранит `rule_id`, severity, evidence, recommendation и confidence.
- Unit core: `Dolg_APP/services/engineering_units.py` через Pint принимает `10k`, `6.8kOhm`, `2.5мА`, `100нФ`, русские и ASCII-единицы.
- Constraint core: `Dolg_APP/services/constraint_solver.py` через Z3 подбирает варианты LED-резистора, делителя, RC cutoff, NE555, стабилизатора и теплового запаса.
- Import/risk core: `Dolg_APP/services/cad_parsers.py` переводит SPICE/LTspice строки через Lark, `risk_scoring.py` добавляет fuzzy risk label.
- Reuse: `ProjectReview` выводит expert findings и fuzzy-risk, `rule_ai` отвечает по `Expert trace`, learning/lab используют общий unit-service.
- Demo-ready: `check_demo_ready --json` проверяет `expert_stack` и smoke `rule_pack/rule_engine/pint/lark/z3/fuzzy`.

## 2026-05-19 update: import preview + Learning-by-review

Следующий хвост закрыт в том же паттерне "фича -> обучалка -> документация": импорт внешней схемы теперь не заканчивается сухим JSON, а ведет пользователя к инженерной проверке и практикуму.

- CAD UI: `/cad/` получил server-side import preview для LTspice/SPICE/KiCad-subset. Панель показывает компоненты, узлы, неподдержанные строки, analysis directives и предупреждения до сохранения.
- Review flow: кнопка сохранения создает `SchematicProject`, сразу формирует `ProjectReview` и открывает HTML-отчет.
- Service-layer: `Dolg_APP/services/cad_import.py` добавляет `build_import_preview_details`, а `Dolg_APP/services/learning_by_review.py` связывает findings/topology с опубликованными уроками.
- Learning-by-review: страница `ProjectReview` показывает практические уроки по найденной ошибке, например отсутствующий GND, делитель, RC-цепь, LED-индикатор или derating.
- Demo-ready: `check_demo_ready --json` проверяет `cad_import_preview_details` и smoke вызова Learning-by-review.
- Tests: `EngineeringReviewTests` покрывает preview, сохранение проекта, suggestions на странице review; `Dolg_APP/tests_browser.py` добавляет optional Playwright-smoke для import -> review -> learning.

## 2026-05-19 update: Media Quality Gate

Первым новым пакетом после review/import внедрен контроль качества изображений каталога.

- Dependencies: `ImageHash` + `PyWavelets` поверх уже используемого Pillow; OpenCV пока не добавлен в runtime, чтобы не утяжелять старт.
- Backend: `shop/services/media_quality.py` проверяет active product image без изменения БД: policy, файл, читаемость, размер, entropy, luma range, edge density, perceptual hash и `quality_score`.
- Data checks: `check_data_integrity --json` добавляет `catalog.media_quality`; `check_demo_ready --json` добавляет верхнеуровневый `media_quality`.
- Текущее состояние: 89 изображений проверены, `average_score=100`, `error_count=0`, `warning_count=0`, `imagehash_available=true`.
- Tests: `ProductImagePolicyTests` проверяет, что generated PNG проходит gate, а tiny local asset проваливается как `image_too_small/image_near_blank`.

## Текущая база

- РЭБ-каталог: 43 товара.
- Активные изображения каталога: 67 проверенных реальных фото в `products/verified/`, 13 точных SVG fallback и 9 generated PNG; legacy Commons-команда отключена, прямые `commons/curated` пути не используются.
- `check_data_integrity --json`: 0 ошибок; no-Wikimedia policy и Media Quality Gate включены в аудит.
- `check_demo_ready --json`: OK; URL smoke, media-policy, scientific stack, lightweight graph/formula/SVG smoke и expert stack проходят.
- Демо-данные: 12 demo-схем, 21 статья энциклопедии, 50 материалов, 4 learning tracks, 13 уроков, 29 заданий.
- `python manage.py check`: 0 ошибок.
- `python manage.py test Dolg_APP.tests knowledge.tests shop.tests --keepdb -v 1`: 123 тестов OK.
- `python manage.py test --keepdb -v 1`: полный discovery-прогон в текущем окружении уперся в 15-минутный таймаут; gate на итерацию разбит по приложениям.

## P0: закрыть хвосты перед новым архивом

1. Media-policy V2:
   при необходимости добавить allowlist официальных изображений производителей/дистрибьюторов поверх локальных assets/generated-заглушек, но без Wikimedia и без неподтвержденных product-shot.

2. Удержать запрет Commons:
   regression-тесты должны проверять, что `import_commons_product_photos` отключен, а `products/commons/*` и `products/curated/*` не проходят demo-ready.

3. Ручной demo-pass:
   пройти `/demo/` по маршруту каталог -> энциклопедия -> CAD -> симуляция -> BOM -> корзина.

4. Скриншоты диплома:
   переснять `docs/diploma_assets/screenshots/` после проверки media и demo-pass.

5. Чистый запуск:
   проверить `run_dolg.bat` двойным кликом и зафиксировать результат в `docs/TESTS_AND_REPORTS.md`.

## P1: CAD/SIM связность

1. Довести CAD -> SIM до общего semantic JSON:
   компоненты, pins, wires, nets, labels, GND, BOM.

2. Расширить DRC:
   уровни `error`, `warning`, `recommendation`; понятные сообщения для пользователя.

3. Добавить probes:
   напряжение узла, ток ветви, перегрузка элемента, отображение на графиках.

4. Довести Pro-аналитику в UI:
   быстрые действия уже есть под результатом симуляции; следующий шаг — отдельные вкладки осциллографа/AC, сохранение SVG-отчетов и измерений.

5. Расширить browser-smoke:
   делитель -> DC, RC-фильтр -> AC и -3 дБ-маркер, SVG/PDF экспорт, visual regression для CAD/projects.

## P1: Инженерная лаборатория

1. Связать расчеты лаборатории с симулятором:
   текущая схема -> расчетная карточка -> ожидаемые измерения -> сравнение с фактическим результатом.

2. Расширить лабораторные метрики:
   duty cycle, RMS по выбранному узлу, мощность элемента, температура корпуса, запас по derating.

3. Использовать scientific stack в лаборатории:
   Monte Carlo tolerance для резисторов/RC, Bode plot для фильтров, FFT для осциллографа и сравнение расчетного/измеренного спектра.

4. Сделать диагностику неисправностей:
   симптом -> точки измерения -> вероятные причины -> переход к статье/товару/заданию.

## P1: Обучение как практикум

1. Связать страницу задания с simulator напрямую:
   кнопка "Отправить текущую схему на проверку" вместо ручной вставки `scheme_data`.

2. Добавить измерительные probes в UI:
   выбор узла/ветви, автозаполнение `simulation_result`, подсветка нужной точки на схеме.

3. Расширить банк заданий:
   задачи по диодам, транзисторному ключу, RC/LC переходным процессам, тепловому запасу корпуса, FFT/Bode/Monte Carlo для Pro-практикума.

4. Добавить частичные баллы:
   отдельно оценивать состав компонентов, GND/источник, номиналы, соединения и результат симуляции.

## P2: дипломные материалы

1. Синхронизировать текст диплома с фактическими цифрами:
   43 РЭБ-товара, 67 verified real photos, 13 SVG fallback, 9 generated PNG без прямых Wikimedia/Commons путей, 12 demo-схем, 21 статья, 50 материалов, 4 learning tracks, 13 уроков, 29 заданий.

2. Проверить презентацию:
   убрать устаревшие числа и заменить скриншоты после P0.

3. Обновить release-архив:
   включить актуальные docs, media, БД и команды запуска.

## P2/P3: комментарии зарегистрированных пользователей

1. Добавить общий `Comment` service/model слой:
   связать комментарии с товарами, статьями, уроками, demo-схемами и `ProjectReview` через content type или отдельные typed foreign keys.

2. Ограничить создание комментариев авторизованными пользователями:
   анонимным показывать чтение и CTA входа, зарегистрированным дать редактирование/удаление своих комментариев.

3. Сразу заложить модерацию:
   статусы `visible/pending/hidden`, жалобы, админ-фильтры, rate-limit, soft delete и проверка на пустой/слишком длинный текст.

4. Для инженерных страниц сделать контекст:
   комментарий может ссылаться на компонент, узел, fault-сценарий, расчет лаборатории или конкретный пункт review.

5. В обучении использовать комментарии как обратную связь:
   обсуждение задания, подсказка преподавателя, фиксация типовой ошибки и возможный переход в FAQ/энциклопедию.

## P2/P3: neural AI sprint

1. Не добавлять PyTorch/GOLEM в текущий runtime без отдельного окружения:
   зависимости тяжелые и требуют датасета, baseline-метрик и GPU/Colab-сценария.

2. Собрать датасет:
   1000+ схем из `demo_projects`, учебных схем, импортируемых SPICE/KiCad subset и открытых источников с проверенной лицензией.

3. Обучить GNN для DRC++:
   задачи `missing ground`, `wrong nominal`, `overheat risk`, `recommend-next-component`; сравнить с rule-based `DolgAIPipeline`.

4. Подключать только как backend:
   `DolgAIPipeline backend='neural'`, факты и ограничения остаются в service-layer review/lab, а нейросеть дает вероятностные рекомендации.

5. Для диплома:
   вынести IEEE Xplore-подборку в библиографию по GNN for circuit analysis, schematic DRC и embeddings для аналоговых схем.

## Gate перед завершением итерации

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test Dolg_APP.tests knowledge.tests shop.tests --keepdb -v 1
.\.venv\Scripts\python.exe manage.py test Dolg_APP.tests.LightweightLibraryIntegrationTests Dolg_APP.tests.EngineeringReviewTests knowledge.tests.LightweightLearningLibraryTests knowledge.tests.LearningModelAndGraderTests --keepdb -v 2
.\.venv\Scripts\python.exe manage.py check_demo_ready --json
.\.venv\Scripts\python.exe manage.py check_data_integrity --json
.\scripts\run_browser_e2e.ps1
```

Целевой результат: `check` без ошибок, `check_demo_ready` без ошибок, `check_data_integrity` без ошибок и без media-warning, browser-smoke проходит.
