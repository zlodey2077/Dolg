# DOLG — Тесты, отчёты, рекомендации

## 2026-06-01: catalog card hotfix and official photo allowlist

- 2026-06-02: Catalog V3 расширен на расходники, инструменты и модули:
  - `enrich_product_parameters` нормализует витринные названия и `package_type` для consumables/tools/modules;
  - добавлены прямые фильтры `material`, `size`, `wire`, `configuration`, `temperature_range`, `compatibility`, `mode`, `safety`;
  - все preview-чипы карточек остаются кликабельными (`nonclickable preview chips = 0`);
  - allowlist official/supplier photos расширен для `breadboard-400`, `breadboard-830`, `breadboard-2x830`, `pcb-protoboard-7x9`, `pcb-protoboard-9x15`, `jumper-mm-65pcs`.
  - фактические метрики после применения команд: 364 товара, raw package types `0`, verified images `79`, generated fallback `285`.
- Скрыты служебные `Product.parameters` из карточек и деталки: `catalog_quality`, `image_source*`, `image_verified_from` больше не попадают в chips и таблицу характеристик.
- Добавлены широкие chips для длинных значений (`type`, `resolution`, `chip`, `connectivity`), чтобы названия не вылезали и не резались в узкой колонке.
- Добавлена allowlist-команда `import_official_product_photos`; обновлены реальные фото для `solder-paste-138`, `solder-lead-free-100g`, `solder-60-40-100g`, `ao3400`, `irlz44n`, `irf9540n` без Wikimedia/Commons.
- Карточки РЭБ выровнены под более полный «диодный» формат: расширены ключевые параметры (`Imax`, `Iout`, `Vz`, `trr`, `DCR`, `SRF`, `GBW`, `Контакт`), сигнал-теги упрощены до `PDF` / `Данные` / `SPICE`.
- Active SVG fallback отключен: при отсутствии хорошего raster-фото генерируется аккуратный UGO-style PNG без названий товара, неоновой рамки и декоративных дуг.
- Checks: `manage.py check`, `makemigrations --check --dry-run`, `test shop.tests.ProductCardHelperTests shop.tests.ProductImagePolicyTests shop.tests.DatasheetIntelligenceTests` — **15/15 OK**; browser smoke desktop/mobile для `diodes/resistors/transistors/ics/capacitors/inductors/connectors/relays` — no overflow, no active SVG, no service-field leakage; `check_demo_ready --json` и `check_data_integrity --json` — OK, без warnings.

## 2026-05-31: neural curation and dataset import gate

- Added explainable PyTorch `deep_hint`: prediction is checked against expert baseline and returns `agreement_score`, `calibrated_confidence`, `confidence_policy`, similar validated cases and final-control policy.
- Added automatic scheme curation: `collect_good_schemes_for_ai` writes validated `AITrainingExample` rows from demo/opt-in projects with `scheme_family`, `complexity_score/label` and `quality_score/label`.
- Expanded AI dataset from 58 to 72 validated examples, including 14 auto-quality schemes; family/complexity/quality distribution is visible in `/staff/ml-dataset/`.
- Fixed external dataset import: `--persist` no longer writes to a missing model field; added `--local-only`, `--as-projects`, `--project-min-quality` so good imported schemes can also become demo `SchematicProject` rows.
- Hardened Open Schematics download path: direct `requests` streaming writes to `Dolg_APP/ml/dataset/external/hf_cache/`, `--local-only` now exits on cache miss without network retries, and `--download-deadline` skips a slow shard instead of leaving the admin import looking frozen.
- Added controlled project promotion for curated schemes: `promote_ai_examples_to_projects` can create private/team/public `SchematicProject` records from validated `AITrainingExample` rows, and `AITrainingExampleAdmin` exposes private/demo promotion actions. Current DB: 14 AI-curated private draft projects linked back to examples.
- Retrained `media/ml/tiny_circuit_ai.pt`: dataset_size=216, curated_size=36, best_val_loss=0.061056. Evaluation: topology_accuracy=0.9716, next_component_accuracy=0.9602, risk_mae=0.0461.
- Checks: `manage.py check`, `makemigrations --check --dry-run`, `validate_ai_dataset --validated-only --limit 120 --json`, `test Dolg_APP.tests.LightweightLibraryIntegrationTests`, `evaluate_circuit_ai --include-curated`, `promote_ai_examples_to_projects --dry-run --json`, `check_demo_ready --json`, `check_data_integrity --json` - OK.

## 2026-05-31: admin/shop security gate

