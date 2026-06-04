"""Тонкий register-layer для shop-шаблонов.

Вся ЛОГИКА (helpers + константы) переехала в `shop/card_helpers.py`
2026-05-19 — было слишком много в одном файле (846 строк).

Здесь только регистрация template-фильтров / тегов через
`register.filter()` / `register.simple_tag()`. Сами функции импортируются
из `shop.card_helpers`.

8 шаблонов с `{% load shop_extras %}` продолжают работать без изменений —
для них API остался тем же.
"""

from django import template

from shop import card_helpers
from shop.services import catalog_filters

register = template.Library()


# ── Базовые helpers ──
register.filter('get_item')(card_helpers.get_item)
register.simple_tag(name='category_icon')(card_helpers.category_icon)
register.filter('manufacturer_label')(card_helpers.manufacturer_label)

# ── Параметры product_detail (раскладка по группам) ──
register.filter('group_parameters')(card_helpers.group_parameters)

# ── Чипы карточки товара ──
register.filter('chip_filter_name')(card_helpers.chip_filter_name)
register.filter('chip_group')(card_helpers.chip_group)
register.filter('parameter_preview')(card_helpers.parameter_preview)
register.filter('datasheet_summary')(card_helpers.datasheet_summary)
register.simple_tag(name='chip_value_valid')(card_helpers.chip_value_valid)

# ── Стоковые картинки ──
register.filter('is_stock_image')(card_helpers.is_stock_image)

# ── Брендовые бейджи + delivery hint ──
register.filter('brand_badge')(card_helpers.brand_badge)
register.filter('delivery_hint')(card_helpers.delivery_hint)

# ── Рейтинг и отзывы (seeded, без БД) ──
register.filter('product_rating')(card_helpers.product_rating)
register.filter('product_reviews')(card_helpers.product_reviews)


@register.simple_tag(takes_context=True)
def catalog_filter_url(context, base_url, key, value):
    request = context.get('request')
    params = getattr(request, 'GET', {}) if request else {}
    return f'{base_url}{catalog_filters.querystring_with(params, key, value, leading_question=True)}'


@register.simple_tag(takes_context=True)
def catalog_filter_active(context, key, value):
    request = context.get('request')
    params = getattr(request, 'GET', {}) if request else {}
    return 'is-active' if catalog_filters.is_filter_active(params, key, value) else ''


@register.filter('facet_count')
def facet_count(facets, args):
    try:
        group, key = str(args).split(':', 1)
    except ValueError:
        return 0
    return catalog_filters.facet_count(facets, group, key)


@register.simple_tag
def catalog_facet_count(facets, group, key):
    return catalog_filters.facet_count(facets, group, key)
