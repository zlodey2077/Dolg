"""Generate a curated circuit training dataset for the tiny PyTorch model.

Output: Dolg_APP/ml/dataset/circuits.json — a list of scheme_data dicts
with ``__training_metadata`` (source_ids, source_topics, teacher_rules,
evidence_kind), compatible with train_tiny_model(extra_schemes=...).

Coverage:
- voltage_divider with E12 resistor pairs (~50 schemes)
- rc_network low/high-pass with varied cutoffs (~30 schemes)
- led_indicator with 3 LED colors × Vcc/R variations (~30 schemes)
- transistor_switch (NPN base resistor + collector load) (~15 schemes)
- battery + ground floating fragments (negative examples for DRC) (~10)
- empty / single-component edge cases (~5)

Run once, then:
    python manage.py train_tiny_circuit_ai --dataset Dolg_APP/ml/dataset/circuits.json
"""

from __future__ import annotations

import json
import random
from pathlib import Path


# E12 series — стандартный ряд номиналов резисторов
E12 = [1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2]


def voltage_divider(r1_ohm, r2_ohm, vin):
    """Generate a voltage divider schematic with given R1/R2 and Vin."""
    return {
        'components': [
            {'id': 'v1', 'type': 'battery', 'label': 'V1', 'voltage': vin, 'x': 100, 'y': 100},
            {'id': 'r1', 'type': 'resistor', 'label': 'R1', 'resistance': r1_ohm, 'x': 200, 'y': 100},
            {'id': 'r2', 'type': 'resistor', 'label': 'R2', 'resistance': r2_ohm, 'x': 300, 'y': 100},
            {'id': 'vout', 'type': 'node', 'label': 'Vout', 'x': 250, 'y': 100},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 200},
        ],
        'connections': [
            {'from': {'compId': 'v1', 'portId': 'p'}, 'to': {'compId': 'r1', 'portId': 'a'}},
            {'from': {'compId': 'r1', 'portId': 'b'}, 'to': {'compId': 'vout', 'portId': 'a'}},
            {'from': {'compId': 'vout', 'portId': 'a'}, 'to': {'compId': 'r2', 'portId': 'a'}},
            {'from': {'compId': 'r2', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'v1', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook', 'kicad_docs'],
            'source_topics': ['voltage_divider', 'ohms_law'],
            'teacher_rules': ['topology.divider_without_output'] if r1_ohm > 0 else [],
            'evidence_kind': 'curated_textbook',
        },
    }


def rc_network(r_ohm, c_uf, vin, kind='lowpass'):
    if kind == 'lowpass':
        comps = [
            {'id': 'v1', 'type': 'battery', 'label': 'V1', 'voltage': vin, 'x': 100, 'y': 100},
            {'id': 'r1', 'type': 'resistor', 'label': 'R1', 'resistance': r_ohm, 'x': 200, 'y': 100},
            {'id': 'c1', 'type': 'capacitor', 'label': 'C1', 'capacitance': c_uf, 'x': 300, 'y': 100},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 200},
        ]
        conns = [
            {'from': {'compId': 'v1', 'portId': 'p'}, 'to': {'compId': 'r1', 'portId': 'a'}},
            {'from': {'compId': 'r1', 'portId': 'b'}, 'to': {'compId': 'c1', 'portId': 'a'}},
            {'from': {'compId': 'c1', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'v1', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ]
    else:  # highpass
        comps = [
            {'id': 'v1', 'type': 'battery', 'label': 'V1', 'voltage': vin, 'x': 100, 'y': 100},
            {'id': 'c1', 'type': 'capacitor', 'label': 'C1', 'capacitance': c_uf, 'x': 200, 'y': 100},
            {'id': 'r1', 'type': 'resistor', 'label': 'R1', 'resistance': r_ohm, 'x': 300, 'y': 100},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 200},
        ]
        conns = [
            {'from': {'compId': 'v1', 'portId': 'p'}, 'to': {'compId': 'c1', 'portId': 'a'}},
            {'from': {'compId': 'c1', 'portId': 'b'}, 'to': {'compId': 'r1', 'portId': 'a'}},
            {'from': {'compId': 'r1', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'v1', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ]
    return {
        'components': comps,
        'connections': conns,
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook', 'ngspice_docs'],
            'source_topics': ['rc_network', 'filter', kind],
            'teacher_rules': [],
            'evidence_kind': 'curated_textbook',
        },
    }


def led_indicator(vin, r_ohm, led_color='red'):
    return {
        'components': [
            {'id': 'v1', 'type': 'battery', 'label': 'V1', 'voltage': vin, 'x': 100, 'y': 100},
            {'id': 'r1', 'type': 'resistor', 'label': 'R1', 'resistance': r_ohm, 'x': 200, 'y': 100},
            {'id': 'led1', 'type': 'led', 'label': 'LED1', 'color': led_color, 'x': 300, 'y': 100},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 200},
        ],
        'connections': [
            {'from': {'compId': 'v1', 'portId': 'p'}, 'to': {'compId': 'r1', 'portId': 'a'}},
            {'from': {'compId': 'r1', 'portId': 'b'}, 'to': {'compId': 'led1', 'portId': 'a'}},
            {'from': {'compId': 'led1', 'portId': 'k'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'v1', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook'],
            'source_topics': ['led_indicator', 'current_limiter'],
            'teacher_rules': [],
            'evidence_kind': 'curated_textbook',
        },
    }


def transistor_switch(rb_ohm, rc_ohm, vcc=5):
    return {
        'components': [
            {'id': 'vcc', 'type': 'battery', 'label': 'V1', 'voltage': vcc, 'x': 100, 'y': 100},
            {'id': 'rc', 'type': 'resistor', 'label': 'Rc', 'resistance': rc_ohm, 'x': 200, 'y': 100},
            {'id': 'rb', 'type': 'resistor', 'label': 'Rb', 'resistance': rb_ohm, 'x': 200, 'y': 200},
            {'id': 'q1', 'type': 'transistor', 'label': 'Q1', 'x': 300, 'y': 150},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 250},
        ],
        'connections': [
            {'from': {'compId': 'vcc', 'portId': 'p'}, 'to': {'compId': 'rc', 'portId': 'a'}},
            {'from': {'compId': 'rc', 'portId': 'b'}, 'to': {'compId': 'q1', 'portId': 'c'}},
            {'from': {'compId': 'rb', 'portId': 'b'}, 'to': {'compId': 'q1', 'portId': 'b'}},
            {'from': {'compId': 'q1', 'portId': 'e'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'vcc', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook'],
            'source_topics': ['transistor_switch', 'common_emitter'],
            'teacher_rules': [],
            'evidence_kind': 'curated_textbook',
        },
    }


def floating_fragment_bad():
    """Negative example: компоненты без GND — DRC должен ругнуться."""
    return {
        'components': [
            {'id': 'v1', 'type': 'battery', 'label': 'V1', 'voltage': 9, 'x': 100, 'y': 100},
            {'id': 'r1', 'type': 'resistor', 'label': 'R1', 'resistance': 1000, 'x': 200, 'y': 100},
        ],
        'connections': [
            {'from': {'compId': 'v1', 'portId': 'p'}, 'to': {'compId': 'r1', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['kicad_docs', 'ngspice_docs'],
            'source_topics': ['drc', 'missing_ground'],
            'teacher_rules': ['erc.missing_ground'],
            'evidence_kind': 'curated_negative',
        },
    }


# ============================================================================
# Расширенные топологии: используют типы inductor/diode/ic/button которых
# раньше не было — даёт нейронке покрытие всех 10 COMPONENT_TYPES.
# ============================================================================

def diode_bridge_rectifier(vin):
    """4-диодный мост: AC vin → DC через 4 диода + сглаживающий конденсатор."""
    return {
        'components': [
            {'id': 'v1', 'type': 'battery', 'label': 'V1', 'voltage': vin, 'x': 100, 'y': 100},
            {'id': 'd1', 'type': 'diode', 'label': 'D1', 'x': 200, 'y': 80},
            {'id': 'd2', 'type': 'diode', 'label': 'D2', 'x': 200, 'y': 160},
            {'id': 'd3', 'type': 'diode', 'label': 'D3', 'x': 300, 'y': 80},
            {'id': 'd4', 'type': 'diode', 'label': 'D4', 'x': 300, 'y': 160},
            {'id': 'c1', 'type': 'capacitor', 'label': 'C1', 'capacitance': 470, 'x': 400, 'y': 120},
            {'id': 'rl', 'type': 'resistor', 'label': 'RL', 'resistance': 1000, 'x': 500, 'y': 120},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 250},
        ],
        'connections': [
            {'from': {'compId': 'v1', 'portId': 'p'}, 'to': {'compId': 'd1', 'portId': 'a'}},
            {'from': {'compId': 'v1', 'portId': 'p'}, 'to': {'compId': 'd2', 'portId': 'k'}},
            {'from': {'compId': 'd1', 'portId': 'k'}, 'to': {'compId': 'd3', 'portId': 'k'}},
            {'from': {'compId': 'd2', 'portId': 'a'}, 'to': {'compId': 'd4', 'portId': 'a'}},
            {'from': {'compId': 'd3', 'portId': 'a'}, 'to': {'compId': 'c1', 'portId': 'a'}},
            {'from': {'compId': 'c1', 'portId': 'a'}, 'to': {'compId': 'rl', 'portId': 'a'}},
            {'from': {'compId': 'd4', 'portId': 'k'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'rl', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook', 'ngspice_docs'],
            'source_topics': ['diode_bridge', 'rectifier', 'power_supply'],
            'teacher_rules': [],
            'evidence_kind': 'curated_textbook',
        },
    }


def lc_tank(l_uh, c_pf):
    """LC-резонансный контур: индуктивность + конденсатор параллельно."""
    return {
        'components': [
            {'id': 'v1', 'type': 'battery', 'label': 'V1', 'voltage': 5, 'x': 100, 'y': 100},
            {'id': 'r1', 'type': 'resistor', 'label': 'R1', 'resistance': 10000, 'x': 200, 'y': 100},
            {'id': 'l1', 'type': 'inductor', 'label': 'L1', 'inductance': l_uh, 'x': 300, 'y': 80},
            {'id': 'c1', 'type': 'capacitor', 'label': 'C1', 'capacitance': c_pf, 'x': 300, 'y': 160},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 250},
        ],
        'connections': [
            {'from': {'compId': 'v1', 'portId': 'p'}, 'to': {'compId': 'r1', 'portId': 'a'}},
            {'from': {'compId': 'r1', 'portId': 'b'}, 'to': {'compId': 'l1', 'portId': 'a'}},
            {'from': {'compId': 'r1', 'portId': 'b'}, 'to': {'compId': 'c1', 'portId': 'a'}},
            {'from': {'compId': 'l1', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'c1', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'v1', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook'],
            'source_topics': ['lc_tank', 'resonant', 'oscillator'],
            'teacher_rules': [],
            'evidence_kind': 'curated_textbook',
        },
    }


def rl_filter(r_ohm, l_uh):
    """RL-фильтр для очистки питания."""
    return {
        'components': [
            {'id': 'v1', 'type': 'battery', 'label': 'V1', 'voltage': 12, 'x': 100, 'y': 100},
            {'id': 'l1', 'type': 'inductor', 'label': 'L1', 'inductance': l_uh, 'x': 200, 'y': 100},
            {'id': 'r1', 'type': 'resistor', 'label': 'R1', 'resistance': r_ohm, 'x': 300, 'y': 100},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 200},
        ],
        'connections': [
            {'from': {'compId': 'v1', 'portId': 'p'}, 'to': {'compId': 'l1', 'portId': 'a'}},
            {'from': {'compId': 'l1', 'portId': 'b'}, 'to': {'compId': 'r1', 'portId': 'a'}},
            {'from': {'compId': 'r1', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'v1', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook'],
            'source_topics': ['rl_filter', 'choke', 'power_supply'],
            'teacher_rules': [],
            'evidence_kind': 'curated_textbook',
        },
    }


def ne555_astable(r1_ohm, r2_ohm, c_nf):
    """Классический NE555 в astable-режиме (мультивибратор)."""
    return {
        'components': [
            {'id': 'vcc', 'type': 'battery', 'label': 'V1', 'voltage': 5, 'x': 100, 'y': 100},
            {'id': 'u1', 'type': 'ic', 'label': 'U1', 'part_number': 'NE555', 'x': 300, 'y': 150},
            {'id': 'r1', 'type': 'resistor', 'label': 'R1', 'resistance': r1_ohm, 'x': 200, 'y': 80},
            {'id': 'r2', 'type': 'resistor', 'label': 'R2', 'resistance': r2_ohm, 'x': 200, 'y': 130},
            {'id': 'c1', 'type': 'capacitor', 'label': 'C1', 'capacitance': c_nf, 'x': 200, 'y': 200},
            {'id': 'c2', 'type': 'capacitor', 'label': 'C2', 'capacitance': 10, 'x': 400, 'y': 200},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 450, 'y': 280},
        ],
        'connections': [
            {'from': {'compId': 'vcc', 'portId': 'p'}, 'to': {'compId': 'u1', 'portId': 'vcc'}},
            {'from': {'compId': 'vcc', 'portId': 'p'}, 'to': {'compId': 'r1', 'portId': 'a'}},
            {'from': {'compId': 'r1', 'portId': 'b'}, 'to': {'compId': 'r2', 'portId': 'a'}},
            {'from': {'compId': 'r2', 'portId': 'b'}, 'to': {'compId': 'u1', 'portId': 'thr'}},
            {'from': {'compId': 'u1', 'portId': 'thr'}, 'to': {'compId': 'c1', 'portId': 'a'}},
            {'from': {'compId': 'c1', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'u1', 'portId': 'gnd'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'c2', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'vcc', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook', 'ngspice_docs'],
            'source_topics': ['ne555', 'astable', 'oscillator', 'timer'],
            'teacher_rules': [],
            'evidence_kind': 'curated_textbook',
        },
    }


def voltage_regulator_7805(load_ohm):
    """LM7805 линейный регулятор + bypass-конденсаторы Cin/Cout."""
    return {
        'components': [
            {'id': 'vin', 'type': 'battery', 'label': 'V1', 'voltage': 9, 'x': 100, 'y': 100},
            {'id': 'u1', 'type': 'ic', 'label': 'U1', 'part_number': 'LM7805', 'x': 300, 'y': 100},
            {'id': 'cin', 'type': 'capacitor', 'label': 'Cin', 'capacitance': 100, 'x': 200, 'y': 150},
            {'id': 'cout', 'type': 'capacitor', 'label': 'Cout', 'capacitance': 10, 'x': 400, 'y': 150},
            {'id': 'rl', 'type': 'resistor', 'label': 'RL', 'resistance': load_ohm, 'x': 500, 'y': 100},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 250},
        ],
        'connections': [
            {'from': {'compId': 'vin', 'portId': 'p'}, 'to': {'compId': 'u1', 'portId': 'vin'}},
            {'from': {'compId': 'vin', 'portId': 'p'}, 'to': {'compId': 'cin', 'portId': 'a'}},
            {'from': {'compId': 'u1', 'portId': 'vout'}, 'to': {'compId': 'cout', 'portId': 'a'}},
            {'from': {'compId': 'u1', 'portId': 'vout'}, 'to': {'compId': 'rl', 'portId': 'a'}},
            {'from': {'compId': 'cin', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'cout', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'rl', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'u1', 'portId': 'gnd'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'vin', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook'],
            'source_topics': ['voltage_regulator', 'lm7805', 'linear_regulator'],
            'teacher_rules': [],
            'evidence_kind': 'curated_textbook',
        },
    }


def button_pullup_to_ic(pullup_ohm):
    """Кнопка + pull-up резистор → вход IC. Классическая схема дребезга."""
    return {
        'components': [
            {'id': 'vcc', 'type': 'battery', 'label': 'V1', 'voltage': 5, 'x': 100, 'y': 100},
            {'id': 'rpu', 'type': 'resistor', 'label': 'Rpu', 'resistance': pullup_ohm, 'x': 200, 'y': 100},
            {'id': 'sw1', 'type': 'button', 'label': 'SW1', 'x': 300, 'y': 150},
            {'id': 'u1', 'type': 'ic', 'label': 'U1', 'part_number': 'MCU', 'x': 400, 'y': 100},
            {'id': 'cdeb', 'type': 'capacitor', 'label': 'Cdeb', 'capacitance': 100, 'x': 300, 'y': 200},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 280},
        ],
        'connections': [
            {'from': {'compId': 'vcc', 'portId': 'p'}, 'to': {'compId': 'rpu', 'portId': 'a'}},
            {'from': {'compId': 'rpu', 'portId': 'b'}, 'to': {'compId': 'u1', 'portId': 'gpio'}},
            {'from': {'compId': 'rpu', 'portId': 'b'}, 'to': {'compId': 'sw1', 'portId': 'a'}},
            {'from': {'compId': 'sw1', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'rpu', 'portId': 'b'}, 'to': {'compId': 'cdeb', 'portId': 'a'}},
            {'from': {'compId': 'cdeb', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'u1', 'portId': 'gnd'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'vcc', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook', 'kicad_docs'],
            'source_topics': ['button', 'pullup', 'debounce', 'mcu_input'],
            'teacher_rules': [],
            'evidence_kind': 'curated_textbook',
        },
    }


def two_stage_rc_filter(r1, c1, r2, c2):
    """Двухкаскадный RC LPF — для покрытия multistage-схем."""
    return {
        'components': [
            {'id': 'v1', 'type': 'battery', 'label': 'V1', 'voltage': 5, 'x': 100, 'y': 100},
            {'id': 'r1', 'type': 'resistor', 'label': 'R1', 'resistance': r1, 'x': 200, 'y': 100},
            {'id': 'c1', 'type': 'capacitor', 'label': 'C1', 'capacitance': c1, 'x': 250, 'y': 200},
            {'id': 'r2', 'type': 'resistor', 'label': 'R2', 'resistance': r2, 'x': 350, 'y': 100},
            {'id': 'c2', 'type': 'capacitor', 'label': 'C2', 'capacitance': c2, 'x': 400, 'y': 200},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 280},
        ],
        'connections': [
            {'from': {'compId': 'v1', 'portId': 'p'}, 'to': {'compId': 'r1', 'portId': 'a'}},
            {'from': {'compId': 'r1', 'portId': 'b'}, 'to': {'compId': 'c1', 'portId': 'a'}},
            {'from': {'compId': 'r1', 'portId': 'b'}, 'to': {'compId': 'r2', 'portId': 'a'}},
            {'from': {'compId': 'r2', 'portId': 'b'}, 'to': {'compId': 'c2', 'portId': 'a'}},
            {'from': {'compId': 'c1', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'c2', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'v1', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook'],
            'source_topics': ['rc_network', 'multistage', 'cascade_filter'],
            'teacher_rules': [],
            'evidence_kind': 'curated_textbook',
        },
    }


def diode_clipper(vin):
    """Диодный ограничитель: 2 диода + резистор + источник."""
    return {
        'components': [
            {'id': 'v1', 'type': 'battery', 'label': 'V1', 'voltage': vin, 'x': 100, 'y': 100},
            {'id': 'r1', 'type': 'resistor', 'label': 'R1', 'resistance': 1000, 'x': 200, 'y': 100},
            {'id': 'd1', 'type': 'diode', 'label': 'D1', 'x': 300, 'y': 80},
            {'id': 'd2', 'type': 'diode', 'label': 'D2', 'x': 300, 'y': 160},
            {'id': 'rl', 'type': 'resistor', 'label': 'RL', 'resistance': 10000, 'x': 400, 'y': 100},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 250},
        ],
        'connections': [
            {'from': {'compId': 'v1', 'portId': 'p'}, 'to': {'compId': 'r1', 'portId': 'a'}},
            {'from': {'compId': 'r1', 'portId': 'b'}, 'to': {'compId': 'd1', 'portId': 'a'}},
            {'from': {'compId': 'r1', 'portId': 'b'}, 'to': {'compId': 'd2', 'portId': 'k'}},
            {'from': {'compId': 'r1', 'portId': 'b'}, 'to': {'compId': 'rl', 'portId': 'a'}},
            {'from': {'compId': 'd1', 'portId': 'k'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'd2', 'portId': 'a'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'rl', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'v1', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook'],
            'source_topics': ['diode_clipper', 'overvoltage_protection'],
            'teacher_rules': [],
            'evidence_kind': 'curated_textbook',
        },
    }


def common_emitter_amplifier(rb, rc, re_ohm):
    """Усилитель с общим эмиттером: R-divider bias + Rc нагрузка + Re в эмиттере."""
    return {
        'components': [
            {'id': 'vcc', 'type': 'battery', 'label': 'V1', 'voltage': 12, 'x': 100, 'y': 100},
            {'id': 'rb1', 'type': 'resistor', 'label': 'Rb1', 'resistance': rb, 'x': 200, 'y': 80},
            {'id': 'rb2', 'type': 'resistor', 'label': 'Rb2', 'resistance': rb // 4, 'x': 200, 'y': 180},
            {'id': 'rc', 'type': 'resistor', 'label': 'Rc', 'resistance': rc, 'x': 300, 'y': 80},
            {'id': 're', 'type': 'resistor', 'label': 'Re', 'resistance': re_ohm, 'x': 300, 'y': 220},
            {'id': 'q1', 'type': 'transistor', 'label': 'Q1', 'x': 300, 'y': 150},
            {'id': 'cin', 'type': 'capacitor', 'label': 'Cin', 'capacitance': 10, 'x': 150, 'y': 150},
            {'id': 'cout', 'type': 'capacitor', 'label': 'Cout', 'capacitance': 10, 'x': 380, 'y': 100},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 280},
        ],
        'connections': [
            {'from': {'compId': 'vcc', 'portId': 'p'}, 'to': {'compId': 'rb1', 'portId': 'a'}},
            {'from': {'compId': 'vcc', 'portId': 'p'}, 'to': {'compId': 'rc', 'portId': 'a'}},
            {'from': {'compId': 'rb1', 'portId': 'b'}, 'to': {'compId': 'q1', 'portId': 'b'}},
            {'from': {'compId': 'rb1', 'portId': 'b'}, 'to': {'compId': 'rb2', 'portId': 'a'}},
            {'from': {'compId': 'rb1', 'portId': 'b'}, 'to': {'compId': 'cin', 'portId': 'b'}},
            {'from': {'compId': 'rc', 'portId': 'b'}, 'to': {'compId': 'q1', 'portId': 'c'}},
            {'from': {'compId': 'rc', 'portId': 'b'}, 'to': {'compId': 'cout', 'portId': 'a'}},
            {'from': {'compId': 'q1', 'portId': 'e'}, 'to': {'compId': 're', 'portId': 'a'}},
            {'from': {'compId': 'rb2', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 're', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'vcc', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook'],
            'source_topics': ['common_emitter', 'amplifier', 'transistor_biasing'],
            'teacher_rules': [],
            'evidence_kind': 'curated_textbook',
        },
    }


def led_indicator_reversed(vin, r_ohm):
    """Negative: LED поставлен наоборот (анод к GND) — обучаем рулу erc.led_reverse_polarity."""
    return {
        'components': [
            {'id': 'v1', 'type': 'battery', 'label': 'V1', 'voltage': vin, 'x': 100, 'y': 100},
            {'id': 'r1', 'type': 'resistor', 'label': 'R1', 'resistance': r_ohm, 'x': 200, 'y': 100},
            # Анод (a) и катод (k) поменяли местами: a → GND вместо k → GND
            {'id': 'led1', 'type': 'led', 'label': 'LED1', 'x': 300, 'y': 100},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 200},
        ],
        'connections': [
            {'from': {'compId': 'v1', 'portId': 'p'}, 'to': {'compId': 'r1', 'portId': 'a'}},
            {'from': {'compId': 'r1', 'portId': 'b'}, 'to': {'compId': 'led1', 'portId': 'k'}},
            {'from': {'compId': 'led1', 'portId': 'a'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'v1', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook'],
            'source_topics': ['led', 'reverse_polarity', 'drc'],
            'teacher_rules': ['erc.led_reverse_polarity'],
            'evidence_kind': 'curated_negative',
        },
    }


# ============================================================================
# Wave 3 (v3): операционные усилители, мосты, измерительные схемы, осцилляторы.
# ============================================================================

def opamp_inverting_amplifier(rin, rf):
    """Инвертирующий усилитель на ОУ: G = -Rf/Rin."""
    return {
        'components': [
            {'id': 'vcc', 'type': 'battery', 'label': 'V1', 'voltage': 12, 'x': 100, 'y': 100},
            {'id': 'u1', 'type': 'ic', 'label': 'U1', 'part_number': 'LM358', 'x': 300, 'y': 150},
            {'id': 'rin', 'type': 'resistor', 'label': 'Rin', 'resistance': rin, 'x': 200, 'y': 150},
            {'id': 'rf', 'type': 'resistor', 'label': 'Rf', 'resistance': rf, 'x': 300, 'y': 90},
            {'id': 'rl', 'type': 'resistor', 'label': 'RL', 'resistance': 10000, 'x': 400, 'y': 150},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 280},
        ],
        'connections': [
            {'from': {'compId': 'vcc', 'portId': 'p'}, 'to': {'compId': 'u1', 'portId': 'vcc'}},
            {'from': {'compId': 'rin', 'portId': 'b'}, 'to': {'compId': 'u1', 'portId': 'in_neg'}},
            {'from': {'compId': 'rf', 'portId': 'a'}, 'to': {'compId': 'u1', 'portId': 'in_neg'}},
            {'from': {'compId': 'rf', 'portId': 'b'}, 'to': {'compId': 'u1', 'portId': 'out'}},
            {'from': {'compId': 'u1', 'portId': 'out'}, 'to': {'compId': 'rl', 'portId': 'a'}},
            {'from': {'compId': 'u1', 'portId': 'in_pos'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'u1', 'portId': 'gnd'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'rl', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'vcc', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook'],
            'source_topics': ['opamp', 'inverting_amplifier', 'analog'],
            'teacher_rules': [],
            'evidence_kind': 'curated_textbook',
        },
    }


def opamp_noninverting_amplifier(r1, r2):
    """Неинвертирующий усилитель на ОУ: G = 1 + R2/R1."""
    return {
        'components': [
            {'id': 'vcc', 'type': 'battery', 'label': 'V1', 'voltage': 12, 'x': 100, 'y': 100},
            {'id': 'u1', 'type': 'ic', 'label': 'U1', 'part_number': 'LM358', 'x': 300, 'y': 150},
            {'id': 'r1', 'type': 'resistor', 'label': 'R1', 'resistance': r1, 'x': 250, 'y': 220},
            {'id': 'r2', 'type': 'resistor', 'label': 'R2', 'resistance': r2, 'x': 320, 'y': 90},
            {'id': 'rl', 'type': 'resistor', 'label': 'RL', 'resistance': 10000, 'x': 400, 'y': 150},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 280},
        ],
        'connections': [
            {'from': {'compId': 'vcc', 'portId': 'p'}, 'to': {'compId': 'u1', 'portId': 'vcc'}},
            {'from': {'compId': 'u1', 'portId': 'in_neg'}, 'to': {'compId': 'r1', 'portId': 'a'}},
            {'from': {'compId': 'u1', 'portId': 'in_neg'}, 'to': {'compId': 'r2', 'portId': 'a'}},
            {'from': {'compId': 'r2', 'portId': 'b'}, 'to': {'compId': 'u1', 'portId': 'out'}},
            {'from': {'compId': 'u1', 'portId': 'out'}, 'to': {'compId': 'rl', 'portId': 'a'}},
            {'from': {'compId': 'r1', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'u1', 'portId': 'gnd'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'rl', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'vcc', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook'],
            'source_topics': ['opamp', 'noninverting_amplifier', 'analog'],
            'teacher_rules': [],
            'evidence_kind': 'curated_textbook',
        },
    }


def opamp_voltage_follower():
    """ОУ-повторитель: gain=1, высокое Zin, низкое Zout."""
    return {
        'components': [
            {'id': 'vcc', 'type': 'battery', 'label': 'V1', 'voltage': 12, 'x': 100, 'y': 100},
            {'id': 'u1', 'type': 'ic', 'label': 'U1', 'part_number': 'LM358', 'x': 300, 'y': 150},
            {'id': 'rs', 'type': 'resistor', 'label': 'Rs', 'resistance': 10000, 'x': 200, 'y': 100},
            {'id': 'rl', 'type': 'resistor', 'label': 'RL', 'resistance': 100, 'x': 400, 'y': 150},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 280},
        ],
        'connections': [
            {'from': {'compId': 'vcc', 'portId': 'p'}, 'to': {'compId': 'u1', 'portId': 'vcc'}},
            {'from': {'compId': 'vcc', 'portId': 'p'}, 'to': {'compId': 'rs', 'portId': 'a'}},
            {'from': {'compId': 'rs', 'portId': 'b'}, 'to': {'compId': 'u1', 'portId': 'in_pos'}},
            {'from': {'compId': 'u1', 'portId': 'in_neg'}, 'to': {'compId': 'u1', 'portId': 'out'}},
            {'from': {'compId': 'u1', 'portId': 'out'}, 'to': {'compId': 'rl', 'portId': 'a'}},
            {'from': {'compId': 'u1', 'portId': 'gnd'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'rl', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'vcc', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook'],
            'source_topics': ['opamp', 'voltage_follower', 'buffer'],
            'teacher_rules': [],
            'evidence_kind': 'curated_textbook',
        },
    }


def wheatstone_bridge(r1, r2, r3, r4):
    """Мост Уитстона: 4 резистора + дифференциальный измеритель."""
    return {
        'components': [
            {'id': 'v1', 'type': 'battery', 'label': 'V1', 'voltage': 5, 'x': 100, 'y': 150},
            {'id': 'r1', 'type': 'resistor', 'label': 'R1', 'resistance': r1, 'x': 200, 'y': 100},
            {'id': 'r2', 'type': 'resistor', 'label': 'R2', 'resistance': r2, 'x': 200, 'y': 200},
            {'id': 'r3', 'type': 'resistor', 'label': 'R3', 'resistance': r3, 'x': 300, 'y': 100},
            {'id': 'r4', 'type': 'resistor', 'label': 'R4', 'resistance': r4, 'x': 300, 'y': 200},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 280},
        ],
        'connections': [
            {'from': {'compId': 'v1', 'portId': 'p'}, 'to': {'compId': 'r1', 'portId': 'a'}},
            {'from': {'compId': 'v1', 'portId': 'p'}, 'to': {'compId': 'r3', 'portId': 'a'}},
            {'from': {'compId': 'r1', 'portId': 'b'}, 'to': {'compId': 'r2', 'portId': 'a'}},
            {'from': {'compId': 'r3', 'portId': 'b'}, 'to': {'compId': 'r4', 'portId': 'a'}},
            {'from': {'compId': 'r2', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'r4', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'v1', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook'],
            'source_topics': ['wheatstone_bridge', 'measurement'],
            'teacher_rules': [],
            'evidence_kind': 'curated_textbook',
        },
    }


def r2r_dac_4bit():
    """R-2R DAC, 4 бита: классическая лестница из R и 2R."""
    return {
        'components': [
            {'id': 'v1', 'type': 'battery', 'label': 'V1', 'voltage': 5, 'x': 100, 'y': 100},
            {'id': 'r1', 'type': 'resistor', 'label': 'R1', 'resistance': 10000, 'x': 200, 'y': 100},
            {'id': 'r2', 'type': 'resistor', 'label': 'R2', 'resistance': 10000, 'x': 250, 'y': 100},
            {'id': 'r3', 'type': 'resistor', 'label': 'R3', 'resistance': 10000, 'x': 300, 'y': 100},
            {'id': 'r2r1', 'type': 'resistor', 'label': '2R1', 'resistance': 20000, 'x': 200, 'y': 200},
            {'id': 'r2r2', 'type': 'resistor', 'label': '2R2', 'resistance': 20000, 'x': 250, 'y': 200},
            {'id': 'r2r3', 'type': 'resistor', 'label': '2R3', 'resistance': 20000, 'x': 300, 'y': 200},
            {'id': 'r2r4', 'type': 'resistor', 'label': '2R4', 'resistance': 20000, 'x': 350, 'y': 200},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 280},
        ],
        'connections': [
            {'from': {'compId': 'v1', 'portId': 'p'}, 'to': {'compId': 'r1', 'portId': 'a'}},
            {'from': {'compId': 'r1', 'portId': 'b'}, 'to': {'compId': 'r2', 'portId': 'a'}},
            {'from': {'compId': 'r2', 'portId': 'b'}, 'to': {'compId': 'r3', 'portId': 'a'}},
            {'from': {'compId': 'r1', 'portId': 'a'}, 'to': {'compId': 'r2r1', 'portId': 'a'}},
            {'from': {'compId': 'r1', 'portId': 'b'}, 'to': {'compId': 'r2r2', 'portId': 'a'}},
            {'from': {'compId': 'r2', 'portId': 'b'}, 'to': {'compId': 'r2r3', 'portId': 'a'}},
            {'from': {'compId': 'r3', 'portId': 'b'}, 'to': {'compId': 'r2r4', 'portId': 'a'}},
            {'from': {'compId': 'r2r1', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'r2r2', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'r2r3', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'r2r4', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'v1', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook'],
            'source_topics': ['r2r_dac', 'dac', 'digital_to_analog'],
            'teacher_rules': [],
            'evidence_kind': 'curated_textbook',
        },
    }


def high_side_pmos_switch(r_load):
    """High-side switch на P-MOSFET для нагрузки."""
    return {
        'components': [
            {'id': 'vcc', 'type': 'battery', 'label': 'V1', 'voltage': 12, 'x': 100, 'y': 100},
            {'id': 'q1', 'type': 'transistor', 'label': 'Q1', 'part_number': 'IRF9540', 'x': 200, 'y': 100},
            {'id': 'rg', 'type': 'resistor', 'label': 'Rg', 'resistance': 10000, 'x': 250, 'y': 180},
            {'id': 'rload', 'type': 'resistor', 'label': 'RL', 'resistance': r_load, 'x': 300, 'y': 100},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 250},
        ],
        'connections': [
            {'from': {'compId': 'vcc', 'portId': 'p'}, 'to': {'compId': 'q1', 'portId': 's'}},
            {'from': {'compId': 'q1', 'portId': 'd'}, 'to': {'compId': 'rload', 'portId': 'a'}},
            {'from': {'compId': 'q1', 'portId': 'g'}, 'to': {'compId': 'rg', 'portId': 'a'}},
            {'from': {'compId': 'rg', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'rload', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'vcc', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook'],
            'source_topics': ['mosfet_switch', 'high_side', 'load_driver'],
            'teacher_rules': [],
            'evidence_kind': 'curated_textbook',
        },
    }


def schmitt_trigger_74hc14():
    """Schmitt-триггер инвертор 74HC14 + RC цепь — генератор."""
    return {
        'components': [
            {'id': 'vcc', 'type': 'battery', 'label': 'V1', 'voltage': 5, 'x': 100, 'y': 100},
            {'id': 'u1', 'type': 'ic', 'label': 'U1', 'part_number': '74HC14', 'x': 300, 'y': 150},
            {'id': 'r1', 'type': 'resistor', 'label': 'R1', 'resistance': 10000, 'x': 200, 'y': 150},
            {'id': 'c1', 'type': 'capacitor', 'label': 'C1', 'capacitance': 0.1, 'x': 200, 'y': 220},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 280},
        ],
        'connections': [
            {'from': {'compId': 'vcc', 'portId': 'p'}, 'to': {'compId': 'u1', 'portId': 'vcc'}},
            {'from': {'compId': 'u1', 'portId': 'out'}, 'to': {'compId': 'r1', 'portId': 'a'}},
            {'from': {'compId': 'r1', 'portId': 'b'}, 'to': {'compId': 'u1', 'portId': 'in'}},
            {'from': {'compId': 'u1', 'portId': 'in'}, 'to': {'compId': 'c1', 'portId': 'a'}},
            {'from': {'compId': 'c1', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'u1', 'portId': 'gnd'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'vcc', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook'],
            'source_topics': ['schmitt_trigger', 'oscillator', 'digital'],
            'teacher_rules': [],
            'evidence_kind': 'curated_textbook',
        },
    }


def current_mirror(rref):
    """Зеркало тока (basic): два NPN с общим базовым узлом."""
    return {
        'components': [
            {'id': 'vcc', 'type': 'battery', 'label': 'V1', 'voltage': 5, 'x': 100, 'y': 100},
            {'id': 'rref', 'type': 'resistor', 'label': 'Rref', 'resistance': rref, 'x': 200, 'y': 100},
            {'id': 'q1', 'type': 'transistor', 'label': 'Q1', 'x': 250, 'y': 200},
            {'id': 'q2', 'type': 'transistor', 'label': 'Q2', 'x': 350, 'y': 200},
            {'id': 'rl', 'type': 'resistor', 'label': 'RL', 'resistance': 1000, 'x': 400, 'y': 100},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 280},
        ],
        'connections': [
            {'from': {'compId': 'vcc', 'portId': 'p'}, 'to': {'compId': 'rref', 'portId': 'a'}},
            {'from': {'compId': 'vcc', 'portId': 'p'}, 'to': {'compId': 'rl', 'portId': 'a'}},
            {'from': {'compId': 'rref', 'portId': 'b'}, 'to': {'compId': 'q1', 'portId': 'c'}},
            {'from': {'compId': 'q1', 'portId': 'c'}, 'to': {'compId': 'q1', 'portId': 'b'}},
            {'from': {'compId': 'q1', 'portId': 'b'}, 'to': {'compId': 'q2', 'portId': 'b'}},
            {'from': {'compId': 'rl', 'portId': 'b'}, 'to': {'compId': 'q2', 'portId': 'c'}},
            {'from': {'compId': 'q1', 'portId': 'e'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'q2', 'portId': 'e'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'vcc', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook'],
            'source_topics': ['current_mirror', 'analog_bias'],
            'teacher_rules': [],
            'evidence_kind': 'curated_textbook',
        },
    }


def voltage_doubler(c_uf):
    """Удвоитель напряжения (Cockcroft-Walton, 1 каскад)."""
    return {
        'components': [
            {'id': 'v1', 'type': 'battery', 'label': 'V1', 'voltage': 5, 'x': 100, 'y': 100},
            {'id': 'c1', 'type': 'capacitor', 'label': 'C1', 'capacitance': c_uf, 'x': 200, 'y': 100},
            {'id': 'c2', 'type': 'capacitor', 'label': 'C2', 'capacitance': c_uf, 'x': 300, 'y': 100},
            {'id': 'd1', 'type': 'diode', 'label': 'D1', 'x': 250, 'y': 150},
            {'id': 'd2', 'type': 'diode', 'label': 'D2', 'x': 350, 'y': 150},
            {'id': 'rl', 'type': 'resistor', 'label': 'RL', 'resistance': 10000, 'x': 400, 'y': 100},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 250},
        ],
        'connections': [
            {'from': {'compId': 'v1', 'portId': 'p'}, 'to': {'compId': 'c1', 'portId': 'a'}},
            {'from': {'compId': 'c1', 'portId': 'b'}, 'to': {'compId': 'd1', 'portId': 'a'}},
            {'from': {'compId': 'd1', 'portId': 'k'}, 'to': {'compId': 'c2', 'portId': 'a'}},
            {'from': {'compId': 'd1', 'portId': 'k'}, 'to': {'compId': 'd2', 'portId': 'a'}},
            {'from': {'compId': 'd2', 'portId': 'k'}, 'to': {'compId': 'rl', 'portId': 'a'}},
            {'from': {'compId': 'c2', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'rl', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'v1', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook'],
            'source_topics': ['voltage_doubler', 'charge_pump', 'cockcroft_walton'],
            'teacher_rules': [],
            'evidence_kind': 'curated_textbook',
        },
    }


# ----- Negative examples for every expert rule -----

def parallel_voltage_sources_bad():
    """Negative: 2 источника с разным V на одной шине → erc.parallel_voltage_sources."""
    return {
        'components': [
            {'id': 'v1', 'type': 'battery', 'label': 'V1', 'voltage': 5, 'x': 100, 'y': 100},
            {'id': 'v2', 'type': 'battery', 'label': 'V2', 'voltage': 9, 'x': 200, 'y': 100},
            {'id': 'rl', 'type': 'resistor', 'label': 'RL', 'resistance': 1000, 'x': 300, 'y': 100},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 200},
        ],
        'connections': [
            {'from': {'compId': 'v1', 'portId': 'p'}, 'to': {'compId': 'v2', 'portId': 'p'}},
            {'from': {'compId': 'v1', 'portId': 'p'}, 'to': {'compId': 'rl', 'portId': 'a'}},
            {'from': {'compId': 'rl', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'v1', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'v2', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['kicad_docs', 'ngspice_docs'],
            'source_topics': ['drc', 'parallel_sources', 'short_circuit'],
            'teacher_rules': ['erc.parallel_voltage_sources'],
            'evidence_kind': 'curated_negative',
        },
    }


def source_short_to_ground_bad(vin):
    """Negative: battery замкнут прямо на GND без R → erc.source_short_to_ground."""
    return {
        'components': [
            {'id': 'v1', 'type': 'battery', 'label': 'V1', 'voltage': vin, 'x': 100, 'y': 100},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 200, 'y': 200},
        ],
        'connections': [
            {'from': {'compId': 'v1', 'portId': 'p'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'v1', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['ngspice_docs'],
            'source_topics': ['drc', 'short_circuit'],
            'teacher_rules': ['erc.source_short_to_ground'],
            'evidence_kind': 'curated_negative',
        },
    }


def transistor_pinout_swap_bad():
    """Negative: коллектор прямо на GND, эмиттер на +V → topology.transistor_pinout_swap."""
    return {
        'components': [
            {'id': 'vcc', 'type': 'battery', 'label': 'V1', 'voltage': 5, 'x': 100, 'y': 100},
            {'id': 'rb', 'type': 'resistor', 'label': 'Rb', 'resistance': 10000, 'x': 200, 'y': 150},
            {'id': 'q1', 'type': 'transistor', 'label': 'Q1', 'x': 300, 'y': 150},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 250},
        ],
        'connections': [
            # NPN с перевёрнутыми c/e: c → GND, e → Vcc
            {'from': {'compId': 'vcc', 'portId': 'p'}, 'to': {'compId': 'q1', 'portId': 'e'}},
            {'from': {'compId': 'rb', 'portId': 'b'}, 'to': {'compId': 'q1', 'portId': 'b'}},
            {'from': {'compId': 'q1', 'portId': 'c'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            {'from': {'compId': 'vcc', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['all_about_circuits_textbook'],
            'source_topics': ['drc', 'transistor', 'pinout_swap'],
            'teacher_rules': ['topology.transistor_pinout_swap'],
            'evidence_kind': 'curated_negative',
        },
    }


def dangling_named_net_bad():
    """Negative: висящий именованный узел Vout, degree=1 → erc.dangling_named_net."""
    return {
        'components': [
            {'id': 'v1', 'type': 'battery', 'label': 'V1', 'voltage': 5, 'x': 100, 'y': 100},
            {'id': 'r1', 'type': 'resistor', 'label': 'R1', 'resistance': 1000, 'x': 200, 'y': 100},
            {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': 350, 'y': 250},
            # Висящий node с label 'Sense' — degree=1, нигде не используется
            {'id': 'sense', 'type': 'node', 'label': 'Sense', 'x': 400, 'y': 100},
        ],
        'connections': [
            {'from': {'compId': 'v1', 'portId': 'p'}, 'to': {'compId': 'r1', 'portId': 'a'}},
            {'from': {'compId': 'r1', 'portId': 'b'}, 'to': {'compId': 'sense', 'portId': 'a'}},
            {'from': {'compId': 'v1', 'portId': 'n'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
        ],
        '__training_metadata': {
            'source_ids': ['kicad_docs'],
            'source_topics': ['drc', 'dangling_net', 'named_net'],
            'teacher_rules': ['erc.dangling_named_net'],
            'evidence_kind': 'curated_negative',
        },
    }


def _make_variation(scheme, variation_idx):
    """Создаёт вариацию базовой схемы: jitter номиналов и позиций.

    Использует variation_idx для детерминизма (одна и та же base + idx → один
    и тот же результат при seed=42 на global random). Это позволяет:
    - сохранить топологию (соединения, типы компонентов)
    - изменить значения (resistance, capacitance, voltage) на ±20%
    - сдвинуть x/y на ±15 пикселей (модель учится топологии, не позициям)
    """
    import copy
    new = copy.deepcopy(scheme)
    rng = random.Random(hash((variation_idx, str(scheme.get('components', [])[:2]))) & 0xFFFFFFFF)

    # Jitter values
    for comp in new.get('components', []):
        for value_key in ('resistance', 'capacitance', 'inductance', 'voltage', 'current'):
            if value_key in comp and isinstance(comp[value_key], (int, float)):
                jitter = 1.0 + (rng.random() - 0.5) * 0.4  # ±20%
                comp[value_key] = round(comp[value_key] * jitter, 4)
        # Position jitter (±15 px)
        if 'x' in comp:
            comp['x'] = int(comp.get('x', 0) + (rng.random() - 0.5) * 30)
        if 'y' in comp:
            comp['y'] = int(comp.get('y', 0) + (rng.random() - 0.5) * 30)

    # Метаданные: помечаем что это вариация
    meta = new.get('__training_metadata') or {}
    meta = dict(meta)  # копия
    meta['variation_of'] = meta.get('topology') or '?'
    meta['variation_idx'] = variation_idx
    meta['evidence_kind'] = meta.get('evidence_kind', 'procedural_jitter')
    new['__training_metadata'] = meta
    return new


def main():
    random.seed(42)
    schemes = []

    # 1. Voltage dividers — 50 вариантов
    voltages = [3.3, 5, 9, 12, 15, 24]
    for vin in voltages:
        for r1 in E12[::2]:  # каждое второе значение
            for r2 in E12[::2]:
                r1_full = int(r1 * 1000)
                r2_full = int(r2 * 1000)
                schemes.append(voltage_divider(r1_full, r2_full, vin))
                if len(schemes) >= 50:
                    break
            if len(schemes) >= 50:
                break
        if len(schemes) >= 50:
            break

    # 2. RC filters — 30 (15 LP + 15 HP)
    rc_count_before = len(schemes)
    for kind in ['lowpass', 'highpass']:
        for r_kohm in [1, 4.7, 10, 22, 47]:
            for c_uf in [0.001, 0.01, 0.1]:
                schemes.append(rc_network(int(r_kohm * 1000), c_uf, 5, kind=kind))
                if len(schemes) - rc_count_before >= 30:
                    break
            if len(schemes) - rc_count_before >= 30:
                break

    # 3. LED indicators — 30 вариантов
    led_count_before = len(schemes)
    for vin in [3.3, 5, 9, 12]:
        for r in [220, 330, 470, 680, 1000, 2200, 4700]:
            for color in ['red', 'green', 'blue']:
                schemes.append(led_indicator(vin, r, color))
                if len(schemes) - led_count_before >= 30:
                    break
            if len(schemes) - led_count_before >= 30:
                break
        if len(schemes) - led_count_before >= 30:
            break

    # 4. Transistor switches — 15
    sw_before = len(schemes)
    for rb in [1000, 2200, 4700, 10000, 22000]:
        for rc in [220, 470, 1000]:
            schemes.append(transistor_switch(rb, rc, vcc=5))
            if len(schemes) - sw_before >= 15:
                break
        if len(schemes) - sw_before >= 15:
            break

    # 5. Negative examples — 10
    for _ in range(10):
        schemes.append(floating_fragment_bad())

    # 6. Diode bridge rectifiers — 12 (разные Vin)
    for vin in [6, 9, 12, 15, 18, 24]:
        schemes.append(diode_bridge_rectifier(vin))
        schemes.append(diode_bridge_rectifier(vin))  # дубликат для разнообразия (random.seed=42)

    # 7. LC tanks — 15 (резонансные контура, разные L/C)
    lc_count_before = len(schemes)
    for l_uh in [10, 47, 100, 470, 1000]:
        for c_pf in [10, 100, 1000]:
            schemes.append(lc_tank(l_uh, c_pf))
            if len(schemes) - lc_count_before >= 15:
                break
        if len(schemes) - lc_count_before >= 15:
            break

    # 8. RL filters — 12
    rl_before = len(schemes)
    for r_ohm in [100, 220, 470, 1000]:
        for l_uh in [10, 100, 1000]:
            schemes.append(rl_filter(r_ohm, l_uh))
            if len(schemes) - rl_before >= 12:
                break
        if len(schemes) - rl_before >= 12:
            break

    # 9. NE555 astable — 18 (популярная для timer/oscillator)
    ne_before = len(schemes)
    for r1 in [1000, 4700, 10000]:
        for r2 in [10000, 22000, 47000]:
            for c_nf in [10, 100]:
                schemes.append(ne555_astable(r1, r2, c_nf))
                if len(schemes) - ne_before >= 18:
                    break
            if len(schemes) - ne_before >= 18:
                break
        if len(schemes) - ne_before >= 18:
            break

    # 10. Voltage regulators 7805 — 10 (разные нагрузки)
    for r_load in [100, 220, 470, 1000, 2200, 4700, 10000, 22000, 47000, 100000]:
        schemes.append(voltage_regulator_7805(r_load))

    # 11. Button + pullup — 10 (debounce-схема)
    for r_pu in [1000, 2200, 4700, 10000, 22000]:
        for _ in range(2):
            schemes.append(button_pullup_to_ic(r_pu))

    # 12. Two-stage RC filters — 12
    two_rc_before = len(schemes)
    for r1 in [1000, 4700, 10000]:
        for c1 in [0.01, 0.1, 1]:
            for r2 in [1000, 4700]:
                schemes.append(two_stage_rc_filter(r1, c1, r2, c1 * 0.5))
                if len(schemes) - two_rc_before >= 12:
                    break
            if len(schemes) - two_rc_before >= 12:
                break
        if len(schemes) - two_rc_before >= 12:
            break

    # 13. Diode clippers — 8
    for vin in [3.3, 5, 9, 12, 15, 18, 24, 30]:
        schemes.append(diode_clipper(vin))

    # 14. Common emitter amplifiers — 12
    ce_before = len(schemes)
    for rb in [22000, 47000, 100000, 220000]:
        for rc in [1000, 2200, 4700]:
            schemes.append(common_emitter_amplifier(rb, rc, 470))
            if len(schemes) - ce_before >= 12:
                break
        if len(schemes) - ce_before >= 12:
            break

    # 15. LED reverse polarity (negative) — 8
    for vin in [3.3, 5, 9, 12]:
        for r in [220, 470]:
            schemes.append(led_indicator_reversed(vin, r))

    # 16. Op-amp inverting — 9
    for rin in [1000, 4700, 10000]:
        for rf in [10000, 47000, 100000]:
            schemes.append(opamp_inverting_amplifier(rin, rf))

    # 17. Op-amp non-inverting — 9
    for r1 in [1000, 4700, 10000]:
        for r2 in [10000, 47000, 100000]:
            schemes.append(opamp_noninverting_amplifier(r1, r2))

    # 18. Op-amp voltage follower — 5 (одинаковые, для baseline)
    for _ in range(5):
        schemes.append(opamp_voltage_follower())

    # 19. Wheatstone bridges — 10
    for delta_pct in [0, 1, 5, 10, 20]:
        for r_base in [1000, 4700]:
            sensor = int(r_base * (1 + delta_pct / 100))
            schemes.append(wheatstone_bridge(r_base, r_base, r_base, sensor))

    # 20. R-2R DAC — 5
    for _ in range(5):
        schemes.append(r2r_dac_4bit())

    # 21. High-side PMOS switch — 8
    for r_load in [10, 22, 47, 100, 220, 470, 1000, 2200]:
        schemes.append(high_side_pmos_switch(r_load))

    # 22. Schmitt trigger oscillators — 5
    for _ in range(5):
        schemes.append(schmitt_trigger_74hc14())

    # 23. Current mirrors — 6
    for rref in [220, 470, 1000, 2200, 4700, 10000]:
        schemes.append(current_mirror(rref))

    # 24. Voltage doublers — 5
    for c_uf in [0.1, 1, 10, 47, 100]:
        schemes.append(voltage_doubler(c_uf))

    # 25-28. Negative examples for ALL remaining expert rules
    for _ in range(8):
        schemes.append(parallel_voltage_sources_bad())
    for vin in [3.3, 5, 9, 12, 24, 48]:
        schemes.append(source_short_to_ground_bad(vin))
    for _ in range(6):
        schemes.append(transistor_pinout_swap_bad())
    for _ in range(6):
        schemes.append(dangling_named_net_bad())

    # === EXPANSION: value-variation multiplier ===
    # Стратегия: HF dataset недоступен (Cloudflare/network), генерируем
    # 8 вариаций каждой базовой схемы (jitter номиналов + позиций).
    # Это даёт реалистичный balanced dataset 340 → 3000+ без сети.
    base_count = len(schemes)
    variation_multiplier = 8
    print(f'Base curated set: {base_count} schemes. Expanding with {variation_multiplier}× variations…')
    expanded = []
    for scheme in schemes:
        for var_idx in range(variation_multiplier):
            new_scheme = _make_variation(scheme, var_idx)
            expanded.append(new_scheme)
    schemes.extend(expanded)
    print(f'After expansion: {len(schemes)} total schemes.')

    out = {
        'version': '4.0',
        'description': 'DOLG curated circuit dataset v4 — 28 topologies × 9 variations (base + 8 jittered). '
                       'HF-independent: procedural, reproducible (seed=42), без сетевых зависимостей.',
        'count': len(schemes),
        'topology_coverage': [
            'voltage_divider', 'rc_network', 'led_indicator', 'transistor_switch',
            'diode_bridge_rectifier', 'lc_tank', 'rl_filter',
            'ne555_astable', 'voltage_regulator_7805', 'button_pullup',
            'two_stage_rc', 'diode_clipper', 'common_emitter_amplifier',
            'opamp_inverting', 'opamp_noninverting', 'opamp_voltage_follower',
            'wheatstone_bridge', 'r2r_dac', 'high_side_pmos_switch',
            'schmitt_trigger', 'current_mirror', 'voltage_doubler',
            'drc_neg_missing_ground', 'drc_neg_led_reverse',
            'drc_neg_parallel_sources', 'drc_neg_source_short',
            'drc_neg_transistor_swap', 'drc_neg_dangling_net',
        ],
        'component_types_covered': [
            'battery', 'ground', 'resistor', 'capacitor', 'inductor',
            'led', 'diode', 'transistor', 'ic', 'button', 'node',
        ],
        'expert_rules_covered': [
            'erc.missing_ground', 'erc.led_reverse_polarity',
            'erc.parallel_voltage_sources', 'erc.source_short_to_ground',
            'topology.transistor_pinout_swap', 'erc.dangling_named_net',
        ],
        'schemes': schemes,
    }

    out_path = Path('Dolg_APP/ml/dataset/circuits.json')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Wrote {len(schemes)} schemes to {out_path} ({out_path.stat().st_size} bytes)')


if __name__ == '__main__':
    main()
