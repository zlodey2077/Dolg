"""Admin views for ML training: запуск тренировки нейронки прямо с сайта.

Доступно только staff-пользователям (`@staff_member_required`). Тренировка и
импорт HuggingFace-датасетов запускаются в **отдельных потоках** (threading),
чтобы HTTP-запрос не висел. Прогресс пишется в Django-cache, frontend
опрашивает его по AJAX каждые 1.5 сек.

URL-ы (см. Dolg_APP/urls.py):
    /staff/ml-training/              — GET страница с кнопкой + progress UI
    /staff/ml-training/start/        — POST запуск тренировки (выбор датасета)
    /staff/ml-training/status/       — GET текущий прогресс (JSON)
    /staff/ml-training/reset/        — POST сброс state
    /staff/ml-training/import/       — POST импорт HF dataset в БД
    /staff/ml-training/import/status — GET прогресс импорта
"""

from __future__ import annotations

import json
import mimetypes
import os
import threading
import time
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.db.models.fields.files import FileField
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

MLTRAIN_PROGRESS_KEY = 'dolg.ml.train.progress'
MLTRAIN_LOCK_KEY = 'dolg.ml.train.lock'
MLIMPORT_PROGRESS_KEY = 'dolg.ml.import.progress'
MLIMPORT_LOCK_KEY = 'dolg.ml.import.lock'
DATASET_ROOT = Path('Dolg_APP/ml/dataset')
DEFAULT_DATASET = DATASET_ROOT / 'circuits.json'


def _staff_user(user):
    return user if getattr(user, 'is_authenticated', False) else None


def _json_safe(value):
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _create_ml_job(*, job_type: str, user=None, source: str = '', parameters: dict | None = None):
    from Dolg_APP.models import MLJob

    return MLJob.objects.create(
        job_type=job_type,
        status='queued',
        source=(source or '')[:160],
        parameters=parameters or {},
        created_by=_staff_user(user),
    )


def _job_to_payload(job) -> dict | None:
    if not job:
        return None
    return {
        'id': job.pk,
        'job_type': job.job_type,
        'status': job.status,
        'progress_percent': job.progress_percent,
        'source': job.source,
        'message': job.message,
        'processed': job.processed,
        'created_count': job.created_count,
        'updated_count': job.updated_count,
        'skipped_count': job.skipped_count,
        'started_at': job.started_at.isoformat() if job.started_at else None,
        'heartbeat_at': job.heartbeat_at.isoformat() if job.heartbeat_at else None,
        'finished_at': job.finished_at.isoformat() if job.finished_at else None,
        'created_at': job.created_at.isoformat() if job.created_at else None,
        'error': job.error[:500] if job.error else '',
    }


def _latest_ml_job(job_type: str | None = None):
    from Dolg_APP.models import MLJob

    qs = MLJob.objects.all()
    if job_type:
        qs = qs.filter(job_type=job_type)
    return qs.order_by('-created_at').first()


def _progress_percent(payload: dict) -> int:
    if payload.get('progress_percent') is not None:
        return max(0, min(100, int(payload.get('progress_percent') or 0)))
    if payload.get('state') == 'done':
        return 100
    total = payload.get('total_epochs') or payload.get('limit')
    current = payload.get('epoch') or payload.get('processed')
    try:
        if total and current is not None:
            return max(0, min(100, int(float(current) / float(total) * 100)))
    except TypeError, ValueError, ZeroDivisionError:
        pass
    return 0


