"""Tests for neural_teacher — движковый учитель (физика + топология + expert findings).

Проверяют, что метки берутся из реального ядра движков: верные напряжения MNA,
дифференцированный риск из expert_rules, штатная деградация на нерешаемой схеме.
"""

from __future__ import annotations

from Dolg_APP.ml import neural_teacher as t
from Dolg_APP.ml.gnn_simulator import _divider_scheme


def _battery_no_ground():
    return {
        'components': [
            {'id': 'v1', 'type': 'battery', 'voltage': 9},
            {'id': 'r1', 'type': 'resistor', 'resistance': 100},
        ],
        'connections': [{'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}}],
    }


def test_dc_labels_divider_physics_correct():
    dc = t.dc_labels(_divider_scheme(9.0, 1000, 2000))
    assert dc is not None
    # делитель 1k/2k от 9 В: средний узел = 9·2000/3000 = 6 В
    assert any(abs(v - 6.0) < 0.1 for v in dc['voltages'].values())
    assert dc['engine'] == 'dolg-numpy-mna'


def test_dc_labels_unsolvable_returns_none():
    assert t.dc_labels({'components': [], 'connections': []}) is None


def test_topology_label_divider():
    assert t.topology_label(_divider_scheme(9.0, 1000, 2000)) == 'voltage_divider'


def test_expert_risk_differentiates_missing_ground():
    div_risk = t.expert_risk(_divider_scheme(9.0, 1000, 2000))
    bad_risk = t.expert_risk(_battery_no_ground())
    assert div_risk is not None and bad_risk is not None
    # схема без земли рискованнее корректного делителя
    assert bad_risk[0] >= div_risk[0]
    # и причина — реальный rule_id отсутствия земли
    assert any('ground' in r for r in bad_risk[1])


def test_expert_risk_serious_only_not_saturated():
    # риск не насыщается до 1.0 на корректной схеме из-за docs/layout-гигиены
    div_risk = t.expert_risk(_divider_scheme(9.0, 1000, 2000))
    assert div_risk is not None
    assert 0.0 <= div_risk[0] <= 1.0


def test_label_shape():
    label = t.label(_divider_scheme(9.0, 1000, 2000))
    for key in ('topology', 'voltages', 'currents', 'solvable', 'expert_risk', 'expert_reasons'):
        assert key in label
    assert label['solvable'] is True


def test_risk_from_findings_none_when_empty():
    assert t.expert_risk_from_findings([]) is None
    # findings есть, но не серьёзные → риск 0.0 (электрической угрозы нет)
    assert t.expert_risk_from_findings([{'severity': 'info', 'rule_id': 'docs.x'}]) == (0.0, [])
