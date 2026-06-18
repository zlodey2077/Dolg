import math
import re
from collections import Counter, defaultdict

from django.db.models import Q

from Dolg_APP.schematic_validation import COMPONENT_TO_CATEGORY, validate_scheme_data
from knowledge.services.engineering_lab import evaluate_measurement, extract_measurement
from shop.component_validation import missing_spice_model_warning, nominal_mismatch_warning
from shop.models import Product

from .artifact_ingestion import artifact_reports_from_project, review_external_cad_artifacts
from .engineering_units import parse_engineering_number
from .expert_rules import build_expert_facts, evaluate_expert_rules
from .review_i18n import localize_review_report
from .risk_scoring import assess_fuzzy_project_risk
from .schematic_graph import analyze_graph_topology

STATUS_LABELS = {
    'ready': 'готово',
    'needs_review': 'нужна проверка',
    'risk': 'есть риск',
    'critical': 'критично',
}

TYPE_ALIASES = {
    'r': 'resistor',
    'res': 'resistor',
    'c': 'capacitor',
    'cap': 'capacitor',
    'l': 'inductor',
    'd': 'diode',
    'led': 'led',
    'v': 'battery',
    'vsource': 'battery',
    'voltage': 'battery',
    'voltage_source': 'battery',
    'gnd': 'ground',
    '0': 'ground',
    'q': 'transistor',
    'npn': 'transistor',
    'pnp': 'transistor',
    'bjt': 'transistor',
    'u': 'ic',
    'ic': 'ic',
    'regulator': 'regulator',
    'linear_regulator': 'regulator',
    'button': 'button',
    'switch': 'button',
}

UNIT_FACTORS = {
    '': 1.0,
    'v': 1.0,
    'mv': 1e-3,
    'a': 1.0,
    'ma': 1e-3,
    'ua': 1e-6,
    'ohm': 1.0,
    'r': 1.0,
    'k': 1e3,
    'kohm': 1e3,
    'meg': 1e6,
    'mohm': 1e6,
    'w': 1.0,
    'mw': 1e-3,
    'f': 1.0,
    'uf': 1e-6,
    'u': 1e-6,
    'nf': 1e-9,
    'pf': 1e-12,
    'hz': 1.0,
    'khz': 1e3,
    'mhz': 1e6,
}


def normalize_component_type(value):
    raw = str(value or '').strip().lower()
    if raw in TYPE_ALIASES:
        return TYPE_ALIASES[raw]
    if raw.startswith('res'):
        return 'resistor'
    if raw.startswith('cap'):
        return 'capacitor'
    if raw.startswith('ind'):
        return 'inductor'
    if raw.startswith('bat') or raw.startswith('source'):
        return 'battery'
    return raw


def parse_number(value, default=None):
    parsed = parse_engineering_number(value, default=default)
    return parsed if parsed is not None else default


def _component_value(component, *names):
    for name in names:
        if name in component:
            return component.get(name)
    for container_name in ('parameters', 'catalog_parameters', 'props', 'simulation'):
        container = component.get(container_name)
        if isinstance(container, dict):
            for name in names:
                if name in container:
                    return container.get(name)
    return None


def _component_catalog_ref(component):
    return (
        component.get('catalog_slug') or component.get('catalog_ref') or component.get('part_number') or ''
    ).strip()


def _component_label(component):
    return str(
        component.get('label')
        or component.get('ref')
        or component.get('part_number')
        or component.get('id')
        or component.get('type')
        or 'component'
    )


def _iter_components(scheme_data):
    if not isinstance(scheme_data, dict):
        return []
    components = scheme_data.get('components') or []
    return [item for item in components if isinstance(item, dict)]


def _iter_connections(scheme_data):
    if not isinstance(scheme_data, dict):
        return []
    connections = scheme_data.get('connections') or []
    return [item for item in connections if isinstance(item, dict)]


