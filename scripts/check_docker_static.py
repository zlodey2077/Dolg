"""Static validation for Docker/DevOps files without a Docker daemon.

This is intentionally lightweight: it catches path drift, missing services and
obvious production footguns before CI runs the real Docker build/smoke test.

Run:
    .venv\\Scripts\\python.exe scripts\\check_docker_static.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / 'deploy'
COMPOSE = DEPLOY / 'docker-compose.yml'
DOCKERFILE = DEPLOY / 'Dockerfile'
ENTRYPOINT = DEPLOY / 'entrypoint.sh'
NGINX_CONF = DEPLOY / 'nginx.conf'
PROMETHEUS = DEPLOY / 'prometheus.yml'
CI_WORKFLOW = ROOT / '.github' / 'workflows' / 'django.yml'
K8S = DEPLOY / 'k8s'


def section(title: str) -> None:
    print(f'\n=== {title} ===')


def check(passed: bool, label: str, detail: str = '') -> bool:
    mark = 'OK  ' if passed else 'WARN'
    line = f'  [{mark}] {label}'
    if detail:
        line += f' - {detail}'
    print(line)
    return passed


def read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def require_contains(text: str, checks: list[tuple[str, str]]) -> int:
    failed = 0
    for needle, desc in checks:
        if not check(needle in text, desc, f'pattern: {needle!r}'):
            failed += 1
    return failed


def main() -> int:
    failed = 0

    section('required files')
    for path in [COMPOSE, DOCKERFILE, ENTRYPOINT, NGINX_CONF, PROMETHEUS, CI_WORKFLOW, K8S]:
        if not check(path.exists(), str(path.relative_to(ROOT))):
            failed += 1

    section('docker-compose.yml')
    compose = read(COMPOSE)
    failed += require_contains(
        compose,
        [
            ('services:', 'top-level services key'),
            ('  db:', 'Postgres service'),
            ('  redis:', 'Redis service'),
            ('  web:', 'Django WSGI service'),
            ('  asgi:', 'Django ASGI service'),
            ('  worker:', 'Celery worker service'),
            ('  nginx:', 'nginx edge service'),
            ('  prometheus:', 'Prometheus service'),
            ('  grafana:', 'Grafana service'),
            ('redis://redis:6379/0', 'Redis URL for Channels'),
            ('CELERY_BROKER_URL', 'Celery broker configured'),
            ('METRICS_TOKEN', 'Prometheus token passed to Django'),
            ('condition: service_healthy', 'health-gated dependencies'),
            ('read_only: true', 'read-only app containers'),
            ('cap_drop:', 'capability drop configured'),
            ('no-new-privileges:true', 'no-new-privileges configured'),
            ('${HTTP_BIND:-0.0.0.0}:${HTTP_PORT:-80}:8080', 'nginx binds high internal port'),
            ('${GRAFANA_ADMIN_PASSWORD:?need GRAFANA_ADMIN_PASSWORD in .env}', 'Grafana password fail-fast'),
            ('${EMAIL_BACKEND:?need non-console EMAIL_BACKEND in .env}', 'email backend fail-fast'),
        ],
    )

    section('Dockerfile')
    dockerfile = read(DOCKERFILE)
    failed += require_contains(
        dockerfile,
        [
            ('FROM python:', 'base image declared'),
            ('USER ', 'non-root USER'),
            ('HEALTHCHECK', 'image healthcheck'),
            ('PYTHONDONTWRITEBYTECODE', 'bytecode disabled'),
            ('PYTHONUNBUFFERED', 'unbuffered logs'),
            ('PIP_NO_CACHE_DIR', 'pip cache disabled'),
            ('MPLCONFIGDIR=/tmp/matplotlib', 'matplotlib cache redirected'),
            ('XDG_CACHE_HOME=/tmp/.cache', 'XDG cache redirected'),
            ('COPY moderation/  moderation/', 'moderation app copied'),
            ('COPY deploy/entrypoint.sh ./', 'entrypoint copied from deploy path'),
            ('ENTRYPOINT ["./entrypoint.sh"]', 'entrypoint configured'),
            ('CMD ["gunicorn"', 'gunicorn default command'),
        ],
    )
    active_lines = [
        line for line in dockerfile.splitlines() if line.strip() and not line.strip().startswith('#')
    ]
    active_text = '\n'.join(active_lines)
    forbidden = [('COPY . .', 'unbounded COPY . .'), ('apt-get install -y\n', 'apt install without cleanup')]
    for needle, desc in forbidden:
        if needle in active_text:
            check(False, desc, f'pattern: {needle!r}')
            failed += 1
        else:
            check(True, desc, 'absent')

    section('entrypoint.sh')
    entrypoint = read(ENTRYPOINT)
    failed += require_contains(
        entrypoint,
        [
            ('set -e', 'fail-fast shell'),
            ('RUN_PROD_CHECKS', 'prod checks can be controlled per process'),
            ('RUN_MIGRATIONS', 'migration gate for non-web processes'),
            ('RUN_COLLECTSTATIC', 'collectstatic gate for non-web processes'),
            ('RUN_CREATE_SUPERUSER', 'superuser gate for non-web processes'),
            ('python manage.py check_prod_settings', 'production preflight runs'),
            ('python manage.py migrate --noinput', 'migrations available at boot'),
            ('python manage.py collectstatic', 'static collection available at boot'),
            ('os.environ', 'superuser values read through environment'),
        ],
    )

    section('nginx.conf')
    nginx = read(NGINX_CONF)
    failed += require_contains(
        nginx,
        [
            ('listen 8080;', 'high internal listen port'),
            ('upstream dolg_web', 'WSGI upstream'),
            ('upstream dolg_asgi', 'ASGI upstream'),
            ('location /ws/', 'websocket route'),
            ('proxy_set_header Upgrade', 'websocket upgrade header'),
            ('proxy_set_header X-Forwarded-Proto', 'forwarded proto header'),
            ('location = /metrics', 'metrics hidden on public edge'),
            ('return 403;', 'metrics denied on public edge'),
            ('alias /var/www/static/', 'static volume served by nginx'),
            ('alias /var/www/media/', 'media volume served by nginx'),
        ],
    )

    section('prometheus.yml')
    prometheus = read(PROMETHEUS)
    failed += require_contains(
        prometheus,
        [
            ("metrics_path: '/metrics'", 'Django metrics path without slash'),
            ('authorization:', 'Prometheus authenticates to protected /metrics'),
            ('local-metrics-token-change-me', 'local metrics token is explicit'),
            ("targets: ['web:8000']", 'Prometheus scrapes internal web service'),
        ],
    )

    section('CI workflow')
    ci = read(CI_WORKFLOW)
    failed += require_contains(
        ci,
        [
            ('container:', 'container job present'),
            ('scripts/check_k8s_static.py', 'Kubernetes static validation in CI'),
            ('docker compose -f deploy/docker-compose.yml config', 'compose config validation'),
            ('docker build -f deploy/Dockerfile -t dolg-ci:latest .', 'Docker build validation'),
            ('aquasecurity/trivy-action', 'Trivy image scan'),
            (
                'docker compose -f deploy/docker-compose.yml up -d --build db redis web',
                'container smoke start',
            ),
            ('moderation Dolg_PR', 'moderation included in lint/test paths'),
        ],
    )

    section('Kubernetes base')
    k8s_files = [
        'kustomization.yaml',
        'namespace.yaml',
        'storage.yaml',
        'postgres.yaml',
        'redis.yaml',
        'django.yaml',
        'nginx.yaml',
        'monitoring.yaml',
    ]
    for rel in k8s_files:
        path = K8S / rel
        if not check(path.exists(), f'deploy/k8s/{rel}'):
            failed += 1
    if K8S.exists():
        kustomization = read(K8S / 'kustomization.yaml')
        failed += require_contains(
            kustomization,
            [
                ('secretGenerator:', 'local Kubernetes secret generator'),
                ('configMapGenerator:', 'local Kubernetes config generator'),
                ('dolg-secret', 'Django secret object'),
                ('dolg-config', 'Django config object'),
            ],
        )

    print(f'\n{"=" * 50}')
    if failed == 0:
        print('ALL CHECKS PASSED - Docker/DevOps files passed static validation.')
        print('Runtime validation still requires: docker compose up -d --build')
        return 0

    print(f'FAILED {failed} checks - see WARN lines above.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
