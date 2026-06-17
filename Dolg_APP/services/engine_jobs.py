"""Async EngineJob worker helpers.

The web API only persists jobs. This module is the first worker-side layer:
it claims queued local jobs, executes the internal NumPy MNA adapter, and
stores a normalized result payload. External CLI engines stay outside Django
requests and will later live in Docker/Kubernetes workers.
"""

from __future__ import annotations

import math
import os
import socket
import time
from typing import Any

from django.db import connection, transaction
from django.utils import timezone

from Dolg_APP.models import EngineJob, ProjectEvent, SimulationRun

from .engineering_units import parse_engineering_number
from .monte_carlo import (
    run_ac_sweep,
    run_tolerance_analysis,
    scheme_to_circuit,
    solve_dc,
    solve_transient,
)

LOCAL_ENGINE_IDS = ('dolg-numpy-mna',)
TERMINAL_STATUSES = {'success', 'error', 'cancelled', 'stale'}


class EngineJobExecutionError(RuntimeError):
    """Expected worker-side job failure that should be stored on the job."""


def default_worker_id() -> str:
    return f'{socket.gethostname()}:{os.getpid()}'


def claim_next_engine_job(
    *,
    worker_id: str | None = None,
    engine_ids: list[str] | tuple[str, ...] | None = None,
) -> EngineJob | None:
    """Atomically claim the oldest queued job for the requested engines."""
    worker_id = worker_id or default_worker_id()
    engine_ids = _normalize_engine_ids(engine_ids)
    now = timezone.now()

    with transaction.atomic():
        jobs = EngineJob.objects.filter(status='queued').order_by('created_at', 'id')
        if engine_ids:
            jobs = jobs.filter(engine_id__in=engine_ids)
        if getattr(connection.features, 'has_select_for_update', False):
            skip_locked = getattr(connection.features, 'has_select_for_update_skip_locked', False)
            jobs = jobs.select_for_update(skip_locked=skip_locked)

        job = jobs.first()
        if not job:
            return None

        updated = EngineJob.objects.filter(pk=job.pk, status='queued').update(
            status='running',
            progress_percent=10,
            message='Worker claimed job.',
            worker=worker_id,
            started_at=now,
            heartbeat_at=now,
        )
        if not updated:
            return None
        job.refresh_from_db()
        return job