def _update_ml_job_from_progress(payload: dict, *, job_type: str):
    """Mirror cache progress into persistent MLJob history."""
    if not isinstance(payload, dict):
        return None
    from Dolg_APP.models import MLJob

    job = None
    job_id = payload.get('job_id')
    if job_id:
        job = MLJob.objects.filter(pk=job_id).first()
    if job is None:
        job = (
            MLJob.objects.filter(job_type=job_type, status__in=['queued', 'running'])
            .order_by('-created_at')
            .first()
        )
    if job is None:
        return None

    state = payload.get('state')
    message = str(payload.get('message') or '')[:260]
    stdout_tail = str(payload.get('output_tail') or '')[-4000:]

    if state == 'running':
        if job.started_at is None:
            job.started_at = timezone.now()
        job.status = 'running'
        job.heartbeat_at = timezone.now()
        job.progress_percent = _progress_percent(payload)
        job.message = message or job.message
        job.processed = int(payload.get('epoch') or payload.get('processed') or job.processed or 0)
        job.created_count = int(
            payload.get('imported')
            or payload.get('created')
            or payload.get('created_count')
            or job.created_count
            or 0
        )
        job.updated_count = int(
            payload.get('updated') or payload.get('updated_count') or job.updated_count or 0
        )
        job.skipped_count = int(
            payload.get('skipped') or payload.get('skipped_count') or job.skipped_count or 0
        )
        job.result = {
            'state': state,
            'train_loss': payload.get('train_loss'),
            'val_loss': payload.get('val_loss'),
            'elapsed': payload.get('elapsed'),
            'decode_errors': payload.get('decode_errors'),
        }
        job.save()
    elif state == 'done':
        result = payload.get('result') if payload.get('result') is not None else payload
        job.processed = int(payload.get('processed') or job.processed or 0)
        job.created_count = int(
            payload.get('imported')
            or payload.get('created')
            or payload.get('created_count')
            or job.created_count
            or 0
        )
        job.updated_count = int(
            payload.get('updated') or payload.get('updated_count') or job.updated_count or 0
        )
        job.skipped_count = int(
            payload.get('skipped') or payload.get('skipped_count') or job.skipped_count or 0
        )
        job.mark_success(message=message or 'Done', result=_json_safe(result), stdout_tail=stdout_tail)
    elif state == 'error':
        job.mark_error(
            error=str(payload.get('error') or payload.get('traceback') or 'Unknown ML job error'),
            message=message or 'Error',
            stdout_tail=stdout_tail,
        )
    return job


def _recent_ml_jobs(limit: int = 8):
    from Dolg_APP.models import MLJob

    return list(MLJob.objects.select_related('created_by').order_by('-created_at')[:limit])


def _set_progress(payload: dict) -> None:
    """Атомарно пишем текущий progress в cache (TTL = 1 час)."""
    payload.setdefault('server_time', time.time())
    cache.set(MLTRAIN_PROGRESS_KEY, payload, timeout=3600)
    _update_ml_job_from_progress(payload, job_type='training')


def _get_progress() -> dict:
    return cache.get(MLTRAIN_PROGRESS_KEY) or {'state': 'idle'}


def _is_running() -> bool:
    return bool(cache.get(MLTRAIN_LOCK_KEY))


def _set_import_progress(payload: dict) -> None:
    payload.setdefault('server_time', time.time())
    cache.set(MLIMPORT_PROGRESS_KEY, payload, timeout=3600)
    _update_ml_job_from_progress(payload, job_type='dataset_import')


def _get_import_progress() -> dict:
    return cache.get(MLIMPORT_PROGRESS_KEY) or {'state': 'idle'}


def _is_importing() -> bool:
    return bool(cache.get(MLIMPORT_LOCK_KEY))


def _count_schemes_in_json(path: Path) -> int:
    """Считаем кол-во схем в dataset-JSON. Поддерживаем list и {schemes:[...]}."""
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return 0
    if isinstance(payload, list):
        return len(payload)
    return len(payload.get('schemes') or [])


def _collect_datasets() -> list[dict]:
    """Сканируем Dolg_APP/ml/dataset/ + external/ и возвращаем список JSON-файлов.

    Каждый элемент: {path, rel, name, size_kb, scheme_count, source, mtime}.
    Сортируется по mtime DESC (свежие первые), затем по имени.
    """
    DATASET_ROOT.mkdir(parents=True, exist_ok=True)
    items = []
    for json_path in DATASET_ROOT.rglob('*.json'):
        try:
            stat = json_path.stat()
        except OSError:
            continue
        rel = json_path.relative_to(DATASET_ROOT).as_posix()
        items.append(
            {
                'path': str(json_path),
                'rel': rel,
                'name': json_path.name,
                'size_kb': round(stat.st_size / 1024, 1),
                'scheme_count': _count_schemes_in_json(json_path),
                'source': 'external' if 'external' in rel else 'curated',
                'mtime': stat.st_mtime,
            }
        )
    items.sort(key=lambda x: (-x['mtime'], x['name']))
    return items


def _count_db_examples() -> dict:
    """Распределение AITrainingExample по evidence_kind в БД."""
    try:
        from Dolg_APP.services.ai_training import (
            summarize_ai_training_examples,
            validate_ai_training_examples,
        )
    except ImportError:
        return {'total': 0, 'by_kind': {}, 'validation': {'errors_count': 0, 'warnings_count': 0}}
    summary = summarize_ai_training_examples()
    validation = validate_ai_training_examples(limit=500)
    return {
        **summary,
        'by_kind': summary.get('by_evidence_kind') or summary.get('by_kind') or {},
        'validation': {
            'ok': validation.get('ok'),
            'scanned': validation.get('scanned'),
            'errors_count': validation.get('errors_count'),
            'warnings_count': validation.get('warnings_count'),
        },
    }


