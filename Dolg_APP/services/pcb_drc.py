"""DRC PCB-слоя (медь) — правила IPC-2221 поверх computed layout.

Дополняет схемный DRC (`schematic_validation`/`project_review`) проверками уже
*разведённой платы*: ширина трассы под ток, зазоры между нетами, технологический
минимум, отступ от края. Работает чисто по геометрии `layout` (pads/traces/comps/
pcb_w_mm/pcb_h_mm) из `pcb_layout.compute_pcb_layout` или автотрассировщика —
поэтому тестируется headless, без браузера.

Expert-first: каждый finding = {rule_id, severity, message, recommendation} —
тот же контракт, что у схемного review (нейронка не выносит вердикт, выносят правила).

Источник порогов: IPC-2221 (current capacity, conductor spacing), типовые
fab-ограничения (JLCPCB/PCBWay ≈0.127–0.15 мм min trace/space).
"""

from __future__ import annotations

import math

# Технологический минимум (большинство дешёвых фабрик: 6 mil ≈ 0.152 мм).
MIN_FAB_TRACE_MM = 0.15
MIN_FAB_CLEARANCE_MM = 0.15
# Отступ меди от края платы (IPC: ≥0.5 мм типично для фрезеровки).
EDGE_CLEARANCE_MM = 0.5
# IPC-2221 коэффициенты для current capacity.
IPC2221_K_EXTERNAL = 0.048  # внешние слои
IPC2221_K_INTERNAL = 0.024  # внутренние слои
IPC2221_B = 0.44  # показатель при ΔT
IPC2221_C = 0.725  # показатель при площади
MILS_PER_MM = 39.3701
COPPER_OZ_THICKNESS_MILS = 1.378  # толщина 1 oz/ft² меди в mil


def ipc2221_min_trace_width_mm(
    current_a: float,
    *,
    temp_rise_c: float = 10.0,
    copper_oz: float = 1.0,
    external: bool = True,
) -> float:
    """Минимальная ширина дорожки (мм) для тока по IPC-2221.

    I = k·ΔT^0.44·A^0.725  (A — площадь сечения в mil²) → инвертируем в ширину при
    заданной толщине меди. Для внешних слоёв k=0.048, внутренних 0.024.
    """
    if current_a <= 0:
        return 0.0
    k = IPC2221_K_EXTERNAL if external else IPC2221_K_INTERNAL
    temp_rise_c = max(temp_rise_c, 1.0)
    area_mils2 = (current_a / (k * temp_rise_c**IPC2221_B)) ** (1.0 / IPC2221_C)
    thickness_mils = max(copper_oz, 0.1) * COPPER_OZ_THICKNESS_MILS
    width_mils = area_mils2 / thickness_mils
    return width_mils / MILS_PER_MM


def _seg_points(trace: dict) -> tuple[float, float, float, float] | None:
    f = trace.get('from') or {}
    t = trace.get('to') or {}
    try:
        return (float(f['x_mm']), float(f['y_mm']), float(t['x_mm']), float(t['y_mm']))
    except KeyError, TypeError, ValueError:
        return None


def _seg_distance(a: tuple, b: tuple) -> float:
    """Минимальное расстояние между двумя отрезками в 2D (мм)."""

    def dot(ux, uy, vx, vy):
        return ux * vx + uy * vy

    ax, ay, bx, by = a
    cx, cy, dx, dy = b
    ux, uy = bx - ax, by - ay
    vx, vy = dx - cx, dy - cy
    wx, wy = ax - cx, ay - cy
    aa = dot(ux, uy, ux, uy)
    bb = dot(ux, uy, vx, vy)
    cc = dot(vx, vy, vx, vy)
    dd = dot(ux, uy, wx, wy)
    ee = dot(vx, vy, wx, wy)
    denom = aa * cc - bb * bb
    sc = sd = denom
    tc = td = denom
    if denom < 1e-12:  # отрезки почти параллельны
        sd = 1.0
        tc, td = ee, cc
    else:
        sc = bb * ee - cc * dd
        tc = aa * ee - bb * dd
        if sc < 0:
            sc, tc, td = 0.0, ee, cc
        elif sc > sd:
            sc, tc, td = sd, ee + bb, cc
    if tc < 0:
        tc = 0.0
        sc = 0.0 if -dd < 0 else (sd if -dd > aa else -dd)
        sd = 1.0 if aa < 1e-12 else aa
    elif tc > td:
        tc = td
        sc = 0.0 if (-dd + bb) < 0 else (sd if (-dd + bb) > aa else (-dd + bb))
        sd = 1.0 if aa < 1e-12 else aa
    s = 0.0 if abs(sd) < 1e-12 else sc / sd
    t = 0.0 if abs(td) < 1e-12 else tc / td
    dpx = wx + s * ux - t * vx
    dpy = wy + s * uy - t * vy
    return math.hypot(dpx, dpy)


def _finding(rule_id, severity, message, recommendation, where=None):
    return {
        'rule_id': rule_id,
        'severity': severity,  # error | warning | info
        'message': message,
        'recommendation': recommendation,
        'where': where or {},
    }


