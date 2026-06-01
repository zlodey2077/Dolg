"""Единые квоты для tier'ов DOLG.

Принципы:
- Free — лимиты ниже реальных серверных возможностей: цель не «защита»,
  а «причина оплатить Pro».
- Pro — пока не реализован полноценно, оставлен в structure для будущей
  интеграции biling. На текущем коде get_user_tier() всегда возвращает 'free'
  для не-staff юзеров.
- Staff / superuser — безлимит (None).

Использование:
    @enforce_daily_quota('simulations')   # 429 если >= лимит на сегодня
    def api_project_save_simulation(request, pk): ...

    @enforce_project_limit                # 429 если уже max_projects
    def api_project_create(request): ...

    allowed, reason = check_quota(user, 'simulations')   # ручная проверка
"""
import functools
from datetime import datetime, time

from django.http import JsonResponse
from django.utils import timezone

# ── Tier-конфиги ───────────────────────────────────────────────────────────
# None = безлимит. Цифры — реальные лимиты Free для дипломного MVP.

FREE_TIER = {
    'max_projects': 10,
    'max_sheets_per_project': 3,
    'max_components_per_scheme': 100,
    'simulations_per_day': 20,
    'ai_requests_per_day': 10,
    'chat_topics_per_day': 5,
    'chat_replies_per_day': 20,
    'max_upload_mb': 5,
    'max_active_share_links': 5,
    'max_history_versions': 10,
    'max_tran_duration_ms': 100,
}

PRO_TIER = {
    'max_projects': None,
    'max_sheets_per_project': 20,
    'max_components_per_scheme': 5000,
    'simulations_per_day': None,
    'ai_requests_per_day': 200,
    'chat_topics_per_day': None,
    'chat_replies_per_day': None,
    'max_upload_mb': 25,
    'max_active_share_links': 100,
    'max_history_versions': 100,
    'max_tran_duration_ms': 10_000,
}

UNLIMITED = {k: None for k in FREE_TIER}


# ── Tier-detection ─────────────────────────────────────────────────────────

def get_user_tier(user) -> str:
    from .services.entitlements import get_effective_plan

    plan = get_effective_plan(user)
    return 'pro' if plan == 'enterprise' else plan

    """Возвращает 'guest' / 'free' / 'pro' / 'unlimited'.
    Логика:
    - Не залогинен → guest
    - staff/superuser → unlimited
    - Личная Subscription.is_pro_active() → pro
    - User является member организации с активной Subscription → pro
      (Enterprise: подписка на org покрывает всех членов)
    - Иначе → free

    Per-user кеш на user-instance (одинаковый user в рамках одного request
    не пересчитывает tier). Это снимает 2 DB-query за вызов, а функция
    вызывается из get_limit, _is_pro_or_enterprise, декораторов и template-tag'ов
    по 5-15 раз на запрос.
    """
    if user is None or not user.is_authenticated:
        return 'guest'
    # Кеш атрибут — устанавливается на user instance (живёт в рамках запроса)
    cached = getattr(user, '_tier_cache', None)
    if cached is not None:
        return cached
    if user.is_staff or user.is_superuser:
        user._tier_cache = 'unlimited'
        return 'unlimited'
    # 1) Личная подписка
    try:
        sub = user.subscription
        if sub.is_pro_active():
            user._tier_cache = 'pro'
            return 'pro'
    except Exception:
        pass
    # 2) Подписка любой org куда user входит (Enterprise)
    try:
        from .models import OrganizationMember
        org_ids = OrganizationMember.objects.filter(
            user=user, deactivated_at__isnull=True,
        ).values_list('organization_id', flat=True)
        if org_ids:
            from .models import Subscription
            org_subs = Subscription.objects.filter(organization_id__in=org_ids)
            for s in org_subs:
                if s.is_pro_active():
                    user._tier_cache = 'pro'
                    return 'pro'
    except Exception:
        pass
    user._tier_cache = 'free'
    return 'free'


def get_tier_config(user) -> dict:
    tier = get_user_tier(user)
    return {
        'guest':     FREE_TIER,        # для guest пока те же лимиты — middleware блокирует раньше
        'free':      FREE_TIER,
        'pro':       PRO_TIER,
        'unlimited': UNLIMITED,
    }[tier]


def get_limit(user, key: str):
    """Возвращает лимит для юзера по ключу. None = безлимит."""
    return get_tier_config(user).get(key)


# ── Live-проверки ──────────────────────────────────────────────────────────

def get_today_usage(user):
    """Атомарно возвращает DailyUsage за сегодня. Lazy-import чтобы избежать
    circular-import (models импортирует quotas в декораторах)."""
    from .models import DailyUsage
    return DailyUsage.get_today(user)


