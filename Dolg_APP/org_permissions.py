"""Role-based access control для организаций.

Иерархия ролей:
    owner > admin > engineer > reviewer > viewer

Действия namespace: 'object.verb'
    'org.delete', 'org.update', 'org.billing'
    'org.members.invite', 'org.members.remove', 'org.members.role_change'
    'project.create', 'project.edit_own', 'project.edit_team', 'project.delete'
    'bom.submit', 'bom.approve', 'bom.reject'
    'audit.read', 'audit.export'
    'order.create'
    'settings.policy'

Использование:
    from .org_permissions import user_can, require_org_permission

    if user_can(request.user, org, 'project.edit_team'):
        ...

    @require_org_permission('bom.approve', org_arg='org_slug')
    def api_bom_approve(request, org_slug, bom_id): ...
"""
import functools

from django.http import JsonResponse

# Базовая матрица прав. Owner получает ВСЁ автоматически (см. user_can).
ROLE_PERMISSIONS = {
    'owner': {
        'org.delete', 'org.update', 'org.billing',
        'org.members.invite', 'org.members.remove', 'org.members.role_change',
        'project.create', 'project.edit_own', 'project.edit_team', 'project.delete',
        'project.read',
        'bom.submit', 'bom.approve', 'bom.reject',
        'audit.read', 'audit.export',
        'order.create',
        'settings.policy',
        'api.token.create', 'api.token.revoke',
        'org.chat.read', 'org.chat.write', 'org.chat.create_conversation', 'org.chat.archive',
        'org.moderation.manage',
        'catalog.product.create', 'catalog.product.edit', 'catalog.product.delete',
    },
    'admin': {
        'org.update',
        'org.members.invite', 'org.members.remove', 'org.members.role_change',
        'project.create', 'project.edit_own', 'project.edit_team', 'project.delete',
        'project.read',
        'bom.submit', 'bom.approve', 'bom.reject',
        'audit.read', 'audit.export',
        'order.create',
        'settings.policy',
        'api.token.create',
        'org.chat.read', 'org.chat.write', 'org.chat.create_conversation', 'org.chat.archive',
        'org.moderation.manage',
        'catalog.product.create', 'catalog.product.edit',
    },
    'engineer': {
        'project.create', 'project.edit_own', 'project.edit_team',
        'project.read',
        'bom.submit',
        'org.chat.read', 'org.chat.write',
        'catalog.product.create',  # инженеры могут предлагать товары в каталог
    },
    'reviewer': {
        'project.read',
        'bom.approve', 'bom.reject',
        'org.chat.read', 'org.chat.write',
    },
    'moderator': {
        'project.read',
        'org.chat.read', 'org.chat.write',
        'org.moderation.manage',
    },
    'viewer': {
        'project.read',
        'org.chat.read',
    },
}


def user_can(user, organization, action: str) -> bool:
    """True если user имеет разрешение action в organization.

    Special cases:
    - staff / superuser → True всегда (для тестирования и поддержки)
    - не member org → False
    - owner — всегда True (даже если в ROLE_PERMISSIONS чего-то не хватает)
    """
    if user is None or not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    if organization is None:
        return False

    role = organization.get_role(user)
    if not role:
        return False
    if role == 'owner':
        return True
    return action in ROLE_PERMISSIONS.get(role, set())


def get_user_role(user, organization) -> str:
    """Возвращает роль user в org, или '' если не member."""
    if user is None or not user.is_authenticated or organization is None:
        return ''
    if user.is_staff or user.is_superuser:
        return 'admin'   # для UI-отображения; user_can даст True всё равно
    return organization.get_role(user)


def require_org_permission(action: str, org_arg: str = 'org_slug', org_field: str = 'slug'):
    """Декоратор: проверяет, что user имеет action в org из URL-параметра.

    Usage:
        @require_org_permission('bom.approve', org_arg='org_slug')
        def view(request, org_slug, ...):
            org = request.organization   # вью получит org инжектированно
            ...

    Если permission deny → 403 JSON (для API) или redirect (для пагов).
    """
    def decorator(view):
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            from .models import Organization

            org_value = kwargs.get(org_arg)
            if not org_value:
                return _deny(request, 'missing org parameter')

            try:
                org = Organization.objects.get(**{org_field: org_value})
            except Organization.DoesNotExist:
                return _deny(request, 'organization not found', status=404)

            if not user_can(request.user, org, action):
                return _deny(
                    request,
                    f'У вас нет прав на «{action}» в организации «{org.name}». '
                    f'Ваша роль: «{get_user_role(request.user, org) or "не член"}».',
                    status=403,
                )
            # Инжектим org в request, чтобы view не повторял lookup
            request.organization = org
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


def _deny(request, message: str, status: int = 403):
    if request.headers.get('Accept', '').startswith('application/json') or request.path.startswith('/api/'):
        return JsonResponse({'ok': False, 'error': 'permission_denied', 'message': message}, status=status)
    # Для HTML — простая 403/404 страница
    from django.http import HttpResponseForbidden, HttpResponseNotFound
    if status == 404:
        return HttpResponseNotFound(message)
    return HttpResponseForbidden(message)


# ============================================================
# Template-tags helpers (импортируются в tier_tags.py)
# ============================================================

def template_user_can(user, organization, action: str) -> bool:
    """Alias для использования из шаблонов через template tag."""
    return user_can(user, organization, action)
