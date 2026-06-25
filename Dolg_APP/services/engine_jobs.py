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
from django.db.models import Q
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

ENGINE_RESULT_CONTRACT = {
    'kind': 'dolg.engine.result',
    'version': 1,
}
ENGINE_JOB_STALE_AFTER_SECONDS = 180
LOCAL_ENGINE_IDS = ('dolg-engine-router', 'dolg-numpy-mna')
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
        append_job_audit(
            job,
            'claimed',
            actor=worker_id,
            message='Worker claimed queued job.',
            meta={'worker': worker_id},
        )
        return job


def append_job_audit(
    job: EngineJob,
    action: str,
    *,
    actor: str = 'system',
    message: str = '',
    meta: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Append a compact audit event to EngineJob.audit_log."""
    entry = {
        'at': timezone.now().isoformat(),
        'action': str(action or 'event')[:64],
        'actor': str(actor or 'system')[:120],
        'message': str(message or '')[:260],
        'meta': _json_safe(meta or {}),
    }
    current = job.audit_log if isinstance(job.audit_log, list) else []
    next_log = [*current, entry][-60:]
    EngineJob.objects.filter(pk=job.pk).update(audit_log=next_log)
    job.audit_log = next_log
    return next_log


def retry_engine_job(
    job: EngineJob,
    *,
    actor: str = 'system',
    reason: str = 'Retry requested.',
) -> tuple[bool, str]:
    """Reset a terminal job to queued while preserving a short audit trail."""
    if job.status in {'queued', 'running'}:
        return False, 'job is already active'
    retry_count = int(job.retry_count or 0)
    max_retries = int(job.max_retries or 0)
    if max_retries >= 0 and retry_count >= max_retries:
        message = f'max retries reached ({retry_count}/{max_retries})'
        EngineJob.objects.filter(pk=job.pk).update(reason=message, message=message)
        job.reason = message
        job.message = message
        append_job_audit(job, 'retry_rejected', actor=actor, message=message)
        return False, message

    now_reason = str(reason or 'Retry requested.')[:180]
    EngineJob.objects.filter(pk=job.pk).update(
        status='queued',
        progress_percent=0,
        message=now_reason,
        reason=now_reason,
        retry_count=retry_count + 1,
        external_id='',
        worker='',
        result={},
        result_contract_version=ENGINE_RESULT_CONTRACT['version'],
        warnings=[],
        artifacts=[],
        error='',
        started_at=None,
        heartbeat_at=None,
        finished_at=None,
    )
    job.refresh_from_db()
    append_job_audit(
        job,
        'retry',
        actor=actor,
        message=now_reason,
        meta={'retry_count': job.retry_count, 'max_retries': job.max_retries},
    )
    return True, now_reason


def mark_stale_engine_jobs(
    *,
    max_age_seconds: int = ENGINE_JOB_STALE_AFTER_SECONDS,
    actor: str = 'system',
    limit: int = 100,
) -> dict[str, Any]:
    """Mark running jobs stale when their heartbeat is older than the cutoff."""
    now = timezone.now()
    cutoff = now - timezone.timedelta(seconds=max(1, int(max_age_seconds or ENGINE_JOB_STALE_AFTER_SECONDS)))
    candidates = (
        EngineJob.objects.filter(status='running')
        .filter(Q(heartbeat_at__lt=cutoff) | Q(heartbeat_at__isnull=True, started_at__lt=cutoff))
        .order_by('heartbeat_at', 'started_at', 'id')[: max(1, min(int(limit or 100), 1000))]
    )
    stale_jobs = []
    for job in candidates:
        reason = f'Heartbeat stale for more than {max_age_seconds} seconds.'
        EngineJob.objects.filter(pk=job.pk, status='running').update(
            status='stale',
            progress_percent=max(0, min(int(job.progress_percent or 0), 99)),
            message=reason,
            reason=reason[:180],
            heartbeat_at=now,
            finished_at=now,
        )
        job.refresh_from_db()
        append_job_audit(
            job,
            'stale',
            actor=actor,
            message=reason,
            meta={'cutoff': cutoff.isoformat(), 'max_age_seconds': max_age_seconds},
        )
        stale_jobs.append(_job_outcome(job))
    return {'marked': len(stale_jobs), 'jobs': stale_jobs, 'cutoff': cutoff.isoformat()}


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
    if job.engine_id == 'dolg-engine-router':
        return _run_engine_router_adapter(job)
    return _run_numpy_mna_adapter(job)


def _run_engine_router_adapter(job: EngineJob) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    """First real server-engine router: stable local route now, Docker routes later."""
    options = job.options or {}
    target_engine = str(
        options.get('target_engine') or options.get('delegate_engine') or 'dolg-numpy-mna'
    ).strip()
    pyspice_routes = {'pyspice', 'dolg-pyspice', 'pyspice-worker', 'dolg-ngspice', 'ngspice'}
    xyce_routes = {'xyce', 'dolg-xyce', 'xyce-worker'}
    if target_engine in pyspice_routes:
        _touch_job(job, progress_percent=45, message='Router delegated job to PySpice (ngspice) adapter.')
        result, warnings, artifacts = _run_pyspice_adapter(job)
        delegated = 'pyspice-ngspice'
    elif target_engine in xyce_routes:
        _touch_job(job, progress_percent=45, message='Router delegated job to Xyce adapter.')
        result, warnings, artifacts = _run_xyce_adapter(job)
        delegated = 'xyce'
    elif target_engine in {'', 'dolg-numpy-mna'}:
        _touch_job(job, progress_percent=45, message='Router delegated job to NumPy MNA adapter.')
        result, warnings, artifacts = _run_numpy_mna_adapter(job)
        delegated = 'dolg-numpy-mna'
    else:
        raise EngineJobExecutionError(
            f'dolg-engine-router route "{target_engine}" is not connected yet; use a dedicated worker.'
        )

    metrics = result.setdefault('metrics', {})
    metrics['router_engine'] = 'dolg-engine-router'
    metrics['delegated_engine'] = delegated
    result['engine_router'] = {
        'id': 'dolg-engine-router',
        'delegated_engine': delegated,
        'route_reason': 'local route: PySpice (ngspice) или NumPy MNA до Docker-воркеров',
    }
    artifacts = [
        *artifacts,
        {'kind': 'route', 'engine': 'dolg-engine-router', 'delegated_engine': delegated},
    ]
    return result, warnings, artifacts


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


def _run_pyspice_adapter(job: EngineJob) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    """In-process PySpice (ngspice) воркер. Тот же формат результата, что NumPy MNA, но
    физика — индустриальный ngspice. Любой анализ, который PySpice не вернул, падает на MNA."""
    scheme_data = _scheme_data(job)
    options = job.options or {}
    analysis = _normalize_analysis(job.analysis_type, options)

    if analysis == 'dc':
        result = _run_dc_pyspice(job, scheme_data)
    elif analysis == 'transient':
        result = _run_transient_pyspice(job, scheme_data, options)
    elif analysis == 'ac':
        result = _run_ac_pyspice(job, scheme_data, options)
    elif analysis == 'tolerance':
        result = _run_tolerance(job, scheme_data, options)  # Monte-Carlo — пока через NumPy
    else:
        raise EngineJobExecutionError(f'pyspice adapter does not support analysis "{analysis}" yet')

    return result, list(result.get('warnings') or []), list(result.get('artifacts') or [])


def _run_dc_pyspice(job: EngineJob, scheme_data: dict[str, Any]) -> dict[str, Any]:
    from . import pyspice_engine

    volts = pyspice_engine.solve_dc(scheme_data) if pyspice_engine.available() else None
    if volts is None:
        return _run_dc(job, scheme_data)  # фолбэк MNA

    voltages = _number_map(volts)
    circuit = scheme_to_circuit(scheme_data)
    return {
        'ok': True,
        'schema_version': 1,
        'engine': job.engine_id,
        'engine_name': job.engine_name,
        'analysis_type': 'dc',
        'nodes': [{'id': node, 'voltage_v': value, 'unit': 'V'} for node, value in voltages.items()],
        'branches': [],
        'waveforms': [],
        'metrics': {
            'node_count': int(circuit.get('n_nodes') or 0),
            'element_count': len(circuit.get('elements') or []),
            'backend': 'pyspice-ngspice',
        },
        'node_voltages': voltages,
        'currents_a': {},
        'warnings': [],
        'artifacts': [],
    }


def _run_transient_pyspice(
    job: EngineJob, scheme_data: dict[str, Any], options: dict[str, Any]
) -> dict[str, Any]:
    from . import pyspice_engine

    t_stop = _option_number(options, ('t_stop', 'stop_s', 'stop', 'tStop'), default=1e-3, unit='second')
    dt = _option_number(
        options,
        ('dt', 'step_s', 'step', 'time_step', 'timeStep'),
        default=max(t_stop / 200.0, 1e-9),
        unit='second',
    )
    max_points = _option_int(options, ('max_points', 'maxPoints'), default=1024, minimum=16, maximum=4096)

    transient = (
        pyspice_engine.solve_transient(scheme_data, t_stop=t_stop, dt=dt)
        if pyspice_engine.available()
        else None
    )
    if transient is None:
        return _run_transient(job, scheme_data, options)  # фолбэк MNA

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
    circuit = scheme_to_circuit(scheme_data)
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
            'backend': 'pyspice-ngspice',
        },
        'warnings': [],
        'artifacts': [],
    }


def _run_ac_pyspice(job: EngineJob, scheme_data: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    from . import pyspice_engine

    f_start = _option_number(options, ('f_start', 'start_hz', 'start', 'fStart'), default=1.0, unit='hertz')
    f_stop = _option_number(options, ('f_stop', 'stop_hz', 'stop', 'fStop'), default=1e6, unit='hertz')
    points = _option_int(options, ('points', 'samples'), default=60, minimum=4, maximum=512)
    if f_start <= 0:
        f_start = 1.0
    if f_stop <= f_start or points <= 1:
        freqs = [f_start]
    else:
        ratio = (f_stop / f_start) ** (1.0 / (points - 1))
        freqs = [f_start * ratio**i for i in range(points)]

    ac = pyspice_engine.solve_ac(scheme_data, freqs) if pyspice_engine.available() else None
    if ac is None:
        return _run_ac(job, scheme_data, options)  # фолбэк MNA

    return {
        'ok': True,
        'schema_version': 1,
        'engine': job.engine_id,
        'engine_name': job.engine_name,
        'analysis_type': 'ac',
        'nodes': _json_safe({str(net): data for net, data in (ac.get('nodes') or {}).items()}),
        'branches': [],
        'waveforms': [],
        'metrics': {
            'points': len(ac.get('freqs') or []),
            'backend': 'pyspice-ngspice',
        },
        'frequencies_hz': [float(value) for value in ac.get('freqs') or []],
        'warnings': [],
        'artifacts': [],
    }


def _run_xyce_adapter(job: EngineJob) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    """Xyce (Sandia industrial SPICE) воркер: shell-out в Xyce.exe. DC — через Xyce; transient/
    AC/tolerance пока через NumPy MNA (Xyce-парсеры этих режимов — на доработку)."""
    scheme_data = _scheme_data(job)
    options = job.options or {}
    analysis = _normalize_analysis(job.analysis_type, options)

    if analysis == 'dc':
        result = _run_dc_xyce(job, scheme_data)
    elif analysis == 'transient':
        result = _run_transient(job, scheme_data, options)
    elif analysis == 'ac':
        result = _run_ac(job, scheme_data, options)
    elif analysis == 'tolerance':
        result = _run_tolerance(job, scheme_data, options)
    else:
        raise EngineJobExecutionError(f'xyce adapter does not support analysis "{analysis}" yet')

    return result, list(result.get('warnings') or []), list(result.get('artifacts') or [])


def _run_dc_xyce(job: EngineJob, scheme_data: dict[str, Any]) -> dict[str, Any]:
    from . import xyce_engine

    volts = xyce_engine.solve_dc(scheme_data) if xyce_engine.available() else None
    if volts is None:
        return _run_dc(job, scheme_data)  # фолбэк MNA (Xyce не найден/не решил)

    voltages = _number_map(volts)
    circuit = scheme_to_circuit(scheme_data)
    return {
        'ok': True,
        'schema_version': 1,
        'engine': job.engine_id,
        'engine_name': job.engine_name,
        'analysis_type': 'dc',
        'nodes': [{'id': node, 'voltage_v': value, 'unit': 'V'} for node, value in voltages.items()],
        'branches': [],
        'waveforms': [],
        'metrics': {
            'node_count': int(circuit.get('n_nodes') or 0),
            'element_count': len(circuit.get('elements') or []),
            'backend': 'xyce',
        },
        'node_voltages': voltages,
        'currents_a': {},
        'warnings': [],
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
    normalized_result = normalize_engine_result(job, result, warnings=warnings, artifacts=artifacts)
    EngineJob.objects.filter(pk=job.pk).update(
        status='success',
        progress_percent=100,
        message=f'Completed by local worker in {elapsed_ms} ms.',
        reason='',
        result=_json_safe(normalized_result),
        result_contract_version=ENGINE_RESULT_CONTRACT['version'],
        warnings=[str(item) for item in normalized_result.get('warnings') or warnings],
        artifacts=_json_safe(normalized_result.get('artifacts') or artifacts),
        error='',
        heartbeat_at=timezone.now(),
        finished_at=timezone.now(),
    )
    job.refresh_from_db()
    append_job_audit(
        job,
        'success',
        actor=job.worker or 'worker',
        message=f'Completed in {elapsed_ms} ms.',
        meta={'elapsed_ms': elapsed_ms, 'contract_version': ENGINE_RESULT_CONTRACT['version']},
    )
    try:
        _persist_simulation_run(
            job, normalized_result, normalized_result.get('warnings') or warnings, elapsed_ms
        )
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
        'local_ai': _json_safe(result.get('local_ai') or {}),
    }


def _count_result_rows(value: Any) -> int:
    if isinstance(value, dict):
        return len(value)
    if isinstance(value, (list, tuple)):
        return len(value)
    return 0


def _finish_error(job: EngineJob, error: str, started: float) -> None:
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    reason = str(error or 'worker error')[:180]
    EngineJob.objects.filter(pk=job.pk).update(
        status='error',
        progress_percent=100,
        message=f'Worker failed after {elapsed_ms} ms.',
        reason=reason,
        error=error[:4000],
        heartbeat_at=timezone.now(),
        finished_at=timezone.now(),
    )
    job.refresh_from_db()
    append_job_audit(
        job,
        'error',
        actor=job.worker or 'worker',
        message=reason,
        meta={'elapsed_ms': elapsed_ms},
    )


def normalize_engine_result(
    job: EngineJob,
    result: dict[str, Any] | None,
    *,
    warnings: list[str] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Normalize adapter output for future Xyce/PySpice/GnuCap workers."""
    payload = _json_safe(result or {})
    if not isinstance(payload, dict):
        payload = {'raw': payload}
    payload['ok'] = bool(payload.get('ok', True))
    payload['schema_version'] = int(payload.get('schema_version') or ENGINE_RESULT_CONTRACT['version'])
    payload['contract'] = dict(ENGINE_RESULT_CONTRACT)
    payload['engine_job_id'] = job.id
    payload['engine'] = payload.get('engine') or job.engine_id
    payload['engine_name'] = payload.get('engine_name') or job.engine_name
    payload['analysis_type'] = payload.get('analysis_type') or job.analysis_type
    payload.setdefault('nodes', [])
    payload.setdefault('branches', [])
    payload.setdefault('waveforms', [])
    payload.setdefault('metrics', {})
    try:
        from .engine_ai import attach_engine_ai_result

        payload = attach_engine_ai_result(
            payload,
            scheme_data=job.scheme_data or {},
            engine_id=job.engine_id,
            analysis_type=job.analysis_type,
        )
    except Exception as exc:
        payload['local_ai'] = {
            'backend': 'local_ai',
            'available': False,
            'error': str(exc)[:180],
        }
    payload['warnings'] = [str(item) for item in (warnings or payload.get('warnings') or [])]
    payload['artifacts'] = _json_safe(artifacts or payload.get('artifacts') or [])
    return payload


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
    except TypeError, ValueError:
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
