"""Lightweight /healthz для liveness/readiness-проб (load balancer, uptime-monitor).

Без аутентификации (пробы анонимны) и без чувствительных данных. Возвращает 200,
если БД и кеш доступны, иначе 503 — чтобы оркестратор/балансировщик мог снять
нездоровый инстанс из ротации.
"""

from __future__ import annotations

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache


@never_cache
def healthz(request):
    checks: dict[str, str] = {}
    ok = True

    try:
        with connection.cursor() as cur:
            cur.execute('SELECT 1')
            cur.fetchone()
        checks['database'] = 'ok'
    except Exception:
        checks['database'] = 'error'
        ok = False

    try:
        cache.set('healthz:ping', '1', 5)
        checks['cache'] = 'ok' if cache.get('healthz:ping') == '1' else 'error'
        ok = ok and checks['cache'] == 'ok'
    except Exception:
        checks['cache'] = 'error'
        ok = False

    return JsonResponse(
        {'status': 'ok' if ok else 'unhealthy', 'checks': checks},
        status=200 if ok else 503,
    )
