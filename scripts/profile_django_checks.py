r"""Profile Django system checks by registered callable.

Usage:
    .venv\Scripts\python.exe scripts/profile_django_checks.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Dolg_PR.settings')
os.environ.setdefault('DOLG_SKIP_ASGI', '1')

import django


def main() -> int:
    t0 = time.perf_counter()
    django.setup()
    print(f'django.setup: {time.perf_counter() - t0:.3f}s', flush=True)

    from django.core.checks.registry import registry

    rows: list[tuple[float, str, int]] = []
    original = list(registry.registered_checks)
    registry.registered_checks = set()

    for check in original:
        registry.registered_checks.add(_timed_check(check, rows))

    t0 = time.perf_counter()
    messages = registry.run_checks(app_configs=None, tags=None, include_deployment_checks=False, databases=None)
    print(f'run_checks: {time.perf_counter() - t0:.3f}s; messages={len(messages)}', flush=True)
    print('top checks:')
    for dt, name, count in sorted(rows, reverse=True)[:40]:
        print(f'{dt:8.3f}s  {name}  messages={count}')
    return 0


def _timed_check(check, rows):
    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        result = check(*args, **kwargs)
        dt = time.perf_counter() - t0
        name = f'{check.__module__}.{getattr(check, "__name__", repr(check))}'
        rows.append((dt, name, len(result or [])))
        print(f'CHECK {dt:8.3f}s {name}', flush=True)
        return result

    wrapper.tags = getattr(check, 'tags', set())
    wrapper.deployment = getattr(check, 'deployment', False)
    return wrapper


if __name__ == '__main__':
    raise SystemExit(main())
