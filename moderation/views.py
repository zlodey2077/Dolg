import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from .models import ModerationCase
from .permissions import (
    user_can_moderate_org,
    user_can_moderate_site,
    user_can_moderate_target,
)
from .services import apply_action, case_to_dict, create_report, target_from_payload


def _json_error(message, *, status=400, code='error'):
    return JsonResponse({'ok': False, 'error': code, 'message': message}, status=status)


def _moderatable_cases(user):
    qs = ModerationCase.objects.select_related('content_type', 'organization').prefetch_related('reports', 'actions')
    if user_can_moderate_site(user):
        return qs
    org_ids = []
    try:
        org_ids = [
            membership.organization_id
            for membership in user.org_memberships.select_related('organization').filter(deactivated_at__isnull=True)
            if user_can_moderate_org(user, membership.organization)
        ]
    except Exception:
        org_ids = []
    if not org_ids:
        return qs.none()
    return qs.filter(scope='organization', organization_id__in=org_ids)


def _has_moderation_access(user):
    if user_can_moderate_site(user):
        return True
    try:
        return any(
            user_can_moderate_org(user, membership.organization)
            for membership in user.org_memberships.select_related('organization').filter(deactivated_at__isnull=True)
        )
    except Exception:
        return False


@login_required(login_url='accounts:login')
def moderation_dashboard(request):
    if not _has_moderation_access(request.user):
        return HttpResponseForbidden('Нет прав на очередь модерации.')
    cases = _moderatable_cases(request.user).filter(status__in=['open', 'in_review'])[:50]
    return render(request, 'moderation/dashboard.html', {
        'cases': cases,
        'can_moderate_site': user_can_moderate_site(request.user),
    })


@login_required(login_url='accounts:login')
@require_GET
def api_queue(request):
    status = request.GET.get('status') or 'open'
    qs = _moderatable_cases(request.user)
    if status != 'all':
        qs = qs.filter(status=status)
    return JsonResponse({'ok': True, 'cases': [case_to_dict(case) for case in qs[:100]]})


@login_required(login_url='accounts:login')
@require_POST
def api_report(request):
    try:
        data = json.loads(request.body or '{}')
    except (json.JSONDecodeError, ValueError):
        return _json_error('Invalid JSON')

    target_type = data.get('target_type')
    target_id = data.get('target_id')
    reason = (data.get('reason') or 'other').strip()[:32]
    details = (data.get('details') or '').strip()[:2000]
    if not target_type or not target_id:
        return _json_error('target_type and target_id are required')

    try:
        target = target_from_payload(target_type, target_id)
    except Exception:
        return _json_error('Target not found', status=404, code='not_found')

    report = create_report(target=target, reporter=request.user, reason=reason, details=details)
    return JsonResponse({
        'ok': True,
        'report': {
            'id': report.id,
            'case_id': report.case_id,
            'reason': report.reason,
            'status': report.status,
        },
        'case': case_to_dict(report.case),
    })


@login_required(login_url='accounts:login')
@require_POST
def api_case_action(request, case_id):
    case = get_object_or_404(ModerationCase.objects.select_related('content_type', 'organization'), pk=case_id)
    if not user_can_moderate_target(request.user, case.target):
        return _json_error('forbidden', status=403, code='forbidden')

    try:
        data = json.loads(request.body or '{}')
    except (json.JSONDecodeError, ValueError):
        return _json_error('Invalid JSON')

    action_type = (data.get('action') or '').strip()
    reason = (data.get('reason') or '').strip()[:2000]
    payload = data.get('payload') if isinstance(data.get('payload'), dict) else {}
    allowed = {'hide', 'restore', 'remove', 'warn', 'mute', 'ban', 'read_only', 'mark_reviewed', 'reject_report'}
    if action_type not in allowed:
        return _json_error('Unknown action')

    action = apply_action(case=case, actor=request.user, action_type=action_type, reason=reason, payload=payload)
    case.refresh_from_db()
    return JsonResponse({
        'ok': True,
        'action': {'id': action.id, 'type': action.action_type},
        'case': case_to_dict(case),
    })
