"""Защита Prometheus /metrics/.

`/metrics/` раскрывает внутренние счётчики (пути запросов, статусы, объёмы) —
публичный доступ нежелателен (information disclosure). Защищаем на уровне Django
как defense-in-depth (поверх возможной nginx-защиты): пускаем staff-пользователя
ИЛИ запрос с верным токеном `METRICS_TOKEN` (для машинного Prometheus-скрейпера).
Иначе — 403. Сравнение токена — constant-time.
"""

from __future__ import annotations

import hmac

from django.conf import settings
from django.http import HttpResponseForbidden
from django_prometheus.exports import ExportToDjangoView


def _provided_token(request) -> str:
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return auth[7:].strip()
    return (request.GET.get('token') or '').strip()


def _allowed(request) -> bool:
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated and user.is_staff:
        return True
    token = (getattr(settings, 'METRICS_TOKEN', '') or '').strip()
    if token:
        provided = _provided_token(request)
        if provided and hmac.compare_digest(provided, token):
            return True
    return False


def protected_metrics(request):
    """staff ИЛИ верный METRICS_TOKEN → отдаём метрики; иначе 403."""
    if not _allowed(request):
        return HttpResponseForbidden('metrics: forbidden')
    return ExportToDjangoView(request)
