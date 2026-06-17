"""Russian localization for schematic checks and project review reports.

The review core still keeps machine-friendly codes in English, but all
human-facing findings should be readable in Russian for diploma/demo use.
"""

from __future__ import annotations

import copy
import re
from typing import Any

STATUS_LABELS_RU = {
    'ready': 'готово',
    'needs_review': 'нужна проверка',
    'risk': 'есть риск',
    'critical': 'критично',
    'external_cad_findings': 'Внешние CAD-проверки',
    'readiness_missing': 'Пробелы готовности к сборке',
    'mtbf_hours': 'MTBF, часов',
}

SEVERITY_LABELS_RU = {
    'critical': 'критично',
    'error': 'ошибка',
    'risk': 'риск',
    'warning': 'предупреждение',
    'recommendation': 'рекомендация',
    'info': 'информация',
}

TOPOLOGY_LABELS_RU = {
    'generic': 'общая схема',
    'voltage_divider': 'делитель напряжения',
    'rc_network': 'RC-цепь',
    'led_indicator': 'LED-индикатор',
}

METRIC_LABELS_RU = {
    'components': 'Компоненты',
    'connections': 'Соединения',
    'simulations': 'Симуляции',
    'measurements': 'Измерения',
    'faults': 'Сценарии неисправностей',
    'bom_matched': 'BOM связан с каталогом',
    'bom_missing': 'BOM без связи с каталогом',
    'connected_components': 'Связные части схемы',
    'cycle_count': 'Циклы в графе',
    'topology': 'Топология',
    'expert_findings': 'Экспертные выводы',
    'fuzzy_risk_score': 'Мягкая оценка риска',
    'validity_issues': 'Выход за пределы модели',
}

METRIC_LABELS_RU.update(
    {
        'external_cad_findings': 'Внешние CAD-проверки',
        'readiness_missing': 'Пробелы готовности к сборке',
        'mtbf_hours': 'MTBF, часов',
    }
)

METRIC_ORDER = (
    'components',
    'connections',
    'topology',
    'connected_components',
    'faults',
    'expert_findings',
    'measurements',
    'simulations',
    'bom_matched',
    'bom_missing',
    'cycle_count',
    'fuzzy_risk_score',
    'validity_issues',
    'external_cad_findings',
    'readiness_missing',
    'mtbf_hours',
)

MEASUREMENT_LABELS_RU = {
    'node_voltage': 'Напряжение узла',
    'branch_current': 'Ток ветви',
    'rms_voltage': 'RMS-напряжение',
    'frequency': 'Частота',
    'duty_cycle': 'Коэффициент заполнения',
    'component_power': 'Мощность элемента',
    'junction_temperature': 'Температура перехода',
    'cutoff_frequency': 'Частота среза',
}

MEASUREMENT_STATUS_RU = {
    'ok': 'норма',
    'pass': 'норма',
    'risk': 'риск',
    'warning': 'предупреждение',
    'fail': 'ошибка',
    'error': 'ошибка',
}

