"""Moderation workflows shared by API views, admin actions and tests."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils import timezone

from .models import ModerationAction, ModerationCase, ModerationReport, UserRestriction
from .permissions import target_organization

HIDDEN_PLACEHOLDER = 'Скрыто модератором'


def create_report(*, target, reporter, reason='other', details='') -> ModerationReport:
    organization = target_organization(target)
    summary = f'{target.__class__.__name__} #{target.pk}: {reason}'
    case = ModerationCase.get_or_open(
        target=target,
        reporter=reporter,
        organization=organization,
        summary=summary,
    )
    report = ModerationReport.objects.create(
        case=case,
        reporter=reporter if getattr(reporter, 'is_authenticated', False) else None,
        reason=reason or 'other',
        details=(details or '').strip(),
    )
    return report


def apply_action(
    *, case: ModerationCase, actor, action_type: str, reason='', payload=None
) -> ModerationAction:
    payload = dict(payload or {})
    target = case.target
    action = ModerationAction.objects.create(
        case=case,
        actor=actor if getattr(actor, 'is_authenticated', False) else None,
        action_type=action_type,
        reason=reason or '',
        payload=payload,
    )

    if action_type in {'hide', 'remove', 'restore', 'mark_reviewed'}:
        _apply_content_action(target, actor=actor, action_type=action_type, reason=reason)
    elif action_type in {'mute', 'ban', 'read_only'}:
        target_user = _target_user(target, payload)
        if target_user is not None:
            duration_days = int(payload.get('duration_days') or 7)
            UserRestriction.objects.create(
                user=target_user,
                restriction_type=action_type,
                scope=case.scope,
                organization=case.organization if case.scope == 'organization' else None,
                reason=reason or '',
                expires_at=timezone.now() + timedelta(days=duration_days) if duration_days > 0 else None,
                created_by=actor if getattr(actor, 'is_authenticated', False) else None,
            )

    if action_type == 'reject_report':
        case.status = 'rejected'
        case.resolved_at = timezone.now()
        case.reports.update(status='rejected')
    elif action_type in {'hide', 'remove', 'restore', 'mark_reviewed', 'warn', 'mute', 'ban', 'read_only'}:
        case.status = 'resolved'
        case.resolved_at = timezone.now()
        case.reports.update(status='accepted')
    else:
        case.status = 'in_review'
    case.save(update_fields=['status', 'resolved_at', 'updated_at'])
    _log_action(case=case, action=action, actor=actor)
    return action


def visible_queryset(qs, user=None):
    if user and getattr(user, 'is_authenticated', False):
        if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
            return qs
        fields = {field.name for field in qs.model._meta.fields}
        visibility = Q(moderation_status='visible')
        if 'author' in fields:
            visibility |= Q(author=user)
        if 'user' in fields:
            visibility |= Q(user=user)
        return qs.filter(visibility)
    return qs.filter(moderation_status='visible')


def is_content_visible_to(obj, user=None) -> bool:
    status = getattr(obj, 'moderation_status', 'visible')
    if status == 'visible':
        return True
    if user and getattr(user, 'is_authenticated', False):
        if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
            return True
    return False


def is_content_available_to(obj, user=None) -> bool:
    if getattr(obj, 'moderation_status', 'visible') == 'visible':
        return True
    if user and getattr(user, 'is_authenticated', False):
        if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
            return True
        author_id = getattr(obj, 'author_id', None) or getattr(obj, 'user_id', None)
        return author_id == user.id
    return False


def display_body(obj, user=None) -> str:
    if is_content_visible_to(obj, user):
        return getattr(obj, 'body', '')
    return HIDDEN_PLACEHOLDER


def user_is_restricted(user, restriction_type=None, organization=None) -> bool:
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    qs = UserRestriction.objects.filter(user=user, lifted_at__isnull=True)
    if restriction_type:
        if restriction_type == 'write':
            qs = qs.filter(restriction_type__in=['mute', 'ban', 'read_only'])
        else:
            qs = qs.filter(restriction_type=restriction_type)
    qs = qs.filter(Q(starts_at__lte=timezone.now()) | Q(starts_at__isnull=True))
    qs = qs.filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True))
    if organization is not None:
        qs = qs.filter(Q(scope='global') | Q(scope='organization', organization=organization))
    else:
        qs = qs.filter(scope='global')
    return qs.exists()


def target_from_payload(target_type: str, target_id):
    content_type = _content_type_from_alias(target_type)
    model = content_type.model_class()
    return model._default_manager.get(pk=target_id)


def case_to_dict(case: ModerationCase) -> dict:
    target = case.target
    return {
        'id': case.id,
        'status': case.status,
        'scope': case.scope,
        'summary': case.summary,
        'target_type': f'{case.content_type.app_label}.{case.content_type.model}',
        'target_id': case.object_id,
        'target_label': str(target)[:160] if target is not None else '',
        'organization_id': case.organization_id,
        'reports_count': case.reports.count(),
        'actions_count': case.actions.count(),
        'created_at': case.created_at.isoformat(),
        'updated_at': case.updated_at.isoformat(),
    }


def _apply_content_action(target, *, actor, action_type: str, reason: str):
    if target is None or not hasattr(target, 'moderation_status'):
        return
    if action_type == 'restore':
        status = 'visible'
    elif action_type == 'mark_reviewed':
        status = 'visible'
    elif action_type == 'remove':
        status = 'removed'
    else:
        status = 'hidden'
    target.moderation_status = status
    target.moderation_reason = reason or ''
    target.moderated_by = actor if getattr(actor, 'is_authenticated', False) else None
    target.moderated_at = timezone.now()
    target.save(update_fields=['moderation_status', 'moderation_reason', 'moderated_by', 'moderated_at'])


def _target_user(target, payload):
    user_id = payload.get('user_id')
    if user_id:
        try:
            return get_user_model().objects.get(pk=user_id)
        except get_user_model().DoesNotExist:
            return None
    return getattr(target, 'author', None) or getattr(target, 'user', None)


def _content_type_from_alias(target_type: str):
    normalized = (target_type or '').strip().lower()
    aliases = {
        'comment': ('Dolg_APP', 'comment'),
        'chat_topic': ('Dolg_APP', 'chattopic'),
        'chat_reply': ('Dolg_APP', 'chatreply'),
        'org_message': ('Dolg_APP', 'orgconversationmessage'),
        'project': ('Dolg_APP', 'schematicproject'),
        'engineering_artifact': ('Dolg_APP', 'engineeringartifact'),
        'ai_training_example': ('Dolg_APP', 'aitrainingexample'),
        'product': ('shop', 'product'),
        'article': ('knowledge', 'article'),
        'learning_lesson': ('knowledge', 'learninglesson'),
        'learning_task': ('knowledge', 'learningtask'),
        'user': ('auth', 'user'),
    }
    if normalized in aliases:
        app_label, model = aliases[normalized]
    elif '.' in normalized:
        app_label, model = normalized.split('.', 1)
    else:
        raise ContentType.DoesNotExist(normalized)
    return ContentType.objects.get(app_label=app_label, model=model)


def _log_action(*, case, action, actor):
    try:
        from Dolg_APP.models import AuditLog

        AuditLog.log(
            actor=actor,
            action=f'moderation.{action.action_type}',
            organization=case.organization,
            object_type=case.content_type.model,
            object_id=case.object_id,
            payload={'case_id': case.id, 'reason': action.reason},
        )
    except Exception:
        return None
