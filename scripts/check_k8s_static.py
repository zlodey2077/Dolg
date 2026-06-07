"""Static validation for deploy/k8s without requiring a live cluster."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
K8S = ROOT / 'deploy' / 'k8s'

REQUIRED_FILES = [
    'kustomization.yaml',
    'namespace.yaml',
    'storage.yaml',
    'postgres.yaml',
    'redis.yaml',
    'django.yaml',
    'nginx.yaml',
    'monitoring.yaml',
    'networkpolicy.yaml',
    'README.md',
]

REQUIRED_KINDS = {
    ('Namespace', 'dolg'),
    ('PersistentVolumeClaim', 'postgres-data'),
    ('PersistentVolumeClaim', 'redis-data'),
    ('PersistentVolumeClaim', 'django-media'),
    ('PersistentVolumeClaim', 'django-staticfiles'),
    ('Service', 'postgres'),
    ('Service', 'redis'),
    ('Service', 'dolg-web'),
    ('Service', 'dolg-asgi'),
    ('Service', 'dolg-nginx'),
    ('Service', 'prometheus'),
    ('Service', 'grafana'),
    ('Deployment', 'postgres'),
    ('Deployment', 'redis'),
    ('Deployment', 'dolg-web'),
    ('Deployment', 'dolg-asgi'),
    ('Deployment', 'dolg-worker'),
    ('Deployment', 'dolg-nginx'),
    ('Deployment', 'prometheus'),
    ('Deployment', 'grafana'),
    ('Job', 'dolg-migrate'),
    ('ConfigMap', 'nginx-config'),
    ('ConfigMap', 'prometheus-config'),
    ('NetworkPolicy', 'default-deny'),
    ('NetworkPolicy', 'allow-dns-egress'),
    ('NetworkPolicy', 'allow-edge-ingress'),
    ('NetworkPolicy', 'allow-edge-to-django'),
    ('NetworkPolicy', 'allow-edge-to-asgi'),
    ('NetworkPolicy', 'allow-django-to-stateful'),
    ('NetworkPolicy', 'allow-stateful-from-django'),
    ('NetworkPolicy', 'allow-edge-egress'),
    ('NetworkPolicy', 'allow-prometheus-scrape'),
    ('NetworkPolicy', 'allow-grafana-to-prometheus'),
}


def check(passed: bool, label: str, detail: str = '') -> bool:
    mark = 'OK  ' if passed else 'WARN'
    line = f'  [{mark}] {label}'
    if detail:
        line += f' - {detail}'
    print(line)
    return passed


def load_yaml(path: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for item in yaml.safe_load_all(path.read_text(encoding='utf-8')):
        if item:
            docs.append(item)
    return docs


def iter_containers(doc: dict[str, Any]) -> list[dict[str, Any]]:
    template = doc.get('spec', {}).get('template', {})
    spec = template.get('spec', {})
    return list(spec.get('containers', [])) + list(spec.get('initContainers', []))


def pod_spec(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get('spec', {}).get('template', {}).get('spec', {})


def main() -> int:
    failed = 0

    print('=== required k8s files ===')
    for rel in REQUIRED_FILES:
        path = K8S / rel
        if not check(path.exists(), rel):
            failed += 1

    docs: list[dict[str, Any]] = []
    for path in sorted(K8S.glob('*.yaml')):
        try:
            docs.extend(load_yaml(path))
        except yaml.YAMLError as exc:
            check(False, f'valid YAML: {path.relative_to(ROOT)}', str(exc))
            failed += 1

    print('\n=== required objects ===')
    present = {(doc.get('kind'), doc.get('metadata', {}).get('name')) for doc in docs}
    for kind_name in sorted(REQUIRED_KINDS):
        if not check(kind_name in present, f'{kind_name[0]}/{kind_name[1]}'):
            failed += 1

    print('\n=== image hygiene ===')
    for doc in docs:
        name = doc.get('metadata', {}).get('name', '<unknown>')
        for container in iter_containers(doc):
            image = container.get('image', '')
            if not image:
                continue
            if not check(':latest' not in image, f'{name}/{container.get("name")} avoids :latest', image):
                failed += 1
            if image.startswith('dolg:'):
                if not check(
                    container.get('imagePullPolicy') == 'IfNotPresent',
                    f'{name}/{container.get("name")} keeps local image usable',
                    image,
                ):
                    failed += 1

    print('\n=== pod security ===')
    namespace = next(
        (
            doc
            for doc in docs
            if doc.get('kind') == 'Namespace' and doc.get('metadata', {}).get('name') == 'dolg'
        ),
        {},
    )
    labels = namespace.get('metadata', {}).get('labels', {})
    if not check(
        labels.get('pod-security.kubernetes.io/enforce') == 'baseline', 'namespace enforces baseline PSS'
    ):
        failed += 1
    if not check(
        labels.get('pod-security.kubernetes.io/warn') == 'restricted', 'namespace warns on restricted PSS'
    ):
        failed += 1
    if not check(
        labels.get('pod-security.kubernetes.io/audit') == 'restricted', 'namespace audits restricted PSS'
    ):
        failed += 1

    workload_kinds = {'Deployment', 'Job'}
    for doc in docs:
        if doc.get('kind') not in workload_kinds:
            continue
        name = doc.get('metadata', {}).get('name', '<unknown>')
        spec = pod_spec(doc)
        seccomp_type = spec.get('securityContext', {}).get('seccompProfile', {}).get('type')
        if not check(seccomp_type == 'RuntimeDefault', f'{name} uses RuntimeDefault seccomp'):
            failed += 1
        for container in iter_containers(doc):
            security = container.get('securityContext', {})
            cname = container.get('name')
            if not check(
                security.get('allowPrivilegeEscalation') is False,
                f'{name}/{cname} forbids privilege escalation',
            ):
                failed += 1
            drops = set(security.get('capabilities', {}).get('drop', []))
            if not check('ALL' in drops, f'{name}/{cname} drops all Linux capabilities'):
                failed += 1

    print('\n=== django workload checks ===')
    django_names = {'dolg-web', 'dolg-asgi', 'dolg-worker', 'dolg-migrate'}
    for doc in docs:
        name = doc.get('metadata', {}).get('name')
        if name not in django_names:
            continue
        containers = iter_containers(doc)
        for container in containers:
            env_from = container.get('envFrom', [])
            has_config = any('configMapRef' in item for item in env_from)
            has_secret = any('secretRef' in item for item in env_from)
            if not check(has_config, f'{name}/{container.get("name")} uses dolg-config'):
                failed += 1
            if not check(has_secret, f'{name}/{container.get("name")} uses dolg-secret'):
                failed += 1

    print('\n=== kustomization references ===')
    kustomization = yaml.safe_load((K8S / 'kustomization.yaml').read_text(encoding='utf-8'))
    resources = set(kustomization.get('resources', []))
    for rel in REQUIRED_FILES:
        if rel in {'kustomization.yaml', 'README.md'}:
            continue
        if not check(rel in resources, f'kustomization includes {rel}'):
            failed += 1
    generators = {item.get('name') for item in kustomization.get('configMapGenerator', [])}
    secrets = {item.get('name') for item in kustomization.get('secretGenerator', [])}
    if not check('dolg-config' in generators, 'kustomization generates dolg-config'):
        failed += 1
    if not check('dolg-secret' in secrets, 'kustomization generates dolg-secret'):
        failed += 1

    print(f'\n{"=" * 50}')
    if failed == 0:
        print('ALL CHECKS PASSED - Kubernetes manifests passed static validation.')
        print('Runtime validation still requires: kubectl apply -k deploy/k8s')
        return 0
    print(f'FAILED {failed} checks - see WARN lines above.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