def _tiny_model_status() -> dict:
    try:
        from Dolg_APP.ml.neural import MODEL_VERSION, default_model_path, torch_available
    except Exception as exc:
        return {'ok': False, 'exists': False, 'error': str(exc)}

    path = default_model_path()
    result = {
        'ok': True,
        'exists': path.exists(),
        'path': str(path),
        'expected_version': MODEL_VERSION,
        'torch_available': torch_available(),
        'size_kb': 0,
        'mtime': None,
        'meta': {},
    }
    if not path.exists():
        return result
    try:
        stat = path.stat()
        result['size_kb'] = round(stat.st_size / 1024, 1)
        result['mtime'] = stat.st_mtime
    except OSError:
        pass
    if not result['torch_available']:
        result['meta_error'] = 'PyTorch is not installed'
        return result
    try:
        import torch

        payload = torch.load(path, map_location='cpu')
        result['meta'] = payload.get('meta') or {}
    except Exception as exc:
        result['meta_error'] = str(exc)
    return result


def _format_bytes(size: int | float | None) -> str:
    try:
        value = float(size or 0)
    except TypeError, ValueError:
        value = 0
    for unit in ('B', 'KB', 'MB', 'GB'):
        if value < 1024 or unit == 'GB':
            return f'{value:.1f} {unit}' if unit != 'B' else f'{int(value)} B'
        value /= 1024
    return f'{value:.1f} GB'


def _database_console_snapshot() -> dict:
    """Read-only database overview for staff Data Console."""
    engine = connection.settings_dict.get('ENGINE', '')
    name = connection.settings_dict.get('NAME', '')
    host = connection.settings_dict.get('HOST', '')
    vendor = connection.vendor
    snapshot = {
        'vendor': vendor,
        'engine': engine,
        'name': str(name),
        'host': host or 'local file',
        'is_postgres': vendor == 'postgresql',
        'tables': [],
        'models': [],
        'file_fields': [],
        'postgres': {},
    }

    with connection.cursor() as cursor:
        table_names = connection.introspection.table_names(cursor)
        quote = connection.ops.quote_name
        for table in sorted(table_names):
            row_count = None
            try:
                cursor.execute(f'SELECT COUNT(*) FROM {quote(table)}')
                row_count = cursor.fetchone()[0]
            except Exception:
                row_count = None
            snapshot['tables'].append({'name': table, 'rows': row_count})

        if vendor == 'postgresql':
            try:
                cursor.execute('SELECT version()')
                snapshot['postgres']['version'] = cursor.fetchone()[0]
            except Exception:
                snapshot['postgres']['version'] = ''
            try:
                cursor.execute('SELECT pg_database_size(current_database())')
                snapshot['postgres']['size'] = _format_bytes(cursor.fetchone()[0])
            except Exception:
                snapshot['postgres']['size'] = ''

    for model in apps.get_models():
        opts = model._meta
        if opts.proxy or not opts.managed:
            continue
        count = None
        try:
            count = model._default_manager.count()
        except Exception:
            count = None
        snapshot['models'].append(
            {
                'label': opts.label,
                'app_label': opts.app_label,
                'model_name': opts.model_name,
                'db_table': opts.db_table,
                'rows': count,
                'admin_url': f'/admin/{opts.app_label}/{opts.model_name}/',
            }
        )
        for field in opts.fields:
            if isinstance(field, FileField):
                filled = None
                try:
                    filled = (
                        model._default_manager.exclude(**{field.name: ''})
                        .exclude(**{f'{field.name}__isnull': True})
                        .count()
                    )
                except Exception:
                    filled = None
                snapshot['file_fields'].append(
                    {
                        'model': opts.label,
                        'field': field.name,
                        'upload_to': str(field.upload_to),
                        'filled': filled,
                        'admin_url': f'/admin/{opts.app_label}/{opts.model_name}/',
                    }
                )

    snapshot['models'].sort(key=lambda item: (item['app_label'], item['model_name']))
    snapshot['file_fields'].sort(key=lambda item: (item['model'], item['field']))
    return snapshot


