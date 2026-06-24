from types import SimpleNamespace
from unittest.mock import patch

from django.db import DatabaseError
from django.test import SimpleTestCase

from .context_processors import cart_count


class CartContextProcessorTests(SimpleTestCase):
    def test_cart_count_fails_soft_when_database_is_unavailable(self):
        request = SimpleNamespace(
            user=SimpleNamespace(is_authenticated=False),
            session=SimpleNamespace(session_key='guest-session'),
        )

        with patch('shop.context_processors.CartItem.objects.filter', side_effect=DatabaseError):
            result = cart_count(request)

        self.assertEqual(result, {'cart_count': 0})
        self.assertEqual(request._cart_count_cache, 0)
