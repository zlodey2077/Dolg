import hashlib
import logging
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import EmailValidator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from .models import Address

_logger = logging.getLogger(__name__)

# Email verification: токен через django.core.signing (HMAC), без отдельной
# модели в БД — TTL 24 часа, payload = user.id. На пере-регистрацию старые
# токены становятся невалидны автоматически (проверяем email_verified).
EMAIL_VERIFY_SALT = 'dolg.email-verify.v1'
EMAIL_VERIFY_TTL_SEC = 24 * 3600


def _send_email_verification(request, user):
    """Отправляет письмо со ссылкой /accounts/verify-email/<token>/.
    Не падает при сбое SMTP — просто логирует, регистрация всё равно
    проходит. Пользователь может перезапросить через профиль."""
    if not user.email:
        return
    token = signing.dumps({'uid': user.id, 'email': user.email}, salt=EMAIL_VERIFY_SALT)
    verify_path = reverse('accounts:verify_email', kwargs={'token': token})
    verify_url = request.build_absolute_uri(verify_path)
    body = (
        f'Здравствуйте, {user.username}!\n\n'
        f'Подтвердите ваш e-mail для аккаунта DOLG, перейдя по ссылке:\n{verify_url}\n\n'
        f'Ссылка действительна {EMAIL_VERIFY_TTL_SEC // 3600} часа. '
        'Если вы не регистрировались — игнорируйте письмо.\n'
    )
    try:
        send_mail(
            'DOLG: подтвердите e-mail',
            body,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
    except Exception as exc:
        _logger.warning('Email-verification письмо не отправлено для %s: %s', user.email, exc)


# Лимиты для пользовательских строк профиля — Django CharField не enforce-ит
# их при прямом присваивании, поэтому слайсим на стороне view.
MAX_NAME_LEN = 50
MAX_BIO_LEN = 2000
_email_validator = EmailValidator()

ALLOWED_AVATAR_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
# Tier-based лимиты приходят из Dolg_APP.quotas.FREE_TIER / PRO_TIER.
# Хардкод-fallback на 5 МБ если quotas-модуль недоступен (миграции и т.п.)
MAX_AVATAR_SIZE = 5 * 1024 * 1024


def _profile_choice(profile, field_name, raw_value):
    allowed = {key for key, _label in profile._meta.get_field(field_name).choices}
    value = (raw_value or '').strip()
    if field_name == 'ai_backend' and value == 'cloud':
        value = 'local'
    current = getattr(profile, field_name)
    if field_name == 'ai_backend' and current == 'cloud':
        current = 'local'
    return value if value in allowed else current


def _max_upload_for_user(user) -> int:
    """Возвращает upload-limit в байтах для tier юзера.
    Free: 5 МБ, Pro: 25 МБ, staff: 100 МБ.
    """
    try:
        from Dolg_APP.quotas import get_limit

        mb = get_limit(user, 'max_upload_mb')
        if mb is None:
            return 100 * 1024 * 1024
        return int(mb) * 1024 * 1024
    except Exception:
        return MAX_AVATAR_SIZE


# Защита от brute-force на login: 5 неудачных попыток подряд → lockout
# на 60 секунд (хранится в сессии). Этого хватит, чтобы прогон по
# словарю стал бесполезным, но обычный пользователь, ошибшийся 1-2
# раза, не страдает.
LOGIN_FAIL_LIMIT = 5
LOGIN_LOCKOUT_SEC = 60
LOGIN_FAIL_WINDOW_SEC = 15 * 60


def _login_cache_identity(request, username: str) -> str:
    ip = (request.META.get('REMOTE_ADDR') or 'unknown').strip()
    normalized = (username or '').strip().lower()[:150]
    digest = hashlib.sha256(f'{normalized}|{ip}'.encode()).hexdigest()
    return digest


def _login_cache_key(kind: str, request, username: str) -> str:
    return f'dolg:login:{kind}:{_login_cache_identity(request, username)}'


def _cached_login_wait_seconds(request, username: str) -> int:
    locked_until = cache.get(_login_cache_key('locked_until', request, username))
    if not locked_until:
        return 0
    wait = int(float(locked_until) - time.time())
    if wait <= 0:
        cache.delete(_login_cache_key('locked_until', request, username))
        return 0
    return wait


def _record_cached_login_failure(request, username: str) -> tuple[int, bool]:
    fail_key = _login_cache_key('fails', request, username)
    fails = int(cache.get(fail_key, 0) or 0) + 1
    if fails >= LOGIN_FAIL_LIMIT:
        cache.set(
            _login_cache_key('locked_until', request, username),
            time.time() + LOGIN_LOCKOUT_SEC,
            LOGIN_LOCKOUT_SEC,
        )
        cache.delete(fail_key)
        return fails, True
    cache.set(fail_key, fails, LOGIN_FAIL_WINDOW_SEC)
    return fails, False


def _clear_cached_login_failures(request, username: str) -> None:
    cache.delete(_login_cache_key('fails', request, username))
    cache.delete(_login_cache_key('locked_until', request, username))


def _parse_address_fields(post_data):
    """Returns (fields_dict, error_message). error_message is None on success."""
    title = post_data.get('title', '').strip()
    addr = post_data.get('address', '').strip()
    city = post_data.get('city', '').strip()
    postal_code = post_data.get('postal_code', '').strip()
    country = post_data.get('country', 'Россия').strip()
    if not all([title, addr, city, postal_code]):
        return None, 'Заполните все обязательные поля адреса'
    return {
        'title': title,
        'address': addr,
        'city': city,
        'postal_code': postal_code,
        'country': country,
    }, None


def register(request):
    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        email = (request.POST.get('email') or '').strip()
        password = request.POST.get('password') or ''
        password_confirm = request.POST.get('password_confirm') or ''

        if not username or not email or not password:
            messages.error(request, 'Заполните все поля')
            return render(request, 'accounts/register.html')

        if password != password_confirm:
            messages.error(request, 'Пароли не совпадают')
            return render(request, 'accounts/register.html')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Пользователь с таким именем уже существует')
            return render(request, 'accounts/register.html')

        if User.objects.filter(email=email).exists():
            messages.error(request, 'Пользователь с такой почтой уже существует')
            return render(request, 'accounts/register.html')

        # Прогоняем пароль через AUTH_PASSWORD_VALIDATORS из settings.py
        # (мин. длина, common-passwords, attribute-similarity, numeric-only).
        # Раньше create_user пропускал эти проверки и принимал пароль "1".
        try:
            validate_password(password, user=User(username=username, email=email))
        except ValidationError as e:
            messages.error(request, 'Пароль слабый: ' + '; '.join(e.messages))
            return render(request, 'accounts/register.html')

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
        )
        # UserProfile создаётся автоматически сигналом в accounts/signals.py
        _send_email_verification(request, user)

        messages.success(
            request,
            'Аккаунт создан. На указанный e-mail отправлено письмо для подтверждения. '
            'Войдите с вашими данными — подтверждение можно сделать позже из профиля.',
        )
        return redirect('accounts:login')

    return render(request, 'accounts/register.html')


