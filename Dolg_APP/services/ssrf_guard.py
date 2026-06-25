"""SSRF-guard helpers для server-side HTTP-запросов с user-controlled URL.

Используется когда мы принимаем URL от пользователя (или admin) и должны
его получить с нашего сервера — типичный кейс: импорт каталога по URL,
fetch user avatar, OG-preview. Без guard'а юзер может направить нас в
cloud-metadata (http://169.254.169.254 на AWS/GCP/Yandex Cloud, который
возвращает IAM-токены), на внутренние сервисы по 127.0.0.1, в SSRF
по 0.0.0.0 / IPv6 ::1 / link-local fe80::, в private RFC1918 сети.

Использование::

    from Dolg_APP.services.ssrf_guard import safe_fetch_url, UrlBlocked

    try:
        response = safe_fetch_url('https://example.com/datasheet.pdf')
    except UrlBlocked as exc:
        return JsonResponse({'error': str(exc)}, status=400)

Hardcoded trusted internal/service URL'ы проходят через
обычные ``requests``-вызовы — для них guard не нужен.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import requests

ALLOWED_SCHEMES = frozenset({'https'})
MAX_REDIRECTS = 5
DEFAULT_TIMEOUT = 15
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 МБ


class UrlBlocked(Exception):
    """URL отклонён guard'ом — либо схема, либо целевая сеть запрещены."""


def _is_blocked_ip(ip_str: str) -> bool:
    """True если IP — loopback / private / link-local / multicast / reserved / unspecified."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        # Невалидный IP — однозначно отклоняем.
        return True
    if ip.is_loopback:
        return True
    if ip.is_private:
        return True
    if ip.is_link_local:
        return True
    if ip.is_multicast:
        return True
    if ip.is_reserved:
        return True
    if ip.is_unspecified:
        return True
    # AWS / GCP / Azure / Yandex Cloud метаданные:
    # 169.254.169.254 — link_local уже покрывает, но явно для ясности.
    metadata_ips = {'169.254.169.254', '169.254.170.2', 'fd00:ec2::254'}
    if ip_str in metadata_ips:
        return True
    return False


def _validate_url(url: str) -> tuple[str, str, int]:
    """Парсит URL и проверяет схему. Возвращает (scheme, host, port)."""
    if not url or not isinstance(url, str):
        raise UrlBlocked('URL пуст или не строка.')
    if len(url) > 2048:
        raise UrlBlocked('URL слишком длинный (>2048).')
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UrlBlocked(f'Запрещённая схема: {parsed.scheme!r} (разрешены только https).')
    if not parsed.hostname:
        raise UrlBlocked('URL не содержит hostname.')
    if '@' in parsed.netloc:
        raise UrlBlocked('Userinfo в URL не разрешено (потенциальный obfuscation).')
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    if port < 1 or port > 65535:
        raise UrlBlocked(f'Невалидный порт: {port}.')
    # Запрещаем нестандартные порты, чтобы не дотянуться до 22 (SSH),
    # 25 (SMTP), 6379 (Redis), 9200 (ES) и т.п.
    if port not in (80, 443):
        raise UrlBlocked(f'Запрещённый порт: {port} (разрешены 80 и 443).')
    return parsed.scheme, parsed.hostname, port


def _resolve_and_check_dns(hostname: str) -> str:
    """Резолвит hostname → IP, проверяет что не в blocklist. Возвращает резолвенный IP."""
    try:
        # getaddrinfo возвращает все семейства (v4 + v6) — проверяем каждый.
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise UrlBlocked(f'Не удалось разрешить имя {hostname!r}: {exc}.') from exc
    if not infos:
        raise UrlBlocked(f'DNS-резолв вернул пустой набор для {hostname!r}.')
    resolved_ips = []
    for info in infos:
        ip_str = info[4][0]
        if _is_blocked_ip(ip_str):
            raise UrlBlocked(
                f'IP {ip_str} (резолв {hostname!r}) — '
                'запрещён: loopback/private/link-local/multicast/metadata.'
            )
        resolved_ips.append(ip_str)
    return resolved_ips[0]


def safe_fetch_url(
    url: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    method: str = 'GET',
    max_size: int = MAX_CONTENT_LENGTH,
    allow_redirects: bool = True,
    headers: dict | None = None,
) -> requests.Response:
    """Безопасный HTTP GET (или другой method) с защитой от SSRF.

    Шаги:
    1. Парс URL → проверка схемы/порта/format'а.
    2. DNS-резолв → проверка IP (no loopback/private/link-local/metadata).
    3. Сам HTTP-запрос с timeout, max-size, ограниченным числом redirect'ов.
    4. Если redirect — повторная DNS-проверка для нового host'а
       (chase_redirects сами проверяет каждый hop).

    Raises UrlBlocked если URL отклонён. Иначе возвращает requests.Response.
    Content-Length ≤ max_size; иначе UrlBlocked.
    """
    _, hostname, _port = _validate_url(url)
    _resolve_and_check_dns(hostname)

    # Своя сессия с manual redirect-tracking, чтобы каждый hop тоже проверять.
    session = requests.Session()
    session.max_redirects = MAX_REDIRECTS
    current_url = url
    for _hop in range(MAX_REDIRECTS + 1):
        response = session.request(
            method,
            current_url,
            timeout=timeout,
            allow_redirects=False,
            headers=headers or {},
            stream=True,
        )
        # Размер по заголовку
        cl = response.headers.get('Content-Length')
        if cl and int(cl) > max_size:
            response.close()
            raise UrlBlocked(f'Content-Length {cl} превышает лимит {max_size}.')
        if response.is_redirect and allow_redirects:
            new_url = response.headers.get('Location', '')
            response.close()
            if not new_url:
                raise UrlBlocked('Redirect без Location заголовка.')
            # Validate new URL с тем же guard'ом — следующий hop.
            _, new_host, _ = _validate_url(new_url)
            _resolve_and_check_dns(new_host)
            current_url = new_url
            continue
        # Финальный ответ — материализуем content с проверкой размера.
        chunks = []
        downloaded = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            downloaded += len(chunk)
            if downloaded > max_size:
                response.close()
                raise UrlBlocked(f'Загружено {downloaded} байт, превышен лимит {max_size}.')
            chunks.append(chunk)
        # Перепаковываем content в response для удобства caller'а.
        response._content = b''.join(chunks)
        return response
    raise UrlBlocked(f"Слишком много redirect'ов (>{MAX_REDIRECTS}).")
