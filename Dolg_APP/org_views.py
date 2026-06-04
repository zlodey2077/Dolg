"""Views для Organization (Enterprise tier).

Endpoints:
    /orgs/                              — список орг куда юзер входит
    /orgs/create/                       — wizard self-serve регистрация компании
    /orgs/<slug>/                       — dashboard org
    /orgs/<slug>/members/               — список + invite
    /orgs/<slug>/members/invite/        — POST: создать приглашение
    /orgs/<slug>/members/<id>/role/     — POST: изменить роль
    /orgs/<slug>/members/<id>/remove/   — POST: отключить member
    /orgs/<slug>/invite/<token>/        — accept-link из email
    /orgs/<slug>/settings/              — settings + policies
    /orgs/<slug>/audit/                 — лог действий

Все view (кроме accept-invite) требуют auth + соответствующее org.permission.
"""

import secrets
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from .models import AuditLog, Organization, OrganizationInvite, OrganizationMember
from .org_permissions import get_user_role, require_org_permission, user_can
from .services.entitlements import feature_summary, require_feature


def _request_org(request, *args, **kwargs):
    return getattr(request, 'organization', None)


# ============================================================
# Список org
# ============================================================
@login_required(login_url='accounts:login')
def org_list(request):
    """Список организаций, в которых юзер состоит."""
    memberships = (
        request.user.org_memberships.filter(deactivated_at__isnull=True)
        .select_related('organization')
        .order_by('organization__name')
    )
    return render(
        request,
        'orgs/list.html',
        {
            'memberships': memberships,
            'can_create_more': True,  # пока всем разрешено
        },
    )


# ============================================================
# Self-serve регистрация (wizard)
# ============================================================
@login_required(login_url='accounts:login')
def org_create(request):
    """5-шаговый wizard: name / slug / billing_email / size / legal-consent.
    POST создаёт Organization + OrganizationMember(owner) и редиректит в
    onboarding-wizard. AuditLog пишет согласие с версиями документов.
    """
    if request.method != 'POST':
        return render(request, 'orgs/create.html', {})

    name = (request.POST.get('name') or '').strip()
    slug = (request.POST.get('slug') or '').strip() or slugify(name)
    billing_email = (request.POST.get('billing_email') or '').strip() or request.user.email
    size = (request.POST.get('expected_size') or '1-5').strip()
    plan = 'team' if size in ('1-5', '6-20') else 'business'

    if not name:
        messages.error(request, 'Введите название компании')
        return redirect('hello:org_create')

    if Organization.objects.filter(slug=slug).exists():
        messages.error(request, f'Slug «{slug}» уже занят. Выберите другой.')
        return redirect('hello:org_create')

    # Required legal-чекбоксы
    legal_versions = {
        'msa': '1.0',
        'dpa': '1.0',
        'aup': '1.0',
        'privacy': '1.0',
    }
    missing = [k for k in legal_versions if not request.POST.get(f'agree_{k}')]
    if missing:
        messages.error(request, f'Согласие с документами обязательно: {", ".join(missing)}')
        return redirect('hello:org_create')

    seats = {'1-5': 5, '6-20': 10, '21-50': 50, '50+': 100}.get(size, 10)

    org = Organization.objects.create(
        name=name,
        slug=slug,
        billing_email=billing_email,
        plan=plan,
        seats_max=seats,
        owner=request.user,
    )
    OrganizationMember.objects.create(
        organization=org,
        user=request.user,
        role='owner',
        invited_by=request.user,
    )

    # Audit-log: фиксация создания + согласие с legal-документами
    AuditLog.log(
        actor=request.user,
        action='org.create',
        organization=org,
        object_type='Organization',
        object_id=org.id,
        payload={
            'name': org.name,
            'plan': org.plan,
            'seats_max': org.seats_max,
            'legal_versions_accepted': legal_versions,
        },
        request=request,
    )

    messages.success(request, f'🎉 Организация «{org.name}» создана!')
    return redirect('hello:org_dashboard', org_slug=org.slug)


