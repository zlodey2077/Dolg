"""Tier-tags для Django-шаблонов: is_pro_user, get_tier.

Используется в base.html и article/project templates для условного рендера
Pro-фич (Markdown comments, темы, custom logo). Не падает если у юзера
нет Subscription записи — возвращает False.
"""

from django import template

register = template.Library()


@register.filter(name='is_pro_user')
def is_pro_user(user) -> bool:
    """True если у юзера активный Pro-доступ (включая staff/superuser)."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_staff or user.is_superuser:
        return True
    try:
        return bool(user.subscription.is_pro_active())
    except Exception:
        return False


@register.filter(name='user_tier')
def user_tier(user) -> str:
    """Возвращает строку tier: guest/free/pro/unlimited."""
    from ..quotas import get_user_tier

    return get_user_tier(user)


@register.simple_tag(name='user_can')
def user_can_tag(user, organization, action: str) -> bool:
    """{% user_can user org 'bom.approve' as can_approve %}{% if can_approve %}…{% endif %}"""
    from ..org_permissions import user_can

    return user_can(user, organization, action)


@register.simple_tag(name='user_role')
def user_role_tag(user, organization) -> str:
    """{% user_role user org as role %}"""
    from ..org_permissions import get_user_role

    return get_user_role(user, organization)


@register.filter(name='user_orgs')
def user_orgs(user):
    """Возвращает active OrganizationMember для user (для navbar org-switcher).
    Шаблон может итерировать: {% for m in user|user_orgs %}{{ m.organization.name }}{% endfor %}.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return []
    try:
        return list(user.org_memberships.filter(deactivated_at__isnull=True).select_related('organization'))
    except Exception:
        return []