def _safe_media_path(raw_path: str = '') -> tuple[Path, str]:
    media_root = Path(settings.MEDIA_ROOT).resolve()
    raw = (raw_path or '').strip().replace('\\', '/').strip('/')
    candidate = (media_root / raw).resolve()
    try:
        rel = candidate.relative_to(media_root).as_posix()
    except ValueError:
        candidate = media_root
        rel = ''
    return candidate, rel


def _storage_console_snapshot(path: str = '', preview_file: str = '') -> dict:
    """Small media file browser: directory listing + optional safe preview."""
    media_root = Path(settings.MEDIA_ROOT).resolve()
    current, rel = _safe_media_path(path)
    if not current.exists() or not current.is_dir():
        current, rel = media_root, ''

    dirs = []
    files = []
    try:
        children = sorted(current.iterdir(), key=lambda item: (item.is_file(), item.name.lower()))
    except OSError:
        children = []

    for item in children:
        try:
            stat = item.stat()
            item_rel = item.relative_to(media_root).as_posix()
        except OSError:
            continue
        if item.is_dir():
            dirs.append(
                {
                    'name': item.name,
                    'path': item_rel,
                    'mtime': timezone.datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.get_current_timezone()
                    ),
                }
            )
        elif item.is_file():
            mime, _enc = mimetypes.guess_type(item.name)
            files.append(
                {
                    'name': item.name,
                    'path': item_rel,
                    'size': stat.st_size,
                    'size_label': _format_bytes(stat.st_size),
                    'mime': mime or 'application/octet-stream',
                    'mtime': timezone.datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.get_current_timezone()
                    ),
                    'url': settings.MEDIA_URL.rstrip('/') + '/' + item_rel,
                }
            )

    breadcrumbs = []
    accum = []
    for part in rel.split('/') if rel else []:
        accum.append(part)
        breadcrumbs.append({'name': part, 'path': '/'.join(accum)})

    preview = None
    if preview_file:
        selected, selected_rel = _safe_media_path(preview_file)
        try:
            selected.relative_to(current)
        except ValueError:
            selected = None
        if selected and selected.exists() and selected.is_file():
            stat = selected.stat()
            mime, _enc = mimetypes.guess_type(selected.name)
            mime = mime or 'application/octet-stream'
            preview = {
                'name': selected.name,
                'path': selected_rel,
                'size_label': _format_bytes(stat.st_size),
                'mime': mime,
                'url': settings.MEDIA_URL.rstrip('/') + '/' + selected_rel,
                'text': '',
                'is_image': mime.startswith('image/'),
            }
            if stat.st_size <= 200 * 1024 and (
                mime.startswith('text/') or mime in {'application/json', 'application/xml', 'image/svg+xml'}
            ):
                try:
                    preview['text'] = selected.read_text(encoding='utf-8', errors='replace')[:12000]
                except OSError:
                    preview['text'] = ''

    total_size = 0
    total_files = 0
    try:
        for item in media_root.rglob('*'):
            if item.is_file():
                total_files += 1
                total_size += item.stat().st_size
    except OSError:
        pass

    return {
        'root': str(media_root),
        'current_path': rel,
        'parent_path': str(Path(rel).parent).replace('\\', '/')
        if rel and str(Path(rel).parent) != '.'
        else '',
        'breadcrumbs': breadcrumbs,
        'dirs': dirs,
        'files': files,
        'preview': preview,
        'total_files': total_files,
        'total_size_label': _format_bytes(total_size),
    }


