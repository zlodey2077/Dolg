from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlencode

from django.db.models import QuerySet

from Dolg_APP.services.engineering_units import parse_engineering_quantity
from shop.models import Product
from shop.smart_search import extract_range_constraints, filter_by_ranges, parse_query_tokens

ENGINEERING_FILTERS = {
    'nominal': ('value', 'resistance', 'capacitance', 'inductance', 'capacity'),
    'power': ('power', 'wattage', 'tdp', 'tdp_rated'),
    'voltage': ('voltage', 'supply_voltage', 'vceo', 'vr', 'vrrm', 'vf', 'coil_voltage'),
    'current': ('current', 'ic', 'id', 'if'),
    'tolerance': ('tolerance',),
    'type': ('type',),
    'pins': ('pins', 'pin_count', 'contact_count'),
    'pitch': ('pitch',),
    'frequency': ('frequency', 'base_clock', 'boost_clock', 'refresh_rate', 'bandwidth'),
    'capacity': (
        'capacity',
        'ram',
        'storage',
        'vram',
        'battery',
        'battery_earbuds',
        'battery_case',
        'cache_l3',
    ),
    'display': ('screen_size', 'resolution', 'panel', 'display', 'hdr'),
    'platform': ('socket', 'chipset', 'chipset_support', 'chip', 'cpu', 'gpu', 'gpu_chip', 'process'),
    'connectivity': (
        'connectivity',
        'network',
        'outputs',
        'inputs',
        'power_conn',
        'm2_slots',
        'pcie',
        'ram_slots',
        'charging',
        'os',
        'codec',
    ),
    'form_factor': ('form_factor',),
    'interface': ('interface',),
    'dielectric': ('dielectric',),
    'mounting': ('mounting',),
    'material': ('material', 'contact_material', 'flux_core'),
    'application': ('application',),
    'size': ('length', 'width', 'diameter', 'size', 'board_size', 'hole_count', 'points', 'power_rails'),
    'wire': ('gauge', 'section', 'color'),
    'configuration': ('configuration', 'orientation', 'gender'),
    'temperature_range': (
        'temperature_range',
        'operating_temp',
        'max_temp',
        'temp_max',
        'min_temp',
        'melting_point',
    ),
    'compatibility': ('compatibility',),
    'mode': ('mode', 'signal'),
    'safety': ('safety',),
}

STANDARD_FILTERS = (
    'q',
    'manufacturer',
    'lifecycle',
    'package',
    'in_stock',
    'part_number',
    'hide_eol',
    'price_min',
    'price_max',
    'has_datasheet',
    'has_spice_model',
    'has_cad_model',
)
CATALOG_FILTERS = STANDARD_FILTERS + tuple(ENGINEERING_FILTERS.keys())

FILTER_LABELS = {
    'q': 'Search',
    'manufacturer': 'Manufacturer',
    'lifecycle': 'Lifecycle',
    'package': 'Package',
    'in_stock': 'In stock',
    'part_number': 'Part number',
    'price_min': 'Price from',
    'price_max': 'Price to',
    'has_datasheet': 'Datasheet',
    'has_spice_model': 'SPICE model',
    'has_cad_model': 'CAD model',
    'nominal': 'Nominal',
    'power': 'Power',
    'voltage': 'Voltage',
    'current': 'Current',
    'tolerance': 'Tolerance',
    'type': 'Type',
    'pins': 'Pins',
    'pitch': 'Pitch',
    'frequency': 'Frequency',
    'capacity': 'Capacity',
    'display': 'Display',
    'platform': 'Platform',
    'connectivity': 'Connectivity',
    'mounting': 'Mounting',
    'interface': 'Interface',
    'form_factor': 'Form factor',
    'dielectric': 'Dielectric',
    'material': 'Material',
    'application': 'Application',
    'size': 'Size',
    'wire': 'Wire',
    'configuration': 'Configuration',
    'temperature_range': 'Temperature',
    'compatibility': 'Compatibility',
    'mode': 'Mode',
    'safety': 'Safety',
}

RANGE_PREFIXES = {
    'R': ('nominal', 'ohm'),
    'V': ('voltage', 'volt'),
    'P': ('power', 'watt'),
}

FILTER_UNITS = {
    'power': 'watt',
    'voltage': 'volt',
    'current': 'ampere',
    'tolerance': 'percent',
}

KEY_UNITS = {
    'resistance': 'ohm',
    'value': 'ohm',
    'power': 'watt',
    'wattage': 'watt',
    'tdp': 'watt',
    'tdp_rated': 'watt',
    'voltage': 'volt',
    'supply_voltage': 'volt',
    'vceo': 'volt',
    'vr': 'volt',
    'vrrm': 'volt',
    'vf': 'volt',
    'coil_voltage': 'volt',
    'current': 'ampere',
    'ic': 'ampere',
    'id': 'ampere',
    'if': 'ampere',
    'tolerance': 'percent',
}


