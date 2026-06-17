ДОЛГ — ДИПЛОМНАЯ ВЕБ-ПЛАТФОРМА
Веб-приложение, объединяющее интернет-магазин электронных компонентов,
редактор принципиальных схем и SPICE-симулятор, работающие в одном
рабочем пространстве. Проект соответствует требованиям ВКР «Разработка
веб-приложения для продажи радио- и электронных компонентов со встроенными
инструментами проектирования и симуляции схем».

Стек
  Уровень · Технология · Примечание
  Backend · Python 3.14 + Django 6.0 · MVT, ORM, встроенная админка
  Frontend · HTML5 + CSS3 + vanilla JS (ES6+) · Серверный рендеринг Django-шаблонов + клиентские приложения для редактора и симулятора
  БД (dev) · SQLite · Для продакшна предусмотрен PostgreSQL (изменить "DATABASES" в "Dolg_PR/settings.py")
  Графика · HTML5 Canvas 2D · Редактор схем, CAD, графики симуляции
  Симулятор · "ngspice.wasm" (Emscripten 2.0.7, ngspice 33) + JS-MNA fallback · Реальный SPICE в браузере, Web Worker для неблокирующего UI
  Численная аналитика · NumPy + SciPy + Matplotlib + Pandas · FFT-спектр, Bode plot, Monte Carlo tolerance, THD/SINAD/ENOB, parameter sweep, server-side DC fallback, статистика запусков
  Инженерные расчеты · "python-engineering" + собственный service-layer · Валидация числовых входов; электронные формулы остаются в "knowledge/services/engineering_lab.py"
  Графы, формулы и SVG схем · NetworkX + SymPy + Schemdraw · Топология схем для review/AI/learning, символьные формулы и технические SVG-иллюстрации учебных узлов
  Expert-first review · jsonschema + rule-engine + Pint + Lark + Z3 + scikit-fuzzy · Версионированные rule packs, unit-safe номиналы, импорт SPICE/LTspice subset, подбор номиналов по ограничениям и мягкая оценка риска
  Legal knowledge corpus · Открытые учебники + официальная документация · Источники для энциклопедии, learning, review evidence и AI-контекста без пиратских архивов
  Media Quality Gate · Pillow + ImageHash · Проверка товарных изображений: битость, размер, пустые/однотонные файлы, policy-нарушения и perceptual hash для дублей локальных product-shot
  PDF · "reportlab" · Гарантийные талоны и сертификаты на товары
  Публичный доступ · Cloudflare Tunnel ("cloudflared.exe") · Один бинарник, без регистрации

Структура проекта
    DOLG_Diploma/
    ├── Dolg_PR/              # Конфигурация проекта (settings, urls)
    ├── Dolg_APP/             # Редактор схем, CAD, проекты, симуляция
    │   ├── templates/tools/  # simulation.html, cad.html, projects.html
    │   ├── tests.py          # core Django-тесты: проекты, review/import, Pro-аналитика, fallback, PDF
    │   ├── tests_browser.py  # optional Playwright smoke: simulation/BOM, DC/AC/TRAN, modals, exports, CAD, projects
    │   ├── services/         # project_review.py, schematic_graph.py, cad_import.py, rule_ai.py, simulation_analysis.py
    │   └── simulation_quota.py
    ├── shop/                 # Каталог, корзина, BOM, PDF-документы, страница «О проекте»
    │   ├── static/simulation/   # ngspice.js + ngspice.wasm + ngspice-worker.js
    │   │                        # (+ JS-MNA fallback, scheme-normalizer.js, scheme-export.js, scheme-bom.js, scheme-netlist.js)
    │   ├── templates/shop/about.html
    │   └── management/commands/ # populate_reb_products, attach_*images, enrich*
    ├── accounts/             # Пользователи, профили, адреса (+ сигнал auto-UserProfile)
    ├── orders/               # Заказы, доставка, платежи
    ├── knowledge/            # Энциклопедия (6 категорий, 21 статья, вложенные материалы)
    ├── media/products/       # Товарные изображения: локальные assets + generated-заглушки без Wikimedia/Commons
    ├── requirements.txt
    ├── start_local.bat       # Локальный запуск на 127.0.0.1:8000 (для своей работы)
    ├── start_public.bat      # Локальный + Cloudflare Tunnel (демо/защита/телефон)
    ├── start_server.py       # Питон-launcher для start_public.bat
    └── cloudflared.exe       # Портативный Cloudflare Tunnel (63 МБ)


Установка и запуск
1. Подготовка окружения
    # Клонировать / распаковать проект, перейти в папку
    cd DOLG_Diploma

    # Создать виртуальное окружение (один раз)
    python -m venv .venv

    # Активировать
    # Windows:
    .\.venv\Scripts\activate
    # Linux/macOS:
    source .venv/bin/activate

    # Установить зависимости
    pip install -r requirements.txt


2. Миграции и наполнение БД
    python manage.py migrate
    python manage.py populate_reb_products        # 43 РЭБ-компонента
    python manage.py normalize_reb_catalog        # нормализовать REB v2: part_number, mounting, ratings, datasheet_url
    python manage.py enrich_datasheets --all --missing-only # заполнить Product.parameters.datasheet_extracted
    python manage.py apply_verified_product_photos # вернуть проверенные реальные фото в products/verified/
    python manage.py apply_curated_product_photos  # fallback-policy: локальный raster/verified asset или generated UGO PNG
    python manage.py enrich_product_parameters     # заполнить parameters JSON
    python manage.py populate_knowledge            # энциклопедия + фото/видео/файлы материалов
    python manage.py seed_legal_sources            # легальные источники: open textbooks + официальная документация
    python manage.py populate_demo_projects        # 12 демо-схем (basic → advanced)
    python manage.py seed_announcements             # 4 объявления для информационного канала чата
    python manage.py setup_roles                    # группы "Менеджер" и "Пользователь"
    python manage.py check_demo_ready               # smoke-проверка перед показом
    python manage.py check_data_integrity           # аудит каталога, статей, media и demo-схем


3. Суперпользователь
Создайте локального администратора перед демонстрацией или проверкой проекта:

    python manage.py createsuperuser


Не храните реальные пароли в README или публичных архивах проекта. Для настроек
окружения используйте ".env.example" как шаблон.

4. Запуск
В корне репо ровно ДВА launcher-скрипта — больше не нужно:

Локально (для своей работы):
    # Двойной клик на start_local.bat
    # или вручную:
    python manage.py runserver 127.0.0.1:8000

Открыть: http://127.0.0.1:8000/

С публичной ссылкой (для защиты / телефона / ревью):
    # Двойной клик на start_public.bat — запустит Django + Cloudflare Tunnel.
    # Скрипт ждёт URL, делает propagation-probe и автоматически открывает браузер.
    # Публичный URL вида https://random-words-abcd.trycloudflare.com — в окне launcher-а.