def build_connectivity_metrics(scheme_data):
    components = _iter_components(scheme_data)
    connections = _iter_connections(scheme_data)
    graph_analysis = analyze_graph_topology(scheme_data)
    graph_metrics = graph_analysis.get('metrics', {})
    counts = Counter(normalize_component_type(c.get('type')) for c in components)
    used_ids = set()
    net_degree = defaultdict(int)

    for conn in connections:
        source = conn.get('from') or {}
        target = conn.get('to') or {}
        source_id = source.get('compId')
        target_id = target.get('compId')
        if source_id is not None:
            used_ids.add(source_id)
            net_degree[str(source_id)] += 1
        if target_id is not None:
            used_ids.add(target_id)
            net_degree[str(target_id)] += 1

    unconnected = [
        _component_label(c)
        for c in components
        if normalize_component_type(c.get('type')) not in {'ground', 'node'} and c.get('id') not in used_ids
    ]

    metrics = {
        'component_count': len(components),
        'connection_count': len(connections),
        'component_counts': dict(counts),
        'has_ground': counts.get('ground', 0) > 0,
        'has_source': counts.get('battery', 0) > 0,
        'unconnected': unconnected,
        'single_pin_nodes': [node for node, degree in net_degree.items() if degree == 1],
    }
    metrics.update(
        {
            'graph_ok': graph_analysis.get('ok', True),
            'graph_errors': graph_analysis.get('errors', []),
            'graph_warnings': graph_analysis.get('warnings', []),
            'connected_components_count': graph_metrics.get('connected_components_count', 0),
            'is_connected': graph_metrics.get('is_connected', True),
            'isolated_components': graph_metrics.get('isolated_components', []),
            'floating_components': graph_metrics.get('floating_components', []),
            'paths_to_ground': graph_metrics.get('paths_to_ground', {}),
            'cycle_count': graph_metrics.get('cycle_count', 0),
            'topology': graph_metrics.get('topology', 'generic'),
            'has_output_node': graph_metrics.get('has_output_node', False),
            'output_nodes': graph_metrics.get('output_nodes', []),
        }
    )
    return metrics


def evaluate_bom_risks(scheme_data):
    risks = []
    matched = []
    missing_catalog = []
    components = _iter_components(scheme_data)

    for component in components:
        ctype = normalize_component_type(component.get('type'))
        catalog_ref = _component_catalog_ref(component)
        product = None
        if catalog_ref:
            product = (
                Product.objects.select_related('category')
                .filter(Q(part_number__iexact=catalog_ref) | Q(slug__iexact=catalog_ref))
                .first()
            )
            if not product:
                risks.append(
                    {
                        'level': 'warning',
                        'component': _component_label(component),
                        'message': f'товар не найден в каталоге: {catalog_ref}',
                    }
                )
                missing_catalog.append(catalog_ref)
            else:
                matched.append(product.part_number or product.slug)
                expected_category = COMPONENT_TO_CATEGORY.get(ctype)
                if expected_category and product.category.slug != expected_category:
                    risks.append(
                        {
                            'level': 'warning',
                            'component': _component_label(component),
                            'message': f'категория не совпадает: ожидалась «{expected_category}», получена «{product.category.slug}»',
                        }
                    )
                for warning in (
                    nominal_mismatch_warning(component, product),
                    missing_spice_model_warning(component, product),
                ):
                    if warning:
                        risks.append(
                            {
                                'level': 'warning',
                                'component': _component_label(component),
                                'message': warning,
                            }
                        )
                if product.lifecycle_status in {'eol', 'obsolete'}:
                    risks.append(
                        {
                            'level': 'risk',
                            'component': _component_label(component),
                            'message': f'lifecycle status is {product.lifecycle_status}',
                        }
                    )
                if product.stock <= 0:
                    risks.append(
                        {
                            'level': 'risk',
                            'component': _component_label(component),
                            'message': 'catalog item is out of stock',
                        }
                    )
        elif ctype not in {'ground', 'node'}:
            missing_catalog.append(_component_label(component))

    return {
        'matched_count': len(set(matched)),
        'missing_catalog_count': len(missing_catalog),
        'missing_catalog': missing_catalog[:20],
        'risks': risks,
    }


def _numbers_from_text(value, expected_unit=''):
    if value in (None, ''):
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    text = str(value).replace(',', '.')
    chunks = re.findall(r'[-+]?\d+(?:\.\d+)?\s*(?:[a-zA-Zа-яА-ЯµΩ°/%]+)?', text)
    values = []
    for chunk in chunks:
        suffix = re.sub(r'[-+]?\d+(?:\.\d+)?\s*', '', chunk.strip().lower()).strip()
        if suffix and expected_unit and not _suffix_matches_expected_unit(suffix, expected_unit):
            continue
        parsed = parse_engineering_number(chunk.strip(), None, expected_unit=expected_unit)
        if parsed is not None:
            values.append(abs(parsed))
    return values


def _suffix_matches_expected_unit(suffix, expected_unit):
    expected = str(expected_unit or '').strip().lower()
    suffix = suffix.replace('µ', 'u').replace('ω', 'ohm').replace('Ω', 'ohm')
    unit_sets = {
        'v': ('v', 'в', 'mv', 'мв', 'kv', 'кв'),
        'a': ('a', 'а', 'ma', 'ма', 'ua', 'мка', 'uа'),
        'w': ('w', 'вт', 'mw', 'мвт'),
        'c': ('c', '°c', 'degc'),
    }
    aliases = unit_sets.get(expected.lower(), ())
    return suffix in aliases


