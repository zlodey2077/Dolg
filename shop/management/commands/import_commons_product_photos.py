from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        'Disabled legacy command. DOLG no longer imports product images from '
        'Wikimedia Commons; use apply_curated_product_photos instead.'
    )

    def handle(self, *args, **options):
        raise CommandError(
            'Wikimedia/Commons image import is disabled by product media policy. '
            'Run: python manage.py apply_curated_product_photos --force'
        )
