from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from PIL import Image, ImageDraw, ImageFont

from shop.models import Product
from shop.services.media_quality import audit_product_image
from shop.services.product_images import GENERATED_IMAGE_POLICY, VERIFIED_IMAGE_DIR


@dataclass(frozen=True)
class OfficialPhoto:
    slug: str
    url: str
    source_title: str
    label: str = ''
    replace_black_background: bool = False


OFFICIAL_PHOTOS = {
    item.slug: item
    for item in [
        OfficialPhoto(
            slug='breadboard-400',
            url='https://cdn-shop.adafruit.com/970x728/64-06.jpg',
            source_title='Adafruit product photo',
        ),
        OfficialPhoto(
            slug='breadboard-830',
            url='https://cdn-shop.adafruit.com/970x728/239-03.jpg',
            source_title='Adafruit product photo',
        ),
        OfficialPhoto(
            slug='breadboard-2x830',
            url='https://cdn-shop.adafruit.com/970x728/239-05.jpg',
            source_title='Adafruit product photo',
        ),
        OfficialPhoto(
            slug='pcb-protoboard-7x9',
            url='https://cdn-shop.adafruit.com/970x728/1606-06.jpg',
            source_title='Adafruit product photo',
        ),
        OfficialPhoto(
            slug='pcb-protoboard-9x15',
            url='https://cdn-shop.adafruit.com/970x728/1606-06.jpg',
            source_title='Adafruit product photo',
        ),
        OfficialPhoto(
            slug='jumper-mm-65pcs',
            url='https://cdn-shop.adafruit.com/970x728/759-03.jpg',
            source_title='Adafruit product photo',
        ),
        OfficialPhoto(
            slug='solder-paste-138',
            url='https://vxb.com/cdn/shop/files/61XnUsid7fL.jpg?v=1778102724&width=1280',
            source_title='VXB product photo',
        ),
        OfficialPhoto(
            slug='solder-lead-free-100g',
            url='https://static.rapidonline.com/catalogueimages/product/10/69/s10-6939p01wl.jpg',
            source_title='Rapid Electronics product photo',
        ),
        OfficialPhoto(
            slug='solder-60-40-100g',
            url='https://www.ersa-shop.com/wp-content/uploads/ap-attachments/49631/48094/FEL050100FR.jpg',
            source_title='Ersa/Felder product photo',
        ),
        OfficialPhoto(
            slug='ao3400',
            url='https://metastech.com/cdn/shop/files/AO3400_3.png?v=1765957797&width=1946',
            source_title='Metas product photo',
            replace_black_background=True,
        ),
        OfficialPhoto(
            slug='irlz44n',
            url='https://assets.infineon.com/is/image/infineon/infineon-pg-to220-3-904-vig-png-package-en.png',
            source_title='Infineon TO-220 package photo',
            label='IRLZ44N TO-220',
        ),
        OfficialPhoto(
            slug='irf9540n',
            url='https://assets.infineon.com/is/image/infineon/infineon-pg-to220-3-904-vig-png-package-en.png',
            source_title='Infineon TO-220 package photo',
            label='IRF9540N TO-220',
        ),
    ]
}


