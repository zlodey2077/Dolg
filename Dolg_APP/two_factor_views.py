"""View'ы для enrollment / verify / disable 2FA.

URLs (см. Dolg_APP/urls.py):
  /2fa/setup/    — GET (показывает QR) + POST (confirm с 6-значным кодом)
  /2fa/verify/   — login challenge, ввод TOTP/backup после password
  /2fa/disable/  — POST (отключить 2FA для текущего user'а)
  /2fa/backup/   — GET (показать оставшиеся backup-коды, перегенерировать)
"""
from __future__ import annotations

import base64
from io import BytesIO

import django_otp
import qrcode
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from . import two_factor


@login_required(login_url='accounts:login')
def two_factor_setup(request):
    """Enrollment. GET — показываем QR + раздел backup-кодов.
    POST — пользователь вводит первый код от Authenticator → confirm."""
    if two_factor.user_has_confirmed_totp(request.user):
        messages.info(request, '2FA уже включена. Для повторной настройки сначала отключите её.')
        return redirect('accounts:profile')

    device = two_factor.get_or_create_unconfirmed_totp(request.user)

    if request.method == 'POST':
        token = (request.POST.get('token') or '').strip().replace(' ', '')
        if two_factor.confirm_totp_device(device, token):
            messages.success(
                request,
                '✅ 2FA включена. Сохраните backup-коды — без них и без телефона восстановить доступ нельзя.'
            )
            # После confirm создаются backup-коды — показываем их один раз
            backup_codes = list(
                device.user.staticdevice_set.filter(name='backup').first().token_set.values_list('token', flat=True)
            )
            return render(request, 'auth/2fa_backup_codes.html', {
                'backup_codes': backup_codes,
                'is_freshly_generated': True,
            })
        messages.error(request, 'Неверный код. Попробуйте ещё раз — код в Authenticator меняется каждые 30 сек.')

    # GET (или POST с ошибкой): рисуем QR
    otpauth_url = device.config_url   # otpauth://totp/DOLG:alice@x.test?secret=...&issuer=DOLG
    qr_data_uri = _make_qr_data_uri(otpauth_url)
    return render(request, 'auth/2fa_setup.html', {
        'qr_data_uri': qr_data_uri,
        'otpauth_url': otpauth_url,
        'secret_b32': device.bin_key.hex(),  # на случай ручного ввода в Authenticator
    })


@require_POST
@login_required(login_url='accounts:login')
def two_factor_disable(request):
    """Удалить все TOTP+backup устройства user'а."""
    if two_factor.disable_2fa(request.user):
        messages.success(request, '🔓 2FA отключена. Рекомендуем включить обратно — она защищает аккаунт.')
    else:
        messages.info(request, '2FA не была включена.')
    return redirect('accounts:profile')


def two_factor_verify(request):
    """Login challenge — Require2FAMiddleware редиректит сюда юзера, который
    залогинен по password, но НЕ прошёл OTP в этой сессии.

    GET: форма ввода кода. POST: проверка токена → mark session как OTP-verified
    через django_otp.login(request, device).
    """
    user = request.user
    if not user.is_authenticated:
        return redirect('accounts:login')
    # Если 2FA уже пройдена в этой сессии (или вообще не настроена) — редиректим
    if user.is_verified() or not two_factor.user_has_confirmed_totp(user):
        return redirect(request.session.pop('_dolg_pending_2fa_next', None)
                        or reverse('accounts:profile'))

    if request.method == 'POST':
        token = (request.POST.get('token') or '').strip().replace(' ', '').replace('-', '')
        # Пробуем сначала TOTP — 6 цифр
        for device in TOTPDevice.objects.filter(user=user, confirmed=True):
            if device.verify_token(token):
                django_otp.login(request, device)
                messages.success(request, '✓ 2FA подтверждена.')
                next_url = request.session.pop('_dolg_pending_2fa_next', None) or reverse('accounts:profile')
                return redirect(next_url)
        # Затем backup-код — 8 символов, одноразовый
        for device in StaticDevice.objects.filter(user=user, confirmed=True):
            if device.verify_token(token):
                django_otp.login(request, device)
                remaining = two_factor.get_backup_codes_count(user)
                messages.warning(
                    request,
                    f'✓ Использован backup-код. Осталось {remaining} — рекомендуем перегенерировать.'
                )
                next_url = request.session.pop('_dolg_pending_2fa_next', None) or reverse('accounts:profile')
                return redirect(next_url)
        messages.error(request, 'Неверный код. Попробуйте снова или backup-код.')

    return render(request, 'auth/2fa_verify.html', {'username': user.username})


@require_GET
@login_required(login_url='accounts:login')
def two_factor_backup_codes_view(request):
    """Показать счётчик оставшихся backup-кодов. Для безопасности САМИ коды
    показываются только при initial-enrollment или при явной regen-кнопке."""
    if not two_factor.user_has_confirmed_totp(request.user):
        messages.warning(request, '2FA не настроена.')
        return redirect('hello:two_factor_setup')

    remaining = two_factor.get_backup_codes_count(request.user)
    return render(request, 'auth/2fa_backup_codes.html', {
        'remaining': remaining,
        'is_freshly_generated': False,
    })


@require_POST
@login_required(login_url='accounts:login')
def two_factor_backup_codes_regenerate(request):
    """Перегенерировать backup-коды (старые становятся невалидными)."""
    if not two_factor.user_has_confirmed_totp(request.user):
        return HttpResponseBadRequest('2FA not enabled')
    codes = two_factor._ensure_backup_codes(request.user)
    messages.warning(
        request,
        '🔄 Старые backup-коды отозваны. Запишите новые — они показаны ниже.'
    )
    return render(request, 'auth/2fa_backup_codes.html', {
        'backup_codes': codes,
        'is_freshly_generated': True,
    })


def _make_qr_data_uri(text: str) -> str:
    """Генерирует PNG-QR в формате data: URI (можно вставить в <img src=...>)
    без отдельного endpoint'а."""
    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode('ascii')
    return f'data:image/png;base64,{b64}'
