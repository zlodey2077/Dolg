"""Статическая валидация Docker-инфры без рантайма.

Запускается локально без Docker daemon — даёт уверенность, что compose,
Dockerfile и entrypoint синтаксически и логически валидны. Не заменяет
реальный `docker compose up`, но ловит ~80% типичных ошибок.

Запуск:
    .venv\\Scripts\\python.exe scripts\\check_docker_static.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / 'docker-compose.yml'
DOCKERFILE = ROOT / 'Dockerfile'
ENTRYPOINT = ROOT / 'entrypoint.sh'
NGINX_CONF = ROOT / 'nginx.conf'


def section(title):
    print(f'\n=== {title} ===')


def check(passed, label, detail=''):
    mark = 'OK  ' if passed else 'WARN'
    line = f'  [{mark}] {label}'
    if detail:
        line += f' — {detail}'
    print(line)
    return passed


def main():
    failed = 0
    section('docker-compose.yml')
    txt = COMPOSE.read_text(encoding='utf-8')
    structure = [
        ('services:',         'top-level services key'),
        ('  db:',             'service db'),
        ('  web:',            'service web'),
        ('  nginx:',          'service nginx'),
        ('volumes:',          'top-level volumes key'),
        ('depends_on:',       'service dependencies'),
        ('healthcheck:',      'db healthcheck (pg_isready)'),
        ('postgres:16',       'pinned postgres major'),
        ('nginx:1.27',        'pinned nginx version'),
        ('SECRET_KEY',        'SECRET_KEY env var'),
        ('DATABASE_URL',      'DATABASE_URL passes from compose to web'),
        ('?need SECRET_KEY',  'обязательный fail-fast если SECRET_KEY пуст'),
        ('condition: service_healthy', 'web ждёт healthy db'),
    ]
    for needle, desc in structure:
        if not check(needle in txt, desc, f'pattern: {needle!r}'):
            failed += 1

    section('Dockerfile best-practice')
    df = DOCKERFILE.read_text(encoding='utf-8')
    df_positive = [
        ('FROM python:',            'base image declared'),
        ('USER ',                   'non-root USER'),
        ('HEALTHCHECK',             'HEALTHCHECK directive'),
        ('PYTHONUNBUFFERED',        'unbuffered stdout'),
        ('PIP_NO_CACHE_DIR',        'pip without cache layer'),
        ('ENTRYPOINT',              'ENTRYPOINT'),
        ('CMD ',                    'CMD as default args'),
        ('--no-install-recommends', 'apt slim install'),
        ('fonts-dejavu',            'cyrillic fonts for PDF'),
    ]
    for needle, desc in df_positive:
        if not check(needle in df, desc, f'pattern: {needle!r}'):
            failed += 1
    # Антипаттерны: ищем только в активных директивах, не в комментариях
    # (строки, начинающиеся с #).
    active_lines = [
        ln for ln in df.splitlines()
        if ln.strip() and not ln.strip().startswith('#')
    ]
    active_text = '\n'.join(active_lines)
    df_negative = [
        ('COPY . .',                'НЕ должно быть бесконтрольного COPY . .'),
        ('apt-get install -y\n',    'apt без очистки кеша'),
    ]
    for needle, desc in df_negative:
        if needle in active_text:
            check(False, desc + ' (найдено!)', f'pattern: {needle!r}')
            failed += 1
        else:
            check(True, desc, 'отсутствует')

    section('entrypoint.sh (после audit round-2)')
    ep = ENTRYPOINT.read_text(encoding='utf-8')
    # Раньше тут был shell-injection через '$DJANGO_SUPERUSER_USERNAME'
    inj = re.search(r"u\s*=\s*['\"]\$", ep)
    if inj:
        check(False, 'NO shell-injection в Python-исходник', 'найдена интерполяция $VAR в литерал')
        failed += 1
    else:
        check(True, 'NO shell-injection в Python-исходник', 'литерал использует os.environ')
    if not check('os.environ' in ep, 'os.environ для чтения env-vars'):
        failed += 1
    if not check('set -e' in ep, 'set -e (fail-fast)'):
        failed += 1
    if not check('COLLECTSTATIC_CLEAR' in ep, 'opt-in --clear для collectstatic'):
        failed += 1
    if not check('migrate --noinput' in ep, 'migrate выполняется при старте'):
        failed += 1

    section('nginx.conf')
    nx = NGINX_CONF.read_text(encoding='utf-8')
    nginx_checks = [
        ('upstream dolg_web', 'upstream backend'),
        ('proxy_set_header X-Forwarded-Proto', 'X-Forwarded-Proto (для SECURE_PROXY_SSL_HEADER в Django)'),
        ('proxy_set_header X-Forwarded-For',   'X-Forwarded-For (real-IP)'),
        ('proxy_set_header Host',              'X-Forwarded-Host (для USE_X_FORWARDED_HOST)'),
        ('alias /var/www/static/',             'static volume mount'),
        ('alias /var/www/media/',              'media volume mount'),
        ('add_header X-Content-Type-Options',  'security header'),
        ('add_header X-Frame-Options',         'clickjacking защита'),
    ]
    for needle, desc in nginx_checks:
        if not check(needle in nx, desc, f'pattern: {needle!r}'):
            failed += 1

    print(f'\n{"=" * 50}')
    if failed == 0:
        print('ALL CHECKS PASSED — Docker-инфра прошла статическую валидацию.')
        print('Реальный запуск: docker compose up -d --build')
        sys.exit(0)
    else:
        print(f'FAILED {failed} checks — см. WARN выше.')
        sys.exit(1)


if __name__ == '__main__':
    main()