def _train_in_background(
    *, epochs: int, dataset_path: str | None, size: int, include_db: bool = False, job_id: int | None = None
) -> None:
    """Внутренний worker — выполняется в отдельном потоке."""
    from Dolg_APP.ml.neural import train_tiny_model

    try:
        cache.set(MLTRAIN_LOCK_KEY, True, timeout=3600)
        started_at = time.time()
        _set_progress(
            {
                'job_id': job_id,
                'state': 'running',
                'epoch': 0,
                'total_epochs': epochs,
                'train_loss': None,
                'val_loss': None,
                'started_at': started_at,
                'heartbeat_at': started_at,
                'message': 'Подготовка датасета…',
            }
        )

        # Подгружаем dataset из JSON + опционально из БД
        extra_schemes = []
        if dataset_path:
            try:
                payload = json.loads(Path(dataset_path).read_text(encoding='utf-8'))
                items = payload if isinstance(payload, list) else (payload.get('schemes') or [])
                extra_schemes = [item for item in items if isinstance(item, dict) and item.get('components')]
            except Exception as exc:
                _set_progress(
                    {
                        'job_id': job_id,
                        'state': 'error',
                        'error': f'Не удалось загрузить датасет: {exc}',
                    }
                )
                return

        if include_db:
            try:
                from Dolg_APP.services.ai_training import curated_training_schemes

                db_schemes = curated_training_schemes(limit=5000)
                extra_schemes.extend(db_schemes)
            except Exception:
                pass  # БД не критична — продолжаем с тем, что есть

        def on_progress(epoch, total, train_loss, val_loss):
            _set_progress(
                {
                    'job_id': job_id,
                    'state': 'running',
                    'epoch': int(epoch),
                    'total_epochs': int(total),
                    'train_loss': float(train_loss) if train_loss is not None else None,
                    'val_loss': float(val_loss) if val_loss is not None else None,
                    'started_at': started_at,
                    'elapsed': round(time.time() - started_at, 1),
                    'message': f'Эпоха {epoch}/{total}',
                }
            )

        result = train_tiny_model(
            size=size,
            epochs=epochs,
            extra_schemes=extra_schemes,
            progress_callback=on_progress,
        )

        _set_progress(
            {
                'job_id': job_id,
                'state': 'done',
                'result': result,
                'finished_at': time.time(),
                'elapsed': round(time.time() - started_at, 1),
                'message': f'Готово! Итоговый loss = {result.get("final_loss")}',
            }
        )
    except Exception as exc:
        import traceback

        _set_progress(
            {
                'job_id': job_id,
                'state': 'error',
                'error': str(exc),
                'traceback': traceback.format_exc(),
            }
        )
    finally:
        cache.delete(MLTRAIN_LOCK_KEY)


# ---------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------


@staff_member_required
def ml_training_page(request):
    """GET: страница с кнопкой запуска и live progress."""
    progress = _get_progress()
    datasets = _collect_datasets()
    db_stats = _count_db_examples()
    context = {
        'progress': progress,
        'is_running': _is_running(),
        # Legacy fields для совместимости с шаблоном
        'dataset_path': str(DEFAULT_DATASET),
        'dataset_exists': DEFAULT_DATASET.exists(),
        'dataset_size_kb': round(DEFAULT_DATASET.stat().st_size / 1024, 1) if DEFAULT_DATASET.exists() else 0,
        # Новое: список всех найденных JSON-датасетов + DB-стат
        'datasets': datasets,
        'datasets_total_schemes': sum(d['scheme_count'] for d in datasets),
        'db_stats': db_stats,
        # Импорт HF
        'import_progress': _get_import_progress(),
        'is_importing': _is_importing(),
        # HF_TOKEN — анонимная загрузка часто зависает. Показываем хинт
        # в шаблоне, если токен не задан.
        'has_hf_token': bool(os.getenv('HF_TOKEN') or os.getenv('HUGGINGFACE_TOKEN')),
        'recent_jobs': _recent_ml_jobs(limit=6),
    }
    return render(request, 'admin/ml_training.html', context)


@staff_member_required
def ml_dataset_quality_page(request):
    """GET: staff-only quality dashboard for AI dataset and tiny model."""
    try:
        from Dolg_APP.services.ai_training import (
            summarize_ai_training_examples,
            validate_ai_training_examples,
        )
    except Exception as exc:
        summary = {'ok': False, 'total': 0, 'error': str(exc)}
        validation = {
            'ok': False,
            'scanned': 0,
            'errors_count': 0,
            'warnings_count': 0,
            'errors': [],
            'warnings': [],
        }
    else:
        summary = summarize_ai_training_examples()
        validation = validate_ai_training_examples(limit=1000)
    return render(
        request,
        'admin/ml_dataset_quality.html',
        {
            'summary': summary,
            'validation': validation,
            'model_status': _tiny_model_status(),
            'db_stats': _count_db_examples(),
            'datasets': _collect_datasets(),
            'recent_jobs': _recent_ml_jobs(limit=8),
        },
    )