def run_due_engine_jobs(
    *,
    limit: int = 1,
    worker_id: str | None = None,
    engine_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Claim and run up to ``limit`` queued jobs."""
    worker_id = worker_id or default_worker_id()
    limit = max(1, min(int(limit or 1), 100))
    jobs = []

    for _ in range(limit):
        job = claim_next_engine_job(worker_id=worker_id, engine_ids=engine_ids)
        if not job:
            break
        jobs.append(run_engine_job(job, worker_id=worker_id))

    return {
        'processed': len(jobs),
        'worker_id': worker_id,
        'jobs': jobs,
    }


def run_engine_job(job: EngineJob, *, worker_id: str | None = None) -> dict[str, Any]:
    """Execute a claimed or queued job and persist the terminal state."""
    worker_id = worker_id or default_worker_id()
    if job.status in TERMINAL_STATUSES:
        return _job_outcome(job)
    if job.status == 'queued':
        _mark_running(job, worker_id)

    started = time.perf_counter()
    _touch_job(job, progress_percent=35, message='Running engine adapter.')
    try:
        result, warnings, artifacts = execute_engine_job(job)
    except EngineJobExecutionError as exc:
        _finish_error(job, str(exc), started)
    except Exception as exc:  # pragma: no cover - safety net for worker durability.
        _finish_error(job, f'unhandled worker error: {exc}', started)
    else:
        _finish_success(job, result, warnings, artifacts, started)
    return _job_outcome(job)


def execute_engine_job(job: EngineJob) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    if job.engine_id not in LOCAL_ENGINE_IDS:
        raise EngineJobExecutionError(
            f'No local adapter for engine "{job.engine_id}". Run a dedicated Docker/CLI worker for this engine.'
        )
    return _run_numpy_mna_adapter(job)


def _run_numpy_mna_adapter(job: EngineJob) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    scheme_data = _scheme_data(job)
    options = job.options or {}
    analysis = _normalize_analysis(job.analysis_type, options)

    if analysis == 'dc':
        result = _run_dc(job, scheme_data)
    elif analysis == 'transient':
        result = _run_transient(job, scheme_data, options)
    elif analysis == 'ac':
        result = _run_ac(job, scheme_data, options)
    elif analysis == 'tolerance':
        result = _run_tolerance(job, scheme_data, options)
    else:
        raise EngineJobExecutionError(f'dolg-numpy-mna does not support analysis "{analysis}" yet')

    warnings = list(result.get('warnings') or [])
    artifacts = list(result.get('artifacts') or [])
    return result, warnings, artifacts


def _run_dc(job: EngineJob, scheme_data: dict[str, Any]) -> dict[str, Any]:
    circuit = scheme_to_circuit(scheme_data)
    if not circuit.get('elements'):
        raise EngineJobExecutionError('scheme has no simulatable components')

    raw = solve_dc(circuit)
    voltages = _number_map(raw.get('voltages') or {})
    currents = _number_map(raw.get('currents') or {})
    nodes = [{'id': node, 'voltage_v': value, 'unit': 'V'} for node, value in voltages.items()]
    branches = [{'id': branch, 'current_a': value, 'unit': 'A'} for branch, value in currents.items()]

    return {
        'ok': True,
        'schema_version': 1,
        'engine': job.engine_id,
        'engine_name': job.engine_name,
        'analysis_type': 'dc',
        'nodes': nodes,
        'branches': branches,
        'waveforms': [],
        'metrics': {
            'node_count': int(circuit.get('n_nodes') or 0),
            'element_count': len(circuit.get('elements') or []),
            'voltage_source_count': len(currents),
        },
        'node_voltages': voltages,
        'currents_a': currents,
        'warnings': [],
        'artifacts': [],
    }


def _run_transient(
    job: EngineJob,
    scheme_data: dict[str, Any],
    options: dict[str, Any],
) -> dict[str, Any]:
    circuit = scheme_to_circuit(scheme_data)
    if not circuit.get('elements'):
        raise EngineJobExecutionError('scheme has no simulatable components')

    t_stop = _option_number(options, ('t_stop', 'stop_s', 'stop', 'tStop'), default=1e-3, unit='second')
    dt = _option_number(
        options,
        ('dt', 'step_s', 'step', 'time_step', 'timeStep'),
        default=max(t_stop / 200.0, 1e-9),
        unit='second',
    )
    max_points = _option_int(options, ('max_points', 'maxPoints'), default=1024, minimum=16, maximum=4096)
    transient = solve_transient(circuit, t_stop=t_stop, dt=dt)
    times = [float(value) for value in transient.get('time') or []]
    indices = _thin_indices(len(times), max_points)
    thin_times = [times[i] for i in indices]

    voltage_series = {}
    waveforms = []
    for node, values in (transient.get('voltages') or {}).items():
        node_id = str(node)
        thin_values = [float(values[i]) for i in indices]
        voltage_series[node_id] = thin_values
        waveforms.append(
            {
                'name': f'V({node_id})',
                'node': node_id,
                'unit': 'V',
                'points': [{'x': x, 'y': y} for x, y in zip(thin_times, thin_values)],
            }
        )

    return {
        'ok': True,
        'schema_version': 1,
        'engine': job.engine_id,
        'engine_name': job.engine_name,
        'analysis_type': 'transient',
        'time_s': thin_times,
        'nodes': [{'id': node, 'samples': values, 'unit': 'V'} for node, values in voltage_series.items()],
        'branches': [],
        'waveforms': waveforms,
        'metrics': {
            'steps': int(transient.get('steps') or len(times)),
            'returned_points': len(thin_times),
            'dt_s': float(transient.get('dt') or dt),
            't_stop_s': t_stop,
            'node_count': int(circuit.get('n_nodes') or 0),
            'element_count': len(circuit.get('elements') or []),
        },
        'warnings': [],
        'artifacts': [],
    }


def _run_ac(job: EngineJob, scheme_data: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    f_start = _option_number(options, ('f_start', 'start_hz', 'start', 'fStart'), default=1.0, unit='hertz')
    f_stop = _option_number(options, ('f_stop', 'stop_hz', 'stop', 'fStop'), default=1e6, unit='hertz')
    points = _option_int(options, ('points', 'samples'), default=60, minimum=4, maximum=512)
    ac = run_ac_sweep(scheme_data, f_start=f_start, f_stop=f_stop, points=points)
    if not ac.get('ok'):
        raise EngineJobExecutionError(str(ac.get('reason') or ac.get('error') or 'ac sweep failed'))

    return {
        'ok': True,
        'schema_version': 1,
        'engine': job.engine_id,
        'engine_name': job.engine_name,
        'analysis_type': 'ac',
        'nodes': _json_safe(ac.get('nodes') or {}),
        'branches': [],
        'waveforms': [],
        'metrics': {
            'points': len(ac.get('freqs') or []),
            'output_node': ac.get('output_node'),
            'f_3db_hz': ac.get('f_3db_hz'),
            'kind': ac.get('kind'),
        },
        'frequencies_hz': [float(value) for value in ac.get('freqs') or []],
        'warnings': [],
        'artifacts': [],
    }


def _run_tolerance(
    job: EngineJob,
    scheme_data: dict[str, Any],
    options: dict[str, Any],
) -> dict[str, Any]:
    iterations = _option_int(options, ('iterations', 'samples'), default=500, minimum=10, maximum=5000)
    tolerance = _option_number(options, ('tolerance', 'tolerance_percent', 'tolerancePercent'), default=0.05)
    if tolerance > 1.0:
        tolerance /= 100.0
    seed = _option_int(options, ('seed',), default=None, minimum=0, maximum=2**31 - 1)
    component_tolerances = options.get('component_tolerances') or options.get('componentTolerances') or {}
    if not isinstance(component_tolerances, dict):
        component_tolerances = {}

    report = run_tolerance_analysis(
        scheme_data,
        iterations=iterations,
        tolerance=tolerance,
        seed=seed,
        component_tolerances=component_tolerances,
        worst_case=_option_bool(options, ('worst_case', 'worstCase'), default=True),
    )
    mc = report.get('monte_carlo') or {}
    if mc.get('errors') and not mc.get('success'):
        raise EngineJobExecutionError('; '.join(str(err) for err in mc.get('errors')[:3]))

    return {
        'ok': True,
        'schema_version': 1,
        'engine': job.engine_id,
        'engine_name': job.engine_name,
        'analysis_type': 'tolerance',
        'nodes': _json_safe(mc.get('nodes') or {}),
        'branches': _json_safe(mc.get('currents') or {}),
        'waveforms': [],
        'metrics': {
            'iterations': mc.get('iterations'),
            'success': mc.get('success'),
            'failed': mc.get('failed'),
            'iter_per_sec': mc.get('iter_per_sec'),
            'tolerance': tolerance,
        },
        'monte_carlo': _json_safe(mc),
        'worst_case': _json_safe(report.get('worst_case') or {}),
        'paranoia': _json_safe(report.get('paranoia') or {}),
        'warnings': [str(err) for err in mc.get('errors') or []],
        'artifacts': [],
    }


def _mark_running(job: EngineJob, worker_id: str) -> None:
    now = timezone.now()
    EngineJob.objects.filter(pk=job.pk).update(
        status='running',
        progress_percent=10,
        message='Worker started job.',
        worker=worker_id,
        started_at=now,
        heartbeat_at=now,
    )
    job.refresh_from_db()


def _touch_job(job: EngineJob, *, progress_percent: int, message: str) -> None:
    EngineJob.objects.filter(pk=job.pk).update(
        progress_percent=max(0, min(progress_percent, 99)),
        message=message,
        heartbeat_at=timezone.now(),
    )
    job.refresh_from_db()


def _finish_success(
    job: EngineJob,
    result: dict[str, Any],
    warnings: list[str],
    artifacts: list[dict[str, Any]],
    started: float,
) -> None:
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    EngineJob.objects.filter(pk=job.pk).update(
        status='success',
        progress_percent=100,
        message=f'Completed by local worker in {elapsed_ms} ms.',
        result=_json_safe(result),
        warnings=[str(item) for item in warnings],
        artifacts=_json_safe(artifacts),
        error='',
        heartbeat_at=timezone.now(),
        finished_at=timezone.now(),
    )
    job.refresh_from_db()
    try:
        _persist_simulation_run(job, result, warnings, elapsed_ms)
    except Exception as exc:  # pragma: no cover - history is useful, not job-critical.
        saved_warnings = [str(item) for item in warnings]
        saved_warnings.append(f'SimulationRun history save failed: {exc}')
        EngineJob.objects.filter(pk=job.pk).update(warnings=_json_safe(saved_warnings))
        job.warnings = saved_warnings


def _persist_simulation_run(
    job: EngineJob,
    result: dict[str, Any],
    warnings: list[str],
    elapsed_ms: int,
) -> SimulationRun | None:
    if not job.project_id:
        return None
    with transaction.atomic():
        run = SimulationRun.objects.create(
            project_id=job.project_id,
            user_id=job.user_id,
            analysis_type=_simulation_run_analysis(job.analysis_type, result),
            engine=job.engine_id,
            elapsed_ms=max(0, int(elapsed_ms or 0)),
            status='success',
            progress_percent=100,
            message=f'EngineJob #{job.pk}: {job.engine_name or job.engine_id}',
            started_at=job.started_at,
            finished_at=job.finished_at or timezone.now(),
            netlist=job.netlist,
            result_summary=_engine_result_summary(result, warnings),
            result_data=_json_safe(result),
            warnings=[str(item) for item in (warnings or result.get('warnings') or [])],
        )
        ProjectEvent.objects.create(
            project_id=job.project_id,
            user_id=job.user_id,
            event_type='simulation_run',
            payload={
                'run_id': run.id,
                'engine_job_id': job.id,
                'analysis_type': run.analysis_type,
                'engine': run.engine,
                'status': run.status,
                'elapsed_ms': run.elapsed_ms,
                'progress_percent': run.progress_percent,
            },
        )
    return run


def _simulation_run_analysis(analysis_type: str, result: dict[str, Any]) -> str:
    raw = str(result.get('analysis_type') or analysis_type or 'unknown').strip().lower()
    if raw in {'transient', 'time'}:
        return 'tran'
    if raw in {'dc', 'op', 'ac', 'tran', 'pulse'}:
        return raw
    return 'unknown'


def _engine_result_summary(result: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    return {
        'type': result.get('analysis_type') or result.get('type') or 'unknown',
        'node_count': _count_result_rows(result.get('nodes') or result.get('node_voltages')),
        'branch_count': _count_result_rows(result.get('branches') or result.get('currents_a')),
        'waveform_count': _count_result_rows(result.get('waveforms')),
        'has_warnings': bool(warnings or result.get('warnings')),
        'metrics': _json_safe(result.get('metrics') or {}),
    }


def _count_result_rows(value: Any) -> int:
    if isinstance(value, dict):
        return len(value)
    if isinstance(value, (list, tuple)):
        return len(value)
    return 0


def _finish_error(job: EngineJob, error: str, started: float) -> None:
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    EngineJob.objects.filter(pk=job.pk).update(
        status='error',
        progress_percent=100,
        message=f'Worker failed after {elapsed_ms} ms.',
        error=error[:4000],
        heartbeat_at=timezone.now(),
        finished_at=timezone.now(),
    )
    job.refresh_from_db()


def _job_outcome(job: EngineJob) -> dict[str, Any]:
    return {
        'id': job.id,
        'engine_id': job.engine_id,
        'analysis_type': job.analysis_type,
        'status': job.status,
        'progress_percent': job.progress_percent,
        'message': job.message,
        'error': job.error,
    }


def _scheme_data(job: EngineJob) -> dict[str, Any]:
    scheme_data = job.scheme_data or {}
    if not isinstance(scheme_data, dict):
        raise EngineJobExecutionError('scheme_data must be an object')
    if not isinstance(scheme_data.get('components') or [], list):
        raise EngineJobExecutionError('scheme_data.components must be a list')
    if not isinstance(scheme_data.get('connections') or [], list):
        raise EngineJobExecutionError('scheme_data.connections must be a list')
    return scheme_data


def _normalize_engine_ids(engine_ids: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if engine_ids is None:
        return LOCAL_ENGINE_IDS
    return tuple(
        sorted({str(engine_id).strip().lower() for engine_id in engine_ids if str(engine_id).strip()})
    )


def _normalize_analysis(analysis_type: str, options: dict[str, Any]) -> str:
    raw = (
        str(options.get('analysis_type') or options.get('analysis') or analysis_type or 'dc').strip().lower()
    )
    aliases = {
        'unknown': 'dc',
        'op': 'dc',
        'operating_point': 'dc',
        'operating-point': 'dc',
        'tran': 'transient',
        'transient': 'transient',
        'time': 'transient',
        'ac_sweep': 'ac',
        'ac-sweep': 'ac',
        'sweep_ac': 'ac',
        'mc': 'tolerance',
        'monte-carlo': 'tolerance',
        'monte_carlo': 'tolerance',
        'worst_case': 'tolerance',
        'worst-case': 'tolerance',
        'tolerance': 'tolerance',
    }
    return aliases.get(raw, raw or 'dc')


def _option_number(
    options: dict[str, Any],
    keys: tuple[str, ...],
    *,
    default: float,
    unit: str = '',
) -> float:
    value = _first_option(options, keys)
    parsed = parse_engineering_number(value, default=default, expected_unit=unit)
    number = float(parsed if parsed is not None else default)
    if not math.isfinite(number):
        return float(default)
    return max(number, 1e-18)


def _option_int(
    options: dict[str, Any],
    keys: tuple[str, ...],
    *,
    default: int | None,
    minimum: int,
    maximum: int,
) -> int | None:
    value = _first_option(options, keys)
    if value is None:
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


def _option_bool(options: dict[str, Any], keys: tuple[str, ...], *, default: bool) -> bool:
    value = _first_option(options, keys)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def _first_option(options: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in options and options[key] not in (None, ''):
            return options[key]
    return None


def _number_map(mapping: dict[Any, Any]) -> dict[str, float]:
    return {str(key): float(value) for key, value in sorted(mapping.items(), key=lambda item: str(item[0]))}


def _thin_indices(length: int, limit: int) -> list[int]:
    if length <= 0:
        return []
    if length <= limit:
        return list(range(length))
    return sorted({round(i * (length - 1) / (limit - 1)) for i in range(limit)})


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, 'item'):
        try:
            return _json_safe(value.item())
        except Exception:
            return str(value)
    return value
