"""Server-side numerical helpers for Pro simulation analytics.

The browser remains the main simulation surface. This module gives Django a
small, deterministic backend for FFT, Bode plots, tolerance sweeps and a
limited DC fallback when ngspice.wasm cannot handle a simple circuit.
"""

from __future__ import annotations

import csv
import math
from io import StringIO

import matplotlib

matplotlib.use('Agg')

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from scipy import fft, signal

from .project_review import normalize_component_type, parse_number

MAX_POINTS = 4096


def _as_float_array(values, *, limit=MAX_POINTS):
    arr = np.asarray(values or [], dtype=float)
    arr = arr[np.isfinite(arr)]
    if limit and arr.size > limit:
        arr = arr[:limit]
    return arr


def _svg_from_figure(fig):
    buffer = StringIO()
    fig.savefig(buffer, format='svg', bbox_inches='tight')
    return buffer.getvalue()


def _thin_points(x_values, y_values, limit=512):
    if len(x_values) <= limit:
        idx = np.arange(len(x_values))
    else:
        idx = np.linspace(0, len(x_values) - 1, limit).astype(int)
    return [
        {'x': float(x_values[i]), 'y': float(y_values[i])}
        for i in idx
        if math.isfinite(float(x_values[i])) and math.isfinite(float(y_values[i]))
    ]


def fft_spectrum(samples, sample_rate_hz, *, window='hann'):
    values = _as_float_array(samples)
    sample_rate = float(sample_rate_hz or 0)
    if values.size < 4:
        return {'ok': False, 'error': 'at_least_four_samples_required'}
    if sample_rate <= 0:
        return {'ok': False, 'error': 'sample_rate_hz_must_be_positive'}

    centered = values - np.mean(values)
    if window == 'hann':
        centered = centered * np.hanning(values.size)

    spectrum = fft.rfft(centered)
    freqs = fft.rfftfreq(values.size, d=1.0 / sample_rate)
    magnitudes = np.abs(spectrum) / max(values.size / 2, 1)

    if magnitudes.size > 1:
        peak_index = int(np.argmax(magnitudes[1:]) + 1)
    else:
        peak_index = 0

    fig = Figure(figsize=(6.4, 3.2))
    ax = fig.subplots()
    ax.plot(freqs, magnitudes, color='#00a7c7', linewidth=1.5)
    ax.set_title('FFT spectrum')
    ax.set_xlabel('Frequency, Hz')
    ax.set_ylabel('Magnitude')
    ax.grid(True, alpha=0.25)

    return {
        'ok': True,
        'sample_count': int(values.size),
        'sample_rate_hz': sample_rate,
        'peak_frequency_hz': float(freqs[peak_index]),
        'peak_magnitude': float(magnitudes[peak_index]),
        'points': _thin_points(freqs, magnitudes),
        'svg': _svg_from_figure(fig),
    }


def _bode_from_transfer_function(config):
    numerator = _as_float_array(config.get('numerator'), limit=32)
    denominator = _as_float_array(config.get('denominator'), limit=32)
    if numerator.size == 0 or denominator.size == 0:
        raise ValueError('transfer function requires numerator and denominator')

    frequencies = _as_float_array(config.get('frequencies_hz'), limit=MAX_POINTS)
    if frequencies.size == 0:
        start = float(config.get('start_hz') or 10)
        stop = float(config.get('stop_hz') or 100000)
        points = int(config.get('points') or 160)
        frequencies = np.logspace(math.log10(start), math.log10(stop), points)

    system = signal.TransferFunction(numerator, denominator)
    _, magnitude_db, phase_deg = signal.bode(system, w=2 * np.pi * frequencies)
    return frequencies, magnitude_db, phase_deg


def _bode_from_rc_lowpass(config):
    resistance = parse_number(config.get('resistance_ohm') or config.get('r_ohm'), None)
    capacitance = parse_number(config.get('capacitance_f') or config.get('c_f'), None)
    if not resistance or not capacitance:
        raise ValueError('rc_lowpass requires resistance_ohm and capacitance_f')
    start = float(config.get('start_hz') or 1)
    stop = float(config.get('stop_hz') or 100000)
    points = int(config.get('points') or 160)
    frequencies = np.logspace(math.log10(start), math.log10(stop), points)
    omega = 2 * np.pi * frequencies
    response = 1.0 / (1.0 + 1j * omega * resistance * capacitance)
    magnitude_db = 20 * np.log10(np.abs(response))
    phase_deg = np.angle(response, deg=True)
    return frequencies, magnitude_db, phase_deg