Ключевые страницы
  URL · Что · Требует логина
  "/" · Каталог товаров (потребительская электроника + РЭБ-компоненты) · —
  "/about/" · Страница «О проекте» с описанием модулей и сценариев · —
  "/demo/" · Сквозной демонстрационный маршрут: каталог → энциклопедия → CAD → симуляция → BOM → заказ · —
  "/search/?q=..." · Глобальный поиск по товарам, категориям, статьям, демо-схемам и инструментам · —
  "/readyz/" · JSON readiness-проверка БД, каталога, энциклопедии и демо-проектов · —
  "/category/<slug>/" · Страница категории с фильтрами · —
  "/product/<slug>/" · Карточка товара с параметрами, datasheet, гарантией · —
  "/compare/" · Сравнение до 4 товаров с авто-аналитикой «лучше/хуже» · —
  "/cart/" · Корзина · —
  "/checkout/" · Оформление заказа · ✓
  "/orders/" · История заказов · ✓
  "/accounts/profile/" · Профиль, адреса, аватар · ✓
  "/knowledge/" · Энциклопедия — физика, компоненты, PCB, история · —
  "/knowledge/lab/" · Инженерная лаборатория: расчеты и оценки узлов · —
  "/knowledge/learning/" · Практикум обучения с автопроверкой задач · —
  "/simulation/" · Редактор принципиальных схем + симулятор (ngspice.wasm), гостевой demo-режим · —
  "/cad/" · 2D-САПР с шаблонами ГОСТ и готовыми компонентами · ✓
  "/projects/" · Список проектов (включая 12 демо-схем) · ✓
  "/chat/" · Публичный технический чат (Q&A) + сайдбар объявлений · Чтение — нет, писать — ✓
  "/orgs/" · Список организаций (Enterprise) · ✓
  "/orgs/<slug>/conversations/" · Приватные беседы команды · Member org
  "/admin/" · Админ-панель Django · Staff

Основные возможности
Каталог
• Иерархические категории, фильтры (производитель, lifecycle, package)
• Умный поиск через "shop/smart_search.py" (rapidfuzz):
  • Multi-token parsing: «резистор vishay 1k» → 3 токена, AND-логика, каждый
    ищется в name / part_number / description
  • Quoted фразы: ""op-amp ic"" — один токен
  • Fuzzy fallback на typo: если строгий поиск ничего не нашёл, через
    "rapidfuzz.process.extract" (WRatio) подбираем близкие part_number / name
    с similarity ≥ 70 → решает «резстор» (опечатка) → «резистор»
  • Facets с counts: sidebar показывает «Vishay (8) · Yageo (4)» вместо
    плоского списка фильтров (через "compute_facets")
  • DB-agnostic — работает и на SQLite, и на Postgres. Можно дополнить
    Postgres FTS ("SearchVector" + русская морфология) при миграции на Postgres
    — см. docs/SMART_SEARCH.md (memory "smart-search-todo")

Как добавить реальные фото товаров
Каталог поддерживает три источника изображений (в порядке приоритета):
1. Локальный asset — "media/products/<slug>.{png,jpg,jpeg,webp}".
   Это «настоящее» фото, привязанное к товару. SVG исключён из автодетекта —
   только при ручной загрузке через админку как "Product.image".
2. Generated PNG-арт — процедурный плейсхолдер 900×620 с категория-специфичной
   геометрией (резисторы со цветовыми кольцами, ICs с пинами, разъёмы и т.д.).
   Генерируется через Pillow в "shop/services/product_images.py" и кладётся в
   "media/products/generated/<slug>.png". Внутри нет названий товара; для
   антидублей добавлен небольшой технический fingerprint из vias/штрихов.
3. Заглушка категории в template (SVG-div) — fallback если "Product.image"
   пустое или попало под "STOCK_IMAGE_PATHS"/"is_stock_image".

Чтобы быстро заменить generated-арт на настоящие фото:

    # 1. Скопируйте файлы в папку
    #    media/products/incoming/<slug>.<ext>
    #    Имя файла = product.slug. Расширение — png/jpg/jpeg/webp.

    # 2. Запустите команду
    python manage.py import_product_photos --dry-run   # план
    python manage.py import_product_photos              # применить

    # 3. Опции
    python manage.py import_product_photos --slug r-1k                 # только один slug
    python manage.py import_product_photos --slug r-1k,c-100u           # несколько через запятую
    python manage.py import_product_photos --keep-source                 # не удалять файлы из incoming


Команда копирует файл в "media/products/<slug>.<ext>" и вызывает
"apply_product_image_policy(product)" — "product.image" переключается
на новый локальный asset, "parameters.image_source" обновляется до
"local product asset".
• Карточка товара: параметры, datasheet, гарантийный талон (PDF на лету)
• Datasheet Intelligence V1: команда "enrich_datasheets --all --missing-only" заполняет "Product.parameters.datasheet_extracted", а карточка товара показывает компактный DI-блок с package, предельными режимами, рабочими условиями, тепловыми данными и подсказками применения. "check_data_integrity --json" контролирует, что у РЭБ-позиций этот слой заполнен.
• Изображения товаров: сначала используется точный локальный raster "products/<slug>.", затем проверенное реальное фото "products/verified/<slug>.", затем generated UGO-style PNG через "shop.services.product_images" на Pillow. SVG больше не выбирается автоматически как активная картинка товара.
• Реальные фото из старого кеша не включаются напрямую из "commons/curated": команда "apply_verified_product_photos" копирует только отобранные файлы в "products/verified/", а denylist оставляет сомнительные кадры на generated fallback.
• Точечные официальные/поставщицкие product-shot для проблемных карточек берутся только из allowlist-команды "import_official_product_photos"; она валидирует файл через Media Quality Gate и не возвращает Wikimedia/Commons в активный каталог.
• Wikimedia/Commons полностью отключены для активного каталога: legacy-команда "import_commons_product_photos" теперь падает с ошибкой, "check_demo_ready" и "check_data_integrity" считают Commons/curated-источники нарушением media-policy.

Редактор схем ("/simulation/")
• Компоненты по ГОСТ 2.728-74 / 2.702-2011: R, C, L, диод, LED, источник, переключатель, NPN/PNP-транзистор, GND, узлы (≤ 4 проводов)
• Ортогональные провода с авто-маршрутизацией, T-tap (узел появляется автоматически), hop-rendering для непересекающихся проводов
• Anti-collision подписи (R1, R2, C1, V1) — группировка по типу, автовыбор позиции (низ/верх/право/лево)
• Перемещение: "←↑↓→" — 1 px (точно), Shift — 10 px, Ctrl — отдельный шаг хода; шаг хода настраивается независимо от визуальной сетки, "R" — поворот, "Delete" — удалить, Shift при перетаскивании — без snap
• Ctrl+Z / Ctrl+Y — Undo/Redo (50 шагов)
• Панель свойств для всех типов: значение/единицы (с инженерными суффиксами "1k", "4.7k", "10u", "100n"), состояние переключателя, модель транзистора, кнопки 🔄 Поворот / 📋 Копия / 🗑 Удалить
• Экспорт: SPICE-netlist (".cir"), PNG, SVG и PDF-представление схемы
• BOM из схемы → группирование → bulk-добавление в корзину; выбранный в свойствах товара "catalog_ref" учитывается первым
• Экспорт BOM: клиентский CSV и серверный XLSX-файл с итогами, артикулами, категориями, корпусами и datasheet-ссылками
• Поиск товара каталога прямо в свойствах выбранного компонента: сохраняются SKU, карточка товара, datasheet, корпус, производитель и параметры
• Сохранение/загрузка проектов в личном кабинете, история версий схем и серверная DRC-проверка

