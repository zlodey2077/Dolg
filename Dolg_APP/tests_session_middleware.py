from types import SimpleNamespace

from django.http import HttpResponse
from django.test import SimpleTestCase

from .middleware import AnonSessionExpiryMiddleware


class DummySession:
    def __init__(self, *, session_key=None, modified=False):
        self.session_key = session_key
        self.modified = modified
        self.expiry = None

    def get_expiry_age(self):
        return 14 * 24 * 3600

    def set_expiry(self, value):
        self.expiry = value
        self.modified = True


class AnonSessionExpiryMiddlewareTests(SimpleTestCase):
    def test_does_not_create_session_for_plain_guest_page(self):
        session = DummySession(session_key=None, modified=False)
        request = SimpleNamespace(
            path='/',
            user=SimpleNamespace(is_authenticated=False),
            session=session,
        )

        response = AnonSessionExpiryMiddleware(lambda _request: HttpResponse('ok'))(request)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(session.expiry)
        self.assertFalse(session.modified)

    def test_sets_short_expiry_for_existing_guest_session(self):
        session = DummySession(session_key='guest-session', modified=False)
        request = SimpleNamespace(
            path='/',
            user=SimpleNamespace(is_authenticated=False),
            session=session,
        )

        AnonSessionExpiryMiddleware(lambda _request: HttpResponse('ok'))(request)

        self.assertEqual(session.expiry, AnonSessionExpiryMiddleware.GUEST_TTL_SECONDS)
