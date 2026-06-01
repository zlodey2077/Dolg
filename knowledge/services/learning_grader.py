import math
import re

from Dolg_APP.schematic_validation import validate_scheme_data
from Dolg_APP.services.engineering_units import parse_engineering_quantity
from Dolg_APP.services.schematic_graph import analyze_graph_topology

from .engineering_lab import evaluate_measurement, extract_measurement, lab_expected_value
from .formula_steps import check_equivalent_expression, explain_formula, formula_expected_value

TYPE_ALIASES = {
    'r': 'resistor',
    'res': 'resistor',
    'c': 'capacitor',
    'cap': 'capacitor',
    'l': 'inductor',
    'd': 'diode',
    'gnd': 'ground',
    'vsource': 'battery',
    'voltage_source': 'battery',
    'dc_source': 'battery',
    'source': 'battery',
    'npn': 'transistor',
    'pnp': 'transistor',
    'bjt': 'transistor',
    'mosfet': 'transistor',
    'pushbutton': 'button',
    'push_button': 'button',
    'switch': 'button',
    'linear_regulator': 'regulator',
    'voltage_regulator': 'regulator',
    'zener': 'diode',
}

def _result(correct, feedback, score=None, details=None):
    return {
        'correct': bool(correct),
        'score': 100 if score is None and correct else (0 if score is None else score),
        'feedback': feedback,
        'details': details or {},
    }


def _canonical_type(component_type):
    raw = str(component_type or '').strip().lower()
    return TYPE_ALIASES.get(raw, raw)


def _to_expected_unit(value, expected_unit=''):
    parsed = parse_engineering_quantity(value, expected_unit=expected_unit)
    if not parsed.ok:
        return None
    return parsed.value


def _looks_like_formula_expression(value):
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    plain_number = re.fullmatch(r'[-+]?\d+(?:[.,]\d+)?(?:e[-+]?\d+)?\s*[\wµωΩа-яА-Я]*', text)
    return not plain_number and any(char.isalpha() for char in text) and any(op in text for op in '+-*/()')


def _payload_value(answer, *keys):
    if isinstance(answer, dict):
        for key in keys:
            if key in answer:
                return answer[key]
        for key in ('answer', 'value', 'result'):
            if key in answer:
                return answer[key]
    return answer


def _tolerance(expected, rubric):
    tolerance_abs = float(rubric.get('tolerance_abs') or rubric.get('tolerance') or 0)
    tolerance_percent = float(rubric.get('tolerance_percent') or 0)
    if tolerance_percent:
        tolerance_abs = max(tolerance_abs, abs(expected) * tolerance_percent / 100)
    return tolerance_abs


def _within_expected(value, rubric):
    expected_range = rubric.get('expected_range') or rubric.get('range')
    if isinstance(expected_range, (list, tuple)) and len(expected_range) == 2:
        low, high = float(expected_range[0]), float(expected_range[1])
        return low <= value <= high, {'min': low, 'max': high}

    if 'min_value' in rubric or 'max_value' in rubric:
        low = float(rubric.get('min_value', -math.inf))
        high = float(rubric.get('max_value', math.inf))
        return low <= value <= high, {'min': low, 'max': high}

    expected = float(rubric.get('expected_value'))
    tolerance = _tolerance(expected, rubric)
    return abs(value - expected) <= tolerance, {'expected': expected, 'tolerance': tolerance}


def _component_value(component, field):
    if field in component:
        return component[field]

    for container_key in ('parameters', 'props', 'simulation'):
        container = component.get(container_key)
        if isinstance(container, dict) and field in container:
            return container[field]

    if field == 'resistance':
        return component.get('value') or component.get('nominal')
    if field == 'capacitance':
        return component.get('value') or component.get('nominal')
    if field == 'voltage':
        return component.get('voltage') or component.get('value')
    return component.get('value')


def _task_kind(task):
    return getattr(task, 'task_type', '')


def grade_task(task, payload):
    payload = payload or {}
    kind = _task_kind(task)
    if kind == 'math_numeric':
        return grade_math_task(task, _payload_value(payload, 'answer', 'value', 'result'))
    if kind == 'circuit_build':
        return grade_circuit_task(task, payload.get('scheme_data') if isinstance(payload, dict) else payload)
    if kind == 'simulation_measure':
        scheme_data = payload.get('scheme_data', {}) if isinstance(payload, dict) else {}
        simulation_result = payload.get('simulation_result', payload) if isinstance(payload, dict) else payload
        return grade_simulation_task(task, scheme_data, simulation_result)
    return _result(False, 'Неизвестный тип задания.', details={'task_type': kind})


