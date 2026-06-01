"""Эвристики для AI-pipeline (Фаза 1).

Все функции принимают scheme_data в формате, который сохраняет редактор
DOLG (см. simulation.html buildSchemeData):
  scheme_data = {
    'components': [{'id', 'type', 'x', 'y', 'ports', 'resistance', ...}, ...],
    'connections': [{'from': {compId, portId}, 'to': {compId, portId}, 'waypoints'}, ...]
  }

После переходa на Phase 2 (нейронные модели) эти функции остаются как
fallback / baseline для сравнения метрик.
"""
from collections import Counter, defaultdict

# Типы компонентов: «активные» = вносят энергию или нелинейность.
ACTIVE_TYPES = {'battery', 'led', 'diode', 'npn', 'pnp', 'transistor', 'ic'}
PASSIVE_TYPES = {'resistor', 'capacitor', 'inductor'}
INFRASTRUCTURE_TYPES = {'ground', 'node', 'switch'}


def schema_to_graph(scheme_data: dict) -> dict:
    """Строит adjacency-list по components+connections.
    Возвращает {comp_id: set(neighbors_comp_ids)}.
    """
    graph = defaultdict(set)
    for comp in scheme_data.get('components', []) or []:
        graph[comp['id']]   # ensure node exists даже без рёбер
    for conn in scheme_data.get('connections', []) or []:
        f = (conn.get('from') or {}).get('compId')
        t = (conn.get('to') or {}).get('compId')
        if f is not None and t is not None:
            graph[f].add(t)
            graph[t].add(f)
    return dict(graph)


def count_components_by_type(scheme_data: dict) -> dict:
    """Counter по comp.type."""
    return dict(Counter(
        c.get('type', 'unknown')
        for c in (scheme_data.get('components') or [])
    ))


def find_isolated_nodes(graph: dict, scheme_data: dict) -> list:
    """Возвращает list[anomaly] для каждого изолированного компонента
    (нет ни одного соединения). Кроме ground/node — они часто placeholders."""
    components = {c['id']: c for c in (scheme_data.get('components') or [])}
    anomalies = []
    for comp_id, neighbors in graph.items():
        if not neighbors:
            comp = components.get(comp_id)
            if not comp:
                continue
            if comp.get('type') in INFRASTRUCTURE_TYPES:
                continue   # ground/node без связей — допустимо при сборке
            anomalies.append({
                'type': 'isolated_node',
                'severity': 'warning',
                'message': f'{comp.get("label", comp.get("type"))} не подключен ни к одной цепи.',
                'component_ids': [comp_id],
            })
    return anomalies


def find_cycles_without_active(graph: dict, scheme_data: dict) -> list:
    """Грубая проверка: если есть цикл из 2+ компонентов и все они passive
    (R/L/C только), это подозрительно для DC-схемы — нет источника тока.

    Returns: list[anomaly]
    """
    # Простейшая проверка: если ВО ВСЕЙ схеме нет ни одного active-компонента —
    # это аномалия для самой схемы. Полный cycle-detection — overkill для Phase 1.
    has_active = any(
        c.get('type') in ACTIVE_TYPES
        for c in (scheme_data.get('components') or [])
    )
    if not has_active and len(scheme_data.get('components') or []) >= 2:
        return [{
            'type': 'no_active_components',
            'severity': 'warning',
            'message': 'В схеме нет источника питания (battery / led / транзистора). '
                       'SPICE-симуляция вернёт тривиальный результат.',
            'component_ids': [],
        }]
    return []


