"""Mock-SSO для Enterprise.

В production здесь были бы реальные OIDC-handshake через `django-allauth`
(Azure AD / Okta / Google Workspace). Для дипломной версии — симуляция:
1. Юзер на /accounts/login/?sso=<org-slug> кликает «Sign in with SSO»
2. Перенаправление на /sso/<provider>/redirect/?org=<slug> — фейк-страница
   с кнопкой «Confirm sign-in as user@company.com» (имитирует страницу IdP)
3. POST с этой страницы → создаётся/находится user → auto-add в org → login
4. AuditLog: 'auth.sso_login'

Если организация не имеет SSO-настроенной (org.sso_config пуст) — кнопка
SSO не показывается; идёт обычный login.
"""
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.crypto import get_random_string
from django.views.decorators.http import require_GET, require_POST

from .models import AuditLog, Organization, OrganizationMember

User = get_user_model()


@require_GET
def sso_redirect(request, org_slug):
    """Mock IdP-redirect: показывает фейк-страницу «Sign-in to Azure AD».
    В реальной системе тут redirect на https://login.microsoftonline.com/...
    """
    org = get_object_or_404(Organization, slug=org_slug)
    if not settings.DEBUG and not getattr(settings, 'ALLOW_MOCK_SSO', False):
        messages.error(request, 'Mock SSO disabled outside DEBUG. Configure a real OIDC provider.')
        return redirect('accounts:login')
    if not org.settings.get('sso_enabled'):
        messages.error(request, f'SSO не настроен для «{org.name}».')
        return redirect('accounts:login')

    provider = org.settings.get('sso_provider', 'azure')
    # Генерируем nonce — anti-CSRF в SSO-flow
    nonce = get_random_string(32)
    request.session['sso_nonce'] = nonce
    request.session['sso_org_slug'] = org.slug

    return render(request, 'orgs/sso_mock.html', {
        'org': org,
        'provider': provider,
        'nonce': nonce,
        # Mock — заранее знаем какой email будет
        'suggested_email': f'employee@{org.settings.get("primary_domain", org.slug + ".com")}',
    })


@require_POST
def sso_callback(request, org_slug):
    """Mock OIDC callback. Принимает email + nonce, создаёт/находит юзера,
    добавляет в org с default-role, login.
    """
    org = get_object_or_404(Organization, slug=org_slug)
    if not settings.DEBUG and not getattr(settings, 'ALLOW_MOCK_SSO', False):
        messages.error(request, 'Mock SSO disabled outside DEBUG. Configure a real OIDC provider.')
        return redirect('accounts:login')
    if not org.settings.get('sso_enabled'):
        messages.error(request, f'SSO РЅРµ РЅР°СЃС‚СЂРѕРµРЅ РґР»СЏ В«{org.name}В».')
        return redirect('accounts:login')
    email = (request.POST.get('email') or '').strip().lower()
    nonce = request.POST.get('nonce', '')

    if not email:
        messages.error(request, 'SSO: пустой email')
        return redirect('accounts:login')

    allowed_domains = [
        str(domain).strip().lower().lstrip('@')
        for domain in (org.settings.get('allowed_domains') or [])
        if str(domain).strip()
    ]
    if allowed_domains:
        email_domain = email.rsplit('@', 1)[-1] if '@' in email else ''
        if email_domain not in allowed_domains:
            messages.error(request, 'SSO: email domain is not allowed for this organization')
            return redirect('accounts:login')

    expected_nonce = request.session.pop('sso_nonce', None)
    if not expected_nonce or expected_nonce != nonce:
        messages.error(request, 'SSO: nonce mismatch (защита от CSRF)')
        return redirect('accounts:login')

    # Создаём/находим user по email
    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            'username': email.split('@')[0] + '_' + secrets.token_hex(2),
        },
    )
    if created:
        user.set_unusable_password()  # не разрешаем password-login для SSO юзеров
        user.save()
        from accounts.models import UserProfile
        UserProfile.objects.get_or_create(user=user, defaults={'email_verified': True})

    # Auto-add в org с дефолтной ролью (engineer)
    if not org.has_member(user):
        OrganizationMember.objects.create(
            organization=org, user=user, role='engineer',
        )

    # Login
    user.backend = 'django.contrib.auth.backends.ModelBackend'
    login(request, user)

    AuditLog.log(
        actor=user, action='auth.sso_login', organization=org,
        object_type='User', object_id=user.id,
        payload={'provider': org.settings.get('sso_provider', 'mock'), 'created': created},
        request=request,
    )

    messages.success(request, f'🔐 SSO login успешен ({email})')
    return redirect('hello:org_dashboard', org_slug=org.slug)
