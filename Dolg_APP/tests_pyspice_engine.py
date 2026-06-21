"""Tests for the PySpice (ngspice) DC engine adapter.

Скипаются, если PySpice не установлен (CI без requirements-ai). Проверяют, что
ngspice-результат совпадает с NumPy MNA в той же узловой нумерации.
"""

from __future__ import annotations

import pytest

from Dolg_APP.ml.gnn_simulator import _divider_scheme
from Dolg_APP.services import pyspice_engine as ps

pytestmark = pytest.mark.skipif(not ps.available(), reason='PySpice не установлен')


def test_available():
    assert ps.available() is True


def test_solve_dc_divider_ohms_law():
    # делитель 1k/2k от 9 В: средний узел = 9·2000/3000 = 6 В
    voltages = ps.solve_dc(_divider_scheme(9.0, 1000, 2000))
    assert voltages is not None
    assert voltages[0] == 0.0  # ground
    assert any(abs(v - 6.0) < 0.01 for v in voltages.values())


def test_solve_dc_matches_mna():
    from Dolg_APP.services import monte_carlo

    scheme = _divider_scheme(12.0, 2200, 3300)
    mna = monte_carlo.solve_dc(monte_carlo.scheme_to_circuit(scheme))['voltages']
    spi = ps.solve_dc(scheme)
    assert spi is not None
    for net, mna_v in mna.items():
        assert abs(spi.get(net, 0.0) - mna_v) < 0.01, f'net {net}: spi={spi.get(net)} mna={mna_v}'


def test_solve_dc_empty_is_trivial_ground():
    assert ps.solve_dc({'components': [], 'connections': []}) == {0: 0.0}


def _rc_scheme(v=5.0, r=1000, c=1e-6):
    return {
        'components': [
            {'id': 'V1', 'type': 'battery', 'voltage': v, 'ports': [{'id': '+'}, {'id': '-'}]},
            {'id': 'R1', 'type': 'resistor', 'resistance': r, 'ports': [{'id': '1'}, {'id': '2'}]},
            {'id': 'C1', 'type': 'capacitor', 'capacitance': c, 'ports': [{'id': '1'}, {'id': '2'}]},
            {'id': 'G', 'type': 'ground', 'ports': [{'id': '1'}]},
        ],
        'connections': [
            {'from': {'compId': 'V1', 'portId': '+'}, 'to': {'compId': 'R1', 'portId': '1'}},
            {'from': {'compId': 'R1', 'portId': '2'}, 'to': {'compId': 'C1', 'portId': '1'}},
            {'from': {'compId': 'C1', 'portId': '2'}, 'to': {'compId': 'G', 'portId': '1'}},
            {'from': {'compId': 'V1', 'portId': '-'}, 'to': {'compId': 'G', 'portId': '1'}},
        ],
    }


def test_solve_transient_rc_charging():
    # RC: V=5, R=1k, C=1µF → tau=1мс. Узел кондёра: 0 → 63% (3.16В) @tau → ~5В.
    import bisect

    tr = ps.solve_transient(_rc_scheme(), t_stop=5e-3, dt=1e-5)
    assert tr is not None
    assert tr['engine'] == 'pyspice-ngspice'
    assert tr['voltages'][0] == [0.0] * len(tr['time'])  # ground

    charging = [n for n, v in tr['voltages'].items() if v[0] < 0.1 and v[-1] > 4.5]
    assert charging, 'нет узла-конденсатора, заряжающегося 0 → ~5'
    out = tr['voltages'][charging[0]]
    i = bisect.bisect_left(tr['time'], 1e-3)  # t = tau
    assert 2.8 < out[i] < 3.5  # ~63% от 5В = 3.16


def test_solve_transient_no_source_none():
    assert ps.solve_transient({'components': [], 'connections': []}, t_stop=1e-3, dt=1e-5) is None


def test_solve_dc_no_source_returns_none():
    # схема без источника → DC operating point вырожден → None (caller падает на MNA)
    scheme = {
        'components': [
            {'id': 'r1', 'type': 'resistor', 'resistance': 1000, 'ports': [{'id': '1'}, {'id': '2'}]},
            {'id': 'g', 'type': 'ground', 'ports': [{'id': '1'}]},
        ],
        'connections': [{'from': {'compId': 'r1', 'portId': '2'}, 'to': {'compId': 'g', 'portId': '1'}}],
    }
    assert ps.solve_dc(scheme) is None