@staff_member_required
def staff_ops_dashboard(request):
    """Staff cockpit for runtime, business, data, ML and moderation counters."""
    from Dolg_APP.services.ops_metrics import collect_ops_snapshot

    snapshot = collect_ops_snapshot(use_cache=False)
    catalog = snapshot.get('catalog') or {}
    projects = snapshot.get('projects') or {}
    ai_ml = snapshot.get('ai_ml') or {}
    moderation = snapshot.get('moderation') or {}

    project_counts = {
        'total': projects.get('projects_total', 0),
        'active': projects.get('projects_active', 0),
        'demo': projects.get('projects_demo', 0),
        'public': projects.get('projects_public', 0),
        'pending_review': projects.get('projects_pending_review', 0),
        'reviews': projects.get('reviews', 0),
        'events': projects.get('events', 0),
    }
    ai_counts = {
        'examples': ai_ml.get('examples', 0),
        'validated': ai_ml.get('validated', 0),
        'with_project': 0,
        'artifacts': ai_ml.get('artifacts', 0),
        'artifact_errors': ai_ml.get('artifact_errors', 0),
    }
    catalog_counts = {
        'products': catalog.get('products', 0),
        'categories': catalog.get('categories', 0),
    }
    knowledge_counts = {
        'articles': 0,
        'learning_tasks': 0,
    }
    try:
        from knowledge.models import Article, LearningTask

        knowledge_counts = {
            'articles': Article.objects.count(),
            'learning_tasks': LearningTask.objects.count(),
        }
    except Exception:
        pass
    moderation_counts = {
        'cases_open': moderation.get('cases_open', 0),
        'reports': moderation.get('reports_total', 0),
        'restrictions_active': moderation.get('restrictions_active', 0),
    }
    return render(
        request,
        'admin/ops_dashboard.html',
        {
            'ops_snapshot': snapshot,
            'project_counts': project_counts,
            'ai_counts': ai_counts,
            'catalog_counts': catalog_counts,
            'knowledge_counts': knowledge_counts,
            'moderation_counts': moderation_counts,
            'ml_status_counts': ai_ml.get('ml_status') or {},
            'ml_type_counts': ai_ml.get('ml_type') or {},
            'recent_jobs': _recent_ml_jobs(limit=10),
            'current_training': _get_progress(),
            'current_import': _get_import_progress(),
        },
    )


@staff_member_required
def staff_data_console(request):
    """Read-only database + media explorer for staff operations."""
    path = request.GET.get('path', '')
    preview = request.GET.get('preview', '')
    return render(
        request,
        'admin/data_console.html',
        {
            'db_snapshot': _database_console_snapshot(),
            'storage_snapshot': _storage_console_snapshot(path=path, preview_file=preview),
        },
    )


@staff_member_required
@require_GET
def staff_ops_snapshot_api(request):
    from Dolg_APP.services.ops_metrics import collect_ops_snapshot

    try:
        period_days = int(request.GET.get('period_days', 7))
    except TypeError, ValueError:
        period_days = 7
    period_days = max(1, min(90, period_days))
    return JsonResponse(
        {
            'ok': True,
            'snapshot': collect_ops_snapshot(period_days=period_days, use_cache=False),
        }
    )


def _validate_dataset_path(raw: str | None) -> Path | None:
    """Защита от path-traversal: разрешаем только пути внутри DATASET_ROOT."""
    if not raw:
        return None
    try:
        candidate = Path(raw).resolve()
        root = DATASET_ROOT.resolve()
        candidate.relative_to(root)
    except ValueError, OSError:
        return None
    return candidate if candidate.exists() else None


@staff_member_required
@require_POST
def ml_training_start(request):
    """POST: запуск тренировки в отдельном потоке.

    Параметры:
      epochs (int)         — 10..1000
      size (int)           — 50..1000 (synthetic размер)
      dataset_path (str)   — путь к JSON-датасету (опционально, default = circuits.json)
      include_db (bool)    — добавить ли AITrainingExample из БД к extra_schemes
    """
    if _is_running():
        return JsonResponse({'ok': False, 'error': 'Тренировка уже запущена.'}, status=409)

    try:
        epochs = int(request.POST.get('epochs', 200))
        size = int(request.POST.get('size', 240))
    except TypeError, ValueError:
        return JsonResponse({'ok': False, 'error': 'Невалидные параметры.'}, status=400)

    epochs = max(10, min(1000, epochs))
    size = max(50, min(1000, size))

    requested = request.POST.get('dataset_path') or str(DEFAULT_DATASET)
    safe_path = _validate_dataset_path(requested)
    dataset_path = str(safe_path) if safe_path else None
    include_db = request.POST.get('include_db') in ('1', 'true', 'on', 'yes')
    job = _create_ml_job(
        job_type='training',
        user=request.user,
        source=Path(dataset_path).name if dataset_path else 'synthetic',
        parameters={
            'epochs': epochs,
            'size': size,
            'dataset_path': dataset_path,
            'include_db': include_db,
        },
    )

    thread = threading.Thread(
        target=_train_in_background,
        kwargs={
            'epochs': epochs,
            'dataset_path': dataset_path,
            'size': size,
            'include_db': include_db,
            'job_id': job.pk,
        },
        daemon=True,
    )
    thread.start()

    return JsonResponse(
        {
            'ok': True,
            'epochs': epochs,
            'size': size,
            'dataset_path': dataset_path,
            'include_db': include_db,
            'job_id': job.pk,
            'message': 'Тренировка запущена в фоне. Следите за прогрессом.',
        }
    )