def detect_topology_pattern(scheme_data: dict) -> str:
    """Грубая классификация топологии: 'rc_filter', 'voltage_divider',
    'bridge_rectifier', 'amplifier', 'ladder', 'parallel_loads', 'unknown'.

    Phase 2: заменится на GNN-классификатор с обучением на demo-проектах.
    """
    types = count_components_by_type(scheme_data)
    n_r = types.get('resistor', 0)
    n_c = types.get('capacitor', 0)
    n_l = types.get('inductor', 0)
    n_d = types.get('diode', 0)
    n_t = types.get('npn', 0) + types.get('pnp', 0) + types.get('transistor', 0)
    n_b = types.get('battery', 0)

    # Эвристика 1: 1 battery + 1+ резисторов + 1+ конденсаторов → RC-фильтр
    if n_b == 1 and n_r >= 1 and n_c >= 1 and n_t == 0 and n_d == 0:
        if n_r == 1 and n_c == 1:
            return 'rc_filter'
        return 'cascade_rc'

    # Эвристика 2: 1 battery + 2 резистора без C/L → делитель напряжения
    if n_b == 1 and n_r == 2 and n_c == 0 and n_l == 0 and n_t == 0:
        return 'voltage_divider'

    # Эвристика 3: 4 диода + 1 battery → мост Греца
    if n_d == 4 and n_b == 1:
        return 'bridge_rectifier'

    # Эвристика 4: транзисторы есть → усилитель
    if n_t >= 1 and n_b >= 1:
        return 'amplifier' if n_t >= 2 else 'transistor_circuit'

    # Эвристика 5: много резисторов + много конденсаторов = RC-каскад
    if n_r >= 5 and n_c >= 5:
        return 'cascade_rc'

    # Эвристика 6: только резисторы (без C/L) с одним battery → R-сетка
    if n_r >= 4 and n_c == 0 and n_l == 0 and n_b == 1:
        return 'ladder' if n_r >= 10 else 'parallel_loads'

    # Эвристика 7: LC-tank
    if n_l >= 1 and n_c >= 1 and n_b >= 1:
        return 'lc_tank'

    return 'unknown'


_USE_CASE_DESCRIPTIONS = {
    'rc_filter':        'Фильтрация частот: вход → пропускает медленные сигналы, '
                        'отрезает быстрые. Типовая частота среза fc = 1/(2πRC).',
    'cascade_rc':       'Многокаскадная фильтрация. Каждая ступень усиливает '
                        'спад в полосе задерживания на 20 дБ/декада.',
    'voltage_divider':  'Опорное напряжение для ADC: Vout = Vin × R2/(R1+R2). '
                        'Часто используется для контроля заряда батареи.',
    'bridge_rectifier': 'Преобразование AC → DC. На выходе пульсирующее '
                        'однополярное напряжение, после фильтра C — гладкое DC.',
    'amplifier':        'Усилитель малого сигнала. R_c/R_e задаёт коэффициент усиления. '
                        'Каждый каскад добавляет ≈10× усиления.',
    'transistor_circuit': 'Транзисторная цепь: коммутатор, ключ или усилитель класса A.',
    'lc_tank':          'Резонансный контур. f₀ = 1/(2π√LC). Применяется в радиоприёмниках, '
                        'генераторах, передатчиках.',
    'ladder':            'R-2R лестница. Эквивалентное сопротивление каждой ступени = R. '
                        'Используется в DAC (цифро-аналоговых преобразователях).',
    'parallel_loads':   'Параллельные нагрузки. Общий ток = сумма токов через каждое плечо.',
    'unknown':          'Нестандартная топология. Возможно, пользовательская сборка для '
                        'специфической задачи.',
}

_TITLE_BY_TOPOLOGY = {
    'rc_filter':         'RC-фильтр',
    'cascade_rc':        'RC-каскад',
    'voltage_divider':   'Делитель напряжения',
    'bridge_rectifier':  'Мостовой выпрямитель (мост Греца)',
    'amplifier':         'Усилитель',
    'transistor_circuit': 'Транзисторная цепь',
    'lc_tank':           'LC-резонансный контур',
    'ladder':            'Резистивная R-2R лестница',
    'parallel_loads':    'Параллельные нагрузки',
    'unknown':           'Пользовательская схема',
}