def run_pcb_drc(
    layout: dict,
    *,
    nets_current: dict | None = None,
    temp_rise_c: float = 10.0,
    copper_oz: float = 1.0,
) -> dict:
    """Проверка разведённой платы по правилам IPC-2221 / fab-минимумам.

    Args:
        layout: computed layout (traces[], pads[], pcb_w_mm/pcb_h_mm, trace_width_mm,
            clearance_mm). Трасса: {from:{x_mm,y_mm}, to:{x_mm,y_mm}, conn_id, width_mm}.
        nets_current: {conn_id: ток_А} — для проверки ширины под ток (если известны).

    Returns: {'findings': [...], 'summary': {errors, warnings, checked_traces, ...}}.
    """
    traces = [t for t in (layout.get('traces') or []) if _seg_points(t)]
    clearance_req = float(layout.get('clearance_mm') or MIN_FAB_CLEARANCE_MM)
    clearance_req = max(clearance_req, MIN_FAB_CLEARANCE_MM)
    pcb_w = float(layout.get('pcb_w_mm') or 0)
    pcb_h = float(layout.get('pcb_h_mm') or 0)
    nets_current = nets_current or {}

    findings: list[dict] = []

    # 1. Технологический минимум ширины + ток (IPC-2221).
    thin_seen: set = set()
    underrated_seen: set = set()
    for tr in traces:
        cid = str(tr.get('conn_id') or '')
        width = float(tr.get('width_mm') or layout.get('trace_width_mm') or 0)
        if width > 0 and width < MIN_FAB_TRACE_MM and cid not in thin_seen:
            thin_seen.add(cid)
            findings.append(
                _finding(
                    'pcb.trace_width_below_fab_min',
                    'error',
                    f'Ширина трассы {width:.3g} мм ниже технологического минимума '
                    f'{MIN_FAB_TRACE_MM} мм (net {cid or "?"}).',
                    f'Увеличьте ширину до ≥{MIN_FAB_TRACE_MM} мм или уточните возможности фабрики.',
                    where={'conn_id': cid, 'width_mm': width},
                )
            )
        current = nets_current.get(cid) or nets_current.get(tr.get('conn_id'))
        if current and cid not in underrated_seen:
            req = ipc2221_min_trace_width_mm(float(current), temp_rise_c=temp_rise_c, copper_oz=copper_oz)
            if width > 0 and width < req:
                underrated_seen.add(cid)
                findings.append(
                    _finding(
                        'pcb.trace_underrated_for_current',
                        'error',
                        f'Трасса net {cid} шириной {width:.3g} мм не держит {float(current):.3g} А: '
                        f'по IPC-2221 нужно ≥{req:.3g} мм (ΔT={temp_rise_c:.0f}°C, {copper_oz:g}oz).',
                        f'Расширьте дорожку до ≥{req:.2g} мм, добавьте медь (oz) или снизьте ток.',
                        where={'conn_id': cid, 'width_mm': width, 'required_mm': round(req, 4)},
                    )
                )

    # 2. Зазор между трассами РАЗНЫХ нетов.
    pair_seen: set = set()
    for i in range(len(traces)):
        seg_i = _seg_points(traces[i])
        ci = str(traces[i].get('conn_id') or f'_{i}')
        li = traces[i].get('layer', 'top')
        for j in range(i + 1, len(traces)):
            cj = str(traces[j].get('conn_id') or f'_{j}')
            if ci == cj:
                continue  # одна цепь — касание разрешено
            if traces[j].get('layer', 'top') != li:
                continue  # разные слои меди не конфликтуют
            key = tuple(sorted((ci, cj)))
            if key in pair_seen:
                continue
            dist = _seg_distance(seg_i, _seg_points(traces[j]))
            if dist < clearance_req - 1e-6:
                pair_seen.add(key)
                findings.append(
                    _finding(
                        'pcb.trace_clearance_violation',
                        'error',
                        f'Зазор между net {ci} и net {cj} = {dist:.3g} мм, меньше требуемого '
                        f'{clearance_req:.3g} мм (слой {li}).',
                        'Раздвиньте трассы, сузьте дорожки или переразведите этот участок.',
                        where={'nets': list(key), 'distance_mm': round(dist, 4), 'layer': li},
                    )
                )

    # 3. Отступ меди от края платы.
    if pcb_w > 0 and pcb_h > 0:
        edge_seen = False
        for tr in traces:
            ax, ay, bx, by = _seg_points(tr)
            min_edge = min(ax, bx, ay, by, pcb_w - max(ax, bx), pcb_h - max(ay, by))
            if min_edge < EDGE_CLEARANCE_MM - 1e-6 and not edge_seen:
                edge_seen = True
                findings.append(
                    _finding(
                        'pcb.trace_near_board_edge',
                        'warning',
                        f'Медь подходит к краю платы ближе {EDGE_CLEARANCE_MM} мм (≈{max(min_edge, 0):.3g} мм).',
                        f'Отодвиньте трассы от края на ≥{EDGE_CLEARANCE_MM} мм (запас под фрезеровку).',
                        where={'min_edge_mm': round(max(min_edge, 0), 4)},
                    )
                )

    errors = sum(1 for f in findings if f['severity'] == 'error')
    warnings = sum(1 for f in findings if f['severity'] == 'warning')
    return {
        'findings': findings,
        'summary': {
            'errors': errors,
            'warnings': warnings,
            'checked_traces': len(traces),
            'clearance_req_mm': clearance_req,
            'verdict': 'fail' if errors else ('warning' if warnings else 'pass'),
        },
    }