def _bode_from_points(config):
    frequencies = _as_float_array(config.get('frequencies_hz'), limit=MAX_POINTS)
    magnitude_db = _as_float_array(
        config.get('magnitude_db') or config.get('magnitudes_db'), limit=MAX_POINTS
    )
    phase_deg = _as_float_array(config.get('phase_deg') or config.get('phases_deg'), limit=MAX_POINTS)

    if frequencies.size and magnitude_db.size:
        length = min(frequencies.size, magnitude_db.size)
        frequencies = frequencies[:length]
        magnitude_db = magnitude_db[:length]
        if phase_deg.size:
            phase_deg = phase_deg[:length]
        else:
            phase_deg = np.zeros(length)
        return frequencies, magnitude_db, phase_deg

    real = _as_float_array(config.get('real'), limit=MAX_POINTS)
    imag = _as_float_array(config.get('imag'), limit=MAX_POINTS)
    if frequencies.size and real.size and imag.size:
        length = min(frequencies.size, real.size, imag.size)
        response = real[:length] + 1j * imag[:length]
        return (
            frequencies[:length],
            20 * np.log10(np.maximum(np.abs(response), 1e-18)),
            np.angle(response, deg=True),
        )
    raise ValueError('bode payload requires AC points, rc_lowpass or transfer_function')


def bode_plot(config):
    config = config or {}
    try:
        kind = (config.get('kind') or '').strip().lower()
        if kind == 'transfer_function':
            frequencies, magnitude_db, phase_deg = _bode_from_transfer_function(config)
        elif kind in {'rc_lowpass', 'rc'}:
            frequencies, magnitude_db, phase_deg = _bode_from_rc_lowpass(config)
        else:
            frequencies, magnitude_db, phase_deg = _bode_from_points(config)
    except (TypeError, ValueError) as exc:
        return {'ok': False, 'error': str(exc)}

    if frequencies.size < 2:
        return {'ok': False, 'error': 'at_least_two_frequency_points_required'}

    cutoff = None
    max_db = float(np.max(magnitude_db))
    target = max_db - 3.0
    below = np.where(magnitude_db <= target)[0]
    if below.size:
        cutoff = float(frequencies[int(below[0])])

    fig = Figure(figsize=(6.4, 5.2))
    ax1, ax2 = fig.subplots(2, 1, sharex=True)
    ax1.semilogx(frequencies, magnitude_db, color='#00a7c7', linewidth=1.5)
    ax1.set_ylabel('Magnitude, dB')
    ax1.grid(True, which='both', alpha=0.25)
    ax2.semilogx(frequencies, phase_deg, color='#ff7a30', linewidth=1.5)
    ax2.set_xlabel('Frequency, Hz')
    ax2.set_ylabel('Phase, deg')
    ax2.grid(True, which='both', alpha=0.25)
    fig.suptitle('Bode plot')

    return {
        'ok': True,
        'points_count': int(frequencies.size),
        'cutoff_frequency_hz': cutoff,
        'magnitude_points': _thin_points(frequencies, magnitude_db),
        'phase_points': _thin_points(frequencies, phase_deg),
        'svg': _svg_from_figure(fig),
    }


def _sample_nominal(rng, nominal, tolerance_percent, count, distribution):
    nominal = float(nominal)
    tolerance = abs(float(tolerance_percent or 0)) / 100.0
    if distribution == 'normal':
        # Treat tolerance as roughly +/-3 sigma.
        return rng.normal(nominal, max(abs(nominal) * tolerance / 3.0, 1e-18), count)
    return rng.uniform(nominal * (1 - tolerance), nominal * (1 + tolerance), count)


def monte_carlo_tolerance(config):
    config = config or {}
    kind = (config.get('kind') or 'voltage_divider').strip().lower()
    sample_count = max(16, min(int(config.get('samples') or 1000), 20000))
    rng = np.random.default_rng(int(config.get('seed') or 42))
    distribution = (config.get('distribution') or 'normal').strip().lower()

    try:
        if kind == 'voltage_divider':
            vin = float(config.get('vin') or 5)
            r1 = _sample_nominal(
                rng,
                parse_number(config.get('r1_ohm'), 1000),
                config.get('r1_tolerance_percent', 5),
                sample_count,
                distribution,
            )
            r2 = _sample_nominal(
                rng,
                parse_number(config.get('r2_ohm'), 1000),
                config.get('r2_tolerance_percent', 5),
                sample_count,
                distribution,
            )
            values = vin * r2 / np.maximum(r1 + r2, 1e-18)
            metric = 'vout'
            unit = 'V'
        elif kind == 'rc_cutoff':
            r = _sample_nominal(
                rng,
                parse_number(config.get('resistance_ohm'), 10000),
                config.get('r_tolerance_percent', 5),
                sample_count,
                distribution,
            )
            c = _sample_nominal(
                rng,
                parse_number(config.get('capacitance_f'), 1e-7),
                config.get('c_tolerance_percent', 10),
                sample_count,
                distribution,
            )
            values = 1.0 / (2 * np.pi * np.maximum(r * c, 1e-24))
            metric = 'cutoff_frequency'
            unit = 'Hz'
        else:
            return {'ok': False, 'error': f'unsupported monte carlo kind: {kind}'}
    except (TypeError, ValueError) as exc:
        return {'ok': False, 'error': str(exc)}

    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {'ok': False, 'error': 'no finite monte carlo samples'}

    fig = Figure(figsize=(6.4, 3.2))
    ax = fig.subplots()
    ax.hist(finite, bins=min(48, max(8, int(math.sqrt(finite.size)))), color='#00a7c7', alpha=0.82)
    ax.set_title(f'Monte Carlo: {metric}')
    ax.set_xlabel(unit)
    ax.set_ylabel('Count')
    ax.grid(True, alpha=0.2)

    return {
        'ok': True,
        'kind': kind,
        'metric': metric,
        'unit': unit,
        'samples': int(finite.size),
        'mean': float(np.mean(finite)),
        'std': float(np.std(finite)),
        'min': float(np.min(finite)),
        'max': float(np.max(finite)),
        'p05': float(np.percentile(finite, 5)),
        'p50': float(np.percentile(finite, 50)),
        'p95': float(np.percentile(finite, 95)),
        'svg': _svg_from_figure(fig),
    }


