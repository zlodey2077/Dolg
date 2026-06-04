import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from shop.models import Category, Product
from shop.services.datasheet_intelligence import (
    build_product_datasheet_record,
    cache_path_for_url,
    dependency_status,
)


class Command(BaseCommand):
    help = 'Extracts lightweight datasheet intelligence into Product.parameters.datasheet_extracted.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=20)
        parser.add_argument('--all', action='store_true', help='Process all matching REB products.')
        parser.add_argument(
            '--missing-only', action='store_true', help='Skip products that already have datasheet_extracted.'
        )
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--live-refresh', action='store_true')
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **options):
        limit = max(1, options['limit'])
        products_qs = (
            Product.objects.select_related('category')
            .filter(category__slug__in=Category.REB_SLUGS)
            .exclude(datasheet_url='')
            .order_by('slug')
        )
        if options['missing_only']:
            products_qs = [
                product
                for product in products_qs
                if not (product.parameters or {}).get('datasheet_extracted')
            ]
        if options['all']:
            products = list(products_qs)
        elif isinstance(products_qs, list):
            products = products_qs[:limit]
        else:
            products = list(products_qs[:limit])
        report = {
            'ok': True,
            'dry_run': options['dry_run'],
            'live_refresh': options['live_refresh'],
            'missing_only': options['missing_only'],
            'all': options['all'],
            'dependencies': dependency_status(),
            'processed': [],
            'warnings': [],
        }

        for product in products:
            cache_path = cache_path_for_url(settings.MEDIA_ROOT, product.datasheet_url)
            source = 'metadata_fallback'
            if cache_path.exists():
                record = build_product_datasheet_record(product, pdf_path=cache_path)
                source = 'cache'
            elif options['live_refresh']:
                downloaded = self._download(product.datasheet_url, cache_path)
                if downloaded:
                    record = build_product_datasheet_record(product, pdf_path=cache_path)
                    source = 'live'
                else:
                    record = build_product_datasheet_record(product)
                    report['warnings'].append(f'{product.slug}: live download failed, used metadata fallback')
            else:
                record = build_product_datasheet_record(product)
                report['warnings'].append(f'{product.slug}: no cached PDF, used metadata fallback')

            params = dict(product.parameters or {})
            params['datasheet_extracted'] = record
            item = {
                'slug': product.slug,
                'part_number': product.part_number,
                'source': source,
                'confidence': record.get('confidence'),
                'fields_found': [key for key, value in (record.get('fields') or {}).items() if value],
            }
            report['processed'].append(item)
            if not options['dry_run']:
                product.parameters = params
                product.save(update_fields=['parameters', 'updated_at'])

        if options['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Datasheet intelligence processed: {len(report["processed"])}; '
                    f'dry_run={report["dry_run"]}; live_refresh={report["live_refresh"]}'
                )
            )
            for item in report['processed']:
                self.stdout.write(
                    f'  - {item["slug"]}: {item["source"]} confidence={item["confidence"]} '
                    f'fields={", ".join(item["fields_found"]) or "-"}'
                )
            for warning in report['warnings']:
                self.stdout.write(self.style.WARNING(f'  warning: {warning}'))

    def _download(self, url: str, target: Path) -> bool:
        try:
            import requests

            response = requests.get(url, timeout=15)
            response.raise_for_status()
            if not response.content.startswith(b'%PDF'):
                return False
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(response.content)
            return True
        except Exception:
            return False
