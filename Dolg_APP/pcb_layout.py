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
        comp.get('package') or comp.get('footprint') or comp.get('catalog_package') or
        comp.get('package_type') or params.get('package') or params.get('footprint') or
        params.get('package_type') or ''
    ).upper()
    body = params.get('body_mm') or comp.get('body_mm') or {}
    if isinstance(body, dict) and (body.get('w') or body.get('width')) and (body.get('h') or body.get('height')):
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
        'npn': (5.2, 4.2), 'pnp': (5.2, 4.2),
        'switch': (10, 6),
        'ground': (4, 4),
        'node': (2, 2),
    }
    return type_size_mm.get(comp_type, (8, 5))


def _pin_count(package, fallback):
    import re
    match = re.search(r'(?:DIP|SOIC|SOP|TSSOP|SSOP|QFP|QFN|SOT)-?\s*(\d+)', package or '', re.I)
    return max(2, int(match.group(1))) if match else fallback


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
    trace_width_mm = float(board_opts.get('trace_width_mm') or board_opts.get('traceWidthMm') or TRACE_WIDTH_MM)
    clearance_mm = float(board_opts.get('clearance_mm') or board_opts.get('clearanceMm') or TRACE_CLEARANCE_MM)
    grid_mm = float(board_opts.get('grid_mm') or board_opts.get('gridMm') or BOARD_GRID_MM)
    thickness_mm = float(board_opts.get('thickness_mm') or board_opts.get('thicknessMm') or BOARD_THICKNESS_MM)
    components = scheme_data.get('components', []) or []
    connections = scheme_data.get('connections', []) or []

    # Bbox исходной схемы в pixels — чтобы потом сдвинуть в (0,0) с margin.
    if not components:
        return {
            'pads': [], 'traces': [], 'comps': [], 'vias': [], 'holes': [],
            'pcb_w_mm': MIN_BOARD_MM, 'pcb_h_mm': MIN_BOARD_MM,
            'thickness_mm': thickness_mm,
            'trace_width_mm': trace_width_mm,
            'clearance_mm': clearance_mm,
            'origin_x_mm': 0, 'origin_y_mm': 0,
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
    pads_by_port = {}     # (comp_id, port_id) → (x_mm, y_mm) — для traces
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
        comps_out.append({
            'id': comp.get('id'), 'type': comp.get('type'),
            'label': label_text,
            'x_mm': cx_mm, 'y_mm': cy_mm,
            'w_mm': w_mm, 'h_mm': h_mm,
            # Готовый rect-bbox для SVG
            'x_left_mm': round(cx_mm - w_mm / 2, 3),
            'y_top_mm':  round(cy_mm - h_mm / 2, 3),
            # Подпись — над компонентом (с отступом 1.2мм от верх. грани).
            'label_x_mm': cx_mm,
            'label_y_mm': round(cy_mm - h_mm / 2 - 1.2, 3),
            'rotation': comp.get('rotation', 0),
            'side': comp.get('side', 'top'),
        })
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
        return (endpoint.get('compId') or endpoint.get('componentId') or endpoint.get('id'),
                endpoint.get('portId') or endpoint.get('pinId') or endpoint.get('port') or endpoint.get('pin') or '')

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
                    vias_out.append({
                        'x_mm': _round3(ax),
                        'y_mm': _round3(ay),
                        'diameter_mm': AUTO_VIA_DIAMETER_MM,
                        'hole_mm': AUTO_VIA_HOLE_MM,
                        'auto': True,
                        'conn_id': conn.get('id'),
                    })

            traces_out.append({
                'from': {'x_mm': ax, 'y_mm': ay},
                'to':   {'x_mm': bx, 'y_mm': by},
                'conn_id': conn.get('id'),
                'layer': seg_layer,
                'width_mm': trace_w,
            })
            prev_layer = seg_layer

        # Vias из импортированной схемы (если есть)
        for via in conn.get('vias') or []:
            x_mm, y_mm = _to_mm(via.get('x', 0), via.get('y', 0))
            vias_out.append({
                'x_mm': x_mm,
                'y_mm': y_mm,
                'diameter_mm': float(via.get('diameter_mm') or via.get('diameterMm') or 1.1),
                'hole_mm': float(via.get('hole_mm') or via.get('holeMm') or 0.45),
            })

    holes_out = []
    hole_inset = min(5.0, pcb_w_mm / 8, pcb_h_mm / 8)
    if pcb_w_mm >= 35 and pcb_h_mm >= 35:
        for x_mm, y_mm in (
            (hole_inset, hole_inset),
            (pcb_w_mm - hole_inset, hole_inset),
            (hole_inset, pcb_h_mm - hole_inset),
            (pcb_w_mm - hole_inset, pcb_h_mm - hole_inset),
        ):
            holes_out.append({'x_mm': round(x_mm, 3), 'y_mm': round(y_mm, 3), 'diameter_mm': 3.2, 'kind': 'mount'})

    return {
        'pads': pads_out, 'traces': traces_out, 'comps': comps_out,
        'vias': vias_out, 'holes': holes_out,
        'pcb_w_mm': pcb_w_mm, 'pcb_h_mm': pcb_h_mm,
        'thickness_mm': thickness_mm,
        'trace_width_mm': trace_width_mm,
        'clearance_mm': clearance_mm,
        'margin_mm': margin_mm,
        'origin_x_mm': 0, 'origin_y_mm': 0,
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
    out.write('%FSLAX25Y25*%\n')         # формат координат: 2 целых, 5 дробных
    out.write('%MOMM*%\n')                # единицы — миллиметры
    out.write('%LPD*%\n')                 # polarity dark (рисуем медь)
    # Apertures
    out.write(f'%ADD10C,{PAD_DIAMETER_MM}*%\n')   # D10 = pad circle
    out.write(f'%ADD11C,{TRACE_WIDTH_MM}*%\n')    # D11 = trace circle
    out.write('G75*\n')                   # multi-quadrant arc (на будущее)
    out.write('G01*\n')                   # linear interpolation

    def _coord(mm):
        # 2.5: умножаем на 1e5, дописываем ведущие нули если нужно.
        return f'{int(round(mm * 1e5)):07d}'

    # Traces: D11 + G01 + от→до
    out.write('D11*\n')
    for tr in layout['traces']:
        f = tr['from']; t = tr['to']
        out.write(f'X{_coord(f["x_mm"])}Y{_coord(f["y_mm"])}D02*\n')  # move
        out.write(f'X{_coord(t["x_mm"])}Y{_coord(t["y_mm"])}D01*\n')  # draw to
    # Pads: D10 + flash (D03)
    out.write('D10*\n')
    for pad in layout['pads']:
        out.write(f'X{_coord(pad["x_mm"])}Y{_coord(pad["y_mm"])}D03*\n')

    out.write('M02*\n')   # End-of-file
    return out.getvalue()


def to_gerber_drill(layout):
    """Excellon drill format (NC drill) — отдельный файл *.DRL для отверстий.
    Минимальная версия: одно сверло, по флешу на каждую pad.
    """
    out = StringIO()
    out.write('M48\n')                   # начало header'а
    out.write('METRIC,LZ\n')             # mm + leading zeros
    out.write('T01C0.80\n')              # tool 1, диаметр 0.8 mm
    out.write('%\n')                     # конец header
    out.write('G90\n')                   # absolute mode
    out.write('M71\n')                   # metric units
    out.write('T01\n')                   # выбираем tool 1
    for pad in layout['pads']:
        # X/Y в мм с точкой; LZ означает «leading zeros», ничего не убираем
        out.write(f'X{pad["x_mm"]:.3f}Y{pad["y_mm"]:.3f}\n')
    for via in layout.get('vias', []):
        out.write(f'X{via["x_mm"]:.3f}Y{via["y_mm"]:.3f}\n')
    for hole in layout.get('holes', []):
        out.write(f'X{hole["x_mm"]:.3f}Y{hole["y_mm"]:.3f}\n')
    out.write('T00\n')                   # деселект tool
    out.write('M30\n')                   # end of program
    return out.getvalue()