RULE_TRANSLATIONS = {
    'erc.missing_ground': {
        'title': 'Нет опорного узла GND',
        'recommendation': 'Добавьте GND или опорный узел перед тем, как доверять симуляции и измерениям.',
    },
    'erc.missing_source': {
        'title': 'Нет источника питания или сигнала',
        'recommendation': 'Добавьте источник напряжения/тока или явно пометьте источник после импорта.',
    },
    'topology.floating_fragments': {
        'title': 'Есть плавающие фрагменты схемы',
        'recommendation': 'Соедините плавающие фрагменты с основной опорной цепью или удалите неиспользуемые компоненты.',
    },
    'topology.divider_without_output': {
        'title': 'У делителя не подписан выходной узел',
        'recommendation': 'Назовите среднюю точку Vout/out, чтобы лаборатория и учебные задания могли измерять ее.',
    },
    'bom.missing_catalog_binding': {
        'title': 'В BOM есть компоненты без связи с каталогом',
        'recommendation': 'Свяжите элементы схемы с товарами каталога перед экспортом BOM и оформлением заказа.',
    },
    'derating.power_or_thermal_risk': {
        'title': 'Риск по мощности или температурному запасу',
        'recommendation': 'Увеличьте запас по мощности, напряжению или току либо выберите другой корпус перед выпуском.',
    },
    'simulation.no_saved_measurements': {
        'title': 'Нет сохраненных измерений симуляции',
        'recommendation': 'Запустите DC/AC/TRAN-проверку и сохраните метрики expected vs measured.',
    },
    'import.unsupported_items': {
        'title': 'Импорт содержит неподдержанные элементы CAD/SPICE',
        'recommendation': 'Проверьте неподдержанные строки импорта перед сохранением проекта или запуском review.',
    },
    'erc.led_reverse_polarity': {
        'title': 'LED включён обратной полярностью',
        'recommendation': 'Переверните светодиод: анод должен смотреть к источнику через токоограничивающий резистор, катод — к GND.',
    },
    'erc.parallel_voltage_sources': {
        'title': 'Параллельные источники напряжения с разным номиналом',
        'recommendation': 'Уберите конфликт источников: один источник на узел или разнесите их развязывающим элементом, иначе КЗ.',
    },
    'erc.source_short_to_ground': {
        'title': 'Короткое замыкание источника на GND',
        'recommendation': 'Поставьте токоограничивающий резистор между источником и GND либо измените топологию.',
    },
    'erc.dangling_named_net': {
        'title': 'Висящий именованный узел',
        'recommendation': 'Подключите помеченный узел к схеме или удалите его метку.',
    },
    'topology.transistor_pinout_swap': {
        'title': 'Подозрительная распиновка транзистора',
        'recommendation': 'Проверьте распиновку: коллектор обычно к +V через нагрузку, эмиттер — к GND (для NPN).',
    },
}

FAULT_TRANSLATIONS = {
    'missing_ground': {
        'title': 'Нет опорного узла GND',
        'symptom': 'Рабочая точка DC может плавать, а SPICE может не сойтись или создать искусственную опору.',
        'recommendation': 'Добавьте GND и подключите к нему обратный путь цепи.',
    },
    'missing_source': {
        'title': 'Нет источника питания',
        'symptom': 'Напряжения узлов и токи ветвей остаются неопределенными или нулевыми.',
        'recommendation': 'Добавьте источник напряжения/тока и задайте его номинал.',
    },
    'open_component': {
        'title': 'Компонент не подключен',
        'symptom': 'В ветви нет тока, а показания пробников не совпадают с расчетом.',
        'recommendation': 'Подключите оба вывода компонента или удалите неиспользуемый элемент.',
    },
    'led_without_resistor': {
        'title': 'Ток LED не ограничен',
        'symptom': 'Ток светодиода может выйти за безопасную область.',
        'recommendation': 'Поставьте последовательный резистор и проверьте ток ветви.',
    },
    'power_overload': {
        'title': 'Перегрузка компонента по мощности',
        'symptom': 'Температурный запас мал, компонент может перегреться.',
        'recommendation': 'Выберите больший запас по мощности, уменьшите ток или измените топологию.',
    },
    'drc_error': {
        'title': 'Ошибка DRC',
        'recommendation': 'Исправьте ошибку DRC перед симуляцией или экспортом.',
    },
}

