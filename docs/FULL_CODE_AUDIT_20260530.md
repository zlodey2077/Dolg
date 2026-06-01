# Полный аудит кода DOLG

Дата: 2026-05-30.  
Режим: чтение, фиксация рисков и планов. Исправления в код не вносились.

## Обновление 2026-05-31

По команде пользователя исправлены первые критичные пункты:

- `AUD-009`: комментарии к проектам теперь проходят object-level проверку через `_project_for_read`.
- `AUD-010`: тяжелые inline endpoints `export pdf`, `monte_carlo`, `circuit_python`, `engineering_review` закрыты авторизацией и дневной квотой; duplicate Monte Carlo endpoint дополнительно закрыт Pro-gate.
- `AUD-011`: traceback больше не возвращается клиенту в `api_engineering_review`; детали уходят в server log.
- `AUD-012`: создание review переведено на write-доступ; `latest` больше не создает snapshot для read-only пользователя.
- `AUD-013`: сохранение схемы больше не блокируется обычными DRC-ошибками; блокируется только некорректная структура `scheme_data`.
- `AUD-014`: mock SSO дополнительно выключается вне `DEBUG`, если явно не задан `ALLOW_MOCK_SSO`, и проверяет `allowed_domains`.

Добавлены регрессионные тесты: `Dolg_APP/tests_access_hardening.py`.

Проверка после правок:

- `.\.venv\Scripts\python.exe -m py_compile Dolg_APP\views.py Dolg_APP\sso_views.py Dolg_APP\tests_access_hardening.py` — OK.
- `FAST_TESTS=1 .\.venv\Scripts\python.exe manage.py test Dolg_APP.tests_access_hardening -v 2` — 7 тестов, OK.
- `.\.venv\Scripts\python.exe manage.py check` — OK, но остается warning о default `SECRET_KEY` при `DEBUG=False`.
- `.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` — FAIL: обнаружены ожидаемые миграции для `orders` и `shop` по полям `price/total_amount`. Это не связано с текущими правками и вынесено в следующий аудит моделей/админки.

## Область аудита

Проверены основные зоны проекта:

- настройки запуска и deployment: `Dolg_PR/settings.py`, `Dolg_PR/urls.py`;
- публичные и авторизованные API: `Dolg_APP/views.py`, `Dolg_APP/urls.py`;
- проектный сеанс, CAD/SIM, review, AI, комментарии: `Dolg_APP`;
- роли, Enterprise, SSO, API-токены: `Dolg_APP/org_views.py`, `Dolg_APP/sso_views.py`;
- модерация: `moderation`;
- профиль и загрузки файлов: `accounts`;
- заказы и платежи: `orders`;
- зависимости: `requirements*.txt`, `pyproject.toml`;
- техническая документация в `docs`.

## Проверки и результат

| Проверка | Результат |
|---|---|
| `manage.py check` | не завершилась за ~60 секунд при параллельном запуске с другими проверками |
| `makemigrations --check --dry-run` | не завершилась за ~60 секунд при параллельном запуске |
| `check_demo_ready --json` | не завершилась за ~60 секунд при параллельном запуске |
| `check_data_integrity --json` | не завершилась за ~60 секунд при параллельном запуске |
| импорт `Dolg_PR.settings` | около 4.5 секунд, выводит warning о default `SECRET_KEY` при `DEBUG=False` |

Вероятная причина долгого `manage.py check`: кастомный system check в `Dolg_APP/checks.py` рекурсивно сканирует все `*.html` от `BASE_DIR`, а не только реальные template-директории.

## Критичные и высокие риски

### AUD-009: доступ к комментариям приватных проектов не проверяется

Серьезность: high.  
Область: security / privacy.  
Где: `Dolg_APP/views.py:555`, `Dolg_APP/views.py:574`, `Dolg_APP/views.py:616`.

