import json

from django.core.management.base import BaseCommand

from shop.models import Category, Product
from shop.services.reb_catalog_quality import normalize_reb_product


class Command(BaseCommand):
    help = 'Normalize REB catalog engineering metadata: mounting, ratings, datasheets and part numbers.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--force', action='store_true', help='Re-infer fields even when a weak value is already present.')
        parser.add_argument('--limit', type=int, default=0)
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **options):
        qs = (
            Product.objects
            .select_related('category')
            .filter(category__slug__in=Category.REB_SLUGS)
            .order_by('category__slug', 'slug')
        )
        if options['limit']:
            qs = qs[:max(1, options['limit'])]

        report = {
            'ok': True,
            'dry_run': options['dry_run'],
            'force': options['force'],
            'scanned': 0,
            'changed': 0,
            'changes_by_category': {},
            'items': [],
            'warnings': [],
        }

        for product in qs:
            report['scanned'] += 1
            result = normalize_reb_product(product, force=options['force'])
            if not result.changed:
                continue

            report['changed'] += 1
            slug = product.category.slug
            report['changes_by_category'][slug] = report['changes_by_category'].get(slug, 0) + 1
            item = {
                'slug': product.slug,
                'category': slug,
                'part_number': product.part_number,
                'changes': sorted(result.changes.keys()),
                'warnings': result.warnings,
            }
            report['items'].append(item)
            for warning in result.warnings:
                report['warnings'].append(f'{product.slug}: {warning}')

            if not options['dry_run']:
                product.save(update_fields=[
                    'part_number',
                    'package_type',
                    'datasheet_url',
                    'parameters',
                    'updated_at',
                ])

        if options['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            return

        self.stdout.write(self.style.SUCCESS(
            f'REB catalog normalization: scanned={report["scanned"]}, changed={report["changed"]}, '
            f'dry_run={report["dry_run"]}'
        ))
        for category, count in sorted(report['changes_by_category'].items()):
            self.stdout.write(f'  - {category}: {count}')
        for item in report['items'][:30]:
            self.stdout.write(f"  * {item['slug']}: {', '.join(item['changes'])}")
        if len(report['items']) > 30:
            self.stdout.write(f'  ... {len(report["items"]) - 30} more')
