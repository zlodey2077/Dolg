from django.apps import AppConfig


class ShopConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'shop'

    def ready(self):
        # Регистрируем signals (merge guest-cart на login).
        from . import signals  # noqa: F401
