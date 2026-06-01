# Гайд по скриншотам для защиты диплома

Список страниц и состояний, которые желательно зафиксировать перед защитой
для слайдов и приложений к диплому. Положите файлы в `docs/screenshots/<group>/`.

## Подготовка

```bash
# 1. Очистить и заполнить демо-данными
python manage.py migrate
python manage.py populate_reb_products
python manage.py populate_demo_projects
python manage.py seed_announcements
python manage.py apply_curated_product_photos

# 2. Создать админа
python manage.py createsuperuser   # admin / любой надёжный пароль

# 3. Создать demo-org для Enterprise-скриншотов
python manage.py shell -c "
from Dolg_APP.models import Organization, OrganizationMember, Subscription
from django.contrib.auth import get_user_model
from datetime import timedelta
from django.utils import timezone

U = get_user_model()
admin = U.objects.get(username='admin')
org, _ = Organization.objects.get_or_create(
    slug='dolg-demo',
    defaults={'name':'DOLG Demo Inc.', 'owner':admin, 'billing_email':'demo@dolg.local', 'plan':'business', 'seats_max':25}
)
OrganizationMember.objects.get_or_create(organization=org, user=admin, defaults={'role':'owner'})
Subscription.objects.update_or_create(
    organization=org,
    defaults={'tier':'pro','status':'active','provider':'manual','period_end':timezone.now()+timedelta(days=365)},
)
print('Demo org готова:', org.slug)
"

# 4. Запустить сервер
python manage.py runserver 0.0.0.0:8000
```

## 1. Каталог и shop

| Файл | Что захватить |
|---|---|
| `01-index-main.png` | Главная `/` без фильтров — категорий и полки товаров |
| `02-index-filtered.png` | Главная с активным фильтром (например, `?manufacturer=vishay`) |
| `03-category.png` | Страница категории (резисторы) с боковыми фильтрами |
| `04-product-detail.png` | Карточка товара с параметрами + datasheet |
| `05-compare.png` | `/compare/` с 3 товарами и автоанализом «лучше/хуже» |
| `06-cart.png` | Корзина с парой товаров |
| `07-checkout.png` | Оформление заказа |

## 2. Редактор схем и симулятор

| Файл | Что захватить |
|---|---|
| `10-simulator-blank.png` | Симулятор без схемы — toolbar и сетка |
| `11-simulator-rc-filter.png` | Загружен RC-фильтр (демо), показаны компоненты с подписями |
| `12-simulator-tran.png` | Запущен TRAN — графики напряжений и токов |
| `13-simulator-ac.png` | AC-анализ — Bode plot (мага + фаза) |
| `14-fft.png` | Pro-аналитика: FFT spectrum через SciPy |
| `15-thermal.png` | Тепловой анализ с цветовой аурой компонентов |
| `16-what-if-slider.png` | What-if слайдер на номинале R/C |
| `17-bom.png` | Модалка BOM с матчингом каталога |
| `18-3d-pcb.png` | 3D PCB viewer (Three.js) |
| `19-virtual-lab.png` | Виртуальная лаборатория (осциллограф/мультиметр/генератор) |
| `20-ai-fab.png` | AI-ассистент: чат с Claude (одна из вкладок) |
| `21-ai-pipeline.png` | AI-ассистент: pipeline strip с DRC++/След.компонент/Объясни |

## 3. CAD и проекты

| Файл | Что захватить |
|---|---|
| `30-cad-blank.png` | CAD с ГОСТ-рамкой А4 |
| `31-cad-with-blocks.png` | CAD с компонентами (DIP-8, делитель) и штриховкой |
| `32-projects-list.png` | `/projects/` со списком пользовательских проектов |
| `33-project-versions.png` | Боковая панель версий проекта |

## 4. Энциклопедия и обучение

| Файл | Что захватить |
|---|---|
| `40-knowledge-index.png` | `/knowledge/` — 6 категорий |
| `41-article.png` | Открытая статья с фото/datasheet/материалами |
| `42-engineering-lab.png` | `/knowledge/lab/` — калькулятор узла (например, NE555) |
| `43-learning-task.png` | Учебная задача с автопроверкой |

## 5. Чат и Enterprise (новое в 2026-05-19)

| Файл | Что захватить |
|---|---|
| `50-chat-list.png` | `/chat/` — список топиков + сайдбар «📢 Информационный канал» |
| `51-chat-topic-detail.png` | Открытый топик с ответами + реакции |
| `52-chat-new-topic.png` | Форма создания топика (для авторизованного) |
| `53-org-dashboard.png` | `/orgs/<slug>/` — карточки members/projects |
| `54-org-members.png` | `/orgs/<slug>/members/` — таблица с ролями |
| `55-org-audit.png` | `/orgs/<slug>/audit/` — лог действий |
| `56-org-conversation-list.png` | `/orgs/<slug>/conversations/` |
| `57-org-conversation-chat.png` | Открытый канал команды с парой сообщений |
| `58-org-approval.png` | `/orgs/<slug>/approval/` — очередь approval |
| `59-org-settings-branding.png` | Org-настройки: логотип, цвет, SSO toggle |
| `60-org-api-tokens.png` | API tokens management |

## 6. Биллинг и подписки

| Файл | Что захватить |
|---|---|
| `70-billing-plans.png` | `/billing/` — таблица tier'ов с ценами |
| `71-pro-trial-active.png` | Профиль с активной Pro-подпиской |
| `72-quota-banner.png` | Баннер «лимит исчерпан» в симуляторе для Free |

## 7. Админ-панель

| Файл | Что захватить |
|---|---|
| `80-admin-index.png` | `/admin/` — все зарегистрированные модели |
| `81-admin-organization.png` | Список Organization с фильтрами |
| `82-admin-announcement.png` | Форма редактирования Announcement |
| `83-admin-auditlog.png` | AuditLog с примером записей |

## 8. Тесты и метрики (для слайда «качество»)

| Файл | Что захватить |
|---|---|
| `90-pytest-passed.png` | Терминал с `pytest --cov` финальным выводом (263 passed, 71%) |
| `91-ruff-clean.png` | Терминал с `ruff check . — All checks passed!` |
| `92-coverage-html.png` | `htmlcov/index.html` — HTML отчёт по покрытию |

## Технические советы по съёмке

1. **Браузер**: Chrome / Firefox с DevTools закрытым.
2. **Разрешение**: минимум 1920×1080 (для печатных версий желательно 2560×1440).
3. **Тёмная тема DOLG** — на скриншотах смотрится профессиональнее печатной чёрно-белой.
4. **Чтобы не было блика на курсоре** — `Ctrl+Shift+P → "Capture full size screenshot"` в DevTools (для длинных страниц).
5. **Для PDF-приложений к диплому** — экспортируйте в PNG, не JPEG (текст резче).
6. **Расширение названий файлов** — придерживайтесь предложенной схемы `<NN>-<group>-<state>.png`, потом проще ссылаться из текста ВКР.

## Где использовать

- Глава 2 (Архитектура и компоненты) — 01-09, 30-31
- Глава 3 (Симулятор и аналитика) — 10-21
- Глава 4 (Энциклопедия) — 40-43
- Глава 5 (Enterprise и коллаборация) — 50-60
- Приложение А (Скриншоты) — все
- Презентация / речь — 4-5 самых эффектных (например, 13 + 18 + 21 + 51 + 57)
