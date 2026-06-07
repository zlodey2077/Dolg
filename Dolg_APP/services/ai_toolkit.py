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
