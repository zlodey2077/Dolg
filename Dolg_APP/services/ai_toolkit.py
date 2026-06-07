"""Toolkit локального AI-ассистента: вызывает инженерные движки и возвращает
готовые строки + источник для вшивания в ответ rule_ai.

Принцип «compute-don't-guess»: число берётся из реального движка (MNA, Monte
Carlo, P=U²/R), а не выдумывается языковой моделью. Полностью self-hosted —
никаких внешних API. Каждый блок помечает источник (expert-first).
"""

from __future__ import annotations

from typing import Any


def compute_dc(scheme_data: dict | None) -> dict[str, Any]:
    """DC-решение схемы через NumPy MNA. {ok, voltages, currents, source} либо {ok:False}."""
    try:
        from .monte_carlo import scheme_to_circuit, solve_dc

        circuit = scheme_to_circuit(scheme_data or {})
        if circuit['n_nodes'] <= 1 or not circuit['elements']:
            return {'ok': False, 'reason': 'no_circuit'}
        result = solve_dc(circuit)
        return {
            'ok': True,
            'voltages': result['voltages'],
            'currents': result['currents'],
            'circuit': circuit,
            'source': 'MNA (NumPy solve_dc)',
        }
    except Exception as exc:
        return {'ok': False, 'reason': str(exc)}


def dc_voltage_lines(scheme_data: dict | None, *, limit: int = 6) -> list[str]:
    """Строки с реальными напряжениями узлов + токами источников (DC)."""
    dc = compute_dc(scheme_data)
    if not dc['ok']:
        return []
    lines = [f'узел {net}: {v:.3f} В' for net, v in sorted(dc['voltages'].items()) if net != 0]
    lines = lines[:limit]
    for vid, current in (dc['currents'] or {}).items():
        lines.append(f'ток через {vid}: {current * 1000:.2f} мА')
    if lines:
        lines.append(f'источник: {dc["source"]}')
    return lines


def power_lines(scheme_data: dict | None, *, limit: int = 6) -> list[str]:
    """Рассеиваемая мощность на резисторах из DC-решения: P = ΔU²/R."""
    dc = compute_dc(scheme_data)
    if not dc['ok']:
        return []
    voltages = dc['voltages']
    rows: list[tuple[str, float]] = []
    for elem in dc['circuit']['elements']:
        if elem['type'] != 'R' or elem['value'] <= 0:
            continue
        n1, n2 = elem['nodes']
        delta = abs(voltages.get(n1, 0.0) - voltages.get(n2, 0.0))
        power = delta * delta / elem['value']
        rows.append((str(elem['id']), power))
    if not rows:
        return []
    rows.sort(key=lambda item: -item[1])
    lines = []
    for rid, power in rows[:limit]:
        lines.append(f'{rid}: {power * 1000:.1f} мВт' if power < 1 else f'{rid}: {power:.2f} Вт')
    lines.append('источник: P = ΔU²/R по DC-решению (MNA)')
    return lines


def _components(scheme_data: dict | None):
    return (scheme_data or {}).get('components') or []


def _first_of(scheme_data: dict | None, ctype: str):
    return next((c for c in _components(scheme_data) if (c.get('type') or '').lower() == ctype), None)