def verify_email(request, token):
    """Endpoint /accounts/verify-email/<token>/ — клик по ссылке из письма.
    signing.loads с TTL=24ч; проверяем что user/email актуален. Идемпотентно."""
    try:
        payload = signing.loads(token, salt=EMAIL_VERIFY_SALT, max_age=EMAIL_VERIFY_TTL_SEC)
    except signing.SignatureExpired:
        messages.error(request, 'Ссылка устарела. Запросите новую из профиля.')
        return redirect('accounts:profile' if request.user.is_authenticated else 'accounts:login')
    except signing.BadSignature:
        messages.error(request, 'Некорректная ссылка подтверждения.')
        return redirect('shop:index')

    user = get_object_or_404(User, pk=payload.get('uid'))
    # Проверка email актуального пользователя — если он сменил email после
    # выдачи токена, старый токен не должен подтверждать текущий адрес.
    if user.email != payload.get('email'):
        messages.error(request, 'E-mail в ссылке не совпадает с текущим адресом.')
        return redirect('accounts:profile' if request.user.is_authenticated else 'accounts:login')

    profile = user.profile
    if not profile.email_verified:
        profile.email_verified = True
        profile.save(update_fields=['email_verified'])
    messages.success(request, '✓ E-mail подтверждён.')
    return redirect('accounts:profile' if request.user.is_authenticated else 'accounts:login')


RESEND_VERIFY_COOLDOWN_SEC = 5 * 60  # 5 минут — спам-protection для SMTP


