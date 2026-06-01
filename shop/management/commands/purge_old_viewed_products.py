"""Удаляет ViewedProduct старше N дней (default: 90)."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from shop.models import ViewedProduct


class Command(BaseCommand):
    help = 'Удаляет ViewedProduct старше N дней (default: 90).'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=90)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        cutoff = timezone.now() - timedelta(days=days)
        qs = ViewedProduct.objects.filter(viewed_at__lt=cutoff)
        n = qs.count()
        if dry_run:
            self.stdout.write(f'[DRY-RUN] Будет удалено: {n} записей (viewed_at < {cutoff.isoformat()})')
            return
        if n == 0:
            self.stdout.write('Нет записей для удаления.')
            return
        qs.delete()
        self.stdout.write(self.style.SUCCESS(f'Удалено: {n} записей.'))
