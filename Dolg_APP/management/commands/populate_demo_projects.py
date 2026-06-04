"""Создаёт демо-проекты схем разной сложности (для презентации на защите).

Проекты принадлежат пользователю admin и помечены is_demo=True — поэтому
видны всем авторизованным пользователям как учебные примеры (read-only для не-владельца).

Запуск:
    python manage.py populate_demo_projects
    python manage.py populate_demo_projects --reset

Формат scheme_data повторяет тот, что редактор сохраняет через buildSchemeData()
в Dolg_APP/templates/tools/simulation.html (версия 2).
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from Dolg_APP.models import SchematicProject

User = get_user_model()

DRAW_STEP = 30
COMPONENT_WIDTH = 60
COMPONENT_HEIGHT = 40


def _snap_to_step(value, step=DRAW_STEP):
    """Округление к ближайшему чертёжному шагу без banker's rounding."""
    return int((value + step / 2) // step) * step


def _normalize_component_position(component, step=DRAW_STEP):
    """Привязывает центр компонента к шагу хода редактора схем."""
    normalized = dict(component)
    normalized['x'] = _snap_to_step(normalized['x'] + COMPONENT_WIDTH / 2, step) - COMPONENT_WIDTH / 2
    normalized['y'] = _snap_to_step(normalized['y'] + COMPONENT_HEIGHT / 2, step) - COMPONENT_HEIGHT / 2
    normalized['x'] = int(normalized['x'])
    normalized['y'] = int(normalized['y'])
    return normalized


def _normalize_connection(connection, step=DRAW_STEP):
    normalized = dict(connection)
    normalized['from'] = dict(connection['from'])
    normalized['to'] = dict(connection['to'])
    normalized['waypoints'] = [
        {'x': _snap_to_step(point['x'], step), 'y': _snap_to_step(point['y'], step)}
        for point in connection.get('waypoints', [])
    ]
    return normalized


def _c(id_, type_, x, y, **extra):
    """Компонент в формате simulation.html."""
    base = {
        'id': id_,
        'type': type_,
        'x': x,
        'y': y,
        'resistance': 1000,
        'capacitance': 1,
        'voltage': 5,
        'inductance': 1,
        'rotation': 0,
        'label': {
            'resistor': 'R',
            'capacitor': 'C',
            'inductor': 'L',
            'diode': 'D',
            'led': 'LED',
            'battery': 'V',
            'switch': 'S',
            'npn': 'Q',
            'pnp': 'Q',
            'ground': 'GND',
            'node': '•',
        }.get(type_, '?'),
        'ports': [],
    }
    # Порты — как в getComponentPorts()
    if type_ == 'battery':
        base['ports'] = [
            {'id': '+', 'label': '+', 'x': -30, 'y': 0},
            {'id': '-', 'label': '-', 'x': 30, 'y': 0},
        ]
    elif type_ == 'ground':
        base['ports'] = [{'id': 'a', 'label': 'GND', 'x': 0, 'y': -20}]
    elif type_ == 'node':
        base['ports'] = [{'id': 'a', 'label': '•', 'x': 0, 'y': 0}]
    elif type_ in ('npn', 'pnp'):
        base['ports'] = [
            {'id': 'b', 'label': 'B', 'x': -30, 'y': 0},
            {'id': 'c', 'label': 'C', 'x': 0, 'y': -20},
            {'id': 'e', 'label': 'E', 'x': 0, 'y': 20},
        ]
    else:
        base['ports'] = [
            {'id': 'a', 'label': '+', 'x': -30, 'y': 0},
            {'id': 'b', 'label': '-', 'x': 30, 'y': 0},
        ]
    base.update(extra)
    return base


def _w(from_id, from_port, to_id, to_port, waypoints=None):
    return {
        'id': None,
        'from': {'compId': from_id, 'portId': from_port},
        'to': {'compId': to_id, 'portId': to_port},
        'waypoints': list(waypoints) if waypoints else [],
    }


DESIGNATOR_PREFIX = {
    'resistor': 'R',
    'capacitor': 'C',
    'inductor': 'L',
    'diode': 'D',
    'led': 'D',
    'battery': 'V',
    'switch': 'SA',
    'npn': 'Q',
    'pnp': 'Q',
    'transistor': 'Q',
    'ic': 'U',
    'ground': 'GND',
    'node': 'N',
}


def _component_port_xy(component, port_id):
    """World-координаты порта с учётом rotation компонента.

    БАГ ДО ФИКСА: rotation игнорировался — для vertical resistor (rot=90) порт 'a'
    считался как (cx-30, cy) вместо (cx, cy-30). Из-за этого `_orthogonalize_connection`
    auto-elbow попадал в body center соседнего компонента, и провод визуально
    проходил «сквозь» резистор. После фикса elbow аккуратный.
    """
    import math

    cx = component['x'] + COMPONENT_WIDTH / 2
    cy = component['y'] + COMPONENT_HEIGHT / 2
    rot = int(component.get('rotation') or 0) % 360
    for port in component.get('ports', []):
        if port.get('id') == port_id:
            lx, ly = port.get('x', 0), port.get('y', 0)
            if rot == 90:
                wx, wy = cx - ly, cy + lx
            elif rot == 180:
                wx, wy = cx - lx, cy - ly
            elif rot == 270:
                wx, wy = cx + ly, cy - lx
            elif rot == 0:
                wx, wy = cx + lx, cy + ly
            else:
                rad = rot * math.pi / 180
                wx = cx + lx * math.cos(rad) - ly * math.sin(rad)
                wy = cy + lx * math.sin(rad) + ly * math.cos(rad)
            return {'x': _snap_to_step(wx), 'y': _snap_to_step(wy)}
    return {'x': _snap_to_step(cx), 'y': _snap_to_step(cy)}


def _assign_designators(components):
    counters = {}
    normalized = []
    for component in components:
        item = dict(component)
        prefix = DESIGNATOR_PREFIX.get(item.get('type'), 'E')
        if prefix == 'GND':
            item['label'] = 'GND'
        elif prefix == 'N':
            counters[prefix] = counters.get(prefix, 0) + 1
            item['label'] = f'{prefix}{counters[prefix]}'
        else:
            counters[prefix] = counters.get(prefix, 0) + 1
            item['label'] = f'{prefix}{counters[prefix]}'
        normalized.append(item)
    return normalized


def _component_body_rect(component):
    """BBox корпуса компонента (без выводов) в world-координатах с учётом rotation.
    Возвращает (left, top, right, bottom) или None если компонент не имеет тела
    (node/ground — точечные/линейные)."""
    t = component.get('type')
    if t in ('node', 'ground', None):
        return None
    cx = component['x'] + COMPONENT_WIDTH / 2
    cy = component['y'] + COMPONENT_HEIGHT / 2
    rot = int(component.get('rotation') or 0) % 360
    is_vert = rot in (90, 270)
    if t in ('resistor', 'capacitor', 'inductor', 'diode', 'led', 'battery', 'switch'):
        w, h = (12, 34) if is_vert else (34, 12)
    else:  # npn/pnp/etc — кружок ~32 px
        w, h = 32, 32
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def _point_inside_any_body(x, y, components, exclude_ids):
    """True если точка (x, y) лежит внутри корпуса любого компонента (кроме
    тех, что в exclude_ids — обычно endpoint'ы провода)."""
    for c in components:
        if c.get('id') in exclude_ids:
            continue
        r = _component_body_rect(c)
        if r and r[0] < x < r[2] and r[1] < y < r[3]:
            return True
    return False


def _orthogonalize_connection(connection, by_id):
    normalized = dict(connection)
    normalized['from'] = dict(connection['from'])
    normalized['to'] = dict(connection['to'])
    if normalized.get('waypoints'):
        return normalized

    source = by_id.get(normalized['from']['compId'])
    target = by_id.get(normalized['to']['compId'])
    if not source or not target:
        return normalized

    start = _component_port_xy(source, normalized['from']['portId'])
    end = _component_port_xy(target, normalized['to']['portId'])
    if start['x'] == end['x'] or start['y'] == end['y']:
        return normalized

    dx = abs(start['x'] - end['x'])
    dy = abs(start['y'] - end['y'])
    # Два варианта L-разводки — выбираем тот, чей elbow НЕ внутри чужого корпуса.
    # Если оба плохие — оставляем waypoints пустыми, frontend разведёт через
    # buildOrthogonalPath с obstacle-avoidance.
    candidate_a = {'x': end['x'], 'y': start['y']}
    candidate_b = {'x': start['x'], 'y': end['y']}
    primary, fallback = (candidate_a, candidate_b) if dx >= dy else (candidate_b, candidate_a)
    exclude = {source.get('id'), target.get('id')}
    comps = list(by_id.values())
    for elbow in (primary, fallback):
        if elbow == start or elbow == end:
            continue
        if _point_inside_any_body(elbow['x'], elbow['y'], comps, exclude):
            continue
        normalized['waypoints'] = [elbow]
        return normalized
    # Оба elbow'а попадают в чужой корпус — пусть фронт разводит сам.
    return normalized


def scheme(components, connections):
    normalized_components = [
        _normalize_component_position(component) for component in _assign_designators(components)
    ]
    by_id = {component['id']: component for component in normalized_components}
    normalized_connections = []
    for index, connection in enumerate(connections):
        conn = _orthogonalize_connection(connection, by_id)
        conn = _normalize_connection(conn)
        conn['id'] = index + 1
        normalized_connections.append(conn)
    return {
        'version': 2,
        'drawing_step': DRAW_STEP,
        'components': normalized_components,
        'connections': normalized_connections,
        'board': {
            'margin_mm': 6,
            'trace_width_mm': 0.5,
            'clearance_mm': 1.5,
            'thickness_mm': 1.6,
            'grid_mm': 5,
        },
        'timestamp': '2026-05-04T00:00:00Z',
    }


# ============================================================
# ПРОЕКТ 1 (basic): LED с токоограничительным резистором
# ============================================================
def demo_led_basic():
    """5 В батарея → резистор 220 Ом → LED → GND. Минимальная цепь.
    Узел N1 у GND собирает обратную ветвь от LED и от батареи (-)."""
    comps = [
        _c(0, 'battery', 200, 200, voltage=5),
        _c(1, 'resistor', 360, 200, resistance=220),
        _c(2, 'led', 520, 200),
        _c(3, 'ground', 460, 380),
        _c(4, 'node', 460, 320),  # N1: общая «земляная» точка
    ]
    conns = [
        _w(0, '+', 1, 'a'),
        _w(1, 'b', 2, 'a'),
        _w(2, 'b', 4, 'a'),
        _w(0, '-', 4, 'a'),
        _w(4, 'a', 3, 'a'),
    ]
    return {
        'name': '🔴 LED-индикатор 5 В',
        'description': 'Простая цепь: батарея 5 В + резистор 220 Ом + светодиод. Для знакомства с интерфейсом и расчёта по закону Ома.',
        'difficulty': 'basic',
        'category': 'led',
        'scheme_data': scheme(comps, conns),
    }


# ============================================================
# ПРОЕКТ 2 (basic): Делитель напряжения
# ============================================================
def demo_voltage_divider():
    """Два резистора — типовой вход ADC для опорного напряжения.
    Узел N1 — общий «минус» (батарея и нижний R сходятся к GND)."""
    comps = [
        _c(0, 'battery', 200, 180, voltage=9),
        _c(1, 'resistor', 360, 240, resistance=10_000),
        _c(2, 'resistor', 360, 360, resistance=4_700),
        _c(3, 'ground', 280, 500),
        _c(4, 'node', 280, 440),  # N1
    ]
    conns = [
        _w(0, '+', 1, 'a'),
        _w(1, 'b', 2, 'a'),
        _w(2, 'b', 4, 'a'),
        _w(0, '-', 4, 'a'),
        _w(4, 'a', 3, 'a'),
    ]
    return {
        'name': '⚡ Делитель напряжения 9→2.88 В',
        'description': 'R1 10 кОм + R2 4.7 кОм. Vout = Vin × R2/(R1+R2) ≈ 2.88 В. Классическая опорная схема для входа АЦП.',
        'difficulty': 'basic',
        'category': 'other',
        'scheme_data': scheme(comps, conns),
    }


# ============================================================
# ПРОЕКТ 3 (medium): RC-фильтр нижних частот
# ============================================================
def demo_rc_filter():
    """Г-образный фильтр низких частот: R горизонтально в сигнальной линии,
    C вертикально на землю. Классическое УГО — как в учебнике."""
    comps = [
        _c(0, 'battery', 180, 240, voltage=5),
        _c(1, 'resistor', 340, 240, resistance=1_000),
        # Конденсатор шунтирует на землю — поворачиваем вертикально.
        _c(2, 'capacitor', 460, 320, capacitance=0.1, rotation=90),
        _c(3, 'ground', 460, 500),
        _c(4, 'node', 280, 400),
    ]
    conns = [
        _w(0, '+', 1, 'a'),
        _w(1, 'b', 2, 'a'),  # R.b → C.вход (верх)
        _w(2, 'b', 3, 'a'),  # C.выход (низ) → GND-узел
        _w(0, '-', 4, 'a'),
        _w(4, 'a', 3, 'a'),
    ]
    return {
        'name': '📉 RC-фильтр низких частот',
        'description': 'R=1 кОм, C=0.1 мкФ. Частота среза fc = 1/(2πRC) ≈ 1.6 кГц. Анализ AC/transient покажет АЧХ и переходную характеристику.',
        'difficulty': 'medium',
        'category': 'other',
        'scheme_data': scheme(comps, conns),
    }


# ============================================================
# ПРОЕКТ 4 (medium): Мостовой выпрямитель
# ============================================================
def demo_bridge_rectifier():
    """4 диода + сглаживающий конденсатор — мост Греца.
    4 узла: N1 (вход +), N2 (выход +), N3 (вход −), N4 (выход −/GND)."""
    comps = [
        _c(0, 'battery', 180, 300, voltage=12),
        # Мост из 4 диодов
        _c(1, 'diode', 380, 220),
        _c(2, 'diode', 380, 380),
        _c(3, 'diode', 540, 220),
        _c(4, 'diode', 540, 380),
        # Сглаживающий конденсатор + нагрузка
        _c(5, 'capacitor', 700, 260, capacitance=100),  # 100 мкФ
        _c(6, 'resistor', 700, 380, resistance=1_000),
        _c(7, 'ground', 700, 580),
        # Узлы
        _c(8, 'node', 280, 300),  # N1: входной +
        _c(9, 'node', 660, 220),  # N2: выходной + (после D3)
        _c(10, 'node', 280, 460),  # N3: вход − (батарея и D4.b)
        _c(11, 'node', 700, 520),  # N4: GND и обратные ветви
    ]
    conns = [
        _w(0, '+', 8, 'a'),
        _w(8, 'a', 1, 'a'),
        _w(8, 'a', 2, 'a'),
        _w(1, 'b', 3, 'a'),
        _w(2, 'b', 4, 'a'),
        _w(3, 'b', 9, 'a'),
        _w(9, 'a', 5, 'a'),
        _w(9, 'a', 6, 'a'),
        _w(0, '-', 10, 'a'),
        _w(4, 'b', 10, 'a'),
        _w(10, 'a', 11, 'a'),
        _w(5, 'b', 11, 'a'),
        _w(6, 'b', 11, 'a'),
        _w(11, 'a', 7, 'a'),
    ]
    return {
        'name': '🌊 Мостовой выпрямитель (мост Греца)',
        'description': '4 диода + сглаживающий конденсатор 100 мкФ + нагрузка 1 кОм. Демонстрирует выпрямление переменного тока и работу пассивного фильтра пульсаций.',
        'difficulty': 'medium',
        'category': 'power',
        'scheme_data': scheme(comps, conns),
    }


# ============================================================
# ПРОЕКТ 5 (advanced): LC-резонансный контур
# ============================================================
def demo_lc_tank():
    """Параллельный LC + последовательный R демпфер. L и C нарисованы
    вертикально между сигнальной линией и землёй — классический LC-tank."""
    comps = [
        _c(0, 'battery', 180, 240, voltage=10),
        _c(1, 'resistor', 340, 240, resistance=100),
        _c(2, 'inductor', 480, 320, inductance=10, rotation=90),  # L шунт
        _c(3, 'capacitor', 600, 320, capacitance=10, rotation=90),  # C шунт
        _c(4, 'ground', 540, 540),
        _c(5, 'node', 440, 240),  # ветвление на L и C
        _c(6, 'node', 600, 240),  # верх C
        _c(7, 'node', 540, 440),  # общая земля
    ]
    conns = [
        _w(0, '+', 1, 'a'),
        _w(1, 'b', 5, 'a'),
        _w(5, 'a', 2, 'a'),  # вход L
        _w(5, 'a', 6, 'a'),  # переход к C по верху
        _w(6, 'a', 3, 'a'),  # вход C
        _w(2, 'b', 7, 'a'),  # низ L → земля
        _w(3, 'b', 7, 'a'),  # низ C → земля
        _w(0, '-', 7, 'a'),
        _w(7, 'a', 4, 'a'),
    ]
    return {
        'name': '🎵 LC-резонансный контур',
        'description': 'L=10 мГн и C=10 мкФ параллельно, последовательный R=100 Ом как демпфер. Резонансная частота f₀ = 1/(2π√LC) ≈ 503 Гц. При симуляции transient-анализ покажет затухающие колебания.',
        'difficulty': 'advanced',
        'category': 'audio',
        'scheme_data': scheme(comps, conns),
    }


# ============================================================
# ПРОЕКТ 6 (medium): Мост Уитстона (классическая измерительная схема)
# ============================================================
def demo_wheatstone_bridge():
    """4 резистора в виде ромба + измерительные узлы A, B.
    Сбалансирован при R1·R4 = R2·R3. ngspice решает за миллисекунды.
    N1: батарея(+) → R1, R2; N2: R3, R4 → GND, вместе с батареей(-)."""
    comps = [
        _c(0, 'battery', 180, 320, voltage=10),
        _c(1, 'resistor', 360, 220, resistance=10_000),
        _c(2, 'resistor', 360, 420, resistance=22_000),
        _c(3, 'resistor', 540, 220, resistance=22_000),
        _c(4, 'resistor', 540, 420, resistance=47_000),
        _c(5, 'ground', 720, 540),
        _c(6, 'node', 280, 320),  # N1: V+ ветвление
        _c(7, 'node', 720, 460),  # N2: GND ветвление
    ]
    conns = [
        _w(0, '+', 6, 'a'),
        _w(6, 'a', 1, 'a'),
        _w(6, 'a', 2, 'a'),
        _w(1, 'b', 3, 'a'),  # узел A прямо в проводе R1.b—R3.a
        _w(2, 'b', 4, 'a'),  # узел B прямо в проводе R2.b—R4.a
        _w(3, 'b', 7, 'a'),
        _w(4, 'b', 7, 'a'),
        _w(0, '-', 7, 'a'),
        _w(7, 'a', 5, 'a'),
    ]
    return {
        'name': '⚖️ Мост Уитстона',
        'description': 'Четыре резистора в форме ромба, источник 10 В по одной диагонали, измерение напряжения по второй. R1=10к, R2=22к, R3=22к, R4=47к. ΔV между точками A и B зависит от баланса плеч R1·R4 vs R2·R3.',
        'difficulty': 'medium',
        'category': 'sensor',
        'scheme_data': scheme(comps, conns),
    }


# ============================================================
# ПРОЕКТ 7 (medium): Двухкаскадный RC-фильтр низких частот
# ============================================================
def demo_cascade_rc_lpf():
    """Два RC-каскада подряд (Π-LPF): резисторы горизонтально в сигнальной
    линии, конденсаторы вертикально на землю. Крутизна спада −40 дБ/дек."""
    comps = [
        _c(0, 'battery', 180, 240, voltage=5),
        _c(1, 'resistor', 340, 240, resistance=2_200),
        _c(2, 'capacitor', 440, 320, capacitance=0.047, rotation=90),  # шунт C1
        _c(3, 'resistor', 540, 240, resistance=4_700),
        _c(4, 'capacitor', 640, 320, capacitance=0.022, rotation=90),  # шунт C2
        _c(5, 'ground', 540, 540),
        _c(6, 'node', 440, 240),  # выход R1 ветвится на C1 и R2
        _c(7, 'node', 540, 440),  # общая земля
    ]
    conns = [
        _w(0, '+', 1, 'a'),
        _w(1, 'b', 6, 'a'),
        _w(6, 'a', 2, 'a'),  # C1 верх
        _w(6, 'a', 3, 'a'),  # цепь дальше → R2
        _w(2, 'b', 7, 'a'),  # C1 низ → земля
        _w(3, 'b', 4, 'a'),  # выход R2 → C2 верх
        _w(4, 'b', 7, 'a'),  # C2 низ → земля
        _w(0, '-', 7, 'a'),
        _w(7, 'a', 5, 'a'),
    ]
    return {
        'name': '📊 Двухкаскадный RC-фильтр',
        'description': 'Два RC-LPF последовательно. R1=2.2к/C1=47 нФ → fc1≈1.5 кГц; R2=4.7к/C2=22 нФ → fc2≈1.5 кГц. Совокупная крутизна спада −40 дБ/дек, переходный анализ покажет более плавный отклик.',
        'difficulty': 'medium',
        'category': 'audio',
        'scheme_data': scheme(comps, conns),
    }


# ============================================================
# ПРОЕКТ 8 (advanced): Параллельные нагрузки — делитель тока
# ============================================================
def demo_current_divider():
    """Один источник + 3 параллельных резистора (вертикальные «нагрузки» на землю).
    I_n = I_total × G_n/G_sum. Земля собирается через 2 узла-каскад,
    чтобы ни в одном узле не было больше 4 проводов."""
    comps = [
        _c(0, 'battery', 180, 240, voltage=10),
        _c(1, 'resistor', 340, 320, resistance=1_000, rotation=90),
        _c(2, 'resistor', 460, 320, resistance=2_200, rotation=90),
        _c(3, 'resistor', 580, 320, resistance=4_700, rotation=90),
        _c(4, 'ground', 460, 540),
        _c(5, 'node', 280, 240),  # V+ ветвление
        _c(6, 'node', 400, 440),  # сбор R1.b и R2.b
        _c(7, 'node', 520, 440),  # сбор R3.b и batt(-) → GND
    ]
    conns = [
        _w(0, '+', 5, 'a'),
        _w(5, 'a', 1, 'a'),
        _w(5, 'a', 2, 'a'),
        _w(5, 'a', 3, 'a'),
        _w(1, 'b', 6, 'a'),
        _w(2, 'b', 6, 'a'),
        _w(6, 'a', 7, 'a'),
        _w(3, 'b', 7, 'a'),
        _w(0, '-', 7, 'a'),
        _w(7, 'a', 4, 'a'),
    ]
    return {
        'name': '🔀 Параллельные нагрузки — делитель тока',
        'description': 'V=10 В на трёх резисторах: R1=1 кОм, R2=2.2 кОм, R3=4.7 кОм. Общий ток ≈ 17 мА (10 + 4.55 + 2.13). Эквивалентное сопротивление ≈ 590 Ом.',
        'difficulty': 'advanced',
        'category': 'power',
        'scheme_data': scheme(comps, conns),
    }


# ============================================================
# ПРОЕКТ 9 (stress): Большая лестничная резистивная сетка R-2R (~600 элементов)
# ============================================================
def demo_big_ladder():
    """12-битный R-2R DAC — каноническая схема из учебников.

    Переписана 2026-05 (v3) по образцу реального 12-bit R-2R DAC:
    - 12 секций (= 12 бит — типовая разрядность бюджетных DAC).
    - Vref-источник (батарея) ВЕРТИКАЛЬНО слева: '+' идёт вверх к
      верхней шине, '-' — горизонтально к нижней шине + вертикально вниз
      к ground. Никаких «километровых» обходных кабелей.
    - Все провода строго ortho: верхняя/нижняя шины — прямые горизонтали,
      перемычки R→2R и bat→bus — короткие L-образные.
    - Никаких node-точек между секциями (port-as-junction, degree=2).
    - Y нижней шины = ровно Y_MID + 30 (= где сидят rsh.b порты),
      раньше Y_BOT был на 60 px ниже и приходилось делать обход.
    """
    SECTIONS = 12  # 12-битный DAC — реальная разрядность
    GRID = 100  # шаг секции
    Y_TOP = 180  # верхняя Vref-шина (где сидят rs.a/rs.b)
    Y_MID = 290  # центр вертикальных шунтов 2R
    Y_BUS = 320  # нижняя GND-шина (= Y_MID + 30 = где rsh.b)
    X_BAT = 120  # x-координата батареи и ground (слева)
    X_START = 240  # x-координата первой секции
    comps = []
    conns = []

    bat_id = 0
    gnd_id = 1
    # Батарея вертикально: '+' сверху, '-' снизу — естественная ориентация
    # для источника, питающего «верхнюю» шину и заземление.
    comps.append(_c(bat_id, 'battery', X_BAT, Y_MID, rotation=270, voltage=10))
    # Ground строго под батареей, на одной вертикали — короткая ветка.
    comps.append(_c(gnd_id, 'ground', X_BAT, Y_BUS + 60))

    next_id = 2
    prev_top_id = bat_id
    prev_top_port = '+'
    first_rsh_id = None
    last_rsh_id = None

    for k in range(SECTIONS):
        x = X_START + k * GRID
        # Последовательный R сверху (10 кОм) — горизонтально
        rs_id = next_id
        next_id += 1
        comps.append(_c(rs_id, 'resistor', x, Y_TOP, resistance=10_000))
        # Шунт 2R вертикально (20 кОм) — центр в Y_MID, b-порт сидит на Y_BUS
        rsh_id = next_id
        next_id += 1
        comps.append(_c(rsh_id, 'resistor', x, Y_MID, resistance=20_000, rotation=90))

        # Верхняя шина: prev.port → rs.a (или bat.+ для первой секции)
        if k == 0:
            # bat.+ at (X_BAT, Y_MID-30=260) → up to (X_BAT, Y_TOP) → right to rs.a
            conns.append(_w(prev_top_id, prev_top_port, rs_id, 'a', waypoints=[{'x': X_BAT, 'y': Y_TOP}]))
        else:
            conns.append(_w(prev_top_id, prev_top_port, rs_id, 'a'))
        # rs.b → rsh.a (вниз к шунту). rs.b ещё используется как prev_top
        # на следующей итерации — degree=2, точки нет.
        conns.append(_w(rs_id, 'b', rsh_id, 'a'))

        # Нижняя шина: цепочка rsh_k.b → rsh_{k+1}.b (на одной Y=Y_BUS)
        if last_rsh_id is not None:
            conns.append(_w(last_rsh_id, 'b', rsh_id, 'b'))
        else:
            first_rsh_id = rsh_id
        last_rsh_id = rsh_id

        prev_top_id = rs_id
        prev_top_port = 'b'

    # bat.- (X_BAT, Y_MID+30=320=Y_BUS) → first_rsh.b (X_START, Y_BUS).
    # На одной Y → прямая горизонталь, без waypoints.
    conns.append(_w(bat_id, '-', first_rsh_id, 'b'))
    # bat.- ↓ gnd.a — обе на X_BAT, вертикальный коротыш (40 px).
    conns.append(_w(bat_id, '-', gnd_id, 'a'))

    total = len(comps)
    return {
        'name': '🪜 R-2R DAC (12-бит) — каноническая схема',
        'description': (
            f'12-битный R-2R DAC: {SECTIONS} ступеней R=10кОм / 2R=20кОм. '
            f'Vref={10} В сверху, GND снизу. Эквивалентное сопротивление '
            f'каждой ступени = R, что даёт двоично-взвешенный выход. '
            f'Каноническая схема из любого учебника по аналоговой схемотехнике. '
            f'Электрически: {total} компонентов, {len(conns)} проводов.'
        ),
        'difficulty': 'advanced',
        'category': 'other',
        'scheme_data': scheme(comps, conns),
    }


# ============================================================
# ПРОЕКТ 10 (stress): Каскад из 50 RC-секций (~250 элементов)
# ============================================================
def demo_long_rc_chain():
    """8-каскадный RC-LPF — каноническая реализация LPF 8-го порядка.

    Переписана 2026-05 (v3) — аналогично big_ladder:
    - 8 секций (RC-LPF 8-го порядка — типовая разрядность для AA-фильтра ADC).
    - Источник Vin (батарея) вертикальный слева, '+' сверху → сигнальная
      шина, '-' снизу → GND. Без обходных проводов.
    - Y нижней шины = Y_MID + 30 (где сидят cs.b), без вылета вниз.
    """
    SECTIONS = 8  # 8-pole LPF — реальный AA-фильтр
    GRID = 100
    Y_TOP = 180
    Y_MID = 290
    Y_BUS = 320  # = Y_MID + 30 = где cs.b
    X_BAT = 120
    X_START = 240
    comps = []
    conns = []

    bat_id = 0
    gnd_id = 1
    comps.append(_c(bat_id, 'battery', X_BAT, Y_MID, rotation=270, voltage=5))
    comps.append(_c(gnd_id, 'ground', X_BAT, Y_BUS + 60))

    next_id = 2
    prev_top_id = bat_id
    prev_top_port = '+'
    first_cs_id = None
    last_cs_id = None

    for k in range(SECTIONS):
        x = X_START + k * GRID
        rs_id = next_id
        next_id += 1
        comps.append(_c(rs_id, 'resistor', x, Y_TOP, resistance=1_000))
        cs_id = next_id
        next_id += 1
        comps.append(_c(cs_id, 'capacitor', x, Y_MID, capacitance=0.1, rotation=90))

        if k == 0:
            conns.append(_w(prev_top_id, prev_top_port, rs_id, 'a', waypoints=[{'x': X_BAT, 'y': Y_TOP}]))
        else:
            conns.append(_w(prev_top_id, prev_top_port, rs_id, 'a'))
        conns.append(_w(rs_id, 'b', cs_id, 'a'))

        if last_cs_id is not None:
            conns.append(_w(last_cs_id, 'b', cs_id, 'b'))
        else:
            first_cs_id = cs_id
        last_cs_id = cs_id

        prev_top_id = rs_id
        prev_top_port = 'b'

    conns.append(_w(bat_id, '-', first_cs_id, 'b'))
    conns.append(_w(bat_id, '-', gnd_id, 'a'))

    total = len(comps)
    return {
        'name': '📉 RC-LPF 8-го порядка (anti-aliasing)',
        'description': (
            f'{SECTIONS} последовательных RC-секций (R=1кОм, C=0.1мкФ). '
            f'Совокупный спад {SECTIONS * 20} дБ/декада выше fc≈1.6 кГц — '
            f'каноническая структура AA-фильтра перед ADC. '
            f'Электрически: {total} компонентов, {len(conns)} проводов.'
        ),
        'difficulty': 'advanced',
        'category': 'audio',
        'scheme_data': scheme(comps, conns),
    }


# ============================================================
# ПРОЕКТ 11 (advanced): Комплексный усилитель класса А
# ============================================================
def demo_class_a_amplifier():
    """🎚 Двухкаскадный усилитель класса А — широкий layout, шаг 120 px.

    Все pass-through узлы убраны — оставлен только n_vcc_l как «якорь»,
    иначе маршрутизатор делал лишний Z-поворот. drawNode скрывает дот при
    degree<3, поэтому n_vcc_l невидим, а 16 оставшихся узлов — настоящие
    T/+-узлы (3+ провода).

    Колонки cx (шаг 120):
      120: блок питания (bat → sw → d1 → L1, вертикально)
      240: C_smooth (вертикальный, между шинами)
      360: V_sig (вертикальный)
      480: C_in (горизонтальный)
      600: делитель базы 1 (R_b1, R_b2) + n_base1
      720: VT1, R_c1, R_e1, n_col1, n_em1
      840: эмиттерный шунт C_e1
      960: межкаскадный C_couple (горизонтальный)
      1080: делитель базы 2 (R_b3, R_b4) + n_base2
      1200: VT2, R_c2, R_e2, n_col2, n_em2 (отдельный n_vcc_rc2 — без коллизий)
      1320: эмиттерный шунт C_e2
      1440: выходной C_out (горизонтальный)
      1560: нагрузка R_load + символ ground

    Шины: Vcc на y=80, GND на y=540. Коллекторная горизонталь y=230,
    базовая (сигнальная) y=290, эмиттерная y=350.
    Габариты 1620×620 px — широкий формат для чёткой маршрутизации
    проводов без перекрытий (раньше было 1120×540, узко).

    Электрика: усиление ≈ (R_c/R_e) ≈ 10 на каскад, общее ≈ 100.
    D1 с rotation=270 — анод снизу, катод сверху: ток bat+ ↑ Vcc
    через прямое смещение.
    """
    comps = []
    conns = []
    nid = [0]

    def CC(t, cx, cy, **kw):
        c = _c(nid[0], t, cx - 30, cy - 20, **kw)
        comps.append(c)
        nid[0] += 1
        return nid[0] - 1

    def WW(fid, fp, tid, tp):
        conns.append(_w(fid, fp, tid, tp))

    # ===== Vcc-узлы (y=80) =====
    n_vcc_l = CC('node', 120, 80)  # якорь L1→Vcc (degree=2, невидим)
    n_vcc_csm = CC('node', 240, 80)
    n_vcc_rb1 = CC('node', 600, 80)
    n_vcc_rc1 = CC('node', 720, 80)
    n_vcc_rb3 = CC('node', 1080, 80)
    n_vcc_rc2 = CC('node', 1200, 80)  # отдельный узел для R_c2 (не пиггибэк)

    # ===== GND-узлы (y=540) =====
    n_gnd_csm = CC('node', 240, 540)
    n_gnd_sig = CC('node', 360, 540)
    n_gnd_rb2 = CC('node', 600, 540)
    n_gnd_re1 = CC('node', 720, 540)
    n_gnd_ce1 = CC('node', 840, 540)
    n_gnd_rb4 = CC('node', 1080, 540)
    n_gnd_re2 = CC('node', 1200, 540)
    n_gnd_ce2 = CC('node', 1320, 540)
    n_gnd_rld = CC('node', 1560, 540)

    # ===== Внутренние узлы каскадов =====
    n_base1 = CC('node', 600, 290)
    n_col1 = CC('node', 720, 230)
    n_em1 = CC('node', 720, 350)
    n_base2 = CC('node', 1080, 290)
    n_col2 = CC('node', 1200, 230)
    n_em2 = CC('node', 1200, 350)

    # ===== Блок питания (вертикальный столбик cx=120) =====
    bat = CC('battery', 120, 440, rotation=90, voltage=15)
    sw1 = CC('switch', 120, 350, rotation=90)
    d1 = CC('diode', 120, 260, rotation=270)  # анод снизу, катод сверху
    l1 = CC('inductor', 120, 170, rotation=90, inductance=10)

    # ===== Сглаживание (между Vcc=80 и GND=540, cy=310 — посередине) =====
    c_sm = CC('capacitor', 240, 310, rotation=90, capacitance=100)

    # ===== Сигнал и вход =====
    vsig = CC('battery', 360, 440, rotation=90, voltage=0)
    c_in = CC('capacitor', 480, 290, capacitance=1)

    # ===== Каскад 1 =====
    r_b1 = CC('resistor', 600, 140, rotation=90, resistance=47_000)
    r_b2 = CC('resistor', 600, 440, rotation=90, resistance=10_000)
    r_c1 = CC('resistor', 720, 140, rotation=90, resistance=4_700)
    q1 = CC('npn', 720, 290)
    r_e1 = CC('resistor', 720, 440, rotation=90, resistance=470)
    c_e1 = CC('capacitor', 840, 440, rotation=90, capacitance=10)

    # ===== Связь и каскад 2 =====
    c_cpl = CC('capacitor', 960, 230, capacitance=10)
    r_b3 = CC('resistor', 1080, 140, rotation=90, resistance=47_000)
    r_b4 = CC('resistor', 1080, 440, rotation=90, resistance=10_000)
    r_c2 = CC('resistor', 1200, 140, rotation=90, resistance=4_700)
    q2 = CC('npn', 1200, 290)
    r_e2 = CC('resistor', 1200, 440, rotation=90, resistance=470)
    c_e2 = CC('capacitor', 1320, 440, rotation=90, capacitance=10)

    # ===== Выход =====
    c_out = CC('capacitor', 1440, 230, capacitance=10)
    r_load = CC('resistor', 1560, 440, rotation=90, resistance=10_000)
    gnd = CC('ground', 1560, 600)

    # ============== Соединения ==============
    # --- Питание ---
    WW(bat, '-', n_gnd_csm, 'a')  # bat- сразу на GND-шину (без n_gnd_bat)
    WW(bat, '+', sw1, 'b')
    WW(sw1, 'a', d1, 'a')  # ток в анод d1 (rot=270 → анод снизу)
    WW(d1, 'b', l1, 'b')
    WW(l1, 'a', n_vcc_l, 'a')
    WW(n_vcc_l, 'a', n_vcc_csm, 'a')  # горизонтальный участок Vcc-шины

    # --- Vcc-шина (y=80) ---
    WW(n_vcc_csm, 'a', n_vcc_rb1, 'a')
    WW(n_vcc_rb1, 'a', n_vcc_rc1, 'a')
    WW(n_vcc_rc1, 'a', n_vcc_rb3, 'a')
    WW(n_vcc_rb3, 'a', n_vcc_rc2, 'a')

    # --- GND-шина (y=540) ---
    WW(n_gnd_csm, 'a', n_gnd_sig, 'a')
    WW(n_gnd_sig, 'a', n_gnd_rb2, 'a')
    WW(n_gnd_rb2, 'a', n_gnd_re1, 'a')
    WW(n_gnd_re1, 'a', n_gnd_ce1, 'a')
    WW(n_gnd_ce1, 'a', n_gnd_rb4, 'a')
    WW(n_gnd_rb4, 'a', n_gnd_re2, 'a')
    WW(n_gnd_re2, 'a', n_gnd_ce2, 'a')
    WW(n_gnd_ce2, 'a', n_gnd_rld, 'a')
    WW(n_gnd_rld, 'a', gnd, 'a')

    # --- C_smooth ---
    WW(n_vcc_csm, 'a', c_sm, 'a')
    WW(c_sm, 'b', n_gnd_csm, 'a')

    # --- Сигнал ---
    WW(vsig, '-', n_gnd_sig, 'a')
    WW(vsig, '+', c_in, 'a')
    WW(c_in, 'b', n_base1, 'a')

    # --- Каскад 1 ---
    WW(n_vcc_rb1, 'a', r_b1, 'a')
    WW(r_b1, 'b', n_base1, 'a')
    WW(n_base1, 'a', r_b2, 'a')
    WW(r_b2, 'b', n_gnd_rb2, 'a')

    WW(n_vcc_rc1, 'a', r_c1, 'a')
    WW(r_c1, 'b', n_col1, 'a')
    WW(n_col1, 'a', q1, 'c')
    WW(n_base1, 'a', q1, 'b')
    WW(q1, 'e', n_em1, 'a')
    WW(n_em1, 'a', r_e1, 'a')
    WW(r_e1, 'b', n_gnd_re1, 'a')
    WW(n_em1, 'a', c_e1, 'a')
    WW(c_e1, 'b', n_gnd_ce1, 'a')

    # --- Связь ---
    WW(n_col1, 'a', c_cpl, 'a')
    WW(c_cpl, 'b', n_base2, 'a')

    # --- Каскад 2 ---
    WW(n_vcc_rb3, 'a', r_b3, 'a')
    WW(n_vcc_rc2, 'a', r_c2, 'a')  # отдельный Vcc-тап (без пиггибэка на n_vcc_rb3)
    WW(r_b3, 'b', n_base2, 'a')
    WW(n_base2, 'a', r_b4, 'a')
    WW(r_b4, 'b', n_gnd_rb4, 'a')
    WW(r_c2, 'b', n_col2, 'a')
    WW(n_col2, 'a', q2, 'c')
    WW(n_base2, 'a', q2, 'b')
    WW(q2, 'e', n_em2, 'a')
    WW(n_em2, 'a', r_e2, 'a')
    WW(r_e2, 'b', n_gnd_re2, 'a')
    WW(n_em2, 'a', c_e2, 'a')
    WW(c_e2, 'b', n_gnd_ce2, 'a')

    # --- Выход (горизонтальный C_out на y=230, затем нагрузка на cx=1560) ---
    WW(n_col2, 'a', c_out, 'a')
    WW(c_out, 'b', r_load, 'a')
    WW(r_load, 'b', n_gnd_rld, 'a')

    return {
        'name': '🎚 Двухкаскадный усилитель класса А (BJT, все типы)',
        'description': (
            'Двухкаскадный усилитель напряжения на NPN. Использует ВСЕ типы '
            'компонентов: 2× battery, switch, diode (rot=270 — прямое смещение), '
            'inductor, 5× capacitor, 9× resistor, 2× NPN, 16 настоящих T-узлов '
            '+ 1 невидимый якорь, ground. Широкий layout с шагом 120 px по X '
            '(1620×620 px) — провода маршрутизируются без перекрытий. '
            'Vcc на y=80, GND на y=540, коллектор y=230, база y=290, эмиттер y=350. '
            'Усиление ≈ (R_c/R_e) ≈ 10 на каскад, общее ≈ 100. '
            'AC-анализ: полоса ≈ 10 Гц … 100 кГц.'
        ),
        'difficulty': 'advanced',
        'category': 'audio',
        'scheme_data': scheme(comps, conns),
    }


# ============================================================
# ПРОЕКТ 12 (medium): Thermal showcase — все 4 уровня нагрева
# ============================================================
def demo_thermal_showcase():
    """Демо-стенд для тепловой аналитики: 5 параллельных резисторов от 12 В,
    подобраны так, чтобы P/TDP попадал в каждую цветовую зону аналитики
    (зелёная → жёлтая → оранжевая → красная) при дефолтном TDP=0.25 Вт.

    P = V²/R, V = 12 В, TDP = 0.25 Вт:
      R1 = 10 кОм → 14 мВт   (~6%)   зелёный, безопасно
      R2 = 1 кОм  → 144 мВт  (~58%)  жёлтый, заметный нагрев
      R3 = 680 Ом → 212 мВт  (~85%)  оранжевый, близко к лимиту
      R4 = 470 Ом → 306 мВт  (~123%) красный, превышение TDP
      R5 = 220 Ом → 654 мВт  (~262%) красный, критическое превышение

    На защите достаточно нажать «▶ Симуляция» — на схеме сразу видно
    цветовой градиент от зелёного до красного, в результатах — таблица
    топ-5 с предупреждениями ⚠️ для перегруженных резисторов.
    """
    comps = [
        _c(0, 'battery', 180, 270, voltage=12),
        _c(1, 'node', 390, 270),  # верхняя шина (V+)
        # Параллельные резисторы — каждый с порта 'a' к верхней шине, 'b' к нижней
        _c(2, 'resistor', 480, 240, resistance=10000),  # green
        _c(3, 'resistor', 480, 300, resistance=1000),  # yellow
        _c(4, 'resistor', 480, 360, resistance=680),  # orange
        _c(5, 'resistor', 480, 420, resistance=470),  # red
        _c(6, 'resistor', 480, 480, resistance=220),  # red²
        _c(7, 'node', 600, 540),  # нижняя шина (GND)
        _c(8, 'ground', 390, 540),
    ]
    conns = [
        # battery+ → верхняя шина
        _w(0, '+', 1, 'a'),
        # верхняя шина → каждый резистор (порт a)
        _w(1, 'a', 2, 'a'),
        _w(1, 'a', 3, 'a'),
        _w(1, 'a', 4, 'a'),
        _w(1, 'a', 5, 'a'),
        _w(1, 'a', 6, 'a'),
        # каждый резистор (порт b) → нижняя шина
        _w(2, 'b', 7, 'a'),
        _w(3, 'b', 7, 'a'),
        _w(4, 'b', 7, 'a'),
        _w(5, 'b', 7, 'a'),
        _w(6, 'b', 7, 'a'),
        # нижняя шина → battery- и → GND
        _w(7, 'a', 0, '-'),
        _w(7, 'a', 8, 'a'),
    ]
    return {
        'name': '🌡 Тепловая шкала: 5 резисторов 12 В',
        'description': (
            'Демо тепловой аналитики: пять параллельных резисторов от батареи 12 В, '
            'подобранных по P=V²/R так, чтобы покрыть все цветовые зоны '
            '(зелёный 6% → жёлтый 58% → оранжевый 85% → красный 123% → 262%). '
            'Запустите симуляцию — увидите ауры всех уровней одновременно '
            'и таблицу «🔥 Тепловая нагрузка».'
        ),
        'difficulty': 'medium',
        'category': 'other',
        'scheme_data': scheme(comps, conns),
    }


# Активный список демо.
# 2026-05-20: возврат 3 «showcase»-схем (R-2R DAC 12-бит, RC-LPF 8-секц,
# двухкаскадный класс A) — раньше были временно изъяты, но это было
# неправильно. Эти схемы — каноника учебников, нельзя их подменять
# упрощёнными огрызками. demo_class_a_amplifier перерисован с более
# просторным шагом (130 px) и чистыми Vcc/GND-шинами.
# Огрызки demo_r2r_dac_4bit / demo_lpf_3section / demo_single_stage_ce
# удалены — больше не нужны.
DEMO_PROJECTS = [
    demo_led_basic,
    demo_voltage_divider,
    demo_rc_filter,
    demo_bridge_rectifier,
    demo_lc_tank,
    demo_wheatstone_bridge,
    demo_cascade_rc_lpf,
    demo_current_divider,
    demo_big_ladder,
    demo_long_rc_chain,
    demo_class_a_amplifier,
    demo_thermal_showcase,
]


class Command(BaseCommand):
    help = 'Создаёт демо-проекты схем разной сложности, принадлежащие пользователю admin.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Удалить все демо-проекты перед созданием.')
        parser.add_argument('--owner', default='admin', help='Логин владельца (по умолчанию admin).')

    @transaction.atomic
    def handle(self, *args, **opts):
        try:
            owner = User.objects.get(username=opts['owner'])
        except User.DoesNotExist:
            self.stderr.write(
                self.style.ERROR(
                    f"Пользователь '{opts['owner']}' не найден. Создайте его или укажите --owner."
                )
            )
            return

        if opts['reset']:
            deleted, _ = SchematicProject.objects.filter(is_demo=True).delete()
            self.stdout.write(self.style.WARNING(f'Удалено демо-проектов: {deleted}'))

        created, updated = 0, 0
        for builder in DEMO_PROJECTS:
            data = builder()
            obj, is_created = SchematicProject.objects.update_or_create(
                user=owner,
                name=data['name'],
                is_demo=True,
                defaults={
                    'description': data['description'],
                    'difficulty': data['difficulty'],
                    'category': data['category'],
                    'status': 'completed',
                    'scheme_data': data['scheme_data'],
                },
            )
            if is_created:
                created += 1
            else:
                updated += 1

        total = SchematicProject.objects.filter(is_demo=True).count()
        self.stdout.write(
            self.style.SUCCESS(f'OK: создано {created}, обновлено {updated}. Всего демо-проектов: {total}.')
        )