- Подробный отчет: [AUDIT_ADMIN_SHOP_20260531.md](AUDIT_ADMIN_SHOP_20260531.md).
- Закрыто: POST-only для корзины/сравнения, auth-cart bug в `repeat_order`, локальный `SECRET_KEY`, opt-in `ManifestStaticFilesStorage`, миграции Decimal-валидаторов, media-policy error `t1-ok`, неизвестные `legal_sources` в expert rules.
- Админка усилена как data-control слой: Product quality summary/actions, Order bulk audit, optimized `select_related/prefetch_related`, smoke 14/14 admin pages = 200.
- Проверки: `manage.py check`, `makemigrations --check --dry-run`, targeted tests, `check_data_integrity --json`, `check_demo_ready --json` — OK.

Сводный документ по тестированию и состоянию проекта.

---

## 1. Текущий статус

- `python manage.py check` — **0 ошибок** (включая 0 silenced).
- `python manage.py makemigrations --check --dry-run` — **No changes detected** после добавления scientific simulation stack и миграции `Dolg_APP.0010`.
- `python manage.py migrate` — локальная SQLite применяет `Dolg_APP.0010_schematicproject_approval_state_and_more`.
- Targeted regression нового этапа — **20/20 OK**:
  `python manage.py test Dolg_APP.tests.EngineeringReviewTests knowledge.tests.EngineeringLabTests knowledge.tests.PopulateKnowledgeLearningTests shop.tests.GlobalSearchAndDemoRouteTests --keepdb -v 2`.
- Targeted regression scientific stack — **13/13 OK**:
  `python manage.py test Dolg_APP.tests.SimulationAnalysisLibraryTests --keepdb -v 2`.
- Targeted regression scientific stack + lab — **16/16 OK**:
  `python manage.py test Dolg_APP.tests.SimulationAnalysisLibraryTests knowledge.tests.EngineeringLabTests --keepdb -v 1`.
- Search regression scientific stack — **7/7 OK**:
  `python manage.py test shop.tests.GlobalSearchAndDemoRouteTests --keepdb -v 2`.
- Demo-ready scientific stack smoke — **1/1 OK**:
  `python manage.py test shop.tests.DemoReadyCommandScientificStackTests --keepdb -v 2`.
- Targeted regression lightweight graph/formula/SVG stack — **11/11 OK**:
  `python manage.py test Dolg_APP.tests.LightweightLibraryIntegrationTests Dolg_APP.tests.EngineeringReviewTests --keepdb -v 2`.
- Targeted regression learning formula/SVG stack — **16/16 OK**:
  `python manage.py test knowledge.tests.LightweightLearningLibraryTests knowledge.tests.LearningModelAndGraderTests --keepdb -v 2`.
- Targeted regression expert-first stack — **18/18 OK**:
  `python manage.py test Dolg_APP.tests.ExpertSystemLibraryTests Dolg_APP.tests.EngineeringReviewTests Dolg_APP.tests.LightweightLibraryIntegrationTests shop.tests.DemoReadyCommandScientificStackTests --keepdb -v 2`.
- Targeted regression import preview + Learning-by-review — **11/11 OK**:
  `python manage.py test Dolg_APP.tests.EngineeringReviewTests --keepdb -v 2`.
- Demo-ready smoke после import-preview обновления — **1/1 OK**:
  `python manage.py test shop.tests.DemoReadyCommandScientificStackTests --keepdb -v 2`.
- Media Quality Gate regression — **10/10 OK**:
  `python manage.py test shop.tests.ProductImagePolicyTests --keepdb -v 1`.
- Datasheet Intelligence V1 regression — **3/3 OK**:
  `python manage.py test shop.tests.DatasheetIntelligenceTests --keepdb -v 2`.
- Browser smoke harness import -> review -> learning — **1 skipped без RUN_BROWSER_E2E**:
  `python manage.py test Dolg_APP.tests_browser --verbosity 1 --keepdb`.
- Search regression expert topics — **8/8 OK**:
  `python manage.py test shop.tests.GlobalSearchAndDemoRouteTests --keepdb -v 2`.
- Server regression затронутых приложений — **123/123 OK**:
  `python manage.py test Dolg_APP.tests knowledge.tests shop.tests --keepdb -v 1`.
