"""Тесты Guest-сценария (незарегистрированный пользователь).

Покрывают:
- Доступ к публичным разделам (каталог, симулятор, CAD read-only, knowledge)
- Закрытость save/API endpoints для anonymous (302/403)
- Legal-страницы (/terms/, /privacy/, /cookies/)
- Footer-disclaimer и trademark notice
- Cookie-banner и auth-modal JS подключены
- AnonymizeIPMiddleware обнуляет последний октет без consent
"""

from django.test import TestCase, override_settings


@override_settings(ALLOWED_HOSTS=['*'])
class GuestPublicAccessTests(TestCase):
    """Что guest может открыть без логина — должно быть 200."""

    def test_index_accessible(self):
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_category_page_accessible(self):
        # Берём любую существующую категорию (в чистой test-БД может не быть GPU)
        from shop.models import Category

        cat = Category.objects.first()
        if cat is None:
            self.skipTest('no categories in DB')
        self.assertEqual(self.client.get(f'/category/{cat.slug}/').status_code, 200)

    def test_product_detail_accessible(self):
        # Любой продукт — берём первый из БД
        from shop.models import Product

        p = Product.objects.first()
        if p is None:
            self.skipTest('no products in DB')
        self.assertEqual(self.client.get(f'/product/{p.slug}/').status_code, 200)

    def test_search_accessible(self):
        self.assertEqual(self.client.get('/search/?q=resistor').status_code, 200)

    def test_cart_accessible(self):
        self.assertEqual(self.client.get('/cart/').status_code, 200)

    def test_simulation_accessible_for_guest(self):
        """Симулятор открыт для guest (read-only режим)."""
        self.assertEqual(self.client.get('/simulation/').status_code, 200)

    def test_cad_accessible_for_guest(self):
        """CAD теперь открыт для guest (раньше требовал login)."""
        self.assertEqual(self.client.get('/cad/').status_code, 200)

    def test_knowledge_accessible(self):
        self.assertEqual(self.client.get('/knowledge/').status_code, 200)


@override_settings(ALLOWED_HOSTS=['*'])
class GuestProtectedEndpointsTests(TestCase):
    """API и приватные view должны редиректить/блокировать guest."""

    def test_projects_list_redirects_to_login(self):
        r = self.client.get('/projects/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/accounts/login/', r.url)

    def test_account_profile_redirects(self):
        r = self.client.get('/accounts/profile/')
        self.assertEqual(r.status_code, 302)

    def test_api_projects_list_blocked(self):
        r = self.client.get('/projects/api/list/')
        # либо 302 на login, либо 403
        self.assertIn(r.status_code, (302, 403))

    def test_ai_endpoint_blocked(self):
        r = self.client.post('/api/ai/chat/', data={}, content_type='application/json')
        self.assertIn(r.status_code, (302, 403, 405))


@override_settings(ALLOWED_HOSTS=['*'])
class LegalPagesTests(TestCase):
    """Все три legal-страницы должны открываться без auth."""

    def test_terms(self):
        self.assertEqual(self.client.get('/terms/').status_code, 200)

    def test_privacy(self):
        self.assertEqual(self.client.get('/privacy/').status_code, 200)

    def test_cookies_policy(self):
        r = self.client.get('/cookies/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Политика использования cookies')
        self.assertContains(r, 'dolg_cookie_consent')


@override_settings(ALLOWED_HOSTS=['*'])
class FooterAndScriptsTests(TestCase):
    """Footer содержит обязательные legal-элементы и подключены guest-JS."""

    def setUp(self):
        self.response = self.client.get('/')
        self.html = self.response.content.decode('utf-8')

    def test_footer_has_dmca_email(self):
        self.assertIn('dmca@dolg.local', self.html)

    def test_footer_has_trademark_disclaimer(self):
        self.assertIn('trademarks', self.html.lower())

    def test_footer_has_cookies_link(self):
        self.assertIn('/cookies/', self.html)

    def test_cookie_banner_js_loaded(self):
        # Файл дважды переименован чтобы обойти агрессивные adblock-фильтры:
        # cookie-banner.js → cookie-notice.js → consent-ui.js
        # (uBlock на публичных доменах режет всё со словами banner/cookie/notice).
        self.assertIn('consent-ui.js', self.html)

    def test_auth_modal_js_loaded(self):
        self.assertIn('auth-modal.js', self.html)

    def test_save_cta_banner_js_loaded(self):
        self.assertIn('save-cta-banner.js', self.html)

    def test_body_has_guest_auth_marker(self):
        # data-user-auth="0" для guest
        self.assertIn('data-user-auth="0"', self.html)


