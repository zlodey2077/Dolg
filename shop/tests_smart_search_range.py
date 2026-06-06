"""Tests for Smart-search Phase 1.5 range tokens (R<10k, P>0.25, V<=50)."""

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from shop.smart_search import (
    extract_range_constraints,
    filter_by_ranges,
    product_matches_range,
)


def _p(**params):
    return SimpleNamespace(parameters=params)


class ExtractRangeTests(SimpleTestCase):
    def test_single_range_token(self):
        text, cons = extract_range_constraints('R<10k')
        self.assertEqual(text, '')
        self.assertEqual(len(cons), 1)
        self.assertEqual(cons[0].prefix, 'r')
        self.assertEqual(cons[0].op, '<')
        self.assertEqual(cons[0].target, 10000)

    def test_mixed_text_and_range(self):
        text, cons = extract_range_constraints('резистор R<10k P>0.1')
        self.assertEqual(text, 'резистор')
        ops = {c.prefix: c.op for c in cons}
        self.assertEqual(ops, {'r': '<', 'p': '>'})

    def test_non_range_word_kept(self):
        text, cons = extract_range_constraints('v2 vishay')
        self.assertEqual(cons, [])
        self.assertEqual(text, 'v2 vishay')

    def test_empty(self):
        self.assertEqual(extract_range_constraints(''), ('', []))


class MatchRangeTests(SimpleTestCase):
    def test_resistance_less_than(self):
        _, cons = extract_range_constraints('R<10k')
        self.assertTrue(product_matches_range(_p(resistance='4.7 кОм'), cons[0]))
        self.assertFalse(product_matches_range(_p(resistance='47 кОм'), cons[0]))

    def test_voltage_falls_back_to_max_voltage(self):
        _, cons = extract_range_constraints('V<=100')
        self.assertTrue(product_matches_range(_p(max_voltage='50 В'), cons[0]))
        self.assertFalse(product_matches_range(_p(max_voltage='200 В'), cons[0]))

    def test_equals_uses_isclose(self):
        _, cons = extract_range_constraints('R=10k')
        self.assertTrue(product_matches_range(_p(resistance='10 кОм'), cons[0]))

    def test_missing_param_no_match(self):
        _, cons = extract_range_constraints('R<10k')
        self.assertFalse(product_matches_range(_p(capacitance='100 нФ'), cons[0]))


class FilterByRangesTests(SimpleTestCase):
    def test_and_of_two_constraints(self):
        _, cons = extract_range_constraints('R>1k R<100k')
        items = [
            _p(resistance='4.7 кОм'),  # 4700 — внутри (1k..100k)
            _p(resistance='220 Ом'),  # 220 — мимо (<1k)
            _p(resistance='1 МОм'),  # 1e6 — мимо (>100k)
        ]
        result = filter_by_ranges(items, cons)
        self.assertEqual(len(result), 1)

    def test_no_constraints_returns_all(self):
        items = [_p(resistance='1k'), _p(resistance='2k')]
        self.assertEqual(len(filter_by_ranges(items, [])), 2)
