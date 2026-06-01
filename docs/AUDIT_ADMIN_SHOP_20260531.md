# Аудит и правки: магазин, безопасность, админка

Дата: 2026-05-31

## Что закрыто

- Настройки безопасности:
  - добавлен локальный `SECRET_KEY` в `.env`;
  - `ManifestStaticFilesStorage` переведен в opt-in через `USE_MANIFEST_STATIC=1`, чтобы локальная демо-админка не падала без `collectstatic`;
  - `manage.py check` проходит без предупреждения о дефолтном ключе.
- Магазин:
  - state-changing действия корзины и сравнения переведены на POST: `add_to_cart`, `remove_from_cart`, `update_cart_item`, `compare_toggle`, `compare_clear`;
  - шаблоны корзины, сравнения и карточки товара обновлены под POST + CSRF;
  - `repeat_order` теперь кладет товары в корзину авторизованного пользователя, а не в гостевую session-корзину.
- Данные и библиография:
  - создана миграция Decimal-валидаторов для `Product.price`, `Order.total_amount`, `OrderItem.price`;
  - legal source ids в экспертных правилах нормализованы к реальным источникам;
  - добавлены источники для IPC/IEC/EU/JLCPCB/Coilcraft;
  - товар `t1-ok` переведен на контролируемую generated-заглушку без Wikimedia.
- Админка:
  - `ProductAdmin` расширен до инструмента контроля данных: datasheet/model/image status, quality summary, фильтр Datasheet Quality, bulk actions для DI и data-review;
  - `CategoryAdmin` показывает счетчик товаров;
  - `OrderAdmin` получил оптимизированный счетчик позиций, `list_select_related`, audit-log для bulk смены статусов и сообщения админу;
  - user/admin lists оптимизированы через `select_related`/`prefetch_related`;
  - проектные, review, moderation и AI-training admin lists получили `list_select_related`;
  - admin site header/title обновлены под инженерную панель DOLG.

## Проверки

- `python manage.py check` - OK.
- `python manage.py makemigrations --check --dry-run` - OK, No changes detected.
- Admin smoke через Django Client - 14/14 ключевых страниц отдали 200:
  - index, products, categories, cart items;
  - orders, order items;
  - users, user profiles;
  - articles, learning tasks;
  - moderation cases;
  - schematic projects, project reviews, AI training examples.
- Targeted tests:
  - `shop.tests.CategoryModelTest ProductModelTest ShopViewsTest CatalogFilterTests SearchSuggestTests` - 18/18 OK;
  - `orders accounts moderation` - 5/5 OK;
  - `shop.tests.ComponentSearchTests BomMatchTests BomAddAllTests CompareToggleTests CompareAnalyzerTests` - 27/27 OK;
  - `shop.tests.DatasheetIntelligenceTests` - 3/3 OK;
  - `knowledge.tests.LegalSourcesTests` - 3/3 OK;
  - `shop.tests.DataIntegrityLegalSourcesTests DemoReadyCommandScientificStackTests` - 3/3 OK.
- `python manage.py check_data_integrity --json` - OK:
  - errors: 0;
  - media quality: 364 checked, average_score 100, error_count 0, warning_count 0;
  - legal source errors: 0.
- `python manage.py check_demo_ready --json` - OK:
  - scientific, graph, formula, circuit SVG, expert, catalog filters, legal sources, artifact, moderation, entitlement, neural, media quality, project session stacks прошли.

## Остатки

- Каталог все еще имеет предупреждения качества данных:
  - 91 РЭБ-товар с неполными инженерными полями;
  - 184 РЭБ-товара без `datasheet_url`.
- В `check_demo_ready` Datasheet Intelligence работает через fallback, но optional parser-зависимости отсутствуют:
  - `PyMuPDF` / `fitz`;
  - `pdfplumber`.
- Админку можно усилить следующим слоем:
  - отдельный admin dashboard по качеству каталога: missing datasheet, missing rating limits, needs review, image policy;
  - bulk-команда enrichment прямо из админки с прогрессом и журналом;
  - Grafana/metrics для заказов, AI, ML training, dataset import, simulation jobs;
  - отдельная очередь data-review для товаров и source-aware rules;
  - audit-события для редактирования ключевых инженерных полей товара.

## Вывод

Критичные проблемы магазина/админки закрыты: GET-действия с изменением состояния убраны, локальная админка больше не зависит от manifest static, повтор заказа работает для авторизованных пользователей, admin smoke и demo/data checks зеленые. Следующий фронт - не чинить аварии, а делать админку центром сбора и контроля инженерных данных.

## Дополнение 2026-05-31: усиление админки как data-control панели

- `ProductAdmin`:
  - добавлен dashboard качества каталога: всего товаров, РЭБ, РЭБ без datasheet, извлеченный Datasheet Intelligence, отсутствующие изображения, позиции на проверке, низкий остаток и отсутствие на складе;
  - добавлено быстрое редактирование `lifecycle_status`, `price`, `stock` прямо из списка;
  - оставлены bulk actions для Datasheet Intelligence и флагов data-review.
- `SchematicProjectAdmin`:
  - список проектов расширен до проектных сеансов: организация, visibility, approval_state, счетчики версий, симуляций, review и измерений;
  - добавлен dashboard проектных данных: активные/демо/публичные/командные проекты, pending review, review snapshots, simulation runs, measurements;
  - в форму проекта добавлены `organization`, `visibility`, `approval_state`, `share_token`, `deleted_at`.
- `ProjectReviewAdmin`:
  - добавлены цветные score/status, счетчик findings и readonly-сводка ошибок, предупреждений, рекомендаций и fault cases;
  - JSON-блоки разнесены по fieldsets: findings, metrics/sections, input snapshots.
- `SimulationRunAdmin` и `ProjectMeasurementAdmin`:
  - добавлен прогресс симуляций;
  - для измерений показаны expected value и delta.
- `EngineeringArtifactAdmin`:
  - добавлены счетчики facts/warnings/errors, размер файла и bulk-статусы parsed/partial/unsupported;
  - добавлено действие создания `AITrainingExample` из summary инженерного артефакта.
- `AITrainingExampleAdmin`:
  - добавлены preview prompt, source/rule metadata и bulk validation/unvalidation для подготовки датасета.
- `knowledge/admin.py`:
  - убраны N+1 `.count()` для категорий и learning tracks через аннотации;
  - добавлены `list_select_related` и `date_hierarchy` для статей, уроков, заданий, попыток и прогресса.
- `accounts/admin.py` и `moderation/admin.py`:
  - добавлены autocomplete/date hierarchy, а moderation bulk actions оформлены через `@admin.action`.

Проверки после правок:

- `python manage.py check` - OK, 57.7s.
- `python manage.py makemigrations --check --dry-run` - OK, No changes detected, 59.4s.
- Admin smoke через Django Client c `secure=True` и `HTTP_HOST=localhost` - 15/15 страниц отдали 200:
  - index;
  - products, categories;
  - schematic projects, project reviews, simulation runs, measurements, engineering artifacts, AI training examples;
  - orders;
  - articles, learning tracks, learning lessons;
  - moderation cases;
  - user profiles.

Остаток по админке:

- вынести тяжелые bulk actions (`Datasheet Intelligence`, artifact ingestion, AI dataset building) в фоновые jobs с прогрессом;
- подключить Grafana/metrics к job status, ML training, dataset import, simulation/review latency и admin activity;
- добавить отдельный queue-screen для data-review товаров и артефактов;
- расширить audit для ручного изменения критичных инженерных полей товара, схемы, review и AI examples.