def _safe_db(value):
    value = float(value)
    if value <= 0 or not math.isfinite(value):
        return None
    return float(20 * math.log10(value))


def signal_quality(samples, sample_rate_hz, *, fundamental_hz=None, max_harmonics=5, window='hann'):
    values = _as_float_array(samples)
    sample_rate = float(sample_rate_hz or 0)
    if values.size < 8:
        return {'ok': False, 'error': 'at_least_eight_samples_required'}
    if sample_rate <= 0:
        return {'ok': False, 'error': 'sample_rate_hz_must_be_positive'}

    dc_offset = float(np.mean(values))
    ac_values = values - dc_offset
    if window == 'hann':
        win = np.hanning(values.size)
    else:
        win = np.ones(values.size)
    coherent_gain = max(float(np.mean(win)), 1e-12)

    spectrum = fft.rfft(ac_values * win)
    freqs = fft.rfftfreq(values.size, d=1.0 / sample_rate)
    amplitudes = np.abs(spectrum) / max(values.size * coherent_gain / 2.0, 1e-12)
    amplitudes[0] = 0

    if fundamental_hz:
        fundamental = float(fundamental_hz)
        if fundamental <= 0:
            return {'ok': False, 'error': 'fundamental_hz_must_be_positive'}
        fundamental_index = int(np.argmin(np.abs(freqs - fundamental)))
    else:
        fundamental_index = int(np.argmax(amplitudes[1:]) + 1) if amplitudes.size > 1 else 0
        fundamental = float(freqs[fundamental_index])

    if fundamental_index <= 0 or fundamental <= 0:
        return {'ok': False, 'error': 'fundamental_not_found'}

    harmonic_rows = []
    excluded = np.zeros(amplitudes.size, dtype=bool)
    excluded[0] = True
    max_harmonics = max(1, min(int(max_harmonics or 5), 12))
    nyquist = sample_rate / 2.0
    for order in range(1, max_harmonics + 1):
        target = fundamental * order
        if target > nyquist:
            break
        idx = int(np.argmin(np.abs(freqs - target)))
        lo = max(0, idx - 1)
        hi = min(amplitudes.size, idx + 2)
        excluded[lo:hi] = True
        harmonic_rows.append(
            {
                'order': order,
                'frequency_hz': float(freqs[idx]),
                'magnitude': float(amplitudes[idx]),
                'db_relative': 0.0,
            }
        )

    fundamental_mag = harmonic_rows[0]['magnitude'] if harmonic_rows else 0.0
    if fundamental_mag <= 0:
        return {'ok': False, 'error': 'fundamental_magnitude_is_zero'}

    harmonic_power = sum(item['magnitude'] ** 2 for item in harmonic_rows[1:])
    thd_percent = float(math.sqrt(harmonic_power) / fundamental_mag * 100.0)
    for item in harmonic_rows:
        item['db_relative'] = _safe_db(item['magnitude'] / fundamental_mag)

    noise_power = float(np.sum(amplitudes[~excluded] ** 2))
    distortion_noise = harmonic_power + noise_power
    sinad_db = None
    enob = None
    if distortion_noise > 0:
        sinad_db = float(20 * math.log10(fundamental_mag / math.sqrt(distortion_noise)))
        enob = float((sinad_db - 1.76) / 6.02)

    rms = float(np.sqrt(np.mean(values**2)))
    ac_rms = float(np.sqrt(np.mean(ac_values**2)))
    peak_to_peak = float(np.max(values) - np.min(values))
    crest_factor = float(np.max(np.abs(values)) / rms) if rms > 0 else None

    if thd_percent < 1 and (enob is None or enob >= 9):
        verdict = 'excellent'
        feedback = 'Clean signal: low harmonic distortion and healthy numeric resolution.'
    elif thd_percent < 5:
        verdict = 'ok'
        feedback = 'Usable signal: harmonics are visible but not dominant.'
    elif thd_percent < 15:
        verdict = 'risk'
        feedback = 'Distortion is noticeable; check clipping, bias point or load.'
    else:
        verdict = 'distorted'
        feedback = 'High harmonic content; waveform is likely clipped or nonlinear.'

    time_axis = np.arange(values.size) / sample_rate
    plot_limit = min(values.size, 512)
    fig = Figure(figsize=(6.4, 5.0))
    ax1, ax2 = fig.subplots(2, 1)
    ax1.plot(time_axis[:plot_limit], values[:plot_limit], color='#00a7c7', linewidth=1.2)
    ax1.set_title('Signal quality')
    ax1.set_xlabel('Time, s')
    ax1.set_ylabel('Amplitude')
    ax1.grid(True, alpha=0.25)
    ax2.bar(
        [item['order'] for item in harmonic_rows],
        [item['magnitude'] for item in harmonic_rows],
        color='#ff7a30',
        alpha=0.82,
    )
    ax2.set_xlabel('Harmonic')
    ax2.set_ylabel('Magnitude')
    ax2.grid(True, axis='y', alpha=0.25)

    return {
        'ok': True,
        'sample_count': int(values.size),
        'sample_rate_hz': sample_rate,
        'fundamental_frequency_hz': fundamental,
        'dc_offset': dc_offset,
        'rms': rms,
        'ac_rms': ac_rms,
        'peak_to_peak': peak_to_peak,
        'crest_factor': crest_factor,
        'thd_percent': thd_percent,
        'sinad_db': sinad_db,
        'enob': enob,
        'verdict': verdict,
        'feedback': feedback,
        'harmonics': harmonic_rows,
        'svg': _svg_from_figure(fig),
    }


