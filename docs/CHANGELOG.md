# CHANGELOG — DOLG

Хронология изменений проекта. Каждая запись — самостоятельный пакет фич/правок.

---

## 2026-05-31: Engineering Review 3D Analysis Map

- В HTML-отчете Engineering Review добавлена интерактивная 3D-карта анализа на Three.js: `Design Health Score`, DRC/ERC, BOM-риск, derating, saved measurements, simulations, CAD/ERC findings и floating fragments показываются как объемные столбцы и risk points.
- Новый service-layer `Dolg_APP/services/review_visualization.py` собирает безопасный JSON-payload из snapshot `ProjectReview`; шаблон только отображает данные и не дублирует инженерные расчеты.
- Frontend-файл `shop/static/review/review-3d.js` использует локальный `shop/static/lib/three.min.js`, поддерживает вращение мышью, resize и табличный fallback, если WebGL или Three.js недоступны.
- Targeted regression: `python manage.py test Dolg_APP.tests_review_visualization` и `python manage.py test Dolg_APP.tests.EngineeringReviewTests.test_review_page_and_pdf_are_available_to_owner`.

## 2026-05-17: Engineering Review, CAD Import, Self AI

Новый этап развития закрепляет DOLG не как отдельный каталог или симулятор, а как инженерный контур проверки проекта.

- `ProjectReview` сохраняет snapshot проверки: схема, DRC/ERC, BOM-риск, измерения, derating, fault-сценарии, рекомендации и `Design Health Score`.
- `/projects/api/<id>/review/` создает review, `/projects/review/<id>/` показывает HTML-отчет, `/projects/review/<id>.pdf` экспортирует отчет для демо/защиты.
- `ProjectMeasurement` хранит измерения лаборатории и симуляции: напряжение узла, ток ветви, RMS, частота, duty cycle, мощность и температура.
- `Dolg_APP/services/cad_import.py` импортирует ограниченный LTspice/SPICE netlist и KiCad subset во внутренний `scheme_data`, после чего запускается тот же review core.
- `Dolg_APP/services/learning_by_review.py` связывает findings и topology review с практическими уроками: отсутствующий GND, делитель, RC-цепь, LED-индикатор и derating.
- `Dolg_APP/services/rule_ai.py` добавляет самописный rule-based AI-помощник без обязательной внешней LLM: ответы строятся по схеме, BOM, review, расчетам и fault library.
- Self AI расширен до intent-режимов: краткий разбор схемы, GND, план исправления, измерения `expected vs measured`, derating, BOM/каталог, CAD-import и learning-by-review; API возвращает `intent`, `confidence` и быстрые действия для UI.
- В `knowledge` добавлен диагностический learning track `diagnostika-prostyh-shem`, который использует реальные ошибки review: нет GND, перегрев, измерение результата.
- Search и `check_demo_ready` знают про review/import/diagnostics; demo-ready smoke проверяет `cad_import_preview_details` и Learning-by-review, targeted regression: `python manage.py test Dolg_APP.tests.EngineeringReviewTests knowledge.tests.EngineeringLabTests knowledge.tests.PopulateKnowledgeLearningTests shop.tests.GlobalSearchAndDemoRouteTests shop.tests.DemoReadyCommandScientificStackTests`.

## 2026-05-17: Scientific Simulation Stack

Новый численный слой добавлен без пересмотра архитектуры: все расчеты лежат в Python service-layer и переиспользуются API, лабораторией и будущими учебными заданиями.

- `Dolg_APP/services/simulation_analysis.py` использует NumPy/SciPy/Matplotlib/Pandas для FFT, Bode plot, Monte Carlo tolerance, signal quality THD/SINAD/ENOB, parameter sweep, DC fallback и статистики запусков.
- Pro endpoints: `/simulation/api/pro/fft/`, `/simulation/api/pro/bode/`, `/simulation/api/pro/monte-carlo/`, `/simulation/api/pro/signal-quality/`, `/simulation/api/pro/parameter-sweep/`.
- Fallback endpoint: `/simulation/api/fallback-solve/` решает простые DC-цепи R/V/GND на сервере.
- Project analytics: `/projects/api/<id>/simulation-runs/stats/` возвращает slowest runs и агрегаты по типам анализа.
- Pro-метрики можно сохранить в `ProjectMeasurement` через существующий endpoint `/projects/api/<id>/measurements/create/`.
- `python-engineering` подключен к инженерной лаборатории как validation backend; библиотека не заменяет собственные электронные формулы, потому что ее текущий пакет не содержит готовых калькуляторов для NE555/RC/стабилизаторов.
- `check_demo_ready --json` проверяет установленные scientific-библиотеки и мини-сценарии service-layer: `fft_svg`, `bode_svg`, `monte_carlo_svg`, `signal_quality_svg`, `parameter_sweep_svg`, `dc_fallback`.
- Phase 2 AI получил первый безопасный PyTorch-слой: tiny neural backend для `DolgAIPipeline backend='neural'` дает probabilistic `deep_hint` по топологии, риску и следующему компоненту, а expert/review остается финальным verdict.