- `python manage.py check_demo_ready --json` после `migrate`, `populate_knowledge` и `seed_legal_sources` — **OK**; текущие счетчики: 5 learning tracks, 16 lessons, 38 tasks, 12 demo projects; `scientific_stack` показывает версии NumPy/SciPy/Matplotlib/Pandas/python-engineering и service-smoke `fft_svg/bode_svg/monte_carlo_svg/signal_quality_svg/parameter_sweep_svg/dc_fallback`, `graph_stack`, `formula_stack`, `circuit_svg_stack` проверяют NetworkX/SymPy/Schemdraw, `expert_stack` проверяет jsonschema/rule-engine/Pint/Lark/Z3/scikit-fuzzy, а `legal_sources_stack` проверяет source retrieval, rule bibliography, search smoke, source-backed learning и AI training metadata.
- Новые проверки покрывают `ProjectReview`, `ProjectMeasurement`, LTspice/SPICE import subset, visual/server-side import preview, сохранение импортированной схемы в проект с review, Learning-by-review suggestions, self-hosted rule AI fallback, lab sweep, сравнение измерений, diagnostics learning track и поиск по `LTspice/derating`.
- Новые проверки scientific stack покрывают FFT peak detection, Bode plot для RC, Monte Carlo tolerance, THD/SINAD/ENOB signal quality, parameter sweep, NumPy DC fallback, Bode/Monte Carlo/Signal/Sweep Pro-only API, non-Pro fallback API, Pro toolbar в шаблоне, сохранение Pro-метрики в `ProjectMeasurement`, Pandas-статистику запусков и demo-ready service-smoke.
- Новые проверки lightweight stack покрывают NetworkX-топологию схем, предупреждения о схеме без GND, floating nodes, определение делителя, SymPy-формулы и эквивалентные выражения, Schemdraw SVG для учебных схем и lazy import тяжелой scientific-аналитики.
- Новые проверки expert-first stack покрывают rule pack validation через `jsonschema`, `rule-engine` predicates, Pint parsing русских и ASCII-единиц, Lark SPICE/LTspice import subset, Z3-подбор делителя, scikit-fuzzy risk score, expert findings в `ProjectReview`, `Expert trace` в `rule_ai` и поиск по `rule-engine/jsonschema/pint/z3/fuzzy`.
- `python manage.py check_demo_ready --json` — **OK**, URL smoke, no-Wikimedia media-policy, Media Quality Gate, scientific stack smoke, lightweight stack smoke, expert stack smoke, `cad_import_preview_details` и Learning-by-review smoke проходят.
- `python manage.py check_data_integrity --json` — аудит БД/данных: **0 ошибок, 0 предупреждений**; пустых, битых, Commons/curated и неподконтрольных активных изображений нет; `missing_datasheet_extracted=[]` для РЭБ-товаров; `catalog.media_quality` показывает 364 проверенных изображения, `average_score=100`, `error_count=0`, `warning_count=0`, `imagehash_available=true`.
- Тарифный слой Free/Pro/Enterprise проверяется через `Dolg_APP.services.entitlements`: Pro-аналитика и расширенный AI возвращают `plan_required` для Free, Pro получает scientific/AI features, Enterprise получает командные AI/org features. `check_demo_ready --json` содержит блок `entitlement_stack`.
- Datasheet Intelligence V1 заполняет `Product.parameters.datasheet_extracted` даже без live-доступа к PDF: fallback берет package, ratings, operating conditions, thermal/application hints из нормализованных параметров товара, а деталка товара показывает compact DI summary вместо сырого JSON.
- Каталог-медиа: 364 товара; 79 активных реальных фото перенесены в `products/verified/`, остальные позиции получают generated PNG fallback. Активные карточки не ссылаются на `products/commons/`, `products/curated/` или неподконтрольные внешние изображения; качество контролируется `shop.services.media_quality` через Pillow/ImageHash.
- Обучение и лаборатория: 5 опубликованных маршрутов, 16 уроков, 38 заданий; `/knowledge/lab/` входит в demo-ready URL smoke.
- `python manage.py test --keepdb -v 1` — для полного discovery-прогона в текущем окружении уперся в 15-минутный таймаут; актуальный проверенный gate пока разбит по приложениям.
- `.\scripts\run_browser_e2e.ps1` — **3/3 OK** для browser-smoke сценариев `/simulation/ → BOM → XLSX → cart`, `/cad/` и `/projects/`.
- ngspice.wasm подключён, AC/TRAN/DC анализы работают через Web Worker.
- JS-MNA fallback покрывает DC, если WASM недоступен.

---

## 2. Покрытие тестами по приложениям

