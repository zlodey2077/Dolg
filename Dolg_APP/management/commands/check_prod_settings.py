"""Сторожевая команда: блокирует старт сервиса с небезопасным prod-конфигом.

Запускается в entrypoint.sh ДО gunicorn. Возвращает exit-code != 0 если
любой из нарушающих чеков сработал → docker-compose не поднимает web.

Локально (DEBUG=True) — команда тихо проходит, чтобы dev-цикл не страдал.
"""

import os
import sys

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Production-readiness assertions: SECRET_KEY, ALLOWED_HOSTS, DEBUG=False, etc.'

    def handle(self, *args, **opts):
        if settings.DEBUG:
            self.stdout.write(self.style.NOTICE('DEBUG=True — production assertions skipped (dev mode).'))
            return

        errors = []

        # 1. SECRET_KEY — не дефолтный
        default_key = 'django-insecure-local-development-key-change-me'
        if settings.SECRET_KEY == default_key:
            errors.append(
                'SECRET_KEY использует дефолт. Сгенерируйте свой:\n'
                '   python -c "from django.core.management.utils '
                'import get_random_secret_key; print(get_random_secret_key())"'
            )

        # 2. ALLOWED_HOSTS — не пустой
        if not settings.ALLOWED_HOSTS:
            errors.append('ALLOWED_HOSTS пуст — Django откажет всем запросам.')

        # 3. Email backend — не console в проде (письма уходят в логи)
        if 'console' in settings.EMAIL_BACKEND.lower():
            errors.append(
                f'EMAIL_BACKEND={settings.EMAIL_BACKEND} — это console-backend, '
                'верификации email и заказы не будут отправляться. '
                'Поставьте smtp.EmailBackend или другой.'
            )

        # 4. SECRET_KEY — длина (Django generates 50 chars by default)
        if len(settings.SECRET_KEY) < 32:
            errors.append(
                f'SECRET_KEY всего {len(settings.SECRET_KEY)} символов — слишком короткий. Должен быть ≥ 32.'
            )

        # 5. Security headers активны (мы их сами проставляем в settings.py)
        if not getattr(settings, 'SECURE_HSTS_SECONDS', 0):
            errors.append('SECURE_HSTS_SECONDS=0 — HSTS отключён в проде.')

        if not getattr(settings, 'SESSION_COOKIE_SECURE', False):
            errors.append('SESSION_COOKIE_SECURE=False — куки уйдут по HTTP.')

        # 6. Anthropic API — warn, не блокируем (AI работает в demo-режиме)
        warnings = []
        if not getattr(settings, 'ANTHROPIC_API_KEY', ''):
            warnings.append(
                'ANTHROPIC_API_KEY не задан — AI-ассистент в demo-режиме '
                '(всем пользователям сообщается «AI временно недоступен»).'
            )

        # Вывод
        for w in warnings:
            self.stdout.write(self.style.WARNING('WARNING: ' + w))

        if errors:
            self.stdout.write(
                self.style.ERROR(f'\nERROR: Production-config непригоден ({len(errors)} ошибок):\n')
            )
            for i, err in enumerate(errors, 1):
                self.stdout.write(self.style.ERROR(f' {i}. {err}\n'))
            self.stdout.write(
                self.style.ERROR(
                    '\nИсправьте через переменные окружения / .env и попробуйте снова.\n'
                    'Если нужно ПРИНУДИТЕЛЬНО проигнорировать (НЕ в проде!) — установите '
                    'SKIP_PROD_CHECKS=1.\n'
                )
            )
            if os.getenv('SKIP_PROD_CHECKS') == '1':
                self.stdout.write(
                    self.style.WARNING(
                        'SKIP_PROD_CHECKS=1 — нарушения проигнорированы. На свой страх и риск.'
                    )
                )
                return
            sys.exit(1)

        self.stdout.write(self.style.SUCCESS('OK: Production config OK.'))
