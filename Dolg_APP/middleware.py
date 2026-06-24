"""Custom middlewares для DOLG.

AnonymizeIPMiddleware — 152-ФЗ / GDPR compliance:
  - Без согласия на «Аналитика» (cookie 'dolg_cookie_consent') IP юзера
    в request.META['REMOTE_ADDR'] обнуляется в последнем октете
    (IPv4: 192.168.1.42 → 192.168.1.0; IPv6: усекаем до /64).
  - Это влияет на стандартные access-логи Django (они используют REMOTE_ADDR),
    Sentry, и любую инициализацию через get_client_ip().
  - Авторизованные юзеры тоже анонимизируются, кроме случая когда
    consent.analytics=True (тогда оригинальный IP остаётся).

AnonSessionExpiryMiddleware — для guest-сессий ставит TTL = 24 часа
(вместо дефолтных 2 недель), чтобы legacy-корзины анонимов не висели
вечно. Авторизованные сессии — стандартный SESSION_COOKIE_AGE.
"""

import json


class HealthzMiddleware:
    """Return health probes before URLConf imports the whole application."""

    HEALTH_PATHS = {'/healthz', '/healthz/'}
    READY_PATHS = {'/readyz', '/readyz/'}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info in self.HEALTH_PATHS:
            from .health import healthz

            return healthz(request)
        if request.path_info in self.READY_PATHS:
            from .health import readyz

            return readyz(request)
        return self.get_response(request)