@dataclass(frozen=True)
class RangeExpression:
    filter_name: str
    unit: str
    op: str = ''
    value: float | None = None
    low: float | None = None
    high: float | None = None


def truthy(value: str | None) -> bool:
    return str(value or '').strip().lower() in {'1', 'true', 'on', 'yes', 'y'}


def clean_params(params) -> dict[str, str]:
    result = {}
    for key in CATALOG_FILTERS:
        value = params.get(key, '')
        if value is None:
            value = ''
        if key in {'in_stock', 'has_datasheet', 'has_spice_model', 'has_cad_model', 'hide_eol'}:
            if truthy(value):
                result[key] = '1'
        else:
            value = str(value).strip()
            if value:
                result[key] = value
    return result


def apply_catalog_filters(products, params) -> tuple[list[Product], str]:
    active = clean_params(params)
    query = active.get('q', '')

    items = list(products.select_related('category') if isinstance(products, QuerySet) else products)
    if query:
        # Phase 1.5: вынимаем range-токены («R<10k», «P>0.25») и фильтруем по
        # параметрам (Python-side), остаток — обычный текстовый поиск.
        text_query, range_constraints = extract_range_constraints(query)
        if range_constraints:
            items = filter_by_ranges(items, range_constraints)
        if text_query:
            items = _search_products(items, text_query)

    manufacturer = active.get('manufacturer')
    if manufacturer:
        items = [product for product in items if product.manufacturer == manufacturer]

    lifecycle = active.get('lifecycle')
    if lifecycle:
        items = [product for product in items if product.lifecycle_status == lifecycle]

    package = active.get('package')
    if package:
        needle = package.lower()
        items = [product for product in items if needle in (product.package_type or '').lower()]

    part_number = active.get('part_number')
    if part_number:
        needle = part_number.lower().strip()
        items = [product for product in items if needle in (product.part_number or '').lower()]

    if truthy(active.get('in_stock')):
        items = [product for product in items if product.stock > 0]

    if truthy(active.get('hide_eol')):
        # «Скрыть EOL/Obsolete» — отрезает компоненты, снятые с производства.
        # NRND (Not Recommended for New Designs) НЕ скрываем — он ещё в производстве,
        # просто не рекомендуется для новых дизайнов.
        items = [product for product in items if product.lifecycle_status not in ('eol', 'obsolete')]

    price_min = _to_float(active.get('price_min'))
    if price_min is not None:
        items = [product for product in items if float(product.price) >= price_min]

    price_max = _to_float(active.get('price_max'))
    if price_max is not None:
        items = [product for product in items if float(product.price) <= price_max]

    if truthy(active.get('has_datasheet')):
        items = [product for product in items if bool(product.datasheet_url)]
    if truthy(active.get('has_spice_model')):
        items = [product for product in items if bool((product.parameters or {}).get('spice_model'))]
    if truthy(active.get('has_cad_model')):
        items = [
            product
            for product in items
            if bool(
                (product.parameters or {}).get('cad_model_url') or (product.parameters or {}).get('cad_model')
            )
        ]

    for name in ENGINEERING_FILTERS:
        value = active.get(name, '')
        if value:
            items = [product for product in items if matches_engineering_filter(product, name, value)]

    return items, query


def search_products(products, query: str) -> list[Product]:
    return _search_products(list(products), query)


def matches_engineering_filter(product: Product, name: str, raw_value: str) -> bool:
    params = product.parameters or {}
    expression = parse_range_expression(raw_value, default_filter=name)
    for key in ENGINEERING_FILTERS[name]:
        value = params.get(key)
        if value in (None, ''):
            continue
        if expression and expression.filter_name == name:
            if _value_matches_expression(value, expression, key):
                return True
        elif _substring_or_numeric_match(value, raw_value, key, name):
            return True
    return False


def parse_range_expression(raw: str, default_filter: str = 'nominal') -> RangeExpression | None:
    text = _normalize_text(raw)
    if not text:
        return None

    prefix = ''
    rest = text
    if len(text) >= 2 and text[0].upper() in RANGE_PREFIXES and (text[1] in '<>=' or text[1].isspace()):
        prefix = text[0].upper()
        rest = text[1:].strip()

    filter_name, unit = RANGE_PREFIXES.get(prefix, (default_filter, _default_unit(default_filter)))

    if '..' in rest:
        left, right = rest.split('..', 1)
        low = parse_catalog_number(left, unit)
        high = parse_catalog_number(right, unit)
        if low is None or high is None:
            return None
        return RangeExpression(filter_name=filter_name, unit=unit, low=min(low, high), high=max(low, high))

    match = re.match(r'^(<=|>=|<|>|=)?\s*(.+)$', rest)
    if not match:
        return None
    op = match.group(1) or ''
    value = parse_catalog_number(match.group(2), unit)
    if value is None:
        return None
    return RangeExpression(filter_name=filter_name, unit=unit, op=op, value=value)