Симулятор
• Реальный SPICE — "ngspice.wasm" (Emscripten 2.0.7, ngspice 33), работает в Web Worker
• Анализы: DC / OP, переходный процесс (TRAN), АЧХ/ФЧХ (AC) с декадной разверткой
• Графики на canvas: время / log-частота, отдельные оси для V и I, синхронные курсоры
• Аналитика по сигналам: min / max / peak-to-peak / avg / RMS, оценка частоты по нулевым переходам
• Аналитика АЧХ: Gmax, fmax, фаза в максимуме, −3 дБ полоса (с лог-интерполяцией) для ФНЧ / ФВЧ / полосовых
• Pro-аналитика на сервере: FFT через "scipy.fft.rfft", Bode plot через Matplotlib SVG, Monte Carlo tolerance через NumPy, signal quality THD/SINAD/ENOB и what-if parameter sweep.
• В панели результатов симуляции есть быстрые действия Pro: "FFT spectrum", "Signal quality", "Bode plot", "Monte Carlo", "What-if sweep", "Server DC fallback", "Slow runs".
• Результаты Pro-аналитики можно сохранить как "ProjectMeasurement": частота пика, THD, -3 дБ cutoff, среднее Monte Carlo, среднее sweep или напряжение узла server fallback.
• Server-side fallback-solver: простые DC-цепи R/V/GND решаются на сервере NumPy MNA, если браузерный ngspice/JS fallback не справился.
• Pandas-статистика запусков: endpoint проекта возвращает самые медленные симуляции и агрегаты по типам анализа.
• Измерительные курсоры T1/T2 на TRAN (Shift+Click) → ΔT, 1/ΔT, ΔV / ΔI; синхронный курсор по f на AC mag/phase
• DRC: висящие выводы, отсутствие GND, короткое замыкание, плавающие секции
• Квоты: "admin" — безлимитно, юзер — 100 запусков/сутки, гость — 10
• Сохранение результатов запусков симуляции для авторизованных проектов
• JS-MNA fallback на случай отказа WASM — DC честно через Гаусс-элиминацию "Ax = b"

CAD ("/cad/")
• Шаблоны ГОСТ 2.104 Форма 1 (А4 / А3 / А2 рамка + штамп)
• Библиотека компонентов: DIP-8/14/16, PCB 100×80, DB-9, делитель напряжения
• Штриховки (45°, 135°, ×, точки, горизонталь, вертикаль) с настраиваемым шагом
• Настраиваемая сетка, слои, undo/redo, импорт/экспорт в localStorage
• Server-side import preview для LTspice/SPICE/KiCad-subset: компоненты, узлы, GND, неподдержанные элементы, analysis directives и предупреждения показываются до сохранения.
• Из import preview можно создать "SchematicProject", сразу запустить "ProjectReview" и перейти к отчету с Learning-by-review подсказками.

Энциклопедия ("/knowledge/")
• 6 категорий: Физика · Компоненты · Корпуса · PCB · История · Практика
• 21 статья с дополнительными материалами: фото, gif/video, datasheet, чек-листы, внешние и внутренние ссылки
• Полнотекстовое содержимое, связь с разделами каталога и переходами в CAD/SIM

Инженерная лаборатория и обучение ("/knowledge/lab/", "/knowledge/learning/")
• Расчеты прикладных узлов: транзисторный ключ, NE555, линейный стабилизатор, RC-антидребезг, тепловой запас.
• Оценка результата не только числом: статусы "норма", "риск", "перегрев", "нужен запас" и инженерный комментарий.
• "python-engineering" подключен как слой валидации числовых входов; предметные электронные формулы остаются в собственном Python service-layer.
• Расширенные измерительные метрики для задач: ток ветви, RMS, частота, duty cycle, мощность элемента, температура, -3 дБ точка.
• Практикум использует общий service-layer лаборатории: опубликовано 4 маршрута, 13 уроков и 29 заданий.
• Старый "/learn/" оставлен как совместимый redirect на "/knowledge/learning/".

Контроль данных
• "check_data_integrity" проверяет товары, media, дубли изображений, запрет Wikimedia/Commons, параметры РЭБ, материалы статей, внутренние ссылки и валидность demo-схем.
• "apply_curated_product_photos" генерирует контролируемые PNG-изображения товаров и записывает в "parameters.image_source_policy = no-wikimedia".
• "shop.services.media_quality" добавляет Media Quality Gate на Pillow/ImageHash: "check_data_integrity" и "check_demo_ready" видят качество изображения, размер, пустоту, perceptual hash и итоговый score.
• "populate_demo_projects" пересобирает demo-схемы с позиционными обозначениями ("R1", "C1", "V1") и ортогональными проводами.

Демо-проекты
Команда "populate_demo_projects" создаёт 12 схем разной сложности (видны всем).
Seed пересобирает схемы в едином стиле: позиционные обозначения "R1/C1/V1",
ортогональные провода, корректные "ports" и параметры платы для 3D/PCB:
• 🔴 LED-индикатор 5 В (basic)
• ⚡ Делитель напряжения 9→2.88 В (basic)
• 📉 RC-фильтр низких частот (medium)
• 🌊 Мостовой выпрямитель (medium)
• 🎵 LC-резонансный контур (advanced)
• ⚖️ Мост Уитстона (medium)
• 📊 Двухкаскадный RC-фильтр (medium)
• 🔀 Параллельные нагрузки — делитель тока (advanced)
• 🌡 Тепловая шкала: 5 резисторов 12 В (medium)
• 🪜 R-2R DAC (4-бит, учебная версия) (medium) — переработанная версия 12-битного DAC, чистый layout
• 📉 RC-LPF 3-го порядка (3 каскада) (medium) — переработанная версия 8-секционного LPF
• 🎚 Однокаскадный усилитель CE (NPN) (advanced) — переработанная версия двухкаскадного класса А

Три громоздкие «showcase»-функции ("demo_big_ladder" 12-bit DAC,
"demo_long_rc_chain" 8-секционный LPF, "demo_class_a_amplifier" двухкаскадный BJT)
оставлены в коде populate_demo_projects.py (Dolg_APP/management/commands/populate_demo_projects.py)
как reference, но не включены в активный "DEMO_PROJECTS" — на стандартной канве
auto-route налезал на компоненты. Их можно вернуть после редизайна.

