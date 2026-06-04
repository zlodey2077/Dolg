"""Создаёт начальный набор объявлений для информационного канала чата.

Идемпотентно: при повторных запусках обновляет существующие по title.
Запуск:
    python manage.py seed_announcements
    python manage.py seed_announcements --reset   # удалить все перед созданием
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from Dolg_APP.models import Announcement

User = get_user_model()


# (title, body, level, is_pinned, expires_days_from_now=None)
SEED_ANNOUNCEMENTS = [
    (
        '💬 Запущена система чатов',
        'Теперь в DOLG можно обсуждать схемы и компоненты в публичном чате. '
        'Доступно всем зарегистрированным. Pro-юзеры получают Markdown + любые emoji-реакции.',
        'info',
        True,
        None,
    ),
    (
        '🏢 Enterprise: приватные беседы для команды',
        'В разделе «Беседы» доступны приватные каналы для членов организации. '
        'Поддерживаются @упоминания, threaded-ответы, архив, AJAX-обновление.',
        'info',
        True,
        None,
    ),
    (
        '🤖 AI-ассистент теперь содержит ML-pipeline',
        'DRC++, рекомендация компонентов и объяснение схемы — теперь как кнопки '
        'в правом нижнем 🤖. Панель тянется за угол, ответы пишутся в чат с историей.',
        'info',
        False,
        None,
    ),
    (
        '⚠ Тестовый режим: реальные платежи отключены',
        'Подписки Pro и Enterprise сейчас работают в demo-режиме. '
        'Активация — через билинг (mock-Stripe). Реальная оплата появится в production-релизе.',
        'warning',
        False,
        None,
    ),
]


class Command(BaseCommand):
    help = 'Создаёт seed-объявления для сайдбара информационного канала чата.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Удалить все Announcement перед созданием.')
        parser.add_argument('--owner', default='admin', help='Логин автора объявлений (по умолчанию admin).')

    def handle(self, *args, **opts):
        try:
            author = User.objects.get(username=opts['owner'])
        except User.DoesNotExist:
            author = None
            self.stderr.write(
                self.style.WARNING(f"Пользователь '{opts['owner']}' не найден — author останется None.")
            )

        if opts['reset']:
            deleted, _ = Announcement.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'Удалено объявлений: {deleted}'))

        created, updated = 0, 0
        for title, body, level, pinned, expires_days in SEED_ANNOUNCEMENTS:
            expires_at = (timezone.now() + timedelta(days=expires_days)) if expires_days else None
            obj, is_created = Announcement.objects.update_or_create(
                title=title,
                defaults={
                    'body': body,
                    'level': level,
                    'is_pinned': pinned,
                    'is_published': True,
                    'expires_at': expires_at,
                    'author': author,
                },
            )
            if is_created:
                created += 1
            else:
                updated += 1

        total = Announcement.objects.count()
        self.stdout.write(
            self.style.SUCCESS(f'OK: создано {created}, обновлено {updated}. Всего объявлений: {total}.')
        )