`api_comments_list` фильтрует комментарии по `project_id`, но не проверяет, имеет ли пользователь доступ к самому проекту. `api_comments_create` берет проект через `SchematicProject.all_objects.get(pk=project_id)` и тоже не вызывает `_project_for_read` или `_project_for_write`.

Риск: авторизованный пользователь, знающий id приватного проекта, может читать видимые комментарии к нему и оставлять новые комментарии.

План исправления:

1. В `api_comments_list` при `project_id` сначала получать проект через `_project_for_read(request.user, project_id)`.
2. В `api_comments_create` для проектных комментариев использовать `_project_for_read` или отдельное право `can_comment`.
3. Добавить тест: чужой приватный проект не отдает комментарии и не принимает POST.

Материал для диплома: пример важности object-level permissions в web-ориентированной CAD-среде.

### AUD-010: часть тяжелых CAD/SIM API открыта без авторизации и feature-gate

Серьезность: high.  
Область: security / availability / subscriptions.  
Где: `Dolg_APP/views.py:1963`, `Dolg_APP/views.py:2097`, `Dolg_APP/views.py:2124`, `Dolg_APP/views.py:2153`.

Без `login_required` и без тарифных проверок работают:

- `api_export_scheme_pdf`;
- `api_monte_carlo`;
- `api_export_circuit_python`;
- `api_engineering_review`.

Отдельно: в проекте есть Pro-gated endpoint `api_simulation_monte_carlo`, но рядом остается открытый `api_monte_carlo`, который обходит тарифную модель.

Риск: обход Pro-функций, нагрузка на CPU/RAM, генерация PDF/code/review анонимными запросами.

План исправления:

1. Добавить `login_required` на тяжелые endpoints или строгий anonymous quota.
2. `api_monte_carlo` закрыть через `pro_monte_carlo` или удалить дубль, если он устарел.
3. Ограничить размер `request.body`, число компонентов и `iterations`.
4. Добавить тесты Free/Pro/anonymous для каждого endpoint.

### AUD-011: `api_engineering_review` возвращает хвост traceback клиенту

Серьезность: high.  
Область: security / information disclosure.  
Где: `Dolg_APP/views.py:2186`.

При ошибке сборки review endpoint добавляет в JSON `traceback.format_exc()[-2000:]`.

Риск: раскрытие внутренних путей, имен классов, деталей service-layer и потенциальных секретных фрагментов контекста.

План исправления:

1. Клиенту возвращать только короткий безопасный код ошибки.
2. Traceback писать в logger/Sentry.
3. В `DEBUG=True` можно оставить расширенную диагностику только локально.

### AUD-012: review создается через read-доступ

Серьезность: high.  
Область: access control / data integrity.  
Где: `Dolg_APP/views.py:1795`, `Dolg_APP/views.py:1803`, `Dolg_APP/views.py:1020`.

`api_project_review_create` и `api_project_review_latest` получают проект через `_project_for_read`, но `_create_project_review` создает `ProjectReview` и `ProjectEvent`.

Риск: пользователь с read-доступом к командному, demo или public-проекту может менять историю проекта и создавать новые snapshots review.

План исправления:

1. Разделить “посмотреть review” и “создать новый review”.
2. Для создания использовать `_project_for_write` или новое право `project.review.create`.
3. `latest` не должен создавать review автоматически для read-only пользователя.

### AUD-013: сохранение схемы блокируется DRC-ошибками

Серьезность: high для UX, medium для безопасности.  
Область: CAD/SIM workflow.  
Где: `Dolg_APP/views.py:1342`, `Dolg_APP/views.py:1351`.

`api_project_save_scheme` вызывает `_validate_scheme_data` и возвращает `400 DRC failed`, если схема не проходит проверку.

Риск: пользователь может не сохранить черновик неполной схемы. Это похоже на причину жалобы “сохранить схему не работает”. Для CAD-редактора ошибка DRC должна блокировать экспорт/approval/review, но не обычное сохранение draft.

План исправления:

1. Сохранять draft всегда, если JSON валиден и квоты не превышены.
2. DRC-результат сохранять в ответе, версии или отдельном поле.
3. Для “готово к сборке” оставить строгую проверку.

### AUD-014: Mock SSO может самозаписывать пользователя в организацию

Серьезность: high для production, acceptable-risk для локальной демо.  
Область: enterprise / authentication.  
Где: `Dolg_APP/sso_views.py:33`, `Dolg_APP/sso_views.py:53`, `Dolg_APP/sso_views.py:85`.

Mock SSO принимает email из POST, создает пользователя и добавляет его в организацию как `engineer`, если `sso_enabled=True`. В `org_settings` есть `allowed_domains`, но в callback домен email не проверяется.

Риск: если mock SSO случайно включен в публичном стенде, пользователь может сам войти в организацию.

План исправления:

1. Явно запретить mock SSO при `DEBUG=False`, если не включен отдельный `ALLOW_MOCK_SSO`.
2. Проверять email domain по `allowed_domains`.
3. В production заменить mock на OIDC/allauth provider.

### AUD-015: API-токены хранятся в открытом виде

Серьезность: high для production.  
Область: enterprise API / secrets.  
Где: `Dolg_APP/models.py:384`, `Dolg_APP/models.py:394`, `Dolg_APP/org_views.py:482`, `Dolg_APP/org_views.py:490`.

`OrganizationApiToken.token` хранится как raw token. Создание показывает токен один раз, но в базе он остается пригодным.

Дополнительная проблема: по поиску не найдено полноценного middleware/auth backend для `Authorization: Bearer dolg_*`. То есть feature выглядит как UI/roadmap, но не завершенный API-контур.

План исправления:

1. Хранить только hash токена и короткий prefix для отображения.
2. Добавить middleware/auth helper для Bearer-токенов.
3. Логировать usage и last_used_at.
4. В дипломе не заявлять публичное API как production-ready, если оно не будет доведено.

## Средние риски

### AUD-016: доступ к review HTML/PDF не совпадает с API-доступом

Серьезность: medium.  
Область: project workflow.  
Где: `Dolg_APP/views.py:1812`, `Dolg_APP/views.py:1827`.

`project_review_page` и `project_review_pdf` разрешают только владельца проекта или demo-проект. При этом API чтения проекта поддерживает team/public через `_project_for_read`.

Риск: командный пользователь может создать или увидеть review через API, но не открыть отчет или PDF.

План: использовать единую проверку `_project_for_read` по `review.project_id` или отдельный helper `review_for_read`.

### AUD-017: CSV export пишет событие через read-доступ

Серьезность: medium.  
Область: audit / project history.  
Где: `Dolg_APP/views.py:1618`.

`api_project_simulation_export_csv` разрешен через `_project_for_read`, но после отдачи CSV пишет `ProjectEvent`.

Риск: read-only пользователь меняет историю сеанса.

План: либо не писать событие для read-only, либо логировать его в отдельный personal audit, либо требовать write-доступ для событий проекта.

### AUD-018: `api_pcb_autoroute` без обязательной авторизации

Серьезность: medium.  
Область: availability / CAD.  
Где: `Dolg_APP/views.py:759`.

Endpoint не помечен `login_required`, хотя использует `_project_for_read`. Анонимный пользователь не попадет в приватные проекты, но может гонять вычисления на demo/public проектах.

План: добавить `login_required` или отдельную публичную квоту/кеш.

### AUD-019: глобальная модерация доступна любому `is_staff`

Серьезность: medium.  
Область: moderation / roles.  
Где: `moderation/permissions.py:61`, `moderation/permissions.py:64`.

`user_has_global_permission` возвращает `True` для любого `user.is_staff`. Это проще для админки, но конфликтует с идеей отдельных групп: `site_moderator`, `catalog_editor`, `knowledge_editor`, `support_agent`.

План:

1. Оставить `superuser` как полный bypass.
2. Для `is_staff` проверять конкретные Groups/permissions.
3. Добавить тест, что `support_agent` не может скрывать контент.

### AUD-020: загрузки изображений проверяются в основном по `content_type`

Серьезность: medium.  
Область: uploads / XSS / media.  
Где: `accounts/views.py:330`, `accounts/views.py:342`, `accounts/views.py:357`, `Dolg_APP/org_views.py:591`, `Dolg_APP/org_views.py:594`.

Аватары и Pro-логотипы ограничивают типы без SVG, но проверяют MIME со стороны клиента. В org logo SVG разрешен.

Риск: некорректные или вредоносные файлы в media; для SVG возможны XSS/active content проблемы, особенно если файл отдается с неправильным content type.

План:

1. Проверять изображение через Pillow.
2. Для SVG либо запретить, либо санитизировать и отдавать с безопасными заголовками.
3. Ограничить размеры изображения в пикселях.

### AUD-021: 2FA можно отключить без повторного подтверждения

Серьезность: medium.  
Область: account security.  
Где: `accounts/two_factor.py` нужно проверить точный flow перед исправлением.

Предварительно видно, что отключение 2FA завязано на текущую сессию. Middleware требует verified 2FA-сессию, если устройство уже включено, но для безопасности лучше требовать повторный пароль или OTP при отключении.

План: добавить re-auth step для disable 2FA.

### AUD-022: dependency drift между prod/base requirements

Серьезность: medium.  
Область: dependency management.  
Где: `requirements.txt:79`, `requirements-prod.txt:6`.

В base зафиксирован `sentry-sdk==2.45.0`, в prod `sentry-sdk==2.23.1`. Это может давать непредсказуемую версию в зависимости от порядка установки.

План:

1. Свести версии в один constraints-файл.
2. Для AI-зависимостей оставить отдельный extra/runtime, как уже начато в `requirements-ai.txt`.

### AUD-023: `Dolg_APP/templates/tools/simulation.html` слишком большой

Серьезность: medium.  
Область: maintainability / frontend regressions.  
Где: `Dolg_APP/templates/tools/simulation.html`.

Файл содержит 14 707 строк. Это главный источник риска для CAD/SIM: трудно тестировать, легко сломать UI и сложно проводить review.

План:

1. Выделить canvas engine, toolbar, AI panel, measurements, export/import в отдельные JS modules.
2. Ввести smoke-тесты на критические действия: добавить компонент, соединить, сохранить, review, AI context.
3. Обновить `docs/ARCHITECTURE.md`: там ранее встречалась устаревшая оценка размера файла.

## Низкие риски и deployment-hardening

### AUD-024: production defaults слишком мягкие

Серьезность: low/medium.  
Область: deployment.  
Где: `Dolg_PR/settings.py:49`, `Dolg_PR/settings.py:71`, `Dolg_PR/settings.py:397`.

Default `SECRET_KEY` при `DEBUG=False` дает warning, но не hard-fail. `SERVE_MEDIA=True` по умолчанию удобен для демо, но не production-профиль.

План: для production добавить `scripts/check_prod_settings.py` как обязательный preflight или сделать fail-fast в настройках для `DEBUG=False`.

### AUD-025: CSP opt-in и `unsafe-inline`

Серьезность: medium для production, low для demo.  
Область: security.  
Где: `Dolg_PR/settings.py:213`, `Dolg_PR/settings.py:218`, `Dolg_PR/settings.py:219`.

CSP включается только при `ENABLE_CSP`, а profile допускает `unsafe-inline`. Это объяснимо большим inline CAD/SIM UI, но требует hardening после декомпозиции фронта.

План: после выноса JS/CSS убрать `unsafe-inline`, добавить nonce/hash и расширить smoke-тесты.

### AUD-026: локализация настроек не совпадает с русским интерфейсом