def _max_limit_from_values(*values, expected_unit=''):
    candidates = []
    for value in values:
        candidates.extend(_numbers_from_text(value, expected_unit=expected_unit))
    return max(candidates) if candidates else None


def _product_for_component(component):
    catalog_ref = _component_catalog_ref(component)
    if not catalog_ref:
        return None
    return (
        Product.objects.select_related('category')
        .filter(Q(part_number__iexact=catalog_ref) | Q(slug__iexact=catalog_ref))
        .first()
    )


def _datasheet_field_text(product, field):
    record = (product.parameters or {}).get('datasheet_extracted') if product else None
    if not isinstance(record, dict):
        return ''
    fields = record.get('fields') if isinstance(record.get('fields'), dict) else {}
    values = fields.get(field) or []
    return ' '.join(str(item) for item in values)


def _component_limits(component, product=None):
    params = product.parameters if product else {}
    product_text_abs = _datasheet_field_text(product, 'absolute_maximum_ratings')
    product_text_thermal = _datasheet_field_text(product, 'thermal_data')
    component_params = component.get('parameters') if isinstance(component.get('parameters'), dict) else {}

    def pick(*keys, expected_unit=''):
        values = []
        for key in keys:
            values.extend(
                [
                    component.get(key),
                    component_params.get(key),
                    params.get(key) if isinstance(params, dict) else None,
                ]
            )
        return _max_limit_from_values(*values, expected_unit=expected_unit)

    return {
        'voltage_v': pick(
            'max_voltage_v',
            'max_voltage',
            'voltage',
            'supply_voltage',
            'vds',
            'vceo',
            'vrrm',
            expected_unit='V',
        )
        or _max_limit_from_values(product_text_abs, expected_unit='V'),
        'current_a': pick(
            'max_current_a', 'max_current', 'current', 'id', 'ic', 'if', 'output_current', expected_unit='A'
        )
        or _max_limit_from_values(product_text_abs, expected_unit='A'),
        'power_w': pick('max_power_w', 'rated_power_w', 'tdp_w', 'power', 'max_power', expected_unit='W')
        or _max_limit_from_values(product_text_abs, product_text_thermal, expected_unit='W'),
        'temperature_c': pick(
            'max_junction_c',
            'max_temperature_c',
            'max_temp',
            'temperature',
            'junction_temperature',
            expected_unit='C',
        )
        or _max_limit_from_values(product_text_thermal, expected_unit='C'),
    }


def _measurement_component_match(item, component):
    label = str(getattr(item, 'label', '') or '').lower()
    result = getattr(item, 'result', {}) or {}
    component_tokens = {
        str(component.get('id') or '').lower(),
        str(component.get('label') or '').lower(),
        str(component.get('ref') or '').lower(),
        str(component.get('part_number') or '').lower(),
    }
    component_tokens.discard('')
    if result.get('component') and str(result.get('component')).lower() in component_tokens:
        return True
    return bool(component_tokens and any(token in label for token in component_tokens))


def _measured_value(component, measurements, metric_names):
    for key in metric_names:
        value = parse_number(_component_value(component, key), None)
        if value is not None:
            return value
    for item in measurements or []:
        metric = str(getattr(item, 'metric', '') or '').lower()
        if metric not in metric_names:
            continue
        if _measurement_component_match(item, component):
            return getattr(item, 'value', None)
    return None


