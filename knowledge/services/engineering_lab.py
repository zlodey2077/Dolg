import math

from Dolg_APP.services.engineering_units import parse_engineering_number

try:
    from pyeng.general.validation import validate_float as _pyeng_validate_float
except Exception:  # pragma: no cover - optional dependency fallback
    _pyeng_validate_float = None


ENGINEERING_VALIDATION_BACKEND = 'python-engineering' if _pyeng_validate_float else 'builtin'


STATUS_LABELS = {
    'ok': 'норма',
    'risk': 'риск',
    'overheat': 'перегрев',
    'needs_margin': 'нужен запас',
}


LAB_TOOLS = [
    {
        'kind': 'transistor_switch',
        'title': 'Транзисторный ключ',
        'description': 'Расчет базового резистора, резистора нагрузки и мощности транзистора в ключевом режиме.',
        'fields': [
            {'name': 'supply_voltage', 'label': 'Питание', 'unit': 'В', 'default': 5},
            {'name': 'load_voltage', 'label': 'Падение на нагрузке', 'unit': 'В', 'default': 2},
            {'name': 'load_current_ma', 'label': 'Ток нагрузки', 'unit': 'мА', 'default': 20},
            {'name': 'input_voltage', 'label': 'Управляющее напряжение', 'unit': 'В', 'default': 5},
            {'name': 'forced_beta', 'label': 'Принудительный hFE', 'unit': '×', 'default': 10},
            {'name': 'vbe', 'label': 'Vbe', 'unit': 'В', 'default': 0.7},
            {'name': 'vce_sat', 'label': 'Vce(sat)', 'unit': 'В', 'default': 0.2},
        ],
    },
    {
        'kind': 'ne555_astable',
        'title': 'Генератор NE555',
        'description': 'Частота, времена высокого/низкого уровня и скважность астабильного генератора.',
        'fields': [
            {'name': 'r1_ohm', 'label': 'R1', 'unit': 'Ом', 'default': '10k'},
            {'name': 'r2_ohm', 'label': 'R2', 'unit': 'Ом', 'default': '68k'},
            {'name': 'capacitance_f', 'label': 'C', 'unit': 'Ф', 'default': '100n'},
        ],
    },
    {
        'kind': 'linear_regulator',
        'title': 'Линейный стабилизатор',
        'description': 'Падение напряжения, рассеиваемая мощность и температура кристалла.',
        'fields': [
            {'name': 'vin', 'label': 'Vin', 'unit': 'В', 'default': 12},
            {'name': 'vout', 'label': 'Vout', 'unit': 'В', 'default': 5},
            {'name': 'load_current_ma', 'label': 'Ток нагрузки', 'unit': 'мА', 'default': 250},
            {'name': 'dropout_voltage', 'label': 'Dropout', 'unit': 'В', 'default': 2},
            {'name': 'theta_ja', 'label': 'RθJA', 'unit': '°C/Вт', 'default': 50},
            {'name': 'ambient_c', 'label': 'Температура среды', 'unit': '°C', 'default': 25},
            {'name': 'max_junction_c', 'label': 'Tj max', 'unit': '°C', 'default': 125},
        ],
    },
    {
        'kind': 'rc_debounce',
        'title': 'RC-антидребезг',
        'description': 'Постоянная времени, время установления и частота среза цепи кнопки.',
        'fields': [
            {'name': 'resistance_ohm', 'label': 'R', 'unit': 'Ом', 'default': '10k'},
            {'name': 'capacitance_f', 'label': 'C', 'unit': 'Ф', 'default': '100n'},
        ],
    },
    {
        'kind': 'thermal_margin',
        'title': 'Тепловой запас',
        'description': 'Оценка температуры кристалла и запаса до предельного значения.',
        'fields': [
            {'name': 'power_w', 'label': 'Мощность', 'unit': 'Вт', 'default': 1.5},
            {'name': 'theta_ja', 'label': 'RθJA', 'unit': '°C/Вт', 'default': 50},
            {'name': 'ambient_c', 'label': 'Температура среды', 'unit': '°C', 'default': 25},
            {'name': 'max_junction_c', 'label': 'Tj max', 'unit': '°C', 'default': 125},
        ],
    },
]


LAB_TOOL_MAP = {item['kind']: item for item in LAB_TOOLS}