def _series_from_payload(payload):
    payload = payload or {}
    result = payload.get('result') if isinstance(payload.get('result'), dict) else payload
    points = result.get('points') or result.get('samples') or []
    if isinstance(points, list) and points and isinstance(points[0], dict):
        x_values = _as_float_array([item.get('x') for item in points])
        y_values = _as_float_array([item.get('y') for item in points])
        length = min(x_values.size, y_values.size)
        return x_values[:length], y_values[:length]

    values = (
        payload.get('values') or payload.get('samples') or result.get('values') or result.get('samples') or []
    )
    y_values = _as_float_array(values)
    if y_values.size == 0:
        return np.asarray([]), np.asarray([])
    times = payload.get('times') or result.get('times') or []
    x_values = _as_float_array(times)
    if x_values.size != y_values.size:
        sample_rate = float(
            payload.get('sample_rate_hz') or payload.get('sampleRateHz') or result.get('sample_rate_hz') or 0
        )
        if sample_rate > 0:
            x_values = np.arange(y_values.size) / sample_rate
        else:
            x_values = np.arange(y_values.size)
    return x_values[: y_values.size], y_values


def _nearest_marker(x_values, y_values, marker):
    if x_values.size == 0 or y_values.size == 0:
        return None
    x_target = float(marker.get('x'))
    idx = int(np.argmin(np.abs(x_values - x_target)))
    return {
        'label': marker.get('label') or f'x={x_target:g}',
        'x': float(x_values[idx]),
        'y': float(y_values[idx]),
        'index': idx,
    }


def _formula_value(expression, variables):
    try:
        import sympy as sp

        allowed = {
            key: float(value) for key, value in (variables or {}).items() if isinstance(value, (int, float))
        }
        symbols = {key: sp.Symbol(key) for key in allowed}
        expr = sp.sympify(str(expression), locals=symbols)
        value = float(expr.evalf(subs=allowed))
        if math.isfinite(value):
            return {'ok': True, 'expression': str(expression), 'value': value}
    except Exception as exc:
        return {'ok': False, 'expression': str(expression), 'error': str(exc)}
    return {'ok': False, 'expression': str(expression), 'error': 'formula_not_finite'}


