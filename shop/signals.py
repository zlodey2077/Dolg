"""Signals для shop-приложения.

merge_session_cart_on_login — при login юзера переносит CartItem'ы,
привязанные к session_id, на user_id.

mark_search_index_stale — при save/delete Product помечает FAISS/TF-IDF индекс
устаревшим. Сам индекс не пересоздаётся (это дорого, ~1-2 сек), вместо этого
admin при изменениях должен вручную запустить `python manage.py rebuild_search_index`.
Помеченный stale индекс используется как есть — это даёт graceful degradation
вместо downtime.
"""

import logging

from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import CartItem, Product

logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def merge_session_cart_on_login(sender, request, user, **kwargs):
    """При login: session-cart → user-cart. Решает кейс «добавил в корзину
    как guest, потом залогинился → товары не пропали»."""
    session_id = request.session.session_key
    if not session_id:
        return

    session_items = CartItem.objects.filter(session_id=session_id, user__isnull=True)
    if not session_items.exists():
        return

    for session_item in list(session_items):
        existing = CartItem.objects.filter(user=user, product=session_item.product).first()
        if existing:
            # Уже есть товар у юзера — суммируем (с clamp по stock)
            new_qty = min(
                existing.quantity + session_item.quantity,
                session_item.product.stock,
            )
            existing.quantity = new_qty
            existing.save(update_fields=['quantity'])
            session_item.delete()
        else:
            # Перепривязываем session-item на user
            session_item.user = user
            session_item.session_id = ''  # больше не нужен
            session_item.save(update_fields=['user', 'session_id'])


def _mark_search_index_stale_path():
    """Возвращает path к маркер-файлу, который сигналит «индекс устарел»."""
    from pathlib import Path

    from django.conf import settings

    return Path(settings.MEDIA_ROOT) / 'search' / '.stale'


@receiver(post_save, sender=Product)
def mark_search_index_stale_on_save(sender, instance, **kwargs):
    """При создании/изменении Product индекс TF-IDF становится неактуальным.
    Создаём marker-файл `media/search/.stale` (touch) — admin/management видит,
    что нужен rebuild_search_index. Сам индекс не пересоздаётся (это блокирующая
    операция на 1-2 сек, лагает save).

    Игнорируем raw=True (loaddata fixtures) — там обычно bulk-импорт.
    """
    if kwargs.get('raw'):
        return
    try:
        path = _mark_search_index_stale_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    except Exception as e:  # pragma: no cover — best-effort
        logger.warning('Failed to mark search index stale: %s', e)


@receiver(post_delete, sender=Product)
def mark_search_index_stale_on_delete(sender, instance, **kwargs):
    """То же при удалении Product."""
    mark_search_index_stale_on_save(sender, instance, **kwargs)
