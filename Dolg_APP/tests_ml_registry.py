"""Tests for the neural model registry (основа нейронной части)."""

from __future__ import annotations

from Dolg_APP.ml import registry
from Dolg_APP.ml.gnn_simulator import _divider_scheme


def test_defaults_registered():
    assert registry.get('tiny_circuit_hints') is not None
    assert registry.get('gnn_voltage') is not None
    assert len(registry.all_models()) >= 2


def test_model_metadata_contract():
    tiny = registry.get('tiny_circuit_hints')
    assert tiny.task == 'circuit_hints'
    assert 'expert_risk' in tiny.teacher  # учится у движкового учителя
    gnn = registry.get('gnn_voltage')
    assert gnn.task == 'voltage_regression'
    assert gnn.teacher == ('voltages',)


def test_status_shape():
    rows = registry.status()
    assert {r['key'] for r in rows} >= {'tiny_circuit_hints', 'gnn_voltage'}
    for row in rows:
        assert 'torch' in row and 'trained' in row and 'task' in row


def test_predict_unknown_key_returns_none():
    assert registry.predict('does_not_exist', _divider_scheme(9.0, 1000, 2000)) is None


def test_predict_tiny_returns_dict():
    # TinyCircuitNet предсказывает даже без обученных весов (свежий baseline)
    out = registry.predict('tiny_circuit_hints', _divider_scheme(9.0, 1000, 2000))
    assert isinstance(out, dict)
    assert 'topology' in out


def test_predict_gnn_dict_or_none():
    # GNN: dict {net: V} если есть веса/torch, иначе graceful None — но не падение
    out = registry.predict('gnn_voltage', _divider_scheme(9.0, 1000, 2000))
    assert out is None or isinstance(out, dict)