def _parse_number(value, default=None):
    parsed = parse_engineering_number(value, default=default)
    return parsed if parsed is not None else default


def _input(payload, name, default=None, scale=1.0):
    value = _parse_number((payload or {}).get(name), default) * scale
    if _pyeng_validate_float is not None:
        _pyeng_validate_float(name, value)
    return value


def _output(label, value, unit='', digits=3):
    if value is None or not math.isfinite(value):
        display = 'не рассчитано'
    elif abs(value) >= 1000 or (0 < abs(value) < 0.01):
        display = f'{value:.{digits}g}'
    else:
        display = f'{value:.{digits}f}'.rstrip('0').rstrip('.')
    return {'label': label, 'value': value, 'unit': unit, 'display': display}


def _status(status, feedback, warnings=None):
    return {
        'status': status,
        'status_label': STATUS_LABELS.get(status, status),
        'feedback': feedback,
        'warnings': warnings or [],
    }


def _thermal_status(junction_c, max_junction_c, dropout_margin=None):
    margin = max_junction_c - junction_c
    if dropout_margin is not None and dropout_margin < 0:
        return _status(
            'needs_margin', 'Входного напряжения не хватает для стабильной работы линейного стабилизатора.'
        )
    if junction_c >= max_junction_c:
        return _status(
            'overheat',
            'Расчетная температура выше допустимой: нужен радиатор, меньший ток или другой узел питания.',
        )
    if margin < 20:
        return _status('risk', 'Запас по температуре меньше 20 °C: схема работает на грани.')
    return _status('ok', 'Тепловой режим выглядит нормально, запас достаточный.')


def calculate_lab(kind, payload):
    calculators = {
        'transistor_switch': _calculate_transistor_switch,
        'ne555_astable': _calculate_ne555_astable,
        'linear_regulator': _calculate_linear_regulator,
        'rc_debounce': _calculate_rc_debounce,
        'thermal_margin': _calculate_thermal_margin,
    }
    if kind not in calculators:
        return {
            'ok': False,
            'kind': kind,
            'error': 'unknown_lab_tool',
            'feedback': 'Неизвестный расчет инженерной лаборатории.',
        }
    result = calculators[kind](payload or {})
    result.update(
        {
            'ok': True,
            'kind': kind,
            'title': LAB_TOOL_MAP[kind]['title'],
            'validation_backend': ENGINEERING_VALIDATION_BACKEND,
        }
    )
    return result


def _calculate_transistor_switch(payload):
    supply = _input(payload, 'supply_voltage', 5)
    load_voltage = _input(payload, 'load_voltage', 2)
    load_current = _input(payload, 'load_current_ma', 20, scale=1e-3)
    input_voltage = _input(payload, 'input_voltage', 5)
    forced_beta = max(_input(payload, 'forced_beta', 10), 1)
    vbe = _input(payload, 'vbe', 0.7)
    vce_sat = _input(payload, 'vce_sat', 0.2)

    base_current = load_current / forced_beta
    base_resistor = (input_voltage - vbe) / base_current if base_current > 0 else math.inf
    load_resistor = (supply - load_voltage - vce_sat) / load_current if load_current > 0 else math.inf
    transistor_power = vce_sat * load_current
    base_power = (input_voltage - vbe) * base_current

    if input_voltage <= vbe:
        assessment = _status('needs_margin', 'Управляющее напряжение ниже Vbe: ключ не откроется надежно.')
    elif load_resistor <= 0:
        assessment = _status(
            'risk', 'Для выбранного питания и нагрузки не остается напряжения на резистор нагрузки.'
        )
    elif transistor_power > 0.5:
        assessment = _status('risk', 'Мощность на транзисторе уже заметная: проверьте корпус и радиатор.')
    else:
        assessment = _status('ok', 'Ключ выглядит рабочим: базовый ток задан с запасом, мощность мала.')

    return {
        **assessment,
        'outputs': {
            'base_current_ma': _output('Ток базы', base_current * 1000, 'мА'),
            'base_resistor_ohm': _output('Базовый резистор', base_resistor, 'Ом'),
            'load_resistor_ohm': _output('Резистор нагрузки', load_resistor, 'Ом'),
            'transistor_power_w': _output('Мощность транзистора', transistor_power, 'Вт'),
            'base_power_w': _output('Мощность базового резистора', base_power, 'Вт'),
        },
    }