class Command(BaseCommand):
    help = 'Downloads allowlisted official/supplier product photos into products/verified and applies them.'

    def add_arguments(self, parser):
        parser.add_argument('--slug', help='Only process one slug or a comma-separated slug list.')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--force', action='store_true')

    def handle(self, *args, **options):
        slugs = self._selected_slugs(options.get('slug'))
        media_root = Path(settings.MEDIA_ROOT)
        verified_root = media_root / VERIFIED_IMAGE_DIR
        verified_root.mkdir(parents=True, exist_ok=True)

        checked = applied = skipped = 0
        for slug in slugs:
            checked += 1
            spec = OFFICIAL_PHOTOS[slug]
            try:
                product = Product.objects.get(slug=slug)
            except Product.DoesNotExist:
                skipped += 1
                self.stdout.write(self.style.WARNING(f'skip: product not found: {slug}'))
                continue

            suffix = self._suffix_for_url(spec.url)
            target = verified_root / f'{slug}{suffix}'
            relative = f'{VERIFIED_IMAGE_DIR}/{target.name}'

            if options['dry_run']:
                self.stdout.write(f'plan: {slug} <- {spec.url}')
                continue

            if options['force'] or not target.exists():
                self._download_to_verified(spec, target)

            previous_image = product.image.name if product.image else ''
            previous_params = dict(product.parameters or {})
            product.image.name = relative
            params = dict(product.parameters or {})
            params.update(
                {
                    'image_source': 'verified official/supplier product photo',
                    'image_source_url': spec.url,
                    'image_source_policy': GENERATED_IMAGE_POLICY,
                    'image_verified_from': spec.source_title,
                }
            )
            product.parameters = params

            report = audit_product_image(product, media_root=media_root)
            if not report['ok']:
                product.image.name = previous_image
                product.parameters = previous_params
                skipped += 1
                self.stdout.write(self.style.WARNING(f'skip: {slug} failed quality gate {report["errors"]}'))
                continue

            product.save(update_fields=['image', 'parameters'])
            applied += 1
            self.stdout.write(f'{slug:<28} <- {relative}')

        self.stdout.write(
            self.style.SUCCESS(f'Official photos checked={checked}, applied={applied}, skipped={skipped}.')
        )

    def _selected_slugs(self, raw: str | None) -> list[str]:
        if not raw:
            return list(OFFICIAL_PHOTOS)
        slugs = [item.strip() for item in raw.split(',') if item.strip()]
        unknown = sorted(set(slugs) - set(OFFICIAL_PHOTOS))
        if unknown:
            raise CommandError(f'Unknown allowlisted slug(s): {", ".join(unknown)}')
        return slugs

    @staticmethod
    def _suffix_for_url(url: str) -> str:
        suffix = Path(urlparse(url).path).suffix.lower()
        return suffix if suffix in {'.jpg', '.jpeg', '.png', '.webp'} else '.jpg'

    def _download_to_verified(self, spec: OfficialPhoto, target: Path) -> None:
        request = Request(
            spec.url,
            headers={
                'User-Agent': 'DOLG-Diploma media-quality importer/1.0',
                'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
            },
        )
        with urlopen(request, timeout=30) as response:
            with tempfile.NamedTemporaryFile(delete=False, suffix=target.suffix) as tmp:
                shutil.copyfileobj(response, tmp)
                temp_path = Path(tmp.name)
        try:
            self._normalize_image(
                temp_path,
                target,
                spec.label,
                replace_black_background=spec.replace_black_background,
            )
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _normalize_image(
        source: Path,
        target: Path,
        label: str,
        *,
        replace_black_background: bool = False,
    ) -> None:
        with Image.open(source) as opened:
            image = opened.convert('RGB')
        if replace_black_background:
            image = _replace_black_background(image)
        if label:
            draw = ImageDraw.Draw(image)
            font = _font(max(22, image.width // 36), bold=True)
            padding = max(14, image.width // 80)
            bbox = draw.textbbox((0, 0), label, font=font)
            width = bbox[2] - bbox[0]
            height = bbox[3] - bbox[1]
            box = (
                padding,
                padding,
                padding + width + padding,
                padding + height + padding,
            )
            draw.rounded_rectangle(box, radius=8, fill=(255, 255, 255), outline=(0, 120, 180), width=2)
            draw.text((padding + padding // 2, padding + padding // 2), label, fill=(8, 18, 36), font=font)
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target, quality=92, optimize=True)


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        'C:/Windows/Fonts/arialbd.ttf' if bold else 'C:/Windows/Fonts/arial.ttf',
        'C:/Windows/Fonts/segoeuib.ttf' if bold else 'C:/Windows/Fonts/segoeui.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
        if bold
        else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    ]
    for path in candidates:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _replace_black_background(image: Image.Image) -> Image.Image:
    pixels = image.load()
    width, height = image.size
    for y in range(height):
        for x in range(width):
            red, green, blue = pixels[x, y]
            if red < 8 and green < 8 and blue < 8:
                pixels[x, y] = (255, 255, 255)
    return image