def evaluate_validity_guard(scheme_data, measurements=None):
    """Check whether measured/calculated values stay inside known ratings."""
    issues = []
    metrics = {'checked_components': 0, 'known_limits': 0, 'out_of_range': 0}
    for component in _iter_components(scheme_data):
        ctype = normalize_component_type(component.get('type'))
        if ctype in {'ground', 'node'}:
            continue
        product = _product_for_component(component)
        limits = _component_limits(component, product=product)
        if not any(limits.values()):
            continue
        metrics['checked_components'] += 1
        metrics['known_limits'] += sum(1 for value in limits.values() if value)
        label = _component_label(component)
        checks = [
            (
                'component_voltage',
                'voltage_v',
                ('component_voltage', 'voltage', 'dc_voltage', 'node_voltage'),
                'В',
            ),
            ('branch_current', 'current_a', ('branch_current', 'component_current', 'current'), 'А'),
            ('component_power', 'power_w', ('component_power', 'power_w', 'power'), 'Вт'),
            (
                'junction_temperature',
                'temperature_c',
                ('junction_temperature', 'temperature_c', 'temperature'),
                '°C',
            ),
        ]
        for metric, limit_key, aliases, unit_label in checks:
            limit = limits.get(limit_key)
            if not limit:
                continue
            measured = _measured_value(component, measurements, aliases)
            if measured is None:
                continue
            ratio = abs(float(measured)) / limit if limit else 0
            if ratio < 0.8:
                continue
            level = 'critical' if ratio >= 1 else 'risk' if ratio >= 0.9 else 'warning'
            if level in {'critical', 'risk'}:
                metrics['out_of_range'] += 1
            issues.append(
                {
                    'level': level,
                    'component': label,
                    'metric': metric,
                    'value': float(measured),
                    'limit': float(limit),
                    'ratio': round(ratio, 3),
                    'message': (
                        f'Результат {metric}={float(measured):g} {unit_label} для {label} '
                        f'близок к пределу или выходит за область применимости модели '
                        f'({float(limit):g} {unit_label}).'
                    ),
                    'source': 'datasheet_extracted'
                    if product and (product.parameters or {}).get('datasheet_extracted')
                    else 'product_parameters',
                }
            )
    return {'issues': issues, 'metrics': metrics}


def _latest_simulation_payload(simulation_runs):
    latest = {}
    for run in simulation_runs or []:
        if getattr(run, 'result_data', None):
            latest[getattr(run, 'analysis_type', 'unknown') or 'unknown'] = run.result_data
    return latest


def _simulation_metric(simulation_runs, metric, component=None):
    for run in simulation_runs or []:
        value = extract_measurement(
            getattr(run, 'result_data', {}) or {},
            metric,
            {'component': component or '', 'branch': component or ''},
        )
        if value is not None:
            return value, run
    return None, None


def evaluate_derating(scheme_data, simulation_runs=None, measurements=None):
    issues = []
    metrics = {
        'checked_components': 0,
        'power_risks': 0,
        'thermal_risks': 0,
    }

    measurement_by_metric = {}
    for item in measurements or []:
        measurement_by_metric[getattr(item, 'metric', '')] = item

    for component in _iter_components(scheme_data):
        ctype = normalize_component_type(component.get('type'))
        if ctype in {'ground', 'node'}:
            continue
        metrics['checked_components'] += 1
        label = _component_label(component)
        power_limit = parse_number(
            _component_value(component, 'tdp_w', 'power_w', 'rated_power_w', 'power', 'max_power'),
            None,
        )
        measured_power = parse_number(_component_value(component, 'measured_power_w', 'power_w'), None)
        if measured_power is None:
            measured_power, _ = _simulation_metric(
                simulation_runs, 'component_power', str(component.get('id'))
            )
        if measured_power is None and 'component_power' in measurement_by_metric:
            measured_power = measurement_by_metric['component_power'].value

        if power_limit and measured_power is not None:
            ratio = measured_power / power_limit if power_limit else 0
            if ratio >= 1:
                level = 'critical'
                metrics['power_risks'] += 1
            elif ratio >= 0.7:
                level = 'risk'
                metrics['power_risks'] += 1
            elif ratio >= 0.5:
                level = 'warning'
            else:
                continue
            issues.append(
                {
                    'level': level,
                    'component': label,
                    'message': f'power derating {measured_power:g} W / {power_limit:g} W ({ratio:.0%})',
                    'metric': 'component_power',
                    'value': measured_power,
                    'limit': power_limit,
                }
            )

        max_temp = parse_number(_component_value(component, 'max_junction_c', 'max_temperature_c'), None)
        measured_temp = parse_number(
            _component_value(component, 'junction_temperature_c', 'temperature_c'), None
        )
        if measured_temp is None:
            measured_temp, _ = _simulation_metric(
                simulation_runs, 'junction_temperature', str(component.get('id'))
            )
        if measured_temp is None and 'junction_temperature' in measurement_by_metric:
            measured_temp = measurement_by_metric['junction_temperature'].value
        if max_temp and measured_temp is not None:
            margin = max_temp - measured_temp
            if margin <= 0:
                level = 'critical'
                metrics['thermal_risks'] += 1
            elif margin < 20:
                level = 'risk'
                metrics['thermal_risks'] += 1
            else:
                continue
            issues.append(
                {
                    'level': level,
                    'component': label,
                    'message': f'thermal margin {margin:g} C',
                    'metric': 'junction_temperature',
                    'value': measured_temp,
                    'limit': max_temp,
                }
            )

    return {'issues': issues, 'metrics': metrics}


