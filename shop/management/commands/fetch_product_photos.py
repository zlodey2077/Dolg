"""Найти РЕАЛЬНЫЕ фото товаров из нескольких источников (генерация UGO — только fallback).

Источники по приоритету: official-CDN (курируемые) → Nexar/Octopart (по part_number, нужен
NEXAR_CLIENT_ID/SECRET) → LCSC/EasyEDA (поиск по MPN). Каждый кандидат проходит гейт качества
(разрешение/энтропия/детализация) — «некачественные» отбраковываются. Прошедшее фото идёт в
products/verified/<slug> и привязывается через media-policy. Wikimedia не используется.

Запуск:
    python manage.py fetch_product_photos --dry-run            # показать кандидатов, без скачивания
    python manage.py fetch_product_photos                      # только товары с UGO-генерацией/placeholder
    python manage.py fetch_product_photos --all                # все товары (перепроверить даже verified)
    python manage.py fetch_product_photos --slug r-1k --slug bc547
    python manage.py fetch_product_photos --source nexar --source lcsc   # подмножество/порядок источников
    python manage.py fetch_product_photos --limit 20

Ключи Nexar (опционально, иначе источник пропускается):
    setx NEXAR_CLIENT_ID ...   и   setx NEXAR_CLIENT_SECRET ...
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from shop.models import Product
from shop.services.media_quality import classify_image_source
from shop.services.photo_sources import DEFAULT_ORDER, SOURCES, find_and_apply_photo


class Command(BaseCommand):
    help = 'Ищет реальные фото товаров (official-CDN/Nexar/LCSC), генерация UGO остаётся fallback.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--slug', action='append', default=[], help='Только эти slug (повторяемо/через запятую).'
        )
        parser.add_argument('--source', action='append', default=[], help='Подмножество/порядок источников.')
        parser.add_argument('--limit', type=int, default=0, help='Не больше N товаров (0 = без лимита).')
        parser.add_argument(
            '--all', action='store_true', help='Все товары (иначе только generated/placeholder).'
        )
        parser.add_argument('--dry-run', action='store_true', help='Показать кандидатов без скачивания.')

    def handle(self, *args, **options):
        slug_filter = set()
        for value in options.get('slug') or []:
            slug_filter.update(s.strip() for s in value.split(',') if s.strip())

        order = [s for s in (options.get('source') or []) if s in SOURCES] or DEFAULT_ORDER
        unknown = [s for s in (options.get('source') or []) if s not in SOURCES]
        if unknown:
            self.stdout.write(self.style.WARNING(f'Неизвестные источники проигнорированы: {unknown}'))
        self.stdout.write(f'Источники (приоритет): {" → ".join(order)}')

        qs = Product.objects.all().order_by('slug')
        if slug_filter:
            qs = qs.filter(slug__in=slug_filter)

        targets = []
        for p in qs:
            if not options['all'] and classify_image_source(p) not in {'generated', 'missing'}:
                continue  # уже есть реальное фото — не трогаем
            targets.append(p)
            if options['limit'] and len(targets) >= options['limit']:
                break

        self.stdout.write(
            f'К обработке: {len(targets)} товаров'
            + (' (только generated/placeholder)' if not options['all'] else ' (--all)')
        )

        found = failed = 0
        for p in targets:
            res = find_and_apply_photo(p, order=order, dry_run=options['dry_run'])
            if res.ok:
                found += 1
                tag = 'кандидат' if options['dry_run'] else 'фото'
                self.stdout.write(self.style.SUCCESS(f'  ✓ {p.slug}: {tag} из {res.source} — {res.url[:70]}'))
            else:
                failed += 1
                self.stdout.write(f'  · {p.slug}: {res.reason} (пробовал: {len(res.tried)})')

        verb = 'найдено кандидатов' if options['dry_run'] else 'привязано реальных фото'
        self.stdout.write(self.style.SUCCESS(f'\nГотово: {verb} {found}, без результата {failed}.'))
        if not options['dry_run']:
            self.stdout.write(
                'Для оставшихся остаётся UGO-генерация (apply_product_image_policy / generate).'
            )
