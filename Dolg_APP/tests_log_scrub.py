"""Tests for sensitive-data log scrubbing."""

from __future__ import annotations

import logging

from django.test import SimpleTestCase

from Dolg_APP.log_scrub import SensitiveDataFilter, scrub


class ScrubTests(SimpleTestCase):
    def test_redacts_hosted_llm_style_key(self):
        out = scrub('using key sk-local-abc123DEF456ghi in request')
        self.assertNotIn('abc123DEF456ghi', out)
        self.assertIn('sk-***', out)

    def test_redacts_bearer_token(self):
        out = scrub('Authorization: Bearer abcDEF123456token')
        self.assertNotIn('abcDEF123456token', out)
        self.assertIn('Bearer ***', out)

    def test_redacts_password_and_token_kv(self):
        self.assertIn('***', scrub('password=SuperSecret1'))
        self.assertNotIn('SuperSecret1', scrub('password=SuperSecret1'))
        self.assertNotIn('zzz999token1', scrub('token: zzz999token1'))

    def test_redacts_email_and_csrftoken(self):
        self.assertEqual(scrub('user alice@example.com'), 'user ***@***')
        self.assertIn('csrftoken=***', scrub('Cookie: csrftoken=AbC123; other=1'))

    def test_plain_text_untouched(self):
        self.assertEqual(scrub('просто обычное сообщение лога'), 'просто обычное сообщение лога')


class FilterTests(SimpleTestCase):
    def _record(self, msg, args=None):
        return logging.LogRecord('t', logging.INFO, __file__, 1, msg, args, None)

    def test_filter_scrubs_msg_and_keeps_record(self):
        f = SensitiveDataFilter()
        rec = self._record('login with password=hunter2')
        self.assertTrue(f.filter(rec))  # запись не отбрасывается
        self.assertNotIn('hunter2', rec.msg)

    def test_filter_scrubs_string_args(self):
        f = SensitiveDataFilter()
        rec = self._record('key %s', ('sk-ant-secret123456',))
        f.filter(rec)
        self.assertNotIn('secret123456', rec.args[0])

    def test_filter_never_raises_on_weird_args(self):
        f = SensitiveDataFilter()
        rec = self._record('value %d', (42,))
        self.assertTrue(f.filter(rec))
