"""Конфигурация django-jazzmin для админки DOLG (тёмная тема + навигация + поиск).

Вынесено отдельным модулем, чтобы в settings.py было всего 2 строки активации:
    INSTALLED_APPS = ['jazzmin', *INSTALLED_APPS]   # ПЕРЕД 'django.contrib.admin'
    from .jazzmin_config import JAZZMIN_SETTINGS, JAZZMIN_UI_TWEAKS  # noqa: F401,E402

Предварительно: pip install django-jazzmin (уже в requirements.txt).
Документация: https://django-jazzmin.readthedocs.io/configuration/
"""

# ── Основные настройки: брендинг, поиск, навигация, иконки ────────────────────────────────────
JAZZMIN_SETTINGS = {
    'site_title': 'DOLG · Админка',
    'site_header': 'DOLG',
    'site_brand': 'DOLG',
    'site_logo_classes': 'img-circle',
    'welcome_sign': 'Панель управления DOLG — каталог, схемы, заказы, обучение',
    'copyright': 'DOLG · дипломный проект',
    # Глобальный поиск в шапке по ключевым моделям.
    'search_model': ['shop.Product', 'auth.User', 'Dolg_APP.SchematicProject', 'orders.Order'],
    # Быстрые ссылки в верхнем меню.
    'topmenu_links': [
        {'name': 'На сайт', 'url': '/', 'new_window': False},
        {'name': 'Каталог', 'url': '/', 'new_window': False},
        {'app': 'shop'},
    ],
    'usermenu_links': [
        {'name': 'На сайт', 'url': '/', 'icon': 'fas fa-globe'},
    ],
    # Сайдбар: показываем, разворачиваем, иконки.
    'show_sidebar': True,
    'navigation_expanded': True,
    'hide_apps': [],
    'hide_models': [],
    # Порядок приложений в сайдбаре — важное выше.
    'order_with_respect_to': ['shop', 'Dolg_APP', 'orders', 'accounts', 'knowledge', 'moderation', 'auth'],
    # Иконки FontAwesome 5 (сайдбар становится информативным, а не текстовым списком).
    'icons': {
        'auth': 'fas fa-users-cog',
        'auth.user': 'fas fa-user',
        'auth.Group': 'fas fa-users',
        'shop': 'fas fa-store',
        'shop.Product': 'fas fa-microchip',
        'shop.Category': 'fas fa-layer-group',
        'shop.Cart': 'fas fa-shopping-cart',
        'shop.CartItem': 'fas fa-cart-plus',
        'orders': 'fas fa-receipt',
        'orders.Order': 'fas fa-file-invoice-dollar',
        'Dolg_APP': 'fas fa-project-diagram',
        'Dolg_APP.SchematicProject': 'fas fa-diagram-project',
        'accounts': 'fas fa-id-card',
        'accounts.UserProfile': 'fas fa-id-badge',
        'knowledge': 'fas fa-book',
        'knowledge.Article': 'fas fa-file-lines',
        'moderation': 'fas fa-shield-halved',
    },
    'default_icon_parents': 'fas fa-chevron-circle-right',
    'default_icon_children': 'fas fa-circle',
    # Удобство форм: табы вместо длинной простыни полей + связанные объекты в модалках.
    'related_modal_active': True,
    'changeform_format': 'horizontal_tabs',
    'changeform_format_overrides': {
        'auth.user': 'collapsible',
        'auth.group': 'vertical_tabs',
    },
    # UI-кастомайзер показываем только staff в dev — пусть подберут тему на лету.
    'show_ui_builder': False,
}

# ── Тема под cosmic-стиль DOLG: тёмная, синий акцент ──────────────────────────────────────────
JAZZMIN_UI_TWEAKS = {
    'theme': 'darkly',  # тёмная Bootswatch-тема, близкая к cosmic-стилю сайта
    'dark_mode_theme': 'darkly',
    'navbar': 'navbar-dark',
    'navbar_fixed': True,
    'sidebar_fixed': True,
    'sidebar': 'sidebar-dark-info',
    'sidebar_nav_compact_style': True,
    'sidebar_nav_flat_style': True,
    'brand_colour': 'navbar-dark',
    'accent': 'accent-info',
    'body_small_text': False,
    'footer_fixed': False,
    'actions_sticky_top': True,  # кнопки сохранения «прилипают» — удобнее в длинных формах
    'button_classes': {
        'primary': 'btn-info',
        'success': 'btn-success',
        'danger': 'btn-danger',
    },
}