# ============================================================
# Dashboard
# ============================================================
@login_required(login_url='accounts:login')
@require_org_permission('project.read')
def org_dashboard(request, org_slug):
    org = request.organization
    role = get_user_role(request.user, org)
    members_total = org.active_members_count()
    projects_total = org.projects.filter(deleted_at__isnull=True).count()
    pending_reviews = org.projects.filter(approval_state='pending_review').count()

    # Recent audit (top-10) для members с правом audit.read
    recent_audit = []
    if user_can(request.user, org, 'audit.read'):
        recent_audit = list(org.audit_log.order_by('-timestamp')[:10])

    return render(
        request,
        'orgs/dashboard.html',
        {
            'org': org,
            'role': role,
            'entitlements': feature_summary(request.user, organization=org),
            'members_total': members_total,
            'projects_total': projects_total,
            'pending_reviews': pending_reviews,
            'recent_audit': recent_audit,
            'can_invite': user_can(request.user, org, 'org.members.invite'),
            'can_audit': user_can(request.user, org, 'audit.read'),
            'can_settings': user_can(request.user, org, 'org.update'),
            'can_billing': user_can(request.user, org, 'org.billing'),
            'can_catalog_add': user_can(request.user, org, 'catalog.product.create'),
        },
    )


# ============================================================
# Members management
# ============================================================
@login_required(login_url='accounts:login')
@require_org_permission('project.read')
def org_members(request, org_slug):
    org = request.organization
    members = (
        org.memberships.filter(deactivated_at__isnull=True)
        .select_related('user')
        .order_by('-role', 'joined_at')
    )
    pending_invites = org.invites.filter(accepted_at__isnull=True).order_by('-created_at')
    return render(
        request,
        'orgs/members.html',
        {
            'org': org,
            'members': members,
            'pending_invites': pending_invites,
            'can_invite': user_can(request.user, org, 'org.members.invite'),
            'can_remove': user_can(request.user, org, 'org.members.remove'),
            'can_change_role': user_can(request.user, org, 'org.members.role_change'),
            'role_choices': OrganizationMember.ROLE_CHOICES,
        },
    )


@require_POST
@login_required(login_url='accounts:login')
@require_org_permission('org.members.invite')
def org_invite_create(request, org_slug):
    """Создать приглашение (email + role). Generate token, send email
    (через console.EmailBackend в DEBUG)."""
    from django.core.mail import send_mail

    org = request.organization
    email = (request.POST.get('email') or '').strip().lower()
    role = (request.POST.get('role') or 'engineer').strip()

    if not email:
        messages.error(request, 'Введите email')
        return redirect('hello:org_members', org_slug=org_slug)

    valid_roles = {r for r, _ in OrganizationMember.ROLE_CHOICES} - {'owner'}
    if role not in valid_roles:
        messages.error(request, 'Недопустимая роль')
        return redirect('hello:org_members', org_slug=org_slug)

    # Проверим лимит seats
    if org.active_members_count() + org.invites.filter(accepted_at__isnull=True).count() >= org.seats_max:
        messages.error(
            request,
            f'Достигнут лимит {org.seats_max} seats. Обратитесь к sales для увеличения.',
        )
        return redirect('hello:org_members', org_slug=org_slug)

    invite = OrganizationInvite.objects.create(
        organization=org,
        email=email,
        token=secrets.token_urlsafe(32),
        role=role,
        invited_by=request.user,
        expires_at=timezone.now() + timedelta(days=7),
    )

    # Send email
    accept_url = request.build_absolute_uri(f'/orgs/{org.slug}/invite/{invite.token}/')
    send_mail(
        subject=f'Приглашение в команду «{org.name}» на DOLG',
        message=(
            f'Здравствуйте,\n\n'
            f'{request.user.username} пригласил вас в команду «{org.name}» на DOLG '
            f'в роли «{dict(OrganizationMember.ROLE_CHOICES).get(role, role)}».\n\n'
            f'Перейдите по ссылке для принятия (действует 7 дней):\n{accept_url}\n\n'
            f'Если вы не ожидали этого письма — просто проигнорируйте.\n'
        ),
        from_email='noreply@dolg.local',
        recipient_list=[email],
        fail_silently=True,
    )

    AuditLog.log(
        actor=request.user,
        action='org.members.invite',
        organization=org,
        object_type='OrganizationInvite',
        object_id=invite.id,
        payload={'email': email, 'role': role},
        request=request,
    )
    messages.success(request, f'✅ Приглашение отправлено на {email}')
    return redirect('hello:org_members', org_slug=org_slug)


