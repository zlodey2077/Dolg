# Тестовый settings: тонкий обёртка над settings.py с быстрыми сейлсами,
# которая нужна CI (.github/workflows/django.yml). Локально pytest умеет
# жить и на основном settings.py через FAST_TESTS=1.
from .settings import *

# Хеш паролей быстрее по умолчанию (MD5 не для прода, для теста).
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

# В памяти кэш — без Redis/Memcached.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'dolg-tests',
    }
}

# Не отправляем email, не таскаем CSP-фильтры в тестах.
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# Признак тестового окружения, читается из settings.py guard на 0a SECRET_KEY.
IS_TESTING = True