| Приложение | Файл | Тестов | Что покрыто |
|---|---|---:|---|
| `accounts` | [accounts/tests.py](accounts/tests.py) | 8  | Модель `UserProfile`, автосоздание через сигнал, `full_address`, регистрация, логин, профиль, команда `setup_roles` и роль менеджера |
| `shop`     | [shop/tests.py](shop/tests.py)         | 64 | Модели `Category`/`Product`, view-страницы, `_apply_filters`, `search_suggest`, глобальный поиск по товарам/статьям/проектам/learning/tool topics включая FFT/Bode/Monte Carlo и expert topics, Datasheet Intelligence V1, demo-ready scientific/lightweight/expert stack smoke, `api_component_search`, анализатор «лучше/хуже» в сравнении, `api_bom_match`, server-side XLSX-экспорт BOM, `api_bom_add_all`, `compare_toggle`/`compare_clear` |
| `orders`   | [orders/tests.py](orders/tests.py)     | 16 | Модель `Order`, генерация `order_number`, полный flow checkout (создание Order+OrderItem, списание stock, очистка корзины, email-уведомление, отказ при нехватке stock, требование адреса, пустая корзина → редирект), отмена заказа (возврат stock, статус, защита от чужих), повтор заказа |
| `Dolg_APP` | [Dolg_APP/tests.py](Dolg_APP/tests.py), `Dolg_APP/tests_*.py` | 58 + 101 role-matrix | Модели проектов, `ProjectReview`, expert findings, rule pack validation, Pint unit parsing, Lark import, Z3 solver, fuzzy risk, NetworkX topology metrics, `ProjectMeasurement`, CAD import, self-hosted AI, Pro FFT/Bode/Monte Carlo, signal quality THD/SINAD/ENOB, parameter sweep, NumPy fallback, Pandas simulation stats, Pro toolbar smoke, сохранение Pro-метрик, PCB layout, share-token, demo populate, role/plan regression suites |
| `knowledge` | [knowledge/tests.py](knowledge/tests.py) | 29 | Энциклопедия, связанные товары и контекстные расчеты в статьях, модели обучения, grader `math/circuit/simulation`, SymPy formula grading, Schemdraw учебные SVG, инженерная лаборатория, `python-engineering` validation backend, API `/knowledge/lab/api/`, seed `populate_knowledge` для learning tracks |

**Итого по серверным тест-файлам: текущий счетчик по обнаруженным `test_` — 247 тестов в `shop/Dolg_APP/knowledge`, включая role-matrix suites в `Dolg_APP/tests_*.py`. Последний полный gate до lightweight/expert stack был разбит по targeted-прогонам; новый слой закрыт targeted-прогонами 18/18, 16/16 и 8/8 OK. Полный стандартный прогон лучше запускать разбивкой по приложениям или с большим таймаутом.**

---

## 3. Как запускать

```bash
# Активировать venv (Windows)
.\.venv\Scripts\activate

# Проверка конфигурации
python manage.py check

# Полная проверка с coverage (Windows PowerShell)
.\scripts\run_checks.ps1

# Все тесты вручную
python manage.py test accounts shop orders Dolg_APP

# Отдельное приложение
python manage.py test shop
python manage.py test orders
python manage.py test accounts
python manage.py test Dolg_APP

# Browser/e2e smoke (требует Microsoft Edge и Playwright)
.\scripts\run_browser_e2e.ps1

# Вердикт стандартного запуска: "Ran 124 tests ..." → OK (skipped=6).
# Вердикт browser-smoke: "Ran 3 tests ..." → OK.

# Аудит данных перед демонстрацией
python manage.py check_demo_ready --json
python manage.py check_data_integrity --json
```

Тесты используют `--keepdb` стратегию косвенно: SQLite in-memory через `Dolg_PR/settings.py` (DATABASES.default использует `:memory:` под `test`-командой).

---

## 4. История ключевых изменений тестового слоя