@login_required(login_url='accounts:login')
@require_http_methods(['POST'])
def resend_verification(request):
    """Перезапросить подтверждение из профиля (для тех, у кого истёк токен или
    кто пропустил первое письмо). Rate-limit 5 минут через session — иначе
    кнопкой можно засыпать SMTP-провайдера."""
    if request.user.profile.email_verified:
        messages.info(request, 'E-mail уже подтверждён.')
        return redirect('accounts:profile')

    now = time.time()
    last_resend = request.session.get('_last_verify_resend', 0)
    if now - last_resend < RESEND_VERIFY_COOLDOWN_SEC:
        wait = int(RESEND_VERIFY_COOLDOWN_SEC - (now - last_resend))
        messages.warning(request, f'Слишком часто. Подождите ещё {wait} с перед повторной отправкой.')
        return redirect('accounts:profile')

    _send_email_verification(request, request.user)
    request.session['_last_verify_resend'] = now
    messages.success(request, 'Письмо для подтверждения отправлено повторно.')
    return redirect('accounts:profile')


def login_view(request):
    if request.method == 'POST':
        # Rate-limit по сессии: после LOGIN_FAIL_LIMIT неудач — пауза LOGIN_LOCKOUT_SEC.
        # Состояние ('_login_fail_count', '_login_locked_until') хранится в session.
        now = time.time()
        locked_until = request.session.get('_login_locked_until', 0)
        if locked_until and now < locked_until:
            wait = int(locked_until - now)
            messages.error(request, f'Слишком много неудачных попыток. Подождите {wait} с.')
            return render(request, 'accounts/login.html')

        username = request.POST.get('username') or ''
        password = request.POST.get('password')
        cached_wait = _cached_login_wait_seconds(request, username)
        if cached_wait:
            messages.error(
                request, f'Слишком много неудачных попыток для этого логина. Подождите {cached_wait} с.'
            )
            return render(request, 'accounts/login.html')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            # Сбрасываем счётчик неудачных попыток после успешного входа.
            request.session.pop('_login_fail_count', None)
            request.session.pop('_login_locked_until', None)
            _clear_cached_login_failures(request, username)
            messages.success(request, f'Добро пожаловать, {user.username}!')
            # ?next= может прийти и через GET (если пришли с @login_required),
            # и через POST (если форма сохранила его в hidden input). POST имеет
            # приоритет — это то, что пользователь реально отправил.
            next_url = request.POST.get('next') or request.GET.get('next', '')
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
            return redirect('shop:index')
        else:
            fails = int(request.session.get('_login_fail_count', 0)) + 1
            request.session['_login_fail_count'] = fails
            _, cache_locked = _record_cached_login_failure(request, username)
            if fails >= LOGIN_FAIL_LIMIT:
                request.session['_login_locked_until'] = now + LOGIN_LOCKOUT_SEC
                messages.error(request, f'Превышен лимит попыток. Lockout {LOGIN_LOCKOUT_SEC} с.')
            elif cache_locked:
                messages.error(request, f'Превышен лимит попыток. Lockout {LOGIN_LOCKOUT_SEC} с.')
            else:
                left = LOGIN_FAIL_LIMIT - fails
                messages.error(request, f'Неверные учетные данные (осталось попыток: {left})')

    # has_sso: True если admin создал хотя бы один SocialApp в
    # /admin/socialaccount/socialapp/. Без SocialApp template-tag
    # {% provider_login_url 'google' %} бросает 500 — поэтому SSO-секцию
    # на странице login прячем когда provider не настроен.
    has_sso = False
    try:
        from allauth.socialaccount.models import SocialApp

        has_sso = SocialApp.objects.exists()
    except Exception:
        pass
    return render(request, 'accounts/login.html', {'has_sso': has_sso})


def logout_view(request):
    logout(request)
    messages.success(request, 'Вы успешно вышли из аккаунта')
    return redirect('shop:index')


@login_required(login_url='accounts:login')
def profile(request):
    profile = request.user.profile
    addresses = request.user.addresses.all()

    # Live-сводка лимитов и текущего использования — для прогресс-баров
    # и tier-badge в шаблоне.
    from Dolg_APP.quotas import usage_summary

    quota = usage_summary(request.user)
    orders_count = 0
    try:
        orders_count = request.user.orders.count()
    except Exception:
        orders_count = 0

    context = {
        'profile': profile,
        'addresses': addresses,
        'quota': quota,
        'orders_count': orders_count,
        'is_email_verified': bool(getattr(profile, 'email_verified', False)),
    }
    return render(request, 'accounts/profile.html', context)