def check_daily_quota(user, action: str) -> tuple[bool, str]:
    """action ∈ {'simulations', 'ai_requests'}. Возвращает (allowed, reason)."""
    limit = get_limit(user, f'{action}_per_day')
    if limit is None:
        return True, ''
    usage = get_today_usage(user)
    field = f'{action}_count'
    current = getattr(usage, field, 0)
    if current >= limit:
        return False, f'Лимит {limit}/день для tier «{get_user_tier(user)}» исчерпан.'
    return True, ''


def increment_daily(user, action: str):
    """Increments {action}_count для юзера на сегодня (atomic F-expression)."""
    from django.db.models import F

    usage = get_today_usage(user)
    field = f'{action}_count'
    setattr(usage, field, F(field) + 1)
    usage.save(update_fields=[field])


def check_project_limit(user) -> tuple[bool, str]:
    """True если можно создать ещё один проект."""
    limit = get_limit(user, 'max_projects')
    if limit is None:
        return True, ''
    from .models import SchematicProject
    # Учитываем только не-soft-deleted
    qs = SchematicProject.objects.filter(user=user)
    try:
        qs = qs.filter(deleted_at__isnull=True)   # после миграции этапа 3
    except Exception:
        pass
    current = qs.count()
    if current >= limit:
        return False, f'Достигнут лимит {limit} проектов для tier «{get_user_tier(user)}». ' \
                      f'Удалите старый или повысьте tier.'
    return True, ''


def check_active_share_links(user) -> tuple[bool, str]:
    """True если можно ещё один share-link включить."""
    limit = get_limit(user, 'max_active_share_links')
    if limit is None:
        return True, ''
    from .models import SchematicProject
    current = SchematicProject.objects.filter(user=user).exclude(share_token='').count()
    if current >= limit:
        return False, f'Активных share-link\'ов уже {current} из {limit}. ' \
                      f'Деактивируйте старый.'
    return True, ''


# ── Helpers для frontend ───────────────────────────────────────────────────

def usage_summary(user) -> dict:
    """Возвращает JSON-сериализуемый summary для UI-баннеров и /api/usage/today/."""
    from .services.entitlements import feature_summary

    tier = get_user_tier(user)
    cfg = get_tier_config(user)
    entitlements = feature_summary(user)
    if user is None or not user.is_authenticated:
        return {
            'tier': tier,
            'plan': entitlements['plan'],
            'limits': cfg,
            'features': entitlements['features'],
            'feature_flags': entitlements['flags'],
            'usage': {},
        }
    usage = get_today_usage(user)
    from .models import SchematicProject
    projects_count = SchematicProject.objects.filter(user=user).filter(
        deleted_at__isnull=True
    ).count() if hasattr(SchematicProject, 'deleted_at') else \
        SchematicProject.objects.filter(user=user).count()
    active_shares = SchematicProject.objects.filter(user=user).exclude(share_token='').count()
    return {
        'tier': tier,
        'plan': entitlements['plan'],
        'limits': cfg,
        'features': entitlements['features'],
        'feature_flags': entitlements['flags'],
        'usage': {
            'projects': projects_count,
            'simulations_today': usage.simulations_count,
            'ai_requests_today': usage.ai_requests_count,
            'active_share_links': active_shares,
        },
        'resets_at': _next_midnight_iso(),
    }


def _next_midnight_iso() -> str:
    """ISO-таймстамп следующей полуночи в TZ сервера (для UI «сбросится в…»)."""
    now = timezone.localtime()
    tomorrow = (now + timezone.timedelta(days=1)).date()
    midnight = timezone.make_aware(datetime.combine(tomorrow, time.min)) \
        if timezone.is_naive(datetime.combine(tomorrow, time.min)) \
        else datetime.combine(tomorrow, time.min)
    return midnight.isoformat()


# ── Декораторы для view'ов ─────────────────────────────────────────────────

def _quota_error_response(message: str, limit, action: str):
    return JsonResponse({
        'ok': False,
        'error': 'quota_exceeded',
        'action': action,
        'limit': limit,
        'message': message,
        'resets_at': _next_midnight_iso(),
    }, status=429)


def enforce_daily_quota(action: str):
    """Декоратор для view'ов: проверяет лимит, инкрементирует counter после
    успешного выполнения. При превышении возвращает 429 JSON.

    Внимание: счётчик инкрементируется ВНЕ зависимости от того, успешен ли
    view (вернул 200 или 500). Это намеренно — даже неудачные попытки
    «съедают» лимит, как у big-tech API. Если хотим иначе — переписать
    на context manager.
    """
    def decorator(view):
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.user.is_authenticated:
                allowed, reason = check_daily_quota(request.user, action)
                if not allowed:
                    limit = get_limit(request.user, f'{action}_per_day')
                    return _quota_error_response(reason, limit, action)
                increment_daily(request.user, action)
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


def enforce_project_limit(view):
    """Декоратор на api_project_create — блокирует если уже max_projects."""
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            allowed, reason = check_project_limit(request.user)
            if not allowed:
                limit = get_limit(request.user, 'max_projects')
                return _quota_error_response(reason, limit, 'create_project')
        return view(request, *args, **kwargs)
    return wrapper
