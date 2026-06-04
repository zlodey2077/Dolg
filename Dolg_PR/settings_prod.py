import os

from .settings import *

DEBUG = False

STATIC_ROOT = BASE_DIR / 'staticfiles'

if os.getenv('POSTGRES_DB'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('POSTGRES_DB'),
            'USER': os.getenv('POSTGRES_USER', ''),
            'PASSWORD': os.getenv('POSTGRES_PASSWORD', ''),
            'HOST': os.getenv('POSTGRES_HOST', 'localhost'),
            'PORT': os.getenv('POSTGRES_PORT', '5432'),
        }
    }

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        # Структурированный формат «время | уровень | logger | message [extra-fields]».
        # Достаточно для grep-друженного парсинга в docker logs или Loki/ELK,
        # без необходимости тянуть structlog как зависимость.
        'structured': {
            'format': '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            'datefmt': '%Y-%m-%dT%H:%M:%S%z',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'structured',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': os.getenv('LOG_LEVEL', 'INFO'),
    },
    'loggers': {
        # Все security-события Django (CSRF, suspicious requests) — WARNING+.
        'django.security': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        # 5xx ошибки тоже отдельно с WARNING-порогом.
        'django.request': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        # Наши приложения дефолтно на INFO.
        'Dolg_APP': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'shop': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'accounts': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'orders': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'knowledge': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}
