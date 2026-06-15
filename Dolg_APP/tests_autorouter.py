"""Tests for Block C1: A* PCB autorouter."""

from __future__ import annotations

import pytest

from Dolg_APP.services.autorouter import (
    _chamfer_corners,
    astar,
    autoroute_layout,
    build_obstacle_grid,
)


def _layout_two_pads_with_obstacle():
    """50×50мм плата, 2 пада слева/справа, препятствие посередине."""
    return {
        'pcb_w_mm': 50.0,
        'pcb_h_mm': 50.0,
        'trace_width_mm': 0.5,
        'pads': [
            {'comp_id': 'A', 'port_id': '1', 'x_mm': 5.0, 'y_mm': 25.0},
            {'comp_id': 'B', 'port_id': '1', 'x_mm': 45.0, 'y_mm': 25.0},
        ],
        'comps': [
            {'id': 'OBST', 'x_left_mm': 20.0, 'y_top_mm': 22.0, 'w_mm': 10.0, 'h_mm': 6.0},
        ],
    }


def test_routes_around_obstacle_when_possible():
    """A* должен обогнуть препятствие и не идти прямо через него."""
    layout = _layout_two_pads_with_obstacle()
    connections = [
        {
            'id': 'net1',
            'from': {'compId': 'A', 'portId': '1'},
            'to': {'compId': 'B', 'portId': '1'},
        }
    ]
    out = autoroute_layout(layout, connections)
    assert out['autoroute_stats']['routed'] == 1
    assert out['autoroute_stats']['failed'] == 0
    # Если бы шли прямой Manhattan = 40мм, а с обходом >= 40+2*4 (обход
    # препятствия высотой 6мм + clearance 1мм с каждой стороны ≥ 8мм).
    assert out['autoroute_stats']['total_length_mm'] >= 44

    # И ни один сегмент не должен пересекать тело препятствия (20..30, 22..28)
    for tr in out['traces']:
        for end in ('from', 'to'):
            x = tr[end]['x_mm']
            y = tr[end]['y_mm']
            # Точка строго внутри bbox (без clearance) — не должно быть
            assert not (20.1 < x < 29.9 and 22.1 < y < 27.9), (
                f'Trace endpoint {x},{y} crossed obstacle interior'
            )


def test_chamfer_cuts_right_angle_to_45():
    # L-полилиния: вверх до (0,10), затем вправо — 90° угол в (0,10).
    out = _chamfer_corners([(0.0, 0.0), (0.0, 10.0), (10.0, 10.0)], 2.0)
    assert (0.0, 10.0) not in out  # острый угол срезан
    assert (0.0, 8.0) in out and (2.0, 10.0) in out  # две точки-среза
    # диагональ между ними — 45° (|dx| == |dy|)
    i = out.index((0.0, 8.0))
    ax, ay = out[i]
    bx, by = out[i + 1]
    assert abs(bx - ax) == pytest.approx(abs(by - ay))


def test_chamfer_noop_for_short_polyline():
    assert _chamfer_corners([(0.0, 0.0), (1.0, 1.0)], 2.0) == [(0.0, 0.0), (1.0, 1.0)]


def test_traces_have_45deg_chamfer():
    layout = _layout_two_pads_with_obstacle()
    connections = [{'id': 'n', 'from': {'compId': 'A', 'portId': '1'}, 'to': {'compId': 'B', 'portId': '1'}}]
    out = autoroute_layout(layout, connections)
    assert '45' in out['autoroute_stats']['algorithm']
    diagonal = any(
        abs(tr['from']['x_mm'] - tr['to']['x_mm']) > 1e-6
        and abs(tr['from']['y_mm'] - tr['to']['y_mm']) > 1e-6
        for tr in out['traces']
    )
    assert diagonal, 'ожидался хотя бы один диагональный (45°) сегмент после chamfer'


def test_no_connections_yields_empty_traces():
    layout = _layout_two_pads_with_obstacle()
    out = autoroute_layout(layout, [])
    assert out['traces'] == []
    assert out['autoroute_stats']['routed'] == 0


