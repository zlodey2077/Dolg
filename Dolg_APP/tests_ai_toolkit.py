"""Tests for the local-AI toolkit (engine-backed answer sections)."""

from __future__ import annotations

from django.test import SimpleTestCase

from Dolg_APP.services import ai_toolkit


def _divider(v=9.0, r1=1000, r2=2000):
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


class ComputeDcTests(SimpleTestCase):
    def test_divider_solves_to_six_volts(self):
        dc = ai_toolkit.compute_dc(_divider(9, 1000, 2000))
        self.assertTrue(dc['ok'])
        # делитель 9В·2k/(1k+2k) = 6В — должен быть среди напряжений узлов
        self.assertTrue(any(abs(v - 6.0) < 1e-2 for v in dc['voltages'].values()), dc['voltages'])

    def test_empty_scheme_not_ok(self):
        self.assertFalse(ai_toolkit.compute_dc({'components': [], 'connections': []})['ok'])
        self.assertFalse(ai_toolkit.compute_dc(None)['ok'])


class LineHelpersTests(SimpleTestCase):
    def test_dc_voltage_lines_contain_source(self):
        lines = ai_toolkit.dc_voltage_lines(_divider())
        self.assertTrue(lines)
        self.assertTrue(any('источник: MNA' in line for line in lines))
        self.assertTrue(any('В' in line for line in lines))

    def test_power_lines_real_numbers(self):
        lines = ai_toolkit.power_lines(_divider(9, 1000, 2000))
        self.assertTrue(lines)
        self.assertTrue(any('R1' in line or 'R2' in line for line in lines))
        self.assertTrue(any('P = ΔU²/R' in line for line in lines))

    def test_tolerance_lines_have_verdict_and_source(self):
        lines = ai_toolkit.tolerance_lines(_divider(), tolerance=0.05)
        self.assertTrue(lines)
        self.assertTrue(any('вердикт' in line for line in lines))
        self.assertTrue(any('Monte Carlo' in line for line in lines))

    def test_unsolvable_returns_empty(self):
        self.assertEqual(ai_toolkit.dc_voltage_lines({'components': [], 'connections': []}), [])
        self.assertEqual(ai_toolkit.power_lines(None), [])


class FormulaComputeTests(SimpleTestCase):
    def test_rc_cutoff_real_number(self):
        rc = {
            'components': [
                {'id': 'R1', 'type': 'resistor', 'resistance': 1600, 'ports': [{'id': '1'}, {'id': '2'}]},
                {'id': 'C1', 'type': 'capacitor', 'capacitance': '100n', 'ports': [{'id': '1'}, {'id': '2'}]},
            ],
            'connections': [],
        }
        lines = ai_toolkit.formula_compute(rc, 'rc_network')
        self.assertTrue(any('fc' in line and 'Гц' in line for line in lines))
        self.assertTrue(any('99' in line for line in lines))  # ~995 Гц

    def test_led_current_real_number(self):
        led = {
            'components': [
                {'id': 'B1', 'type': 'battery', 'voltage': 5, 'ports': [{'id': '+'}, {'id': '-'}]},
                {'id': 'D1', 'type': 'led', 'vf': 2, 'ports': [{'id': '1'}, {'id': '2'}]},
                {'id': 'R1', 'type': 'resistor', 'resistance': 330, 'ports': [{'id': '1'}, {'id': '2'}]},
            ],
            'connections': [],
        }
        lines = ai_toolkit.formula_compute(led, 'led_indicator')
        self.assertTrue(any('Iled' in line and 'мА' in line for line in lines))
        self.assertTrue(any('9.' in line for line in lines))  # ~9.1 мА

    def test_divider_reports_node_voltages(self):
        lines = ai_toolkit.formula_compute(_divider(9, 1000, 2000), 'voltage_divider')
        self.assertTrue(any('MNA' in line for line in lines))

    def test_missing_values_empty(self):
        self.assertEqual(ai_toolkit.formula_compute({'components': []}, 'rc_network'), [])
        self.assertEqual(ai_toolkit.formula_compute(None, 'unknown_topology'), [])


class RfFilterTests(SimpleTestCase):
    def test_rc_filter_cutoff_and_source(self):
        rc = {
            'components': [
                {'id': 'R1', 'type': 'resistor', 'resistance': 1000, 'ports': [{'id': '1'}, {'id': '2'}]},
                {'id': 'C1', 'type': 'capacitor', 'capacitance': '100n', 'ports': [{'id': '1'}, {'id': '2'}]},
            ],
            'connections': [],
        }
        lines = ai_toolkit.rf_filter_lines(rc)
        self.assertTrue(lines)
        self.assertTrue(any('scikit-rf' in line for line in lines))
        self.assertTrue(any('−3 дБ' in line or 'Гц' in line for line in lines))

    def test_no_capacitor_empty(self):
        only_r = {'components': [{'id': 'R1', 'type': 'resistor', 'resistance': 1000}], 'connections': []}
        self.assertEqual(ai_toolkit.rf_filter_lines(only_r), [])