class RequestBodyLimitMiddleware:
    """Reject oversized request bodies before Django reads them into memory."""

    DEFAULT_API_PREFIXES = (
        '/api/',
        '/accounts/api/',
        '/admin-portal/api/',
        '/cad/api/',
        '/projects/api/',
        '/simulation/api/',
        '/staff/ops/api/',
    )

    JSON_CONTENT_TYPES = (
        'application/json',
        'application/ld+json',
    )

    UPLOAD_CONTENT_TYPES = (
        'multipart/form-data',
        'application/x-www-form-urlencoded',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        limit = self._limit_for(request)
        if limit and self._content_length(request) > limit:
            from django.http import JsonResponse

            return JsonResponse(
                {
                    'error': 'request_too_large',
                    'limit_bytes': limit,
                },
                status=413,
            )
        return self.get_response(request)

    def _limit_for(self, request):
        from django.conf import settings

        content_type = request.META.get('CONTENT_TYPE', '').split(';', 1)[0].strip().lower()
        path = request.path_info or request.path
        api_prefixes = getattr(settings, 'DOLG_BODY_LIMIT_API_PREFIXES', self.DEFAULT_API_PREFIXES)

        if content_type in self.UPLOAD_CONTENT_TYPES:
            return int(getattr(settings, 'DOLG_MAX_UPLOAD_BODY_BYTES', 32 * 1024 * 1024))
        if content_type in self.JSON_CONTENT_TYPES or path.startswith(tuple(api_prefixes)):
            return int(getattr(settings, 'DOLG_MAX_JSON_BODY_BYTES', 2 * 1024 * 1024))
        return 0

    @staticmethod
    def _content_length(request):
        try:
            return int(request.META.get('CONTENT_LENGTH') or 0)
        except (TypeError, ValueError):
            return 0


def _parse_consent(request):
    """Возвращает dict с consent или {} если не задано."""
    raw = request.COOKIES.get('dolg_cookie_consent')
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def _anonymize_ipv4(ip):
    """192.168.1.42 → 192.168.1.0"""
    parts = ip.split('.')
    if len(parts) != 4:
        return ip
    return '.'.join(parts[:3] + ['0'])


def _anonymize_ipv6(ip):
    """fe80::1234:5678 → fe80::0  (усекаем до /64)"""
    # Простейшая обрезка: оставляем первые 4 группы, остальное — 0:0:0:0
    if ':' not in ip:
        return ip
    # Развернём (handle ::)
    if '::' in ip:
        left, _, right = ip.partition('::')
        left_parts = left.split(':') if left else []
        right_parts = right.split(':') if right else []
        missing = 8 - len(left_parts) - len(right_parts)
        parts = left_parts + ['0'] * missing + right_parts
    else:
        parts = ip.split(':')
    if len(parts) < 8:
        return ip
    parts = parts[:4] + ['0', '0', '0', '0']
    return ':'.join(parts)


def _anonymize(ip):
    if not ip:
        return ip
    if ':' in ip:
        return _anonymize_ipv6(ip)
    return _anonymize_ipv4(ip)


class AnonymizeIPMiddleware:
    """Обнуляет последний октет IPv4 / усекает IPv6 до /64 у юзеров без
    согласия на аналитику. Применяется к REMOTE_ADDR + HTTP_X_FORWARDED_FOR.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        consent = _parse_consent(request)
        if not consent.get('analytics'):
            # Анонимизируем
            remote = request.META.get('REMOTE_ADDR', '')
            if remote:
                request.META['REMOTE_ADDR'] = _anonymize(remote)
            xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
            if xff:
                # XFF может содержать список через запятую: client, proxy1, proxy2
                anon_list = [_anonymize(p.strip()) for p in xff.split(',')]
                request.META['HTTP_X_FORWARDED_FOR'] = ', '.join(anon_list)
        return self.get_response(request)


class AuditContextMiddleware:
    """Прозрачно прокидывает request в thread-local, чтобы AuditLog.log
    мог автоматически достать IP и User-Agent даже когда вызывается из
    глубоких функций (signals, save-handlers), куда нет прямого доступа
    к request.

    Использование:
        from Dolg_APP.middleware import get_current_request
        AuditLog.log(actor=user, action='x', request=get_current_request())
    """

    _thread_local = None

    def __init__(self, get_response):
        self.get_response = get_response
        import threading

        AuditContextMiddleware._thread_local = threading.local()

    def __call__(self, request):
        AuditContextMiddleware._thread_local.request = request
        try:
            return self.get_response(request)
        finally:
            # Чистим — иначе worker-thread может потечь между requests
            try:
                del AuditContextMiddleware._thread_local.request
            except AttributeError:
                pass


def get_current_request():
    """Возвращает текущий request (если в request-thread) или None.
    Безопасно для использования в save()-handlers, signals, и т.п.
    """
    tl = AuditContextMiddleware._thread_local
    if tl is None:
        return None
    return getattr(tl, 'request', None)


class AnonSessionExpiryMiddleware:
    """Для guest-сессий — TTL 24 часа (вместо 2 недель).
    Авторизованные — стандартный SESSION_COOKIE_AGE.
    """

    GUEST_TTL_SECONDS = 24 * 3600

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Liveness probe должен оставаться полностью без БД: не создаем
        # гостевую session-cookie ради healthcheck.
        if request.path == '/healthz/':
            return response
        # Только после установки сессии; ничего не трогаем у auth-юзеров
        if hasattr(request, 'user') and not request.user.is_authenticated:
            if hasattr(request, 'session'):
                try:
                    if request.session.get_expiry_age() != self.GUEST_TTL_SECONDS:
                        request.session.set_expiry(self.GUEST_TTL_SECONDS)
                except Exception:
                    pass
        return response


class Require2FAMiddleware:
    """Защита от bypass: если у user'а есть подтверждённое TOTP-устройство,
    но текущая session НЕ прошла OTP-verify — редирект на /2fa/verify/.

    Срабатывает после стандартного login (password OK) — пользователь не
    получает доступ к страницам пока не введёт 2FA-код.

    ВАЖНО: должен стоять ПОСЛЕ OTPMiddleware и AuthenticationMiddleware,
    чтобы request.user.is_verified() был доступен.
    """

    # Эти пути доступны без 2FA challenge:
    # - login/logout (без них пользователь не сможет выйти / попробовать снова)
    # - сама /2fa/verify/ и admin login (defense-in-depth)
    # - static/media для CSS+JS на странице verify
    # - healthz для liveness-probe
    EXEMPT_PREFIXES = (
        '/accounts/login/',
        '/accounts/logout/',
        '/accounts/password',
        '/2fa/verify/',
        '/admin/login/',
        '/admin/logout/',
        '/static/',
        '/media/',
        '/healthz/',
        '/readyz/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(request, 'user', None) or not request.user.is_authenticated:
            return self.get_response(request)
        if any(request.path.startswith(p) for p in self.EXEMPT_PREFIXES):
            return self.get_response(request)
        # is_verified() добавляется OTPMiddleware'ом
        if not getattr(request.user, 'is_verified', lambda: False)():
            # Импортируем lazily — circular: middleware → models → middleware
            from .two_factor import user_has_confirmed_totp

            if user_has_confirmed_totp(request.user):
                # Сохраняем целевой URL чтобы вернуть после успешного verify
                from django.shortcuts import redirect

                request.session['_dolg_pending_2fa_next'] = request.get_full_path()
                return redirect('hello:two_factor_verify')
        return self.get_response(request)
