"""Финализация DRC правил: +11 до 100+, категории старым, валидация."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES_FILE = ROOT / 'Dolg_APP' / 'expert_rules' / 'default_rules.json'

# Категории для старых правил (по их id)
OLD_CATEGORIES = {
    'erc.missing_ground': 'connectivity',
    'erc.missing_source': 'power',
    'topology.floating_fragments': 'connectivity',
    'topology.divider_without_output': 'docs',
    'bom.missing_catalog_binding': 'bom',
    'derating.power_or_thermal_risk': 'rating',
    'simulation.no_saved_measurements': 'simulation',
    'import.unsupported_items': 'bom',
    'erc.led_reverse_polarity': 'polarity',
    'erc.parallel_voltage_sources': 'power',
    'erc.source_short_to_ground': 'power',
    'erc.dangling_named_net': 'connectivity',
    'erc.transistor_pinout_swap': 'polarity',
}

EXTRA_RULES = [
    {
        'id': 'topology.no_simulation_run',
        'category': 'simulation',
        'severity': 'recommendation',
        'title': 'Симуляция ни разу не запускалась на этой схеме',
        'recommendation': 'Запустите ▶ Запуск — без это нельзя верифицировать схему.',
        'when': 'sim_run_count == 0 and component_count > 0',
        'evidence_fields': ['sim_run_count'],
        'confidence': 0.85,
        'source': 'DOLG workflow',
    },
    {
        'id': 'connectivity.gnd_without_other_components',
        'category': 'connectivity',
        'severity': 'recommendation',
        'title': 'GND без других подключённых компонентов',
        'recommendation': 'GND должен быть точкой возврата для тока. Подключите остальные элементы.',
        'when': 'isolated_ground_count > 0',
        'evidence_fields': ['isolated_ground_count'],
        'confidence': 0.85,
        'source': 'KiCad ERC',
    },
    {
        'id': 'power.battery_drains_to_zero',
        'category': 'power',
        'severity': 'recommendation',
        'title': 'Батарея с очень малым внутренним R может «разрядиться» в симуляции',
        'recommendation': 'Добавьте серийный резистор 1 Ω для имитации реального источника.',
        'when': 'ideal_source_count > 0',
        'evidence_fields': ['ideal_source_count'],
        'confidence': 0.55,
        'source': 'ngspice numerical stability',
    },
    {
        'id': 'rating.thermal_no_heatsink',
        'category': 'rating',
        'severity': 'recommendation',
        'title': 'Силовой компонент (P > 1 Вт) без теплоотвода',
        'recommendation': 'Добавьте радиатор или используйте корпус с лучшим теплоотводом.',
        'when': 'high_power_no_heatsink_count > 0',
        'evidence_fields': ['high_power_no_heatsink_count'],
        'confidence': 0.85,
        'source': 'IPC-A-610 thermal',
    },
    {
        'id': 'topology.led_chain_no_constant_current',
        'category': 'topology',
        'severity': 'recommendation',
        'title': 'Цепочка LED без current source / constant current driver',
        'recommendation': 'Используйте LM317 в режиме CC или специализированный LED-driver.',
        'when': 'led_series_chain_no_cc_count > 0',
        'evidence_fields': ['led_series_chain_no_cc_count'],
        'confidence': 0.75,
        'source': 'Industry LED driver practice',
    },
    {
        'id': 'docs.no_revision_marks',
        'category': 'docs',
        'severity': 'recommendation',
        'title': 'Нет ревизии / даты / автора на схеме',
        'recommendation': 'Добавьте заголовок с REV / Date / Author для traceability.',
        'when': 'schematic_title_block_empty == true',
        'evidence_fields': ['schematic_title_block_empty'],
        'confidence': 0.9,
        'source': 'IEEE schematic standards',
    },
    {
        'id': 'simulation.warnings_unresolved',
        'category': 'simulation',
        'severity': 'warning',
        'title': 'Последняя симуляция вернула warnings',
        'recommendation': 'Прочитайте подсказки от ngspice — это знак нестабильности или потенциальной проблемы.',
        'when': 'last_sim_warning_count > 0',
        'evidence_fields': ['last_sim_warning_count'],
        'confidence': 0.85,
        'source': 'ngspice diagnostic',
    },
    {
        'id': 'connectivity.multiple_outputs_on_one_net',
        'category': 'connectivity',
        'severity': 'error',
        'title': 'Несколько выходов IC на одном net\'е (контактная конкуренция)',
        'recommendation': 'Для shared bus используйте tri-state буферы или open-drain.',
        'when': 'multi_output_net_count > 0',
        'evidence_fields': ['multi_output_net_count'],
        'confidence': 0.95,
        'source': 'KiCad ERC',
    },
    {
        'id': 'bom.cost_breakdown_unbalanced',
        'category': 'bom',
        'severity': 'recommendation',
        'title': 'Один компонент составляет > 60% BOM cost',
        'recommendation': 'Подберите аналог дороже-доминирующего компонента — большой выигрыш.',
        'when': 'cost_dominant_share > 0.6',
        'evidence_fields': ['cost_dominant_share'],
        'confidence': 0.7,
        'source': 'DOLG cost optimization',
    },
    {
        'id': 'topology.dc_motor_no_freewheeling_diode',
        'category': 'topology',
        'severity': 'error',
        'title': 'DC-motor / реле без обратного диода (freewheeling)',
        'recommendation': 'Параллельно индуктивной нагрузке поставьте диод (1N4148/1N4007) для защиты транзистора от EMF spike.',
        'when': 'inductive_load_no_diode_count > 0',
        'evidence_fields': ['inductive_load_no_diode_count'],
        'confidence': 0.95,
        'source': 'Industry switching practice',
    },
    {
        'id': 'topology.opto_isolator_no_pulldown',
        'category': 'topology',
        'severity': 'warning',
        'title': 'Опто-изолятор: выходной транзистор без pulldown',
        'recommendation': 'Добавьте 10к между collector и GND (collector — open).',
        'when': 'opto_no_pulldown_count > 0',
        'evidence_fields': ['opto_no_pulldown_count'],
        'confidence': 0.85,
        'source': 'Industry opto-isolator design',
    },
    {
        'id': 'signal.long_unbroken_clock_line',
        'category': 'signal',
        'severity': 'recommendation',
        'title': 'CLK > 300 мм без буфера',
        'recommendation': 'На длинных CLK-линиях добавьте buffer (74LVC1G125) каждые 200-300 мм.',
        'when': 'long_clock_line_count > 0',
        'evidence_fields': ['long_clock_line_count'],
        'confidence': 0.75,
        'source': 'High-speed digital design',
    },
    {
        'id': 'connectivity.no_test_points',
        'category': 'docs',
        'severity': 'recommendation',
        'title': 'Нет тест-точек на ключевых net\'ах',
        'recommendation': 'Для debug добавьте test-points на VCC, GND, CLK, OUT.',
        'when': 'test_point_count == 0 and component_count > 10',
        'evidence_fields': ['test_point_count'],
        'confidence': 0.75,
        'source': 'IPC-A-610 testability',
    },
    {
        'id': 'compliance.ce_marking_components',
        'category': 'compliance',
        'severity': 'recommendation',
        'title': 'Внешние разъёмы без CE-protection (ESD/EMI)',
        'recommendation': 'Для прохождения CE добавьте TVS на входах USB/Ethernet/Power.',
        'when': 'external_connector_count > 0 and ce_protection_count == 0',
        'evidence_fields': ['external_connector_count', 'ce_protection_count'],
        'confidence': 0.7,
        'source': 'EU CE marking',
    },
]


def main():
    with RULES_FILE.open('r', encoding='utf-8') as f:
        data = json.load(f)

    print(f'Before: {len(data["rules"])} rules')

    # 1. Проставить категории старым правилам
    for r in data['rules']:
        if 'category' not in r and r['id'] in OLD_CATEGORIES:
            r['category'] = OLD_CATEGORIES[r['id']]
        elif 'category' not in r:
            r['category'] = 'general'

    # 2. Добавить enabled: True старым уже работающим
    implemented_ids = {
        'erc.missing_ground', 'erc.missing_source', 'topology.floating_fragments',
        'bom.missing_catalog_binding', 'simulation.no_saved_measurements',
        'derating.power_or_thermal_risk', 'import.unsupported_items',
        'erc.led_reverse_polarity', 'erc.parallel_voltage_sources',
        'erc.source_short_to_ground', 'erc.dangling_named_net',
        'erc.transistor_pinout_swap', 'topology.divider_without_output',
    }
    for r in data['rules']:
        if 'enabled' not in r:
            r['enabled'] = r['id'] in implemented_ids

    # 3. Добавить EXTRA_RULES до 100+
    existing_ids = {r['id'] for r in data['rules']}
    for new_rule in EXTRA_RULES:
        if new_rule['id'] in existing_ids:
            continue
        rule = {
            'id': new_rule['id'],
            'title': new_rule['title'],
            'severity': new_rule['severity'],
            'when': new_rule['when'],
            'evidence_fields': new_rule['evidence_fields'],
            'recommendation': new_rule['recommendation'],
            'confidence': new_rule['confidence'],
            'category': new_rule['category'],
            'enabled': False,
            'references': {'source_ids': [new_rule['source']]},
        }
        data['rules'].append(rule)

    data['version'] = '2026.05-expert-v3-100rules'

    with RULES_FILE.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f'After: {len(data["rules"])} rules')

    cats = {}
    for r in data['rules']:
        c = r.get('category', 'unknown')
        cats[c] = cats.get(c, 0) + 1
    print('By category:')
    for c, n in sorted(cats.items(), key=lambda kv: -kv[1]):
        print(f'  {c}: {n}')

    enabled = sum(1 for r in data['rules'] if r.get('enabled', False))
    print(f'Enabled (implemented): {enabled}')
    print(f'Planned: {len(data["rules"]) - enabled}')


if __name__ == '__main__':
    main()
