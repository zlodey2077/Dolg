"""Validation helpers shared by schematic DRC and BOM matching."""

from __future__ import annotations

import math
import re
from typing import Any

FIELD_UNIT_TO_SI = {
    'resistance': 1,
    'capacitance': 1e-6,
    'inductance': 1e-3,
    'voltage': 1,
}

NOMINAL_FIELD_BY_TYPE = {
    'resistor': 'resistance',
    'capacitor': 'capacitance',
    'inductor': 'inductance',
    'battery': 'voltage',
    'voltage_source': 'voltage',
}

PRODUCT_NOMINAL_KEYS = {
    'resistance': ('resistance', 'value', 'nominal', 'resistor_value'),
    'capacitance': ('capacitance', 'value', 'nominal', 'capacitor_value'),
    'inductance': ('inductance', 'value', 'nominal', 'inductor_value'),
    'voltage': ('voltage', 'value', 'nominal', 'rated_voltage'),
}

SI_SUFFIX_MULT = {
    'f': 1e-15,
    'p': 1e-12,
    'n': 1e-9,
    'u': 1e-6,
    'm': 1e-3,
    '': 1,
    'k': 1e3,
    'M': 1e6,
    'G': 1e9,
    'T': 1e12,
}

CYRILLIC_SUFFIXES = {
    'к': 'k',
    'К': 'k',
    'М': 'M',
    'м': 'm',
    'н': 'n',
    'Н': 'n',
    'п': 'p',
    'П': 'p',
}

SPICE_MODEL_REQUIRED_TYPES = {'diode', 'led', 'transistor', 'npn', 'pnp', 'ic'}


def component_nominal_field(component: dict[str, Any]) -> str | None:
    return NOMINAL_FIELD_BY_TYPE.get((component.get('type') or '').strip().lower())


def parse_engineering_value(field: str, raw: Any) -> float | None:
    """Parse editor/product values into the editor field unit.

    For example, resistance is stored in Ohm, capacitance in microfarads and
    inductance in millihenries, matching the browser editor.
    """

    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if math.isfinite(float(raw)) else None

    text = str(raw).strip().replace(',', '.').replace('µ', 'u').replace('μ', 'u')
    text = re.sub(r'\s+', '', text)
    text = text.replace('мк', 'u').replace('МК', 'u').replace('Мк', 'u')
    if not text:
        return None

    match = re.match(r'^(-?\d*\.?\d+(?:[eE][+-]?\d+)?)([fpnumkKMGTкКМмпПнН]?)(.*)$', text)
    if not match:
        return None

    number = float(match.group(1))
    suffix = CYRILLIC_SUFFIXES.get(match.group(2), match.group(2))
    if suffix not in SI_SUFFIX_MULT:
        suffix = ''

    if not suffix:
        return number
    si_value = number * SI_SUFFIX_MULT[suffix]
    return si_value / FIELD_UNIT_TO_SI.get(field, 1)


def product_nominal_value(product: Any, field: str) -> Any:
    params = getattr(product, 'parameters', None) or {}
    for key in PRODUCT_NOMINAL_KEYS.get(field, ()):
        value = params.get(key)
        if value not in (None, ''):
            return value
    return None


def nominal_mismatch_warning(component: dict[str, Any], product: Any) -> str:
    field = component_nominal_field(component)
    if not field or product is None:
        return ''

    component_raw = component.get(field)
    product_raw = product_nominal_value(product, field)
    component_value = parse_engineering_value(field, component_raw)
    product_value = parse_engineering_value(field, product_raw)
    if component_value is None or product_value is None:
        return ''

    scale = max(abs(component_value), abs(product_value), 1e-12)
    if abs(component_value - product_value) / scale <= 0.05:
        return ''

    ref = getattr(product, 'part_number', '') or getattr(product, 'slug', '') or getattr(product, 'name', '')
    return f'номинал схемы ({component_raw}) отличается от товара "{ref}" ({product_raw})'


def missing_spice_model_warning(component: dict[str, Any], product: Any | None = None) -> str:
    component_type = (component.get('type') or '').strip().lower()
    if component_type not in SPICE_MODEL_REQUIRED_TYPES:
        return ''

    component_model = (component.get('spice_model') or '').strip()
    product_params = getattr(product, 'parameters', None) or {}
    product_model = (
        product_params.get('spice_model') or product_params.get('model') or product_params.get('spice') or ''
    )
    if component_model or str(product_model).strip():
        return ''
    return f'для компонента типа {component_type} не задана SPICE-модель'


def unique_warnings(messages: list[str]) -> list[str]:
    seen = set()
    result = []
    for message in messages:
        if message and message not in seen:
            result.append(message)
            seen.add(message)
    return result