EXACT_TRANSLATIONS = {
    'Missing GND reference': 'Нет опорного узла GND',
    'Missing reference ground': 'Нет опорного узла GND',
    'Missing supply/source component': 'Нет источника питания или сигнала',
    'No ground reference': 'Нет опорного узла GND',
    'No supply source': 'Нет источника питания',
    'Floating schematic fragments': 'Есть плавающие фрагменты схемы',
    'Voltage divider has no named output node': 'У делителя не подписан выходной узел',
    'BOM has components without catalog binding': 'В BOM есть компоненты без связи с каталогом',
    'Power or thermal derating issue': 'Риск по мощности или температурному запасу',
    'No saved simulation measurements': 'Нет сохраненных измерений симуляции',
    'Import has unsupported CAD/SPICE items': 'Импорт содержит неподдержанные элементы CAD/SPICE',
    'Unconnected component': 'Компонент не подключен',
    'LED current is not limited': 'Ток LED не ограничен',
    'Component power overload': 'Перегрузка компонента по мощности',
    'DRC error': 'Ошибка DRC',
    'Fix the expert rule expression.': 'Исправьте условие экспертного правила.',
    'Add a GND/reference node before trusting simulation or measurements.': (
        'Добавьте GND или опорный узел перед тем, как доверять симуляции и измерениям.'
    ),
    'Add a voltage/current source or mark the imported source explicitly.': (
        'Добавьте источник напряжения/тока или явно пометьте источник после импорта.'
    ),
    'Connect floating fragments to the main reference path or remove unused components.': (
        'Соедините плавающие фрагменты с основной опорной цепью или удалите неиспользуемые компоненты.'
    ),
    'Name the midpoint node Vout/out so lab checks and learning tasks can measure it.': (
        'Назовите среднюю точку Vout/out, чтобы лаборатория и учебные задания могли измерять ее.'
    ),
    'Bind schematic components to catalog products before BOM export and ordering.': (
        'Свяжите элементы схемы с товарами каталога перед экспортом BOM и оформлением заказа.'
    ),
    'Increase power/voltage/current margin or choose another package before release.': (
        'Увеличьте запас по мощности, напряжению или току либо выберите другой корпус перед выпуском.'
    ),
    'Run at least one DC/AC/TRAN check and save expected-vs-measured metrics.': (
        'Запустите DC/AC/TRAN-проверку и сохраните метрики expected vs measured.'
    ),
    'Review unsupported import lines before saving the project or running review.': (
        'Проверьте неподдержанные строки импорта перед сохранением проекта или запуском review.'
    ),
    'Run at least one DC/AC/TRAN simulation and save the result.': (
        'Запустите хотя бы одну DC/AC/TRAN-симуляцию и сохраните результат.'
    ),
    'Bind schematic components to catalog items before BOM export.': (
        'Свяжите компоненты схемы с товарами каталога перед экспортом BOM.'
    ),
    'Add GND before relying on simulation results.': (
        'Добавьте GND перед тем, как опираться на результаты симуляции.'
    ),
    'Connect floating schematic fragments to the main reference path.': (
        'Подключите плавающие фрагменты схемы к основной опорной цепи.'
    ),
    'Review unsupported import items before saving the imported project.': (
        'Проверьте неподдержанные элементы импорта перед сохранением проекта.'
    ),
    'Add a GND symbol and connect the return path to it.': (
        'Добавьте символ GND и подключите к нему обратный путь цепи.'
    ),
    'Add a voltage/current source and define its nominal value.': (
        'Добавьте источник напряжения/тока и задайте его номинал.'
    ),
    'Connect both pins or remove the unused component.': (
        'Подключите оба вывода или удалите неиспользуемый компонент.'
    ),
    'Place a series resistor and verify branch current.': (
        'Поставьте последовательный резистор и проверьте ток ветви.'
    ),
    'Choose a higher power rating, reduce current, or change topology.': (
        'Выберите больший запас по мощности, уменьшите ток или измените топологию.'
    ),
    'Fix the DRC error before simulation or export.': (
        'Исправьте ошибку DRC перед симуляцией или экспортом.'
    ),
    'DC operating point may float; SPICE can fail or create an artificial reference.': (
        'Рабочая точка DC может плавать, а SPICE может не сойтись или создать искусственную опору.'
    ),
    'Node voltages and branch currents stay undefined or zero.': (
        'Напряжения узлов и токи ветвей остаются неопределенными или нулевыми.'
    ),
    'A branch has no current; probe readings do not match calculations.': (
        'В ветви нет тока, показания пробников не совпадают с расчетом.'
    ),
    'LED current can exceed the safe region.': 'Ток LED может выйти за безопасную область.',
    'Thermal margin is low; the part can overheat.': (
        'Температурный запас мал, компонент может перегреться.'
    ),
}

