"""Tests for Block D2: server-side Monte Carlo DC analysis."""
from __future__ import annotations

import pytest

from Dolg_APP.services.monte_carlo import (
    run_monte_carlo,
    scheme_to_circuit,
    solve_dc,
)


def _voltage_divider(v=9.0, r1=1000, r2=2000):
    """9V → R1 → R2 → GND. V_R2 = v * r2/(r1+r2)."""
    return {
        'components': [
            {'id': 'B1', 'type': 'battery', 'voltage': v,
             'ports': [{'id': '+'}, {'id': '-'}]},
            {'id': 'R1', 'type': 'resistor', 'resistance': r1,
             'ports': [{'id': '1'}, {'id': '2'}]},
            {'id': 'R2', 'type': 'resistor', 'resistance': r2,
             'ports': [{'id': '1'}, {'id': '2'}]},
            {'id': 'G1', 'type': 'ground', 'ports': [{'id': '1'}]},
        ],
        'connections': [
            {'from': {'compId': 'B1', 'portId': '+'},
             'to': {'compId': 'R1', 'portId': '1'}},
            {'from': {'compId': 'R1', 'portId': '2'},
             'to': {'compId': 'R2', 'portId': '1'}},
            {'from': {'compId': 'R2', 'portId': '2'},
             'to': {'compId': 'B1', 'portId': '-'}},
            {'from': {'compId': 'B1', 'portId': '-'},
             'to': {'compId': 'G1', 'portId': '1'}},
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
    result = run_monte_carlo(_voltage_divider(), iterations=2000,
                             tolerance=0.05, seed=42)
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
    low = run_monte_carlo(_voltage_divider(), iterations=500,
                          tolerance=0.01, seed=1)
    high = run_monte_carlo(_voltage_divider(), iterations=500,
                           tolerance=0.10, seed=1)
    low_std = max(st['std'] for st in low['nodes'].values() if st['std'] > 0)
    high_std = max(st['std'] for st in high['nodes'].values() if st['std'] > 0)
    assert high_std > low_std * 3   # 10× tolerance → ~10× std (но clamp срабатывает)


def test_monte_carlo_empty_scheme():
    result = run_monte_carlo({'components': [], 'connections': []})
    assert result['success'] == 0
    assert result.get('errors')


def test_monte_carlo_clamps_iterations():
    """Слишком большое N зажимается MAX_ITERATIONS."""
    result = run_monte_carlo(_voltage_divider(), iterations=100000,
                             tolerance=0.05, seed=1)
    assert result['iterations'] <= 5000


def test_monte_carlo_reproducible_with_seed():
    """Один seed → одинаковый результат."""
    a = run_monte_carlo(_voltage_divider(), iterations=200, seed=42)
    b = run_monte_carlo(_voltage_divider(), iterations=200, seed=42)
    for node in a['nodes']:
        assert abs(a['nodes'][node]['mean'] - b['nodes'][node]['mean']) < 1e-9


def test_monte_carlo_throughput():
    """Поверки производительности — должен укладываться в 5 сек для 1000 итераций."""
    result = run_monte_carlo(_voltage_divider(), iterations=1000,
                             tolerance=0.05, seed=42)
    assert result['elapsed_ms'] < 5000
    assert result['iter_per_sec'] > 100   # лоу-бар на медленном CI


@pytest.mark.parametrize('tolerance', [0.0, 0.5, 0.99])
def test_monte_carlo_tolerance_edge_values(tolerance):
    """Tolerance клампится в [0, 0.5]."""
    result = run_monte_carlo(_voltage_divider(), iterations=50,
                             tolerance=tolerance, seed=1)
    assert 0.0 <= result['tolerance'] <= 0.5
