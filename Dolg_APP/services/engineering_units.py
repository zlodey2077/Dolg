"""Unit-safe engineering number parsing.

Pint is imported lazily so Django startup and simple views stay light. The
helpers keep DOLG's existing engineering suffix behavior (`10k`, `100n`) and
add unit conversion for expert rules, review, lab and learning checks.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

PREFIX_FACTORS = {
    'p': 1e-12,
    'n': 1e-9,
    'u': 1e-6,
    'µ': 1e-6,
    'm': 1e-3,
    'k': 1e3,
    'meg': 1e6,
    'g': 1e9,
    'п': 1e-12,
    'н': 1e-9,
    'мк': 1e-6,
    'м': 1e-3,
    'к': 1e3,
    'мег': 1e6,
    'г': 1e9,
}

UNIT_ALIASES = {
    '': '',
    'v': 'volt',
    'volt': 'volt',
    'volts': 'volt',
    'в': 'volt',
    'a': 'ampere',
    'amp': 'ampere',
    'amps': 'ampere',
    'а': 'ampere',
    'ohm': 'ohm',
    'r': 'ohm',
    'Ω': 'ohm',
    'omega': 'ohm',
    'ом': 'ohm',
    'ω': 'ohm',
    'f': 'farad',
    'farad': 'farad',
    'ф': 'farad',
    'hz': 'hertz',
    'hertz': 'hertz',
    'гц': 'hertz',
    'w': 'watt',
    'watt': 'watt',
    'вт': 'watt',
    's': 'second',
    'sec': 'second',
    'second': 'second',
    'с': 'second',
    'c': 'degC',
    'degc': 'degC',
    '°c': 'degC',
}


DIRECT_SUFFIXES = {
    'v': ('volt', 1.0),
    'в': ('volt', 1.0),
    'mv': ('volt', 1e-3),
    'мв': ('volt', 1e-3),
    'kv': ('volt', 1e3),
    'кв': ('volt', 1e3),
    'a': ('ampere', 1.0),
    'а': ('ampere', 1.0),
    'ma': ('ampere', 1e-3),
    'ма': ('ampere', 1e-3),
    'ua': ('ampere', 1e-6),
    'uа': ('ampere', 1e-6),
    'мка': ('ampere', 1e-6),
    'ohm': ('ohm', 1.0),
    'ом': ('ohm', 1.0),
    'ω': ('ohm', 1.0),
    'kohm': ('ohm', 1e3),
    'kω': ('ohm', 1e3),
    'ком': ('ohm', 1e3),
    'mohm': ('ohm', 1e6),
    'мом': ('ohm', 1e6),
    'hz': ('hertz', 1.0),
    'гц': ('hertz', 1.0),
    'khz': ('hertz', 1e3),
    'кгц': ('hertz', 1e3),
    'mhz': ('hertz', 1e6),
    'мгц': ('hertz', 1e6),
    'w': ('watt', 1.0),
    'вт': ('watt', 1.0),
    'mw': ('watt', 1e-3),
    'мвт': ('watt', 1e-3),
    'f': ('farad', 1.0),
    'ф': ('farad', 1.0),
    'uf': ('farad', 1e-6),
    'uф': ('farad', 1e-6),
    'мкф': ('farad', 1e-6),
    'nf': ('farad', 1e-9),
    'нф': ('farad', 1e-9),
    'pf': ('farad', 1e-12),
    'пф': ('farad', 1e-12),
    's': ('second', 1.0),
    'с': ('second', 1.0),
    'ms': ('second', 1e-3),
    'мс': ('second', 1e-3),
    'us': ('second', 1e-6),
    'uс': ('second', 1e-6),
    'мкс': ('second', 1e-6),
}


@dataclass(frozen=True)
class ParsedQuantity:
    ok: bool
    value: float | None
    unit: str = ''
    source: str = ''
    warning: str = ''
    error: str = ''


@lru_cache(maxsize=1)
def _ureg():
    import pint

    registry = pint.UnitRegistry(autoconvert_offset_to_baseunit=True)
    return registry


def canonical_unit(unit: str | None) -> str:
    raw = str(unit or '').strip().lower()
    raw = raw.replace('ω', 'Ω').replace('ohms', 'ohm').replace('Ω', 'Ω')
    return UNIT_ALIASES.get(raw, raw)


def parse_engineering_quantity(value: Any, expected_unit: str = '', default: float | None = None) -> ParsedQuantity:
    if value is None or isinstance(value, bool):
        if default is None:
            return ParsedQuantity(False, None, canonical_unit(expected_unit), source=str(value), error='empty value')
        return ParsedQuantity(True, float(default), canonical_unit(expected_unit), source=str(value), warning='default used')

    if isinstance(value, (int, float)):
        number = float(value)
        if math.isfinite(number):
            return ParsedQuantity(True, number, canonical_unit(expected_unit), source=str(value))
        return ParsedQuantity(False, default, canonical_unit(expected_unit), source=str(value), error='not finite')

    text = str(value).strip()
    if not text:
        return ParsedQuantity(False, default, canonical_unit(expected_unit), source=text, error='empty value')

    parsed = _parse_suffix_value(text, expected_unit)
    if parsed.ok:
        return parsed

    parsed = _parse_with_pint(text, expected_unit)
    if parsed.ok:
        return parsed

    return ParsedQuantity(False, default, canonical_unit(expected_unit), source=text, error=parsed.error or 'not a number')


def parse_engineering_number(value: Any, default: float | None = None, expected_unit: str = '') -> float | None:
    parsed = parse_engineering_quantity(value, expected_unit=expected_unit, default=default)
    return parsed.value if parsed.ok else default


def unit_warning(value: Any, expected_unit: str = '') -> str:
    parsed = parse_engineering_quantity(value, expected_unit=expected_unit)
    return parsed.warning


def _parse_suffix_value(text: str, expected_unit: str = '') -> ParsedQuantity:
    compact = text.strip().lower().replace(',', '.').replace(' ', '')
    compact = compact.replace('µ', 'u').replace('ω', 'ohm').replace('Ω', 'ohm')
    match = re.fullmatch(r'([-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?)([\w°О©Ωа-яА-Я]*)', compact)
    if not match:
        return ParsedQuantity(False, None, canonical_unit(expected_unit), source=text, error='suffix parser miss')

    number = float(match.group(1))
    suffix = match.group(2) or ''
    expected = canonical_unit(expected_unit)
    unit = expected
    factor = 1.0

    if suffix:
        token = suffix
        direct = DIRECT_SUFFIXES.get(token)
        if direct:
            unit, factor = direct
        else:
            for prefix in sorted(PREFIX_FACTORS, key=len, reverse=True):
                if token.startswith(prefix):
                    rest = token[len(prefix):]
                    if not rest:
                        factor = PREFIX_FACTORS[prefix]
                        unit = expected
                        break
                    if canonical_unit(rest):
                        factor = PREFIX_FACTORS[prefix]
                        unit = canonical_unit(rest)
                        break
            else:
                unit = canonical_unit(token)

    if expected and unit and unit != expected:
        converted = _convert_with_pint(number * factor, unit, expected)
        if converted is not None:
            return ParsedQuantity(True, converted, expected, source=text)
    elif suffix:
        return ParsedQuantity(True, number * factor, expected or unit, source=text)

    warning = ''
    if expected == 'ohm' and suffix == '' and 1 <= abs(number) <= 99:
        warning = 'Value has no engineering prefix; check if you meant kOhm.'
    return ParsedQuantity(True, number, expected or unit, source=text, warning=warning)


def _parse_with_pint(text: str, expected_unit: str = '') -> ParsedQuantity:
    expected = canonical_unit(expected_unit)
    normalized = text.replace('Ω', 'ohm').replace('Ω', 'ohm').replace('µ', 'u')
    try:
        quantity = _ureg().Quantity(normalized)
        if expected:
            quantity = quantity.to(expected)
        magnitude = float(quantity.magnitude)
    except Exception as exc:
        return ParsedQuantity(False, None, expected, source=text, error=str(exc))
    if not math.isfinite(magnitude):
        return ParsedQuantity(False, None, expected, source=text, error='not finite')
    return ParsedQuantity(True, magnitude, expected or str(quantity.units), source=text)


def _convert_with_pint(number: float, unit: str, expected: str) -> float | None:
    try:
        return float((_ureg().Quantity(number, unit)).to(expected).magnitude)
    except Exception:
        return None