def postprocess_simulation(payload):
    """Qucs-like postprocessing for saved or inline simulation data.

    The browser still owns the interactive plot. This helper turns result data
    into measurements, markers, user formulas and optional plots that can be
    stored in the project session.
    """
    payload = payload or {}
    x_values, y_values = _series_from_payload(payload)
    metrics = {}
    measurements = []
    plots = {}
    markers = []
    formula_results = []
    unit = payload.get('unit') or payload.get('y_unit') or ''

    if y_values.size:
        metrics.update(
            {
                'average': float(np.mean(y_values)),
                'rms': float(np.sqrt(np.mean(y_values**2))),
                'peak_to_peak': float(np.max(y_values) - np.min(y_values)),
                'minimum': float(np.min(y_values)),
                'maximum': float(np.max(y_values)),
            }
        )
        measurements.extend(
            [
                {'metric': 'average', 'label': 'Среднее значение', 'value': metrics['average'], 'unit': unit},
                {'metric': 'rms', 'label': 'RMS', 'value': metrics['rms'], 'unit': unit},
                {
                    'metric': 'peak_to_peak',
                    'label': 'Размах peak-to-peak',
                    'value': metrics['peak_to_peak'],
                    'unit': unit,
                },
            ]
        )

    voltage = parse_number(payload.get('voltage') or payload.get('voltage_v'), None)
    current = parse_number(payload.get('current') or payload.get('current_a'), None)
    if voltage is not None and current is not None:
        metrics['power_w'] = float(voltage * current)
        measurements.append(
            {
                'metric': 'component_power',
                'label': 'Мощность элемента',
                'value': metrics['power_w'],
                'unit': 'W',
            }
        )
        if abs(current) > 1e-18:
            metrics['resistance_ohm'] = float(voltage / current)
            measurements.append(
                {
                    'metric': 'dynamic_resistance',
                    'label': 'V/I',
                    'value': metrics['resistance_ohm'],
                    'unit': 'Ohm',
                }
            )

    for marker in payload.get('markers') or []:
        if isinstance(marker, dict) and marker.get('x') is not None:
            found = _nearest_marker(x_values, y_values, marker)
            if found:
                markers.append(found)

    variables = dict(payload.get('variables') or {})
    variables.update({key: value for key, value in metrics.items() if isinstance(value, (int, float))})
    if voltage is not None:
        variables.setdefault('v', voltage)
        variables.setdefault('voltage', voltage)
    if current is not None:
        variables.setdefault('i', current)
        variables.setdefault('current', current)
    for expression in payload.get('formulas') or []:
        formula_results.append(_formula_value(expression, variables))

    operations = set(payload.get('operations') or [])
    sample_rate = float(payload.get('sample_rate_hz') or payload.get('sampleRateHz') or 0)
    if ('fft' in operations or payload.get('fft')) and y_values.size and sample_rate > 0:
        plots['fft'] = fft_spectrum(y_values.tolist(), sample_rate, window=payload.get('window', 'hann'))
    if 'bode' in operations or payload.get('bode'):
        bode_payload = payload.get('bode') if isinstance(payload.get('bode'), dict) else payload
        plots['bode'] = bode_plot(bode_payload)

    return {
        'ok': True,
        'points_count': int(y_values.size),
        'metrics': metrics,
        'measurements': measurements,
        'markers': markers,
        'formulas': formula_results,
        'plots': plots,
    }


def simulation_result_to_csv(result):
    result = result or {}
    output = StringIO()
    writer = csv.writer(output)
    points = result.get('points')
    if isinstance(points, list) and points:
        writer.writerow(['x', 'y'])
        for item in points:
            if isinstance(item, dict):
                writer.writerow([item.get('x', ''), item.get('y', '')])
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                writer.writerow([item[0], item[1]])
        return output.getvalue()

    node_voltages = result.get('nodeVoltages') or result.get('node_voltages')
    if isinstance(node_voltages, dict) and node_voltages:
        writer.writerow(['node', 'voltage'])
        for node, value in node_voltages.items():
            writer.writerow([node, value])
        return output.getvalue()

    metrics = result.get('metrics')
    if isinstance(metrics, dict) and metrics:
        writer.writerow(['metric', 'value'])
        for key, value in metrics.items():
            writer.writerow([key, value])
        return output.getvalue()

    writer.writerow(['key', 'value'])
    for key, value in result.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            writer.writerow([key, value])
    return output.getvalue()


def _sweep_axis(config, default_start, default_stop):
    points = max(8, min(int(config.get('points') or 80), 512))
    start = parse_number(config.get('start'), default_start)
    stop = parse_number(config.get('stop'), default_stop)
    if start is None or stop is None or start == stop:
        raise ValueError('sweep requires different numeric start and stop')
    scale = (config.get('scale') or 'linear').strip().lower()
    if scale == 'log':
        if start <= 0 or stop <= 0:
            raise ValueError('log sweep requires positive start and stop')
        values = np.logspace(math.log10(start), math.log10(stop), points)
    else:
        values = np.linspace(start, stop, points)
        scale = 'linear'
    return values, scale


