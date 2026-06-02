# NEXT_PLAN: развитие DOLG после demo-ready слоя

Рабочий лист ближайшей итерации: [`docs/WORKFRONT_20260517.md`](WORKFRONT_20260517.md).

## Реализовано в новом этапе: review/import/self-AI

- Добавлен `ProjectReview` как ядро инженерной проверки: DRC/ERC, BOM risk, наличие GND/источника, derating, fault-сценарии, измерения, score и HTML/PDF-отчет.
- Добавлен `ProjectMeasurement`: сохраненные измерения лаборатории и симуляции для сравнения "ожидаемое против измеренного".
- Добавлен CAD-import subset: LTspice/SPICE netlist и KiCad subset приводятся к внутреннему `scheme_data` и сразу проходят review.
- Добавлен Self AI V2: без внешней LLM, по данным схемы, review, BOM и fault library; различает вопросы про GND, измерения, BOM, импорт, обучение, derating, подбор и план исправления, хранит 20 сообщений истории и `session_summary`.
- Добавлен learning track `diagnostika-prostyh-shem`: диагностика отсутствующего GND, перегрева и подтверждение измерением.
- Добавлен scientific simulation stack без изменения архитектуры: NumPy/SciPy/Matplotlib/Pandas в `Dolg_APP/services/simulation_analysis.py`, `python-engineering` как validation backend лаборатории.
- Добавлен lightweight graph/formula/SVG stack перед нейронкой: NetworkX в `Dolg_APP/services/schematic_graph.py`, SymPy в `knowledge/services/formula_steps.py`, Schemdraw в `knowledge/services/circuit_svg.py`.
- Добавлен optional PyTorch deep-hints backend: `requirements-ai.txt`, `Dolg_APP/ml/neural.py`, `train_tiny_circuit_ai`, trained model `media/ml/tiny_circuit_ai.pt`; обычный Django startup не импортирует torch.
- Добавлен expert-first stack: `jsonschema` + `rule-engine` для rule packs, Pint для единиц измерения, Lark для SPICE/LTspice parsing subset, Z3 для constraint-подбора номиналов и scikit-fuzzy для мягкой оценки риска.
- Закрыта связка `import -> preview -> save project -> review -> learning`: `/cad/` показывает server-side preview импортированной LTspice/SPICE/KiCad-subset схемы, умеет сохранить проект с review, а отчет `ProjectReview` предлагает уроки Learning-by-review по найденным ошибкам и топологии.
- Добавлен browser-smoke `Dolg_APP/tests_browser.py` для полного сценария CAD import preview -> saved review -> learning block; без `RUN_BROWSER_E2E=1` тест безопасно пропускается.
- Добавлен Media Quality Gate: `shop/services/media_quality.py` использует Pillow + ImageHash, проверяет размер/читаемость/однотонность/perceptual hash и подключен к `check_data_integrity` и `check_demo_ready`.
- Добавлен REB Catalog Quality слой: `shop/services/reb_catalog_quality.py` и команда `normalize_reb_catalog` восстанавливают инженерные поля v2-каталога (part number, монтаж, рейтинги, datasheet), после чего `enrich_datasheets --all --missing-only` заполняет `datasheet_extracted`.

## Новый порядок развития: expert-first

- Ближайший приоритет: экспертные системы и объяснимые правила. Любой вывод review/AI должен иметь `rule_id`, severity, evidence, recommendation, confidence и ссылку на расчет, статью или учебное задание.
- Второй слой: constraint/optimization. Z3 уже покрывает LED-резистор, делитель, RC cutoff, NE555, стабилизатор и тепловой запас; OR-Tools остается для будущего BOM-подбора по цене, наличию, запасу и SPICE-модели.
- Третий слой: neural deep analysis. PyTorch уже подключен как tiny backend для вероятностных `deep_hint`; будущая GNN получит `scheme_data`, graph metrics, rule findings, simulation measurements и BOM facts.
- AI-помощник опирается на `Expert trace` из review и возвращает `intent`, `confidence`, structured `quick_actions`, `context_sources` и `session_summary`; внешняя LLM, если появится, может быть только слоем формулировки без права менять факты.

## Новый фронт после внедрения

