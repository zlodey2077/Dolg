"""Аудит покрытия изображений каталога по категориям и типам источника.

Лёгкий (не открывает файлы): классифицирует картинку каждого продукта по политике
источника (real / placeholder / missing / problem) и сводит по категориям — чтобы
видеть, где каталог держится на сгенерированных заглушках, а где нет картинок.

    python manage.py audit_catalog_media
    python manage.py audit_catalog_media --json
    python manage.py audit_catalog_media --strict   # missing/problem → ненулевой код
"""

import json

from django.core.management.base import BaseCommand, CommandError

from shop.models import Product
from shop.services.media_quality import media_coverage_by_category


class Command(BaseCommand):
    help = 'Покрытие изображений каталога по категориям (real/placeholder/missing/problem).'

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', help='Полный отчёт в JSON.')
        parser.add_argument('--strict', action='store_true', help='missing/problem → ненулевой код.')

    def handle(self, *args, **options):
        products = Product.objects.select_related('category').all()
        report = media_coverage_by_category(products)

        if options['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            self._print_human(report)

        totals = report['totals']
        if options['strict'] and (totals['missing'] or totals['problem']):
            raise CommandError(
                f'Изображения: missing={totals["missing"]}, problem={totals["problem"]} — каталог неполон.'
            )

    def _print_human(self, report):
        t = report['totals']
        self.stdout.write(self.style.MIGRATE_HEADING('Аудит изображений каталога'))
        self.stdout.write(
            f'Всего: {t["total"]} · real: {t["real"]} · заглушки: {t["placeholder"]} · '
            f'нет: {t["missing"]} · проблемные: {t["problem"]} · real-покрытие: {t["real_coverage"] * 100:.0f}%\n'
        )
        for slug, b in report['categories'].items():
            line = (
                f'  {slug:<13} [{b["total"]:>3}] real={b["real"]:>3} '
                f'заглушки={b["placeholder"]:>3} нет={b["missing"]:>2} '
                f'real-покрытие={b["real_coverage"] * 100:>3.0f}%'
            )
            if b['problem']:
                line += f'  ⚠ проблемных={b["problem"]}'
            self.stdout.write(line)
