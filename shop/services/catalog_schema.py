"""Per-category catalog parameter schema + coverage audit.

Единое место, где описано, какие параметры карточки ожидаются для каждой
категории РЭБ-компонентов: `required` (определяющие, должны быть всегда) и
`recommended` (повышают качество, частично заполнены). Дополняет минимальный
`REQUIRED_REB_KEYS` из check_data_integrity осмысленным набором, выверенным по
реальным ключам каталога (не выдуманным — иначе аудит давал бы ложные «missing»).

Параметр считается «присутствующим», если ключ есть в `product.parameters` с
непустым значением ИЛИ у продукта заполнено одноимённое модельное поле.
"""

from __future__ import annotations

from typing import Any

# slug категории → набор параметров. Ключи выверены по фактическому каталогу.
CATEGORY_SCHEMAS: dict[str, dict[str, list[str]]] = {
    'resistors': {
        'required': ['resistance', 'power', 'tolerance', 'mounting'],
        'recommended': ['type', 'material', 'temp_coef', 'max_voltage'],
    },
    'capacitors': {
        'required': ['capacitance', 'voltage', 'mounting'],
        'recommended': ['tolerance', 'dielectric', 'max_temp', 'type'],
    },
    'transistors': {
        'required': ['type', 'max_voltage', 'current', 'mounting'],
        'recommended': ['pins', 'hfe', 'rds_on', 'ft', 'power'],
    },
    'ics': {
        'required': ['type', 'mounting'],
        'recommended': ['pins', 'supply_voltage', 'family', 'channels'],
    },
    'diodes': {
        'required': ['type', 'mounting'],
        'recommended': ['vf', 'current', 'max_current', 'max_voltage'],
    },
    'inductors': {
        'required': ['inductance', 'current', 'mounting'],
        'recommended': ['dcr', 'type', 'srf', 'tolerance'],
    },
    'connectors': {
        'required': ['type', 'current', 'mounting'],
        'recommended': ['pins', 'orientation', 'pitch', 'gender', 'contact_material'],
    },
    'relays': {
        'required': ['type', 'coil_voltage', 'current', 'mounting'],
        'recommended': ['contact_rating', 'configuration'],
    },
}

# Структурные (модельные) поля, ожидаемые у инженерного компонента.
STRUCTURAL_FIELDS = ('part_number', 'package_type', 'datasheet_url')


def schema_for_category(slug: str) -> dict[str, list[str]] | None:
    return CATEGORY_SCHEMAS.get(slug)


def _param_present(product: Any, key: str) -> bool:
    """Ключ заполнен в parameters (непустым) ИЛИ есть одноимённое модельное поле."""
    params = product.parameters if isinstance(getattr(product, 'parameters', None), dict) else {}
    val = params.get(key)
    if val not in (None, '', [], {}):
        return True
    attr = getattr(product, key, None)
    return attr not in (None, '', [], {})


def audit_product(product: Any) -> dict[str, Any] | None:
    """Аудит одного продукта против схемы его категории.

    Returns None, если для категории нет схемы (consumer-категории). Иначе —
    отчёт с недостающими required/recommended и метрикой coverage (доля
    присутствующих параметров от всех ожидаемых).
    """
    slug = getattr(getattr(product, 'category', None), 'slug', None)
    schema = CATEGORY_SCHEMAS.get(slug or '')
    if not schema:
        return None

    required = schema.get('required', [])
    recommended = schema.get('recommended', [])
    missing_required = [k for k in required if not _param_present(product, k)]
    missing_recommended = [k for k in recommended if not _param_present(product, k)]
    missing_structural = [f for f in STRUCTURAL_FIELDS if not getattr(product, f, None)]

    expected = len(required) + len(recommended)
    present = expected - len(missing_required) - len(missing_recommended)
    coverage = round(present / expected, 3) if expected else 1.0

    return {
        'slug': getattr(product, 'slug', None),
        'category': slug,
        'part_number': getattr(product, 'part_number', '') or '',
        'missing_required': missing_required,
        'missing_recommended': missing_recommended,
        'missing_structural': missing_structural,
        'coverage': coverage,
        'ok': not missing_required and not missing_structural,
    }


def audit_catalog(queryset=None) -> dict[str, Any]:
    """Сводный аудит каталога по категориям со схемой.

    Returns: {
        'categories': {slug: {products, full_ok, avg_coverage, missing_required_products,
                              recommended_gaps: {key: count}}},
        'totals': {products, full_ok, avg_coverage},
    }
    """
    from shop.models import Product

    if queryset is None:
        queryset = Product.objects.select_related('category').filter(
            category__slug__in=CATEGORY_SCHEMAS.keys()
        )

    cats: dict[str, dict[str, Any]] = {}
    total_products = 0
    total_ok = 0
    total_coverage = 0.0

    for product in queryset:
        report = audit_product(product)
        if report is None:
            continue
        slug = report['category']
        bucket = cats.setdefault(
            slug,
            {
                'products': 0,
                'full_ok': 0,
                'coverage_sum': 0.0,
                'missing_required_products': 0,
                'recommended_gaps': {},
                'required_gaps': {},
            },
        )
        bucket['products'] += 1
        bucket['coverage_sum'] += report['coverage']
        if report['ok']:
            bucket['full_ok'] += 1
        if report['missing_required']:
            bucket['missing_required_products'] += 1
            for key in report['missing_required']:
                bucket['required_gaps'][key] = bucket['required_gaps'].get(key, 0) + 1
        for key in report['missing_recommended']:
            bucket['recommended_gaps'][key] = bucket['recommended_gaps'].get(key, 0) + 1

        total_products += 1
        total_coverage += report['coverage']
        if report['ok']:
            total_ok += 1

    for bucket in cats.values():
        count = bucket['products'] or 1
        bucket['avg_coverage'] = round(bucket.pop('coverage_sum') / count, 3)
        bucket['recommended_gaps'] = dict(sorted(bucket['recommended_gaps'].items(), key=lambda kv: -kv[1]))
        bucket['required_gaps'] = dict(sorted(bucket['required_gaps'].items(), key=lambda kv: -kv[1]))

    return {
        'categories': dict(sorted(cats.items())),
        'totals': {
            'products': total_products,
            'full_ok': total_ok,
            'avg_coverage': round(total_coverage / total_products, 3) if total_products else 1.0,
        },
    }