- Нейробалабол V3 уже получил curated baseline и graph-feature PyTorch model `0.3.0-tiny-graph-pytorch`. Следующий AI-фронт: расширить корпус до 200-500 реальных схем через opt-in, импортированные SPICE/KiCad примеры и ProjectReview snapshots; learning tasks использовать как source-backed explanation corpus, а не как суррогат схем.
- Staff-контроль AI-датасета вынесен на `/staff/ml-dataset/`: перед любым дообучением проверять validation errors/warnings, coverage `scheme_data/source_ids/teacher_rules`, topology balance и metadata текущей модели.
- Для AI-панели развивать structured deep hint: показывать похожие случаи, teacher rule, legal source и “почему модель так решила”; neural output остается подсказкой, а не инженерным verdict.
- Сшить UI лаборатории и симулятора: сохранять измерения из рабочего сценария без ручной вставки JSON.
- Расширить import preview до интерактивной карты узлов: визуально подсвечивать GND, источники, output node, floating nodes и неподдержанные элементы перед сохранением проекта.
- Развить "Learning-by-review": создавать учебную задачу из конкретного finding review, а не только предлагать готовый урок.
- Довести Self AI quick actions до реальных переходов: по клику открывать нужный блок review, лаборатории, BOM или learning-задачу.
- Расширить fault library: перепутанный номинал, обрыв, короткое, неверный LED-резистор, перегрев стабилизатора.
- Довести Pro-аналитику в интерфейсе: текущие быстрые действия под результатом симуляции развить в отдельные вкладки FFT/Bode/Monte Carlo и связать с сохраненными измерениями.
- Расширить neural dataset: добавить реальные demo_projects, импортированные LTspice/KiCad схемы и ошибки из ProjectReview поверх текущего синтетического teacher dataset.
- Для пользовательских схем использовать только явный opt-in `allow_ai_training` в профиле. Сбор идет отдельной командой `collect_ai_training_examples`, обучение - `train_tiny_circuit_ai --include-curated`; live-ответ AI не дообучает модель сам.
- Расширить browser smoke: расчет -> схема -> измерение -> review -> учебное задание, с реальным Playwright-прогоном при `RUN_BROWSER_E2E=1`.

## P0: ближайший фронт работы

- Использовать `python manage.py check_data_integrity --json` перед крупными правками данных: команда проверяет каталог, media, статьи, внутренние ссылки и demo-схемы.
- Удерживать no-Wikimedia media-policy: `import_commons_product_photos` отключён, активные карточки должны ссылаться на точный локальный asset `products/<slug>.*`, проверенное фото `products/verified/<slug>.*`, точный SVG fallback или `products/generated/*.png`; `check_demo_ready`/`check_data_integrity` блокируют прямые Commons/curated-источники.
- Media V2 делать только через allowlist официальных источников производителей/дистрибьюторов или собственные изображения; неподтвержденные product-shot и Wikimedia не включать.
- Следующий пакет внедрять после Media Quality Gate: Datasheet Intelligence на `PyMuPDF/pdfplumber/pandas` для извлечения pinout, absolute maximum ratings, thermal data и типовых схем включения.
- Пройти вручную маршрут `/demo/`: каталог -> энциклопедия -> CAD -> симуляция -> BOM -> корзина.
- Обновить финальные скриншоты в `docs/diploma_assets/screenshots/` и крупные схемы/диаграммы держать в A3.
- Проверить запуск двойным кликом через `run_dolg.bat` на чистой машине.
- Учитывать новый слой обучения, scientific stack, lightweight stack, expert stack, neural stack и media quality: `check_demo_ready --json` теперь проверяет опубликованные learning tracks/lessons/tasks, версии NumPy/SciPy/Matplotlib/Pandas/python-engineering, service-smoke FFT/Bode/Monte Carlo/Signal quality/Parameter sweep/DC fallback, `graph_stack/formula_stack/circuit_svg_stack`, `expert_stack`, `neural_stack` и `media_quality`.

## P0: каталог V3 по эталону карточки

Аудит 2026-06-01 после первичного наполнения показал: технически карточки стабильны, но по качеству данных до эталона "диодов" еще не хватает локализации, единых обязательных схем параметров и более строгой политики тегов.

- Закрыто 2026-06-02:
  - расходники, инструменты и модули очищены от сырых `Consumable/Tool/Module` и seed-названий;
  - `enrich_product_parameters` нормализует витринные названия, `package_type` и русские значения параметров для consumables/tools/modules;
  - все preview-чипы карточек кликабельны, а `material`, `size`, `wire`, `configuration`, `temperature_range`, `compatibility`, `mode`, `safety` получили прямые backend-фильтры;
  - длинные значения вроде `ABS + фосфористая бронза` выводятся широким чипом, а не режут сетку;
  - allowlist официальных/дистрибьюторских фото расширен для макетных плат, макетных PCB и части расходников; Wikimedia/Commons не используется.
- Текущее состояние после правки: 364 товара, сырых package-type `0`, non-clickable preview chips `0`, verified images `79`, generated fallback `285`.
- Оставшийся хвост: постепенно расширять official/supplier photo allowlist для модулей, инструментов и потребительской электроники; для РЭБ fallback заменить на чистые UGO-style изображения без текста, неона и декоративных дуг.