@override_settings(ALLOWED_HOSTS=['*'])
class CadGuestReadOnlyTests(TestCase):
    """CAD-кнопки save/load/import помечены data-guest-locked для guest."""

    def setUp(self):
        self.response = self.client.get('/cad/')
        self.html = self.response.content.decode('utf-8')

    def test_cad_renders_for_guest(self):
        self.assertEqual(self.response.status_code, 200)

    def test_save_button_has_guest_lock(self):
        # saveBtn у guest получает data-guest-locked="1"
        self.assertIn('data-guest-locked', self.html)

    def test_guest_locked_count_at_least_three(self):
        # save, load, import — минимум 3 кнопки залочены
        self.assertGreaterEqual(self.html.count('data-guest-locked="1"'), 3)


@override_settings(ALLOWED_HOSTS=['*'])
class CartGuestFlowTests(TestCase):
    """Корзина показывает guest-aware кнопку checkout (register, не form-submit)."""

    def test_cart_guest_sees_register_button(self):
        # Сначала добавим что-то в корзину
        from shop.models import Product

        p = Product.objects.first()
        if p is None:
            self.skipTest('no products')
        self.client.post(f'/add-to-cart/{p.slug}/', {'quantity': 1})
        r = self.client.get('/cart/')
        self.assertEqual(r.status_code, 200)
        html = r.content.decode('utf-8')
        # guest-notice присутствует
        self.assertIn('cart-guest-notice', html)
        # Кнопка ведёт на регистрацию с ?next=
        self.assertIn('/accounts/register/?next=/orders/checkout/', html)


class AnonymizeIPMiddlewareTests(TestCase):
    """Middleware затирает последний октет IPv4 если нет consent на analytics."""

    def test_ipv4_anonymized_without_consent(self):
        from Dolg_APP.middleware import _anonymize_ipv4

        self.assertEqual(_anonymize_ipv4('192.168.1.42'), '192.168.1.0')
        self.assertEqual(_anonymize_ipv4('10.0.0.255'), '10.0.0.0')

    def test_ipv6_anonymized_without_consent(self):
        from Dolg_APP.middleware import _anonymize_ipv6

        # /64 truncation: первые 4 группы остаются, остальное → 0:0:0:0
        result = _anonymize_ipv6('2001:db8:1234:5678:abcd:ef01:2345:6789')
        self.assertEqual(result, '2001:db8:1234:5678:0:0:0:0')

    def test_ip_preserved_with_analytics_consent(self):
        """С consent.analytics=true оригинал остаётся."""
        from Dolg_APP.middleware import AnonymizeIPMiddleware

        captured = {}

        def fake_response(request):
            captured['ip'] = request.META.get('REMOTE_ADDR', '')
            from django.http import HttpResponse

            return HttpResponse('ok')

        mw = AnonymizeIPMiddleware(fake_response)
        from django.test import RequestFactory

        rf = RequestFactory()
        request = rf.get('/')
        request.META['REMOTE_ADDR'] = '192.168.1.42'
        # Имитируем cookie с consent.analytics=true
        request.COOKIES['dolg_cookie_consent'] = '{"analytics": true, "marketing": false}'
        mw(request)
        self.assertEqual(captured['ip'], '192.168.1.42')

    def test_ip_anonymized_without_cookie(self):
        from Dolg_APP.middleware import AnonymizeIPMiddleware

        captured = {}

        def fake_response(request):
            captured['ip'] = request.META.get('REMOTE_ADDR', '')
            from django.http import HttpResponse

            return HttpResponse('ok')

        mw = AnonymizeIPMiddleware(fake_response)
        from django.test import RequestFactory

        rf = RequestFactory()
        request = rf.get('/')
        request.META['REMOTE_ADDR'] = '192.168.1.42'
        # без cookie
        mw(request)
        self.assertEqual(captured['ip'], '192.168.1.0')