def parse_catalog_number(raw, expected_unit: str = '') -> float | None:
    text = _normalize_text(raw)
    if not text:
        return None
    if expected_unit == 'percent' or '%' in text:
        match = re.search(r'[-+]?\d+(?:[.,]\d+)?', text)
        return float(match.group(0).replace(',', '.')) if match else None

    text = (
        text.replace('кОм', 'kohm')
        .replace('КОм', 'kohm')
        .replace('ком', 'kohm')
        .replace('кО', 'kohm')
        .replace('Ом', 'ohm')
        .replace('ом', 'ohm')
        .replace('В', 'V')
        .replace('в', 'V')
        .replace('Вт', 'W')
        .replace('вт', 'W')
        .replace('мкФ', 'uF')
        .replace('нФ', 'nF')
        .replace('пФ', 'pF')
    )
    parsed = parse_engineering_quantity(text, expected_unit=expected_unit)
    return parsed.value if parsed.ok else None


def build_active_filter_tags(
    params, base_url: str, manufacturer_choices=None, lifecycle_choices=None
) -> list[dict]:
    active = clean_params(params)
    tags = []
    manufacturer_choices = manufacturer_choices or {}
    lifecycle_choices = lifecycle_choices or {}
    for key in CATALOG_FILTERS:
        if key not in active:
            continue
        value = active[key]
        display = value
        if key == 'manufacturer':
            display = manufacturer_choices.get(value, value)
        elif key == 'lifecycle':
            display = lifecycle_choices.get(value, value)
        elif key in {'in_stock', 'has_datasheet', 'has_spice_model', 'has_cad_model'}:
            display = 'yes'
        tags.append(
            {
                'key': key,
                'label': FILTER_LABELS.get(key, key),
                'value': value,
                'display': display,
                'remove_url': f'{base_url}{querystring_without(params, key, leading_question=True)}',
            }
        )
    return tags


def hidden_filter_inputs(params, exclude: Iterable[str] = ('q', 'page')) -> list[dict]:
    exclude = set(exclude)
    active = clean_params(params)
    return [{'name': key, 'value': value} for key, value in active.items() if key not in exclude]


def querystring_without(params, key: str, leading_question: bool = False) -> str:
    data = _copy_params(params)
    data.pop(key, None)
    data.pop('page', None)
    encoded = urlencode(data, doseq=True)
    return f'?{encoded}' if leading_question and encoded else encoded


def querystring_with(params, key: str, value: str, leading_question: bool = False) -> str:
    data = _copy_params(params)
    data.pop('page', None)
    if value in (None, ''):
        data.pop(key, None)
    else:
        data[key] = value
    encoded = urlencode(data, doseq=True)
    return f'?{encoded}' if leading_question and encoded else encoded


def is_filter_active(params, key: str, value: str) -> bool:
    return str(params.get(key, '')).strip().lower() == str(value).strip().lower()


def build_filter_options(products) -> dict[str, list[str]]:
    buckets = {key: set() for key in ENGINEERING_FILTERS}
    for product in products:
        params = product.parameters or {}
        for filter_name, keys in ENGINEERING_FILTERS.items():
            for key in keys:
                value = params.get(key)
                if value not in (None, ''):
                    buckets[filter_name].add(str(value))
    return {
        key: sorted(values, key=lambda value: (len(value), value.lower()))[:40]
        for key, values in buckets.items()
    }


def compute_catalog_facets(products) -> dict[str, list[tuple[str, int]]]:
    items = list(products)
    return {
        'manufacturer': _ordered_counts(product.manufacturer for product in items),
        'lifecycle': _ordered_counts(product.lifecycle_status for product in items),
        'package': _ordered_counts(product.package_type for product in items),
        'has_datasheet': [('1', sum(1 for product in items if product.datasheet_url))],
        'has_spice_model': [
            ('1', sum(1 for product in items if (product.parameters or {}).get('spice_model')))
        ],
        'has_cad_model': [
            (
                '1',
                sum(
                    1
                    for product in items
                    if (product.parameters or {}).get('cad_model_url')
                    or (product.parameters or {}).get('cad_model')
                ),
            )
        ],
    }


def facet_count(facets, group: str, key: str) -> int:
    for value, count in (facets or {}).get(group, []):
        if str(value) == str(key):
            return count
    return 0