- Эталон карточки: категория, чистое изображение, название, рейтинг, part number, производитель, корпус/форм-фактор, ресурсные чипы, 5-7 инженерных параметров, цена, склад, доставка, CTA.
- Найденные хвосты:
  - `modules/tools/consumables`: базовая локализация и фильтры закрыты; следующий шаг - реальные verified photos и schema-аудит полноты по подтипам.
  - `resistors`: 78 товаров, в основном 4 параметра; добавить технологию, max voltage, temp coefficient/series или noise class, чтобы карточки не выглядели беднее диодов.
  - `ics`: 34 товара, у большинства 3-4 параметра; добавить назначение, pins/package, частоту/GBW/channels/interface для логики, ОУ, стабилизаторов и MCU.
  - `transistors`: 21 товар, многим нужны hFE/Vce(sat) для BJT, Vgs/Rds/Qg для MOSFET, pinout/package и heat/rating aliases.
  - `diodes`: довести сам эталон: русифицировать `max_current`, разделить рабочий ток и предельный ток, добавить surge/reverse leakage там, где уместно.
  - `connectors`: добить недостающие 5-й параметр: orientation/gender/contact material/voltage для headers, Dupont, DC jack.
- Data-layer:
  - завести `shop/services/catalog_schema.py` с required/recommended fields per category/type;
  - добавить команду `audit_catalog_schema --json`, которая выводит coverage, missing fields, english values, weak image source, non-clickable chips;
  - расширить `enrich_product_parameters` не отдельными патчами, а через словари `CATEGORY_TYPE_SCHEMAS`, `SLUG_PARAMETER_OVERRIDES`, `VALUE_TRANSLATIONS`.
- UI-layer:
  - разделить чипы на три класса: ресурсы (`PDF`, `SPICE`, `CAD`, `Параметры`), мета (`бренд`, `корпус`) и параметры;
  - убрать странные/слишком короткие resource labels вроде `Данные`, заменить на понятное `Параметры` или `Из datasheet`;
  - расширять backend-фильтры дальше по мере появления новых полей (`protocol`, `series`, `pinout`, `thermal`, `noise_class`), чтобы новые чипы не становились декоративными;
  - для active chips показывать понятное состояние и "снять фильтр".
- Media-layer:
  - для РЭБ в карточках использовать либо реальное официальное/дистрибьюторское фото, либо чистый UGO-style PNG без текста, неона, полукругов и декоративной сетки;
  - для инструментов/модулей/расходников предпочитать реальные фото; если фото не проверено, показывать аккуратную объясняющую заглушку "фото уточняется у производителя";
  - добавить image audit по категориям: real/official/generated/placeholder coverage.
- Acceptance:
  - в каждой категории `avg_preview >= 5`, кроме случаев, где физически достаточно 4 параметров и это явно разрешено схемой;
  - 0 английских type/application/sensor/tool значений в пользовательском UI;
  - 0 служебных ключей в HTML;
  - 0 горизонтального overflow desktop/mobile;
  - `check_data_integrity --json`, `check_demo_ready --json`, targeted catalog tests и browser smoke проходят.

## P1: инженерная связность CAD/SIM

- Сохранять demo-схемы через `populate_demo_projects`: seed назначает позиционные обозначения и ортогональные маршруты, чтобы БД не расходилась с кодом.
- Довести CAD -> SIM до общего semantic JSON: компоненты, pins, wires, nets, labels, GND, BOM.
- Расширить DRC уровнями: ошибка, предупреждение, рекомендация.
- Добавить интерактивные probes в симуляции: напряжение узла, ток ветви, перегрузка элемента.
- Связать товары каталога с CAD-шаблонами и статьями.
- Расширить browser-smoke: делитель -> DC, RC-фильтр -> AC и -3 дБ-маркер, SVG/PDF экспорт, visual regression для CAD/projects.

## P1: инженерная лаборатория + практикум

- Развивать новые области пакетом: крупная фича -> обучающий блок -> README/NEXT_PLAN/TESTS_AND_REPORTS/DEMO_SCENARIO.
- Связать `/knowledge/lab/` с текущей схемой симулятора: расчет -> ожидаемое измерение -> сравнение с фактической метрикой.
- Подключить simulator к заданиям без ручной вставки JSON: брать текущий `scheme_data` и последний `simulation_result` из рабочей области.
- Использовать NetworkX-проверки в заданиях `circuit_build`: связность, GND, output node, изолированные компоненты и тип топологии.
- Использовать SymPy в `math_numeric`: принимать эквивалентные формулы и показывать шаги вывода для закона Ома, делителя, мощности, RC cutoff и NE555.
- Добавить probes и автозамеры для учебных задач: DC-напряжение узла, ток ветви, RMS, -3 дБ точка.
- Использовать новый численный слой в заданиях: FFT-спектр как Pro-задача, Bode plot для RC/LC, Monte Carlo tolerance для разброса номиналов, THD/SINAD/ENOB для качества сигнала и parameter sweep для подбора номиналов.
- Расширить рубрики частичными баллами и отдельной диагностикой ошибок сборки.
- Следующие области для лаборатории: диагностика неисправностей, проектное review, derating/надежность, контроль сборки.