def grade_math_task(task, answer):
    rubric = dict(getattr(task, 'rubric', {}) or {})
    expected_unit = rubric.get('unit', '')
    formula_config = rubric.get('formula') or rubric.get('formula_check')

    if formula_config and rubric.get('accept_expression'):
        if _looks_like_formula_expression(answer):
            check = check_equivalent_expression(
                formula_config.get('kind'),
                answer,
                variables=formula_config.get('variables'),
                inputs=formula_config.get('inputs') or {},
            )
            return _result(
                check['correct'],
                check['feedback'],
                details={
                    'formula': check,
                    'steps': explain_formula(formula_config.get('kind'), formula_config.get('inputs') or {}),
                },
            )

    if 'expected_value' not in rubric:
        lab_config = rubric.get('lab') or rubric.get('lab_calculation')
        if lab_config:
            try:
                rubric['expected_value'] = lab_expected_value(lab_config)
            except (TypeError, ValueError):
                return _result(False, 'Лабораторный расчет задания настроен некорректно.')
        elif formula_config:
            try:
                rubric['expected_value'] = formula_expected_value(formula_config)
            except (TypeError, ValueError):
                return _result(False, 'Формула задания настроена некорректно.')
        else:
            return _result(False, 'В задании не задано ожидаемое значение.')

    value = _to_expected_unit(answer, expected_unit)
    if value is None:
        return _result(False, 'Введите числовой ответ.', details={'answer': answer})

    correct, bounds = _within_expected(value, rubric)
    expected = bounds.get('expected')
    tolerance = bounds.get('tolerance')
    details = {'value': value, **bounds, 'unit': expected_unit}
    if formula_config:
        details['formula'] = explain_formula(formula_config.get('kind'), formula_config.get('inputs') or {})

    if correct:
        if expected is not None:
            return _result(True, f'Верно: {value:g} {expected_unit} попадает в допуск.', details=details)
        return _result(True, f'Верно: {value:g} {expected_unit} в допустимом диапазоне.', details=details)

    if expected is not None:
        return _result(
            False,
            f'Пока не сходится: получили {value:g} {expected_unit}, ожидается около {expected:g} {expected_unit} '
            f'(допуск ±{tolerance:g}).',
            details=details,
        )
    return _result(False, f'Пока не сходится: {value:g} {expected_unit} вне допустимого диапазона.', details=details)