FAULT_LIBRARY = [
    {
        'code': 'missing_ground',
        'title': 'Отсутствует опорный узел GND',
        'symptom': 'Рабочая точка DC может «плавать»; SPICE падает или создаёт искусственную опору.',
        'recommendation': 'Добавьте символ GND и подключите к нему обратный путь схемы.',
    },
    {
        'code': 'missing_source',
        'title': 'Нет источника питания',
        'symptom': 'Напряжения узлов и токи ветвей остаются неопределёнными или нулевыми.',
        'recommendation': 'Добавьте источник напряжения/тока и задайте его номинал.',
    },
    {
        'code': 'open_component',
        'title': 'Несоединённый компонент',
        'symptom': 'Ветвь без тока; показания пробников не сходятся с расчётом.',
        'recommendation': 'Подключите оба вывода или удалите неиспользуемый компонент.',
    },
    {
        'code': 'led_without_resistor',
        'title': 'Ток через LED не ограничен',
        'symptom': 'Ток через светодиод может превысить безопасный предел.',
        'recommendation': 'Поставьте последовательный резистор и проверьте ток ветви.',
    },
    {
        'code': 'power_overload',
        'title': 'Перегрузка компонента по мощности',
        'symptom': 'Тепловой запас низкий; элемент может перегреться.',
        'recommendation': 'Возьмите компонент с большей мощностью, уменьшите ток или измените топологию.',
    },
]


def detect_faults(scheme_data, validation, connectivity, derating):
    faults = []
    if not connectivity['has_ground']:
        faults.append(FAULT_LIBRARY[0])
    if not connectivity['has_source']:
        faults.append(FAULT_LIBRARY[1])
    if connectivity['unconnected']:
        item = dict(FAULT_LIBRARY[2])
        item['components'] = connectivity['unconnected'][:8]
        faults.append(item)

    counts = connectivity['component_counts']
    if counts.get('led', 0) and not counts.get('resistor', 0):
        faults.append(FAULT_LIBRARY[3])

    if any(issue['level'] in {'risk', 'critical'} for issue in derating.get('issues', [])):
        faults.append(FAULT_LIBRARY[4])

    for error in validation.get('errors') or []:
        faults.append(
            {
                'code': 'drc_error',
                'title': 'Ошибка DRC',
                'symptom': error,
                'recommendation': 'Устраните ошибку DRC перед симуляцией или экспортом.',
            }
        )

    return faults


def collect_measurement_metrics(simulation_runs=None, measurements=None):
    metrics = {}
    for run in simulation_runs or []:
        result = getattr(run, 'result_data', {}) or {}
        run_metrics = result.get('metrics') if isinstance(result.get('metrics'), dict) else {}
        for key, value in run_metrics.items():
            parsed = parse_number(value, None)
            metrics[key] = parsed if parsed is not None else value
    for item in measurements or []:
        metrics[item.metric] = {
            'value': item.value,
            'unit': item.unit,
            'status': item.status,
            'label': item.label,
        }
    return metrics


def compare_measurement(
    metric, value, expected_value=None, tolerance_abs=None, tolerance_percent=None, unit=''
):
    rubric = {'metric': metric, 'unit': unit}
    if expected_value is not None:
        rubric['expected_value'] = expected_value
    if tolerance_abs is not None:
        rubric['tolerance_abs'] = tolerance_abs
    if tolerance_percent is not None:
        rubric['tolerance_percent'] = tolerance_percent
    return evaluate_measurement(metric, value, rubric)


def _score_status(score, errors_count, critical_count):
    if critical_count or errors_count or score < 50:
        return 'critical'
    if score < 75:
        return 'risk'
    if score < 90:
        return 'needs_review'
    return 'ready'


def _recommendation_core(message):
    text = str(message or '').lower()
    if 'gnd' in text or 'ground' in text:
        return 'missing_ground'
    return None


def _rule_recommendation_core(rule_id):
    return {
        'erc.missing_ground': 'missing_ground',
    }.get(str(rule_id or ''))


def _dedupe_recommendations_against_expert(recommendations, expert_findings):
    """Prefer expert-rule recommendations over older generic/fault text."""
    expert_core_text = {}
    for finding in expert_findings or []:
        recommendation = finding.get('recommendation')
        if not recommendation:
            continue
        core = _rule_recommendation_core(finding.get('rule_id')) or _recommendation_core(recommendation)
        if core and core not in expert_core_text:
            expert_core_text[core] = recommendation

    out = []
    seen = set()
    for recommendation in recommendations or []:
        core = _recommendation_core(recommendation)
        if core in expert_core_text and recommendation != expert_core_text[core]:
            continue
        norm = re.sub(r'\s+', ' ', str(recommendation).strip()).lower()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(recommendation)
    return out


