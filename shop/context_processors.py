from django.db.models import Q

from .models import CartItem


def cart_count(request):
    """Возвращает количество товаров в корзине.

    БАГ-фикс (2026-05-19): раньше использовался ТОЛЬКО session_id, поэтому
    для авторизованных юзеров (которые имеют user FK) бейдж корзины в шапке
    всегда показывал 0 — даже когда товары в корзине были.

    Сейчас:
    - guest → ищем по session_id
    - auth  → ищем по user (+ legacy session_items если ещё не смерджились)

    Результат кешируется на request — context_processor вызывается на КАЖДЫЙ
    render базового шаблона, а CartItem не меняется между context-вызовами
    в рамках одного запроса.
    """
    cached = getattr(request, '_cart_count_cache', None)
    if cached is not None:
        return {'cart_count': cached}

    if request.user.is_authenticated:
        session_id = request.session.session_key
        q = Q(user=request.user)
        if session_id:
            q |= Q(session_id=session_id, user__isnull=True)
        count = CartItem.objects.filter(q).count()
    else:
        session_id = request.session.session_key
        count = CartItem.objects.filter(session_id=session_id).count() if session_id else 0

    request._cart_count_cache = count
    return {'cart_count': count}


def compare_list(request):
    """Список slug'ов товаров в сравнении + счётчик (для кнопок на карточках
    и бейджа в шапке)."""
    slugs = request.session.get('compare', [])
    return {
        'compare_slugs': slugs,
        'compare_count': len(slugs),
    }
