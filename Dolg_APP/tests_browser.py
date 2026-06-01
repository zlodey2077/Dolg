import os
import unittest

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from knowledge.models import LearningLesson, LearningTrack

User = get_user_model()


@unittest.skipUnless(os.environ.get('RUN_BROWSER_E2E') == '1', 'RUN_BROWSER_E2E=1 is required')
class ImportReviewLearningBrowserSmoke(StaticLiveServerTestCase):
    """Browser smoke for the demo path: CAD import -> review -> learning."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        try:
            from playwright.sync_api import sync_playwright
            cls._playwright = sync_playwright().start()
            cls.browser = cls._playwright.chromium.launch(headless=True)
        except Exception as exc:  # pragma: no cover - depends on local browser install
            try:
                cls._playwright.stop()
            except Exception:
                pass
            raise unittest.SkipTest(f'Playwright browser is not available: {exc}') from exc

    @classmethod
    def tearDownClass(cls):
        try:
            cls.browser.close()
            cls._playwright.stop()
        finally:
            super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user('browser-smoke', 'browser@example.com', 'pw')
        track = LearningTrack.objects.create(
            title='Диагностика простых схем',
            slug='diagnostika-prostyh-shem',
            summary='Ошибки простых схем превращаются в практикум.',
            level='basic',
            order=1,
            is_published=True,
        )
        LearningLesson.objects.create(
            track=track,
            title='Нет GND и плавающие узлы',
            slug='diagnostics-no-ground',
            summary='Как найти и исправить схему без опорной точки.',
            theory='Добавьте GND, повторите расчет и запустите review.',
            order=1,
            is_published=True,
        )
        self.client.force_login(self.user)
        self.client.get('/cad/')

    def _context(self):
        context = self.browser.new_context(base_url=self.live_server_url)
        cookies = []
        for name in (settings.SESSION_COOKIE_NAME, settings.CSRF_COOKIE_NAME):
            morsel = self.client.cookies.get(name)
            if morsel:
                cookies.append({
                    'name': name,
                    'value': morsel.value,
                    'url': self.live_server_url,
                })
        context.add_cookies(cookies)
        return context

    def test_import_review_learning_path(self):
        context = self._context()
        page = context.new_page()
        page.goto('/cad/')
        page.wait_for_selector('#importCadBtn')

        result = page.evaluate("""async () => {
            const csrf = document.cookie.split('; ')
                .find(row => row.startsWith('csrftoken='))
                ?.split('=')[1] || '';
            const response = await fetch('/cad/api/import/', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
                credentials: 'same-origin',
                body: JSON.stringify({
                    format: 'ltspice',
                    source: 'V1 in out DC 5\\nR1 out in 1k',
                    save_project: true,
                    name: 'Browser import without GND'
                })
            });
            return await response.json();
        }""")

        self.assertTrue(result['ok'])
        self.assertIn('saved_review', result)
        self.assertIn('preview', result)
        self.assertTrue(result['learning_suggestions'])

        page.goto(result['saved_review']['url'])
        page.wait_for_selector('.learning-review')
        self.assertIn('Learning by Review', page.text_content('body'))
        self.assertIn('Нет GND', page.text_content('body'))

        page.goto('/knowledge/learning/')
        page.wait_for_selector('.learning-hero')
        self.assertIn('Диагностика', page.text_content('body'))
        context.close()