# ─── Импорт HuggingFace dataset в БД ────────────────────────────────────────


def _import_in_background(
    *,
    source: str,
    limit: int,
    persist: bool,
    local_only: bool = False,
    as_projects: bool = False,
    project_min_quality: int = 60,
    job_id: int | None = None,
) -> None:
    """Worker: вызов management-команды `import_external_datasets`.

    Прогресс пишется в cache как `started_at` (unix-timestamp). Клиент сам
    считает elapsed от текущего времени минус started_at — это даёт живой
    таймер без необходимости тикать каждую секунду на сервере.
    """
    try:
        cache.set(MLIMPORT_LOCK_KEY, True, timeout=7200)
        started_at = time.time()
        _set_import_progress(
            {
                'job_id': job_id,
                'state': 'running',
                'source': source,
                'limit': limit,
                'persist': persist,
                'local_only': local_only,
                'as_projects': as_projects,
                'project_min_quality': project_min_quality,
                'started_at': started_at,
                'server_time': started_at,  # для синхронизации часов клиент/сервер
                'message': f'Импорт {limit} схем из {source}…',
            }
        )

        # Перехватываем stdout/stderr management-команды
        import io

        buf = io.StringIO()
        try:
            call_command(
                'import_external_datasets',
                source=source,
                limit=limit,
                persist=persist,
                local_only=local_only,
                as_projects=as_projects,
                project_min_quality=project_min_quality,
                # Команда будет писать live-прогресс (processed/imported/skipped)
                # в этот же cache-key каждые 10 строк → JS видит проценты + ETA.
                progress_cache_key=MLIMPORT_PROGRESS_KEY,
                stdout=buf,
                stderr=buf,
            )
            output = buf.getvalue()
            _set_import_progress(
                {
                    'job_id': job_id,
                    'state': 'done',
                    'source': source,
                    'limit': limit,
                    'persist': persist,
                    'output_tail': output[-2000:],  # последние 2 КБ
                    'finished_at': time.time(),
                    'elapsed': round(time.time() - started_at, 1),
                    'message': f'Импорт завершён ({source}, limit={limit}, persist={persist}).',
                }
            )
        except Exception as exc:
            import traceback

            _set_import_progress(
                {
                    'job_id': job_id,
                    'state': 'error',
                    'error': str(exc),
                    'output_tail': buf.getvalue()[-2000:],
                    'traceback': traceback.format_exc(),
                    'elapsed': round(time.time() - started_at, 1),
                }
            )
    finally:
        cache.delete(MLIMPORT_LOCK_KEY)


@staff_member_required
@require_POST
def ml_dataset_import(request):
    """POST: запуск import_external_datasets в фоне.

    Параметры:
      source (str)   — open_schematics | spice_dir
      limit (int)    — 1..5000
      persist (bool) — сохранять ли в AITrainingExample БД
    """
    if _is_importing():
        return JsonResponse({'ok': False, 'error': 'Импорт уже выполняется.'}, status=409)

    source = request.POST.get('source', 'open_schematics')
    if source not in ('open_schematics',):
        return JsonResponse({'ok': False, 'error': f'Неподдерживаемый source: {source}'}, status=400)
    try:
        limit = int(request.POST.get('limit', 500))
    except TypeError, ValueError:
        return JsonResponse({'ok': False, 'error': 'Невалидный limit.'}, status=400)
    limit = max(1, min(5000, limit))
    persist = request.POST.get('persist') in ('1', 'true', 'on', 'yes')
    local_only = request.POST.get('local_only') in ('1', 'true', 'on', 'yes')
    as_projects = request.POST.get('as_projects') in ('1', 'true', 'on', 'yes')
    try:
        project_min_quality = int(request.POST.get('project_min_quality', 60))
    except TypeError, ValueError:
        project_min_quality = 60
    project_min_quality = max(0, min(100, project_min_quality))
    job = _create_ml_job(
        job_type='dataset_import',
        user=request.user,
        source=source,
        parameters={
            'limit': limit,
            'persist': persist,
            'local_only': local_only,
            'as_projects': as_projects,
            'project_min_quality': project_min_quality,
        },
    )

    thread = threading.Thread(
        target=_import_in_background,
        kwargs={
            'source': source,
            'limit': limit,
            'persist': persist,
            'local_only': local_only,
            'as_projects': as_projects,
            'project_min_quality': project_min_quality,
            'job_id': job.pk,
        },
        daemon=True,
    )
    thread.start()

    return JsonResponse(
        {
            'ok': True,
            'source': source,
            'limit': limit,
            'persist': persist,
            'local_only': local_only,
            'as_projects': as_projects,
            'project_min_quality': project_min_quality,
            'job_id': job.pk,
            'message': f'Импорт {limit} схем из {source} запущен.',
        }
    )