def parameter_sweep(config):
    config = config or {}
    kind = (config.get('kind') or 'voltage_divider').strip().lower()
    parameter = (config.get('parameter') or '').strip().lower()
    metric = (config.get('metric') or '').strip().lower()

    try:
        if kind == 'voltage_divider':
            vin = parse_number(config.get('vin'), 5.0)
            r1 = parse_number(config.get('r1_ohm'), 1000.0)
            r2 = parse_number(config.get('r2_ohm'), 1000.0)
            parameter = parameter or 'r2_ohm'
            defaults = {
                'vin': (max(vin * 0.5, 1e-9), max(vin * 1.5, 1e-9)),
                'r1_ohm': (max(r1 * 0.25, 1e-9), max(r1 * 4, 1e-9)),
                'r2_ohm': (max(r2 * 0.25, 1e-9), max(r2 * 4, 1e-9)),
            }
            if parameter not in defaults:
                raise ValueError('voltage_divider supports vin, r1_ohm or r2_ohm sweep')
            x_values, scale = _sweep_axis(config, *defaults[parameter])
            y_values = []
            for x in x_values:
                cur_vin, cur_r1, cur_r2 = vin, r1, r2
                if parameter == 'vin':
                    cur_vin = x
                elif parameter == 'r1_ohm':
                    cur_r1 = x
                else:
                    cur_r2 = x
                y_values.append(cur_vin * cur_r2 / max(cur_r1 + cur_r2, 1e-18))
            metric = 'vout'
            unit = 'V'
            x_unit = 'V' if parameter == 'vin' else 'Ohm'

        elif kind == 'rc_cutoff':
            resistance = parse_number(config.get('resistance_ohm'), 10000.0)
            capacitance = parse_number(config.get('capacitance_f'), 1e-7)
            parameter = parameter or 'resistance_ohm'
            defaults = {
                'resistance_ohm': (max(resistance * 0.1, 1e-9), max(resistance * 10, 1e-9)),
                'capacitance_f': (max(capacitance * 0.1, 1e-15), max(capacitance * 10, 1e-15)),
            }
            if parameter not in defaults:
                raise ValueError('rc_cutoff supports resistance_ohm or capacitance_f sweep')
            x_values, scale = _sweep_axis(config, *defaults[parameter])
            y_values = []
            for x in x_values:
                r = x if parameter == 'resistance_ohm' else resistance
                c = x if parameter == 'capacitance_f' else capacitance
                y_values.append(1.0 / (2 * np.pi * max(r * c, 1e-24)))
            metric = 'cutoff_frequency'
            unit = 'Hz'
            x_unit = 'Ohm' if parameter == 'resistance_ohm' else 'F'

        elif kind == 'ne555_astable':
            r1 = parse_number(config.get('r1_ohm'), 1000.0)
            r2 = parse_number(config.get('r2_ohm'), 10000.0)
            capacitance = parse_number(config.get('capacitance_f'), 1e-7)
            parameter = parameter or 'r2_ohm'
            metric = metric or 'frequency_hz'
            defaults = {
                'r1_ohm': (max(r1 * 0.25, 1e-9), max(r1 * 4, 1e-9)),
                'r2_ohm': (max(r2 * 0.25, 1e-9), max(r2 * 4, 1e-9)),
                'capacitance_f': (max(capacitance * 0.1, 1e-15), max(capacitance * 10, 1e-15)),
            }
            if parameter not in defaults:
                raise ValueError('ne555_astable supports r1_ohm, r2_ohm or capacitance_f sweep')
            if metric not in {'frequency_hz', 'duty_cycle_percent'}:
                raise ValueError('ne555_astable metric must be frequency_hz or duty_cycle_percent')
            x_values, scale = _sweep_axis(config, *defaults[parameter])
            y_values = []
            for x in x_values:
                cur_r1 = x if parameter == 'r1_ohm' else r1
                cur_r2 = x if parameter == 'r2_ohm' else r2
                cur_c = x if parameter == 'capacitance_f' else capacitance
                if metric == 'frequency_hz':
                    y_values.append(1.44 / max((cur_r1 + 2 * cur_r2) * cur_c, 1e-24))
                else:
                    y_values.append((cur_r1 + cur_r2) / max(cur_r1 + 2 * cur_r2, 1e-18) * 100.0)
            unit = 'Hz' if metric == 'frequency_hz' else '%'
            x_unit = 'F' if parameter == 'capacitance_f' else 'Ohm'

        elif kind == 'led_resistor':
            vin = parse_number(config.get('vin'), 5.0)
            vf = parse_number(config.get('vf'), 2.0)
            resistance = parse_number(config.get('resistance_ohm'), 330.0)
            parameter = parameter or 'resistance_ohm'
            metric = metric or 'current_ma'
            defaults = {
                'vin': (max(vin * 0.5, vf + 1e-9), max(vin * 1.5, vf + 1e-9)),
                'vf': (max(vf * 0.5, 0), max(min(vf * 1.5, vin - 1e-9), 1e-9)),
                'resistance_ohm': (max(resistance * 0.25, 1e-9), max(resistance * 4, 1e-9)),
            }
            if parameter not in defaults:
                raise ValueError('led_resistor supports vin, vf or resistance_ohm sweep')
            if metric not in {'current_ma', 'resistor_power_w'}:
                raise ValueError('led_resistor metric must be current_ma or resistor_power_w')
            x_values, scale = _sweep_axis(config, *defaults[parameter])
            y_values = []
            for x in x_values:
                cur_vin = x if parameter == 'vin' else vin
                cur_vf = x if parameter == 'vf' else vf
                cur_r = x if parameter == 'resistance_ohm' else resistance
                current_a = max(cur_vin - cur_vf, 0) / max(cur_r, 1e-18)
                y_values.append(current_a * 1000.0 if metric == 'current_ma' else current_a**2 * cur_r)
            unit = 'mA' if metric == 'current_ma' else 'W'
            x_unit = 'V' if parameter in {'vin', 'vf'} else 'Ohm'

        else:
            return {'ok': False, 'error': f'unsupported sweep kind: {kind}'}
    except (TypeError, ValueError) as exc:
        return {'ok': False, 'error': str(exc)}

    y_values = np.asarray(y_values, dtype=float)
    finite_mask = np.isfinite(x_values) & np.isfinite(y_values)
    x_values = x_values[finite_mask]
    y_values = y_values[finite_mask]
    if x_values.size < 2:
        return {'ok': False, 'error': 'not_enough_finite_sweep_points'}

    target_min = parse_number(config.get('target_min'), None)
    target_max = parse_number(config.get('target_max'), None)
    in_target = np.ones(y_values.size, dtype=bool)
    if target_min is not None:
        in_target &= y_values >= target_min
    if target_max is not None:
        in_target &= y_values <= target_max

    target_fraction = (
        float(np.mean(in_target)) if (target_min is not None or target_max is not None) else None
    )
    if target_fraction is None:
        verdict = 'explore'
        feedback = 'Sweep is ready for visual what-if comparison.'
    elif target_fraction >= 0.5:
        verdict = 'ok'
        feedback = 'A wide part of the sweep is inside the target range.'
    elif target_fraction > 0:
        verdict = 'narrow'
        feedback = 'Target is reachable, but the acceptable nominal range is narrow.'
    else:
        verdict = 'miss'
        feedback = 'Target range is not reached in this sweep.'

    best_index = None
    if target_min is not None or target_max is not None:
        target_center = np.mean([value for value in (target_min, target_max) if value is not None])
        best_index = int(np.argmin(np.abs(y_values - target_center)))

    fig = Figure(figsize=(6.4, 3.4))
    ax = fig.subplots()
    if scale == 'log':
        ax.semilogx(x_values, y_values, color='#00a7c7', linewidth=1.6)
    else:
        ax.plot(x_values, y_values, color='#00a7c7', linewidth=1.6)
    if target_min is not None:
        ax.axhline(target_min, color='#19c37d', linewidth=1, linestyle='--')
    if target_max is not None:
        ax.axhline(target_max, color='#ff7a30', linewidth=1, linestyle='--')
    ax.set_title(f'Sweep: {kind} / {metric}')
    ax.set_xlabel(f'{parameter}, {x_unit}')
    ax.set_ylabel(f'{metric}, {unit}')
    ax.grid(True, which='both', alpha=0.25)

    return {
        'ok': True,
        'kind': kind,
        'parameter': parameter,
        'parameter_unit': x_unit,
        'metric': metric,
        'unit': unit,
        'scale': scale,
        'points_count': int(x_values.size),
        'min': float(np.min(y_values)),
        'max': float(np.max(y_values)),
        'mean': float(np.mean(y_values)),
        'target_fraction': target_fraction,
        'best_point': (
            {'x': float(x_values[best_index]), 'y': float(y_values[best_index])}
            if best_index is not None
            else None
        ),
        'verdict': verdict,
        'feedback': feedback,
        'points': _thin_points(x_values, y_values),
        'svg': _svg_from_figure(fig),
    }