def _calculate_ne555_astable(payload):
    r1 = max(_input(payload, 'r1_ohm', 10e3), 1e-9)
    r2 = max(_input(payload, 'r2_ohm', 68e3), 1e-9)
    capacitance = max(_input(payload, 'capacitance_f', 100e-9), 1e-15)

    high_time = 0.693 * (r1 + r2) * capacitance
    low_time = 0.693 * r2 * capacitance
    period = high_time + low_time
    frequency = 1 / period
    duty_cycle = high_time / period * 100

    if duty_cycle > 80:
        assessment = _status(
            'risk', 'Скважность сильно смещена к высокому уровню: для симметрии нужна другая схема или диод.'
        )
    elif frequency > 100_000:
        assessment = _status(
            'risk', 'Частота высоковата для базового NE555: проверьте datasheet и паразитные емкости.'
        )
    else:
        assessment = _status('ok', 'Режим генератора выглядит нормальным для учебной астабильной схемы.')

    return {
        **assessment,
        'outputs': {
            'frequency_hz': _output('Частота', frequency, 'Гц'),
            'high_time_s': _output('Время высокого уровня', high_time, 'с'),
            'low_time_s': _output('Время низкого уровня', low_time, 'с'),
            'duty_cycle_percent': _output('Duty cycle', duty_cycle, '%'),
            'period_s': _output('Период', period, 'с'),
        },
    }


def _calculate_linear_regulator(payload):
    vin = _input(payload, 'vin', 12)
    vout = _input(payload, 'vout', 5)
    load_current = _input(payload, 'load_current_ma', 250, scale=1e-3)
    dropout = _input(payload, 'dropout_voltage', 2)
    theta_ja = _input(payload, 'theta_ja', 50)
    ambient = _input(payload, 'ambient_c', 25)
    max_junction = _input(payload, 'max_junction_c', 125)

    voltage_drop = vin - vout
    dropout_margin = voltage_drop - dropout
    power = max(voltage_drop, 0) * load_current
    junction = ambient + power * theta_ja
    assessment = _thermal_status(junction, max_junction, dropout_margin)

    return {
        **assessment,
        'outputs': {
            'dropout_margin_v': _output('Запас по dropout', dropout_margin, 'В'),
            'power_w': _output('Рассеиваемая мощность', power, 'Вт'),
            'junction_temperature_c': _output('Температура кристалла', junction, '°C'),
            'thermal_margin_c': _output('Запас до Tj max', max_junction - junction, '°C'),
        },
    }


def _calculate_rc_debounce(payload):
    resistance = max(_input(payload, 'resistance_ohm', 10e3), 1e-9)
    capacitance = max(_input(payload, 'capacitance_f', 100e-9), 1e-15)
    tau = resistance * capacitance
    settle_3tau = 3 * tau
    settle_5tau = 5 * tau
    cutoff = 1 / (2 * math.pi * resistance * capacitance)

    if tau < 0.001:
        assessment = _status('risk', 'Постоянная времени мала: дребезг кнопки может пройти дальше.')
    elif tau > 0.2:
        assessment = _status('risk', 'Постоянная времени велика: интерфейс будет заметно тормозить.')
    else:
        assessment = _status('ok', 'RC-цепь дает разумную задержку для подавления дребезга.')

    return {
        **assessment,
        'outputs': {
            'time_constant_s': _output('Постоянная времени τ', tau, 'с'),
            'settle_3tau_s': _output('Установление 3τ', settle_3tau, 'с'),
            'settle_5tau_s': _output('Установление 5τ', settle_5tau, 'с'),
            'cutoff_frequency_hz': _output('Частота среза', cutoff, 'Гц'),
        },
    }


def _calculate_thermal_margin(payload):
    power = _input(payload, 'power_w', 1.5)
    theta_ja = _input(payload, 'theta_ja', 50)
    ambient = _input(payload, 'ambient_c', 25)
    max_junction = _input(payload, 'max_junction_c', 125)

    junction = ambient + power * theta_ja
    assessment = _thermal_status(junction, max_junction)

    return {
        **assessment,
        'outputs': {
            'junction_temperature_c': _output('Температура кристалла', junction, '°C'),
            'thermal_margin_c': _output('Запас до Tj max', max_junction - junction, '°C'),
            'temperature_rise_c': _output('Нагрев относительно среды', power * theta_ja, '°C'),
        },
    }


