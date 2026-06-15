"""A* PCB Autorouter — Block C1 (master plan 3 weeks).

Берёт computed PCB layout (`pcb_layout.compute_pcb_layout`), строит obstacle grid
по футпринтам компонентов и для каждого net'а запускает A* с штрафом за поворот.
Возвращает обновлённый layout с traces, проложенными вокруг компонентов
вместо текущих HV-elbow путей.

Стратегия (Phase 1 — single-layer MVP):
    1. Grid с шагом 0.5 мм. Компоненты + clearance — obstacles.
    2. Pads — endpoints (входы свободны, иначе нельзя дойти до цели).
    3. A* с 4-связностью + штраф за поворот (Manhattan-friendly).
    4. После трассировки net'а его клетки тоже становятся obstacles (lock-down)
       для следующих net'ов — порядок имеет значение (сначала короткие).
    5. Симплификация: коллинеарные точки удаляются, остаются только углы.

Pitch для защиты:
    «Симуляция → PCB layout → A* autorouter. Один клик — и медные дорожки
     обходят компоненты по сетке, как в EAGLE/KiCad, только проще и быстрее».

Phase 2 (post-defense):
    - Multi-layer (top + bottom) + via placement
    - Rip-up-and-retry для неуспешных net'ов
    - Net priorities (power → signal → GND last)
    - Diagonal moves (8-связность) для коротких трасс
"""

from __future__ import annotations

import heapq
import math

GRID_STEP_MM = 0.5
TURN_PENALTY = 3.0  # штраф за поворот (cells)
COMP_CLEARANCE_MM = 1.0  # отступ от bbox компонента до возможной трассы
TRACE_CLEARANCE_CELLS = 1  # клеток между параллельными трассами
MAX_ASTAR_EXPANSIONS = 250_000  # safety cap: не зависнуть на сложных схемах
# 90° углы манхэттен-пути против правил PCB (§L): срезаем их на 45° (chamfer).
# Только геометрия эмитируемой трассы; A* и lock-down по исходным клеткам.
CHAMFER_MM = 0.8


def _chamfer_corners(points: list[tuple[float, float]], chamfer_mm: float) -> list[tuple[float, float]]:
    """Срезает прямые (90°) углы полилинии на 45°: каждый внутренний угол B → две
    точки на инцидентных сегментах (на расстоянии d от B) + диагональ между ними.
    d ограничено половиной короткого сегмента, чтобы срезы соседних углов не
    пересекались. Точки-срезы лежат на исходных сегментах → не выходят за
    безопасный коридор пути (obstacle-clearance сохраняется)."""
    if len(points) < 3 or chamfer_mm <= 0:
        return points
    out: list[tuple[float, float]] = [points[0]]
    for i in range(1, len(points) - 1):
        ax, ay = points[i - 1]
        bx, by = points[i]
        cx, cy = points[i + 1]
        lab = math.hypot(bx - ax, by - ay)
        lbc = math.hypot(cx - bx, cy - by)
        if lab < 1e-9 or lbc < 1e-9:
            out.append((bx, by))
            continue
        d = min(chamfer_mm, lab / 2.0, lbc / 2.0)
        out.append((bx + (ax - bx) * d / lab, by + (ay - by) * d / lab))
        out.append((bx + (cx - bx) * d / lbc, by + (cy - by) * d / lbc))
    out.append(points[-1])
    return out


def _world_to_cell(x_mm: float, y_mm: float, step: float) -> tuple[int, int]:
    return (int(round(x_mm / step)), int(round(y_mm / step)))


def _cell_to_world(cx: int, cy: int, step: float) -> tuple[float, float]:
    return (round(cx * step, 3), round(cy * step, 3))