1. **2026-04-23:** свернуты ~30 мелких `*.txt`/`*.md`-отчётов в этот документ.
2. **2026-04-24:** добавлен `Dolg_APP/tests.py` с 17 тестами на `SchematicProject`, API проектов и `populate_demo_projects`. К 2026-04 — 34 теста.
3. **2026-04-26:** включены тесты квот симуляции (`SimulationQuota`).
4. **2026-04-27:** расширены `shop/tests.py` (31 тест: `_apply_filters`, `search_suggest`, BOM-API, compare-сессия) и `orders/tests.py` (14 тестов: полный checkout flow, отмена заказа, генерация `order_number`). Итог — 66 тестов.
5. **2026-05-03:** добавлены тесты повторного заказа и email-уведомления checkout, настроены `.coveragerc`, `scripts/run_checks.ps1` и GitHub Actions. Итог — 68 тестов.
6. **2026-05-03:** добавлены роли менеджера, история версий схем, журнал результатов симуляции, гостевой demo-режим `/simulation/`, DRC-проверка и PDF-экспорт схемы; расширены тесты `accounts` и `Dolg_APP`. Итог — 74 теста.
7. **2026-05-03:** добавлены `api_component_search`, поиск товара каталога из панели свойств компонента, учёт явного `catalog_ref` в BOM и маппинг NPN/PNP на категорию транзисторов. Итог — 78 тестов.
8. **2026-05-03:** добавлен server-side XLSX-экспорт BOM через `openpyxl`, общий helper расчёта BOM и проверка структуры Excel-книги в тестах. Итог — 79 тестов.
9. **2026-05-03:** добавлены Playwright browser-smoke для `/simulation/`, DRC/BOM-проверки номиналов и SPICE-моделей, helper `ensureComponentPorts` для старых схем без `ports`. Стандартный итог — 83 OK + 1 skipped, browser-smoke отдельно — 1/1 OK.
10. **2026-05-03:** расширены browser-smoke сценарии для `/cad/` и `/projects/`, добавлена `normalizeSchemeData()` и единая нормализация схем при загрузке/сохранении. Стандартный итог — 83 OK + 3 skipped, browser-smoke отдельно — 3/3 OK.
11. **2026-05-17:** добавлен `check_data_integrity`: проверка изображений товаров, hash-дублей, запрета Wikimedia/Commons, параметров РЭБ, материалов энциклопедии, внутренних ссылок и структуры demo-схем. Seed demo-схем теперь назначает позиционные обозначения и ортогональные маршруты.
12. **2026-05-18:** media-слой каталога переведён на выборочную no-Wikimedia policy: точные локальные assets сохраняются, а для неподтверждённых/проблемных позиций `apply_curated_product_photos` генерирует technical placeholder PNG через `Pillow`. `import_commons_product_photos` отключён, `check_demo_ready` и `check_data_integrity` блокируют `products/commons/*`, `products/curated/*` и Wikimedia URL.
13. **2026-05-25:** добавлен `apply_verified_product_photos`: проверенные реальные фото из старого локального кеша копируются в `products/verified/`; denylist оставляет супы, еду, воду, разбитые экраны и неверные товарные кадры на generated fallback.
13. **2026-05-17:** добавлен практикум `knowledge`: модели `LearningTrack/Lesson/Task/Attempt/Progress`, автопроверка math/circuit/simulation задач и redirect старого `/learn/`.
14. **2026-05-17:** добавлена инженерная лаборатория `/knowledge/lab/`: расчеты транзисторного ключа, NE555, стабилизатора, RC-антидребезга и теплового запаса; второй learning track использует общий service-layer лаборатории. Итог — 146 тестов.
15. **2026-05-17:** добавлен scientific simulation stack: NumPy/SciPy/Matplotlib/Pandas для FFT, Bode plot, Monte Carlo tolerance, THD/SINAD/ENOB signal quality, parameter sweep, server-side DC fallback и статистики запусков; `python-engineering` подключен как validation backend лаборатории. Pro-метрики сохраняются в `ProjectMeasurement`, глобальный поиск находит FFT/Bode/Monte Carlo/SciPy/THD/sweep, а `check_demo_ready` проверяет scientific stack service-smoke. Целевой прогон затронутых приложений — 123/123 OK.
16. **2026-05-18:** добавлен lightweight graph/formula/SVG stack перед нейронным sprint: `networkx` в `Dolg_APP/services/schematic_graph.py`, `sympy` в `knowledge/services/formula_steps.py`, `schemdraw` в `knowledge/services/circuit_svg.py`. Review, rule AI и learning grader используют общий service-layer; `check_demo_ready` проверяет `graph_stack/formula_stack/circuit_svg_stack`; PyTorch/GOLEM не входят в основной runtime.
17. **2026-05-18:** добавлен expert-first stack: `jsonschema` + `rule-engine` для rule packs, Pint для unit-safe номиналов, Lark для SPICE/LTspice subset, Z3 для constraint-подбора, scikit-fuzzy для мягкой оценки риска. `ProjectReview` получает `expert_findings` и fuzzy-risk, `rule_ai` отвечает по `Expert trace`, `check_demo_ready` проверяет `expert_stack`; OR-Tools/RDFLib/PyTorch/GOLEM остаются roadmap.
18. **2026-05-19:** добавлен Media Quality Gate: `ImageHash` + `PyWavelets` поверх Pillow, сервис `shop/services/media_quality.py`, проверки читаемости, размера, пустоты, aspect ratio, edge density и perceptual hash. `check_data_integrity` и `check_demo_ready` выводят media-quality блок; generated placeholders не считаются perceptual-дублями.
19. **2026-05-25:** расширен self-hosted AI-помощник: `rule_ai` различает intent-режимы GND, measurement, BOM, import, learning, derating, recommend и fix-plan; API возвращает `intent`, `confidence`, `quick_actions`, а UI показывает режим и быстрые действия. Добавлены regression-тесты на GND-вопрос и ответ по сохраненному измерению.
20. **2026-05-25:** добавлен Self AI V2 и tiny PyTorch backend: `/api/ai/context/`, карточка "Разбор схемы" в AI-панели, 20 сообщений истории + `session_summary`, structured quick actions, `context_sources`, lazy neural backend `Dolg_APP/ml/neural.py`, optional `requirements-ai.txt`, команда `train_tiny_circuit_ai`. Targeted tests `EngineeringReviewTests + LightweightLibraryIntegrationTests` — **25/25 OK**; `check_demo_ready --json` показывает `neural_stack` OK.
21. **2026-05-26:** добавлен entitlement-layer для Free/Pro/Enterprise: Pro endpoints, AI chat/context/pipeline и org-level Enterprise функции проверяются через общий feature matrix; API возвращает `plan_required`, `token_usage`, `entitlements`, а `/api/usage/today/` возвращает `plan/features/feature_flags`.
22. **2026-05-26:** добавлен безопасный opt-in контур AI-обучения пользовательских схем: поле профиля `allow_ai_training`, команда `collect_ai_training_examples`, поддержка curated schemes в `train_tiny_circuit_ai --include-curated`. Обучение остается пакетным, не во время ответа ассистента.
23. **2026-05-26:** добавлена карта легальных источников `docs/LEGAL_RESOURCE_MAP_20260526.md`: внешние подборки используются только как список тем/названий, а AI/diploma/code corpus строится на официальной документации, открытых учебниках, datasheet, demo-проектах и opt-in пользовательских схемах.
24. **2026-05-26:** `legal_sources.json` превращен в active evidence-layer: `find_legal_sources`, `sources_for_rule`, `sources_for_learning_topic`, source-aware retrieval в Self AI, компактные источники в review HTML/PDF, группа `Источники и документация` в глобальном поиске/autocomplete, source-backed learning seed и metadata для `AITrainingExample`. Проверки: `LegalSourcesTests` — **3/3 OK**, `GlobalSearchAndDemoRouteTests + DemoReadyCommandScientificStackTests` — **12/12 OK**, `DataIntegrityLegalSourcesTests` — **1/1 OK**, AI GND/retrieval regression — **2/2 OK**.