def _search_products(products: list[Product], query: str) -> list[Product]:
    tokens = parse_query_tokens(query)
    if not tokens:
        return products

    range_tokens: list[RangeExpression] = []
    text_tokens = []
    for token in tokens:
        expression = parse_range_expression(token)
        if expression and (
            token[:1].upper() in RANGE_PREFIXES or any(op in token for op in ('<', '>', '..'))
        ):
            range_tokens.append(expression)
        else:
            text_tokens.append(token.lower())

    result = products
    for expression in range_tokens:
        result = [
            product
            for product in result
            if matches_engineering_filter(product, expression.filter_name, _expression_to_raw(expression))
        ]

    if text_tokens:
        strict = [
            product
            for product in result
            if all(token in _product_search_text(product) for token in text_tokens)
        ]
        if strict:
            return strict
        return _fuzzy_products(result, ' '.join(text_tokens))
    return result


def _fuzzy_products(products: list[Product], needle: str) -> list[Product]:
    try:
        from rapidfuzz import fuzz
    except Exception:
        return []
    scored = []
    for product in products[:1000]:
        score = fuzz.WRatio(needle, _product_search_text(product))
        if score >= 70:
            scored.append((score, product))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [product for _score, product in scored[:50]]


def _product_search_text(product: Product) -> str:
    params = product.parameters or {}
    pieces = [
        product.name,
        product.part_number,
        product.description,
        product.package_type,
        product.manufacturer,
        product.get_manufacturer_display(),
        product.category.name,
        product.category.slug,
    ]
    pieces.extend(str(value) for value in params.values() if value not in (None, ''))
    return ' '.join(str(piece or '') for piece in pieces).lower()


def _value_matches_expression(raw_value, expression: RangeExpression, key: str) -> bool:
    values = _extract_numeric_values(raw_value, expression.unit or KEY_UNITS.get(key, ''))
    if not values:
        return False
    if expression.low is not None and expression.high is not None:
        return any(expression.low <= value <= expression.high for value in values)
    if expression.value is None:
        return False
    if expression.op == '<':
        return any(value < expression.value for value in values)
    if expression.op == '<=':
        return any(value <= expression.value for value in values)
    if expression.op == '>':
        return any(value > expression.value for value in values)
    if expression.op == '>=':
        return any(value >= expression.value for value in values)
    return any(math.isclose(value, expression.value, rel_tol=0.03, abs_tol=1e-12) for value in values)


def _substring_or_numeric_match(product_value, raw_filter: str, key: str, filter_name: str) -> bool:
    expression = parse_range_expression(raw_filter, default_filter=filter_name)
    if expression:
        return _value_matches_expression(product_value, expression, key)
    return str(raw_filter).strip().lower() in str(product_value).lower()


def _extract_numeric_values(raw_value, expected_unit: str = '') -> list[float]:
    text = _normalize_text(raw_value)
    if not text:
        return []
    direct = parse_catalog_number(text, expected_unit)
    values = []
    if direct is not None:
        values.append(direct)

    unit_tail = ''
    tail_match = re.search(r'([A-Za-zА-Яа-яµΩОмВвВтФфГц%]+)\s*$', text)
    if tail_match:
        unit_tail = tail_match.group(1)
    for match in re.finditer(r'[-+]?\d+(?:[.,]\d+)?\s*(?:[A-Za-zА-Яа-яµΩ%]+)?', text):
        token = match.group(0).strip()
        if not re.search(r'[A-Za-zА-Яа-яµΩ%]', token) and unit_tail:
            token = f'{token}{unit_tail}'
        value = parse_catalog_number(token, expected_unit)
        if value is not None:
            values.append(value)

    deduped = []
    for value in values:
        if not any(math.isclose(value, existing, rel_tol=1e-12, abs_tol=1e-18) for existing in deduped):
            deduped.append(value)
    return deduped


def _default_unit(filter_name: str) -> str:
    return FILTER_UNITS.get(filter_name, '')


def _expression_to_raw(expression: RangeExpression) -> str:
    if expression.low is not None and expression.high is not None:
        return f'{expression.low}..{expression.high}'
    return f'{expression.op}{expression.value}'


def _normalize_text(raw) -> str:
    return str(raw or '').strip().replace('±', '').replace('−', '-').replace(',', '.')


def _copy_params(params) -> dict:
    if hasattr(params, 'lists'):
        result = {}
        for key, values in params.lists():
            if key == 'page':
                continue
            if not values:
                continue
            result[key] = values if len(values) > 1 else values[-1]
        return result
    return {key: value for key, value in dict(params or {}).items() if key != 'page'}


def _to_float(value) -> float | None:
    if value in (None, ''):
        return None
    try:
        return float(str(value).replace(',', '.'))
    except (TypeError, ValueError):
        return None


def _ordered_counts(values: Iterable[str]) -> list[tuple[str, int]]:
    counter = Counter(value for value in values if value)
    return counter.most_common()
