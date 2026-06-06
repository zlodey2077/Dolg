"""Аудит покрытия параметров каталога по per-category схеме.

Показывает по каждой РЭБ-категории: сколько продуктов полностью валидны
(все required + структурные поля), среднее покрытие (required+recommended) и
ТОП-пробелы (какие рекомендуемые параметры чаще всего отсутствуют) — чтобы
прицельно дотягивать каталог до эталона, а не вслепую.

    python manage.py audit_catalog_schema
    python manage.py audit_catalog_schema --json
    python manage.py audit_catalog_schema --category capacitors
    python manage.py audit_catalog_schema --strict   # required-пробелы → ошибка
"""

import json

from django.core.management.base import BaseCommand, CommandError

from shop.models import Product
from shop.services.catalog_schema import CATEGORY_SCHEMAS, audit_catalog


class Command(BaseCommand):
    help = 'Аудит покрытия параметров каталога по per-category схеме (required/recommended).'

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', help='Вывести полный отчёт в JSON.')
        parser.add_argument('--strict', action='store_true', help='required-пробелы → ненулевой код выхода.')
        parser.add_argument('--category', help='Ограничить одной категорией (slug).')

    def handle(self, *args, **options):
        category = options.get('category')
        if category and category not in CATEGORY_SCHEMAS:
            raise CommandError(
                f'Нет схемы для категории {category!r}. Доступны: {", ".join(sorted(CATEGORY_SCHEMAS))}'
            )

        slugs = [category] if category else list(CATEGORY_SCHEMAS.keys())
        qs = Product.objects.select_related('category').filter(category__slug__in=slugs)
        report = audit_catalog(qs)

        required_gaps_total = sum(len(bucket['required_gaps']) for bucket in report['categories'].values())

        if options['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            self._print_human(report)

        if options['strict'] and required_gaps_total:
            raise CommandError(
                f'Найдены required-пробелы в {required_gaps_total} параметр(ах) — каталог неполон.'
            )

    def _print_human(self, report):
        totals = report['totals']
        self.stdout.write(self.style.MIGRATE_HEADING('Аудит схемы каталога'))
        self.stdout.write(
            f'Всего проверено: {totals["products"]} · полностью валидны: {totals["full_ok"]} · '
            f'среднее покрытие: {totals["avg_coverage"] * 100:.0f}%\n'
        )
        for slug, bucket in report['categories'].items():
            line = (
                f'  {slug:<13} [{bucket["products"]:>3}] '
                f'ok={bucket["full_ok"]:>3}  покрытие={bucket["avg_coverage"] * 100:>3.0f}%'
            )
            if bucket['missing_required_products']:
                line += f'  ⚠ required-пробелы у {bucket["missing_required_products"]}'
            self.stdout.write(line)
            if bucket['required_gaps']:
                gaps = ', '.join(f'{k}×{c}' for k, c in bucket['required_gaps'].items())
                self.stdout.write(self.style.WARNING(f'      required: {gaps}'))
            if bucket['recommended_gaps']:
                gaps = ', '.join(f'{k}×{c}' for k, c in list(bucket['recommended_gaps'].items())[:6])
                self.stdout.write(f'      recommended: {gaps}')
