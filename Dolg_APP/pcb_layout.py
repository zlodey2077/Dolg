"""PCB-layout helper для DOLG.

MVP: переводит scheme_data принципиальной схемы в простую разводку платы:
- Компоненты ставятся на координаты из scheme_data, отскалированные в мм
  (CONST PX_PER_MM). Это «простая» авто-разводка — реальная учитывала бы
  вращение, корпуса, минимальные расстояния. Для дипломной демо-уровня
  достаточно показать принцип.
- Соединения отрисовываются как Manhattan-пути между портами компонентов.
- Pads (контактные площадки) — круги Ø 1.6 мм в позициях портов.

Gerber-файл экспортируется в формате RS-274X (industry standard):
- Один слой (top copper) — `*.GTL`
- Aperture: D10 = circle 1.6mm для pads, D11 = circle 0.5mm для трасс
- Команды: G75 (turn on circular interpolation), %FSLAX25Y25*% (формат
  координат), %MOMM*% (миллиметры), G54 (выбор aperture), G01 (linear
  move), D03 (flash pad).

Это не production-Gerber: реальные платы делаются в KiCad/Altium с
DRC-проверками, через-platы, mask-слоями. Но файл проходит синтаксические
проверки большинства gerber-viewer-ов и достаточен для демонстрации.
"""

import math
from collections import defaultdict
from io import StringIO

# Масштаб: 1 единица в scheme_data ≈ ? мм на PCB. Схема в редакторе живёт в
# pixel-grid 30, типичный делитель занимает 200px — пусть это будет 50мм
# на плате. Соотношение 4 px = 1 mm.
PX_PER_MM = 4
PAD_DIAMETER_MM = 1.6
TRACE_WIDTH_MM = 0.5
TRACE_CLEARANCE_MM = 1.5
BOARD_THICKNESS_MM = 1.6
BOARD_GRID_MM = 5.0
HOLE_DIAMETER_MM = 0.8
MIN_BOARD_MM = 50.0

# Минимальное «поле» вокруг bbox схемы (мм) — чтобы pads не упирались в край.
PCB_MARGIN_MM = 5.0

FABRICATION_RULE_PROFILES = {
    'default': {
        'label': 'DOLG default prototype',
        'clearance_mm': TRACE_CLEARANCE_MM,
        'min_trace_width_mm': TRACE_WIDTH_MM,
        'min_drill_mm': HOLE_DIAMETER_MM,
        'min_annular_ring_mm': 0.2,
    },
    'jlcpcb_standard_2layer': {
        'label': 'JLCPCB standard 2-layer',
        'clearance_mm': 0.127,
        'min_trace_width_mm': 0.127,
        'min_drill_mm': 0.3,
        'min_annular_ring_mm': 0.15,
    },
    'pcbway_standard_2layer': {
        'label': 'PCBWay standard 2-layer',
        'clearance_mm': 0.152,
        'min_trace_width_mm': 0.152,
        'min_drill_mm': 0.3,
        'min_annular_ring_mm': 0.15,
    },
    'oshpark_2layer': {
        'label': 'OSH Park 2-layer',
        'clearance_mm': 0.1524,
        'min_trace_width_mm': 0.1524,
        'min_drill_mm': 0.254,
        'min_annular_ring_mm': 0.127,
    },
}


def _fabrication_profile(board_opts):
    profile_id = (
        (board_opts or {}).get('fabrication_profile')
        or (board_opts or {}).get('fabricationProfile')
        or (board_opts or {}).get('manufacturer_profile')
        or (board_opts or {}).get('manufacturerProfile')
        or 'default'
    )
    profile_id = str(profile_id or 'default').strip().lower()
    profile = FABRICATION_RULE_PROFILES.get(profile_id)
    if not profile:
        profile_id = 'default'
        profile = FABRICATION_RULE_PROFILES[profile_id]
    return profile_id, dict(profile)


def _scale(px):
    """Editor pixels → PCB millimeters."""
    return round(px / PX_PER_MM, 3)


def _round3(value):
    return round(value, 3)


def _orthogonal_points(points, route_index=0, clearance_mm=TRACE_CLEARANCE_MM):
    out = []
    lane = ((route_index % 7) - 3) * max(0.55, clearance_mm * 0.38)
    for idx in range(1, len(points)):
        ax, ay = points[idx - 1]
        bx, by = points[idx]
        if abs(ax - bx) < 0.001 or abs(ay - by) < 0.001:
            out.append((bx, by))
            continue
        dx = abs(ax - bx)
        dy = abs(ay - by)
        if dx >= dy:
            mid_x = _round3((ax + bx) / 2 + lane)
            elbows = [(mid_x, ay), (mid_x, by)]
        else:
            mid_y = _round3((ay + by) / 2 + lane)
            elbows = [(ax, mid_y), (bx, mid_y)]
        for point in elbows:
            prev = out[-1] if out else (ax, ay)
            if ((prev[0] - point[0]) ** 2 + (prev[1] - point[1]) ** 2) ** 0.5 >= 0.05:
                out.append(point)
        prev = out[-1] if out else (ax, ay)
        if ((prev[0] - bx) ** 2 + (prev[1] - by) ** 2) ** 0.5 >= 0.05:
            out.append((bx, by))

    result = [points[0]]
    for point in out:
        prev = result[-1]
        if ((prev[0] - point[0]) ** 2 + (prev[1] - point[1]) ** 2) ** 0.5 >= 0.05:
            result.append(point)
    return result