def lab_expected_value(config):
    config = config or {}
    result = calculate_lab(config.get('kind'), config.get('inputs') or {})
    output = config.get('output')
    value = (result.get('outputs') or {}).get(output, {}).get('value')
    if value is None:
        raise ValueError(f'lab output is not available: {output}')
    return value


def extract_measurement(simulation_result, metric, rubric=None):
    rubric = rubric or {}
    if not isinstance(simulation_result, dict):
        return None

    aliases = {
        'node_voltage': ('node_voltage', 'voltage', 'vout'),
        'branch_current': ('branch_current', 'current'),
        'rms': ('rms', 'vrms'),
        'frequency': ('frequency', 'freq', 'f'),
        'duty_cycle': ('duty_cycle', 'dutyCycle', 'duty'),
        'cutoff_frequency': ('cutoff_frequency', 'f_cutoff', 'f3db', 'cutoffFrequency'),
        'component_power': ('component_power', 'power', 'dissipation'),
        'junction_temperature': ('junction_temperature', 'junctionTemperature', 'temperature'),
        'time_constant': ('time_constant', 'tau'),
    }
    keys = (metric,) + aliases.get(metric, ())
    metrics = simulation_result.get('metrics') if isinstance(simulation_result.get('metrics'), dict) else {}
    for key in keys:
        if key in metrics:
            return _parse_number(metrics[key])
        if key in simulation_result:
            return _parse_number(simulation_result[key])

    if metric == 'node_voltage':
        node = str(rubric.get('node') or rubric.get('target_node') or '')
        for node_map in (
            simulation_result.get('node_voltages'),
            simulation_result.get('nodeVoltages'),
            simulation_result.get('voltages'),
        ):
            if isinstance(node_map, dict):
                if node and node in node_map:
                    return _parse_number(node_map[node])
                if not node:
                    for value in node_map.values():
                        parsed = _parse_number(value)
                        if parsed is not None:
                            return parsed

    if metric == 'branch_current':
        branch = str(rubric.get('branch') or rubric.get('component') or '')
        for current_map in (
            simulation_result.get('branch_currents'),
            simulation_result.get('branchCurrents'),
            simulation_result.get('currents'),
        ):
            if isinstance(current_map, dict) and branch in current_map:
                return _parse_number(current_map[branch])

    if metric == 'component_power':
        component = str(rubric.get('component') or rubric.get('element') or '')
        powers = simulation_result.get('powers')
        if isinstance(powers, dict) and component in powers:
            return _parse_number(powers[component])

    if metric == 'cutoff_frequency':
        ac = simulation_result.get('ac') if isinstance(simulation_result.get('ac'), dict) else {}
        for key in ('f3db', 'cutoff_frequency', 'cutoffFrequency'):
            if key in ac:
                return _parse_number(ac[key])

    return None


def evaluate_measurement(metric, value, rubric):
    rubric = rubric or {}
    if value is None:
        return {
            'correct': False,
            'status': 'risk',
            'status_label': STATUS_LABELS['risk'],
            'feedback': f'Не удалось найти измерение {metric}.',
        }

    if 'expected_range' in rubric or 'range' in rubric:
        low, high = rubric.get('expected_range') or rubric.get('range')
        correct = float(low) <= value <= float(high)
        expected_text = f'{low:g}...{high:g}'
    else:
        expected = float(rubric.get('expected_value'))
        tolerance = float(rubric.get('tolerance_abs') or rubric.get('tolerance') or 0)
        if rubric.get('tolerance_percent'):
            tolerance = max(tolerance, abs(expected) * float(rubric['tolerance_percent']) / 100)
        correct = abs(value - expected) <= tolerance
        expected_text = f'{expected:g} ± {tolerance:g}'

    unit = rubric.get('unit', '')
    if correct:
        return {
            'correct': True,
            'status': 'ok',
            'status_label': STATUS_LABELS['ok'],
            'feedback': f'Измерение в норме: {metric} = {value:g} {unit}.',
        }
    return {
        'correct': False,
        'status': 'risk',
        'status_label': STATUS_LABELS['risk'],
        'feedback': f'Измерение вне допуска: {metric} = {value:g} {unit}, ожидается {expected_text} {unit}.',
    }