---

## 5. Что осталось из рекомендаций

- **`coverage.py`** — настроен через `.coveragerc`; локальный запуск: `.\scripts\run_checks.ps1`.
  Текущий отчёт по прикладному коду после исключения служебных entrypoint/management-файлов — **77 %** строк.
- **CI** — добавлен GitHub Actions workflow `.github/workflows/django.yml` с `python manage.py check`, тестами и coverage-отчётом.
- **Front-end-тесты:** Playwright smoke реализован для `/simulation/ → BOM → XLSX → cart`, `/cad/` и `/projects/`. Остаются сценарии: «расчет в лаборатории -> схема -> измерение -> обучающее задание», «нарисовать делитель → запустить DC», «открыть демо RC-фильтр → AC → −3 дБ-маркер виден», «экспортировать SVG/PDF», visual regression desktop/mobile.
- **Media-аудит:** текущий базовый слой закрыт локальными assets + generated-заглушками и Media Quality Gate. Следующий шаг — optional allowlist официальных изображений производителей/дистрибьюторов, если есть права/ключи API; неподтвержденные product-shot и Wikimedia не включать.

---

## 6. Что было удалено при консолидации (2026-04-23)

`FINAL_REPORT.txt`, `FINAL_STATUS.txt`, `FINAL_TEST_REPORT.md`, `TEST_FINAL.md`, `TEST_FINAL.txt`, `TEST_FINAL_REPORT.md`, `TEST_RESULT.txt`, `TEST_RESULT_SUMMARY.txt`, `check.txt`, `check_final.txt`, `conclusion.txt`, `done.txt`, `end.txt`, `final.txt`, `final_check.txt`, `final_output.txt`, `final_result.txt`, `final_test.txt`, `report.txt`, `result.txt`, `result_final.txt`, `status.txt`, `status_final.txt`, `test.txt`, `test_completion.txt`, `test_done.txt`, `test_final_status.txt`, `test_report.md`, `test_status.txt`.

