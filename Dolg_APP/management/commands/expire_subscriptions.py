"""Понижает истёкшие Subscription'ы в Free.

Запуск (рекомендуется по cron ежедневно):
    python manage.py expire_subscriptions
    python manage.py expire_subscriptions --dry-run

Логика:
- status='cancelled' + period_end < now → status='expired', tier='free'
- status='trial'     + period_end < now → status='expired', tier='free'
- status='active'    + period_end < now + auto_renew=False → status='expired', tier='free'
  (если auto_renew=True — оставляем активным; в production здесь Stripe webhook
   продлевает period_end автоматически).
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from Dolg_APP.models import Subscription


class Command(BaseCommand):
    help = 'Помечает истёкшие подписки как expired + понижает tier до free.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        now = timezone.now()

        qs = Subscription.objects.filter(
            period_end__lt=now,
            tier='pro',
        ).filter(
            Q(status__in=['trial', 'cancelled']) |
            Q(status='active', auto_renew=False)
        )

        n = qs.count()
        if dry_run:
            self.stdout.write(f'[DRY-RUN] Будет понижено: {n} подписок')
            for s in qs[:20]:
                self.stdout.write(f'  {s.user.username}: {s.status}/{s.tier}, period_end={s.period_end}')
            return

        if n == 0:
            self.stdout.write('Нет подписок для деградации.')
            return

        qs.update(status='expired', tier='free')
        self.stdout.write(self.style.SUCCESS(f'Понижено в Free: {n} подписок.'))
