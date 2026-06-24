from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from .middleware import RequestBodyLimitMiddleware


class RequestBodyLimitMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(DOLG_MAX_JSON_BODY_BYTES=16)
    def test_rejects_oversized_json_before_view(self):
        called = False

        def view(_request):
            nonlocal called
            called = True
            return JsonResponse({'ok': True})

        request = self.factory.post(
            '/api/sim/server-engines/recommend/',
            data='{"payload":"' + ('x' * 64) + '"}',
            content_type='application/json',
        )

        response = RequestBodyLimitMiddleware(view)(request)

        self.assertEqual(response.status_code, 413)
        self.assertFalse(called)

    @override_settings(DOLG_MAX_JSON_BODY_BYTES=128)
    def test_allows_small_api_body(self):
        def view(_request):
            return JsonResponse({'ok': True})

        request = self.factory.post(
            '/api/sim/server-engines/recommend/',
            data='{"payload":"ok"}',
            content_type='application/json',
        )

        response = RequestBodyLimitMiddleware(view)(request)

        self.assertEqual(response.status_code, 200)