@login_required(login_url='accounts:login')
def edit_profile(request):
    profile = request.user.profile

    if request.method == 'POST':
        # Валидация email — раньше принимали любую строку, включая "not@valid".
        new_email = (request.POST.get('email') or request.user.email or '').strip()
        if new_email and new_email != request.user.email:
            try:
                _email_validator(new_email)
            except ValidationError:
                messages.error(request, 'Некорректный e-mail')
                return redirect('accounts:edit_profile')
            # Уникальность — чтобы не сломать password-recovery (мы ищем по email).
            if User.objects.filter(email=new_email).exclude(pk=request.user.pk).exists():
                messages.error(request, 'Этот e-mail уже занят')
                return redirect('accounts:edit_profile')

        profile.phone = (request.POST.get('phone') or '').strip()[:50]
        profile.address = (request.POST.get('address') or '').strip()[:200]
        profile.city = (request.POST.get('city') or '').strip()[:100]
        profile.postal_code = (request.POST.get('postal_code') or '').strip()[:20]
        profile.country = (request.POST.get('country') or 'Россия').strip()[:80]
        profile.bio = (request.POST.get('bio') or '').strip()[:MAX_BIO_LEN]
        profile.display_name = (request.POST.get('display_name') or '').strip()[:80]
        profile.headline = (request.POST.get('headline') or '').strip()[:120]
        profile.preferred_theme = _profile_choice(
            profile, 'preferred_theme', request.POST.get('preferred_theme')
        )
        profile.accent_color = _profile_choice(profile, 'accent_color', request.POST.get('accent_color'))
        profile.default_unit_system = _profile_choice(
            profile, 'default_unit_system', request.POST.get('default_unit_system')
        )
        profile.start_page = _profile_choice(profile, 'start_page', request.POST.get('start_page'))
        profile.ai_tone = _profile_choice(profile, 'ai_tone', request.POST.get('ai_tone'))
        profile.interface_density = _profile_choice(
            profile, 'interface_density', request.POST.get('interface_density')
        )
        profile.workspace_layout = _profile_choice(
            profile, 'workspace_layout', request.POST.get('workspace_layout')
        )
        profile.ai_backend = _profile_choice(profile, 'ai_backend', request.POST.get('ai_backend'))
        profile.preferred_sim_engine = _profile_choice(
            profile, 'preferred_sim_engine', request.POST.get('preferred_sim_engine')
        )
        profile.preferred_render_mode = _profile_choice(
            profile, 'preferred_render_mode', request.POST.get('preferred_render_mode')
        )
        profile.enable_workspace_animations = request.POST.get('enable_workspace_animations') == 'on'
        profile.reduce_motion = request.POST.get('reduce_motion') == 'on'
        profile.show_advanced_tools = request.POST.get('show_advanced_tools') == 'on'
        profile.show_profile_public = request.POST.get('show_profile_public') == 'on'
        profile.show_engineering_badges = request.POST.get('show_engineering_badges') == 'on'
        profile.allow_ai_training = request.POST.get('allow_ai_training') == 'on'

        if 'avatar' in request.FILES:
            avatar = request.FILES['avatar']
            limit = _max_upload_for_user(request.user)
            if avatar.size > limit:
                limit_mb = limit // (1024 * 1024)
                messages.error(
                    request,
                    f'Размер файла не должен превышать {limit_mb} МБ для tier '
                    f'«{request.user.is_authenticated and "free"}». '
                    'Активируйте Pro для 25 МБ (4K-аватарки).',
                )
                return redirect('accounts:edit_profile')
            if avatar.content_type not in ALLOWED_AVATAR_TYPES:
                messages.error(request, 'Допустимые форматы: JPEG, PNG, GIF, WebP')
                return redirect('accounts:edit_profile')
            profile.avatar = avatar

        # Pro-only: custom logo на экспортах
        if 'pro_logo' in request.FILES:
            try:
                from Dolg_APP.quotas import get_user_tier

                is_pro = get_user_tier(request.user) in ('pro', 'unlimited')
            except Exception:
                is_pro = request.user.is_staff
            if not is_pro:
                messages.error(
                    request, '🔒 Загрузка логотипа доступна Pro-юзерам. Активируйте Pro в /billing/.'
                )
                return redirect('accounts:edit_profile')
            logo = request.FILES['pro_logo']
            if logo.size > _max_upload_for_user(request.user):
                messages.error(
                    request,
                    f'Логотип превышает лимит {_max_upload_for_user(request.user) // (1024 * 1024)} МБ.',
                )
                return redirect('accounts:edit_profile')
            if logo.content_type not in ALLOWED_AVATAR_TYPES:
                messages.error(request, 'Логотип: JPEG/PNG/GIF/WebP.')
                return redirect('accounts:edit_profile')
            profile.pro_logo = logo
            messages.success(request, '✅ Логотип загружен — будет на ваших PDF/Gerber-экспортах.')

        profile.save()

        # Все длины капируются: раньше можно было сохранить first_name на 5000
        # символов, переполнить таблицу и сломать админку отображения.
        email_changed = new_email != request.user.email
        request.user.email = new_email
        request.user.first_name = (request.POST.get('first_name') or '').strip()[:MAX_NAME_LEN]
        request.user.last_name = (request.POST.get('last_name') or '').strip()[:MAX_NAME_LEN]
        request.user.save()

        if email_changed:
            # Сбрасываем флаг и отправляем новое письмо подтверждения —
            # пользователь должен подтвердить новый адрес.
            profile.email_verified = False
            profile.save(update_fields=['email_verified'])
            _send_email_verification(request, request.user)
            messages.info(request, 'Email изменён — на новый адрес отправлено письмо подтверждения.')

        messages.success(request, 'Профиль успешно обновлен')
        return redirect('accounts:profile')

    context = {
        'profile': profile,
        'user': request.user,
        'theme_choices': profile.THEME_CHOICES,
        'accent_choices': profile.ACCENT_CHOICES,
        'unit_system_choices': profile.UNIT_SYSTEM_CHOICES,
        'start_page_choices': profile.START_PAGE_CHOICES,
        'ai_tone_choices': profile.AI_TONE_CHOICES,
        'interface_density_choices': profile.INTERFACE_DENSITY_CHOICES,
        'workspace_layout_choices': profile.WORKSPACE_LAYOUT_CHOICES,
        'ai_backend_choices': profile.AI_BACKEND_CHOICES,
        'sim_engine_choices': profile.SIM_ENGINE_CHOICES,
        'render_mode_choices': profile.RENDER_MODE_CHOICES,
    }
    return render(request, 'accounts/edit_profile.html', context)


