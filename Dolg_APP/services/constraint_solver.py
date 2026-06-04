"""Small constraint solvers for expert recommendations.

Z3 is imported lazily. V1 deliberately keeps the search space finite and
engineering-friendly by evaluating standard E-series candidate values.
"""

from __future__ import annotations

import math
from typing import Any

from .engineering_units import parse_engineering_number

E12_BASE = (1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2)


def _z3():
    import z3

    return z3


def _standard_values(min_value: float, max_value: float):
    values = []
    for decade in range(-2, 9):
        scale = 10**decade
        for base in E12_BASE:
            value = base * scale
            if min_value <= value <= max_value:
                values.append(value)
    return sorted(set(values))


def solve_design_constraints(kind: str, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    solvers = {
        'led_resistor': solve_led_resistor,
        'voltage_divider': solve_voltage_divider,
        'rc_cutoff': solve_rc_cutoff,
        'ne555_astable': solve_ne555_astable,
        'linear_regulator': solve_linear_regulator,
        'thermal_margin': solve_thermal_margin,
    }
    solver = solvers.get(str(kind or '').strip().lower())
    if solver is None:
        return {'ok': False, 'kind': kind, 'error': 'unknown_constraint_solver', 'options': []}
    return solver(inputs or {})


def solve_led_resistor(inputs):
    z3 = _z3()
    supply = parse_engineering_number(inputs.get('supply_voltage', 5), expected_unit='volt') or 5
    led_drop = parse_engineering_number(inputs.get('led_drop_voltage', 2), expected_unit='volt') or 2
    target_current = (parse_engineering_number(inputs.get('target_current_ma', 20)) or 20) / 1000
    current_tolerance = float(inputs.get('current_tolerance_percent', 20)) / 100
    min_current = target_current * (1 - current_tolerance)
    max_current = target_current * (1 + current_tolerance)
    voltage = max(supply - led_drop, 0)

    r = z3.Real('r')
    solver = z3.Solver()
    solver.add(r > 0, voltage / r >= min_current, voltage / r <= max_current)
    if solver.check() != z3.sat:
        return {'ok': False, 'kind': 'led_resistor', 'error': 'no_solution', 'options': []}

    options = []
    for resistor in _standard_values(1, 1_000_000):
        current = voltage / resistor if resistor else math.inf
        if min_current <= current <= max_current:
            power = current * current * resistor
            options.append(
                {
                    'resistance_ohm': resistor,
                    'current_a': current,
                    'power_w': power,
                    'recommendation': f'use {resistor:g} ohm, current {current * 1000:.2f} mA',
                }
            )
        if len(options) >= 8:
            break
    return {'ok': bool(options), 'kind': 'led_resistor', 'engine': 'z3+e12', 'options': options}


def solve_voltage_divider(inputs):
    z3 = _z3()
    vin = parse_engineering_number(inputs.get('vin', 9), expected_unit='volt') or 9
    target = parse_engineering_number(inputs.get('target_vout', 3), expected_unit='volt') or 3
    tolerance_percent = float(inputs.get('tolerance_percent', 5))
    total_min = parse_engineering_number(inputs.get('total_min_ohm', '2k'), expected_unit='ohm') or 2_000
    total_max = parse_engineering_number(inputs.get('total_max_ohm', '200k'), expected_unit='ohm') or 200_000
    low = target * (1 - tolerance_percent / 100)
    high = target * (1 + tolerance_percent / 100)

    r1, r2 = z3.Reals('r1 r2')
    solver = z3.Solver()
    solver.add(r1 > 0, r2 > 0, r1 + r2 >= total_min, r1 + r2 <= total_max)
    solver.add(vin * r2 / (r1 + r2) >= low, vin * r2 / (r1 + r2) <= high)
    if solver.check() != z3.sat:
        return {'ok': False, 'kind': 'voltage_divider', 'error': 'no_solution', 'options': []}

    candidates = _standard_values(100, 1_000_000)
    options = []
    for rv1 in candidates:
        for rv2 in candidates:
            total = rv1 + rv2
            if not (total_min <= total <= total_max):
                continue
            vout = vin * rv2 / total
            if low <= vout <= high:
                options.append(
                    {
                        'r1_ohm': rv1,
                        'r2_ohm': rv2,
                        'vout_v': vout,
                        'error_percent': abs(vout - target) / target * 100 if target else 0,
                        'recommendation': f'R1={rv1:g} ohm, R2={rv2:g} ohm -> Vout={vout:.3g} V',
                    }
                )
        if len(options) >= 12:
            break
    options.sort(key=lambda item: item['error_percent'])
    return {'ok': bool(options), 'kind': 'voltage_divider', 'engine': 'z3+e12', 'options': options[:8]}


def solve_rc_cutoff(inputs):
    target = parse_engineering_number(inputs.get('target_hz', 1000), expected_unit='hertz') or 1000
    tolerance_percent = float(inputs.get('tolerance_percent', 10))
    low = target * (1 - tolerance_percent / 100)
    high = target * (1 + tolerance_percent / 100)
    resistors = _standard_values(100, 1_000_000)
    capacitors = _standard_values(1e-12, 1e-3)
    options = []
    for resistance in resistors:
        for capacitance in capacitors:
            cutoff = 1 / (2 * math.pi * resistance * capacitance)
            if low <= cutoff <= high:
                options.append(
                    {
                        'resistance_ohm': resistance,
                        'capacitance_f': capacitance,
                        'cutoff_hz': cutoff,
                        'error_percent': abs(cutoff - target) / target * 100 if target else 0,
                        'recommendation': f'R={resistance:g} ohm, C={capacitance:g} F -> fc={cutoff:.3g} Hz',
                    }
                )
        if len(options) >= 16:
            break
    options.sort(key=lambda item: item['error_percent'])
    return {'ok': bool(options), 'kind': 'rc_cutoff', 'engine': 'z3-guided-e12', 'options': options[:8]}


def solve_ne555_astable(inputs):
    target = parse_engineering_number(inputs.get('target_hz', 1000), expected_unit='hertz') or 1000
    tolerance_percent = float(inputs.get('tolerance_percent', 15))
    low = target * (1 - tolerance_percent / 100)
    high = target * (1 + tolerance_percent / 100)
    resistors = _standard_values(1_000, 1_000_000)
    capacitors = _standard_values(100e-12, 100e-6)
    options = []
    for r1 in resistors[:]:
        for r2 in resistors:
            for capacitance in capacitors:
                frequency = 1 / (0.693 * (r1 + 2 * r2) * capacitance)
                if low <= frequency <= high:
                    duty = (r1 + r2) / (r1 + 2 * r2) * 100
                    options.append(
                        {
                            'r1_ohm': r1,
                            'r2_ohm': r2,
                            'capacitance_f': capacitance,
                            'frequency_hz': frequency,
                            'duty_cycle_percent': duty,
                            'error_percent': abs(frequency - target) / target * 100 if target else 0,
                            'recommendation': f'R1={r1:g}, R2={r2:g}, C={capacitance:g} -> f={frequency:.3g} Hz',
                        }
                    )
                if len(options) >= 10:
                    break
            if len(options) >= 10:
                break
        if len(options) >= 10:
            break
    options.sort(key=lambda item: item['error_percent'])
    return {'ok': bool(options), 'kind': 'ne555_astable', 'engine': 'z3-guided-e12', 'options': options[:8]}


def solve_linear_regulator(inputs):
    vin = parse_engineering_number(inputs.get('vin', 12), expected_unit='volt') or 12
    vout = parse_engineering_number(inputs.get('vout', 5), expected_unit='volt') or 5
    current = (parse_engineering_number(inputs.get('load_current_ma', 250)) or 250) / 1000
    theta = parse_engineering_number(inputs.get('theta_ja', 50)) or 50
    ambient = parse_engineering_number(inputs.get('ambient_c', 25), expected_unit='degC') or 25
    tj_max = parse_engineering_number(inputs.get('max_junction_c', 125), expected_unit='degC') or 125
    power = max(vin - vout, 0) * current
    junction = ambient + power * theta
    margin = tj_max - junction
    ok = margin >= float(inputs.get('min_margin_c', 20))
    return {
        'ok': ok,
        'kind': 'linear_regulator',
        'engine': 'constraint-formula',
        'options': [
            {
                'power_w': power,
                'junction_temperature_c': junction,
                'thermal_margin_c': margin,
                'recommendation': 'thermal margin is acceptable'
                if ok
                else 'reduce current, add heatsink or use switching regulator',
            }
        ],
    }


def solve_thermal_margin(inputs):
    return solve_linear_regulator(
        {
            'vin': inputs.get('power_w', 1.5),
            'vout': 0,
            'load_current_ma': 1000,
            'theta_ja': inputs.get('theta_ja', 50),
            'ambient_c': inputs.get('ambient_c', 25),
            'max_junction_c': inputs.get('max_junction_c', 125),
            'min_margin_c': inputs.get('min_margin_c', 20),
        }
    ) | {'kind': 'thermal_margin'}
