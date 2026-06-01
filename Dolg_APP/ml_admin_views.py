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
import os
import threading
import time
from pathlib import Path

from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.core.management import call_command
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

MLTRAIN_PROGRESS_KEY = 'dolg.ml.train.progress'
MLTRAIN_LOCK_KEY = 'dolg.ml.train.lock'
MLIMPORT_PROGRESS_KEY = 'dolg.ml.import.progress'
MLIMPORT_LOCK_KEY = 'dolg.ml.import.lock'
DATASET_ROOT = Path('Dolg_APP/ml/dataset')
DEFAULT_DATASET = DATASET_ROOT / 'circuits.json'


def _set_progress(payload: dict) -> None:
    """Атомарно пишем текущий progress в cache (TTL = 1 час)."""
    cache.set(MLTRAIN_PROGRESS_KEY, payload, timeout=3600)


def _get_progress() -> dict:
    return cache.get(MLTRAIN_PROGRESS_KEY) or {'state': 'idle'}


def _is_running() -> bool:
    return bool(cache.get(MLTRAIN_LOCK_KEY))


def _set_import_progress(payload: dict) -> None:
    cache.set(MLIMPORT_PROGRESS_KEY, payload, timeout=3600)


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
        items.append({
            'path': str(json_path),
            'rel': rel,
            'name': json_path.name,
            'size_kb': round(stat.st_size / 1024, 1),
            'scheme_count': _count_schemes_in_json(json_path),
            'source': 'external' if 'external' in rel else 'curated',
            'mtime': stat.st_mtime,
        })
    items.sort(key=lambda x: (-x['mtime'], x['name']))
    return items


def _count_db_examples() -> dict:
    """Распределение AITrainingExample по evidence_kind в БД."""
    try:
        from Dolg_APP.services.ai_training import summarize_ai_training_examples, validate_ai_training_examples
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


def _train_in_background(*, epochs: int, dataset_path: str | None, size: int,
                          include_db: bool = False) -> None:
    """Внутренний worker — выполняется в отдельном потоке."""
    from Dolg_APP.ml.neural import train_tiny_model

    try:
        cache.set(MLTRAIN_LOCK_KEY, True, timeout=3600)
        started_at = time.time()
        _set_progress({
            'state': 'running',
            'epoch': 0,
            'total_epochs': epochs,
            'train_loss': None,
            'val_loss': None,
            'started_at': started_at,
            'heartbeat_at': started_at,
            'message': 'Подготовка датасета…',
        })

        # Подгружаем dataset из JSON + опционально из БД
        extra_schemes = []
        if dataset_path:
            try:
                payload = json.loads(Path(dataset_path).read_text(encoding='utf-8'))
                items = payload if isinstance(payload, list) else (payload.get('schemes') or [])
                extra_schemes = [item for item in items if isinstance(item, dict) and item.get('components')]
            except Exception as exc:
                _set_progress({
                    'state': 'error',
                    'error': f'Не удалось загрузить датасет: {exc}',
                })
                return

        if include_db:
            try:
                from Dolg_APP.services.ai_training import curated_training_schemes
                db_schemes = curated_training_schemes(limit=5000)
                extra_schemes.extend(db_schemes)
            except Exception:
                pass  # БД не критична — продолжаем с тем, что есть

        def on_progress(epoch, total, train_loss, val_loss):
            _set_progress({
                'state': 'running',
                'epoch': int(epoch),
                'total_epochs': int(total),
                'train_loss': float(train_loss) if train_loss is not None else None,
                'val_loss': float(val_loss) if val_loss is not None else None,
                'started_at': started_at,
                'elapsed': round(time.time() - started_at, 1),
                'message': f'Эпоха {epoch}/{total}',
            })

        result = train_tiny_model(
            size=size,
            epochs=epochs,
            extra_schemes=extra_schemes,
            progress_callback=on_progress,
        )

        _set_progress({
            'state': 'done',
            'result': result,
            'finished_at': time.time(),
            'elapsed': round(time.time() - started_at, 1),
            'message': f'Готово! Итоговый loss = {result.get("final_loss")}',
        })
    except Exception as exc:
        import traceback
        _set_progress({
            'state': 'error',
            'error': str(exc),
            'traceback': traceback.format_exc(),
        })
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
    }
    return render(request, 'admin/ml_training.html', context)


@staff_member_required
def ml_dataset_quality_page(request):
    """GET: staff-only quality dashboard for AI dataset and tiny model."""
    try:
        from Dolg_APP.services.ai_training import summarize_ai_training_examples, validate_ai_training_examples
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
    return render(request, 'admin/ml_dataset_quality.html', {
        'summary': summary,
        'validation': validation,
        'model_status': _tiny_model_status(),
        'db_stats': _count_db_examples(),
        'datasets': _collect_datasets(),
    })