@login_required(login_url='accounts:login')
def add_address(request):
    if request.method == 'POST':
        fields, error = _parse_address_fields(request.POST)
        if error:
            messages.error(request, error)
            return render(request, 'accounts/add_address.html')
        is_default = request.POST.get('is_default', False) == 'on'

        # Атомарная установка default: создание + сброс default у остальных
        # должны быть в одной транзакции, иначе при двух параллельных запросах
        # окажется два is_default=True или ни одного.
        with transaction.atomic():
            address = Address.objects.create(
                user=request.user,
                **fields,
                is_default=is_default,
            )
            if is_default:
                request.user.addresses.exclude(id=address.id).update(is_default=False)

        messages.success(request, 'Адрес добавлен')
        return redirect('accounts:profile')

    return render(request, 'accounts/add_address.html')


@login_required(login_url='accounts:login')
def edit_address(request, address_id):
    address = get_object_or_404(Address, id=address_id, user=request.user)

    if request.method == 'POST':
        fields, error = _parse_address_fields(request.POST)
        if error:
            messages.error(request, error)
            return render(request, 'accounts/edit_address.html', {'address': address})

        is_default = request.POST.get('is_default', False) == 'on'
        with transaction.atomic():
            for attr, value in fields.items():
                setattr(address, attr, value)
            address.is_default = is_default
            address.save()
            if is_default:
                request.user.addresses.exclude(id=address.id).update(is_default=False)

        messages.success(request, 'Адрес обновлен')
        return redirect('accounts:profile')

    context = {'address': address}
    return render(request, 'accounts/edit_address.html', context)


@login_required(login_url='accounts:login')
@require_http_methods(['POST'])
def delete_address(request, address_id):
    address = get_object_or_404(Address, id=address_id, user=request.user)
    address.delete()
    messages.success(request, 'Адрес удален')
    return redirect('accounts:profile')
