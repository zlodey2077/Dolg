from django.apps import AppConfig


class RomanAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'Dolg_APP'

    def ready(self):
        # Регистрируем custom-checks (W001: multi-line {# #} в шаблонах).
        # Импорт делает register-side-effect — реальный check вызывается из
        # manage.py check / runserver автоматически.
        from . import checks  # noqa: F401
