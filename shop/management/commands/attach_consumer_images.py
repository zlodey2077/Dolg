from django.core.management.base import BaseCommand

from shop.models import Category, Product
from shop.services.product_images import apply_product_image_policy


class Command(BaseCommand):
    help = 'Compatibility wrapper: generate local no-Wikimedia images for consumer electronics products.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Regenerate PNG files even if they already exist.')

    def handle(self, *args, **options):
        updated = 0
        checked = 0
        for product in Product.objects.select_related('category').exclude(category__slug__in=Category.REB_SLUGS):
            checked += 1
            if apply_product_image_policy(product, force=options['force']):
                updated += 1
        self.stdout.write(self.style.SUCCESS(f'Done. Consumer images checked: {checked}, updated: {updated}'))
