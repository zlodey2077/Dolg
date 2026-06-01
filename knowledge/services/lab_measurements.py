"""Shared measurement helpers for the lab, learning grader and project review."""

from .engineering_lab import calculate_lab, evaluate_measurement, extract_measurement, lab_expected_value


def compare_lab_measurement(config, simulation_result):
    """Compare one lab-calculated expected value with one simulation metric."""
    config = config or {}
    lab_config = config.get('lab') or config
    metric = config.get('metric') or config.get('output')
    if not metric:
        return {
            'correct': False,
            'status': 'risk',
            'status_label': 'risk',
            'feedback': 'measurement metric is not configured',
        }
    expected = lab_expected_value(lab_config)
    rubric = {
        'expected_value': expected,
        'tolerance_abs': config.get('tolerance_abs', config.get('tolerance', 0)),
        'tolerance_percent': config.get('tolerance_percent', 0),
        'unit': config.get('unit', ''),
        'node': config.get('node', ''),
        'branch': config.get('branch', ''),
        'component': config.get('component', ''),
    }
    value = extract_measurement(simulation_result, metric, rubric)
    result = evaluate_measurement(metric, value, rubric)
    result['expected_value'] = expected
    result['measured_value'] = value
    return result


def run_lab_sweep(kind, base_inputs, sweep_param, values, output):
    """Run a lightweight what-if sweep for an engineering-lab calculator."""
    points = []
    for raw_value in values or []:
        inputs = dict(base_inputs or {})
        inputs[sweep_param] = raw_value
        result = calculate_lab(kind, inputs)
        out = (result.get('outputs') or {}).get(output, {})
        points.append({
            'input': raw_value,
            'value': out.get('value'),
            'status': result.get('status'),
            'status_label': result.get('status_label'),
        })
    numeric = [p['value'] for p in points if isinstance(p.get('value'), (int, float))]
    trend = 'flat'
    if len(numeric) >= 2:
        if numeric[-1] > numeric[0]:
            trend = 'up'
        elif numeric[-1] < numeric[0]:
            trend = 'down'
    return {
        'ok': True,
        'kind': kind,
        'sweep_param': sweep_param,
        'output': output,
        'points': points,
        'min': min(numeric) if numeric else None,
        'max': max(numeric) if numeric else None,
        'trend': trend,
    }
