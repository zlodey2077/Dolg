"""Operational metrics for staff dashboards and future Prometheus gauges.

This module intentionally keeps imports lazy and defensive: an operations page
must degrade to "unknown" instead of failing the whole admin area.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.db.models import Count, Q, Sum
from django.utils import timezone

OPS_SNAPSHOT_CACHE_KEY = 'dolg.ops.snapshot.v1'
OPS_ADMIN_SNAPSHOT_CACHE_KEY = 'dolg.ops.admin_snapshot.v1'
OPS_SNAPSHOT_TTL = 20
STALE_JOB_SECONDS = 120


def _now():
    return timezone.now()


def _json_value(value: Any):
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value


def _mb(value: int | float | None) -> float:
    try:
        return round(float(value or 0) / 1024 / 1024, 1)
    except (TypeError, ValueError):
        return 0.0


def _safe_count(qs) -> int:
    try:
        return int(qs.count())
    except Exception:
        return 0


def _safe_sum(qs, field: str) -> float:
    try:
        value = qs.aggregate(total=Sum(field)).get('total') or 0
        return float(value)
    except Exception:
        return 0.0


def _dir_size(path: Path, *, max_files: int = 5000) -> dict[str, Any]:
    result = {
        'path': str(path),
        'exists': path.exists(),
        'bytes': 0,
        'files': 0,
        'truncated': False,
    }
    if not path.exists():
        return result
    try:
        for item in path.rglob('*'):
            if result['files'] >= max_files:
                result['truncated'] = True
                break
            try:
                if item.is_file():
                    result['files'] += 1
                    result['bytes'] += item.stat().st_size
            except OSError:
                continue
    except OSError as exc:
        result['error'] = str(exc)
    return result


def _disk_usage(path: Path) -> dict[str, Any]:
    target = path if path.exists() else path.parent
    try:
        usage = __import__('shutil').disk_usage(target)
        return {
            'path': str(path),
            'total_bytes': usage.total,
            'used_bytes': usage.used,
            'free_bytes': usage.free,
            'used_ratio': round(usage.used / usage.total, 4) if usage.total else 0,
            'used_percent': round((usage.used / usage.total) * 100, 1) if usage.total else 0,
        }
    except Exception as exc:
        return {'path': str(path), 'error': str(exc), 'used_ratio': None}


def _db_latency_ms() -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        return {'ok': True, 'latency_ms': round((time.perf_counter() - started) * 1000, 2)}
    except Exception as exc:
        return {'ok': False, 'latency_ms': None, 'error': str(exc)}


def _cache_latency_ms() -> dict[str, Any]:
    started = time.perf_counter()
    key = 'dolg.ops.cache.smoke'
    try:
        cache.set(key, {'t': time.time()}, timeout=10)
        value = cache.get(key)
        cache.delete(key)
        return {
            'ok': bool(value),
            'latency_ms': round((time.perf_counter() - started) * 1000, 2),
            'backend': settings.CACHES.get('default', {}).get('BACKEND', ''),
        }
    except Exception as exc:
        return {'ok': False, 'latency_ms': None, 'error': str(exc)}


def collect_runtime_metrics(*, include_storage: bool = True) -> dict[str, Any]:
    base_dir = Path(settings.BASE_DIR)
    media_root = Path(getattr(settings, 'MEDIA_ROOT', base_dir / 'media'))
    static_root = Path(getattr(settings, 'STATIC_ROOT', base_dir / 'staticfiles'))
    dataset_root = base_dir / 'Dolg_APP' / 'ml' / 'dataset'
    search_root = media_root / 'search'

    process = {
        'status': 'unknown',
        'psutil_available': False,
    }
    try:
        import psutil  # type: ignore

        proc = psutil.Process(os.getpid())
        memory = proc.memory_info()
        full_memory = None
        try:
            full_memory = proc.memory_full_info()
        except Exception:
            pass
        started_at = datetime.fromtimestamp(proc.create_time(), tz=timezone.get_current_timezone())
        process = {
            'status': 'ok',
            'psutil_available': True,
            'pid': proc.pid,
            'rss_bytes': int(memory.rss),
            'vms_bytes': int(memory.vms),
            'uss_bytes': int(getattr(full_memory, 'uss', 0) or 0),
            'rss_mb': _mb(memory.rss),
            'vms_mb': _mb(memory.vms),
            'uss_mb': _mb(getattr(full_memory, 'uss', 0) or 0),
            'memory_percent': round(float(proc.memory_percent()), 2),
            'cpu_percent': round(float(proc.cpu_percent(interval=None)), 2),
            'threads': int(proc.num_threads()),
            'started_at': started_at.isoformat(),
            'uptime_seconds': max(0, int((_now() - started_at).total_seconds())),
        }
        try:
            process['open_files'] = len(proc.open_files())
        except Exception:
            process['open_files'] = None
        try:
            process['connections'] = len(proc.net_connections(kind='inet'))
        except Exception:
            process['connections'] = None
    except Exception as exc:
        process['error'] = str(exc)

    if include_storage:
        datasets = _dir_size(dataset_root, max_files=10000)
        try:
            datasets['incomplete_files'] = (
                len(list(dataset_root.rglob('*.incomplete'))) if dataset_root.exists() else 0
            )
        except OSError:
            datasets['incomplete_files'] = None
        media_storage = _dir_size(media_root, max_files=10000)
        search_storage = {
            **_dir_size(search_root, max_files=5000),
            'stale': (search_root / '.stale').exists(),
        }
    else:
        datasets = {
            'path': str(dataset_root),
            'exists': dataset_root.exists(),
            'bytes': None,
            'files': None,
            'truncated': True,
            'incomplete_files': None,
        }
        media_storage = {
            'path': str(media_root),
            'exists': media_root.exists(),
            'bytes': None,
            'files': None,
            'truncated': True,
        }
        search_storage = {
            'path': str(search_root),
            'exists': search_root.exists(),
            'bytes': None,
            'files': None,
            'truncated': True,
            'stale': (search_root / '.stale').exists(),
        }

    return {
        'process': process,
        'db': _db_latency_ms(),
        'cache': _cache_latency_ms(),
        'disk': {
            'base': _disk_usage(base_dir),
            'media': _disk_usage(media_root),
            'staticfiles': _disk_usage(static_root),
            'datasets': _disk_usage(dataset_root),
        },
        'storage': {
            'media': media_storage,
            'datasets': datasets,
            'search_index': search_storage,
        },
    }


def collect_catalog_metrics() -> dict[str, Any]:
    try:
        from shop.models import Category, Product
    except Exception as exc:
        return {'available': False, 'error': str(exc)}

    reb_slugs = getattr(Category, 'REB_SLUGS', [])
    products = Product.objects.all()
    reb_products = products.filter(category__slug__in=reb_slugs)
    lifecycle = {
        item['lifecycle_status'] or 'unknown': item['total']
        for item in products.values('lifecycle_status').annotate(total=Count('id')).order_by()
    }
    return {
        'available': True,
        'products': _safe_count(products),
        'categories': _safe_count(Category.objects.all()),
        'reb_products': _safe_count(reb_products),
        'missing_datasheet': _safe_count(reb_products.filter(datasheet_url='')),
        'datasheet_extracted': _safe_count(products.filter(parameters__has_key='datasheet_extracted')),
        'missing_image': _safe_count(products.filter(Q(image__isnull=True) | Q(image=''))),
        'needs_data_review': _safe_count(products.filter(parameters__needs_moderation=True)),
        'low_stock': _safe_count(products.filter(stock__gt=0, stock__lte=3)),
        'out_of_stock': _safe_count(products.filter(stock__lte=0)),
        'lifecycle': lifecycle,
    }


def collect_business_metrics(period_days: int = 7) -> dict[str, Any]:
    cutoff = _now() - timezone.timedelta(days=period_days)
    User = get_user_model()
    try:
        from orders.models import Order, OrderStatus, PaymentTransaction
        from shop.models import CartItem
    except Exception as exc:
        return {'available': False, 'error': str(exc), 'period_days': period_days}

    try:
        from Dolg_APP.models import DailyUsage, Organization, Subscription
    except Exception as exc:
        return {'available': False, 'error': str(exc), 'period_days': period_days}

    orders = Order.objects.all()
    recent_orders = orders.filter(created_at__gte=cutoff)
    usage = DailyUsage.objects.filter(date__gte=cutoff.date())
    ai_requests = usage.aggregate(total=Sum('ai_requests_count')).get('total') or 0
    simulations = usage.aggregate(total=Sum('simulations_count')).get('total') or 0

    return {
        'available': True,
        'period_days': period_days,
        'users_total': _safe_count(User.objects.all()),
        'users_staff': _safe_count(User.objects.filter(is_staff=True)),
        'users_new': _safe_count(User.objects.filter(date_joined__gte=cutoff)),
        'active_usage_users': usage.values('user_id').distinct().count(),
        'daily_ai_requests': int(ai_requests),
        'daily_simulations': int(simulations),
        'cart_items': _safe_count(CartItem.objects.all()),
        'orders_total': _safe_count(orders),
        'orders_recent': _safe_count(recent_orders),
        'orders_paid': _safe_count(orders.filter(is_paid=True)),
        'orders_pending': _safe_count(orders.filter(status__name=OrderStatus.PENDING)),
        'orders_cancelled': _safe_count(orders.filter(status__name=OrderStatus.CANCELLED)),
        'revenue_paid': _safe_sum(orders.filter(is_paid=True), 'total_amount'),
        'payments_total': _safe_count(PaymentTransaction.objects.all()),
        'payments_failed': _safe_count(PaymentTransaction.objects.filter(status='failed')),
        'subscriptions_total': _safe_count(Subscription.objects.all()),
        'subscriptions_pro_active': sum(1 for sub in Subscription.objects.all() if sub.is_pro_active()),
        'organizations': _safe_count(Organization.objects.all()),
    }


def collect_project_metrics() -> dict[str, Any]:
    try:
        from Dolg_APP.models import (
            ProjectEvent,
            ProjectMeasurement,
            ProjectReview,
            SchematicProject,
            SimulationRun,
        )
    except Exception as exc:
        return {'available': False, 'error': str(exc)}

    reviews = ProjectReview.objects.all()
    status_counts = {
        item['status'] or 'unknown': item['total']
        for item in reviews.values('status').annotate(total=Count('id')).order_by()
    }
    critical_findings = 0
    warning_findings = 0
    for review in reviews.only('errors', 'warnings', 'sections'):
        findings = []
        if isinstance(review.errors, list):
            findings.extend(review.errors)
        if isinstance(review.warnings, list):
            findings.extend(review.warnings)
        sections = review.sections if isinstance(review.sections, dict) else {}
        expert_findings = sections.get('expert_findings') or sections.get('findings') or []
        if isinstance(expert_findings, list):
            findings.extend(expert_findings)
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            severity = str(finding.get('severity') or '').lower()
            critical_findings += int(severity in ('critical', 'error'))
            warning_findings += int(severity == 'warning')

    return {
        'available': True,
        'projects_total': SchematicProject.all_objects.count(),
        'projects_active': SchematicProject.objects.count(),
        'projects_demo': SchematicProject.all_objects.filter(is_demo=True).count(),
        'projects_public': SchematicProject.all_objects.filter(visibility='public').count(),
        'projects_pending_review': SchematicProject.all_objects.filter(
            approval_state='pending_review'
        ).count(),
        'events': ProjectEvent.objects.count(),
        'reviews': reviews.count(),
        'review_status': status_counts,
        'review_critical_findings': critical_findings,
        'review_warning_findings': warning_findings,
        'measurements': ProjectMeasurement.objects.count(),
        'simulation_runs': SimulationRun.objects.count(),
    }


def collect_ai_ml_metrics() -> dict[str, Any]:
    # «Полный» вариант со сводкой/валидацией датасета (тяжёлый запрос).
    # Сейчас делегирует в _fast — полная версия ждёт пост-defense рефакторинга.
    return collect_ai_ml_metrics_fast()


def collect_ai_ml_metrics_fast() -> dict[str, Any]:
    """Cheap AI/ML counters for Django admin index.

    The full variant runs dataset summary/validation, which is useful on the
    dedicated ops page but too slow for the admin landing page.
    """
    try:
        from Dolg_APP.models import AITrainingExample, EngineeringArtifact, MLJob
    except Exception as exc:
        return {'available': False, 'error': str(exc)}

    try:
        from Dolg_APP import ai_assistant

        ai_runtime = ai_assistant.runtime_status(timeout=0.8)
    except Exception as exc:
        ai_runtime = {
            'backend': 'unknown',
            'live_enabled': False,
            'error': str(exc),
        }

    now = _now()
    active_jobs = MLJob.objects.filter(status__in=['queued', 'running'])
    stale_jobs = active_jobs.filter(heartbeat_at__lt=now - timezone.timedelta(seconds=STALE_JOB_SECONDS))
    return {
        'available': True,
        'runtime': ai_runtime,
        'examples': AITrainingExample.objects.count(),
        'validated': AITrainingExample.objects.filter(is_validated=True).count(),
        'graph_ready': AITrainingExample.objects.filter(features__graph_training_ready=True).count(),
        'validation': {
            'ok': True,
            'errors_count': 0,
            'warnings_count': 0,
            'skipped': True,
        },
        'artifacts': EngineeringArtifact.objects.count(),
        'artifact_errors': EngineeringArtifact.objects.filter(status='error').count(),
        'ml_jobs': MLJob.objects.count(),
        'ml_jobs_active': active_jobs.count(),
        'ml_jobs_stale': stale_jobs.count(),
        'ml_status': {
            item['status']: item['total']
            for item in MLJob.objects.values('status').annotate(total=Count('id')).order_by()
        },
        'ml_type': {
            item['job_type']: item['total']
            for item in MLJob.objects.values('job_type').annotate(total=Count('id')).order_by()
        },
    }


def collect_moderation_metrics() -> dict[str, Any]:
    try:
        from moderation.models import ModerationCase, ModerationReport, UserRestriction
    except Exception as exc:
        return {'available': False, 'error': str(exc)}

    now = _now()
    active_restrictions = UserRestriction.objects.filter(lifted_at__isnull=True, starts_at__lte=now).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    )
    return {
        'available': True,
        'cases_open': ModerationCase.objects.filter(status__in=['open', 'in_review']).count(),
        'cases_total': ModerationCase.objects.count(),
        'reports_total': ModerationReport.objects.count(),
        'reports_pending': ModerationReport.objects.filter(status='pending').count(),
        'restrictions_active': active_restrictions.count(),
    }


def collect_security_metrics(period_days: int = 7) -> dict[str, Any]:
    cutoff = _now() - timezone.timedelta(days=period_days)
    User = get_user_model()
    try:
        from Dolg_APP.models import AuditLog, OrganizationApiToken
    except Exception as exc:
        return {'available': False, 'error': str(exc), 'period_days': period_days}

    return {
        'available': True,
        'period_days': period_days,
        'staff_users': User.objects.filter(is_staff=True).count(),
        'superusers': User.objects.filter(is_superuser=True).count(),
        'audit_events_recent': AuditLog.objects.filter(timestamp__gte=cutoff).count(),
        'api_tokens_total': OrganizationApiToken.objects.count(),
        'api_tokens_active': OrganizationApiToken.objects.filter(revoked_at__isnull=True).count(),
        'api_tokens_revoked': OrganizationApiToken.objects.exclude(revoked_at__isnull=True).count(),
    }


def classify_ops_health(snapshot: dict[str, Any]) -> dict[str, Any]:
    alerts: list[dict[str, Any]] = []

    runtime = snapshot.get('runtime') or {}
    process = runtime.get('process') or {}
    if process.get('status') != 'ok':
        alerts.append(
            {
                'severity': 'warning',
                'metric': 'runtime.process',
                'message': 'Process metrics unavailable',
                'recommendation': 'Install psutil or inspect server logs.',
            }
        )
    if (process.get('rss_bytes') or 0) > 900 * 1024 * 1024:
        alerts.append(
            {
                'severity': 'critical',
                'metric': 'runtime.memory_rss',
                'message': 'Django process memory is high',
                'recommendation': 'Check ML imports/training and large dataset reads.',
            }
        )
    elif (process.get('rss_bytes') or 0) > 600 * 1024 * 1024:
        alerts.append(
            {
                'severity': 'warning',
                'metric': 'runtime.memory_rss',
                'message': 'Django process memory is elevated',
                'recommendation': 'Watch ML/admin pages and dataset cache size.',
            }
        )

    if not (runtime.get('db') or {}).get('ok', False):
        alerts.append(
            {
                'severity': 'critical',
                'metric': 'runtime.db',
                'message': 'Database smoke check failed',
                'recommendation': 'Check DATABASE_URL, Postgres container and migrations.',
            }
        )
    if not (runtime.get('cache') or {}).get('ok', False):
        alerts.append(
            {
                'severity': 'warning',
                'metric': 'runtime.cache',
                'message': 'Cache smoke check failed',
                'recommendation': 'Check Django CACHES backend.',
            }
        )

    for name, disk in (runtime.get('disk') or {}).items():
        ratio = disk.get('used_ratio')
        if ratio is not None and ratio >= 0.95:
            alerts.append(
                {
                    'severity': 'critical',
                    'metric': f'disk.{name}',
                    'message': f'Disk usage is {round(ratio * 100, 1)}%',
                    'recommendation': 'Clean old datasets, media or logs.',
                }
            )
        elif ratio is not None and ratio >= 0.85:
            alerts.append(
                {
                    'severity': 'warning',
                    'metric': f'disk.{name}',
                    'message': f'Disk usage is {round(ratio * 100, 1)}%',
                    'recommendation': 'Plan cleanup before imports/training.',
                }
            )

    ai_ml = snapshot.get('ai_ml') or {}
    if (ai_ml.get('ml_jobs_stale') or 0) > 0:
        alerts.append(
            {
                'severity': 'critical',
                'metric': 'ml.jobs_stale',
                'message': f'{ai_ml.get("ml_jobs_stale")} ML jobs have stale heartbeat',
                'recommendation': 'Open MLJob admin and cancel/retry stale jobs.',
            }
        )
    validation = ai_ml.get('validation') or {}
    if (validation.get('errors_count') or 0) > 0:
        alerts.append(
            {
                'severity': 'warning',
                'metric': 'ai.validation_errors',
                'message': f'{validation.get("errors_count")} AI dataset validation errors',
                'recommendation': 'Open dataset quality and fix/exclude bad examples.',
            }
        )
    ai_runtime = ai_ml.get('runtime') or {}
    if ai_runtime.get('backend') == 'ollama':
        ollama = ai_runtime.get('ollama') or {}
        if not ollama.get('available'):
            alerts.append(
                {
                    'severity': 'warning',
                    'metric': 'ai.ollama',
                    'message': 'Ollama runtime is configured but unavailable',
                    'recommendation': 'Start Ollama and check OLLAMA_BASE_URL.',
                }
            )
        elif ollama.get('model') and not ollama.get('model_installed'):
            alerts.append(
                {
                    'severity': 'warning',
                    'metric': 'ai.ollama_model',
                    'message': f'Ollama model {ollama.get("model")} is not installed',
                    'recommendation': f'Run: ollama pull {ollama.get("model")}',
                }
            )

    moderation = snapshot.get('moderation') or {}
    if (moderation.get('cases_open') or 0) > 10:
        alerts.append(
            {
                'severity': 'warning',
                'metric': 'moderation.cases_open',
                'message': 'Moderation queue is growing',
                'recommendation': 'Assign a moderator and close stale cases.',
            }
        )

    severity_rank = {'critical': 2, 'warning': 1}
    max_severity = max((severity_rank.get(item['severity'], 0) for item in alerts), default=0)
    status = 'critical' if max_severity >= 2 else 'warning' if max_severity == 1 else 'ok'
    return {'status': status, 'alerts': alerts}


def collect_ops_snapshot(
    *,
    period_days: int = 7,
    use_cache: bool = True,
    include_storage: bool = True,
) -> dict[str, Any]:
    cache_key = f'{OPS_SNAPSHOT_CACHE_KEY}.{period_days}.{int(include_storage)}'
    if use_cache:
        cached = cache.get(cache_key)
        if cached:
            return cached

    snapshot = {
        'generated_at': _now().isoformat(),
        'period_days': period_days,
        'runtime': collect_runtime_metrics(include_storage=include_storage),
        'catalog': collect_catalog_metrics(),
        'business': collect_business_metrics(period_days=period_days),
        'projects': collect_project_metrics(),
        'ai_ml': collect_ai_ml_metrics(),
        'moderation': collect_moderation_metrics(),
        'security': collect_security_metrics(period_days=period_days),
    }
    snapshot['health'] = classify_ops_health(snapshot)
    cache.set(cache_key, snapshot, timeout=OPS_SNAPSHOT_TTL)
    return snapshot


def collect_admin_index_snapshot(*, use_cache: bool = True) -> dict[str, Any]:
    if use_cache:
        cached = cache.get(OPS_ADMIN_SNAPSHOT_CACHE_KEY)
        if cached:
            return cached

    snapshot = {
        'generated_at': _now().isoformat(),
        'period_days': 7,
        'runtime': collect_runtime_metrics(include_storage=False),
        'catalog': collect_catalog_metrics(),
        'business': collect_business_metrics(period_days=7),
        'projects': collect_project_metrics(),
        'ai_ml': collect_ai_ml_metrics_fast(),
        'moderation': collect_moderation_metrics(),
        'security': collect_security_metrics(period_days=7),
    }
    snapshot['health'] = classify_ops_health(snapshot)
    cache.set(OPS_ADMIN_SNAPSHOT_CACHE_KEY, snapshot, timeout=30)
    return snapshot