def _snap_up(value, grid=BOARD_GRID_MM):
    return round(((value + grid - 0.0001) // grid) * grid, 3)


def _component_center_px(comp):
    return (comp.get('x', 0) + 30, comp.get('y', 0) + 20)


def _footprint_size_mm(comp):
    """Минимальная синхронизация с 3D footprint-map без новой схемы БД."""
    comp_type = (comp.get('type') or '').lower()
    params = comp.get('catalog_parameters') or comp.get('parameters') or {}
    package = (
        comp.get('package')
        or comp.get('footprint')
        or comp.get('catalog_package')
        or comp.get('package_type')
        or params.get('package')
        or params.get('footprint')
        or params.get('package_type')
        or ''
    ).upper()
    body = params.get('body_mm') or comp.get('body_mm') or {}
    if (
        isinstance(body, dict)
        and (body.get('w') or body.get('width'))
        and (body.get('h') or body.get('height'))
    ):
        return (float(body.get('w') or body.get('width')), float(body.get('h') or body.get('height')))
    if any(token in package for token in ('0805', '0603', '1206', '1210', '0402', 'SMD', 'CHIP')):
        if '1206' in package:
            return (3.2, 1.6)
        if '0603' in package:
            return (1.6, 0.8)
        return (2.0, 1.25)
    if 'DIP' in package or comp_type == 'ic':
        pins = _pin_count(package, 8)
        return (max(9, pins * 1.3), 7.6)
    if any(token in package for token in ('SOIC', 'SOP', 'TSSOP', 'SSOP')):
        pins = _pin_count(package, 8)
        return (max(5, pins * 0.75), 4.4 if 'TSSOP' in package or 'SSOP' in package else 5.4)
    if 'TO-220' in package:
        return (10.2, 4.6)
    if 'SOT-23' in package:
        return (2.9, 1.6)
    type_size_mm = {
        'resistor': (10, 3.2),
        'capacitor': (5, 5),
        'inductor': (9, 4),
        'diode': (8, 3),
        'led': (5, 5),
        'battery': (18, 12),
        'transistor': (5.2, 4.2),
        'npn': (5.2, 4.2),
        'pnp': (5.2, 4.2),
        'switch': (10, 6),
        'ground': (4, 4),
        'node': (2, 2),
    }
    return type_size_mm.get(comp_type, (8, 5))


def _pin_count(package, fallback):
    import re

    match = re.search(r'(?:DIP|SOIC|SOP|TSSOP|SSOP|QFP|QFN|SOT)-?\s*(\d+)', package or '', re.I)
    return max(2, int(match.group(1))) if match else fallback


def _as_float(value, default=0.0):
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _distance(a, b):
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def _point_segment_distance(px, py, ax, ay, bx, by):
    dx = bx - ax
    dy = by - ay
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    nearest_x = ax + t * dx
    nearest_y = ay + t * dy
    return math.hypot(px - nearest_x, py - nearest_y)


def _orientation(ax, ay, bx, by, cx, cy):
    value = (by - ay) * (cx - bx) - (bx - ax) * (cy - by)
    if abs(value) < 1e-9:
        return 0
    return 1 if value > 0 else 2


def _on_segment(ax, ay, bx, by, cx, cy):
    return (
        min(ax, cx) - 1e-9 <= bx <= max(ax, cx) + 1e-9
        and min(ay, cy) - 1e-9 <= by <= max(ay, cy) + 1e-9
    )


def _segments_intersect(a, b, c, d):
    ax, ay = a
    bx, by = b
    cx, cy = c
    dx, dy = d
    o1 = _orientation(ax, ay, bx, by, cx, cy)
    o2 = _orientation(ax, ay, bx, by, dx, dy)
    o3 = _orientation(cx, cy, dx, dy, ax, ay)
    o4 = _orientation(cx, cy, dx, dy, bx, by)
    if o1 != o2 and o3 != o4:
        return True
    if o1 == 0 and _on_segment(ax, ay, cx, cy, bx, by):
        return True
    if o2 == 0 and _on_segment(ax, ay, dx, dy, bx, by):
        return True
    if o3 == 0 and _on_segment(cx, cy, ax, ay, dx, dy):
        return True
    if o4 == 0 and _on_segment(cx, cy, bx, by, dx, dy):
        return True
    return False


def _segment_distance(a, b, c, d):
    if _segments_intersect(a, b, c, d):
        return 0.0
    ax, ay = a
    bx, by = b
    cx, cy = c
    dx, dy = d
    return min(
        _point_segment_distance(ax, ay, cx, cy, dx, dy),
        _point_segment_distance(bx, by, cx, cy, dx, dy),
        _point_segment_distance(cx, cy, ax, ay, bx, by),
        _point_segment_distance(dx, dy, ax, ay, bx, by),
    )


def _point_rect_distance(px, py, rect):
    x0, y0, x1, y1 = rect
    dx = max(x0 - px, 0.0, px - x1)
    dy = max(y0 - py, 0.0, py - y1)
    return math.hypot(dx, dy)


def _rect_distance(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    dx = max(bx0 - ax1, ax0 - bx1, 0.0)
    dy = max(by0 - ay1, ay0 - by1, 0.0)
    return math.hypot(dx, dy)


def _segment_rect_distance(a, b, rect):
    ax, ay = a
    bx, by = b
    x0, y0, x1, y1 = rect
    if x0 <= ax <= x1 and y0 <= ay <= y1:
        return 0.0
    if x0 <= bx <= x1 and y0 <= by <= y1:
        return 0.0
    edges = (
        ((x0, y0), (x1, y0)),
        ((x1, y0), (x1, y1)),
        ((x1, y1), (x0, y1)),
        ((x0, y1), (x0, y0)),
    )
    if any(_segments_intersect(a, b, edge_a, edge_b) for edge_a, edge_b in edges):
        return 0.0
    return min(
        _point_rect_distance(ax, ay, rect),
        _point_rect_distance(bx, by, rect),
        *(_point_segment_distance(x, y, ax, ay, bx, by) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))),
    )


def _ipc2221_external_width_mm(current_a, copper_oz=1.0, temp_rise_c=10.0):
    """Approximate IPC-2221 external trace width for current carrying checks."""
    current_a = _as_float(current_a, 0.0)
    copper_oz = max(_as_float(copper_oz, 1.0), 0.25)
    temp_rise_c = max(_as_float(temp_rise_c, 10.0), 1.0)
    if current_a <= 0:
        return 0.0
    area_mil2 = (current_a / (0.048 * (temp_rise_c**0.44))) ** (1 / 0.725)
    copper_thickness_mil = 1.378 * copper_oz
    width_mil = area_mil2 / copper_thickness_mil
    return round(width_mil * 0.0254, 3)


def _component_rect(comp, expand_mm=0.0):
    x0 = _as_float(comp.get('x_left_mm'), _as_float(comp.get('x_mm')) - _as_float(comp.get('w_mm')) / 2)
    y0 = _as_float(comp.get('y_top_mm'), _as_float(comp.get('y_mm')) - _as_float(comp.get('h_mm')) / 2)
    x1 = x0 + _as_float(comp.get('w_mm'))
    y1 = y0 + _as_float(comp.get('h_mm'))
    return (x0 - expand_mm, y0 - expand_mm, x1 + expand_mm, y1 + expand_mm)


def _endpoint_key(endpoint):
    endpoint = endpoint or {}
    return (
        endpoint.get('compId') or endpoint.get('componentId') or endpoint.get('id'),
        endpoint.get('portId')
        or endpoint.get('pinId')
        or endpoint.get('port')
        or endpoint.get('pin')
        or '',
    )


def _component_kind(comp):
    text = ' '.join(
        str(comp.get(key) or '')
        for key in ('type', 'label', 'name', 'package', 'footprint', 'catalog_package', 'package_type')
    ).lower()
    return text


def analyze_pcb_drc(layout, scheme_data=None):
    """Headless PCB DRC for generated layouts.

    The checks are intentionally conservative and deterministic: they do not
    replace KiCad/Altium DRC, but catch obvious issues before Gerber export and
    provide a reusable server-side contract for protocol/PDF generation.
    """
    layout = layout or {}
    scheme_data = scheme_data or {}
    board_opts = scheme_data.get('board') or {}
    profile_id, profile = _fabrication_profile(board_opts)
    profile_clearance_mm = _as_float(profile.get('clearance_mm'), TRACE_CLEARANCE_MM)
    profile_min_trace_width_mm = _as_float(profile.get('min_trace_width_mm'), TRACE_WIDTH_MM)
    min_drill_mm = _as_float(profile.get('min_drill_mm'), HOLE_DIAMETER_MM)
    min_annular_ring_mm = _as_float(profile.get('min_annular_ring_mm'), 0.2)
    clearance_mm = _as_float(
        board_opts.get('clearance_mm') or board_opts.get('clearanceMm'),
        profile_clearance_mm,
    )
    min_trace_width_mm = _as_float(
        board_opts.get('min_trace_width_mm') or board_opts.get('minTraceWidthMm'),
        profile_min_trace_width_mm,
    )
    copper_oz = _as_float(board_opts.get('copper_oz') or board_opts.get('copperOz'), 1.0)
    temp_rise_c = _as_float(board_opts.get('temp_rise_c') or board_opts.get('tempRiseC'), 10.0)
    decoupling_max_mm = _as_float(
        board_opts.get('decoupling_max_distance_mm') or board_opts.get('decouplingMaxDistanceMm'),
        15.0,
    )
    pcb_w_mm = _as_float(layout.get('pcb_w_mm'), MIN_BOARD_MM)
    pcb_h_mm = _as_float(layout.get('pcb_h_mm'), MIN_BOARD_MM)
    components = layout.get('comps', []) or []
    pads = layout.get('pads', []) or []
    traces = layout.get('traces', []) or []
    connections = scheme_data.get('connections', []) or []

    issues = []
    issue_limits = defaultdict(int)
    suppressed = defaultdict(int)

    def add_issue(severity, code, title, detail, refs=None, value=None, limit=8):
        if issue_limits[code] >= limit:
            suppressed[code] += 1
            return
        issue_limits[code] += 1
        issues.append(
            {
                'severity': severity,
                'code': code,
                'title': title,
                'detail': detail,
                'refs': refs or [],
                'value': value,
            }
        )

    conn_by_route = {index: conn for index, conn in enumerate(connections)}
    conn_endpoints = {
        index: {_endpoint_key(conn.get('from')), _endpoint_key(conn.get('to'))}
        for index, conn in enumerate(connections)
    }

    trace_segments = []
    for index, tr in enumerate(traces):
        start = (_as_float((tr.get('from') or {}).get('x_mm')), _as_float((tr.get('from') or {}).get('y_mm')))
        end = (_as_float((tr.get('to') or {}).get('x_mm')), _as_float((tr.get('to') or {}).get('y_mm')))
        route_index = tr.get('route_index')
        if route_index is None:
            route_index = tr.get('conn_index')
        route_index = int(route_index) if isinstance(route_index, int) or str(route_index).isdigit() else None
        conn_key = tr.get('conn_id') if tr.get('conn_id') is not None else route_index
        trace_segments.append(
            {
                'index': index,
                'start': start,
                'end': end,
                'layer': tr.get('layer') or 'top',
                'width_mm': _as_float(tr.get('width_mm'), _as_float(layout.get('trace_width_mm'), TRACE_WIDTH_MM)),
                'conn_key': conn_key,
                'route_index': route_index,
            }
        )

    for tr in trace_segments:
        width_mm = tr['width_mm']
        if width_mm < min_trace_width_mm:
            add_issue(
                'error',
                'trace_width_min',
                'Дорожка уже минимального правила',
                f'Сегмент #{tr["index"] + 1}: {width_mm:.2f} мм < {min_trace_width_mm:.2f} мм.',
                refs=[f'trace:{tr["index"]}'],
                value={'actual_mm': width_mm, 'required_mm': min_trace_width_mm},
            )
        for point in (tr['start'], tr['end']):
            x_mm, y_mm = point
            if x_mm < 0 or y_mm < 0 or x_mm > pcb_w_mm or y_mm > pcb_h_mm:
                add_issue(
                    'error',
                    'trace_outside_board',
                    'Дорожка выходит за контур платы',
                    f'Сегмент #{tr["index"] + 1}: точка ({x_mm:.2f}; {y_mm:.2f}) вне {pcb_w_mm:.1f}x{pcb_h_mm:.1f} мм.',
                    refs=[f'trace:{tr["index"]}'],
                )

    for route_index, conn in conn_by_route.items():
        current_a = _as_float(
            conn.get('current_a')
            or conn.get('currentA')
            or conn.get('expected_current_a')
            or conn.get('max_current_a'),
            0.0,
        )
        required_width = _ipc2221_external_width_mm(current_a, copper_oz=copper_oz, temp_rise_c=temp_rise_c)
        if required_width <= 0:
            continue
        actual_width = min(
            (tr['width_mm'] for tr in trace_segments if tr['route_index'] == route_index),
            default=_as_float(layout.get('trace_width_mm'), TRACE_WIDTH_MM),
        )
        if actual_width + 1e-9 < required_width:
            label = conn.get('label') or conn.get('net') or conn.get('id') or f'net #{route_index + 1}'
            add_issue(
                'error',
                'trace_width_current',
                'Дорожка тонкая для заданного тока',
                f'{label}: {actual_width:.2f} мм, нужно около {required_width:.2f} мм по IPC-2221 для {current_a:.2f} А.',
                refs=[f'connection:{route_index}'],
                value={'actual_mm': actual_width, 'required_mm': required_width, 'current_a': current_a},
            )

    for i, first in enumerate(trace_segments):
        for second in trace_segments[i + 1 :]:
            if first['layer'] != second['layer']:
                continue
            if first['conn_key'] is not None and first['conn_key'] == second['conn_key']:
                continue
            required = clearance_mm + (first['width_mm'] + second['width_mm']) / 2
            actual = _segment_distance(first['start'], first['end'], second['start'], second['end'])
            if actual + 1e-9 < required:
                add_issue(
                    'error',
                    'trace_clearance',
                    'Между дорожками недостаточный зазор',
                    f'Сегменты #{first["index"] + 1} и #{second["index"] + 1}: {actual:.2f} мм < {required:.2f} мм.',
                    refs=[f'trace:{first["index"]}', f'trace:{second["index"]}'],
                    value={'actual_mm': round(actual, 3), 'required_mm': round(required, 3)},
                )

    for i, first in enumerate(pads):
        first_xy = (_as_float(first.get('x_mm')), _as_float(first.get('y_mm')))
        first_radius = _as_float(first.get('diameter_mm'), PAD_DIAMETER_MM) / 2
        first_hole = _as_float(first.get('hole_mm'), HOLE_DIAMETER_MM)
        if first_hole + 1e-9 < min_drill_mm:
            add_issue(
                'error',
                'pad_drill_min',
                'Отверстие pad меньше фабричного минимума',
                f'{first.get("comp_id")}:{first.get("port_id")}: {first_hole:.2f} мм < {min_drill_mm:.2f} мм.',
                refs=[f'pad:{first.get("comp_id")}:{first.get("port_id")}'],
                value={'actual_mm': first_hole, 'required_mm': min_drill_mm},
            )
        first_annular = first_radius - first_hole / 2
        if first_annular + 1e-9 < min_annular_ring_mm:
            add_issue(
                'error',
                'pad_annular_ring',
                'Annular ring pad меньше фабричного минимума',
                f'{first.get("comp_id")}:{first.get("port_id")}: {first_annular:.2f} мм < {min_annular_ring_mm:.2f} мм.',
                refs=[f'pad:{first.get("comp_id")}:{first.get("port_id")}'],
                value={'actual_mm': round(first_annular, 3), 'required_mm': min_annular_ring_mm},
            )
        for second in pads[i + 1 :]:
            if first.get('comp_id') == second.get('comp_id'):
                continue
            second_xy = (_as_float(second.get('x_mm')), _as_float(second.get('y_mm')))
            second_radius = _as_float(second.get('diameter_mm'), PAD_DIAMETER_MM) / 2
            actual = _distance(first_xy, second_xy)
            required = clearance_mm + first_radius + second_radius
            if actual + 1e-9 < required:
                add_issue(
                    'error',
                    'pad_clearance',
                    'Контактные площадки слишком близко',
                    f'{first.get("comp_id")}:{first.get("port_id")} и {second.get("comp_id")}:{second.get("port_id")}: '
                    f'{actual:.2f} мм < {required:.2f} мм.',
                    refs=[f'pad:{first.get("comp_id")}:{first.get("port_id")}', f'pad:{second.get("comp_id")}:{second.get("port_id")}'],
                    value={'actual_mm': round(actual, 3), 'required_mm': round(required, 3)},
                )

    for index, via in enumerate(layout.get('vias', []) or []):
        diameter = _as_float(via.get('diameter_mm'), 1.1)
        hole = _as_float(via.get('hole_mm'), 0.45)
        if hole + 1e-9 < min_drill_mm:
            add_issue(
                'error',
                'via_drill_min',
                'Отверстие via меньше фабричного минимума',
                f'Via #{index + 1}: {hole:.2f} мм < {min_drill_mm:.2f} мм.',
                refs=[f'via:{index}'],
                value={'actual_mm': hole, 'required_mm': min_drill_mm},
            )
        annular = diameter / 2 - hole / 2
        if annular + 1e-9 < min_annular_ring_mm:
            add_issue(
                'error',
                'via_annular_ring',
                'Annular ring via меньше фабричного минимума',
                f'Via #{index + 1}: {annular:.2f} мм < {min_annular_ring_mm:.2f} мм.',
                refs=[f'via:{index}'],
                value={'actual_mm': round(annular, 3), 'required_mm': min_annular_ring_mm},
            )

    for tr in trace_segments:
        endpoint_keys = conn_endpoints.get(tr['route_index']) or set()
        for pad in pads:
            pad_key = (pad.get('comp_id'), pad.get('port_id'))
            if pad_key in endpoint_keys:
                continue
            pad_xy = (_as_float(pad.get('x_mm')), _as_float(pad.get('y_mm')))
            required = clearance_mm + _as_float(pad.get('diameter_mm'), PAD_DIAMETER_MM) / 2 + tr['width_mm'] / 2
            actual = _point_segment_distance(*pad_xy, *tr['start'], *tr['end'])
            if actual + 1e-9 < required:
                add_issue(
                    'error',
                    'trace_pad_clearance',
                    'Дорожка слишком близко к чужому pad',
                    f'Сегмент #{tr["index"] + 1} и pad {pad.get("comp_id")}:{pad.get("port_id")}: '
                    f'{actual:.2f} мм < {required:.2f} мм.',
                    refs=[f'trace:{tr["index"]}', f'pad:{pad.get("comp_id")}:{pad.get("port_id")}'],
                    value={'actual_mm': round(actual, 3), 'required_mm': round(required, 3)},
                )

    for i, first in enumerate(components):
        first_rect = _component_rect(first)
        for second in components[i + 1 :]:
            actual = _rect_distance(first_rect, _component_rect(second))
            if actual + 1e-9 < clearance_mm:
                add_issue(
                    'warning',
                    'component_courtyard',
                    'Футпринты компонентов слишком близко',
                    f'{first.get("label") or first.get("id")} и {second.get("label") or second.get("id")}: '
                    f'{actual:.2f} мм < {clearance_mm:.2f} мм.',
                    refs=[f'component:{first.get("id")}', f'component:{second.get("id")}'],
                )

    component_rects = [(comp, _component_rect(comp, clearance_mm)) for comp in components]
    for tr in trace_segments:
        endpoint_component_ids = {key[0] for key in (conn_endpoints.get(tr['route_index']) or set())}
        for comp, rect in component_rects:
            if comp.get('id') in endpoint_component_ids:
                continue
            actual = _segment_rect_distance(tr['start'], tr['end'], rect)
            if actual <= 1e-9:
                add_issue(
                    'warning',
                    'trace_component_courtyard',
                    'Дорожка пересекает keep-out компонента',
                    f'Сегмент #{tr["index"] + 1} проходит через область {comp.get("label") or comp.get("id")}.',
                    refs=[f'trace:{tr["index"]}', f'component:{comp.get("id")}'],
                )

    capacitors = [comp for comp in components if 'capacitor' in _component_kind(comp) or str(comp.get('label') or '').upper().startswith('C')]
    ic_like = [
        comp
        for comp in components
        if any(
            token in _component_kind(comp)
            for token in ('ic', 'mcu', 'microcontroller', 'processor', 'opamp', 'op-amp', 'adc', 'dac', 'regulator')
        )
    ]
    for comp in ic_like:
        comp_xy = (_as_float(comp.get('x_mm')), _as_float(comp.get('y_mm')))
        nearest = min((_distance(comp_xy, (_as_float(cap.get('x_mm')), _as_float(cap.get('y_mm')))) for cap in capacitors), default=None)
        if nearest is None or nearest > decoupling_max_mm:
            detail = (
                f'{comp.get("label") or comp.get("id")}: нет развязывающего конденсатора ближе {decoupling_max_mm:.1f} мм.'
                if nearest is None
                else f'{comp.get("label") or comp.get("id")}: ближайший конденсатор {nearest:.1f} мм, лимит {decoupling_max_mm:.1f} мм.'
            )
            add_issue(
                'warning',
                'decoupling_distance',
                'Развязка питания далеко от IC/MCU',
                detail,
                refs=[f'component:{comp.get("id")}'],
            )

    graph = defaultdict(set)
    ground_nodes = []
    component_by_id = {comp.get('id'): comp for comp in components}
    for conn in connections:
        a = _endpoint_key(conn.get('from'))
        b = _endpoint_key(conn.get('to'))
        graph[a].add(b)
        graph[b].add(a)
    for comp_id, comp in component_by_id.items():
        kind = _component_kind(comp)
        if 'ground' in kind or 'gnd' in kind:
            comp_pads = [key for key in graph if key[0] == comp_id]
            ground_nodes.extend(comp_pads or [(comp_id, '')])
    if len(ground_nodes) > 1:
        seen = set()
        stack = [ground_nodes[0]]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            stack.extend(graph.get(node, set()) - seen)
        missing = [node for node in ground_nodes if node not in seen]
        if missing:
            add_issue(
                'warning',
                'ground_split',
                'Земля разбита на несвязанные участки',
                f'Найдено {len(missing)} GND-точек вне основной связной группы.',
                refs=[f'pad:{node[0]}:{node[1]}' for node in missing[:5]],
            )

    for code, count in suppressed.items():
        add_issue(
            'info',
            'issues_suppressed',
            'Часть однотипных DRC-сообщений скрыта',
            f'{code}: скрыто ещё {count} сообщений, чтобы отчёт оставался читаемым.',
            refs=[],
            limit=99,
        )

    summary = {
        'errors': sum(1 for issue in issues if issue['severity'] == 'error'),
        'warnings': sum(1 for issue in issues if issue['severity'] == 'warning'),
        'info': sum(1 for issue in issues if issue['severity'] == 'info'),
        'total': len(issues),
    }
    if summary['errors']:
        status = 'fail'
    elif summary['warnings']:
        status = 'warn'
    else:
        status = 'pass'
    return {
        'ok': status != 'fail',
        'status': status,
        'summary': summary,
        'issues': issues,
        'rules': {
            'profile_id': profile_id,
            'profile_label': profile.get('label') or profile_id,
            'clearance_mm': clearance_mm,
            'min_trace_width_mm': min_trace_width_mm,
            'min_drill_mm': min_drill_mm,
            'min_annular_ring_mm': min_annular_ring_mm,
            'copper_oz': copper_oz,
            'temp_rise_c': temp_rise_c,
            'decoupling_max_mm': decoupling_max_mm,
        },
    }


def compute_pcb_layout(scheme_data):
    """Вход: scheme_data из SchematicProject. Выход:
    {
      'pads':  [{'x_mm', 'y_mm', 'comp_id', 'port_id'}, ...],
      'traces':[{'from':{'x_mm','y_mm'}, 'to':{...}, 'conn_id'}, ...],
      'comps': [{'id','type','label','x_mm','y_mm','w_mm','h_mm'}, ...],
      'pcb_w_mm': float, 'pcb_h_mm': float,
      'origin_x_mm': float, 'origin_y_mm': float,  # для центровки
    }
    """
    scheme_data = scheme_data or {}
    board_opts = scheme_data.get('board') or {}
    margin_mm = float(board_opts.get('margin_mm') or board_opts.get('marginMm') or PCB_MARGIN_MM)
    trace_width_mm = float(
        board_opts.get('trace_width_mm') or board_opts.get('traceWidthMm') or TRACE_WIDTH_MM
    )
    clearance_mm = float(
        board_opts.get('clearance_mm') or board_opts.get('clearanceMm') or TRACE_CLEARANCE_MM
    )
    grid_mm = float(board_opts.get('grid_mm') or board_opts.get('gridMm') or BOARD_GRID_MM)
    thickness_mm = float(
        board_opts.get('thickness_mm') or board_opts.get('thicknessMm') or BOARD_THICKNESS_MM
    )
    components = scheme_data.get('components', []) or []
    connections = scheme_data.get('connections', []) or []

    # Bbox исходной схемы в pixels — чтобы потом сдвинуть в (0,0) с margin.
    if not components:
        return {
            'pads': [],
            'traces': [],
            'comps': [],
            'vias': [],
            'holes': [],
            'pcb_w_mm': MIN_BOARD_MM,
            'pcb_h_mm': MIN_BOARD_MM,
            'thickness_mm': thickness_mm,
            'trace_width_mm': trace_width_mm,
            'clearance_mm': clearance_mm,
            'origin_x_mm': 0,
            'origin_y_mm': 0,
        }

    min_x, min_y = float('inf'), float('inf')
    max_x, max_y = float('-inf'), float('-inf')

    def include_px(x_px, y_px):
        nonlocal min_x, min_y, max_x, max_y
        min_x = min(min_x, x_px)
        min_y = min(min_y, y_px)
        max_x = max(max_x, x_px)
        max_y = max(max_y, y_px)

    for comp in components:
        cx_px, cy_px = _component_center_px(comp)
        w_mm, h_mm = _footprint_size_mm(comp)
        half_w_px = max(8, w_mm * PX_PER_MM / 2)
        half_h_px = max(8, h_mm * PX_PER_MM / 2)
        include_px(cx_px - half_w_px, cy_px - half_h_px)
        include_px(cx_px + half_w_px, cy_px + half_h_px)
        for port in comp.get('ports', []) or []:
            include_px(cx_px + port.get('x', 0), cy_px + port.get('y', 0))
    for conn in connections:
        for point in (conn.get('waypoints') or []) + (conn.get('vias') or []):
            include_px(point.get('x', 0), point.get('y', 0))

    raw_w_mm = _scale(max_x - min_x) + 2 * margin_mm
    raw_h_mm = _scale(max_y - min_y) + 2 * margin_mm
    pcb_w_mm = _snap_up(max(MIN_BOARD_MM, raw_w_mm), grid_mm)
    pcb_h_mm = _snap_up(max(MIN_BOARD_MM, raw_h_mm), grid_mm)
    extra_x_mm = max(0, (pcb_w_mm - raw_w_mm) / 2)
    extra_y_mm = max(0, (pcb_h_mm - raw_h_mm) / 2)

    # Helper: переводит editor (px) → PCB (mm) с учётом смещения и margin.
    def _to_mm(x_px, y_px):
        return (
            round(_scale(x_px - min_x) + margin_mm + extra_x_mm, 3),
            round(_scale(y_px - min_y) + margin_mm + extra_y_mm, 3),
        )

    comps_out = []
    pads_by_port = {}  # (comp_id, port_id) → (x_mm, y_mm) — для traces
    for comp in components:
        cx_px, cy_px = _component_center_px(comp)
        cx_mm, cy_mm = _to_mm(cx_px, cy_px)
        w_mm, h_mm = _footprint_size_mm(comp)
        # x_mm/y_mm — центр (нужен 3D-рендеру / Gerber-логике). Для SVG-rect
        # храним готовые left-top, чтобы шаблон не нужно было заставлять
        # делать арифметику ({% widthratio %} не считает с дробями). Раньше
        # шаблон рисовал rect от center'а → коробки уезжали на (w/2, h/2)
        # от своих pads и казалось, что компонент «оторван» от ножек.
        label_text = (comp.get('label') or comp.get('type') or '').strip()
        comps_out.append(
            {
                'id': comp.get('id'),
                'type': comp.get('type'),
                'label': label_text,
                'x_mm': cx_mm,
                'y_mm': cy_mm,
                'w_mm': w_mm,
                'h_mm': h_mm,
                # Готовый rect-bbox для SVG
                'x_left_mm': round(cx_mm - w_mm / 2, 3),
                'y_top_mm': round(cy_mm - h_mm / 2, 3),
                # Подпись — над компонентом (с отступом 1.2мм от верх. грани).
                'label_x_mm': cx_mm,
                'label_y_mm': round(cy_mm - h_mm / 2 - 1.2, 3),
                'rotation': comp.get('rotation', 0),
                'side': comp.get('side', 'top'),
            }
        )
        # Pads: ports на компоненте; берём их координаты из ports[].x/y
        # (offset относительно центра компонента в editor px).
        ports = comp.get('ports', []) or [{'id': '1', 'x': -20, 'y': 0}, {'id': '2', 'x': 20, 'y': 0}]
        for index, port in enumerate(ports):
            port_id = port.get('id') or port.get('name') or str(index + 1)
            px = cx_px + (port.get('x', 0))
            py = cy_px + (port.get('y', 0))
            pad_x_mm, pad_y_mm = _to_mm(px, py)
            pads_by_port[(comp.get('id'), port_id)] = (pad_x_mm, pad_y_mm)

    pads_out = [
        {
            'x_mm': xy[0],
            'y_mm': xy[1],
            'comp_id': key[0],
            'port_id': key[1],
            'diameter_mm': PAD_DIAMETER_MM,
            'hole_mm': HOLE_DIAMETER_MM,
        }
        for key, xy in pads_by_port.items()
    ]

    def _endpoint_key(endpoint):
        endpoint = endpoint or {}
        return (
            endpoint.get('compId') or endpoint.get('componentId') or endpoint.get('id'),
            endpoint.get('portId')
            or endpoint.get('pinId')
            or endpoint.get('port')
            or endpoint.get('pin')
            or '',
        )

    # Traces: HV-routing (2-layer manhattan) + автоматические vias.
    # Классическая схема: H-сегменты идут по TOP, V-сегменты по BOTTOM.
    # Это исключает пересечения трасс на одном слое и даёт «настоящий» PCB
    # вид в 3D viewer'е. Если у conn явно указан layer (импорт) — соблюдаем.
    traces_out = []
    vias_out = []
    AUTO_VIA_DIAMETER_MM = 1.1
    AUTO_VIA_HOLE_MM = 0.45

    def _seg_layer(ax, ay, bx, by):
        """Возвращает layer для сегмента: 'top' для горизонтального, 'bottom' для вертикального."""
        return 'top' if abs(bx - ax) >= abs(by - ay) else 'bottom'

    def _is_via_position(pads_set, x_mm, y_mm, tol=0.05):
        """Не ставим via в позицию pad'а — там нет смысла, pad сам соединяет слои."""
        return any(abs(px - x_mm) < tol and abs(py - y_mm) < tol for (px, py) in pads_set)

    pads_position_set = {(p['x_mm'], p['y_mm']) for p in pads_out}

    for route_index, conn in enumerate(connections):
        f_pad = pads_by_port.get(_endpoint_key(conn.get('from')))
        t_pad = pads_by_port.get(_endpoint_key(conn.get('to')))
        if not f_pad or not t_pad:
            continue
        points = [f_pad]
        for waypoint in conn.get('waypoints') or []:
            points.append(_to_mm(waypoint.get('x', 0), waypoint.get('y', 0)))
        points.append(t_pad)
        points = _orthogonal_points(points, route_index, clearance_mm)

        # Явный layer (импорт из KiCad/Eagle) — приоритет
        forced_layer = 'bottom' if conn.get('layer') == 'bottom' else None
        trace_w = float(conn.get('width_mm') or conn.get('widthMm') or trace_width_mm)

        prev_layer = None
        for idx in range(1, len(points)):
            ax, ay = points[idx - 1]
            bx, by = points[idx]
            # Определяем слой сегмента
            if forced_layer is not None:
                seg_layer = forced_layer
            else:
                seg_layer = _seg_layer(ax, ay, bx, by)

            # Vias на переходе между слоями — H↔V → нужен via в углу
            if prev_layer is not None and prev_layer != seg_layer:
                if not _is_via_position(pads_position_set, ax, ay):
                    vias_out.append(
                        {
                            'x_mm': _round3(ax),
                            'y_mm': _round3(ay),
                            'diameter_mm': AUTO_VIA_DIAMETER_MM,
                            'hole_mm': AUTO_VIA_HOLE_MM,
                            'auto': True,
                            'conn_id': conn.get('id'),
                        }
                    )

            traces_out.append(
                {
                    'from': {'x_mm': ax, 'y_mm': ay},
                    'to': {'x_mm': bx, 'y_mm': by},
                    'conn_id': conn.get('id'),
                    'route_index': route_index,
                    'layer': seg_layer,
                    'width_mm': trace_w,
                }
            )
            prev_layer = seg_layer

        # Vias из импортированной схемы (если есть)
        for via in conn.get('vias') or []:
            x_mm, y_mm = _to_mm(via.get('x', 0), via.get('y', 0))
            vias_out.append(
                {
                    'x_mm': x_mm,
                    'y_mm': y_mm,
                    'diameter_mm': float(via.get('diameter_mm') or via.get('diameterMm') or 1.1),
                    'hole_mm': float(via.get('hole_mm') or via.get('holeMm') or 0.45),
                }
            )

    holes_out = []
    hole_inset = min(5.0, pcb_w_mm / 8, pcb_h_mm / 8)
    if pcb_w_mm >= 35 and pcb_h_mm >= 35:
        for x_mm, y_mm in (
            (hole_inset, hole_inset),
            (pcb_w_mm - hole_inset, hole_inset),
            (hole_inset, pcb_h_mm - hole_inset),
            (pcb_w_mm - hole_inset, pcb_h_mm - hole_inset),
        ):
            holes_out.append(
                {'x_mm': round(x_mm, 3), 'y_mm': round(y_mm, 3), 'diameter_mm': 3.2, 'kind': 'mount'}
            )

    return {
        'pads': pads_out,
        'traces': traces_out,
        'comps': comps_out,
        'vias': vias_out,
        'holes': holes_out,
        'pcb_w_mm': pcb_w_mm,
        'pcb_h_mm': pcb_h_mm,
        'thickness_mm': thickness_mm,
        'trace_width_mm': trace_width_mm,
        'clearance_mm': clearance_mm,
        'margin_mm': margin_mm,
        'origin_x_mm': 0,
        'origin_y_mm': 0,
    }


def to_gerber_top_copper(layout):
    """RS-274X (extended Gerber). Один слой (top copper), флешит pads и
    рисует traces. Не включает silkscreen, mask, drill — отдельный файл.

    Координаты в формате 2.5 (5 цифр после запятой); ngspice/gEDA gerbview
    распознают этот формат.
    """
    out = StringIO()
    # Header
    out.write('G04 DOLG PCB Layout — top copper layer*\n')
    out.write('%FSLAX25Y25*%\n')  # формат координат: 2 целых, 5 дробных
    out.write('%MOMM*%\n')  # единицы — миллиметры
    out.write('%LPD*%\n')  # polarity dark (рисуем медь)
    # Apertures
    out.write(f'%ADD10C,{PAD_DIAMETER_MM}*%\n')  # D10 = pad circle
    out.write(f'%ADD11C,{TRACE_WIDTH_MM}*%\n')  # D11 = trace circle
    out.write('G75*\n')  # multi-quadrant arc (на будущее)
    out.write('G01*\n')  # linear interpolation

    def _coord(mm):
        # 2.5: умножаем на 1e5, дописываем ведущие нули если нужно.
        return f'{int(round(mm * 1e5)):07d}'

    # Traces: D11 + G01 + от→до
    out.write('D11*\n')
    for tr in layout['traces']:
        f = tr['from']
        t = tr['to']
        out.write(f'X{_coord(f["x_mm"])}Y{_coord(f["y_mm"])}D02*\n')  # move
        out.write(f'X{_coord(t["x_mm"])}Y{_coord(t["y_mm"])}D01*\n')  # draw to
    # Pads: D10 + flash (D03)
    out.write('D10*\n')
    for pad in layout['pads']:
        out.write(f'X{_coord(pad["x_mm"])}Y{_coord(pad["y_mm"])}D03*\n')

    out.write('M02*\n')  # End-of-file
    return out.getvalue()


def to_gerber_drill(layout):
    """Excellon drill format (NC drill) — отдельный файл *.DRL для отверстий.
    Минимальная версия: одно сверло, по флешу на каждую pad.
    """
    out = StringIO()
    out.write('M48\n')  # начало header'а
    out.write('METRIC,LZ\n')  # mm + leading zeros
    out.write('T01C0.80\n')  # tool 1, диаметр 0.8 mm
    out.write('%\n')  # конец header
    out.write('G90\n')  # absolute mode
    out.write('M71\n')  # metric units
    out.write('T01\n')  # выбираем tool 1
    for pad in layout['pads']:
        # X/Y в мм с точкой; LZ означает «leading zeros», ничего не убираем
        out.write(f'X{pad["x_mm"]:.3f}Y{pad["y_mm"]:.3f}\n')
    for via in layout.get('vias', []):
        out.write(f'X{via["x_mm"]:.3f}Y{via["y_mm"]:.3f}\n')
    for hole in layout.get('holes', []):
        out.write(f'X{hole["x_mm"]:.3f}Y{hole["y_mm"]:.3f}\n')
    out.write('T00\n')  # деселект tool
    out.write('M30\n')  # end of program
    return out.getvalue()
