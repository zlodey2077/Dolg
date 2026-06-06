"""Tests for Block D2: server-side Monte Carlo DC analysis."""

from __future__ import annotations

import pytest

from Dolg_APP.services.monte_carlo import (
    MAX_ITERATIONS,
    run_monte_carlo,
    run_tolerance_analysis,
    run_worst_case,
    scheme_to_circuit,
    solve_dc,
)


def _voltage_divider(v=9.0, r1=1000, r2=2000):
    """9V → R1 → R2 → GND. V_R2 = v * r2/(r1+r2)."""
    return {
        'components': [
            {'id': 'B1', 'type': 'battery', 'voltage': v, 'ports': [{'id': '+'}, {'id': '-'}]},
            {'id': 'R1', 'type': 'resistor', 'resistance': r1, 'ports': [{'id': '1'}, {'id': '2'}]},
            {'id': 'R2', 'type': 'resistor', 'resistance': r2, 'ports': [{'id': '1'}, {'id': '2'}]},
            {'id': 'G1', 'type': 'ground', 'ports': [{'id': '1'}]},
        ],
        'connections': [
            {'from': {'compId': 'B1', 'portId': '+'}, 'to': {'compId': 'R1', 'portId': '1'}},
            {'from': {'compId': 'R1', 'portId': '2'}, 'to': {'compId': 'R2', 'portId': '1'}},
            {'from': {'compId': 'R2', 'portId': '2'}, 'to': {'compId': 'B1', 'portId': '-'}},
            {'from': {'compId': 'B1', 'portId': '-'}, 'to': {'compId': 'G1', 'portId': '1'}},
        ],
    }


def test_scheme_to_circuit_basic():
    c = scheme_to_circuit(_voltage_divider())
    types = [e['type'] for e in c['elements']]
    assert 'V' in types
    assert types.count('R') == 2


def test_dc_solver_matches_theory_voltage_divider():
    """V_R2 = 9V × 2k/(1k+2k) = 6V; current = 9V/3k = 3mA."""
    c = scheme_to_circuit(_voltage_divider())
    res = solve_dc(c)
    v_max = max(res['voltages'].values())
    assert abs(v_max - 9.0) < 0.01
    # V между источника и землёй есть, средний узел ≈ 6V
    mid = [v for v in res['voltages'].values() if 5.5 < v < 6.5]
    assert len(mid) == 1
    # Ток
    assert len(res['currents']) == 1
    current = next(iter(res['currents'].values()))
    assert abs(abs(current) - 3.0e-3) < 1e-5


def test_monte_carlo_mean_matches_theory():
    """С N=2000 итераций mean ≈ номиналу (±~0.5%)."""
    result = run_monte_carlo(_voltage_divider(), iterations=2000, tolerance=0.05, seed=42)
    assert result['success'] >= 1900
    assert result['failed'] <= 100
    # Среднее на узле с V_out должно быть близко к 6V
    mid_node = None
    for node, st in result['nodes'].items():
        if 5.5 < st['mean'] < 6.5:
            mid_node = st
            break
    assert mid_node is not None
    assert abs(mid_node['mean'] - 6.0) < 0.1
    # p05/p95 окружают mean
    assert mid_node['p05'] < mid_node['mean'] < mid_node['p95']


def test_monte_carlo_tolerance_scales_spread():
    """Больший tolerance → больший std разброс."""
    low = run_monte_carlo(_voltage_divider(), iterations=500, tolerance=0.01, seed=1)
    high = run_monte_carlo(_voltage_divider(), iterations=500, tolerance=0.10, seed=1)
    low_std = max(st['std'] for st in low['nodes'].values() if st['std'] > 0)
    high_std = max(st['std'] for st in high['nodes'].values() if st['std'] > 0)
    assert high_std > low_std * 3  # 10× tolerance → ~10× std (но clamp срабатывает)


def test_monte_carlo_empty_scheme():
    result = run_monte_carlo({'components': [], 'connections': []})
    assert result['success'] == 0
    assert result.get('errors')


def test_monte_carlo_clamps_iterations():
    """Слишком большое N зажимается MAX_ITERATIONS."""
    result = run_monte_carlo(_voltage_divider(), iterations=100000, tolerance=0.05, seed=1)
    assert result['iterations'] <= MAX_ITERATIONS


def test_monte_carlo_reproducible_with_seed():
    """Один seed → одинаковый результат."""
    a = run_monte_carlo(_voltage_divider(), iterations=200, seed=42)
    b = run_monte_carlo(_voltage_divider(), iterations=200, seed=42)
    for node in a['nodes']:
        assert abs(a['nodes'][node]['mean'] - b['nodes'][node]['mean']) < 1e-9


