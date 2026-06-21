"""Tests for the large resistor-grid generator (тысячи элементов → 3D-поле напряжений)."""

from __future__ import annotations

from Dolg_APP.services import large_circuits as lc
from Dolg_APP.services import monte_carlo


def test_grid_size_counts():
    # N×N: n_nodes = N²+1 (с ground); элементов = V + 2·N·(N−1) резисторов + R_gnd.
    n = 10
    c = lc.generate_resistor_grid_circuit(n)
    assert c['n_nodes'] == n * n + 1
    assert len(c['elements']) == 2 * n * (n - 1) + 2


def test_grid_thousands_of_elements():
    c = lc.generate_resistor_grid_circuit(40)
    assert len(c['elements']) > 3000  # «несколько тысяч элементов»


def test_grid_solvable_and_field_gradient():
    n = 8
    c = lc.generate_resistor_grid_circuit(n, v=10.0, r=100.0)
    res = monte_carlo.solve_dc(c)
    field = lc.voltage_field(res['voltages'], n)
    assert len(field) == n and len(field[0]) == n
    # источник в углу (0,0) = 10В; противоположный угол ниже (градиент к земле)
    assert abs(field[0][0] - 10.0) < 0.01
    assert field[0][0] > field[n // 2][n // 2] > field[n - 1][n - 1]
    assert field[n - 1][n - 1] >= 0.0


def test_grid_net_mapping():
    assert lc.grid_net(0, 0, 5) == 1  # net 0 = ground, узлы с 1
    assert lc.grid_net(1, 0, 5) == 6
    assert lc.grid_net(4, 4, 5) == 25
