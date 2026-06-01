"""Помечает правила как enabled: true для тех у которых детектор готов."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES_FILE = ROOT / 'Dolg_APP' / 'expert_rules' / 'default_rules.json'

# Эти правила имеют рабочий detector (или подтверждённую evidence) в
# expert_detectors.py + project_review.py (после обновления 2026-05-31).
NEWLY_ENABLED = {
    # Connectivity
    'conn.single_connection_component',
    'conn.dangling_port',
    'conn.disjoint_islands',
    'conn.duplicate_wire',
    'conn.multiple_gnd_different_nets',
    'connectivity.gnd_without_other_components',
    # Power
    'power.parallel_voltage_same_level',
    'power.source_no_return_path',
    'power.battery_reverse_polarity',
    'power.source_to_gnd_short',
    # Topology
    'topology.led_chain_no_constant_current',
    'topology.dc_motor_no_freewheeling_diode',
    # Docs
    'docs.unlabeled_components',
    'docs.no_net_labels',
    # Simulation
    'simulation.unrealistic_components',
    'topology.no_simulation_run',
    # BOM
    'bom.unbound_components',
    'bom.duplicate_designators',
    'bom.no_spice_model',
}


def main():
    with RULES_FILE.open('r', encoding='utf-8') as f:
        data = json.load(f)

    enabled_before = sum(1 for r in data['rules'] if r.get('enabled', False))
    newly = 0
    for r in data['rules']:
        if r['id'] in NEWLY_ENABLED:
            if not r.get('enabled', False):
                r['enabled'] = True
                newly += 1
            r['references'] = r.get('references', {})
            r['references']['implementation'] = '2026-05-31 expert_detectors v3'

    with RULES_FILE.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    enabled_after = sum(1 for r in data['rules'] if r.get('enabled', False))
    print(f'Enabled before: {enabled_before}')
    print(f'Enabled now: {enabled_after} (+{newly})')
    print(f'Total rules: {len(data["rules"])}')


if __name__ == '__main__':
    main()
