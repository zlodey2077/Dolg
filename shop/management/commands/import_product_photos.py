"""Импорт настоящих фотографий товаров из папки.

Pipeline:
  1. Дропаете файлы в `media/products/incoming/<slug>.{png,jpg,jpeg,webp}`.
  2. Запускаете команду — она копирует файлы в `media/products/<slug>.<ext>`
     и переключает Product.image на новый путь (через apply_product_image_policy).
  3. После успешного импорта файл из incoming/ удаляется (--keep-source чтобы оставить).

Имя файла = product.slug. Команда матчит по slug, и сразу применяет media-policy
(в т.ч. отметит parameters.image_source = 'local product asset').

Запуск:
    python manage.py import_product_photos                 # импорт всех файлов из media/products/incoming/
    python manage.py import_product_photos --slug r-1k     # только конкретный slug
    python manage.py import_product_photos --keep-source    # не удалять файлы из incoming
    python manage.py import_product_photos --dry-run        # показать что будет сделано без записи
"""

import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from shop.models import Product
from shop.services.product_images import (
    LOCAL_ASSET_SUFFIXES,
    apply_product_image_policy,
)

INCOMING_DIR = 'products/incoming'


class Command(BaseCommand):
    help = (
        'Импортирует настоящие фото товаров из media/products/incoming/<slug>.<ext>. '
        'После импорта файлы перемещаются в media/products/<slug>.<ext> '
        'и привязываются к товару через apply_product_image_policy.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--slug',
            action='append',
            default=[],
            help="Импорт только этих slug'ов (можно повторить или через запятую).",
        )
        parser.add_argument(
            '--keep-source',
            action='store_true',
            help='Оставить файлы в incoming/ после копирования (по умолчанию удаляются).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать план импорта без фактических изменений.',
        )

    def handle(self, *args, **options):
        media_root = Path(settings.MEDIA_ROOT)
        incoming = media_root / INCOMING_DIR
        if not incoming.exists():
            incoming.mkdir(parents=True, exist_ok=True)
            self.stdout.write(
                self.style.WARNING(
                    f'Папка {incoming} создана. Положите туда файлы вида <slug>.png/.jpg/.jpeg/.webp '
                    f'и перезапустите команду.'
                )
            )
            return

        # Парсим --slug whitelist
        slug_filter = set()
        for value in options.get('slug') or []:
            slug_filter.update(s.strip() for s in value.split(',') if s.strip())

        # Сканируем incoming
        candidates = []
        for path in sorted(incoming.iterdir()):
            if not path.is_file():
                continue
            ext = path.suffix.lower()
            if ext not in LOCAL_ASSET_SUFFIXES:
                self.stdout.write(self.style.WARNING(f'  пропуск (формат не поддерживается): {path.name}'))
                continue
            slug = path.stem.lower().strip()
            if slug_filter and slug not in slug_filter:
                continue
            candidates.append((slug, ext, path))

        if not candidates:
            msg = (
                f'Нет файлов в {incoming} для импорта'
                + (f' (фильтр: {", ".join(slug_filter)})' if slug_filter else '')
                + '.'
            )
            self.stdout.write(msg)
            return

        # Группируем по slug — у одного товара может быть только одно фото.
        # Если файлов несколько (.png И .jpg), берём первый по приоритету suffix-list.
        by_slug = {}
        for slug, ext, path in candidates:
            by_slug.setdefault(slug, []).append((ext, path))
        for slug, items in by_slug.items():
            items.sort(key=lambda x: LOCAL_ASSET_SUFFIXES.index(x[0]))

        # Импорт
        dry_run = options['dry_run']
        keep_source = options['keep_source']
        imported = 0
        skipped_no_product = 0
        for slug, items in by_slug.items():
            chosen_ext, source_path = items[0]
            try:
                product = Product.objects.get(slug=slug)
            except Product.DoesNotExist:
                skipped_no_product += 1
                self.stdout.write(
                    self.style.WARNING(f'  ⚠ Product со slug "{slug}" не найден — пропуск {source_path.name}')
                )
                continue

            dest = media_root / 'products' / f'{slug}{chosen_ext}'
            action = 'DRY-RUN' if dry_run else 'импорт'
            self.stdout.write(
                f'  {action}: {source_path.name} → {dest.relative_to(media_root)} (товар: {product.name[:50]!r})'
            )

            if dry_run:
                continue

            # Копируем (не двигаем — если operation сорвётся, source ещё цел)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, dest)

            # apply_product_image_policy сам найдёт растровый локальный asset
            # (после фикса 2026-05-19 SVG исключён из LOCAL_ASSET_SUFFIXES)
            # и переключит product.image на products/<slug>.<ext>.
            changed = apply_product_image_policy(product, force=False)
            if changed:
                imported += 1
                self.stdout.write(self.style.SUCCESS(f'    ✓ product.image = {product.image.name}'))
            else:
                self.stdout.write('    (товар уже использует этот файл — image не менялся)')

            if not keep_source:
                source_path.unlink()

            # Если в incoming были запасные форматы (.jpg И .webp того же slug) —
            # игнорируем «лишние»: один товар = одно изображение.
            for extra_ext, extra_path in items[1:]:
                if keep_source:
                    self.stdout.write(
                        self.style.WARNING(
                            f'    ⚠ оставлен дубль: {extra_path.name} (приоритет уже у {chosen_ext})'
                        )
                    )
                else:
                    extra_path.unlink()

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nDRY-RUN. План: {len(by_slug)} файлов к импорту, {skipped_no_product} без товара.'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nГотово: импортировано {imported}, пропущено {skipped_no_product} без товара.'
                )
            )