class _UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, item):
        self.parent.setdefault(item, item)
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, left, right):
        self.parent[self.find(right)] = self.find(left)


def _endpoint_id(endpoint):
    return (str(endpoint.get('compId')), str(endpoint.get('portId') or 'a'))


def server_side_dc_fallback(scheme_data):
    components = [c for c in (scheme_data or {}).get('components', []) if isinstance(c, dict)]
    connections = [c for c in (scheme_data or {}).get('connections', []) if isinstance(c, dict)]
    uf = _UnionFind()

    for conn in connections:
        left = conn.get('from') or {}
        right = conn.get('to') or {}
        if left.get('compId') is not None and right.get('compId') is not None:
            uf.union(_endpoint_id(left), _endpoint_id(right))

    ground_roots = set()
    for comp in components:
        if normalize_component_type(comp.get('type')) == 'ground':
            comp_id = str(comp.get('id'))
            for port in ('a', '1', '0', 'gnd'):
                ground_roots.add(uf.find((comp_id, port)))

    resistors = []
    sources = []
    warnings = []
    for comp in components:
        comp_id = str(comp.get('id'))
        ctype = normalize_component_type(comp.get('type'))
        ports = [endpoint for endpoint in uf.parent if endpoint[0] == comp_id]
        roots = []
        for endpoint in ports:
            root = uf.find(endpoint)
            if root not in roots:
                roots.append(root)
        if len(roots) < 2:
            continue
        if ctype == 'resistor':
            resistance = parse_number(comp.get('resistance') or comp.get('value'), None)
            if resistance and resistance > 0:
                resistors.append((comp, roots[0], roots[1], resistance))
        elif ctype == 'battery':
            voltage = parse_number(comp.get('voltage') or comp.get('value'), 5)
            sources.append((comp, roots[0], roots[1], voltage))

    if not ground_roots:
        return {'ok': False, 'error': 'ground_required_for_dc_fallback'}
    if not sources:
        return {'ok': False, 'error': 'voltage_source_required_for_dc_fallback'}
    if not resistors:
        return {'ok': False, 'error': 'resistor_network_required_for_dc_fallback'}

    all_roots = set()
    for _, n1, n2, _ in resistors + sources:
        all_roots.add(n1)
        all_roots.add(n2)
    non_ground = sorted(root for root in all_roots if root not in ground_roots)
    node_index = {root: idx for idx, root in enumerate(non_ground)}
    size = len(non_ground) + len(sources)
    matrix = np.zeros((size, size), dtype=float)
    vector = np.zeros(size, dtype=float)

    def idx(root):
        return node_index.get(root)

    for _, n1, n2, resistance in resistors:
        conductance = 1.0 / resistance
        i = idx(n1)
        j = idx(n2)
        if i is not None:
            matrix[i, i] += conductance
        if j is not None:
            matrix[j, j] += conductance
        if i is not None and j is not None:
            matrix[i, j] -= conductance
            matrix[j, i] -= conductance

    source_offset = len(non_ground)
    for source_no, (_, n_plus, n_minus, voltage) in enumerate(sources):
        row = source_offset + source_no
        i = idx(n_plus)
        j = idx(n_minus)
        if i is not None:
            matrix[i, row] += 1
            matrix[row, i] += 1
        if j is not None:
            matrix[j, row] -= 1
            matrix[row, j] -= 1
        vector[row] = voltage

    try:
        solution = np.linalg.solve(matrix, vector)
    except np.linalg.LinAlgError as exc:
        return {'ok': False, 'error': f'dc_fallback_matrix_error: {exc}'}

    voltages_by_root = {root: 0.0 for root in ground_roots}
    for root, i in node_index.items():
        voltages_by_root[root] = float(solution[i])

    node_voltages = {}
    for comp in components:
        comp_id = str(comp.get('id'))
        label = str(comp.get('label') or comp_id)
        if normalize_component_type(comp.get('type')) in {'node', 'ground'}:
            roots = [uf.find(endpoint) for endpoint in uf.parent if endpoint[0] == comp_id]
            if roots:
                node_voltages[label] = float(voltages_by_root.get(roots[0], 0.0))

    if not node_voltages:
        warnings.append('No explicit node labels were found; returning internal roots.')
        node_voltages = {str(root): float(value) for root, value in voltages_by_root.items()}

    return {
        'ok': True,
        'type': 'dc',
        'engine': 'server_side_numpy_mna',
        'nodeVoltages': node_voltages,
        'warnings': warnings,
        'matrix_size': size,
    }


