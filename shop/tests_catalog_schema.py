"""Tests for per-category catalog schema + coverage audit."""

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from shop.services.catalog_schema import (
    CATEGORY_SCHEMAS,
    audit_catalog,
    audit_product,
    schema_for_category,
)


def _product(slug, params, **fields):
    base = {
        'slug': fields.get('slug', 'p1'),
        'part_number': fields.get('part_number', 'PN-1'),
        'package_type': fields.get('package_type', 'SMD 0805'),
        'datasheet_url': fields.get('datasheet_url', 'https://example.com/ds.pdf'),
    }
    return SimpleNamespace(category=SimpleNamespace(slug=slug), parameters=params, **base)


def _full_resistor(**over):
    params = {
        'resistance': '10 кОм',
        'power': '0.25 Вт',
        'tolerance': '1%',
        'mounting': 'SMD',
        'type': 'thick film',
        'material': 'metal',
        'temp_coef': '100 ppm',
        'max_voltage': '150 В',
    }
    params.update(over)
    return _product('resistors', params)


class SchemaLookupTests(SimpleTestCase):
    def test_schema_for_known_category(self):
        schema = schema_for_category('resistors')
        self.assertIsNotNone(schema)
        self.assertIn('resistance', schema['required'])

    def test_schema_for_unknown_category(self):
        self.assertIsNone(schema_for_category('smartphones'))


class AuditProductTests(SimpleTestCase):
    def test_full_product_is_ok_full_coverage(self):
        r = audit_product(_full_resistor())
        self.assertTrue(r['ok'])
        self.assertEqual(r['missing_required'], [])
        self.assertEqual(r['missing_recommended'], [])
        self.assertEqual(r['coverage'], 1.0)

    def test_missing_recommended_lowers_coverage_but_stays_ok(self):
        params = _full_resistor().parameters
        params.pop('temp_coef')
        params.pop('material')
        r = audit_product(_product('resistors', params))
        self.assertTrue(r['ok'])  # required целы
        self.assertIn('temp_coef', r['missing_recommended'])
        self.assertLess(r['coverage'], 1.0)

    def test_missing_required_flags_not_ok(self):
        params = _full_resistor().parameters
        params.pop('resistance')
        r = audit_product(_product('resistors', params))
        self.assertFalse(r['ok'])
        self.assertIn('resistance', r['missing_required'])

    def test_missing_structural_field_flags_not_ok(self):
        prod = _product('resistors', _full_resistor().parameters, part_number='')
        r = audit_product(prod)
        self.assertFalse(r['ok'])
        self.assertIn('part_number', r['missing_structural'])

    def test_param_satisfied_by_model_field(self):
        # 'mounting' отсутствует в params, но есть как модельное поле
        params = _full_resistor().parameters
        params.pop('mounting')
        prod = _product('resistors', params)
        prod.mounting = 'THT'
        r = audit_product(prod)
        self.assertNotIn('mounting', r['missing_required'])

    def test_unknown_category_returns_none(self):
        self.assertIsNone(audit_product(_product('smartphones', {'ram': '8 ГБ'})))


class AuditCatalogTests(SimpleTestCase):
    def test_aggregate_counts_and_gaps(self):
        good = _full_resistor()
        bad = _product(
            'resistors', {'resistance': '1к', 'power': '1Вт', 'tolerance': '5%', 'mounting': 'SMD'}
        )
        report = audit_catalog([good, bad])
        cat = report['categories']['resistors']
        self.assertEqual(cat['products'], 2)
        self.assertEqual(cat['full_ok'], 2)  # оба имеют все required + структурные
        # у bad нет recommended → попадают в recommended_gaps
        self.assertIn('temp_coef', cat['recommended_gaps'])
        self.assertEqual(cat['recommended_gaps']['temp_coef'], 1)
        self.assertEqual(report['totals']['products'], 2)

    def test_required_gap_tracked(self):
        bad = _product('capacitors', {'mounting': 'SMD'})  # нет capacitance/voltage
        report = audit_catalog([bad])
        cat = report['categories']['capacitors']
        self.assertEqual(cat['missing_required_products'], 1)
        self.assertIn('capacitance', cat['required_gaps'])

    def test_schemas_cover_all_reb_categories(self):
        expected = {
            'resistors',
            'capacitors',
            'transistors',
            'ics',
            'diodes',
            'inductors',
            'connectors',
            'relays',
        }
        self.assertTrue(expected.issubset(set(CATEGORY_SCHEMAS)))