def _validate_dataset_path(raw: str | None) -> Path | None:
    """Защита от path-traversal: разрешаем только пути внутри DATASET_ROOT."""
    if not raw:
        return None
    try:
        candidate = Path(raw).resolve()
        root = DATASET_ROOT.resolve()
        candidate.relative_to(root)
    except (ValueError, OSError):
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
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'Невалидные параметры.'}, status=400)

    epochs = max(10, min(1000, epochs))
    size = max(50, min(1000, size))

    requested = request.POST.get('dataset_path') or str(DEFAULT_DATASET)
    safe_path = _validate_dataset_path(requested)
    dataset_path = str(safe_path) if safe_path else None
    include_db = request.POST.get('include_db') in ('1', 'true', 'on', 'yes')

    thread = threading.Thread(
        target=_train_in_background,
        kwargs={
            'epochs': epochs,
            'dataset_path': dataset_path,
            'size': size,
            'include_db': include_db,
        },
        daemon=True,
    )
    thread.start()

    return JsonResponse({
        'ok': True,
        'epochs': epochs,
        'size': size,
        'dataset_path': dataset_path,
        'include_db': include_db,
        'message': 'Тренировка запущена в фоне. Следите за прогрессом.',
    })


# ─── Импорт HuggingFace dataset в БД ────────────────────────────────────────

def _import_in_background(
    *,
    source: str,
    limit: int,
    persist: bool,
    local_only: bool = False,
    as_projects: bool = False,
    project_min_quality: int = 60,
) -> None:
    """Worker: вызов management-команды `import_external_datasets`.

    Прогресс пишется в cache как `started_at` (unix-timestamp). Клиент сам
    считает elapsed от текущего времени минус started_at — это даёт живой
    таймер без необходимости тикать каждую секунду на сервере.
    """
    try:
        cache.set(MLIMPORT_LOCK_KEY, True, timeout=7200)
        started_at = time.time()
        _set_import_progress({
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
        })

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
            _set_import_progress({
                'state': 'done',
                'source': source,
                'limit': limit,
                'persist': persist,
                'output_tail': output[-2000:],  # последние 2 КБ
                'finished_at': time.time(),
                'elapsed': round(time.time() - started_at, 1),
                'message': f'Импорт завершён ({source}, limit={limit}, persist={persist}).',
            })
        except Exception as exc:
            import traceback
            _set_import_progress({
                'state': 'error',
                'error': str(exc),
                'output_tail': buf.getvalue()[-2000:],
                'traceback': traceback.format_exc(),
                'elapsed': round(time.time() - started_at, 1),
            })
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
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'Невалидный limit.'}, status=400)
    limit = max(1, min(5000, limit))
    persist = request.POST.get('persist') in ('1', 'true', 'on', 'yes')
    local_only = request.POST.get('local_only') in ('1', 'true', 'on', 'yes')
    as_projects = request.POST.get('as_projects') in ('1', 'true', 'on', 'yes')
    try:
        project_min_quality = int(request.POST.get('project_min_quality', 60))
    except (TypeError, ValueError):
        project_min_quality = 60
    project_min_quality = max(0, min(100, project_min_quality))

    thread = threading.Thread(
        target=_import_in_background,
        kwargs={
            'source': source,
            'limit': limit,
            'persist': persist,
            'local_only': local_only,
            'as_projects': as_projects,
            'project_min_quality': project_min_quality,
        },
        daemon=True,
    )
    thread.start()

    return JsonResponse({
        'ok': True,
        'source': source,
        'limit': limit,
        'persist': persist,
        'local_only': local_only,
        'as_projects': as_projects,
        'project_min_quality': project_min_quality,
        'message': f'Импорт {limit} схем из {source} запущен.',
    })


@staff_member_required
@require_GET
def ml_dataset_import_status(request):
    """GET: текущий прогресс импорта (для polling)."""
    progress = _get_import_progress()
    server_time = time.time()
    if isinstance(progress, dict) and progress.get('state') == 'running':
        heartbeat = progress.get('heartbeat_at') or progress.get('server_time') or progress.get('started_at')
        if heartbeat:
            stale_seconds = max(0, int(server_time - float(heartbeat)))
            progress['stale_seconds'] = stale_seconds
            progress['stale'] = stale_seconds >= 120
    return JsonResponse({
        'ok': True,
        'is_importing': _is_importing(),
        'progress': progress,
        'server_time': server_time,
    })


@staff_member_required
@require_GET
def ml_training_status(request):
    """GET: текущий прогресс (JSON для polling).

    `server_time` нужно для клиентского таймера: JS считает live elapsed
    как (Date.now()/1000 - started_at + (server_time - client_time_at_recv)).
    """
    return JsonResponse({
        'ok': True,
        'is_running': _is_running(),
        'progress': _get_progress(),
        'server_time': time.time(),
    })


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
    if removed:
        msg += f' Удалено {removed} битых .incomplete файла(ов) HF-кеша.'
    return JsonResponse({'ok': True, 'message': msg, 'incomplete_removed': removed})