def test_monte_carlo_throughput():
    """Поверки производительности — должен укладываться в 5 сек для 1000 итераций."""
    result = run_monte_carlo(_voltage_divider(), iterations=1000, tolerance=0.05, seed=42)
    assert result['elapsed_ms'] < 5000
    assert result['iter_per_sec'] > 100  # лоу-бар на медленном CI


@pytest.mark.parametrize('tolerance', [0.0, 0.5, 0.99])
def test_monte_carlo_tolerance_edge_values(tolerance):
    """Tolerance клампится в [0, 0.5]."""
    result = run_monte_carlo(_voltage_divider(), iterations=50, tolerance=tolerance, seed=1)
    assert 0.0 <= result['tolerance'] <= 0.5


def test_monte_carlo_reports_nominal():
    """В отчёте есть номинал (без джиттера): делитель 9V/(1k+2k) → 6V на узле."""
    result = run_monte_carlo(_voltage_divider(), iterations=100, seed=1)
    assert any(abs(v - 6.0) < 1e-3 for v in result['nominal'].values())


# ─── Worst-case / corner analysis ────────────────────────────────────────
def test_worst_case_envelope_brackets_nominal():
    """Угловой анализ: огибающая узла охватывает номинал, полный перебор 2^3."""
    wc = run_worst_case(_voltage_divider(), tolerance=0.05, seed=1)
    assert wc['exhaustive'] is True
    assert wc['components'] == 3  # B1 + R1 + R2 толерантны
    assert wc['evaluated'] == 8  # 2^3 углов
    div_node = max(wc['nodes'].values(), key=lambda n: n['span'])
    assert div_node['min'] < div_node['nominal'] < div_node['max']


def test_worst_case_per_component_override_shrinks_span():
    """Зажатие допусков всех компонентов в 0 → нулевая огибающая."""
    wide = run_worst_case(_voltage_divider(), tolerance=0.05, seed=1)
    tight = run_worst_case(
        _voltage_divider(),
        component_tolerances={'B1': 0.0, 'R1': 0.0, 'R2': 0.0},
        seed=1,
    )
    wide_span = max(n['span'] for n in wide['nodes'].values())
    tight_span = max(n['span'] for n in tight['nodes'].values())
    assert tight_span < wide_span
    assert tight_span < 1e-6


def test_worst_case_zero_tolerance_no_spread():
    wc = run_worst_case(_voltage_divider(), tolerance=0.0, seed=1)
    assert all(n['span'] < 1e-6 for n in wc['nodes'].values())


def test_component_tolerance_percent_one_is_one_percent():
    """Регрессия: tolerance_percent=1 (E96) = ±1%, НЕ ±100%."""
    scheme = _voltage_divider()
    for comp in scheme['components']:
        if comp['id'] == 'R1':
            comp['tolerance_percent'] = 1  # 1% точный резистор
    # R1 узкий (1%), у остальных глобальный 0.05 → R1 почти не влияет на разброс
    circuit_tol = run_worst_case(scheme, tolerance=0.05, seed=1)
    # Если бы 1 трактовалось как 100%, огибающая была бы огромной (>>номинала).
    div_node = max(circuit_tol['nodes'].values(), key=lambda n: n['span'])
    assert div_node['span'] < abs(div_node['nominal'])  # разброс меньше номинала


# ─── Комбинированный отчёт + paranoia ────────────────────────────────────
def test_tolerance_analysis_combines_mc_and_worst_case():
    rep = run_tolerance_analysis(_voltage_divider(), iterations=200, seed=1)
    assert 'monte_carlo' in rep
    assert 'worst_case' in rep
    assert 'paranoia' in rep
    assert rep['paranoia']['verdict'] in {'ok', 'warning', 'critical'}


def test_paranoia_flags_high_spread_as_critical():
    """Большой допуск → широкая огибающая → critical-вердикт с флагами."""
    rep = run_tolerance_analysis(_voltage_divider(), iterations=100, tolerance=0.3, seed=1)
    par = rep['paranoia']
    assert par['verdict'] == 'critical'
    assert par['high'] >= 1
    assert any(f['severity'] == 'high' for f in par['flags'])


def test_paranoia_ok_when_tolerances_zero():
    rep = run_tolerance_analysis(_voltage_divider(), iterations=50, tolerance=0.0, seed=1)
    assert rep['paranoia']['verdict'] == 'ok'
    assert rep['paranoia']['flags'] == []