Серьезность: low.  
Область: localization.  
Где: `Dolg_PR/settings.py:362`, `Dolg_PR/settings.py:364`.

`LANGUAGE_CODE='en-us'`, `TIME_ZONE='UTC'`, хотя UI и дипломный контекст русскоязычные.

План: перейти на `ru-ru` и актуальную зону либо документировать UTC как техническое хранение времени.

### AUD-027: локальные `.env` и `db.sqlite3` есть в рабочей папке

Серьезность: low при текущем `.gitignore`, high при упаковке архива.  
Область: repository hygiene.  
Где: root workspace, `.gitignore`.

`.env` и `db.sqlite3` находятся в корне и игнорируются git. Их нельзя включать в публичный архив, приложение к диплому или репозиторий.

План: перед передачей проекта делать clean export через release script.

## Доменные недочеты CAD/SIM/AI

### AUD-028: AI live-ветка теряет часть source-aware контекста

Серьезность: medium.  
Область: AI.  
Где: `Dolg_APP/views.py:2222`.

Self-hosted ветка возвращает `context_sources`, `quick_actions`, `session_summary`. Live Claude-ветка возвращает пустые `context_sources` и `quick_actions`, а `session_summary` не обновляет.

Риск: разные режимы AI ведут себя по-разному; пользователь видит “балабола”, который теряет контекст.

План:

1. Сделать общий post-processing результата для self/live.
2. Передавать legal sources/review evidence и в live mode.
3. Обновлять `session_summary` после каждого ответа.

### AUD-029: AI pipeline gates неполные

Серьезность: medium.  
Область: subscriptions / AI.  
Где: `Dolg_APP/views.py:477`, `Dolg_APP/views.py:496`, `Dolg_APP/views.py:512`.

`explain` и `recommend` закрыты feature-gate, но `detect_anomalies` доступен Free как `FREE_FEATURES`, а pipeline info открыт без auth. Это может быть нормальным продуктовым решением, но нужно явно закрепить в тарифной матрице и UI.

План: сверить реальные endpoints с `FEATURE_MATRIX` и написать тест-матрицу Free/Pro/Enterprise/staff.

### AUD-030: API tokens feature не завершен как внешний API

Серьезность: medium.  
Область: Enterprise.  
Где: `Dolg_APP/org_views.py:482`, `Dolg_APP/models.py:384`.

Есть UI создания токенов, но не найдено использование `Authorization: Bearer dolg_*` для API-доступа. Для защиты лучше формулировать как “подготовлен контур Enterprise API tokens”, если полноценный auth middleware не будет сделан.

План: либо завершить API-token auth, либо убрать сильные заявления из презентации/речи.

## Что исправлять первым

1. `AUD-009`: object-level access для комментариев проектов.
2. `AUD-010` и `AUD-011`: закрыть тяжелые endpoints и убрать traceback из JSON.
3. `AUD-012`, `AUD-016`, `AUD-017`: привести read/write-доступ к проектному сеансу в единую модель.
4. `AUD-013`: разрешить сохранение draft-схем с DRC-ошибками.
5. `AUD-014`: ограничить mock SSO и проверить `allowed_domains`.
6. `AUD-015`: hash API tokens или честно оставить feature как roadmap.
7. Производительность startup: сузить `Dolg_APP/checks.py` до template dirs или вынести в management command.

## Что можно использовать в дипломе

Факты, которые стоит оформить как архитектурные решения:

- DOLG устроен как web-ориентированная среда проектного сеанса: проект хранит схему, версии, симуляции, измерения, review, BOM, комментарии и события.
- Инженерная логика вынесена в service-layer: расчеты, review, graph analysis, formula/unit layers, expert AI.
- Для качества данных используются management-команды: demo-ready, data-integrity, media/source checks.
- AI должен быть описан как expert-first assistant: он опирается на review, схему, BOM, learning и источники, а не принимает финальные инженерные решения.

Ограничения, которые лучше честно указать:

- production-hardening не завершен: CSP, API tokens, mock SSO, media serving;
- CAD/SIM frontend пока крупный inline-модуль и требует декомпозиции;
- публичные supplier API, полноценный PCB CAD и neural deep analysis находятся в развитии;
- финальная инженерная ответственность остается за человеком.

## Что не обещать на защите без исправлений

- “Полностью безопасная production-система”.
- “Полноценное внешнее API по токенам”.
- “Готовый промышленный SSO”.
- “Полная замена KiCad/Altium”.
- “Автономная нейронка принимает инженерный verdict”.

## Следующий аудит

1. Пройти `shop/views.py` и catalog filter services: XSS, filter injection, N+1, unit parsing edge cases.
2. Пройти `knowledge` learning/check endpoints: grading, progress, anonymous writes, source references.
3. Пройти `orders`: guest tracking, payment state transitions, stock accounting.
4. Пройти media/image pipeline: official images, SVG fallback, broken image recovery.
5. Снять карту моделей для диплома: entity table, UML class diagram, sequence diagrams для catalog -> scheme -> review -> order.

## Первичный аудит Django admin от 2026-05-31

Проверены: `Dolg_APP/admin.py`, `shop/admin.py`, `knowledge/admin.py`, `orders/admin.py`, `accounts/admin.py`, `moderation/admin.py`, `Dolg_APP/ml_admin_views.py`.

### ADMIN-001: `makemigrations --check` падает из-за несинхронизированных validators

Серьезность: medium.  
Где: `shop.models.Product.price`, `orders.models.Order.total_amount`, `orders.models.OrderItem.price`.

Модели получили validators для денежных полей, но миграции не зафиксированы. Это не меняет SQL-тип поля, но ломает regression gate `makemigrations --check --dry-run`.

План: отдельной правкой создать миграции `shop/0004...` и `orders/0004...`, либо осознанно откатить validators из моделей.

### ADMIN-002: Product slug для кириллицы может быть пустым

Серьезность: medium.  
Где: `shop/models.py`, `Product.save`, `shop/admin.py`.

`Product.save()` использует `slugify(self.name)` без `allow_unicode=True` и без fallback-логики, которая уже есть у `Category`. Для товара с русским названием slug может стать пустым, а второй такой товар даст конфликт уникальности.

План: добавить Unicode/fallback slug generation и тест на русское название товара через admin/model save.

### ADMIN-003: админка проектов не показывает часть новых полей сеанса

Серьезность: medium.  
Где: `Dolg_APP/admin.py`, `SchematicProjectAdmin`.

В `fieldsets` нет `organization`, `visibility`, `approval_state`, `share_token`, `deleted_at`. Эти поля уже важны для проектного сеанса, Enterprise и public/team доступа, но через админку их почти нельзя нормально диагностировать.

План: расширить `list_display`, `list_filter`, `readonly_fields` и `fieldsets`; добавить фильтр по soft-deleted через `all_objects` только при необходимости.

### ADMIN-004: заказ и позиции заказа неудобно создавать/редактировать из admin

Серьезность: low/medium.  
Где: `orders/admin.py`, `OrderItemInline`, `OrderItemAdmin`.

`OrderItemInline` и `OrderItemAdmin` делают `product` и `price` readonly. Это защищает коммерческие данные, но фактически мешает вручную собрать тестовый заказ в админке.

План: оставить readonly после создания, но разрешить выбор товара/цены при add-flow или сделать отдельное staff-действие “пересчитать заказ”.

### ADMIN-005: ML staff panel пишет traceback в cache

Серьезность: medium.  
Где: `Dolg_APP/ml_admin_views.py`.

Ошибки фонового обучения/импорта сохраняют полный traceback в cache и могут показываться staff UI. Это не публичный endpoint, но для production лучше ограничить подробности или показывать их только superuser.

План: оставить короткую ошибку для staff, полный traceback отправлять в log/Sentry.
