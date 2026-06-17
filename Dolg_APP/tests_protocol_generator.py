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


def test_synergy_with_engineering_lab_derating():
    # Авто-протокол = лабораторный отчёт: реальный результат calculate_lab → секция.
    from knowledge.services.engineering_lab import calculate_lab

    calc = calculate_lab('derating', {'rated_value': 0.25, 'actual_value': 0.18, 'derating_percent': 50})
    p = build_protocol('Протокол лабораторной', _divider(), lab_calcs=[calc])
    assert 'Состав схемы' in p['sections']
    assert 'Инженерные расчёты' in p['sections']
    assert 'Загрузка' in p['markdown']
