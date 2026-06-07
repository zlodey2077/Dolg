from django.test import TestCase, override_settings


@override_settings(ALLOWED_HOSTS=['*'])
class GuestTrackingTests(TestCase):
    def test_malformed_guest_token_404(self):
        response = self.client.get('/orders/track/not-a-valid-token/')
        self.assertEqual(response.status_code, 404)
