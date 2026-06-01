from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
    verbose_name = 'Управление аккаунтами'

    def ready(self):
        # Регистрируем сигналы при старте приложения
        from . import signals  # noqa: F401