## P1: документация и чистка

- После каждого изменения данных обновлять README, `docs/TESTS_AND_REPORTS.md`, `docs/DEMO_SCENARIO.md` и финальные материалы диплома.
- Держать временные логи, `__pycache__` и `.ruff_cache` вне релизного архива.
- Перед упаковкой выполнять `check`, `check_demo_ready --json`, `check_data_integrity --json` и, если есть время, полный `test`.
- Сверить актуальный текст диплома и презентации с фактическими цифрами: 364 товара, 227 РЭБ-компонентов, 79 verified real photos, 285 generated fallback без прямых Wikimedia/Commons путей, 12 demo-схем, 22 статьи, 99 материалов, 5 learning tracks, 16 уроков, 38 заданий.

## P2: продуктовый слой

- Добавить избранное для товаров, статей и схем.
- Добавить комментарии для зарегистрированных пользователей: сначала к статьям, урокам, товарам, demo-схемам и `ProjectReview`.
- Заложить модерацию комментариев: статус `visible/hidden/pending`, жалобы, удаление владельцем/администратором, rate-limit и антиспам.
- Для инженерных страниц поддержать контекстные комментарии: привязка к компоненту, узлу, fault-сценарию или пункту review, чтобы обсуждение было не абстрактным, а полезным для исправления схемы.
- Добавить проектную корзину: заказ привязан к конкретной схеме/BOM.
- Добавить экспорт проекта архивом: JSON-схема, BOM, netlist, PDF, изображения.
- Добавить избранное/закладки для учебных уроков и задач.

## P2: AI/ML и библиография

- PyTorch держать optional-зависимостью в `requirements-ai.txt`; не переносить в основной runtime, потому что импорт тяжелый.
- Phase 2 AI next: собрать 1000+ схем из `demo_projects`, учебных схем и внешних открытых источников, заменить tiny MLP на GNN для DRC++/recommend-next-component.
- Подключение в продукт: `DolgAIPipeline backend='neural'` использовать как probabilistic `deep_hint`; финальный verdict остается за rule/expert baseline и человеком.
- Для дипломной библиографии отдельно собрать IEEE Xplore-источники по темам `GNN for circuit analysis`, `schematic DRC`, `graph embeddings for electronic circuits`; это не runtime-зависимость проекта.

## P3: production

- Перевести production-режим на PostgreSQL через `DATABASE_URL`.
- Настроить резервные копии базы и `media/`.
- Добавить rate-limit для AI, поиска, BOM и сохранения проектов.
- Добавить отдельную страницу статуса системы и мониторинг.

## 2026-05-25: priority roadmap

- Актуальный список дополнений по важности и сложности вынесен в [`docs/PRIORITY_ROADMAP_20260525.md`](PRIORITY_ROADMAP_20260525.md).
- В P0 добавлено обязательное условие для проверки схемы: пользовательские сообщения DRC/ERC, fault library, expert findings, review UI/PDF и self-hosted AI должны показываться на русском языке.

## 2026-05-26: legal resource corpus

- Добавлена карта источников [`docs/LEGAL_RESOURCE_MAP_20260526.md`](LEGAL_RESOURCE_MAP_20260526.md): VK/Telegram-подборки используются только как ориентир по названиям и темам, без скачивания неофициальных архивов книг.
- Для диплома, кода и AI-датасета закреплен legal-first подход: официальная документация, открытые учебники, datasheet, собственные demo-проекты и пользовательские схемы только через явный opt-in `allow_ai_training`.
- Следующий шаг: завести curated `knowledge_sources.json` и связать источники с правилами review, learning tracks и AI evidence.
## 2026-05-31: LECAD / Lithium ECAD research

- Отдельный TODO: [LECAD_LITHIUM_ECAD_RESEARCH_TODO_20260531.md](LECAD_LITHIUM_ECAD_RESEARCH_TODO_20260531.md).
- Цель: прошерстить сайт LECAD и изучить бесплатную версию Lithium ECAD как сильного конкурента в области разработки схем.
- Формат: legal-first black-box research: публичная документация, установка в песочнице, проверка поведения UI, сохранений, импорта/экспорта, логов и открытых конфигов.
- Ограничения: без обхода защит, патчинга бинарников, извлечения закрытых алгоритмов и действий, нарушающих лицензию.
- Потенциальный выход для DOLG: режим синхронизации CAD/SIM, подсветка review поверх схемы, улучшенный import/export compatibility pack, новые сценарии обучения и AI-разбора схем.
