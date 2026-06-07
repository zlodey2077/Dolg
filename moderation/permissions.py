"""Global and organization-scoped moderation permissions."""

from __future__ import annotations

from django.contrib.auth.models import Group

GROUP_SITE_ADMIN = 'site_admin'
GROUP_SITE_MODERATOR = 'site_moderator'
GROUP_CATALOG_EDITOR = 'catalog_editor'
GROUP_KNOWLEDGE_EDITOR = 'knowledge_editor'
GROUP_SUPPORT_AGENT = 'support_agent'

GLOBAL_GROUPS = [
    GROUP_SITE_ADMIN,
    GROUP_SITE_MODERATOR,
    GROUP_CATALOG_EDITOR,
    GROUP_KNOWLEDGE_EDITOR,
    GROUP_SUPPORT_AGENT,
]

GLOBAL_ROLE_PERMISSIONS = {
    GROUP_SITE_ADMIN: {
        'moderation.manage',
        'moderation.action',
        'moderation.queue',
        'content.moderate',
        'catalog.edit',
        'knowledge.edit',
        'support.view',
    },
    GROUP_SITE_MODERATOR: {
        'moderation.manage',
        'moderation.action',
        'moderation.queue',
        'content.moderate',
        'support.view',
    },
    GROUP_CATALOG_EDITOR: {'catalog.edit', 'support.view'},
    GROUP_KNOWLEDGE_EDITOR: {'knowledge.edit', 'support.view'},
    GROUP_SUPPORT_AGENT: {'support.view'},
}


def ensure_global_moderation_groups() -> list[Group]:
    return [Group.objects.get_or_create(name=name)[0] for name in GLOBAL_GROUPS]


def user_has_global_role(user, role_name: str) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (
            user.is_superuser
            or user.groups.filter(name=role_name).exists()
            or user.groups.filter(name=GROUP_SITE_ADMIN).exists()
        )
    )


def user_has_global_permission(user, permission: str) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    group_names = set(user.groups.values_list('name', flat=True))
    if GROUP_SITE_ADMIN in group_names:
        return True
    return any(permission in GLOBAL_ROLE_PERMISSIONS.get(name, set()) for name in group_names)


def user_can_moderate_site(user) -> bool:
    return user_has_global_permission(user, 'moderation.action')


def target_organization(target):
    if target is None:
        return None
    if hasattr(target, 'organization') and getattr(target, 'organization_id', None):
        return target.organization
    project = getattr(target, 'project', None)
    if project is not None and getattr(project, 'organization_id', None):
        return project.organization
    topic = getattr(target, 'topic', None)
    if topic is not None:
        attached = getattr(topic, 'attached_project', None)
        if attached is not None and getattr(attached, 'organization_id', None):
            return attached.organization
    conversation = getattr(target, 'conversation', None)
    if conversation is not None and getattr(conversation, 'organization_id', None):
        return conversation.organization
    return None


def user_can_moderate_org(user, organization) -> bool:
    if user_can_moderate_site(user):
        return True
    if organization is None:
        return False
    try:
        from Dolg_APP.org_permissions import user_can
    except Exception:
        return False
    return user_can(user, organization, 'org.moderation.manage')


def user_can_moderate_target(user, target) -> bool:
    if user_can_moderate_site(user):
        return True
    return user_can_moderate_org(user, target_organization(target))