Чат и обсуждения ("/chat/")
• Публичные технические топики Q&A-стиля: категория + tags + threading + accepted answer + реакции
• Free: 5 топиков и 20 ответов в день, plain-text, 👍 only
• Pro: безлимит, Markdown + code highlight, любые emoji, pin своих топиков, attach "SchematicProject"
• Guest: read-only (SEO + образовательный материал доступен без регистрации)
• Правый сайдбар «📢 Информационный канал» — модерируемые объявления админа
  (модель "Announcement", уровни info/warning/critical, поддержка expiry).
• Realtime через Django Channels (WebSocket): "/ws/chat/topic/<id>/" пушит
  новые reply подписанным клиентам. AJAX-polling каждые 8-9с остался как fallback
  если WS не подключился. Клиент сам переключается между WS↔polling, без участия пользователя.
• Команда "python manage.py seed_announcements" создаёт стартовый набор объявлений.

Enterprise: организации, RBAC, аудит, приватные беседы ("/orgs/")
• 4 модели: "Organization", "OrganizationMember", "OrganizationInvite",
  "OrganizationApiToken" + центральный "AuditLog".
• RBAC: 5 ролей "owner > admin > engineer > reviewer > viewer" через
  "Dolg_APP/org_permissions.py" (декоратор "@require_org_permission(action)").
• Multi-tenant projects: "SchematicProject" получает "organization" FK + "visibility"
  (private/team/public) + "approval_state" (draft/pending_review/approved/rejected).
• Approval workflow (SOX-style): engineer submit → reviewer approve/reject, всё
  в "AuditLog" (append-only через thread-local request middleware).
• Централизованный биллинг: "Subscription.organization" даёт Pro всем members.
• Mock-SSO для Azure/Okta/Google с anti-CSRF nonce ("/sso/<slug>/redirect/").
• API tokens: scoped Bearer-аутентификация (модели готовы, REST endpoint — TODO).
• Custom branding (логотип / accent-color) на странице org-настроек.
• Security policies: require_2fa, disable_ai, disable_public_share, allowed_domains.
• Приватные беседы команды ("/orgs/<slug>/conversations/"): создание admin/owner,
  отправка engineer+, Markdown, @mentions, archive, realtime WebSocket
  ("/ws/orgs/<slug>/conversations/<id>/") + AJAX-polling как fallback, audit-логи.

AI Phase 2 — семантический поиск (TF-IDF + cosine)
Если в окружении установлен "scikit-learn", endpoint "/api/ai/pipeline/analogs/"
использует TF-IDF embeddings вместо rule-based feature-векторов:

    # Установка опциональная (без неё работает rule-based fallback)
    pip install scikit-learn

    # Построение индекса (один раз после populate_reb_products / обновления каталога)
    python manage.py rebuild_search_index            # все товары
    python manage.py rebuild_search_index --reb      # только РЭБ-категории


Технические детали:
• TF-IDF через "sklearn.feature_extraction.text.TfidfVectorizer":
  ngram_range=(1,2), max_features=5000, sublinear_tf=True
• Cosine similarity через "sklearn.metrics.pairwise.cosine_similarity"
• Index хранится в "media/search/{tfidf_vectorizer.pkl, tfidf_matrix.npz, products.json}"
• Russian lemmatization через pymorphy3 (опционально): «резисторы» = «резистор»,
  «диодами» = «диод», «операционных усилителей» = «операционный усилитель».
  Даёт +20-50% relevance score для русских запросов в нужном падеже/числе.
  Если pymorphy3 не установлен — fallback на raw-tokens
• Auto-stale marker: signal "post_save/post_delete" Product ставит
  "media/search/.stale". После изменений админ запускает
  "python manage.py rebuild_search_index" — сообщение «индекс был помечен stale»
  виден в выводе команды
• Hybrid режим ("hybrid_search"): объединяет TF-IDF top-K с rapidfuzz
  rule-based через RRF (Reciprocal Rank Fusion, k=60)
• Graceful fallback: если sklearn не установлен, view автоматически
  переключается на rule-based (Dolg_APP/ml/pipeline.py (Dolg_APP/ml/pipeline.py))

Почему не fastembed/sentence-transformers: на Windows + Python 3.14
транзитивные зависимости ("py-rust-stemmers" → Rust toolchain;
"torch" → 2 ГБ) не имеют prebuilt wheels. TF-IDF на sklearn — pragmatic
choice для дипломного каталога 100-1000 товаров: pure-Python + numpy/scipy,
мгновенная установка. При переходе на production-каталог 10k+ можно
поменять "_build_index" на embeddings без изменения API ("semantic_top_k",
"hybrid_search", "is_semantic_available").

Безопасность аккаунта: 2FA и SSO
2FA через django-otp (TOTP + backup-коды)
• Установлены "django-otp==1.7.0" + "qrcode==8.2"
• Enrollment: "/2fa/setup/" → QR-код → ввод первого 6-значного кода
• TOTP-устройство: Google Authenticator / Authy / 1Password / Microsoft Authenticator
• При confirm генерируются 10 одноразовых backup-кодов (показываются ОДИН раз)
• Login challenge: "/2fa/verify/" — после пароля Require2FAMiddleware
  редиректит сюда юзеров с включённым 2FA до ввода TOTP/backup-кода
• Backup-коды: "/2fa/backup/" (счётчик + regenerate)
• Отключение: "/2fa/disable/" (POST из профиля)
• Enforcement: при "Organization.settings.require_2fa=True" member'ы вынуждены
  включить 2FA (см. middleware)

SSO через django-allauth (Google / Microsoft / GitHub)
• Установлен "django-allauth==65.16.1" + OAuth providers
• На странице "/accounts/login/" появились SSO-кнопки (🟦 Google · 🪟 Microsoft · 🐙 GitHub)
• Mock-SSO ("/sso/<slug>/redirect/") оставлен для demo Enterprise tier — он не
  требует реальных OAuth-приложений
• Для production требуется создать OAuth-app в каждом провайдере и зарегистрировать
  через "/admin/socialaccount/socialapp/":

    # 1. Google: https://console.cloud.google.com → APIs & Services → Credentials → Create OAuth client ID (Web app)
    #    Authorized redirect URI: https://<your-domain>/accounts/google/login/callback/
    # 2. Microsoft: https://portal.azure.com → Azure AD → App registrations
    #    Redirect: https://<your-domain>/accounts/microsoft/login/callback/
    # 3. GitHub: https://github.com/settings/developers → New OAuth App
    #    Callback: https://<your-domain>/accounts/github/login/callback/

    # 4. В Django admin → Sites → site domain = your-domain
    # 5. /admin/socialaccount/socialapp/ → Add → выбрать provider, client_id, secret


После этого SSO-кнопки на login-странице автоматически работают.

