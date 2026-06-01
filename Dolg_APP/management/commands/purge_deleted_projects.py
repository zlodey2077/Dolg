"""Физически удаляет soft-deleted проекты старше N дней.

Запуск:
    python manage.py purge_deleted_projects                # default 30 дней
    python manage.py purge_deleted_projects --days 7
    python manage.py purge_deleted_projects --dry-run      # только подсчёт
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from Dolg_APP.models import SchematicProject


class Command(BaseCommand):
    help = 'Физически удаляет soft-deleted проекты старше N дней (по умолчанию 30).'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30,
                            help='Возраст в днях, после которого удалять (default: 30).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Только показать, что будет удалено, без изменений.')

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        cutoff = timezone.now() - timedelta(days=days)

        qs = SchematicProject.all_objects.filter(
            deleted_at__isnull=False, deleted_at__lt=cutoff,
        )
        n = qs.count()

        if dry_run:
            self.stdout.write(f'[DRY-RUN] Будет удалено: {n} проектов (deleted_at < {cutoff.isoformat()})')
            for p in qs[:20]:
                self.stdout.write(f'  {p.id}\t{p.user.username}\t{p.name}\t(deleted {p.deleted_at})')
            if n > 20:
                self.stdout.write(f'  ... и ещё {n - 20}')
            return

        if n == 0:
            self.stdout.write('Нет проектов для удаления.')
            return

        deleted, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(f'Физически удалено: {deleted} объектов (включая каскады).'))