EXACT_TRANSLATIONS.update(
    {
        'Manufacturing readiness: some components miss package, ratings or BOM binding.': (
            'Готовность к сборке: у части компонентов не хватает корпуса, предельных режимов или связи с BOM.'
        ),
        'Review imported CAD DRC/ERC findings before relying on this project session.': (
            'Проверьте импортированные DRC/ERC-замечания CAD перед использованием сеанса проектирования.'
        ),
        'Complete assembly readiness: package, ratings, footprint/model and BOM binding.': (
            'Закройте готовность к сборке: корпус, предельные режимы, footprint/model и связь с BOM.'
        ),
        'Short circuit between nets': 'Короткое замыкание между сетями',
        'Element or trace outside board outline': 'Элемент или дорожка вне границы платы',
        'Net connected to uncommitted pin': 'Сеть подключена к неподтвержденному выводу',
        'Imported DRC finding': 'Импортированное замечание DRC',
        'Separate the shorted nets and rerun DRC.': 'Разведите замкнутые сети и повторно запустите DRC.',
        'Move the element or route inside the board outline.': 'Переместите элемент или трассу внутрь контура платы.',
        'Check the symbol pin mapping and commit/connect the pin.': 'Проверьте соответствие выводов символа и подключите вывод.',
        'Inspect imported CAD evidence before release.': 'Проверьте evidence из импортированного CAD перед выпуском.',
    }
)


def status_label_ru(status: str) -> str:
    return STATUS_LABELS_RU.get(str(status or '').strip(), str(status or ''))


def severity_label_ru(severity: str) -> str:
    return SEVERITY_LABELS_RU.get(str(severity or '').strip(), str(severity or ''))


def topology_label_ru(topology: str) -> str:
    return TOPOLOGY_LABELS_RU.get(str(topology or '').strip(), str(topology or ''))


def metric_label_ru(metric: str) -> str:
    return METRIC_LABELS_RU.get(str(metric or '').strip(), str(metric or ''))


def measurement_label_ru(metric: str) -> str:
    return MEASUREMENT_LABELS_RU.get(str(metric or '').strip(), metric_label_ru(metric))


def measurement_status_ru(status: str) -> str:
    return MEASUREMENT_STATUS_RU.get(str(status or '').strip(), str(status or ''))


def _format_scalar(value: Any) -> str:
    if value is None:
        return 'нет данных'
    if isinstance(value, bool):
        return 'да' if value else 'нет'
    if isinstance(value, float):
        return f'{value:g}'
    return str(value)


def format_metric_value(key: str, value: Any) -> str:
    if key == 'topology':
        return topology_label_ru(value)
    if isinstance(value, (list, tuple, set)):
        return str(len(value))
    if isinstance(value, dict):
        return str(len(value))
    return _format_scalar(value)


def build_metric_rows(metrics: dict[str, Any]) -> list[dict[str, str]]:
    if not isinstance(metrics, dict):
        return []
    rows = []
    ordered_keys = [key for key in METRIC_ORDER if key in metrics]
    ordered_keys.extend(key for key in metrics.keys() if key not in ordered_keys)
    for key in ordered_keys:
        rows.append(
            {
                'key': key,
                'label': metric_label_ru(key),
                'value': format_metric_value(key, metrics.get(key)),
            }
        )
    return rows


def build_measurement_rows(sections: dict[str, Any]) -> list[dict[str, str]]:
    if not isinstance(sections, dict):
        return []
    measurements = sections.get('measurements') or {}
    if not isinstance(measurements, dict):
        return []

    rows = []
    for metric, payload in measurements.items():
        if isinstance(payload, dict):
            label = payload.get('label') or measurement_label_ru(metric)
            unit = payload.get('unit') or ''
            value = payload.get('value')
            expected = payload.get('expected') or payload.get('expected_value')
            tolerance = payload.get('tolerance') or payload.get('tolerance_value')
            status = measurement_status_ru(payload.get('status') or '')
            row = {
                'metric': str(metric),
                'label': str(label),
                'value': f'{_format_scalar(value)} {unit}'.strip(),
                'status': status or 'сохранено',
            }
            if expected is not None:
                row['expected'] = f'{_format_scalar(expected)} {unit}'.strip()
                # Delta + automatic status if not provided by upstream layer.
                try:
                    delta = float(value) - float(expected)
                    row['delta'] = f'{delta:+g} {unit}'.strip()
                    if not payload.get('status') and tolerance is not None:
                        try:
                            tol = abs(float(tolerance))
                            base = abs(float(expected)) or 1.0
                            ratio = abs(delta) / base
                            row['status'] = 'норма' if ratio <= tol else 'ошибка'
                        except (TypeError, ValueError):
                            pass
                except (TypeError, ValueError):
                    pass
            if tolerance is not None:
                row['tolerance'] = f'{_format_scalar(tolerance)}'
            rows.append(row)
        else:
            rows.append(
                {
                    'metric': str(metric),
                    'label': measurement_label_ru(metric),
                    'value': _format_scalar(payload),
                    'status': 'из симуляции',
                }
            )
    return rows