## 2026-05-18: Lightweight Graph/Formula/SVG Stack

Перед нейронным этапом добавлен легкий библиотечный слой, который усиливает уже существующие CAD/SIM, review и learning-сервисы без утяжеления старта Django.

- `networkx` используется в `Dolg_APP/services/schematic_graph.py`: связность схемы, floating nodes, путь до GND, изолированные компоненты, простые циклы и базовое определение topology (`voltage_divider`, `rc_network`, `led_indicator`).
- `sympy` используется в `knowledge/services/formula_steps.py`: объяснение закона Ома, делителя, мощности, RC cutoff и NE555, а также проверка эквивалентных выражений в учебных задачах.
- `schemdraw` используется в `knowledge/services/circuit_svg.py`: SVG для учебных и отчетных схем LED-индикатора, делителя, RC-фильтра, NE555 и транзисторного ключа. Карточки товаров через Schemdraw не генерируются.
- Engineering Review, `rule_ai` и grader обучения читают общий graph/formula слой через service-layer; старые DRC/ERC проверки не удалены, а расширены.
- `check_demo_ready --json` проверяет версии библиотек и smoke-сценарии `graph_stack`, `formula_stack`, `circuit_svg_stack`.
- PyTorch вынесен в optional `requirements-ai.txt`, чтобы обычный старт Django не тянул тяжелый импорт; tiny-модель обучается командой `python manage.py train_tiny_circuit_ai`.

## 2026-05-18: Expert-First Review Stack

Следующий слой развития построен в порядке `expert systems -> constraints/optimization -> neural deep analysis`. Нейронная часть не заменяет инженерные правила, а позже будет давать вероятностные `deep_hint` поверх проверяемой базы.

- `Dolg_APP/expert_rules/default_rules.json` хранит версионированный rule pack; `Dolg_APP/services/expert_rules.py` валидирует его через `jsonschema` и исполняет условия через `rule-engine`.
- `Dolg_APP/services/engineering_units.py` использует Pint для общего parsing/validation номиналов: `10k`, `6.8kOhm`, `2.5мА`, `100нФ`, `В/Ом/Гц/Вт` и предупреждения о подозрительных единицах.
- `Dolg_APP/services/constraint_solver.py` добавляет Z3-подбор вариантов для LED-резистора, делителя, RC cutoff, NE555, стабилизатора и теплового запаса.
- `Dolg_APP/services/cad_parsers.py` использует Lark для SPICE/LTspice subset; импорт сначала нормализует схему в `scheme_data`, затем запускает review.
- `Dolg_APP/services/risk_scoring.py` добавляет fuzzy risk score через scikit-fuzzy для перегрева, слабого запаса, BOM-risk и топологических предупреждений.
- `ProjectReview` теперь включает `expert_findings`, `rule_id`, severity, evidence, recommendation, confidence и fuzzy-risk; `rule_ai` отвечает по `Expert trace`, а не придумывает факты.
- `check_demo_ready --json` проверяет новый `expert_stack` и smoke-сценарии `rule_pack`, `rule_engine_finding`, `pint_unit_parse`, `lark_import_preview`, `z3_voltage_divider`, `fuzzy_risk`.
- OR-Tools и RDFLib остаются roadmap; PyTorch подключен как optional deep-hints backend без права менять expert verdict.

## 2026-05-25: Self AI V2 + Tiny PyTorch Backend

