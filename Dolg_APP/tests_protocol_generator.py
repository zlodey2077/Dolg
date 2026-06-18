"""Tests for the engineering/lab protocol generator."""

from __future__ import annotations

from Dolg_APP.services.protocol_generator import build_protocol


def _divider(v=9.0, r1=1000, r2=2000):
    return {
        'components': [
            {'id': 'B1', 'type': 'battery', 'voltage': v, 'label': 'B1', 'ports': [{'id': '+'}, {'id': '-'}]},
            {
                'id': 'R1',
                'type': 'resistor',
                'resistance': r1,
                'label': 'R1',
                'ports': [{'id': '1'}, {'id': '2'}],
            },
            {
                'id': 'R2',
                'type': 'resistor',
                'resistance': r2,
                'label': 'R2',
                'ports': [{'id': '1'}, {'id': '2'}],
            },
            {'id': 'G1', 'type': 'ground', 'label': 'GND', 'ports': [{'id': '1'}]},
        ],
        'connections': [
            {'from': {'compId': 'B1', 'portId': '+'}, 'to': {'compId': 'R1', 'portId': '1'}},
            {'from': {'compId': 'R1', 'portId': '2'}, 'to': {'compId': 'R2', 'portId': '1'}},
            {'from': {'compId': 'R2', 'portId': '2'}, 'to': {'compId': 'B1', 'portId': '-'}},
            {'from': {'compId': 'B1', 'portId': '-'}, 'to': {'compId': 'G1', 'portId': '1'}},
        ],
    }


def test_empty_protocol_has_title_and_no_sections():
    p = build_protocol('Пустой протокол')
    assert p['markdown'].startswith('# Пустой протокол')
    assert p['sections'] == []
    assert 'Сформировано' in p['markdown']


def test_scheme_section_and_bom():
    p = build_protocol('Делитель', _divider())
    assert 'Состав схемы' in p['sections']
    md = p['markdown']
    assert '| Обозначение | Тип | Номинал |' in md
    assert 'R1' in md and 'resistor' in md and '1000' in md


def test_bom_readiness_section_renders_catalog_metadata():
    scheme = _divider()
    scheme['components'][1].update(
        {
            'catalog_ref': 'RC0603FR-071KL',
            'footprint': 'R_0603',
            'datasheet_url': 'https://example.test/r0603.pdf',
            'spice_model': 'R0603_RES',
        }
    )
    p = build_protocol('BOM protocol', scheme, include_dc=False)

    assert any('BOM' in section for section in p['sections'])
    assert 'RC0603FR-071KL' in p['markdown']
    assert 'R_0603' in p['markdown']
    assert 'R0603_RES' in p['markdown']


def test_pcb_drc_section_renders_width_issue():
    scheme = {
        'board': {
            'fabrication_profile': 'jlcpcb_standard_2layer',
            'clearance_mm': 0.3,
            'min_trace_width_mm': 0.15,
        },
        'components': [
            {
                'id': 'r1',
                'type': 'resistor',
                'label': 'R1',
                'x': 80,
                'y': 100,
                'ports': [{'id': 'a', 'x': -20, 'y': 0}, {'id': 'b', 'x': 20, 'y': 0}],
            },
            {
                'id': 'led1',
                'type': 'led',
                'label': 'LED1',
                'x': 240,
                'y': 100,
                'ports': [{'id': 'a', 'x': -20, 'y': 0}, {'id': 'k', 'x': 20, 'y': 0}],
            },
        ],
        'connections': [
            {
                'from': {'compId': 'r1', 'portId': 'b'},
                'to': {'compId': 'led1', 'portId': 'a'},
                'width_mm': 0.2,
                'current_a': 2.0,
            }
        ],
    }
    p = build_protocol('PCB protocol', scheme, include_dc=False)

    assert 'PCB DRC' in p['sections']
    assert 'JLCPCB standard 2-layer' in p['markdown']
    assert 'trace_width_current' in p['markdown']
    assert 'errors=1' in p['markdown']


def test_sources_section_renders_finding_references():
    p = build_protocol(
        'Sources protocol',
        findings=[
            {
                'rule_id': 'ipc.clearance',
                'severity': 'warning',
                'message': 'clearance risk',
                'source_references': [{'title': 'IPC-2221', 'url': 'https://example.test/ipc-2221'}],
            }
        ],
    )

    assert any('Источники' in section for section in p['sections'])
    assert 'IPC-2221' in p['markdown']
    assert 'https://example.test/ipc-2221' in p['markdown']