def build_obstacle_grid(
    layout: dict,
    step_mm: float = GRID_STEP_MM,
    clearance_mm: float = COMP_CLEARANCE_MM,
) -> tuple[int, int, set[tuple[int, int]]]:
    """(grid_w, grid_h, occupied_set). occupied — клетки, через которые трасса
    не может пройти (футпринты компонентов + clearance). Pad-клетки очищаются
    в маленькой окрестности, чтобы A* мог войти в pad."""
    pcb_w = float(layout.get('pcb_w_mm', 50))
    pcb_h = float(layout.get('pcb_h_mm', 50))
    w_cells = int(round(pcb_w / step_mm)) + 1
    h_cells = int(round(pcb_h / step_mm)) + 1
    occupied: set[tuple[int, int]] = set()

    for comp in layout.get('comps', []) or []:
        x_left = float(comp.get('x_left_mm', 0)) - clearance_mm
        y_top = float(comp.get('y_top_mm', 0)) - clearance_mm
        x_right = float(comp.get('x_left_mm', 0)) + float(comp.get('w_mm', 0)) + clearance_mm
        y_bot = float(comp.get('y_top_mm', 0)) + float(comp.get('h_mm', 0)) + clearance_mm
        cx0, cy0 = _world_to_cell(x_left, y_top, step_mm)
        cx1, cy1 = _world_to_cell(x_right, y_bot, step_mm)
        for cx in range(max(0, cx0), min(w_cells, cx1 + 1)):
            for cy in range(max(0, cy0), min(h_cells, cy1 + 1)):
                occupied.add((cx, cy))

    # Освобождаем клетку pad'а + 1-cell окружение → A* может войти/выйти
    for pad in layout.get('pads', []) or []:
        cx, cy = _world_to_cell(float(pad['x_mm']), float(pad['y_mm']), step_mm)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                occupied.discard((cx + dx, cy + dy))

    return (w_cells, h_cells, occupied)


def astar(
    grid_w: int,
    grid_h: int,
    occupied: set[tuple[int, int]],
    start_cell: tuple[int, int],
    goal_cell: tuple[int, int],
    turn_penalty: float = TURN_PENALTY,
    max_expansions: int = MAX_ASTAR_EXPANSIONS,
) -> list[tuple[int, int]] | None:
    """A* с 4-связностью + штрафом за поворот. State = (cell, last_direction).

    Возвращает список клеток от start до goal включительно, или None если пути нет.
    """
    if start_cell == goal_cell:
        return [start_cell]

    dirs = ((1, 0), (-1, 0), (0, 1), (0, -1))
    open_heap: list[tuple[float, int, tuple[int, int], tuple[int, int] | None]] = []
    heapq.heappush(open_heap, (0.0, 0, start_cell, None))
    g_score: dict[tuple[tuple[int, int], tuple[int, int] | None], float] = {(start_cell, None): 0}
    came_from: dict[
        tuple[tuple[int, int], tuple[int, int] | None], tuple[tuple[int, int], tuple[int, int] | None]
    ] = {}
    expansions = 0

    while open_heap:
        f, g, cell, last_dir = heapq.heappop(open_heap)
        if cell == goal_cell:
            # Reconstruct
            path = [cell]
            state = (cell, last_dir)
            while state in came_from:
                prev = came_from[state]
                path.append(prev[0])
                state = prev
            path.reverse()
            return path
        expansions += 1
        if expansions > max_expansions:
            return None

        for d in dirs:
            nx, ny = cell[0] + d[0], cell[1] + d[1]
            if not (0 <= nx < grid_w and 0 <= ny < grid_h):
                continue
            new_cell = (nx, ny)
            if new_cell != goal_cell and new_cell in occupied:
                continue
            turn = turn_penalty if (last_dir is not None and d != last_dir) else 0.0
            new_g = g + 1.0 + turn
            new_state = (new_cell, d)
            if new_g >= g_score.get(new_state, float('inf')):
                continue
            g_score[new_state] = new_g
            came_from[new_state] = (cell, last_dir)
            h = abs(nx - goal_cell[0]) + abs(ny - goal_cell[1])
            heapq.heappush(open_heap, (new_g + h, new_g, new_cell, d))
    return None