@staff_member_required
@require_GET
def ml_dataset_import_status(request):
    """GET: текущий прогресс импорта (для polling)."""
    progress = _get_import_progress()
    latest_job = _update_ml_job_from_progress(progress, job_type='dataset_import') or _latest_ml_job(
        'dataset_import'
    )
    server_time = time.time()
    if isinstance(progress, dict) and progress.get('state') == 'running':
        heartbeat = progress.get('heartbeat_at') or progress.get('server_time') or progress.get('started_at')
        if heartbeat:
            stale_seconds = max(0, int(server_time - float(heartbeat)))
            progress['stale_seconds'] = stale_seconds
            progress['stale'] = stale_seconds >= 120
    return JsonResponse(
        {
            'ok': True,
            'is_importing': _is_importing(),
            'progress': progress,
            'latest_job': _job_to_payload(latest_job),
            'server_time': server_time,
        }
    )


@staff_member_required
@require_GET
def ml_training_status(request):
    """GET: текущий прогресс (JSON для polling).

    `server_time` нужно для клиентского таймера: JS считает live elapsed
    как (Date.now()/1000 - started_at + (server_time - client_time_at_recv)).
    """
    progress = _get_progress()
    latest_job = _update_ml_job_from_progress(progress, job_type='training') or _latest_ml_job('training')
    return JsonResponse(
        {
            'ok': True,
            'is_running': _is_running(),
            'progress': progress,
            'latest_job': _job_to_payload(latest_job),
            'server_time': time.time(),
        }
    )


@staff_member_required
@require_POST
def ml_training_reset(request):
    """POST: сброс state (чтобы пользователь мог запустить новую сессию).

    Сбрасывает: training progress, training lock, import progress, import lock,
    + удаляет зависшие .incomplete файлы в HF-кеше (Cloudflare timeout / hung
    httpx connection — обычная причина зависания импорта на 90+ МБ).
    Background thread сам по себе не убивается (Python GIL), но при следующем
    тике watcher'а он увидит освободившийся lock и выйдет.
    """
    cache.delete(MLTRAIN_PROGRESS_KEY)
    cache.delete(MLTRAIN_LOCK_KEY)
    cache.delete(MLIMPORT_PROGRESS_KEY)
    cache.delete(MLIMPORT_LOCK_KEY)
    from Dolg_APP.models import MLJob

    now = timezone.now()
    jobs_cancelled = MLJob.objects.filter(
        job_type__in=['training', 'dataset_import'],
        status__in=['queued', 'running'],
    ).update(
        status='cancelled',
        heartbeat_at=now,
        finished_at=now,
        message='Reset from staff ML page',
    )

    # Чистим зависшие .incomplete в HF-кеше
    removed = 0
    try:
        from huggingface_hub.constants import HF_HUB_CACHE

        cache_dir = Path(HF_HUB_CACHE)
        for inc in cache_dir.rglob('*.incomplete'):
            try:
                inc.unlink()
                removed += 1
            except OSError:
                pass  # held by background thread — отпустит само
    except Exception:
        pass

    msg = 'Состояние сброшено.'
    if jobs_cancelled:
        msg += f' MLJob отменено: {jobs_cancelled}.'
    if removed:
        msg += f' Удалено {removed} битых .incomplete файла(ов) HF-кеша.'
    return JsonResponse(
        {'ok': True, 'message': msg, 'incomplete_removed': removed, 'jobs_cancelled': jobs_cancelled}
    )
