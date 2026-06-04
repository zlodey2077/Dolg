"""Subscription feature gates for DOLG.

This module is intentionally small and lazy.  It centralises the business
question "can this user use this capability?" without importing numerical,
AI or payment stacks at Django startup.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from typing import Callable, Iterable

from django.http import JsonResponse

PLAN_GUEST = 'guest'
PLAN_FREE = 'free'
PLAN_PRO = 'pro'
PLAN_ENTERPRISE = 'enterprise'
PLAN_UNLIMITED = 'unlimited'

PRO_REQUIRED = 'pro'
ENTERPRISE_REQUIRED = 'enterprise'


FREE_FEATURES = {
    'basic_catalog',
    'basic_cad',
    'basic_lab',
    'basic_simulation',
    'ai_chat_basic',
    'ai_pipeline_info',
    'ai_find_analogs',
    'ai_detect_anomalies',
    'comments_plain',
}

PRO_FEATURES = FREE_FEATURES | {
    'pro_fft',
    'pro_bode',
    'pro_monte_carlo',
    'pro_signal_quality',
    'pro_parameter_sweep',
    'server_side_solver',
    'ai_chat_extended',
    'ai_scheme_context',
    'ai_explain_scheme',
    'ai_recommend_next',
    'ai_deep_hint',
    'comments_rich',
    'extended_history',
    'branded_exports',
}

ENTERPRISE_FEATURES = PRO_FEATURES | {
    'enterprise_workspace',
    'enterprise_roles',
    'enterprise_team_ai_memory',
    'enterprise_ai_audit',
    'enterprise_org_moderation',
    'enterprise_audit_log',
    'enterprise_api_tokens',
    'enterprise_approval_workflow',
    'enterprise_org_analytics',
    'enterprise_sso',
    'enterprise_2fa_policy',
    'enterprise_dataset_export',
}

FEATURE_MATRIX = {
    PLAN_GUEST: FREE_FEATURES - {'ai_chat_basic'},
    PLAN_FREE: FREE_FEATURES,
    PLAN_PRO: PRO_FEATURES,
    PLAN_ENTERPRISE: ENTERPRISE_FEATURES,
    PLAN_UNLIMITED: ENTERPRISE_FEATURES | {'unlimited'},
}

FEATURE_REQUIRED_PLAN = {feature: PRO_REQUIRED for feature in PRO_FEATURES - FREE_FEATURES}
FEATURE_REQUIRED_PLAN.update({feature: ENTERPRISE_REQUIRED for feature in ENTERPRISE_FEATURES - PRO_FEATURES})

FEATURE_LABELS = {
    'pro_fft': 'FFT spectrum',
    'pro_bode': 'Bode plot',
    'pro_monte_carlo': 'Monte Carlo tolerance',
    'pro_signal_quality': 'Signal quality',
    'pro_parameter_sweep': 'Parameter sweep',
    'server_side_solver': 'Server-side fallback solver',
    'ai_chat_extended': 'AI Pro engineer mode',
    'ai_scheme_context': 'AI scheme analysis panel',
    'ai_explain_scheme': 'AI scheme explanation',
    'ai_recommend_next': 'AI next component recommendation',
    'ai_deep_hint': 'PyTorch deep hint',
    'comments_rich': 'Rich comments and community tools',
    'extended_history': 'Extended project history',
    'branded_exports': 'Branded project exports',
    'enterprise_workspace': 'Enterprise workspace',
    'enterprise_team_ai_memory': 'Enterprise team AI memory',
    'enterprise_ai_audit': 'Enterprise AI audit',
    'enterprise_org_moderation': 'Enterprise moderation',
    'enterprise_audit_log': 'Enterprise audit log',
    'enterprise_api_tokens': 'Enterprise API tokens',
    'enterprise_approval_workflow': 'Enterprise approval workflow',
    'enterprise_org_analytics': 'Enterprise analytics',
    'enterprise_sso': 'Enterprise SSO',
    'enterprise_2fa_policy': 'Enterprise 2FA policy',
}


@dataclass(frozen=True)
class FeatureDecision:
    allowed: bool
    feature: str
    current_plan: str
    required_plan: str
    message: str


def get_effective_plan(user, organization=None) -> str:
    """Return guest/free/pro/enterprise/unlimited for the current context."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return PLAN_GUEST
    if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
        return PLAN_UNLIMITED

    if organization is not None:
        org_plan = _plan_from_org(user, organization)
        if org_plan:
            return org_plan

    membership_plan = _best_plan_from_memberships(user)
    if membership_plan == PLAN_ENTERPRISE:
        return PLAN_ENTERPRISE

    if _has_active_personal_pro(user):
        return PLAN_PRO

    if membership_plan == PLAN_PRO:
        return PLAN_PRO
    return PLAN_FREE