Биллинг через Stripe
Pro-подписка опционально может работать через настоящий Stripe (Subscription
mode + Checkout hosted page). По умолчанию проект в demo-mode — все
платежи мокаются, реальный Stripe не дёргается.

Demo-mode (по умолчанию)
• "STRIPE_SECRET_KEY=demo_mode" в ".env" (или просто не задан)
• Нажатие «Купить Pro» сразу активирует подписку через "Dolg_APP.billing.activate_pro"
• Никаких внешних HTTP-запросов

Live-mode (Stripe настоящий)
1. Зарегистрировать аккаунт на stripe.com (https://stripe.com), включить test-mode
2. Создать Product «DOLG Pro» + Price (recurring monthly) → скопировать "price_xxx"
3. Прописать env-vars:
    STRIPE_PUBLIC_KEY=pk_test_xxxxxxxx
    STRIPE_SECRET_KEY=sk_test_xxxxxxxx
    STRIPE_PRO_PRICE_ID=price_xxxxxxxx
    STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxx     # из Webhooks endpoint в dashboard

4. В Stripe Dashboard → Developers → Webhooks → Add endpoint:
   • URL: "https://<your-domain>/billing/stripe-webhook/"
   • Events: "checkout.session.completed", "customer.subscription.updated",
     "customer.subscription.deleted", "invoice.payment_failed"

Локальное тестирование webhook'ов через Stripe CLI
    # 1. Установить Stripe CLI
    # 2. Перенаправить webhooks в локальный Django
    stripe listen --forward-to localhost:8000/billing/stripe-webhook/
    # 3. CLI выдаст webhook secret — прописать в STRIPE_WEBHOOK_SECRET
    # 4. Тригернуть событие для проверки:
    stripe trigger checkout.session.completed


Поток:
1. User жмёт «Купить Pro» → "POST /billing/activate/"
2. "views.billing_activate_pro" детектит "is_stripe_live()" → создаёт Checkout Session → redirect на "session.url" (страница Stripe)
3. После оплаты Stripe возвращает на "/billing/success/?session_id=..." + параллельно шлёт webhook "checkout.session.completed"
4. Webhook-хендлер "Dolg_APP/stripe_billing.handle_checkout_completed" ставит "Subscription.tier='pro'", заполняет "stripe_customer_id"/"stripe_subscription_id", синхронизирует "period_end" из Stripe
5. Cancel → "POST /billing/cancel/" → если есть "stripe_subscription_id" → "stripe.Subscription.modify(..., cancel_at_period_end=True)"

Параллельный модуль для одноразовых платежей за товары — "orders.payment_views.stripe_webhook"
(PaymentIntent flow). Это отдельный bus от Pro-подписок.

Realtime через Django Channels
WebSocket-инфра ("channels==4.3.2" + "daphne==4.2.1") для двух комнат:

  URL · Кто слушает · Кто пушит · Защита
  "/ws/chat/topic/<id>/" · Все (включая guest) · Любой POST "/chat/<id>/reply/" · Topic exists check
  "/ws/orgs/<slug>/conversations/<id>/" · Members org с "org.chat.read" · Любой POST "/orgs/<slug>/conversations/<id>/message/" · "user_can" через AuthMiddlewareStack

Архитектура:
• Channel layer: "channels.layers.InMemoryChannelLayer" (dev/диплом). Для production —
  "channels-redis" (один insert в settings).
• Origin-check: "AllowedHostsOriginValidator" отбрасывает WS-подключения с чужих доменов.
• Consumers: "Dolg_APP/consumers.py" — "ChatTopicConsumer", "OrgConversationConsumer"
  (оба async). Получают event через "group_send" и пушат клиенту JSON.
• Broadcast из view'ев: "_broadcast_chat_reply", "_broadcast_org_message" в
  "chat_views.py". Best-effort: если WS-слой недоступен, HTTP-ответ всё равно
  успешен — JS-клиент сам докатит через polling.
• Клиент: WS primary, polling fallback. Автореконнект с exponential backoff
  (1→2→4→...→30 с). Keep-alive ping каждые 25 сек.

Запуск под Daphne (dev уже работает через "runserver" благодаря ASGI auto-detect):
    daphne -b 0.0.0.0 -p 8000 Dolg_PR.asgi:application   # production
    python manage.py runserver 0.0.0.0:8000               # dev (auto-ASGI)


Тесты, coverage и lint
Текущее состояние: `pytest --collect-only` на 2026-06-17 видит 626 тестов. Последний полный coverage snapshot ниже исторический и требует отдельного обновления.

Быстрый прогон (pytest + django)
    $env:FAST_TESTS = '1'   # пропускает миграции (×3-5 быстрее)
    .\.venv\Scripts\python.exe -m pytest
    .\.venv\Scripts\python.exe -m pytest Dolg_APP\tests_server_engines.py -q
    .\.venv\Scripts\python.exe -m pytest --collect-only -q
    .\.venv\Scripts\python.exe -m pytest --cov  # html-отчёт в htmlcov/


Coverage по приложениям (snapshot 2026-05-19)
  Модуль · Stmts · Cover · Заметки
  "Dolg_APP/models.py" · 421 · 91% · core models — почти полное покрытие
  "Dolg_APP/quotas.py" · 117 · 92% · tier-detection + лимиты
  "Dolg_APP/comments_render.py" · 25 · 96% · bleach + Markdown
  "Dolg_APP/sso_views.py" · 44 · 91% · Mock SSO + nonce
  "Dolg_APP/admin.py" · 82 · 94% · все ModelAdmin'ы
  "Dolg_APP/chat_views.py" · 263 · 69% · новый код, часть endpoints без unit-тестов
  "Dolg_APP/services/simulation_analysis.py" · 518 · 71% · Pro-аналитика (FFT/Bode/Monte Carlo)
  "Dolg_APP/services/schematic_graph.py" · 110 · 89% · DRC++ топология
  "Dolg_APP/org_permissions.py" · 49 · 78% · RBAC framework
  "Dolg_APP/org_views.py" · 283 · 53% · admin-pages — менее критично
  "Dolg_APP/views.py" · 865 · 58% · большой файл, core CRUD покрыт
  "Dolg_APP/ai_assistant.py" · 113 · 54% · Claude API (mock-fallback)
  "Dolg_APP/ml/embeddings.py" · 90 · 8% · stub для Phase 2 (FAISS), не активен
  "shop/models.py" · 77 · 91% · Product, Category, Cart
  "shop/views.py" · 728 · 63% · каталог + BOM + сравнение
  "accounts/models.py" · 40 · 90% · UserProfile
  "knowledge/models.py" · 211 · 80% · Article, Material
  "knowledge/views.py" · 129 · 88% · encyclopedia/lab/learning
  TOTAL · 9969 · 71% · 2876 missed

Тесты по tier'ам
  Файл · Что покрывает · Кол-во
  "Dolg_APP/tests_guest.py" · Guest-сценарий: anonymous доступ, демо-режим · —
  "Dolg_APP/tests_registered.py" · Free-tier: проекты, корзина, квоты · —
  "Dolg_APP/tests_premium.py" · Pro-tier: Markdown comments, advanced analytics · —
  "Dolg_APP/tests_enterprise.py" · Enterprise: RBAC, audit, workflow, SSO · 28 ✅
  "Dolg_APP/tests_chat.py" · Чат/беседы/announcements/quotas · 22 ✅
  "Dolg_APP/tests.py" · Schematic CRUD, BOM, simulation, PDF · —
  "shop/tests.py" · Каталог, фильтры, корзина, BOM-match · 58 ✅

Линтер ruff
    ruff check .              # 0 errors ✅
    ruff check . --fix        # автофикс
    ruff format .             # форматтер (replace black)


Конфиг в pyproject.toml (pyproject.toml): селекторы "E/W/F/I/B/UP/DJ/RUF",
расширенный ignore-list для стилевых noise (DJ012, E402, E731, B007, B028, B905,
RUF005/046/059, и кириллица в комментариях RUF001/002/003).

Production health-check (перед показом)
    python manage.py check_demo_ready --json
    python manage.py check_data_integrity --json

"check_demo_ready" выводит "scientific_stack" (NumPy/SciPy/Matplotlib/Pandas/python-engineering),
smoke-проверки FFT/Bode/Monte Carlo/Signal quality/Parameter sweep/DC fallback,
а также "graph_stack", "formula_stack", "circuit_svg_stack" (NetworkX/SymPy/Schemdraw)
и "expert_stack" (jsonschema/rule-engine/Pint/Lark/Z3/scikit-fuzzy).

Legacy-shorthand (всё ещё работает)
    .\scripts\run_checks.ps1               # выставляет DJANGO_SETTINGS_MODULE=Dolg_PR.settings_test и гонит manage.py test
    .\scripts\run_browser_e2e.ps1          # Playwright browser-smoke


Детальный отчёт по покрытию — в docs/TESTS_AND_REPORTS.md, активный фронт работ — в docs/WORK_FRONT_20260616.md, история развития — в docs/DEVELOPMENT_HISTORY.md.

Дипломная редакция
Перед показом наработок 04.05.2026 диплом ведётся в режиме полноценной ВКР-редакции, а не как набор технических дополнений. Правила оформления и переписывания зафиксированы в docs/DIPLOMA_REWRITE_GUIDE.md: основной текст должен быть связным, длинные фрагменты кода и журнальные таблицы переносятся в приложения, а все заявленные технологии получают явный статус «реализовано», «реализовано частично» или «перспектива».

Рабочая цель ближайших итераций — синхронизировать код, проектные docs и новый DOCX диплома после каждого шага, особенно для модулей симуляции и CAD.

Админ-панель
URL: "/admin/". Доступ выполняется под суперпользователем, созданным командой
"python manage.py createsuperuser".

Зарегистрированы все модели: каталог, заказы (сводка по заказам, цветные бейджи + actions),
адреса, профили, проекты схем, статьи энциклопедии.

Публичная демонстрация
Скачанный "cloudflared.exe" (Cloudflare Tunnel) создаёт одноразовый HTTPS-домен
вида "https://xxx.trycloudflare.com" без регистрации и настройки роутера.
"start_public.bat" запускает всё автоматически.

Для локального дипломного показа "/media/" раздаётся Django даже при "DEBUG=False" через "SERVE_MEDIA=1" по умолчанию. В продакшене за nginx можно поставить "SERVE_MEDIA=0", потому что "nginx.conf" отдаёт "/media/" напрямую.

Для постоянного домена — завести бесплатный Cloudflare-аккаунт и
named tunnel (https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/).

Что ещё планируется (см. "docs/WORK_FRONT_20260616.md" и "docs/DEVELOPMENT_HISTORY.md")
Приоритет 1
• Развить media-policy V2: при наличии ключей официальных порталов производителей/дистрибьюторов подключить ручной allowlist product-shot, но только как проверенный источник поверх текущих локальных assets/generated-заглушек.
• Расширить browser/e2e дальше: добавить screenshot-baseline/diff для CAD, projects, панели свойств и расширенных состояний нижней аналитики симуляции, а также проверку demo-проектов.
• Продолжить ремонт клиентской части по docs/UI_CAD_SIM_AUDIT.md: после выноса "scheme-normalizer.js", "scheme-export.js", "scheme-bom.js" и "scheme-netlist.js" с генерацией SPICE-элементов/analysis directives продолжить разделение rendering/simulation-кода и screenshot-baseline для CAD/projects.
• Сначала чинить и модернизировать существующие модули симуляции и CAD под современные инженерные требования: probes/курcоры графиков, сохранение результатов, понятные ошибки ngspice.wasm, Multisim-like отрисовку схем, DRC/ERC, save/load, сетку/слои/штамп, размеры, горячие клавиши и переполнения интерфейса.
• Сверить актуальный текст диплома с фактической реализацией и перенести все заявленные, но отсутствующие функции в "docs/WORK_FRONT_20260616.md".

Приоритет 2
• PostgreSQL dry-run, Docker + Nginx + Gunicorn для продакшна.
• Расширенная библиотека SPICE-моделей; импорт/экспорт KiCad, LTspice, EDIF, Gerber и Excellon — после стабилизации текущих CAD/симуляции.
• WebGL/PixiJS-рендер CAD при 1000+ элементах.

Future killer-фичи
• Обязательная быстрая фича: "What if"-слайдер параметров компонентов с debounced re-run симуляции и live-графиками.
• Далее: AI-ассистент DOLG, 3D-просмотр платы, диагностика неисправностей и расширение лаборатории до проектного review.
• Marketplace/QR — после публичного деплоя; block-based editor — отдельный learning mode, не часть основного CAD.

Автор
Дипломная работа · 2026 г.
Контакты: "rampage.ninja.dev@gmail.com"

2026-05-17: Engineering Review, CAD Import, Self AI
Новый этап развития закрепляет DOLG не как отдельный каталог или симулятор, а как инженерный контур проверки проекта.

• "ProjectReview" сохраняет snapshot проверки: схема, DRC/ERC, BOM-риск, измерения, derating, fault-сценарии, рекомендации и "Design Health Score".
• "/projects/api/<id>/review/" создает review, "/projects/review/<id>/" показывает HTML-отчет, "/projects/review/<id>.pdf" экспортирует отчет для демо/защиты.
• "ProjectMeasurement" хранит измерения лаборатории и симуляции: напряжение узла, ток ветви, RMS, частота, duty cycle, мощность и температура.
• "Dolg_APP/services/cad_import.py" импортирует ограниченный LTspice/SPICE netlist и KiCad subset во внутренний "scheme_data", после чего запускается тот же review core.
• "Dolg_APP/services/learning_by_review.py" связывает findings и topology review с практическими уроками: отсутствующий GND, делитель, RC-цепь, LED-индикатор и derating.
• "Dolg_APP/services/rule_ai.py" добавляет самописный rule-based AI-помощник без обязательной внешней LLM: ответы строятся по схеме, BOM, review, расчетам и fault library.
• Self AI расширен до intent-режимов: краткий разбор схемы, GND, план исправления, измерения "expected vs measured", derating, BOM/каталог, CAD-import и learning-by-review; API возвращает "intent", "confidence" и быстрые действия для UI.
• В "knowledge" добавлен диагностический learning track "diagnostika-prostyh-shem", который использует реальные ошибки review: нет GND, перегрев, измерение результата.
• Search и "check_demo_ready" знают про review/import/diagnostics; demo-ready smoke проверяет "cad_import_preview_details" и Learning-by-review, targeted regression: "python manage.py test Dolg_APP.tests.EngineeringReviewTests knowledge.tests.EngineeringLabTests knowledge.tests.PopulateKnowledgeLearningTests shop.tests.GlobalSearchAndDemoRouteTests shop.tests.DemoReadyCommandScientificStackTests".

2026-05-17: Scientific Simulation Stack
Новый численный слой добавлен без пересмотра архитектуры: все расчеты лежат в Python service-layer и переиспользуются API, лабораторией и будущими учебными заданиями.

• "Dolg_APP/services/simulation_analysis.py" использует NumPy/SciPy/Matplotlib/Pandas для FFT, Bode plot, Monte Carlo tolerance, signal quality THD/SINAD/ENOB, parameter sweep, DC fallback и статистики запусков.
• Pro endpoints: "/simulation/api/pro/fft/", "/simulation/api/pro/bode/", "/simulation/api/pro/monte-carlo/", "/simulation/api/pro/signal-quality/", "/simulation/api/pro/parameter-sweep/".
• Fallback endpoint: "/simulation/api/fallback-solve/" решает простые DC-цепи R/V/GND на сервере.
• Project analytics: "/projects/api/<id>/simulation-runs/stats/" возвращает slowest runs и агрегаты по типам анализа.
• Pro-метрики можно сохранить в "ProjectMeasurement" через существующий endpoint "/projects/api/<id>/measurements/create/".
• "python-engineering" подключен к инженерной лаборатории как validation backend; библиотека не заменяет собственные электронные формулы, потому что ее текущий пакет не содержит готовых калькуляторов для NE555/RC/стабилизаторов.
• "check_demo_ready --json" проверяет установленные scientific-библиотеки и мини-сценарии service-layer: "fft_svg", "bode_svg", "monte_carlo_svg", "signal_quality_svg", "parameter_sweep_svg", "dc_fallback".
• Phase 2 AI получил первый безопасный PyTorch-слой: tiny neural backend для "DolgAIPipeline backend='neural'" дает probabilistic "deep_hint" по топологии, риску и следующему компоненту, а expert/review остается финальным verdict.

2026-05-18: Lightweight Graph/Formula/SVG Stack
Перед нейронным этапом добавлен легкий библиотечный слой, который усиливает уже существующие CAD/SIM, review и learning-сервисы без утяжеления старта Django.

• "networkx" используется в "Dolg_APP/services/schematic_graph.py": связность схемы, floating nodes, путь до GND, изолированные компоненты, простые циклы и базовое определение topology ("voltage_divider", "rc_network", "led_indicator").
• "sympy" используется в "knowledge/services/formula_steps.py": объяснение закона Ома, делителя, мощности, RC cutoff и NE555, а также проверка эквивалентных выражений в учебных задачах.
• "schemdraw" используется в "knowledge/services/circuit_svg.py": SVG для учебных и отчетных схем LED-индикатора, делителя, RC-фильтра, NE555 и транзисторного ключа. Карточки товаров через Schemdraw не генерируются.
• Engineering Review, "rule_ai" и grader обучения читают общий graph/formula слой через service-layer; старые DRC/ERC проверки не удалены, а расширены.
• "check_demo_ready --json" проверяет версии библиотек и smoke-сценарии "graph_stack", "formula_stack", "circuit_svg_stack".
• PyTorch вынесен в optional "requirements-ai.txt", чтобы обычный старт Django не тянул тяжелый импорт; tiny-модель обучается командой "python manage.py train_tiny_circuit_ai".

2026-05-18: Expert-First Review Stack
Следующий слой развития построен в порядке "expert systems -> constraints/optimization -> neural deep analysis". Нейронная часть не заменяет инженерные правила, а позже будет давать вероятностные "deep_hint" поверх проверяемой базы.

• "Dolg_APP/expert_rules/default_rules.json" хранит версионированный rule pack; "Dolg_APP/services/expert_rules.py" валидирует его через "jsonschema" и исполняет условия через "rule-engine".
• "Dolg_APP/services/engineering_units.py" использует Pint для общего parsing/validation номиналов: "10k", "6.8kOhm", "2.5мА", "100нФ", "В/Ом/Гц/Вт" и предупреждения о подозрительных единицах.
• "Dolg_APP/services/constraint_solver.py" добавляет Z3-подбор вариантов для LED-резистора, делителя, RC cutoff, NE555, стабилизатора и теплового запаса.
• "Dolg_APP/services/cad_parsers.py" использует Lark для SPICE/LTspice subset; импорт сначала нормализует схему в "scheme_data", затем запускает review.
• "Dolg_APP/services/risk_scoring.py" добавляет fuzzy risk score через scikit-fuzzy для перегрева, слабого запаса, BOM-risk и топологических предупреждений.
• "ProjectReview" теперь включает "expert_findings", "rule_id", severity, evidence, recommendation, confidence и fuzzy-risk; "rule_ai" отвечает по "Expert trace", а не придумывает факты.
• "check_demo_ready --json" проверяет новый "expert_stack" и smoke-сценарии "rule_pack", "rule_engine_finding", "pint_unit_parse", "lark_import_preview", "z3_voltage_divider", "fuzzy_risk".
• OR-Tools и RDFLib остаются roadmap; PyTorch подключен как optional deep-hints backend без права менять expert verdict.

2026-05-25: Self AI V2 + Tiny PyTorch Backend
• AI-панель получила карточку "Разбор схемы": topology, score, GND/source, DRC/ERC, floating fragments, measurements и BOM-связь видны до отправки вопроса.
• "/api/ai/context/" возвращает компактный контекст схемы, а "/api/ai/chat/" принимает 20 сообщений истории, "session_summary" и "last_intent".
• "rule_ai" возвращает structured "quick_actions", "context_sources", "used_context", "session_summary" и active token usage для self-hosted режима.
• "Dolg_APP/ml/neural.py" добавляет tiny PyTorch model: fixed feature vector по "scheme_data", topology head, risk head и next-component head.
• "train_tiny_circuit_ai" обучает демо-модель на синтетических схемах и сохраняет "media/ml/tiny_circuit_ai.pt"; текущий прогон: 180 схем, 60 epochs, loss "0.138674".
• "check_demo_ready --json" выводит "neural_stack": torch "2.12.0", trained tiny model OK.

2026-05-25: Engineering Artifact Ingestion
• Добавлен корпус инженерных артефактов: модели "EngineeringArtifact" и "AITrainingExample", команда "python manage.py ingest_engineering_artifacts", сервис "Dolg_APP/services/artifact_ingestion.py".
• V1 парсит DOCX/PDF/PPTX/DXF, P-CAD ".net/.drc/.erc" и OLE metadata. DWG/MS14 не читаются как полноценная схема, но сохраняются как metadata + предупреждение о конвертации.
• "ProjectReview" получил разделы "reliability", "manufacturing", "external_cad" и "artifacts"; импортированные DRC/ERC findings идут в score, evidence и русские поля "title_ru/evidence_ru/recommendation_ru".
• Self AI использует artifact memory как источник контекста: артефакты, check findings, fault cases и learning-by-artifact подсказки.
• "check_demo_ready --json" проверяет "artifact_stack": "pypdf", "python-docx", "python-pptx", "ezdxf", "olefile", P-CAD DRC/NET, DXF, DWG/MS14 stubs, learning-by-artifact и AI training examples.

2026-05-26: Free / Pro / Enterprise entitlements
• Добавлен единый service-layer "Dolg_APP/services/entitlements.py": "get_effective_plan", "has_feature", "check_feature", "require_feature".
• Pro-аналитика теперь закрыта feature-gates: FFT, Bode, Monte Carlo, signal quality, parameter sweep и server-side fallback solver доступны только Pro/Enterprise.
• AI-балабол разделен по тарифам: Free получает базовый чат и DRC++/аналоги, Pro получает расширенный разбор схемы, 20 сообщений истории, "session_summary", token counter и pipeline explain/recommend, Enterprise добавляет командный контекст проекта.
• Enterprise определяется как "Organization.plan='enterprise'" плюс активная org-подписка; org-level функции вроде audit-log, API tokens, approval workflow и analytics проверяются через entitlements.
• "/billing/" показывает Free, Pro и Enterprise; "/api/usage/today/" возвращает "plan", "features" и "feature_flags".

2026-05-26: Legal Knowledge Corpus
• Добавлен "knowledge/data/legal_sources.json": curated-список открытых учебников и официальной документации по электронике, CAD/SPICE, Django, graph/formula/unit stack, constraint solving и PyTorch.
• Добавлена команда "python manage.py seed_legal_sources": создает обзорную статью "Открытые источники и документация DOLG" и привязывает источники как "ArticleMaterial" к профильным статьям энциклопедии.
• Legal corpus стал активным evidence-layer: "knowledge.services.legal_sources" умеет искать источники по запросу, связывать их с "rule_id" и темами обучения, а "rule_ai" добавляет в ответы блок "Опираюсь на" с review finding + legal source.
• Global search и autocomplete теперь показывают группу "Источники и документация" для запросов "ngspice", "KiCad", "Pint", "Z3", "PyTorch", "All About Circuits"; публичной страницы источника в V1 нет, ссылка ведет на связанную статью/обзор.
• Source-backed обучение добавлено в seed: 3 урока и 9 задач по закону Ома, делителю, RC, GND/SPICE/DRC, unit parsing и constraint-подбору LED-резистора. Уроки показывают "Материалы для проверки", а rubric хранит "source_ids/source_topic/teacher_rule".
• AITrainingExample больше не читает внешние тексты: "collect_ai_training_examples" добавляет в "features" только "source_ids", "source_topics", "teacher_rules" и "evidence_kind". "train_tiny_circuit_ai --include-curated" берет scheme features + structured metadata, а PyTorch deep_hint возвращает "evidence_sources".
• "check_demo_ready --json" проверяет "legal_sources_stack": source retrieval, rule bibliography, search smoke, source-backed learning tasks и training metadata. "check_data_integrity --json" валидирует https URL и все source_ids в rules/tasks/training examples.
• Правило для диплома и AI: внешние подборки книг используются только как ориентир по темам/названиям; корпус строится на официальной документации, открытых учебниках, datasheet, demo-проектах и opt-in пользовательских схемах.

2026-06-03: Admin Monitoring Center
• "/staff/ops/" пересобран в операционный центр: health status, alerts, runtime metrics, disk, business, AI/ML, project, moderation и security snapshots.
• Главная Django admin "/admin/" получила компактный мониторинговый блок над списком моделей; метрики догружаются через AJAX из staff-only snapshot API, поэтому админка открывается быстро.
• Добавлен service-layer "Dolg_APP/services/ops_metrics.py"; он собирает единый snapshot для Django admin, JSON API, будущих Prometheus custom metrics и export-отчетов.
• Добавлен "psutil==7.2.2" для RSS/CPU/threads/uptime и storage checks; если пакет недоступен, мониторинг деградирует до "unknown", а не ломает админку.
• Добавлен staff-only endpoint "/staff/ops/api/snapshot/".
• На nginx-границе закрыты публичные "/metrics" и "/metrics/" через 403; Prometheus внутри Docker продолжает scrape "web:8000/metrics/".
• "check_demo_ready --json" теперь проверяет "admin_monitoring_stack": psutil, snapshot sections, staff routes и nginx-защиту metrics endpoint.

2026-06-02: MLJob и Staff Ops Dashboard
• Добавлена модель "MLJob" и миграция "Dolg_APP.0018_mljob": постоянная история импорта датасетов, обучения tiny PyTorch, validation/export/promotion jobs с прогрессом, heartbeat, counters, stdout/error tail и параметрами запуска.
• "/staff/ml-training/" и "/staff/ml-training/import/" теперь создают MLJob; status-endpoints возвращают "latest_job", а reset помечает активные jobs как "cancelled".
• Добавлен staff cockpit "/staff/ops/": счетчики каталога, проектов, review, AITrainingExample, artifacts, moderation и ML status/type counters. В Django admin добавлен "MLJobAdmin".
• AITrainingExample.features получил стандартизированные "dataset_kind", "graph_training_ready" и "training_role"; команда "normalize_ai_dataset_metadata" разделяет корпус на graph-training и retrieval-context. Текущая база: 36 graph-ready схемных примеров и 36 text-only source/learning examples.

2026-05-19: Media Quality Gate
Первый новый пакет после import/review закрывает проблему качества изображений каталога без возврата к Wikimedia/Commons.

• "ImageHash" добавлен к Pillow-слою и используется в "shop/services/media_quality.py" для perceptual hash локальных product-shot.
• Gate проверяет каждую активную карточку: наличие файла, читаемость, минимальный размер, однотонность, extreme aspect ratio, визуальную детализацию, policy-нарушение и итоговый "quality_score".
• Generated-заглушки остаются допустимым контролируемым источником; perceptual-дубли среди них не считаются проблемой, потому что это собственный fallback-art.
• "check_data_integrity --json" теперь возвращает "catalog.media_quality", а "check_demo_ready --json" возвращает верхнеуровневый блок "media_quality".