@require_POST
@login_required(login_url='accounts:login')
@require_org_permission('org.members.role_change')
def org_member_role(request, org_slug, member_id):
    """Изменить роль member. Owner не может понизить себя — нужен transfer ownership."""
    org = request.organization
    new_role = (request.POST.get('role') or '').strip()

    if new_role not in {r for r, _ in OrganizationMember.ROLE_CHOICES}:
        messages.error(request, 'Недопустимая роль')
        return redirect('hello:org_members', org_slug=org_slug)

    member = get_object_or_404(OrganizationMember, id=member_id, organization=org)
    old_role = member.role

    if member.user_id == org.owner_id and new_role != 'owner':
        messages.error(
            request,
            "Нельзя понизить owner'а. Сначала передайте ownership другому admin.",
        )
        return redirect('hello:org_members', org_slug=org_slug)

    member.role = new_role
    member.save(update_fields=['role'])
    AuditLog.log(
        actor=request.user,
        action='org.members.role_change',
        organization=org,
        object_type='OrganizationMember',
        object_id=member.id,
        payload={'user': member.user.username, 'old_role': old_role, 'new_role': new_role},
        request=request,
    )
    messages.success(request, f'Роль {member.user.username}: {old_role} → {new_role}')
    return redirect('hello:org_members', org_slug=org_slug)


@require_POST
@login_required(login_url='accounts:login')
@require_org_permission('org.members.remove')
def org_member_remove(request, org_slug, member_id):
    """Soft-deactivate member. Owner нельзя удалить."""
    org = request.organization
    member = get_object_or_404(OrganizationMember, id=member_id, organization=org)
    if member.user_id == org.owner_id:
        messages.error(request, "Нельзя удалить owner'а. Сначала transfer ownership.")
        return redirect('hello:org_members', org_slug=org_slug)
    member.deactivated_at = timezone.now()
    member.save(update_fields=['deactivated_at'])
    AuditLog.log(
        actor=request.user,
        action='org.members.remove',
        organization=org,
        object_type='OrganizationMember',
        object_id=member.id,
        payload={'user': member.user.username, 'former_role': member.role},
        request=request,
    )
    messages.success(request, f'{member.user.username} отключён от команды')
    return redirect('hello:org_members', org_slug=org_slug)


# ============================================================
# Принятие приглашения (требует auth)
# ============================================================
@login_required(login_url='accounts:login')
def org_invite_accept(request, org_slug, token):
    """Принимает invite. Если уже member — просто redirect в org."""
    org = get_object_or_404(Organization, slug=org_slug)
    invite = get_object_or_404(OrganizationInvite, token=token, organization=org)

    if invite.accepted_at:
        messages.info(request, 'Это приглашение уже принято.')
        return redirect('hello:org_dashboard', org_slug=org.slug)
    if invite.is_expired():
        messages.error(request, "Приглашение истекло (7 дней). Попросите admin'а отправить новое.")
        return redirect('hello:org_list')

    # Соответствие email — мягкая проверка (warning, не блок)
    if invite.email.lower() != (request.user.email or '').lower():
        messages.warning(
            request,
            f'⚠ Приглашение отправлено на {invite.email}, а вы вошли как {request.user.email}. Принимаем.',
        )

    if org.has_member(request.user):
        invite.accepted_at = timezone.now()
        invite.accepted_by = request.user
        invite.save(update_fields=['accepted_at', 'accepted_by'])
        return redirect('hello:org_dashboard', org_slug=org.slug)

    OrganizationMember.objects.create(
        organization=org,
        user=request.user,
        role=invite.role,
        invited_by=invite.invited_by,
    )
    invite.accepted_at = timezone.now()
    invite.accepted_by = request.user
    invite.save(update_fields=['accepted_at', 'accepted_by'])

    AuditLog.log(
        actor=request.user,
        action='org.members.join',
        organization=org,
        object_type='OrganizationMember',
        object_id=invite.id,
        payload={'role': invite.role, 'invite_id': invite.id},
        request=request,
    )

    messages.success(request, f'🎉 Вы присоединились к «{org.name}»!')
    return redirect('hello:org_dashboard', org_slug=org.slug)


