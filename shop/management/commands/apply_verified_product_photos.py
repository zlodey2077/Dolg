from __future__ import annotations

import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from shop.models import Product
from shop.services.media_quality import audit_product_image
from shop.services.product_images import (
    GENERATED_IMAGE_POLICY,
    VERIFIED_IMAGE_DIR,
    VERIFIED_IMAGE_SOURCE,
)

BLOCKED_REAL_PHOTO_SLUGS = {
    # Явно нерелевантные изображения из старого кеша: еда, вода, сломанные
    # экраны, спутниковые/промышленные кадры или фото не того класса товара.
    'asus-proart-pa278qv',
    'asus-rog-zephyrus-g16',
    'amd-radeon-rx-7900-xtx',
    'amd-ryzen-9-7950x3d',
    'be-quiet-dark-rock-pro-4',
    'corsair',
    'corsair-h150i-elite-capellix',
    'gskill-trident-z5-ddr5-16gb',
    'kingston-hyperx-fury-ddr4-16gb',
    'lg-ultrawide-34-219',
    'msi-optix-g273qf-27',
    'samsung-m7-smart-monitor-32',
    'seasonic-focus-plus-750w',
    'st-lm358dt',
    'texas-instruments-ne555dr',
}

SOURCE_DIRS = ('curated', 'commons')
SOURCE_OVERRIDES = {
    # В curated здесь не фото ноутбука, а декоративный экран; commons-кандидат
    # выглядит как реальный laptop-shot, поэтому для этого slug меняем приоритет.
    'macbook-pro-16-m3-max': ('commons', 'curated'),
}
IMAGE_SUFFIXES = ('.png', '.jpg', '.jpeg', '.webp')


class Command(BaseCommand):
    help = 'Copies selected real product photos into products/verified and applies them to matching products.'

    def add_arguments(self, parser):
        parser.add_argument('--slug', help='Only process one product slug.')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument(
            '--force', action='store_true', help='Re-copy verified files even if they already exist.'
        )

    def handle(self, *args, **options):
        media_root = Path(settings.MEDIA_ROOT)
        verified_root = media_root / VERIFIED_IMAGE_DIR
        verified_root.mkdir(parents=True, exist_ok=True)

        qs = Product.objects.select_related('category').order_by('slug')
        if options.get('slug'):
            qs = qs.filter(slug=options['slug'])

        checked = applied = skipped = 0
        for product in qs:
            checked += 1
            candidate = self._find_candidate(media_root, product.slug)
            if not candidate:
                skipped += 1
                continue

            target = verified_root / f'{product.slug}{candidate.suffix.lower()}'
            relative = f'{VERIFIED_IMAGE_DIR}/{target.name}'
            if options['dry_run']:
                self.stdout.write(f'plan: {product.slug} <- {candidate.relative_to(media_root)}')
                continue

            if options['force'] or not target.exists():
                shutil.copy2(candidate, target)

            previous_image = product.image.name if product.image else ''
            previous_params = dict(product.parameters or {})
            product.image.name = relative
            params = dict(product.parameters or {})
            params.update(
                {
                    'image_source': 'verified real product photo',
                    'image_source_url': VERIFIED_IMAGE_SOURCE,
                    'image_source_policy': GENERATED_IMAGE_POLICY,
                    'image_verified_from': candidate.relative_to(media_root).as_posix(),
                }
            )
            product.parameters = params

            report = audit_product_image(product, media_root=media_root)
            if not report['ok']:
                product.image.name = previous_image
                product.parameters = previous_params
                self.stdout.write(
                    self.style.WARNING(f'skip: {product.slug} failed quality gate {report["errors"]}')
                )
                skipped += 1
                continue

            product.save(update_fields=['image', 'parameters'])
            applied += 1
            self.stdout.write(f'{self._safe(product.name)[:42]:<42} <- {relative}')

        self.stdout.write(
            self.style.SUCCESS(
                f'Verified real photos checked={checked}, applied={applied}, skipped={skipped}.'
            )
        )

    @staticmethod
    def _safe(value: str) -> str:
        return str(value or '').encode('ascii', errors='replace').decode('ascii')

    def _find_candidate(self, media_root: Path, slug: str) -> Path | None:
        if slug in BLOCKED_REAL_PHOTO_SLUGS:
            return None
        products_root = media_root / 'products'
        for source_dir in SOURCE_OVERRIDES.get(slug, SOURCE_DIRS):
            root = products_root / source_dir
            for suffix in IMAGE_SUFFIXES:
                candidate = root / f'{slug}{suffix}'
                if candidate.exists():
                    return candidate
        return None
