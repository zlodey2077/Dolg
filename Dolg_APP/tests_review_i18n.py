"""Regression tests: review dedup + localization (verify of stale backlog items).

DRC-дедуп «Отсутствует GND из 3 мест» и локализация findings уже реализованы
в review_i18n; эти тесты фиксируют поведение, чтобы оно не регрессировало.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from Dolg_APP.services.review_i18n import (
    _dedup_messages,
    localize_review_report,
    translate_review_text,
)


class ReviewDedupTests(SimpleTestCase):
    def test_cross_source_gnd_warnings_collapse_to_one(self):
        """GND-предупреждения от validation и graph схлопываются в одно
        (семантическое ядро missing_ground), хотя формулировки разные."""
        report = {
            'status': 'warning',
            'warnings': [
                'В схеме нет GND: симулятор назначит опорный узел автоматически',
                'В графе схемы нет GND: все компоненты считаются floating.',
            ],
        }
        out = localize_review_report(report)
        gnd = [w for w in out['warnings'] if 'gnd' in w.lower()]
        self.assertEqual(len(gnd), 1, out['warnings'])

    def test_dedup_keeps_distinct_messages(self):
        msgs = ['Нет опорного узла GND', 'Нет источника питания', 'Есть плавающие фрагменты схемы']
        self.assertEqual(len(_dedup_messages(msgs)), 3)

    def test_dedup_passes_through_non_strings(self):
        self.assertEqual(_dedup_messages([{'a': 1}, {'a': 1}]), [{'a': 1}, {'a': 1}])


class ReviewLocalizationTests(SimpleTestCase):
    def test_fixed_english_errors_localized(self):
        report = {
            'status': 'fail',
            'errors': ['Missing GND reference'],
            'warnings': ['Missing supply/source component'],
        }
        out = localize_review_report(report)
        self.assertIn('Нет опорного узла GND', out['errors'])
        self.assertIn('Нет источника питания или сигнала', out['warnings'])

    def test_composite_component_message_localized(self):
        """Составное «R1: <english>» локализуется по части после двоеточия."""
        self.assertEqual(
            translate_review_text('R1: Component power overload'),
            'R1: Перегрузка компонента по мощности',
        )

    def test_graph_topology_prefix_localized(self):
        out = translate_review_text('Graph topology: floating fragments')
        self.assertTrue(out.startswith('Граф схемы:'), out)

    def test_unknown_text_preserved(self):
        self.assertEqual(translate_review_text('R7 custom note xyz'), 'R7 custom note xyz')
