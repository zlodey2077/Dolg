from django.core.management.base import BaseCommand

from shop.models import Product
from shop.services.product_images import GENERATED_IMAGE_SOURCE, apply_product_image_policy


class Command(BaseCommand):
    help = (
        'Apply controlled product image policy. Exact local product assets are preserved; '
        'generated placeholders are used only when a product has no acceptable local image.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', action='store_true', help='Regenerate PNG files even if they already exist.'
        )
        parser.add_argument(
            '--force-generated',
            action='store_true',
            help='Ignore existing exact local product assets and use generated placeholders for selected products.',
        )
        parser.add_argument(
            '--only-missing',
            action='store_true',
            help='Update only products without image. Existing product images are left untouched.',
        )
        parser.add_argument(
            '--slug',
            action='append',
            default=[],
            help='Process one or more product slugs. Can be passed several times or comma-separated.',
        )

    def handle(self, *args, **options):
        requested_slugs = []
        for value in options.get('slug') or []:
            requested_slugs.extend(part.strip() for part in value.split(',') if part.strip())

        products = Product.objects.select_related('category').order_by('category__slug', 'slug')
        if requested_slugs:
            products = products.filter(slug__in=requested_slugs)

        updated = 0
        skipped = 0
        generated = 0
        only_missing = options['only_missing']
        force = options['force']
        force_generated = options['force_generated']

        for product in products:
            if only_missing and product.image:
                skipped += 1
                continue

            changed = apply_product_image_policy(product, force=force, force_generated=force_generated)
            generated += 1
            if changed:
                updated += 1
                safe_name = (product.part_number or product.name).encode('ascii', 'replace').decode('ascii')
                self.stdout.write(f'{safe_name[:42]:<42} <- {product.image.name}')

        self.stdout.write(
            self.style.SUCCESS(
                'Done. '
                f'Checked: {generated}, updated DB rows: {updated}, skipped: {skipped}. '
                f'Generated fallback source: {GENERATED_IMAGE_SOURCE} (no Wikimedia).'
            )
        )