def grade_circuit_task(task, scheme_data):
    rubric = getattr(task, 'rubric', {}) or {}
    scheme_data = scheme_data or {}
    validation = validate_scheme_data(scheme_data)
    graph_analysis = analyze_graph_topology(scheme_data)
    components = scheme_data.get('components', []) if isinstance(scheme_data, dict) else []
    connections = scheme_data.get('connections', []) if isinstance(scheme_data, dict) else []

    if not isinstance(components, list):
        components = []
    if not isinstance(connections, list):
        connections = []

    counts = {}
    normalized_components = []
    for component in components:
        if not isinstance(component, dict):
            continue
        component_type = _canonical_type(component.get('type'))
        counts[component_type] = counts.get(component_type, 0) + 1
        normalized_components.append((component_type, component))

    failures = []
    warnings = list(validation.get('warnings') or [])

    if rubric.get('require_drc_ok', True) and validation.get('errors'):
        failures.extend(validation['errors'])
    failures.extend(graph_analysis.get('errors') or [])
    warnings.extend(graph_analysis.get('warnings') or [])

    required_types = rubric.get('required_types') or {}
    for component_type, rule in required_types.items():
        component_type = _canonical_type(component_type)
        if isinstance(rule, dict):
            minimum = int(rule.get('min', rule.get('count', 1)))
            maximum = rule.get('max')
        else:
            minimum = int(rule)
            maximum = None
        current = counts.get(component_type, 0)
        if current < minimum:
            failures.append(f'Нужно добавить {component_type}: минимум {minimum}, сейчас {current}.')
        if maximum is not None and current > int(maximum):
            failures.append(f'Слишком много компонентов {component_type}: максимум {maximum}, сейчас {current}.')

    if rubric.get('require_ground') and counts.get('ground', 0) < 1:
        failures.append('В схеме должен быть GND.')
    if rubric.get('require_source') and counts.get('battery', 0) < 1:
        failures.append('В схеме должен быть источник питания.')

    min_connections = rubric.get('min_connections')
    if min_connections is not None and len(connections) < int(min_connections):
        failures.append(f'Нужно минимум соединений: {min_connections}, сейчас {len(connections)}.')

    graph_metrics = graph_analysis.get('metrics', {})
    if rubric.get('require_connected') and not graph_metrics.get('is_connected', True):
        failures.append('Схема должна быть связной.')
    if rubric.get('require_output_node') and not graph_metrics.get('has_output_node'):
        failures.append('Нужно обозначить выходной узел Vout/out.')

    nominal_hits = []
    for rule in rubric.get('nominal_ranges') or []:
        component_type = _canonical_type(rule.get('type'))
        field = rule.get('field', 'value')
        low = float(rule.get('min', -math.inf))
        high = float(rule.get('max', math.inf))
        unit = rule.get('unit', '')
        label = rule.get('label') or f'{component_type}.{field}'

        found = False
        for current_type, component in normalized_components:
            if current_type != component_type:
                continue
            numeric = _to_expected_unit(_component_value(component, field), unit)
            if numeric is not None and low <= numeric <= high:
                found = True
                nominal_hits.append({'label': label, 'value': numeric, 'unit': unit})
                break
        if not found:
            failures.append(f'Не найден номинал {label} в диапазоне {low:g}...{high:g} {unit}.')

    for rule in rubric.get('required_properties') or []:
        component_type = _canonical_type(rule.get('type'))
        field = rule.get('field')
        op = rule.get('op', 'equals')
        expected = rule.get('value')
        expected_values = rule.get('values') or ([expected] if expected is not None else [])
        label = rule.get('label') or f'{component_type}.{field}'

        matched = False
        for current_type, component in normalized_components:
            if component_type and current_type != component_type:
                continue
            raw_value = _component_value(component, field)
            if raw_value is None:
                raw_value = component.get(field)
            text_value = str(raw_value or '').lower()
            if op == 'contains':
                matched = any(str(item).lower() in text_value for item in expected_values)
            elif op == 'in':
                matched = text_value in {str(item).lower() for item in expected_values}
            else:
                matched = any(text_value == str(item).lower() for item in expected_values)
            if matched:
                break
        if not matched:
            failures.append(f'Не найдено свойство {label}.')

    details = {
        'validation': validation,
        'graph': graph_analysis,
        'component_counts': counts,
        'connections_count': len(connections),
        'nominal_hits': nominal_hits,
    }
    if failures:
        return _result(False, 'Схема пока не проходит проверку: ' + ' '.join(failures), details=details)

    feedback = 'Схема проходит проверку.'
    if warnings:
        feedback += ' Есть предупреждения: ' + ' '.join(warnings[:3])
    return _result(True, feedback, details=details)


def _metric_from_result(metric, simulation_result, rubric):
    return extract_measurement(simulation_result, metric, rubric)


def grade_simulation_task(task, scheme_data, simulation_result):
    rubric = dict(getattr(task, 'rubric', {}) or {})
    metric = rubric.get('metric') or 'node_voltage'
    expected_analysis = rubric.get('required_analysis') or rubric.get('analysis_type')
    actual_analysis = ''
    if isinstance(simulation_result, dict):
        actual_analysis = (
            simulation_result.get('analysis_type')
            or simulation_result.get('analysis')
            or simulation_result.get('type')
            or ''
        )

    if expected_analysis and str(actual_analysis).lower() != str(expected_analysis).lower():
        return _result(
            False,
            f'Нужен анализ {expected_analysis}, а отправлен {actual_analysis or "неизвестный"}.',
            details={'analysis_type': actual_analysis, 'metric': metric},
        )

    value = _metric_from_result(metric, simulation_result, rubric)
    if 'expected_value' not in rubric and not rubric.get('expected_range') and not rubric.get('range'):
        lab_config = rubric.get('lab') or rubric.get('lab_calculation')
        if lab_config:
            try:
                rubric['expected_value'] = lab_expected_value(lab_config)
            except (TypeError, ValueError):
                return _result(False, 'Лабораторный расчет измерения настроен некорректно.')
    measurement = evaluate_measurement(metric, value, rubric)

    correct = measurement['correct']
    correct, bounds = _within_expected(value, rubric) if value is not None else (False, {})
    details = {
        'metric': metric,
        'value': value,
        'analysis_type': actual_analysis,
        'status': measurement.get('status'),
        'status_label': measurement.get('status_label'),
        **bounds,
    }
    if correct:
        return _result(True, measurement['feedback'], details=details)

    return _result(False, measurement['feedback'], details=details)