def test_dc_section_computed_from_scheme():
    p = build_protocol('Делитель', _divider())
    assert any('DC' in s for s in p['sections'])
    # средний узел делителя ≈ 6 В присутствует в тексте
    assert '6' in p['markdown']


def test_dc_can_be_disabled():
    p = build_protocol('Делитель', _divider(), include_dc=False)
    assert not any('DC' in s for s in p['sections'])


def test_lab_calcs_section_renders_outputs_and_status():
    lab = {
        'ok': True,
        'kind': 'derating',
        'title': 'Запас по нагрузке (derating)',
        'status': 'risk',
        'status_label': 'риск',
        'feedback': 'Загрузка 72% выше предела 50%.',
        'outputs': {
            'load_percent': {'label': 'Загрузка', 'value': 72.0, 'unit': '%', 'display': '72'},
        },
    }
    p = build_protocol('Отчёт', lab_calcs=[lab])
    assert 'Инженерные расчёты' in p['sections']
    md = p['markdown']
    assert 'Запас по нагрузке' in md and 'риск' in md and 'Загрузка' in md


def test_findings_sorted_and_show_recommendation():
    findings = [
        {'rule_id': 'pcb.x', 'severity': 'warning', 'message': 'предупреждение W', 'recommendation': 'fix W'},
        {'rule_id': 'pcb.y', 'severity': 'error', 'message': 'ошибка E', 'recommendation': 'fix E'},
    ]
    p = build_protocol('Отчёт', findings=findings)
    md = p['markdown']
    assert 'Проверки' in ' '.join(p['sections'])
    # ошибка (error) идёт раньше предупреждения (warning)
    assert md.index('ошибка E') < md.index('предупреждение W')
    assert 'fix E' in md and 'fix W' in md
    assert p['meta']['has_findings'] is True


def test_measurements_and_notes_sections():
    p = build_protocol(
        'Отчёт',
        measurements=[{'label': 'Vout', 'value': 6.0, 'unit': 'В'}],
        notes='Схема работоспособна, запасы в норме.',
    )
    assert 'Измерения' in p['sections']
    assert 'Выводы' in p['sections']
    assert 'Vout' in p['markdown'] and 'работоспособна' in p['markdown']


def test_simulation_runs_section_renders_engine_history():
    p = build_protocol(
        'Project protocol',
        simulation_runs=[
            {
                'analysis_type': 'tran',
                'engine': 'xyce-worker',
                'status': 'success',
                'elapsed_ms': 42,
                'created': '2026-06-17 08:15',
            }
        ],
    )

    assert any('симуляц' in section.lower() for section in p['sections'])
    assert 'tran' in p['markdown']
    assert 'xyce-worker' in p['markdown']
    assert '42' in p['markdown']


def test_simulation_outputs_section_renders_waveform_summary():
    p = build_protocol(
        'Waveform protocol',
        simulation_runs=[
            {
                'analysis_type': 'tran',
                'engine': 'xyce-worker',
                'result_data': {
                    'metrics': {'steps': 4, 'dt_s': 0.001},
                    'waveforms': [
                        {
                            'name': 'V(out)',
                            'unit': 'V',
                            'points': [
                                {'x': 0.0, 'y': 0.0},
                                {'x': 0.001, 'y': 1.2},
                                {'x': 0.002, 'y': 0.4},
                                {'x': 0.003, 'y': 2.4},
                            ],
                        }
                    ],
                    'artifacts': [{'name': 'tran.csv', 'path': 'artifacts/tran.csv'}],
                },
            }
        ],
    )

    assert any('Осциллограммы' in section for section in p['sections'])
    assert 'V(out)' in p['markdown']
    assert 'steps=4' in p['markdown']
    assert 'tran.csv' in p['markdown']


def test_synergy_with_engineering_lab_derating():
    # Авто-протокол = лабораторный отчёт: реальный результат calculate_lab → секция.
    from knowledge.services.engineering_lab import calculate_lab

    calc = calculate_lab('derating', {'rated_value': 0.25, 'actual_value': 0.18, 'derating_percent': 50})
    p = build_protocol('Протокол лабораторной', _divider(), lab_calcs=[calc])
    assert 'Состав схемы' in p['sections']
    assert 'Инженерные расчёты' in p['sections']
    assert 'Загрузка' in p['markdown']
