"""Symbolic formula helpers for learning feedback.

The numeric laboratory remains the source of truth for calculators. This module
adds SymPy-backed explanation and equivalence checks for practice tasks.
"""

from __future__ import annotations

import math


def _sympy():
    import sympy as sp

    return sp


def _float(value, default=0.0):
    try:
        number = float(value)
    except TypeError, ValueError:
        return default
    return number if math.isfinite(number) else default


def _formula_payload(kind, inputs):
    sp = _sympy()
    data = inputs or {}

    if kind == 'ohms_law_current':
        voltage = _float(data.get('voltage_v', data.get('voltage', 0)))
        resistance = _float(data.get('resistance_ohm', data.get('resistance', 1)), 1)
        expected = voltage / resistance if resistance else 0
        return {
            'unit': 'A',
            'symbols': ('V', 'R'),
            'expression': sp.Symbol('V') / sp.Symbol('R'),
            'values': {'V': voltage, 'R': resistance},
            'expected_value': expected,
            'steps': [
                'Закон Ома для тока: I = V / R.',
                f'Подставляем: I = {voltage:g} / {resistance:g}.',
                f'Получаем: I = {expected:g} A.',
            ],
        }

    if kind == 'voltage_divider':
        vin = _float(data.get('vin', data.get('voltage_v', 0)))
        r1 = _float(data.get('r1_ohm', data.get('r1', 1)), 1)
        r2 = _float(data.get('r2_ohm', data.get('r2', 1)), 1)
        expected = vin * r2 / (r1 + r2) if r1 + r2 else 0
        return {
            'unit': 'V',
            'symbols': ('Vin', 'R1', 'R2'),
            'expression': sp.Symbol('Vin') * sp.Symbol('R2') / (sp.Symbol('R1') + sp.Symbol('R2')),
            'values': {'Vin': vin, 'R1': r1, 'R2': r2},
            'expected_value': expected,
            'steps': [
                'Делитель напряжения: Vout = Vin * R2 / (R1 + R2).',
                f'Подставляем: Vout = {vin:g} * {r2:g} / ({r1:g} + {r2:g}).',
                f'Получаем: Vout = {expected:g} V.',
            ],
        }

    if kind == 'power':
        voltage = _float(data.get('voltage_v', data.get('voltage', 0)))
        current = _float(data.get('current_a', data.get('current', 0)))
        expected = voltage * current
        return {
            'unit': 'W',
            'symbols': ('V', 'I'),
            'expression': sp.Symbol('V') * sp.Symbol('I'),
            'values': {'V': voltage, 'I': current},
            'expected_value': expected,
            'steps': [
                'Мощность: P = V * I.',
                f'Подставляем: P = {voltage:g} * {current:g}.',
                f'Получаем: P = {expected:g} W.',
            ],
        }

    if kind == 'rc_cutoff':
        resistance = _float(data.get('resistance_ohm', data.get('r', 1)), 1)
        capacitance = _float(data.get('capacitance_f', data.get('c', 1e-6)), 1e-6)
        expected = 1 / (2 * math.pi * resistance * capacitance) if resistance and capacitance else 0
        return {
            'unit': 'Hz',
            'symbols': ('R', 'C'),
            'expression': 1 / (2 * sp.pi * sp.Symbol('R') * sp.Symbol('C')),
            'values': {'R': resistance, 'C': capacitance},
            'expected_value': expected,
            'steps': [
                'Частота среза RC-фильтра: fc = 1 / (2πRC).',
                f'Подставляем: fc = 1 / (2π * {resistance:g} * {capacitance:g}).',
                f'Получаем: fc = {expected:g} Hz.',
            ],
        }

    if kind == 'ne555_astable':
        r1 = _float(data.get('r1_ohm', data.get('r1', 1)), 1)
        r2 = _float(data.get('r2_ohm', data.get('r2', 1)), 1)
        capacitance = _float(data.get('capacitance_f', data.get('c', 1e-6)), 1e-6)
        expected = 1.44 / ((r1 + 2 * r2) * capacitance) if capacitance and (r1 + 2 * r2) else 0
        return {
            'unit': 'Hz',
            'symbols': ('R1', 'R2', 'C'),
            'expression': 1.44 / ((sp.Symbol('R1') + 2 * sp.Symbol('R2')) * sp.Symbol('C')),
            'values': {'R1': r1, 'R2': r2, 'C': capacitance},
            'expected_value': expected,
            'steps': [
                'Для NE555 astable: f ≈ 1.44 / ((R1 + 2R2) * C).',
                f'Подставляем: f = 1.44 / (({r1:g} + 2 * {r2:g}) * {capacitance:g}).',
                f'Получаем: f = {expected:g} Hz.',
            ],
        }

    raise ValueError(f'Unknown formula kind: {kind}')


def explain_formula(kind, inputs=None):
    payload = _formula_payload(kind, inputs or {})
    return {
        'kind': kind,
        'unit': payload['unit'],
        'expected_value': payload['expected_value'],
        'steps': payload['steps'],
        'values': payload['values'],
    }


def formula_expected_value(config):
    config = config or {}
    return explain_formula(config.get('kind'), config.get('inputs') or {}).get('expected_value')


def check_equivalent_expression(kind, expression, *, variables=None, inputs=None):
    sp = _sympy()
    payload = _formula_payload(kind, inputs or {})
    allowed_names = {name: sp.Symbol(name) for name in (variables or payload['symbols'])}
    try:
        candidate = sp.sympify(expression, locals=allowed_names)
    except Exception as exc:
        return {
            'correct': False,
            'feedback': f'Не удалось разобрать выражение: {exc}',
        }

    expected = payload['expression']
    try:
        equivalent = sp.simplify(candidate - expected) == 0
    except Exception:
        equivalent = False

    return {
        'correct': bool(equivalent),
        'feedback': 'Формула эквивалентна эталону.' if equivalent else 'Формула не эквивалентна эталону.',
        'expected_expression': str(expected),
        'candidate_expression': str(candidate),
    }
