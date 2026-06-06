"""Tests: Prometheus /metrics/ доступен только staff или по METRICS_TOKEN."""

from __future__ import annotations

import unittest

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

METRICS_URL = '/metrics'


@unittest.skipUnless(getattr(settings, '_HAS_PROMETHEUS', False), 'django-prometheus не установлен')
class MetricsGuardTests(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.staff = User.objects.create_user('opsadmin', password='x', is_staff=True)
        self.plain = User.objects.create_user('regular', password='x')

    def test_anonymous_forbidden(self):
        self.assertEqual(self.client.get(METRICS_URL).status_code, 403)

    def test_non_staff_forbidden(self):
        self.client.force_login(self.plain)
        self.assertEqual(self.client.get(METRICS_URL).status_code, 403)

    def test_staff_allowed(self):
        self.client.force_login(self.staff)
        resp = self.client.get(METRICS_URL)
        self.assertEqual(resp.status_code, 200)

    @override_settings(METRICS_TOKEN='secret-scrape-xyz')
    def test_valid_bearer_token_allowed(self):
        resp = self.client.get(METRICS_URL, HTTP_AUTHORIZATION='Bearer secret-scrape-xyz')
        self.assertEqual(resp.status_code, 200)

    @override_settings(METRICS_TOKEN='secret-scrape-xyz')
    def test_valid_query_token_allowed(self):
        resp = self.client.get(METRICS_URL, {'token': 'secret-scrape-xyz'})
        self.assertEqual(resp.status_code, 200)

    @override_settings(METRICS_TOKEN='secret-scrape-xyz')
    def test_wrong_token_forbidden(self):
        resp = self.client.get(METRICS_URL, HTTP_AUTHORIZATION='Bearer nope')
        self.assertEqual(resp.status_code, 403)

    def test_token_ignored_when_unset(self):
        # METRICS_TOKEN пуст (default) → токен не открывает доступ, только staff.
        resp = self.client.get(METRICS_URL, HTTP_AUTHORIZATION='Bearer anything')
        self.assertEqual(resp.status_code, 403)
