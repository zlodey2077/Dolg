"""Tests for the in-process PySpice (ngspice) worker route in engine_jobs.

Run-функции воркера не трогают БД (это делает адаптер-обёртка), поэтому тестируются
лёгким фейк-job. Скипаются без PySpice.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from Dolg_APP.ml.gnn_simulator import _divider_scheme
from Dolg_APP.services import engine_jobs, pyspice_engine

pytestmark = pytest.mark.skipif(not pyspice_engine.available(), reason='PySpice не установлен')


def _job(scheme, analysis='dc', options=None):
    return SimpleNamespace(
        engine_id='dolg-pyspice',
        engine_name='PySpice (ngspice)',
        analysis_type=analysis,
        options=options or {},
        scheme_data=scheme,
    )


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


def test_pyspice_dc_worker():
    scheme = _divider_scheme(9.0, 1000, 2000)
    res = engine_jobs._run_dc_pyspice(_job(scheme), scheme)
    assert res['ok'] and res['analysis_type'] == 'dc'
    assert res['metrics']['backend'] == 'pyspice-ngspice'
    assert any(abs(n['voltage_v'] - 6.0) < 0.01 for n in res['nodes'])  # средний узел = 6В


def test_pyspice_transient_worker():
    scheme = _rc_scheme()
    res = engine_jobs._run_transient_pyspice(_job(scheme, 'transient'), scheme, {'t_stop': 5e-3, 'dt': 1e-5})
    assert res['ok'] and res['analysis_type'] == 'transient'
    assert res['metrics']['backend'] == 'pyspice-ngspice'
    assert res['waveforms'] and res['time_s']


def test_pyspice_ac_worker():
    scheme = _rc_scheme(v=1.0)
    res = engine_jobs._run_ac_pyspice(
        _job(scheme, 'ac'), scheme, {'f_start': 10, 'f_stop': 100000, 'points': 10}
    )
    assert res['ok'] and res['analysis_type'] == 'ac'
    assert res['metrics']['backend'] == 'pyspice-ngspice'
    assert len(res['frequencies_hz']) == 10


def test_pyspice_adapter_dispatch_dc():
    result, _warnings, _artifacts = engine_jobs._run_pyspice_adapter(
        _job(_divider_scheme(9.0, 1000, 2000), 'dc')
    )
    assert result['analysis_type'] == 'dc'
    assert result['metrics']['backend'] == 'pyspice-ngspice'
    assert result['engine'] == 'dolg-pyspice'
