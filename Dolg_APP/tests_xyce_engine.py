"""Tests for the Xyce (Sandia SPICE) shell-out engine + its engine_jobs worker route.

Скипаются, если Xyce не найден (env XYCE_EXE / PATH / ~/Xyce_portable). Узловая нумерация
Xyce совпадает с NumPy MNA, поэтому сверяем напрямую.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from Dolg_APP.ml.gnn_simulator import _divider_scheme
from Dolg_APP.services import engine_jobs, xyce_engine

pytestmark = pytest.mark.skipif(
    not xyce_engine.available(), reason='Xyce не найден (XYCE_EXE / PATH / ~/Xyce_portable)'
)


def _job(scheme, analysis='dc'):
    return SimpleNamespace(
        engine_id='dolg-xyce',
        engine_name='Xyce',
        analysis_type=analysis,
        options={},
        scheme_data=scheme,
    )


def test_available_and_path():
    assert xyce_engine.available()
    assert xyce_engine.xyce_path()


def test_solve_dc_divider():
    v = xyce_engine.solve_dc(_divider_scheme(9.0, 1000, 2000))
    assert v is not None
    assert v[0] == 0.0  # ground
    assert any(abs(val - 6.0) < 0.01 for val in v.values())  # средний узел = 6В


def test_solve_dc_matches_mna():
    from Dolg_APP.services import monte_carlo

    scheme = _divider_scheme(12.0, 2200, 3300)
    mna = monte_carlo.solve_dc(monte_carlo.scheme_to_circuit(scheme))['voltages']
    xv = xyce_engine.solve_dc(scheme)
    assert xv is not None
    for net, mna_v in mna.items():
        assert abs(xv.get(net, 0.0) - mna_v) < 0.01, f'net {net}: xyce={xv.get(net)} mna={mna_v}'


def test_solve_dc_no_source_none():
    scheme = {
        'components': [
            {'id': 'r1', 'type': 'resistor', 'resistance': 1000, 'ports': [{'id': '1'}, {'id': '2'}]},
            {'id': 'g', 'type': 'ground', 'ports': [{'id': '1'}]},
        ],
        'connections': [{'from': {'compId': 'r1', 'portId': '2'}, 'to': {'compId': 'g', 'portId': '1'}}],
    }
    assert xyce_engine.solve_dc(scheme) is None


def test_xyce_dc_worker():
    scheme = _divider_scheme(9.0, 1000, 2000)
    res = engine_jobs._run_dc_xyce(_job(scheme), scheme)
    assert res['ok'] and res['analysis_type'] == 'dc'
    assert res['metrics']['backend'] == 'xyce'
    assert any(abs(n['voltage_v'] - 6.0) < 0.01 for n in res['nodes'])


def test_xyce_adapter_dispatch_dc():
    result, _warnings, _artifacts = engine_jobs._run_xyce_adapter(
        _job(_divider_scheme(9.0, 1000, 2000), 'dc')
    )
    assert result['analysis_type'] == 'dc'
    assert result['metrics']['backend'] == 'xyce'
    assert result['engine'] == 'dolg-xyce'