- AI-панель получила карточку "Разбор схемы": topology, score, GND/source, DRC/ERC, floating fragments, measurements и BOM-связь видны до отправки вопроса.
- `/api/ai/context/` возвращает компактный контекст схемы, а `/api/ai/chat/` принимает 20 сообщений истории, `session_summary` и `last_intent`.
- `rule_ai` возвращает structured `quick_actions`, `context_sources`, `used_context`, `session_summary` и active token usage для self-hosted режима.
- `Dolg_APP/ml/neural.py` добавляет tiny PyTorch model: fixed feature vector по `scheme_data`, topology head, risk head и next-component head.
- `train_tiny_circuit_ai` обучает демо-модель на синтетических схемах и сохраняет `media/ml/tiny_circuit_ai.pt`; текущий прогон: 180 схем, 60 epochs, loss `0.138674`.
- `check_demo_ready --json` выводит `neural_stack`: torch `2.12.0`, trained tiny model OK.

## 2026-05-25: Engineering Artifact Ingestion

- Добавлен корпус инженерных артефактов: модели `EngineeringArtifact` и `AITrainingExample`, команда `python manage.py ingest_engineering_artifacts`, сервис `Dolg_APP/services/artifact_ingestion.py`.
- V1 парсит DOCX/PDF/PPTX/DXF, P-CAD `.net/.drc/.erc` и OLE metadata. DWG/MS14 не читаются как полноценная схема, но сохраняются как metadata + предупреждение о конвертации.
- `ProjectReview` получил разделы `reliability`, `manufacturing`, `external_cad` и `artifacts`; импортированные DRC/ERC findings идут в score, evidence и русские поля `title_ru/evidence_ru/recommendation_ru`.
- Self AI использует artifact memory как источник контекста: артефакты, check findings, fault cases и learning-by-artifact подсказки.
- `check_demo_ready --json` проверяет `artifact_stack`: `pypdf`, `python-docx`, `python-pptx`, `ezdxf`, `olefile`, P-CAD DRC/NET, DXF, DWG/MS14 stubs, learning-by-artifact и AI training examples.

## 2026-05-26: Free / Pro / Enterprise entitlements

- Добавлен единый service-layer `Dolg_APP/services/entitlements.py`: `get_effective_plan`, `has_feature`, `check_feature`, `require_feature`.
- Pro-аналитика теперь закрыта feature-gates: FFT, Bode, Monte Carlo, signal quality, parameter sweep и server-side fallback solver доступны только Pro/Enterprise.
- AI-балабол разделен по тарифам: Free получает базовый чат и DRC++/аналоги, Pro получает расширенный разбор схемы, 20 сообщений истории, `session_summary`, token counter и pipeline explain/recommend, Enterprise добавляет командный контекст проекта.
- Enterprise определяется как `Organization.plan='enterprise'` плюс активная org-подписка; org-level функции вроде audit-log, API tokens, approval workflow и analytics проверяются через entitlements.
- `/billing/` показывает Free, Pro и Enterprise; `/api/usage/today/` возвращает `plan`, `features` и `feature_flags`.

## 2026-05-26: Legal Knowledge Corpus

- Добавлен `knowledge/data/legal_sources.json`: curated-список открытых учебников и официальной документации по электронике, CAD/SPICE, Django, graph/formula/unit stack, constraint solving и PyTorch.
- Добавлена команда `python manage.py seed_legal_sources`: создает обзорную статью "Открытые источники и документация DOLG" и привязывает источники как `ArticleMaterial` к профильным статьям энциклопедии.
- `check_demo_ready --json` проверяет `legal_sources_stack`: наличие JSON, покрытие тем, learning/AI пригодность, обзорную статью и привязку источников к материалам.
- Правило для диплома и AI: внешние подборки книг используются только как ориентир по темам/названиям; корпус строится на официальной документации, открытых учебниках, datasheet, demo-проектах и opt-in пользовательских схемах.

## 2026-05-19: Media Quality Gate

Первый новый пакет после import/review закрывает проблему качества изображений каталога без возврата к Wikimedia/Commons.

- `ImageHash` добавлен к Pillow-слою и используется в `shop/services/media_quality.py` для perceptual hash локальных product-shot.
- Gate проверяет каждую активную карточку: наличие файла, читаемость, минимальный размер, однотонность, extreme aspect ratio, визуальную детализацию, policy-нарушение и итоговый `quality_score`.
- Generated-заглушки остаются допустимым контролируемым источником; perceptual-дубли среди них не считаются проблемой, потому что это собственный fallback-art.
- `check_data_integrity --json` теперь возвращает `catalog.media_quality`, а `check_demo_ready --json` возвращает верхнеуровневый блок `media_quality`.