# ============================================================
# Audit-log viewer
# ============================================================
@login_required(login_url='accounts:login')
@require_org_permission('audit.read')
@require_feature('enterprise_audit_log', organization_getter=_request_org)
def org_audit(request, org_slug):
    org = request.organization
    action_filter = (request.GET.get('action') or '').strip()
    actor_filter = (request.GET.get('actor') or '').strip()
    qs = org.audit_log.select_related('actor').order_by('-timestamp')
    if action_filter:
        qs = qs.filter(action__startswith=action_filter)
    if actor_filter:
        qs = qs.filter(actor__username__icontains=actor_filter)
    entries = qs[:200]
    distinct_actions = sorted(set(org.audit_log.values_list('action', flat=True)[:500]))
    return render(
        request,
        'orgs/audit.html',
        {
            'org': org,
            'entries': entries,
            'distinct_actions': distinct_actions,
            'action_filter': action_filter,
            'actor_filter': actor_filter,
        },
    )


# ============================================================
# Settings (owner+admin)
# ============================================================
# ============================================================
# Approval workflow для проектов (BOM-готовых)
# ============================================================
@login_required(login_url='accounts:login')
@require_org_permission('project.read')
@require_feature('enterprise_approval_workflow', organization_getter=_request_org)
def org_approval_queue(request, org_slug):
    """Очередь проектов на ревью. Видна reviewer+, action только reviewer+."""
    from .models import SchematicProject

    org = request.organization
    pending = (
        SchematicProject.objects.filter(
            organization=org, approval_state='pending_review', deleted_at__isnull=True
        )
        .select_related('user')
        .order_by('updated_at')
    )
    return render(
        request,
        'orgs/approval_queue.html',
        {
            'org': org,
            'pending': pending,
            'can_approve': user_can(request.user, org, 'bom.approve'),
        },
    )


@require_POST
@login_required(login_url='accounts:login')
@require_org_permission('bom.submit')
@require_feature('enterprise_approval_workflow', organization_getter=_request_org)
def project_submit_for_review(request, org_slug, pk):
    """Engineer submits project for review."""
    from .models import SchematicProject

    org = request.organization
    project = get_object_or_404(SchematicProject, pk=pk, organization=org)
    if project.approval_state == 'pending_review':
        messages.info(request, 'Уже на ревью')
        return redirect('hello:org_approval_queue', org_slug=org_slug)
    project.approval_state = 'pending_review'
    project.save(update_fields=['approval_state', 'updated_at'])
    AuditLog.log(
        actor=request.user,
        action='bom.submit',
        organization=org,
        object_type='SchematicProject',
        object_id=project.id,
        payload={'project_name': project.name, 'from_state': 'draft'},
        request=request,
    )
    messages.success(request, f'✅ «{project.name}» отправлен на ревью')
    return redirect('hello:org_approval_queue', org_slug=org_slug)


@require_POST
@login_required(login_url='accounts:login')
@require_org_permission('bom.approve')
@require_feature('enterprise_approval_workflow', organization_getter=_request_org)
def project_approve(request, org_slug, pk):
    from .models import SchematicProject

    org = request.organization
    project = get_object_or_404(SchematicProject, pk=pk, organization=org)
    comment = (request.POST.get('comment') or '').strip()[:500]
    project.approval_state = 'approved'
    project.save(update_fields=['approval_state', 'updated_at'])
    AuditLog.log(
        actor=request.user,
        action='bom.approve',
        organization=org,
        object_type='SchematicProject',
        object_id=project.id,
        payload={'project_name': project.name, 'comment': comment},
        request=request,
    )
    messages.success(request, f'✅ «{project.name}» одобрен')
    return redirect('hello:org_approval_queue', org_slug=org_slug)


@require_POST
@login_required(login_url='accounts:login')
@require_org_permission('bom.reject')
@require_feature('enterprise_approval_workflow', organization_getter=_request_org)
def project_reject(request, org_slug, pk):
    from .models import SchematicProject

    org = request.organization
    project = get_object_or_404(SchematicProject, pk=pk, organization=org)
    comment = (request.POST.get('comment') or '').strip()[:500]
    project.approval_state = 'rejected'
    project.save(update_fields=['approval_state', 'updated_at'])
    AuditLog.log(
        actor=request.user,
        action='bom.reject',
        organization=org,
        object_type='SchematicProject',
        object_id=project.id,
        payload={'project_name': project.name, 'comment': comment},
        request=request,
    )
    messages.warning(request, f'❌ «{project.name}» отклонён')
    return redirect('hello:org_approval_queue', org_slug=org_slug)


@login_required(login_url='accounts:login')
@require_org_permission('api.token.create')
@require_feature('enterprise_api_tokens', organization_getter=_request_org)
def org_api_tokens(request, org_slug):
    """API tokens management: list + create-form."""
    org = request.organization
    tokens = org.api_tokens.order_by('-created_at')
    return render(
        request,
        'orgs/api_tokens.html',
        {
            'org': org,
            'tokens': tokens,
            'just_created_token': request.session.pop('_just_created_token', None),
        },
    )