Все 29 файлов содержали либо одинаковый текст «Тестирование завершено. Результат: OK», либо обрывки старых пробных запусков.

## 2026-05-25: review i18n

- Добавлен `Dolg_APP/services/review_i18n.py`: перевод пользовательских сообщений проверки схемы, fault library, expert findings, статусов и рекомендаций на русский язык.
- HTML/PDF review-отчет усилен демонстрационными блоками: русские метрики, expert findings, evidence, fault-сценарии и сохраненные измерения.
- `EngineeringReviewTests` проверяет, что отсутствующий GND, severity label, self-hosted AI reply, GND-intent и measurement-intent выводятся по-русски.
- `check_demo_ready --json` расширен smoke-проверками `review_russian_i18n` и `review_metric_rows_ru`.
- `check_demo_ready --json` также проверяет optional neural stack: наличие PyTorch и обученной tiny-модели `media/ml/tiny_circuit_ai.pt`.

## 2026-05-25: engineering artifact ingestion

- Добавлены модели `EngineeringArtifact` и `AITrainingExample`, миграция `Dolg_APP.0015_engineeringartifact_aitrainingexample`.
- Добавлен сервис `Dolg_APP/services/artifact_ingestion.py` и команда `python manage.py ingest_engineering_artifacts`: DOCX/PDF/PPTX/DXF, P-CAD NET/DRC/ERC, OLE metadata; DWG/MS14 сохраняются как metadata-only артефакты с предупреждением о конвертации.
- `ProjectReview` теперь учитывает внешние CAD-проверки, readiness к сборке и reliability summary; review i18n добавляет `title_ru`, `evidence_ru`, `recommendation_ru` для findings.
- `rule_ai` получает artifact memory и learning-by-artifact подсказки, но финальный инженерный verdict остается за expert rules + человеком.
- Проверки: `python manage.py test Dolg_APP.tests.ArtifactIngestionTests Dolg_APP.tests.EngineeringReviewTests Dolg_APP.tests.LightweightLibraryIntegrationTests --verbosity 2` -> **29/29 OK**.
- `python manage.py check_demo_ready --json` -> **OK**, новый блок `artifact_stack` проверяет `pypdf/python-docx/python-pptx/ezdxf/olefile`, P-CAD DRC/NET, DXF, DWG/MS14 stubs, learning-by-artifact и AI training examples.

## 2026-05-31: Self AI / PyTorch dataset sprint

- Расширен `Dolg_APP/services/ai_training.py`: сбор AI examples теперь поддерживает opt-in/demo-схемы, опубликованные learning tasks, сохраненные `ProjectReview` snapshots и `EngineeringArtifact`.
- Добавлены dataset-команды:
  - `python manage.py collect_ai_training_examples --source all --limit N`;
  - `python manage.py validate_ai_dataset --json`;
  - `python manage.py export_ai_dataset --output ...jsonl`;
  - `python manage.py evaluate_circuit_ai --include-curated`.
- `AITrainingExampleAdmin` получил dashboard: total/validated/unvalidated, scheme_data coverage, source_ids, teacher_rules, evidence_kind, topology/source distribution и результат быстрой валидации.
- Self AI теперь возвращает `skills` как структурированный список возможностей: diagnose scheme, explain review, suggest measurement, choose nominal, compare variants, learning task from error, artifact summary, defense demo script.
- Pro/Enterprise deep-hint подключен к `/api/ai/chat/` и `/api/ai/context/`: PyTorch дает вероятностную подсказку по topology/risk/next component, но финальный инженерный verdict остается за expert rules + человеком.
- `api_ai_pipeline_info` возвращает summary AI dataset вместе с neural backend metadata.

Проверки:

- `python manage.py check` -> OK.
- `python manage.py makemigrations --check --dry-run` -> OK, No changes detected.
- `python manage.py validate_ai_dataset --validated-only --limit 20` -> OK, scanned=12, errors=0, warnings=0.
- `python manage.py collect_ai_training_examples --source all --limit 5 --dry-run --json` -> OK.
- `python manage.py export_ai_dataset --limit 5 --output Dolg_APP/ml/dataset/exports/ai_training_dataset_smoke.jsonl --json` -> OK; smoke-файлы после проверки удалены.
- Admin/API smoke: `/admin/Dolg_APP/aitrainingexample/`, `/staff/ml-training/`, `/api/ai/pipeline/info/` -> 200.
- Targeted tests: `Dolg_APP.tests.AIAssistantModuleTests` + `Dolg_APP.tests_premium.AIPipelineTests` -> **9/9 OK**.