def has_feature(user, feature_key: str, organization=None) -> bool:
    plan = get_effective_plan(user, organization=organization)
    if plan == PLAN_UNLIMITED:
        return True
    return feature_key in FEATURE_MATRIX.get(plan, set())


def check_feature(user, feature_key: str, organization=None) -> FeatureDecision:
    plan = get_effective_plan(user, organization=organization)
    allowed = has_feature(user, feature_key, organization=organization)
    required = FEATURE_REQUIRED_PLAN.get(feature_key, PLAN_FREE)
    label = FEATURE_LABELS.get(feature_key, feature_key)
    if allowed:
        return FeatureDecision(True, feature_key, plan, required, '')
    if required == ENTERPRISE_REQUIRED:
        message = f'{label} доступен только для Enterprise-команды с активной подпиской.'
    else:
        message = f'{label} доступен в Pro и Enterprise.'
    return FeatureDecision(False, feature_key, plan, required, message)


def plan_features(plan: str) -> list[str]:
    if plan == PLAN_UNLIMITED:
        return sorted(FEATURE_MATRIX[PLAN_UNLIMITED])
    return sorted(FEATURE_MATRIX.get(plan, set()))


def feature_summary(user, organization=None) -> dict:
    plan = get_effective_plan(user, organization=organization)
    features = plan_features(plan)
    return {
        'plan': plan,
        'features': features,
        'flags': {feature: True for feature in features},
    }


def entitlement_error_payload(decision: FeatureDecision) -> dict:
    return {
        'ok': False,
        'error': 'plan_required',
        'plan_required': decision.required_plan,
        'feature': decision.feature,
        'feature_label': FEATURE_LABELS.get(decision.feature, decision.feature),
        'current_plan': decision.current_plan,
        'message': decision.message,
        'upgrade_url': '/billing/',
    }


def feature_denied_response(user, feature_key: str, *, organization=None, status=403):
    decision = check_feature(user, feature_key, organization=organization)
    if decision.allowed:
        return None
    return JsonResponse(entitlement_error_payload(decision), status=status)


def require_feature(
    feature_key: str,
    *,
    organization_getter: Callable | None = None,
):
    """Decorator for JSON endpoints and lightweight HTML gates."""

    def decorator(view):
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            organization = None
            if organization_getter is not None:
                organization = organization_getter(request, *args, **kwargs)
            denied = feature_denied_response(
                request.user,
                feature_key,
                organization=organization,
            )
            if denied is not None:
                return denied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def required_plan_for(feature_key: str) -> str:
    return FEATURE_REQUIRED_PLAN.get(feature_key, PLAN_FREE)


def _has_active_personal_pro(user) -> bool:
    try:
        sub = user.subscription
        return bool(sub.is_pro_active())
    except Exception:
        return False


def _plan_from_org(user, organization) -> str:
    if organization is None:
        return ''
    try:
        if not organization.has_member(user):
            return ''
        if not _org_has_active_subscription(organization):
            return ''
        return PLAN_ENTERPRISE if organization.plan == PLAN_ENTERPRISE else PLAN_PRO
    except Exception:
        return ''


def _best_plan_from_memberships(user) -> str:
    try:
        from Dolg_APP.models import OrganizationMember

        memberships = OrganizationMember.objects.filter(
            user=user, deactivated_at__isnull=True
        ).select_related('organization')
        best = PLAN_FREE
        for membership in memberships:
            plan = _plan_from_org(user, membership.organization)
            if plan == PLAN_ENTERPRISE:
                return PLAN_ENTERPRISE
            if plan == PLAN_PRO:
                best = PLAN_PRO
        return best
    except Exception:
        return PLAN_FREE


def _org_has_active_subscription(organization) -> bool:
    try:
        from Dolg_APP.models import Subscription

        return any(sub.is_pro_active() for sub in Subscription.objects.filter(organization=organization))
    except Exception:
        return False


def filter_features(features: Iterable[str], user, organization=None) -> dict[str, bool]:
    return {feature: has_feature(user, feature, organization=organization) for feature in features}
