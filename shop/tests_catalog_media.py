"""Tests for catalog media coverage aggregation."""

from __future__ import annotations

from django.test import SimpleTestCase

from shop.services.media_quality import aggregate_media_coverage


class AggregateMediaCoverageTests(SimpleTestCase):
    def test_counts_by_class_and_category(self):
        items = [
            ('resistors', 'local_asset'),
            ('resistors', 'generated'),
            ('resistors', 'missing'),
            ('capacitors', 'local_asset'),
            ('capacitors', 'forbidden'),
        ]
        report = aggregate_media_coverage(items)
        r = report['categories']['resistors']
        self.assertEqual(r['total'], 3)
        self.assertEqual(r['real'], 1)
        self.assertEqual(r['placeholder'], 1)
        self.assertEqual(r['missing'], 1)
        self.assertAlmostEqual(r['real_coverage'], round(1 / 3, 3))
        c = report['categories']['capacitors']
        self.assertEqual(c['problem'], 1)  # forbidden → problem

    def test_totals(self):
        items = [('ics', 'local_asset'), ('ics', 'local_asset'), ('ics', 'generated')]
        report = aggregate_media_coverage(items)
        t = report['totals']
        self.assertEqual(t['total'], 3)
        self.assertEqual(t['real'], 2)
        self.assertEqual(t['placeholder'], 1)
        self.assertAlmostEqual(t['real_coverage'], round(2 / 3, 3))

    def test_off_policy_and_unknown_slug(self):
        report = aggregate_media_coverage([(None, 'off_policy')])
        self.assertIn('unknown', report['categories'])
        self.assertEqual(report['categories']['unknown']['problem'], 1)

    def test_by_type_breakdown_preserved(self):
        report = aggregate_media_coverage([('diodes', 'generated'), ('diodes', 'generated')])
        self.assertEqual(report['categories']['diodes']['by_type']['generated'], 2)

    def test_empty(self):
        report = aggregate_media_coverage([])
        self.assertEqual(report['totals']['total'], 0)
        self.assertEqual(report['totals']['real_coverage'], 0.0)