def test_unreachable_pad_marked_failed():
    """Если pad окружён препятствиями со всех сторон — failed += 1, не падаем."""
    layout = {
        'pcb_w_mm': 20.0,
        'pcb_h_mm': 20.0,
        'trace_width_mm': 0.5,
        'pads': [
            {'comp_id': 'A', 'port_id': '1', 'x_mm': 10.0, 'y_mm': 10.0},
            {'comp_id': 'B', 'port_id': '1', 'x_mm': 17.0, 'y_mm': 17.0},
        ],
        # Кольцо препятствий вокруг pad A
        'comps': [
            {'id': 'W1', 'x_left_mm': 7.0, 'y_top_mm': 6.5, 'w_mm': 6.0, 'h_mm': 1.0},
            {'id': 'W2', 'x_left_mm': 7.0, 'y_top_mm': 13.0, 'w_mm': 6.0, 'h_mm': 1.0},
            {'id': 'W3', 'x_left_mm': 6.5, 'y_top_mm': 7.0, 'w_mm': 1.0, 'h_mm': 6.0},
            {'id': 'W4', 'x_left_mm': 13.0, 'y_top_mm': 7.0, 'w_mm': 1.0, 'h_mm': 6.0},
        ],
    }
    connections = [
        {'id': 'blocked', 'from': {'compId': 'A', 'portId': '1'}, 'to': {'compId': 'B', 'portId': '1'}}
    ]
    out = autoroute_layout(layout, connections)
    stats = out['autoroute_stats']
    assert stats['routed'] == 0
    assert stats['failed'] == 1
    assert 'blocked' in stats['unreachable']


def test_short_nets_routed_before_long_ones():
    """Greedy ordering: короткие net'ы должны проходить первыми → их пути не
    блокируются длинными.  Проверяем что оба net'а разведены."""
    layout = {
        'pcb_w_mm': 60.0,
        'pcb_h_mm': 60.0,
        'trace_width_mm': 0.5,
        'pads': [
            {'comp_id': 'A', 'port_id': '1', 'x_mm': 5.0, 'y_mm': 10.0},
            {'comp_id': 'A', 'port_id': '2', 'x_mm': 8.0, 'y_mm': 10.0},
            {'comp_id': 'B', 'port_id': '1', 'x_mm': 55.0, 'y_mm': 50.0},
            {'comp_id': 'C', 'port_id': '1', 'x_mm': 55.0, 'y_mm': 10.0},
        ],
        'comps': [],
    }
    connections = [
        {'id': 'long', 'from': {'compId': 'A', 'portId': '1'}, 'to': {'compId': 'B', 'portId': '1'}},
        {'id': 'short', 'from': {'compId': 'A', 'portId': '2'}, 'to': {'compId': 'C', 'portId': '1'}},
    ]
    out = autoroute_layout(layout, connections)
    assert out['autoroute_stats']['routed'] == 2
    assert out['autoroute_stats']['failed'] == 0


def test_grid_dimensions_match_board_size():
    layout = _layout_two_pads_with_obstacle()
    grid_w, grid_h, occ = build_obstacle_grid(layout, step_mm=0.5)
    # 50мм / 0.5мм + 1 = 101 cells
    assert grid_w == 101
    assert grid_h == 101
    # Препятствие 10×6мм + clearance 1мм с каждой стороны = 12×8мм
    # → (12/0.5+1) × (8/0.5+1) = 25×17 = 425 клеток как нижняя оценка
    # (минус снятые с pad-окружения, но pads далеко — снятий тут нет)
    assert len(occ) >= 400


def test_astar_returns_none_for_blocked_path():
    """A* возвращает None если путь физически невозможен (полный barrier)."""
    grid_w, grid_h = 10, 10
    occupied = {(5, y) for y in range(grid_h)}  # вертикальный барьер по всему gird
    occupied.add((5, 5))  # подтверждаем что goal-neighbor тоже занят
    # start слева, goal справа — обойти нельзя
    path = astar(grid_w, grid_h, occupied, (1, 5), (8, 5))
    assert path is None


def test_astar_finds_optimal_short_path():
    """Без препятствий A* находит Manhattan-минимальный путь."""
    grid_w, grid_h = 20, 20
    path = astar(grid_w, grid_h, set(), (0, 0), (5, 3))
    assert path is not None
    assert path[0] == (0, 0)
    assert path[-1] == (5, 3)
    # Длина = 5 + 3 + 1 (включая start) = 9 клеток
    assert len(path) == 9


def test_turn_penalty_prefers_straight_paths():
    """A* с штрафом должен предпочитать прямой путь L-образному равной Manhattan-длины."""
    grid_w, grid_h = 20, 20
    # Прямой путь по X: (0,0) → (5,0). Без turn penalty heuristic тривиальная.
    path = astar(grid_w, grid_h, set(), (0, 0), (5, 0), turn_penalty=5.0)
    assert path is not None
    # Все Y == 0 (прямой по горизонтали)
    assert all(p[1] == 0 for p in path)


@pytest.mark.parametrize('step_mm', [0.25, 0.5, 1.0])
def test_step_size_affects_grid_resolution(step_mm):
    """Меньший step → больше клеток. Тривиальная проверка масштабирования."""
    layout = {'pcb_w_mm': 20, 'pcb_h_mm': 20, 'pads': [], 'comps': []}
    grid_w, grid_h, occ = build_obstacle_grid(layout, step_mm=step_mm)
    expected = int(round(20 / step_mm)) + 1
    assert grid_w == expected
    assert grid_h == expected