def translate_review_text(value: Any) -> Any:
    """Translate known review/check strings while preserving unknown data."""
    if isinstance(value, list):
        return [translate_review_text(item) for item in value]
    if isinstance(value, tuple):
        return tuple(translate_review_text(item) for item in value)
    if isinstance(value, dict):
        return {key: translate_review_text(item) for key, item in value.items()}
    if not isinstance(value, str):
        return value

    text = value.strip()
    if not text:
        return value
    if text in EXACT_TRANSLATIONS:
        return EXACT_TRANSLATIONS[text]

    if ': ' in text:
        head, tail = text.split(': ', 1)
        translated_head = translate_review_text(head)
        translated_tail = translate_review_text(tail)
        if translated_head != head or translated_tail != tail:
            return f'{translated_head}: {translated_tail}'

    match = re.fullmatch(r'Graph topology: (.+)', text)
    if match:
        return f'Граф схемы: {translate_review_text(match.group(1))}'

    match = re.fullmatch(r'catalog item not found: (.+)', text)
    if match:
        return f'товар каталога не найден: {match.group(1)}'

    match = re.fullmatch(r'category mismatch: expected ([^,]+), got (.+)', text)
    if match:
        return f'несовпадение категории: ожидается {match.group(1)}, получено {match.group(2)}'

    match = re.fullmatch(r'lifecycle status is (.+)', text)
    if match:
        return f'статус жизненного цикла: {match.group(1)}'

    if text == 'catalog item is out of stock':
        return 'товар каталога отсутствует на складе'

    match = re.fullmatch(r'power derating (.+)', text)
    if match:
        return f'запас по мощности: {match.group(1)}'

    match = re.fullmatch(r'thermal margin (.+) C', text)
    if match:
        return f'тепловой запас: {match.group(1)} °C'

    match = re.fullmatch(r'Detected topology: ([^;]+); use matching lab checks for expected values\.', text)
    if match:
        return (
            f'Определена топология: {topology_label_ru(match.group(1))}; '
            'используйте соответствующие проверки лаборатории для ожидаемых значений.'
        )

    match = re.fullmatch(r'(\d+) components, (\d+) connections, (\d+) errors, (\d+) warnings\.', text)
    if match:
        components, connections, errors, warnings = match.groups()
        return (
            f'{components} компонентов, {connections} соединений, {errors} ошибок, {warnings} предупреждений.'
        )

    return value


def translate_fault(fault: dict[str, Any]) -> dict[str, Any]:
    item = copy.deepcopy(fault)
    translated = FAULT_TRANSLATIONS.get(str(item.get('code') or ''))
    if translated:
        item.update({key: value for key, value in translated.items() if value})
    for key in ('title', 'symptom', 'recommendation'):
        if key in item:
            item[key] = translate_review_text(item[key])
    return item


def translate_finding(finding: dict[str, Any]) -> dict[str, Any]:
    item = copy.deepcopy(finding)
    translated = RULE_TRANSLATIONS.get(str(item.get('rule_id') or item.get('id') or ''))
    if translated:
        item['title'] = translated.get('title', item.get('title'))
        item['recommendation'] = translated.get('recommendation', item.get('recommendation'))
    item['title'] = translate_review_text(item.get('title', ''))
    item['recommendation'] = translate_review_text(item.get('recommendation', ''))
    if 'evidence' in item:
        item['evidence_ru'] = translate_review_text(item.get('evidence'))
    item['title_ru'] = item.get('title', '')
    item['recommendation_ru'] = item.get('recommendation', '')
    item['severity_label'] = severity_label_ru(item.get('severity', ''))
    return item


