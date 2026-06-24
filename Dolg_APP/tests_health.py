"""Tests for health liveness/readiness probes."""

from __future__ import annotations

from django.test import Client, TestCase, override_settings


@override_settings(ALLOWED_HOSTS=['*'])
class HealthzTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_healthz_ok_anonymous(self):
        resp = self.client.get('/healthz')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['checks']['app'], 'ok')
        self.assertNotIn('database', data['checks'])

    def test_readyz_checks_dependencies(self):
        resp = self.client.get('/readyz')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['checks']['database'], 'ok')
        self.assertEqual(data['checks']['cache'], 'ok')

    def test_healthz_not_cached(self):
        resp = self.client.get('/healthz')
        self.assertIn('no-cache', resp.headers.get('Cache-Control', ''))