BASE_FAILURE_RATES = {
    'resistor': 0.02e-6,
    'capacitor': 0.05e-6,
    'inductor': 0.04e-6,
    'diode': 0.04e-6,
    'led': 0.05e-6,
    'transistor': 0.08e-6,
    'ic': 0.20e-6,
    'regulator': 0.15e-6,
    'battery': 0.10e-6,
}


def evaluate_reliability_margin(scheme_data):
    components = scheme_data.get('components') if isinstance(scheme_data, dict) else []
    if not isinstance(components, list):
        components = []
    items = []
    total = 0.0
    counts = Counter()
    for component in components:
        ctype = normalize_component_type(component.get('type') if isinstance(component, dict) else '')
        counts[ctype] += 1
        rate = BASE_FAILURE_RATES.get(ctype, 0.06e-6)
        stress = 1.0
        if isinstance(component, dict):
            if component.get('measured_power_w') and component.get('rated_power_w'):
                try:
                    ratio = float(component.get('measured_power_w')) / max(
                        float(component.get('rated_power_w')), 1e-12
                    )
                    if ratio >= 0.8:
                        stress += 0.8
                    elif ratio >= 0.5:
                        stress += 0.3
                except (TypeError, ValueError):
                    pass
        contribution = rate * stress
        total += contribution
        items.append(
            {
                'component': component.get('id') or component.get('ref') or ctype
                if isinstance(component, dict)
                else ctype,
                'type': ctype,
                'failure_rate_per_hour': contribution,
            }
        )
    mtbf = (1.0 / total) if total > 0 else None
    probability_1000h = math.exp(-total * 1000) if total > 0 else 1.0
    return {
        'component_count': len(components),
        'type_counts': dict(counts),
        'failure_rate_per_hour': total,
        'mtbf_hours': mtbf,
        'probability_1000h': probability_1000h,
        'items': items[:40],
    }


def evaluate_manufacturing_readiness(scheme_data):
    components = scheme_data.get('components') if isinstance(scheme_data, dict) else []
    if not isinstance(components, list):
        components = []
    checks = {
        'has_datasheet': 0,
        'has_package': 0,
        'has_model': 0,
        'has_footprint': 0,
        'has_ratings': 0,
        'has_bom_binding': 0,
    }
    missing = []
    for component in components:
        if not isinstance(component, dict):
            continue
        cid = component.get('id') or component.get('ref') or component.get('type') or 'component'
        has_datasheet = bool(
            component.get('datasheet_url')
            or component.get('datasheet')
            or component.get('product_datasheet_url')
        )
        has_package = bool(
            component.get('package')
            or component.get('footprint')
            or component.get('case')
            or component.get('mounting')
        )
        has_model = bool(
            component.get('spice_model') or component.get('model') or component.get('has_spice_model')
        )
        has_footprint = bool(
            component.get('footprint') or component.get('cad_model') or component.get('has_cad_model')
        )
        has_ratings = any(
            key in component
            for key in ('rated_power_w', 'max_voltage_v', 'max_current_a', 'temperature_max_c')
        )
        has_bom = bool(component.get('product_id') or component.get('sku') or component.get('part_number'))
        for key, ok in [
            ('has_datasheet', has_datasheet),
            ('has_package', has_package),
            ('has_model', has_model),
            ('has_footprint', has_footprint),
            ('has_ratings', has_ratings),
            ('has_bom_binding', has_bom),
        ]:
            if ok:
                checks[key] += 1
        if not all((has_package, has_ratings, has_bom)):
            missing.append(
                {
                    'component': cid,
                    'missing': [
                        label
                        for label, ok in [
                            ('package', has_package),
                            ('ratings', has_ratings),
                            ('bom_binding', has_bom),
                        ]
                        if not ok
                    ],
                }
            )
    total = len([item for item in components if isinstance(item, dict)])
    score = 100 if total == 0 else round(sum(checks.values()) * 100 / max(total * len(checks), 1))
    return {
        'score': score,
        'component_count': total,
        'checks': checks,
        'missing': missing[:40],
    }