def translate_expert_result(expert: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(expert or {})
    result['findings'] = [translate_finding(item) for item in result.get('findings') or []]
    return result


def _dedup_messages(messages):
    """Return list of messages with duplicates removed, preserving order.

    Used to collapse review messages that come from multiple layers
    (validation + project_review + expert findings) but describe the same
    issue after translation, e.g. several variants of «Нет опорного узла GND».
    Dedup is by normalized text (case-insensitive, whitespace-collapsed)
    плюс по семантическому ядру: если в сообщении найдено известное «ядро»
    (GND, источник питания, компоненты без соединений), оно объединяется,
    даже если обёртки сообщений отличаются.
    """
    if not isinstance(messages, (list, tuple)):
        return messages
    seen_norm = set()
    seen_cores = set()
    deduped = []
    for item in messages:
        if not isinstance(item, str):
            deduped.append(item)
            continue
        norm = re.sub(r'\s+', ' ', item.strip()).lower()
        if not norm:
            continue
        if norm in seen_norm:
            continue
        core = _semantic_core(norm)
        if core and core in seen_cores:
            continue
        seen_norm.add(norm)
        if core:
            seen_cores.add(core)
        deduped.append(item)
    return deduped


_SEMANTIC_CORE_PATTERNS = (
    ('missing_ground', re.compile(r'нет\s+опорного\s+узла\s+gnd|gnd:\s+симулятор|нет\s+gnd', re.IGNORECASE)),
    (
        'missing_source',
        re.compile(r'нет\s+источника\s+питания|нет\s+источника\s+питания\s+или\s+сигнала', re.IGNORECASE),
    ),
    ('unconnected', re.compile(r'компоненты\s+без\s+соединений|компонент\s+не\s+подключен', re.IGNORECASE)),
    ('floating', re.compile(r'плавающие\s+фрагменты', re.IGNORECASE)),
)


def _semantic_core(normalized_text):
    for core, pattern in _SEMANTIC_CORE_PATTERNS:
        if pattern.search(normalized_text):
            return core
    return None


def localize_review_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a build_design_review payload with Russian user text."""
    localized = copy.deepcopy(report or {})
    status = localized.get('status')
    localized['status_label'] = status_label_ru(status)
    localized['summary'] = translate_review_text(localized.get('summary', ''))
    localized['errors'] = _dedup_messages(translate_review_text(localized.get('errors') or []))
    localized['warnings'] = _dedup_messages(translate_review_text(localized.get('warnings') or []))
    localized['recommendations'] = _dedup_messages(
        translate_review_text(localized.get('recommendations') or [])
    )
    localized['faults'] = [translate_fault(item) for item in localized.get('faults') or []]
    localized['expert_findings'] = [
        translate_finding(item) for item in localized.get('expert_findings') or []
    ]

    sections = localized.get('sections') or {}
    if isinstance(sections, dict):
        if isinstance(sections.get('drc'), dict):
            sections['drc']['errors'] = _dedup_messages(
                translate_review_text(sections['drc'].get('errors') or [])
            )
            sections['drc']['warnings'] = _dedup_messages(
                translate_review_text(sections['drc'].get('warnings') or [])
            )
        if isinstance(sections.get('connectivity'), dict):
            sections['connectivity']['graph_errors'] = _dedup_messages(
                translate_review_text(sections['connectivity'].get('graph_errors') or [])
            )
            sections['connectivity']['graph_warnings'] = _dedup_messages(
                translate_review_text(sections['connectivity'].get('graph_warnings') or [])
            )
            sections['connectivity']['topology_label'] = topology_label_ru(
                sections['connectivity'].get('topology', '')
            )
        if isinstance(sections.get('bom'), dict):
            for risk in sections['bom'].get('risks') or []:
                if isinstance(risk, dict) and 'message' in risk:
                    risk['message'] = translate_review_text(risk['message'])
        if isinstance(sections.get('derating'), dict):
            for issue in sections['derating'].get('issues') or []:
                if isinstance(issue, dict) and 'message' in issue:
                    issue['message'] = translate_review_text(issue['message'])
        if isinstance(sections.get('expert_system'), dict):
            sections['expert_system'] = translate_expert_result(sections['expert_system'])
        if isinstance(sections.get('external_cad'), dict):
            sections['external_cad']['findings'] = [
                translate_finding(item) for item in sections['external_cad'].get('findings') or []
            ]
    return localized