def _simplify_collinear(path: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Оставляет только углы — коллинеарные точки удаляются."""
    if len(path) <= 2:
        return list(path)
    out = [path[0]]
    for i in range(1, len(path) - 1):
        a, b, c = path[i - 1], path[i], path[i + 1]
        d1 = (b[0] - a[0], b[1] - a[1])
        d2 = (c[0] - b[0], c[1] - b[1])
        if d1 != d2:
            out.append(b)
    out.append(path[-1])
    return out


def _endpoint_key(endpoint: dict | None) -> tuple:
    endpoint = endpoint or {}
    return (
        endpoint.get('compId') or endpoint.get('componentId') or endpoint.get('id'),
        endpoint.get('portId') or endpoint.get('pinId') or endpoint.get('port') or endpoint.get('pin') or '',
    )


def _net_length_mm(f_pad: tuple[float, float], t_pad: tuple[float, float]) -> float:
    """Manhattan-длина net'а — для сортировки (короткие первыми)."""
    return abs(f_pad[0] - t_pad[0]) + abs(f_pad[1] - t_pad[1])


MAX_RIPUP_ROUNDS = 4  # сколько раз обходим неразведённые неты, снимая блокеры


def _lockdown_cells(path: list[tuple[int, int]]) -> set[tuple[int, int]]:
    """Клетки трассы + clearance-ореол — становятся obstacles для других net'ов."""
    cells: set[tuple[int, int]] = set()
    for cx, cy in path:
        for dx in range(-TRACE_CLEARANCE_CELLS, TRACE_CLEARANCE_CELLS + 1):
            for dy in range(-TRACE_CLEARANCE_CELLS, TRACE_CLEARANCE_CELLS + 1):
                cells.add((cx + dx, cy + dy))
    return cells


def _route_one(grid_w, grid_h, occupied, f_pad, t_pad, step_mm, turn_penalty):
    """A* для одного net'а на текущем occupied. Освобождает pad-клетки обоих
    концов (их мог накрыть clearance-ореол чужой трассы — иначе нельзя войти)."""
    start = _world_to_cell(f_pad[0], f_pad[1], step_mm)
    goal = _world_to_cell(t_pad[0], t_pad[1], step_mm)
    freed = set()
    for pc in (start, goal):
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                c = (pc[0] + dx, pc[1] + dy)
                if c in occupied:
                    freed.add(c)
    occ_eff = occupied - freed if freed else occupied
    return astar(grid_w, grid_h, occ_eff, start, goal, turn_penalty)


def autoroute_layout(
    layout: dict,
    scheme_connections: list[dict] | None = None,
    *,
    step_mm: float = GRID_STEP_MM,
    clearance_mm: float = COMP_CLEARANCE_MM,
    turn_penalty: float = TURN_PENALTY,
    enable_ripup: bool = True,
    max_ripup_rounds: int = MAX_RIPUP_ROUNDS,
) -> dict:
    """Главный entry-point: layout → layout с переразведёнными traces.

    Жадная трассировка (короткие net'ы первыми) + **rip-up & reroute**: если net
    не разведён, снимаем уже проложенные трассы, которые лежат на его пути, разводим
    его и переразводим снятые. Свап принимается ТОЛЬКО если итоговое число разведённых
    net'ов строго выросло (иначе откат) — это исключает осцилляцию и гарантирует
    завершение за конечное число раундов.

    Args:
        layout: результат `pcb_layout.compute_pcb_layout(scheme_data)`.
        scheme_connections: оригинальные connections со scheme_data (пары from/to).
        enable_ripup: включить rip-up&reroute фазу после жадной трассировки.

    Returns:
        Новый dict с `traces` и `autoroute_stats` (routed/failed/unreachable/
        avg_length_mm/ripup_rounds/ripup_recovered/…).
    """
    grid_w, grid_h, base_occupied = build_obstacle_grid(layout, step_mm, clearance_mm)
    pads_by_key = {
        (p.get('comp_id'), p.get('port_id')): (float(p['x_mm']), float(p['y_mm']))
        for p in layout.get('pads', []) or []
    }
    trace_width = float(layout.get('trace_width_mm', 0.5))

    # Собираем net'ы + сортируем короткие первыми (greedy strategy)
    pending: list[tuple[float, dict, tuple[float, float], tuple[float, float]]] = []
    for conn in scheme_connections or []:
        f_pad = pads_by_key.get(_endpoint_key(conn.get('from')))
        t_pad = pads_by_key.get(_endpoint_key(conn.get('to')))
        if not f_pad or not t_pad:
            continue
        pending.append((_net_length_mm(f_pad, t_pad), conn, f_pad, t_pad))
    pending.sort(key=lambda x: x[0])

    # Состояние: разведённые net'ы (conn_id → клетки/путь/мета) + список неудач.
    net_cells: dict[str, set[tuple[int, int]]] = {}
    net_path: dict[str, list[tuple[int, int]]] = {}
    meta: dict[str, tuple] = {}
    failed: list[str] = []

    def _occupied(exclude: set[str] | None = None) -> set[tuple[int, int]]:
        occ = set(base_occupied)
        for nid, cells in net_cells.items():
            if exclude and nid in exclude:
                continue
            occ |= cells
        return occ

    def _try_route(cid: str) -> bool:
        conn, f_pad, t_pad = meta[cid]
        path = _route_one(grid_w, grid_h, _occupied(), f_pad, t_pad, step_mm, turn_penalty)
        if path is None:
            return False
        net_cells[cid] = _lockdown_cells(path)
        net_path[cid] = path
        return True

    # Жадная фаза
    for index, (_length, conn, f_pad, t_pad) in enumerate(pending):
        cid = str(conn.get('id') or f'net{index}')
        meta[cid] = (conn, f_pad, t_pad)
        if not _try_route(cid):
            failed.append(cid)

    # Rip-up & reroute фаза
    ripup_rounds = 0
    ripup_recovered = 0
    if enable_ripup and failed:
        for _round in range(max_ripup_rounds):
            if not failed:
                break
            ripup_rounds += 1
            progress = False
            for cid in list(failed):
                conn, f_pad, t_pad = meta[cid]
                # Путь по «голой» плате (только компоненты): если и так нет — мешают
                # не трассы, а корпуса; rip-up бесполезен.
                bare = _route_one(grid_w, grid_h, set(base_occupied), f_pad, t_pad, step_mm, turn_penalty)
                if bare is None:
                    continue
                conflict_cells = _lockdown_cells(bare)
                conflicts = [nid for nid, cells in net_cells.items() if cells & conflict_cells]
                if not conflicts:
                    # Свободно и без снятия — просто разводим (соседи могли освободить).
                    if _try_route(cid):
                        failed.remove(cid)
                        ripup_recovered += 1
                        progress = True
                    continue
                # Снимок для отката, если свап не улучшит итог.
                snap_cells = {k: set(v) for k, v in net_cells.items()}
                snap_path = dict(net_path)
                snap_failed = list(failed)
                before = len(net_cells)
                for nid in conflicts:
                    net_cells.pop(nid, None)
                    net_path.pop(nid, None)
                routed_cid = _try_route(cid)
                if routed_cid:
                    failed.remove(cid)
                for nid in conflicts:  # переразводим снятые
                    if not _try_route(nid) and nid not in failed:
                        failed.append(nid)
                if len(net_cells) > before:  # строго больше разведено — принимаем
                    ripup_recovered += len(net_cells) - before
                    progress = True
                else:  # не улучшили — полный откат
                    net_cells.clear()
                    net_cells.update(snap_cells)
                    net_path.clear()
                    net_path.update(snap_path)
                    failed[:] = snap_failed
            if not progress:
                break

    # Эмит трасс из финальных путей
    new_traces: list[dict] = []
    routed_lengths_mm: list[float] = []
    for cid, path in net_path.items():
        conn = meta[cid][0]
        simplified = _simplify_collinear(path)
        # Полилиния в мире → срезаем прямые углы на 45° (chamfer). A* по клеткам;
        # chamfer только украшает выход.
        world_pts = _chamfer_corners([_cell_to_world(cx, cy, step_mm) for cx, cy in simplified], CHAMFER_MM)
        for i in range(1, len(world_pts)):
            ax, ay = world_pts[i - 1]
            bx, by = world_pts[i]
            new_traces.append(
                {
                    'from': {'x_mm': ax, 'y_mm': ay},
                    'to': {'x_mm': bx, 'y_mm': by},
                    'conn_id': conn.get('id'),
                    'layer': 'top',
                    'width_mm': float(conn.get('width_mm') or conn.get('widthMm') or trace_width),
                    'astar': True,
                }
            )
        length_mm = 0.0
        for i in range(1, len(simplified)):
            ax, ay = simplified[i - 1]
            bx, by = simplified[i]
            length_mm += (abs(ax - bx) + abs(ay - by)) * step_mm
        routed_lengths_mm.append(length_mm)

    out_layout = dict(layout)
    out_layout['traces'] = new_traces
    out_layout['vias'] = []  # Phase 1 — single layer, без vias
    out_layout['autoroute_stats'] = {
        'routed': len(net_path),
        'failed': len(failed),
        'unreachable': failed,
        'avg_length_mm': round(sum(routed_lengths_mm) / len(routed_lengths_mm), 2)
        if routed_lengths_mm
        else 0,
        'total_length_mm': round(sum(routed_lengths_mm), 2),
        'cells_per_mm': round(1.0 / step_mm, 2),
        'grid_w': grid_w,
        'grid_h': grid_h,
        'algorithm': 'A* (Manhattan + turn penalty, 45° chamfered) + rip-up&reroute'
        if enable_ripup
        else 'A* (Manhattan + turn penalty, 45° chamfered)',
        'turn_penalty': turn_penalty,
        'ripup_rounds': ripup_rounds,
        'ripup_recovered': ripup_recovered,
    }
    return out_layout
