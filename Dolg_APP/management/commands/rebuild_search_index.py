"""Перестраивает FAISS-индекс для семантического поиска товаров.

Запуск:
    python manage.py rebuild_search_index           # все товары
    python manage.py rebuild_search_index --reb     # только РЭБ-категории

После запуска индекс сохраняется в `media/search/products.faiss`
+ `media/search/products.json` (id-mapping). На первом вызове fastembed
скачает модель ~30 МБ в `media/search/models/`.
"""
import time

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Перестраивает FAISS-индекс семантического поиска по Product.'

    def add_arguments(self, parser):
        parser.add_argument('--reb', action='store_true',
                            help='Индексировать только РЭБ-категории (8 категорий)')

    def handle(self, *args, **opts):
        from Dolg_APP.ml.semantic_search import (
            build_index,
            is_index_stale,
            is_semantic_available,
        )
        from shop.models import Product
        from shop.views import REB_SLUGS

        if not is_semantic_available():
            self.stderr.write(self.style.ERROR(
                'scikit-learn не установлен. Установите: pip install scikit-learn'
            ))
            return

        if is_index_stale():
            self.stdout.write(self.style.WARNING(
                '⚠ Индекс помечен как stale (Product был изменён) — нужен rebuild.'
            ))

        qs = Product.objects.select_related('category').all()
        if opts['reb']:
            qs = qs.filter(category__slug__in=REB_SLUGS)
            self.stdout.write(f'Фильтр: только РЭБ-категории ({qs.count()} товаров).')

        self.stdout.write(f'Старт индексации {qs.count()} товаров...')
        t0 = time.time()
        count = build_index(list(qs))
        elapsed = time.time() - t0
        self.stdout.write(self.style.SUCCESS(
            f'OK: проиндексировано {count} товаров за {elapsed:.1f}с. '
            f'Индекс сохранён в media/search/. Stale-marker очищен.'
        ))
