"""Tests for the L2 algorithm registry (intent → engine sections)."""

from __future__ import annotations

from django.test import SimpleTestCase

from Dolg_APP.services import ai_algorithms, ai_toolkit
from Dolg_APP.tests_ai_toolkit import _divider


def _regulator_scheme(vin):
    return {
        'components': [
            {'id': 'V1', 'type': 'battery', 'voltage': vin, 'ports': [{'id': '+'}, {'id': '-'}]},
            {'id': 'U1', 'type': 'ic', 'label': '7805', 'ports': [{'id': '1'}, {'id': '2'}, {'id': '3'}]},
        ],
        'connections': [],
    }


def _rc():
    return {
        'components': [
            {'id': 'R1', 'type': 'resistor', 'resistance': 1600, 'ports': [{'id': '1'}, {'id': '2'}]},
            {'id': 'C1', 'type': 'capacitor', 'capacitance': '100n', 'ports': [{'id': '1'}, {'id': '2'}]},
        ],
        'connections': [],
    }


class SectionsForIntentTests(SimpleTestCase):
    def test_measurement_has_dc_section(self):
        sections = ai_algorithms.sections_for_intent('measurement', _divider())
        titles = [t for t, _ in sections]
        self.assertTrue(any('DC' in t for t in titles))
        # реальные числа в строках
        all_lines = [line for _, lines in sections for line in lines]
        self.assertTrue(any('В' in line for line in all_lines))

    def test_thermal_has_power_section(self):
        sections = ai_algorithms.sections_for_intent('thermal', _divider())
        self.assertTrue(any('Мощность' in t for t, _ in sections))

    def test_thermal_has_derating_section(self):
        sections = ai_algorithms.sections_for_intent('thermal', _divider())
        self.assertTrue(any('Запас' in t for t, _ in sections))
        all_lines = [line for _, lines in sections for line in lines]
        # derating-строки содержат процент нагрузки + вердикт
        self.assertTrue(any('%' in line for line in all_lines))

    def test_derating_in_manifest(self):
        thermal = {a['key'] for a in ai_algorithms.available_algorithms('thermal')}
        self.assertIn('derating', thermal)

    def test_plan_for_narrow_is_single(self):
        # Узкий запрос → план = [intent] (обратная совместимость)
        self.assertEqual(ai_algorithms.plan_for('покажи BOM', 'bom'), ['bom'])

    def test_plan_for_comprehensive_is_multi(self):
        # Диагностический запрос → расширенный план (несколько движков)
        plan = ai_algorithms.plan_for('проверь, всё ли ок со схемой', 'overview')
        self.assertGreater(len(plan), 1)
        self.assertIn('thermal', plan)
        # primary intent (если он в плане) идёт первым
        plan2 = ai_algorithms.plan_for('что измерить?', 'measurement')
        self.assertEqual(plan2[0], 'measurement')

    def test_regulator_dropout_ok(self):
        joined = ' '.join(ai_toolkit.regulator_lines(_regulator_scheme(12)))
        self.assertIn('dropout', joined.lower())
        self.assertIn('5', joined)  # Vout=5 из 7805
        self.assertIn('ОК', joined)  # 12-5=7 ≥ 2

    def test_regulator_dropout_too_low(self):
        lines = ai_toolkit.regulator_lines(_regulator_scheme(5))
        self.assertTrue(any('не стабилизирует' in ln for ln in lines))

    def test_regulator_in_manifest(self):
        keys = {a['key'] for a in ai_algorithms.available_algorithms('formula')}
        self.assertIn('regulator', keys)

    def test_sections_for_plan_dedup(self):
        # dc_voltages есть и в measurement, и в overview — в плане не дублируется
        sections = ai_algorithms.sections_for_plan(['measurement', 'thermal'], _divider())
        titles = [t for t, _ in sections]
        self.assertEqual(len(titles), len(set(titles)))
        # план объединяет движки обоих intent'ов (DC + мощность/derating)
        joined = ' '.join(titles)
        self.assertIn('DC', joined)
        self.assertTrue('Мощность' in joined or 'Запас' in joined)

    def test_formula_rc_has_formula_and_rf(self):
        sections = ai_algorithms.sections_for_intent('formula', _rc(), 'rc_network')
        titles = ' '.join(t for t, _ in sections)
        self.assertIn('Расчёт по схеме', titles)
        self.assertIn('RF-анализ', titles)

    def test_empty_scheme_no_sections(self):
        self.assertEqual(ai_algorithms.sections_for_intent('measurement', {'components': []}), [])

    def test_unrelated_intent_no_sections(self):
        self.assertEqual(ai_algorithms.sections_for_intent('demo_script', _divider()), [])

    def test_manifest(self):
        keys = {a['key'] for a in ai_algorithms.available_algorithms()}
        self.assertTrue(
            {'dc_voltages', 'power', 'formula', 'rf_filter', 'tolerance', 'tiny_ai'}.issubset(keys)
        )
        meas = {a['key'] for a in ai_algorithms.available_algorithms('measurement')}
        self.assertIn('dc_voltages', meas)
        self.assertNotIn('power', meas)

    def test_tiny_ai_skill_in_overview(self):
        # tiny-AI зарегистрирована как skill для overview (если torch есть — секция появится)
        meta = {a['key']: a['intents'] for a in ai_algorithms.available_algorithms()}
        self.assertIn('overview', meta['tiny_ai'])
        sections = ai_algorithms.sections_for_intent('overview', _divider())
        # не падает; если tiny-AI доступна — будет секция «Нейроподсказка»
        self.assertIsInstance(sections, list)
