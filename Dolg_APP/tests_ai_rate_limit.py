"""Tests for AI chat rate limiting (per-call interval + per-minute tier-aware)."""

from __future__ import annotations

import time
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase

from Dolg_APP.views import AI_PER_MINUTE_LIMITS, _ai_rate_limit


def _req(user):
    return SimpleNamespace(session={}, user=user)


class AiRateLimitTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.free = User.objects.create_user('rl_free', password='x')
        self.staff = User.objects.create_user('rl_staff', password='x', is_staff=True)

    def _bypass_interval(self, request):
        # Сдвигаем последний вызов в прошлое, чтобы не упереться в per-call интервал.
        request.session['_ai_last_call_at'] = time.time() - 10

    def test_per_call_interval_blocks_rapid_second_call(self):
        request = _req(self.free)
        self.assertFalse(_ai_rate_limit(request))  # 1-й — ок
        self.assertTrue(_ai_rate_limit(request))  # сразу 2-й — заблокирован интервалом

    def test_per_minute_limit_for_free(self):
        request = _req(self.free)
        limit = AI_PER_MINUTE_LIMITS['free']
        allowed = 0
        for _ in range(limit + 5):
            self._bypass_interval(request)
            if not _ai_rate_limit(request):
                allowed += 1
        self.assertEqual(allowed, limit)  # ровно limit прошло, остальное отсечено

    def test_staff_unlimited_no_per_minute_cap(self):
        request = _req(self.staff)
        allowed = 0
        for _ in range(AI_PER_MINUTE_LIMITS['free'] + 10):
            self._bypass_interval(request)
            if not _ai_rate_limit(request):
                allowed += 1
        # unlimited (staff) не упирается в per-minute
        self.assertGreater(allowed, AI_PER_MINUTE_LIMITS['free'])