def build_design_review(
    project, *, simulation_runs=None, measurements=None, import_summary=None, artifact_reports=None
):
    scheme_data = project.scheme_data if project is not None else {}
    if artifact_reports is None:
        artifact_reports = artifact_reports_from_project(project)
    validation = validate_scheme_data(scheme_data)
    connectivity = build_connectivity_metrics(scheme_data)
    bom = evaluate_bom_risks(scheme_data)
    derating = evaluate_derating(scheme_data, simulation_runs=simulation_runs, measurements=measurements)
    validity = evaluate_validity_guard(scheme_data, measurements=measurements)
    reliability = evaluate_reliability_margin(scheme_data)
    manufacturing = evaluate_manufacturing_readiness(scheme_data)
    external_cad = review_external_cad_artifacts(artifact_reports)
    faults = detect_faults(scheme_data, validation, connectivity, derating)
    measurement_metrics = collect_measurement_metrics(simulation_runs, measurements)

    errors = list(validation.get('errors') or [])
    warnings = list(validation.get('warnings') or [])
    recommendations = []
    critical_count = 0
    risk_count = 0

    if not connectivity['has_ground']:
        errors.append('Missing GND reference')
        critical_count += 1
    if not connectivity['has_source']:
        warnings.append('Missing supply/source component')
    for error in connectivity.get('graph_errors') or []:
        errors.append(f'Graph topology: {error}')
    for warning in connectivity.get('graph_warnings') or []:
        warnings.append(warning)

    for item in bom['risks']:
        if item['level'] == 'risk':
            risk_count += 1
        warnings.append(f'{item["component"]}: {item["message"]}')

    for issue in derating['issues']:
        message = f'{issue["component"]}: {issue["message"]}'
        if issue['level'] == 'critical':
            errors.append(message)
            critical_count += 1
        elif issue['level'] == 'risk':
            warnings.append(message)
            risk_count += 1
        else:
            warnings.append(message)

    for issue in validity['issues']:
        message = issue.get('message')
        if issue['level'] == 'critical':
            errors.append(message)
            critical_count += 1
        elif issue['level'] == 'risk':
            warnings.append(message)
            risk_count += 1
        else:
            warnings.append(message)

    for finding in external_cad.get('findings') or []:
        message = f'{finding.get("source_name") or "artifact"}: {finding.get("title") or finding.get("raw") or finding.get("rule_id")}'
        if finding.get('severity') in {'critical', 'error'}:
            errors.append(message)
            if finding.get('severity') == 'critical':
                critical_count += 1
        else:
            warnings.append(message)

    if manufacturing.get('missing'):
        warnings.append('Manufacturing readiness: some components miss package, ratings or BOM binding.')

    for fault in faults:
        recommendations.append(f'{fault["title"]}: {fault["recommendation"]}')

    if not simulation_runs:
        recommendations.append('Run at least one DC/AC/TRAN simulation and save the result.')
    if bom['missing_catalog_count']:
        recommendations.append('Bind schematic components to catalog items before BOM export.')
    if not connectivity['has_ground']:
        recommendations.append('Add GND before relying on simulation results.')
    if connectivity.get('floating_components'):
        recommendations.append('Connect floating schematic fragments to the main reference path.')
    if connectivity.get('topology') in {'voltage_divider', 'rc_network', 'led_indicator'}:
        recommendations.append(
            f'Detected topology: {connectivity["topology"]}; use matching lab checks for expected values.'
        )
    if import_summary:
        recommendations.append('Review unsupported import items before saving the imported project.')
    if external_cad.get('finding_count'):
        recommendations.append('Review imported CAD DRC/ERC findings before relying on this project session.')
    if manufacturing.get('missing'):
        recommendations.append(
            'Complete assembly readiness: package, ratings, footprint/model and BOM binding.'
        )
    if validity['issues']:
        recommendations.append(
            'Проверьте datasheet/rating limits: часть результатов близка к предельным режимам или вне области применимости модели.'
        )

    expert_facts = build_expert_facts(
        connectivity=connectivity,
        bom=bom,
        derating=derating,
        measurements=measurements,
        import_summary=import_summary,
        errors=errors,
        warnings=warnings,
        scheme_data=scheme_data,
    )
    expert = evaluate_expert_rules(expert_facts)
    for finding in expert.get('findings') or []:
        recommendation = finding.get('recommendation')
        if recommendation and recommendation not in recommendations:
            recommendations.append(recommendation)
    recommendations = _dedupe_recommendations_against_expert(
        recommendations, expert.get('findings') or []
    )

    thermal_margins = [
        issue.get('limit') - issue.get('value')
        for issue in derating.get('issues') or []
        if issue.get('metric') == 'junction_temperature'
        and isinstance(issue.get('limit'), (int, float))
        and isinstance(issue.get('value'), (int, float))
    ]
    fuzzy_risk = assess_fuzzy_project_risk(
        thermal_margin_c=min(thermal_margins) if thermal_margins else None,
        bom_risk_count=len(bom.get('risks') or []),
        floating_count=len(connectivity.get('floating_components') or []),
        warning_count=len(warnings),
    )

    # Build a per-category breakdown alongside the scalar score so the UI
    # can show «что именно снизило балл». Negative values, sum = (100 - score)
    # before clamping. Keep the scalar `score` field unchanged for back-compat.
    breakdown_components = [
        ('errors', -len(errors) * 20, 'Ошибки', len(errors)),
        ('warnings', -len(warnings) * 6, 'Предупреждения', len(warnings)),
        ('derating', -risk_count * 8, 'Риски деретинга', risk_count),
        (
            'validity',
            -len([item for item in validity.get('issues') or [] if item.get('level') in {'risk', 'critical'}])
            * 8,
            'Выход за пределы модели',
            len([item for item in validity.get('issues') or [] if item.get('level') in {'risk', 'critical'}]),
        ),
        (
            'expert_risk',
            -len(
                [
                    item
                    for item in expert.get('findings') or []
                    if item.get('severity') in {'risk', 'critical'}
                ]
            )
            * 5,
            'Критичные экспертные выводы',
            len(
                [
                    item
                    for item in expert.get('findings') or []
                    if item.get('severity') in {'risk', 'critical'}
                ]
            ),
        ),
        (
            'external_cad',
            -len(
                [
                    item
                    for item in external_cad.get('findings') or []
                    if item.get('severity') in {'critical', 'error'}
                ]
            )
            * 10,
            'Импорт CAD/ERC',
            len(
                [
                    item
                    for item in external_cad.get('findings') or []
                    if item.get('severity') in {'critical', 'error'}
                ]
            ),
        ),
        (
            'manufacturing',
            -len(manufacturing.get('missing') or []) * 2,
            'Пробелы готовности к сборке',
            len(manufacturing.get('missing') or []),
        ),
        (
            'unconnected',
            -len(connectivity['unconnected']) * 3,
            'Несоединённые компоненты',
            len(connectivity['unconnected']),
        ),
    ]
    score_breakdown = [
        {'key': key, 'delta': delta, 'label': label, 'count': count}
        for key, delta, label, count in breakdown_components
        if delta < 0
    ]
    score = 100 + sum(
        item['delta'] for item in score_breakdown if isinstance(item.get('delta'), (int, float))
    )
    if not score_breakdown:
        score = 100
    score = max(0, min(100, score))
    status = _score_status(score, len(errors), critical_count)

    sections = {
        'drc': validation,
        'connectivity': connectivity,
        'bom': bom,
        'derating': derating,
        'validity': validity,
        'reliability': reliability,
        'manufacturing': manufacturing,
        'external_cad': external_cad,
        'artifacts': artifact_reports or [],
        'measurements': measurement_metrics,
        'expert_system': expert,
        'expert_risk': fuzzy_risk,
        'latest_simulation': _latest_simulation_payload(simulation_runs),
        'import': import_summary or {},
    }

    summary = (
        f'{connectivity["component_count"]} components, '
        f'{connectivity["connection_count"]} connections, '
        f'{len(errors)} errors, {len(warnings)} warnings.'
    )

    report = {
        'score': score,
        'score_breakdown': score_breakdown,
        'status': status,
        'status_label': STATUS_LABELS[status],
        'summary': summary,
        'errors': errors,
        'warnings': warnings,
        'recommendations': recommendations[:20],
        'metrics': {
            'components': connectivity['component_count'],
            'connections': connectivity['connection_count'],
            'simulations': len(simulation_runs or []),
            'measurements': len(measurements or []),
            'faults': len(faults),
            'bom_matched': bom['matched_count'],
            'bom_missing': bom['missing_catalog_count'],
            'connected_components': connectivity.get('connected_components_count', 0),
            'cycle_count': connectivity.get('cycle_count', 0),
            'topology': connectivity.get('topology', 'generic'),
            'expert_findings': len(expert.get('findings') or []),
            'fuzzy_risk_score': fuzzy_risk.get('score'),
            'validity_issues': len(validity.get('issues') or []),
            'external_cad_findings': external_cad.get('finding_count', 0),
            'readiness_missing': len(manufacturing.get('missing') or []),
            'mtbf_hours': reliability.get('mtbf_hours'),
        },
        'sections': sections,
        'faults': faults,
        'expert_findings': expert.get('findings') or [],
    }
    return localize_review_report(report)