@require_POST
@login_required(login_url='accounts:login')
@require_org_permission('api.token.create')
@require_feature('enterprise_api_tokens', organization_getter=_request_org)
def org_api_token_create(request, org_slug):
    from .models import OrganizationApiToken

    org = request.organization
    name = (request.POST.get('name') or '').strip()[:120]
    scope = (request.POST.get('scope') or 'projects.read').split(',')
    if not name:
        messages.error(request, 'Имя обязательно')
        return redirect('hello:org_api_tokens', org_slug=org.slug)
    token = 'dolg_' + secrets.token_urlsafe(40)
    OrganizationApiToken.objects.create(
        organization=org,
        name=name,
        token=token,
        scope=[s.strip() for s in scope if s.strip()],
        created_by=request.user,
    )
    # Один раз показываем сырой token (потом только маска)
    request.session['_just_created_token'] = token
    AuditLog.log(
        actor=request.user,
        action='api.token.create',
        organization=org,
        object_type='OrganizationApiToken',
        payload={'name': name, 'scope': scope},
        request=request,
    )
    messages.success(request, '🔑 Токен создан. Сохраните его — больше не покажем.')
    return redirect('hello:org_api_tokens', org_slug=org.slug)


@require_POST
@login_required(login_url='accounts:login')
@require_org_permission('api.token.revoke')
@require_feature('enterprise_api_tokens', organization_getter=_request_org)
def org_api_token_revoke(request, org_slug, token_id):
    from .models import OrganizationApiToken

    org = request.organization
    tok = get_object_or_404(OrganizationApiToken, id=token_id, organization=org)
    tok.revoked_at = timezone.now()
    tok.save(update_fields=['revoked_at'])
    AuditLog.log(
        actor=request.user,
        action='api.token.revoke',
        organization=org,
        object_type='OrganizationApiToken',
        object_id=tok.id,
        payload={'name': tok.name},
        request=request,
    )
    messages.success(request, 'Токен отозван')
    return redirect('hello:org_api_tokens', org_slug=org.slug)


@login_required(login_url='accounts:login')
@require_org_permission('audit.read')
@require_feature('enterprise_org_analytics', organization_getter=_request_org)
def org_analytics(request, org_slug):
    """Dashboard аналитики: топ-users по активности, audit-stats."""
    from collections import Counter
    from datetime import timedelta

    from django.db.models import Count

    org = request.organization
    cutoff = timezone.now() - timedelta(days=30)

    # Топ-actor по числу записей в audit за 30 дней
    top_actors = (
        org.audit_log.filter(timestamp__gte=cutoff, actor__isnull=False)
        .values('actor__username')
        .annotate(n=Count('id'))
        .order_by('-n')[:10]
    )

    # Топ-actions
    action_counts = Counter(
        org.audit_log.filter(timestamp__gte=cutoff).values_list('action', flat=True)
    ).most_common(15)

    # Approval-stats
    pending = org.projects.filter(approval_state='pending_review').count()
    approved = org.projects.filter(approval_state='approved').count()
    rejected = org.projects.filter(approval_state='rejected').count()

    return render(
        request,
        'orgs/analytics.html',
        {
            'org': org,
            'top_actors': top_actors,
            'action_counts': action_counts,
            'pending': pending,
            'approved': approved,
            'rejected': rejected,
            'period_days': 30,
        },
    )