def generate_scheme_description(scheme_data: dict) -> dict:
    """Phase 1 description-generator. Phase 2: small Transformer."""
    components = scheme_data.get('components', []) or []
    types = count_components_by_type(scheme_data)
    topology = detect_topology_pattern(scheme_data)

    n_total = len(components)
    # Удалим infrastructure из summary count для краткости
    significant_types = {k: v for k, v in types.items()
                         if k not in INFRASTRUCTURE_TYPES}

    # Текстовое перечисление: «3 резистора, 2 конденсатора, 1 батарея»
    parts = []
    type_names_ru = {
        'resistor': 'резистор', 'capacitor': 'конденсатор', 'inductor': 'индуктивность',
        'diode': 'диод', 'led': 'светодиод', 'battery': 'источник питания',
        'switch': 'переключатель', 'npn': 'NPN-транзистор', 'pnp': 'PNP-транзистор',
        'transistor': 'транзистор', 'ic': 'микросхема', 'ground': 'земля',
    }
    for t, n in sorted(significant_types.items(), key=lambda x: -x[1]):
        name = type_names_ru.get(t, t)
        plural = name + ('ов' if name[-1] not in 'аеёиоуыэюя' else '') if n > 1 else name
        # упрощённо для русской мн.ч. — не идеально, но читаемо
        parts.append(f'{n} {plural}')
    components_str = ', '.join(parts) if parts else 'нет значимых компонентов'

    title = _TITLE_BY_TOPOLOGY.get(topology, 'Схема')
    use_case = _USE_CASE_DESCRIPTIONS.get(topology, '')
    summary = (f'Схема содержит {components_str}. ' +
               (f'Похоже на «{title.lower()}». ' if topology != 'unknown' else '') +
               (use_case if use_case else ''))

    return {
        'title': title,
        'summary': summary.strip(),
        'topology': topology,
        'components_breakdown': types,
        'estimated_use_case': use_case,
        'total_components': n_total,
        'total_connections': len(scheme_data.get('connections', []) or []),
    }


# ── Recommendation: следующий компонент ─────────────────────────────
_NEXT_COMPONENT_RULES = [
    # (условие_func, ['рекомендуемые типы'], причина, confidence)
    (lambda t: t.get('battery', 0) > 0 and t.get('ground', 0) == 0,
     ['ground'], 'Каждой схеме с источником нужна земля (общий ноль).', 0.95),
    (lambda t: sum(t.values()) == 0,
     ['battery'], 'Начните с источника питания.', 0.9),
    (lambda t: t.get('battery', 0) > 0 and t.get('resistor', 0) == 0 and t.get('led', 0) > 0,
     ['resistor'], 'LED нужен токоограничительный резистор перед ним.', 0.9),
    (lambda t: t.get('resistor', 0) > 0 and t.get('capacitor', 0) == 0 and t.get('battery', 0) > 0,
     ['capacitor'], 'Добавьте конденсатор — получите RC-фильтр или развязку.', 0.6),
    (lambda t: t.get('npn', 0) > 0 and t.get('resistor', 0) < 2,
     ['resistor'], 'Транзисторный каскад требует делитель базы (2 резистора).', 0.85),
    (lambda t: t.get('diode', 0) >= 1 and t.get('capacitor', 0) == 0,
     ['capacitor'], 'После диода — сглаживающий конденсатор для DC-выхода.', 0.7),
]


def suggest_next_component_by_rules(scheme_data: dict) -> list:
    """Возвращает top-3 рекомендации следующего компонента."""
    types = count_components_by_type(scheme_data)
    recs = []
    seen_types = set()
    for predicate, comp_types, reason, conf in _NEXT_COMPONENT_RULES:
        try:
            if predicate(types):
                for ct in comp_types:
                    if ct not in seen_types:
                        recs.append({
                            'component_type': ct,
                            'reason': reason,
                            'confidence': conf,
                        })
                        seen_types.add(ct)
        except Exception:
            continue
    if not recs:
        # Default: предложить наиболее частые добавления в схему
        recs.append({
            'component_type': 'resistor',
            'reason': 'Универсальный compoнент — почти всегда что-то ограничить или развести.',
            'confidence': 0.4,
        })
    return recs[:3]
