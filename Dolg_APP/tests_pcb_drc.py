"""Tests for PCB-layer DRC (IPC-2221) — Dolg_APP/services/pcb_drc.py."""

from __future__ import annotations

from Dolg_APP.services.pcb_drc import ipc2221_min_trace_width_mm, run_pcb_drc


def _trace(x1, y1, x2, y2, conn_id, width_mm=0.5, layer='top'):
    return {
        'from': {'x_mm': x1, 'y_mm': y1},
        'to': {'x_mm': x2, 'y_mm': y2},
        'conn_id': conn_id,
        'width_mm': width_mm,
        'layer': layer,
    }


def _layout(traces, *, w=50.0, h=50.0, clearance_mm=0.2):
    return {
        'pcb_w_mm': w,
        'pcb_h_mm': h,
        'trace_width_mm': 0.5,
        'clearance_mm': clearance_mm,
        'traces': traces,
    }


def test_ipc2221_one_amp_external_matches_table():
    # 1 А, ΔT=10°C, 1oz, внешний слой → ~0.3 мм (известное табличное значение IPC-2221).
    w = ipc2221_min_trace_width_mm(1.0, temp_rise_c=10.0, copper_oz=1.0, external=True)
    assert 0.25 < w < 0.35, w
    # больше тока → шире
    assert ipc2221_min_trace_width_mm(3.0) > ipc2221_min_trace_width_mm(1.0)
    assert ipc2221_min_trace_width_mm(0.0) == 0.0


def test_clean_board_passes():
    traces = [
        _trace(5, 5, 20, 5, 'n1'),
        _trace(5, 10, 20, 10, 'n2'),  # 5 мм от n1 — с запасом
    ]
    report = run_pcb_drc(_layout(traces))
    assert report['summary']['verdict'] == 'pass'
    assert report['summary']['errors'] == 0


def test_clearance_violation_between_nets():
    traces = [
        _trace(5, 5, 20, 5, 'n1'),
        _trace(5, 5.1, 20, 5.1, 'n2'),  # 0.1 мм < clearance 0.2
    ]
    report = run_pcb_drc(_layout(traces, clearance_mm=0.2))
    ids = {f['rule_id'] for f in report['findings']}
    assert 'pcb.trace_clearance_violation' in ids
    assert report['summary']['verdict'] == 'fail'


def test_same_net_touching_not_flagged():
    # Два сегмента ОДНОЙ цепи рядом — это нормально (касание разрешено).
    traces = [
        _trace(5, 5, 20, 5, 'n1'),
        _trace(5, 5.05, 20, 5.05, 'n1'),
    ]
    report = run_pcb_drc(_layout(traces))
    ids = {f['rule_id'] for f in report['findings']}
    assert 'pcb.trace_clearance_violation' not in ids


def test_different_layers_do_not_conflict():
    traces = [
        _trace(5, 5, 20, 5, 'n1', layer='top'),
        _trace(5, 5.05, 20, 5.05, 'n2', layer='bottom'),
    ]
    report = run_pcb_drc(_layout(traces))
    ids = {f['rule_id'] for f in report['findings']}
    assert 'pcb.trace_clearance_violation' not in ids


def test_trace_below_fab_min_width():
    traces = [_trace(5, 5, 20, 5, 'n1', width_mm=0.1)]  # 0.1 < 0.15
    report = run_pcb_drc(_layout(traces))
    ids = {f['rule_id'] for f in report['findings']}
    assert 'pcb.trace_width_below_fab_min' in ids


def test_trace_underrated_for_current():
    # Узкая 0.2 мм трасса под 3 А → IPC требует заметно больше → ошибка.
    traces = [_trace(5, 5, 40, 5, 'power', width_mm=0.2)]
    report = run_pcb_drc(_layout(traces), nets_current={'power': 3.0})
    findings = {f['rule_id']: f for f in report['findings']}
    assert 'pcb.trace_underrated_for_current' in findings
    assert findings['pcb.trace_underrated_for_current']['where']['required_mm'] > 0.2


def test_adequate_width_for_current_passes():
    # 1 мм трасса под 1 А — с запасом (нужно ~0.3 мм) → нет underrated-ошибки.
    traces = [_trace(5, 5, 40, 5, 'power', width_mm=1.0)]
    report = run_pcb_drc(_layout(traces), nets_current={'power': 1.0})
    ids = {f['rule_id'] for f in report['findings']}
    assert 'pcb.trace_underrated_for_current' not in ids


def test_trace_near_board_edge_warns():
    traces = [_trace(0.1, 0.1, 20, 0.1, 'n1')]  # 0.1 мм от края < 0.5
    report = run_pcb_drc(_layout(traces))
    ids = {f['rule_id'] for f in report['findings']}
    assert 'pcb.trace_near_board_edge' in ids


def test_empty_layout_passes():
    report = run_pcb_drc(_layout([]))
    assert report['summary']['verdict'] == 'pass'
    assert report['summary']['checked_traces'] == 0