def simulation_run_stats(runs, *, limit=5):
    records = []
    for run in runs or []:
        records.append(
            {
                'id': getattr(run, 'id', None),
                'analysis_type': getattr(run, 'analysis_type', 'unknown') or 'unknown',
                'engine': getattr(run, 'engine', '') or '',
                'elapsed_ms': int(getattr(run, 'elapsed_ms', 0) or 0),
                'status': getattr(run, 'status', '') or '',
                'created': getattr(run, 'created_at', None).isoformat()
                if getattr(run, 'created_at', None)
                else '',
            }
        )
    if not records:
        return {
            'ok': True,
            'runs_count': 0,
            'slowest_runs': [],
            'by_analysis_type': [],
            'mean_elapsed_ms': 0,
        }

    frame = pd.DataFrame.from_records(records)
    slowest = frame.sort_values('elapsed_ms', ascending=False).head(limit).to_dict(orient='records')
    grouped = (
        frame.groupby('analysis_type', as_index=False)
        .agg(
            runs=('id', 'count'), mean_elapsed_ms=('elapsed_ms', 'mean'), max_elapsed_ms=('elapsed_ms', 'max')
        )
        .sort_values('max_elapsed_ms', ascending=False)
        .to_dict(orient='records')
    )
    return {
        'ok': True,
        'runs_count': len(frame),
        'slowest_runs': slowest,
        'by_analysis_type': grouped,
        'mean_elapsed_ms': float(frame['elapsed_ms'].mean()),
    }