def formula_compute(scheme_data: dict | None, topology: str | None) -> list[str]:
    """Считает формулу по реальным значениям схемы (Vout / fc / Iled).

    Compute-don't-guess: число берётся из движка/арифметики по номиналам, а не
    из текста. Пустой список, если данных не хватает."""
    import math

    from shop.component_validation import parse_engineering_value

    lines: list[str] = []
    if topology == 'voltage_divider':
        dc = compute_dc(scheme_data)
        if dc['ok']:
            node_v = [f'{v:.3f} В' for net, v in sorted(dc['voltages'].items()) if net != 0]
            if node_v:
                lines.append('Vout = Vin·R2/(R1+R2); напряжения узлов (MNA): ' + ', '.join(node_v))
                lines.append('источник: MNA (NumPy solve_dc)')
    elif topology == 'rc_network':
        r = _first_of(scheme_data, 'resistor')
        c = _first_of(scheme_data, 'capacitor')
        if r and c:
            r_ohm = parse_engineering_value('resistance', r.get('resistance') or r.get('value'))
            c_uf = parse_engineering_value('capacitance', c.get('capacitance') or c.get('value'))
            if r_ohm and c_uf and r_ohm > 0 and c_uf > 0:
                fc = 1.0 / (2 * math.pi * r_ohm * (c_uf * 1e-6))
                lines.append(f'fc = 1/(2π·R·C) ≈ {fc:,.1f} Гц (R={r_ohm:g} Ом, C={c_uf:g} мкФ)')
                lines.append('источник: расчёт по номиналам (точка −3 дБ)')
    elif topology == 'led_indicator':
        b = _first_of(scheme_data, 'battery')
        led = _first_of(scheme_data, 'led')
        r = _first_of(scheme_data, 'resistor')
        if b and led and r:
            vin = parse_engineering_value('voltage', b.get('voltage') or b.get('value'))
            vf = parse_engineering_value('voltage', led.get('vf') or led.get('forward_voltage') or 2)
            r_ohm = parse_engineering_value('resistance', r.get('resistance') or r.get('value'))
            if vin and vf is not None and r_ohm and r_ohm > 0 and vin > vf:
                iled = (vin - vf) / r_ohm
                lines.append(
                    f'Iled = (Vin−Vf)/R ≈ {iled * 1000:.1f} мА (Vin={vin:g}В, Vf={vf:g}В, R={r_ohm:g}Ом)'
                )
                lines.append('источник: закон Ома по номиналам')
    return lines


def rf_filter_lines(scheme_data: dict | None) -> list[str]:
    """S-параметры RC-фильтра через scikit-rf: частота среза −3 дБ + полоса.

    Только если в схеме есть резистор и конденсатор. Compute-don't-guess."""
    from shop.component_validation import parse_engineering_value

    r = _first_of(scheme_data, 'resistor')
    c = _first_of(scheme_data, 'capacitor')
    if not (r and c):
        return []
    r_ohm = parse_engineering_value('resistance', r.get('resistance') or r.get('value'))
    c_uf = parse_engineering_value('capacitance', c.get('capacitance') or c.get('value'))
    if not (r_ohm and c_uf and r_ohm > 0 and c_uf > 0):
        return []
    try:
        from .rf_analysis import analyze_filter

        result = analyze_filter('rc_lowpass', r_ohm=r_ohm, c_farad=c_uf * 1e-6)
    except Exception:
        return []
    cutoff = result.get('cutoff_3db_hz')
    lines = []
    if cutoff:
        lines.append(f'RC low-pass: срез −3 дБ ≈ {cutoff:,.0f} Гц (нагруженный, 50 Ом)')
    if result.get('analytic_corner_hz'):
        lines.append(f'ненагруженный угол 1/(2πRC) ≈ {result["analytic_corner_hz"]:,.0f} Гц')
    lines.append(f'полоса пропускания (S21): {result.get("passband_db", 0):.1f} дБ')
    lines.append('источник: scikit-rf S-параметры (2-порт)')
    return lines


def tolerance_lines(scheme_data: dict | None, *, tolerance: float = 0.05) -> list[str]:
    """Огибающая напряжений при разбросе номиналов (worst-case + вердикт)."""
    try:
        from .monte_carlo import run_tolerance_analysis

        report = run_tolerance_analysis(scheme_data or {}, iterations=2000, tolerance=tolerance, seed=42)
    except Exception:
        return []
    worst = (report.get('worst_case') or {}).get('nodes') or {}
    nodes = sorted(
        ((net, data) for net, data in worst.items() if net != '0'),
        key=lambda kv: -(kv[1].get('span') or 0),
    )
    lines = [
        f'узел {net}: {data["min"]:.2f}…{data["max"]:.2f} В (ном. {data["nominal"]:.2f})'
        for net, data in nodes[:4]
    ]
    if not lines:
        return []
    verdict = (report.get('paranoia') or {}).get('summary')
    if verdict:
        lines.append(f'вердикт: {verdict}')
    lines.append(f'источник: NumPy Monte Carlo + worst-case (±{int(tolerance * 100)}%)')
    return lines