## 2026-05-31: Self AI graph-feature upgrade

- Добавлен curated baseline для нейробалабола: `collect_ai_training_examples --source curated` создает 8 идемпотентных примеров по делителю, GND, LED, RC, floating fragment, source-short и BOM/model binding.
- `collect_ai_training_examples --source all --limit 50` собрал корпус из 58 валидированных записей: 14 review/demo/opt-in схем, 8 curated cases и 36 learning tasks.
- `Dolg_APP/ml/neural.py` обновлен до `0.3.0-tiny-graph-pytorch`: feature vector расширен до 30 признаков, добавлены 10 NetworkX-derived признаков связности, floating/isolated components, циклов, output node, topology one-hot и coverage путей до GND.
- Старые несовместимые модели теперь не ломают AI: при несовпадении `state_dict` backend откатывается на fresh baseline и просит переобучение.
- Добавлена staff-страница `/staff/ml-dataset/`: сводка корпуса, ошибки/предупреждения валидации, evidence kind, topology, teacher rules, legal sources и metadata tiny model.
- AI-панель `/simulation/` показывает PyTorch deep hint отдельным компактным блоком в карточке “Разбор схемы” и добавляет краткую neural-сводку в ответ чата.

Проверки:

- `python manage.py collect_ai_training_examples --source curated --json` -> OK, created=8.
- `python manage.py collect_ai_training_examples --source all --limit 50 --json` -> OK, total=58, validated=58.
- `python manage.py validate_ai_dataset --validated-only --limit 100 --json` -> OK, scanned=58, errors=0, warnings=0.
- `python manage.py train_tiny_circuit_ai --include-curated --max-curated 300 --size 180 --epochs 80 --json` -> OK, model version `0.3.0-tiny-graph-pytorch`, dataset_size=202, curated_size=22, best_val_loss=0.312815.
- `python manage.py evaluate_circuit_ai --include-curated --max-curated 100 --size 120 --json` -> OK, topology_accuracy=0.9648, next_component_accuracy=0.9577, risk_mae=0.0636.
- Staff/API smoke: `/staff/ml-training/`, `/staff/ml-dataset/`, `/admin/Dolg_APP/aitrainingexample/`, `/api/ai/pipeline/info/` -> 200.
- Deep-hint smoke: `build_rule_based_reply(... include_deep_hint=True)` -> trained=True, model `0.3.0-tiny-graph-pytorch`.
- Targeted tests: `Dolg_APP.tests.AIAssistantModuleTests` + `Dolg_APP.tests_premium.AIPipelineTests` -> **9/9 OK**.

## 2026-06-01: REB catalog quality normalization

- Добавлен service-layer `shop/services/reb_catalog_quality.py`: нормализация РЭБ-каталога после сидов `populate_reb_products` / `populate_catalog_v2`.
- Добавлена команда `python manage.py normalize_reb_catalog`: восстанавливает `part_number`, уточняет `package_type`, выводит `mounting`, добавляет rating-поля (`max_voltage`, `current`, `power`, `supply_voltage`) и `datasheet_url`/family reference для REB-карточек.
- После нормализации выполнен `python manage.py enrich_datasheets --all --missing-only --json`: заполнены metadata fallback records `Product.parameters.datasheet_extracted` для новых datasheet URL.
- Исправлен постоянный Django warning в `Dolg_APP/templates/tools/simulation.html`: многострочный `{# ... #}` заменен на `{% comment %}...{% endcomment %}`.

Проверки:

- `python manage.py normalize_reb_catalog --json` -> OK, changed=201; затем повторный запуск -> changed=4 для добивки `XL6009`, `TOR-220uH`, `HL-1U-5V`, `JQX-105F-12V`.
- `python manage.py enrich_datasheets --all --missing-only --json` -> OK, processed=184, metadata_fallback.
- `python manage.py check` -> OK, 0 warnings.
- `python manage.py makemigrations --check --dry-run` -> OK, No changes detected.
- `python manage.py test shop.tests.RebCatalogQualityTests shop.tests.DatasheetIntelligenceTests --keepdb -v 2` -> **6/6 OK**.
- `python manage.py check_data_integrity --json` -> OK, 0 errors, 0 warnings; `invalid_reb=0`, `missing_datasheets=0`, `missing_datasheet_extracted=0`, `missing_rating_limits=0`.
- `python manage.py check_demo_ready --json` -> OK, 0 errors, 0 warnings.
