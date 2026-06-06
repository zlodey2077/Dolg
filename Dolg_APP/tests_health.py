"""Tests for the /healthz liveness/readiness probe."""

from __future__ import annotations

from django.test import Client, TestCase, override_settings


@override_settings(ALLOWED_HOSTS=['*'])
class HealthzTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_healthz_ok_anonymous(self):
        """Проба анонимна и возвращает 200 с проверками БД и кеша."""
        resp = self.client.get('/healthz')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['checks']['database'], 'ok')
        self.assertEqual(data['checks']['cache'], 'ok')

    def test_healthz_not_cached(self):
        resp = self.client.get('/healthz')
        self.assertIn('no-cache', resp.headers.get('Cache-Control', ''))