@login_required(login_url='accounts:login')
@require_org_permission('org.update')
def org_settings(request, org_slug):
    org = request.organization

    if request.method == 'POST':
        org.name = (request.POST.get('name') or org.name).strip()[:200]
        org.billing_email = (request.POST.get('billing_email') or org.billing_email).strip()
        org.custom_color = (request.POST.get('custom_color') or '').strip()[:20]
        # Policies
        settings_data = dict(org.settings or {})
        for key in (
            'require_2fa',
            'disable_ai',
            'disable_public_sharing',
            'require_order_approval',
            'sso_enabled',
        ):
            settings_data[key] = bool(request.POST.get(f'policy_{key}'))
        allowed_domains = (request.POST.get('allowed_domains') or '').strip()
        settings_data['allowed_domains'] = [
            d.strip().lower() for d in allowed_domains.split(',') if d.strip()
        ]
        # SSO provider config (mock)
        sso_provider = (request.POST.get('sso_provider') or '').strip()
        if sso_provider in ('azure', 'okta', 'google'):
            settings_data['sso_provider'] = sso_provider
        org.settings = settings_data
        # Logo upload (если есть)
        if 'custom_logo' in request.FILES:
            logo = request.FILES['custom_logo']
            ALLOWED = {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml'}
            MAX_SIZE = 5 * 1024 * 1024  # 5 МБ
            if logo.size > MAX_SIZE:
                messages.error(request, 'Логотип >5 МБ — не загружен')
            elif logo.content_type not in ALLOWED:
                messages.error(request, 'Логотип: JPEG/PNG/GIF/WebP/SVG')
            else:
                org.custom_logo = logo
                messages.success(request, '🎨 Logo обновлён')
        org.save()
        AuditLog.log(
            actor=request.user,
            action='org.settings_update',
            organization=org,
            object_type='Organization',
            object_id=org.id,
            payload={'settings': settings_data},
            request=request,
        )
        messages.success(request, 'Настройки сохранены')
        return redirect('hello:org_settings', org_slug=org.slug)

    return render(
        request,
        'orgs/settings.html',
        {
            'org': org,
            'can_delete': user_can(request.user, org, 'org.delete'),
        },
    )


# ============================================================
# Catalog: добавление товаров в общий каталог Enterprise-членом
# ============================================================
@require_org_permission('catalog.product.create')
def org_catalog_add(request, org_slug):
    """GET — форма; POST — создаёт shop.Product, помечая источник в parameters.

    Доступно engineer+ роли. Товар идёт в общий каталог `/shop/`, но в
    `parameters._created_by_org = <slug>` остаётся след — Enterprise-команда
    может через каталог-фильтр увидеть «свои» добавления.

    Картинку можно НЕ загружать — товар появится с category-плейсхолдером.
    Pillow-арт админ может догенерить отдельной командой при желании.
    """
    from shop.models import Category, Product

    org = request.organization
    categories = Category.objects.all().order_by('name')
    errors = []
    form_data = {}

    if request.method == 'POST':
        form_data = request.POST.dict()
        # ── Валидация ──
        name = (request.POST.get('name') or '').strip()
        category_id = request.POST.get('category_id') or ''
        price_raw = (request.POST.get('price') or '').strip()
        stock_raw = (request.POST.get('stock') or '0').strip()
        description = (request.POST.get('description') or '').strip()
        manufacturer = (request.POST.get('manufacturer') or 'other').strip()
        part_number = (request.POST.get('part_number') or '').strip()
        package_type = (request.POST.get('package_type') or '').strip()
        datasheet_url = (request.POST.get('datasheet_url') or '').strip()
        lifecycle_status = (request.POST.get('lifecycle_status') or 'active').strip()

        if not name:
            errors.append('Название товара обязательно.')
        if not category_id:
            errors.append('Выберите категорию.')
        if not description:
            errors.append('Краткое описание обязательно.')
        try:
            from decimal import Decimal, InvalidOperation

            price = Decimal(price_raw.replace(',', '.')) if price_raw else None
            if price is None or price < 0:
                errors.append('Укажите корректную цену.')
            # Product.price = DecimalField(max_digits=10, decimal_places=2).
            # Граница: 99999999.99. Если юзер вписал 1e28 (scientific), Decimal
            # это съест, но DB сломается при следующем чтении. Каппируем явно.
            elif price >= Decimal('100000000') or price.adjusted() > 8:
                errors.append('Цена слишком велика. Максимум 99 999 999.99 ₽.')
                price = None
            # Квантизация до 2 знаков — иначе DB cast потом тоже может ругаться
            elif price is not None:
                price = price.quantize(Decimal('0.01'))
        except InvalidOperation, ValueError:
            errors.append('Цена должна быть числом.')
            price = None
        try:
            stock = int(stock_raw) if stock_raw else 0
            if stock < 0:
                errors.append('Запас не может быть отрицательным.')
        except ValueError:
            errors.append('Запас должен быть целым числом.')
            stock = 0

        category = None
        if category_id and not errors:
            try:
                category = Category.objects.get(pk=int(category_id))
            except Category.DoesNotExist, ValueError:
                errors.append('Категория не найдена.')

        if not errors and category is not None and price is not None:
            # Свободные параметры через key=value\n…
            params = {}
            for line in (request.POST.get('parameters_raw') or '').splitlines():
                if '=' in line:
                    k, v = line.split('=', 1)
                    k, v = k.strip(), v.strip()
                    if k and v and not k.startswith('_'):
                        params[k] = v
            # Метка «откуда товар появился» — для audit и фильтрации
            params['_created_by_org'] = org.slug
            params['_created_by_user'] = request.user.username

            # «Свой бренд» — если юзер выбрал собственную org как производителя,
            # сохраняем её slug в parameters, а в Product.manufacturer ставим 'other'
            # (enum-поле не имеет нашей org в choices). brand_badge при отображении
            # подберёт имя org'а из parameters._manufacturer_org_name.
            if manufacturer == f'__org__:{org.slug}':
                params['_manufacturer_org_slug'] = org.slug
                params['_manufacturer_org_name'] = org.name
                manufacturer_value = 'other'
            else:
                manufacturer_value = manufacturer if manufacturer else 'other'

            base_slug = slugify(part_number or name) or f'p-{secrets.token_hex(4)}'
            slug = base_slug
            i = 2
            while Product.objects.filter(slug=slug).exists():
                slug = f'{base_slug}-{i}'
                i += 1

            product = Product(
                name=name,
                category=category,
                description=description,
                price=price,
                stock=stock,
                manufacturer=manufacturer_value,
                part_number=part_number,
                package_type=package_type,
                datasheet_url=datasheet_url,
                lifecycle_status=lifecycle_status
                if lifecycle_status in {'active', 'nrnd', 'eol', 'obsolete'}
                else 'active',
                parameters=params,
                slug=slug,
            )
            uploaded = request.FILES.get('image')
            if uploaded:
                product.image = uploaded
            # Datasheet PDF file → сохраняем в media/datasheets/<slug>.<ext>, ставим
            # datasheet_url на этот путь. Поле Product.datasheet_url URLField, но
            # принимает относительные пути через MEDIA_URL.
            ds_file = request.FILES.get('datasheet_file')
            if ds_file:
                from pathlib import Path as _Path

                from django.conf import settings as dj_settings
                from django.core.files.storage import default_storage

                ext = (_Path(ds_file.name).suffix or '.pdf').lower()
                ds_path = f'datasheets/{slug}{ext}'
                saved_path = default_storage.save(ds_path, ds_file)
                product.datasheet_url = dj_settings.MEDIA_URL + saved_path
                params['_datasheet_file'] = saved_path
                product.parameters = params
            product.save()

            AuditLog.log(
                actor=request.user,
                action='catalog.product.create',
                organization=org,
                object_type='Product',
                object_id=str(product.id),
                payload={
                    'name': name,
                    'category': category.slug,
                    'slug': slug,
                    'has_image': bool(uploaded),
                    'has_datasheet': bool(ds_file),
                },
                request=request,
            )
            messages.success(request, f'Товар «{product.name}» добавлен в каталог.')
            return redirect('shop:product_detail', slug=product.slug)

    # «Свой бренд» опция = текущая организация. Идёт ПЕРВОЙ в списке, чтобы юзер
    # сразу видел свою компанию. Особое значение `__org__:<slug>` — view распознаёт
    # его в save-ветке.
    manufacturer_choices = [
        (f'__org__:{org.slug}', f'{org.name} (моя организация)'),
        ('other', 'Other / не указан'),
        ('yageo', 'Yageo'),
        ('vishay', 'Vishay'),
        ('murata', 'Murata'),
        ('tdk', 'TDK'),
        ('kemet', 'KEMET'),
        ('st', 'STMicroelectronics'),
        ('nxp', 'NXP'),
        ('ti', 'Texas Instruments'),
        ('infineon', 'Infineon'),
        ('onsemi', 'onsemi'),
        ('bourns', 'Bourns'),
        ('panasonic', 'Panasonic'),
        ('nichicon', 'Nichicon'),
        ('wurth', 'Würth Elektronik'),
    ]

    return render(
        request,
        'orgs/catalog_add.html',
        {
            'org': org,
            'categories': categories,
            'manufacturer_choices': manufacturer_choices,
            'lifecycle_choices': [
                ('active', 'Active'),
                ('nrnd', 'NRND'),
                ('eol', 'EOL'),
                ('obsolete', 'Obsolete'),
            ],
            'errors': errors,
            'form_data': form_data,
        },
    )
