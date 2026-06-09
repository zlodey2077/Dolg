from __future__ import annotations

from django.test import SimpleTestCase

from Dolg_APP.services.schematic_layout_quality import analyze_schematic_layout


class SchematicLayoutQualityTests(SimpleTestCase):
    def test_orthogonal_routed_layout_is_ok(self):
        scheme = {
            'components': [
                {'id': 'V1', 'type': 'battery', 'x': 0, 'y': 0},
                {'id': 'R1', 'type': 'resistor', 'x': 160, 'y': 0},
                {'id': 'GND1', 'type': 'ground', 'x': 160, 'y': 140},
            ],
            'connections': [
                {
                    'from': {'compId': 'V1', 'portId': '+'},
                    'to': {'compId': 'R1', 'portId': '1'},
                    'waypoints': [{'x': 80, 'y': 0}],
                },
                {
                    'from': {'compId': 'R1', 'portId': '2'},
                    'to': {'compId': 'GND1', 'portId': 'a'},
                    'waypoints': [{'x': 160, 'y': 70}],
                },
            ],
        }

        report = analyze_schematic_layout(scheme)

        self.assertTrue(report['ok'], report)
        self.assertEqual(report['metrics']['direct_diagonal_connection_count'], 0)

    def test_long_direct_diagonal_wires_are_rejected(self):
        scheme = {
            'components': [
                {'id': 'A', 'type': 'node', 'x': 0, 'y': 0},
                {'id': 'B', 'type': 'node', 'x': 360, 'y': 240},
                {'id': 'C', 'type': 'node', 'x': 0, 'y': 240},
                {'id': 'D', 'type': 'node', 'x': 360, 'y': 0},
                {'id': 'E', 'type': 'node', 'x': 60, 'y': 420},
                {'id': 'F', 'type': 'node', 'x': 420, 'y': 120},
            ],
            'connections': [
                {'from': {'compId': 'A'}, 'to': {'compId': 'B'}},
                {'from': {'compId': 'C'}, 'to': {'compId': 'D'}},
                {'from': {'compId': 'E'}, 'to': {'compId': 'F'}},
            ],
        }

        report = analyze_schematic_layout(scheme)

        self.assertFalse(report['ok'])
        self.assertTrue(
            any(item['code'] == 'unrouted_direct_diagonal_wires' for item in report['findings']),
            report,
        )

    def test_flattened_internal_and_external_needs_hierarchy(self):
        components = [
            {'id': 'P1_GND', 'type': 'pin', 'x': 0, 'y': 0},
            {'id': 'P2_TRIG', 'type': 'pin', 'x': 0, 'y': 80},
            {'id': 'CMP_THRESH', 'type': 'comparator', 'x': 160, 'y': 0},
            {'id': 'SR_LATCH', 'type': 'sr_latch', 'x': 320, 'y': 0},
            {'id': 'OUT_DRIVER', 'type': 'output_driver', 'x': 480, 'y': 0},
            {'id': 'R1_EXT', 'type': 'resistor', 'x': 0, 'y': 220},
            {'id': 'R2_EXT', 'type': 'resistor', 'x': 120, 'y': 220},
            {'id': 'C1_EXT', 'type': 'capacitor', 'x': 240, 'y': 220},
            {'id': 'LED1', 'type': 'led', 'x': 360, 'y': 220},
            {'id': 'T1', 'type': 'transistor', 'x': 480, 'y': 220},
            {'id': 'VCC', 'type': 'battery', 'x': 600, 'y': 220},
            {'id': 'J1', 'type': 'connector', 'x': 720, 'y': 220},
            {'id': 'N1', 'type': 'node', 'x': 0, 'y': 340},
            {'id': 'N2', 'type': 'node', 'x': 120, 'y': 340},
            {'id': 'N3', 'type': 'node', 'x': 240, 'y': 340},
            {'id': 'N4', 'type': 'node', 'x': 360, 'y': 340},
            {'id': 'N5', 'type': 'node', 'x': 480, 'y': 340},
            {'id': 'N6', 'type': 'node', 'x': 600, 'y': 340},
        ]
        scheme = {'components': components, 'connections': [], 'metadata': {'title': 'flat 555 attempt'}}

        report = analyze_schematic_layout(scheme)

        self.assertFalse(report['ok'])
        self.assertTrue(report['metrics']['requires_hierarchy'])
        self.assertTrue(
            any(item['code'] == 'hierarchical_subcircuit_required' for item in report['findings']),
            report,
        )

    def test_subcircuit_metadata_allows_internal_sheet(self):
        scheme = {
            'subcircuits': [{'id': 'NE555'}],
            'components': [
                {'id': 'P1_GND', 'type': 'pin', 'x': 0, 'y': 0},
                {'id': 'CMP_THRESH', 'type': 'comparator', 'x': 160, 'y': 0},
                {'id': 'SR_LATCH', 'type': 'sr_latch', 'x': 320, 'y': 0},
                {'id': 'OUT_DRIVER', 'type': 'output_driver', 'x': 480, 'y': 0},
                {'id': 'R1_EXT', 'type': 'resistor', 'x': 0, 'y': 220},
                {'id': 'R2_EXT', 'type': 'resistor', 'x': 120, 'y': 220},
                {'id': 'C1_EXT', 'type': 'capacitor', 'x': 240, 'y': 220},
                {'id': 'LED1', 'type': 'led', 'x': 360, 'y': 220},
                {'id': 'T1', 'type': 'transistor', 'x': 480, 'y': 220},
                {'id': 'VCC', 'type': 'battery', 'x': 600, 'y': 220},
                {'id': 'J1', 'type': 'connector', 'x': 720, 'y': 220},
                {'id': 'N1', 'type': 'node', 'x': 0, 'y': 340},
                {'id': 'N2', 'type': 'node', 'x': 120, 'y': 340},
                {'id': 'N3', 'type': 'node', 'x': 240, 'y': 340},
                {'id': 'N4', 'type': 'node', 'x': 360, 'y': 340},
                {'id': 'N5', 'type': 'node', 'x': 480, 'y': 340},
                {'id': 'N6', 'type': 'node', 'x': 600, 'y': 340},
            ],
            'connections': [],
        }

        report = analyze_schematic_layout(scheme)

        self.assertTrue(
            all(item['code'] != 'hierarchical_subcircuit_required' for item in report['findings']),
            report,
        )

    def test_bad_child_sheet_fails_hierarchical_document(self):
        scheme = {
            'sheets': [
                {
                    'id': 'bad_external',
                    'components': [
                        {'id': 'A', 'type': 'node', 'x': 0, 'y': 0},
                        {'id': 'B', 'type': 'node', 'x': 360, 'y': 240},
                        {'id': 'C', 'type': 'node', 'x': 0, 'y': 240},
                        {'id': 'D', 'type': 'node', 'x': 360, 'y': 0},
                        {'id': 'E', 'type': 'node', 'x': 60, 'y': 420},
                        {'id': 'F', 'type': 'node', 'x': 420, 'y': 120},
                    ],
                    'connections': [
                        {'from': {'compId': 'A'}, 'to': {'compId': 'B'}},
                        {'from': {'compId': 'C'}, 'to': {'compId': 'D'}},
                        {'from': {'compId': 'E'}, 'to': {'compId': 'F'}},
                    ],
                }
            ],
            'subcircuits': [],
        }

        report = analyze_schematic_layout(scheme)

        self.assertFalse(report['ok'])
        self.assertTrue(report['metrics']['scopes']['sheet:bad_external'])
        self.assertTrue(
            any(
                item['scope'] == 'sheet:bad_external' and item['code'] == 'unrouted_direct_diagonal_wires'
                for item in report['findings']
            ),
            report,
        )

    def test_port_coordinates_are_used_instead_of_component_centers(self):
        scheme = {
            'components': [
                {
                    'id': 'U1',
                    'type': 'ic',
                    'x': 300,
                    'y': 300,
                    'width': 220,
                    'height': 180,
                    'ports': [{'id': 'out', 'x': 410, 'y': 300}],
                },
                {
                    'id': 'R1',
                    'type': 'resistor',
                    'x': 520,
                    'y': 300,
                    'ports': [{'id': '1', 'x': 479, 'y': 300}],
                },
            ],
            'connections': [
                {'from': {'compId': 'U1', 'portId': 'out'}, 'to': {'compId': 'R1', 'portId': '1'}},
            ],
        }

        report = analyze_schematic_layout(scheme)

        self.assertTrue(report['ok'], report)
        self.assertEqual(report['metrics']['direct_diagonal_connection_count'], 0)

    def test_explicit_component_sizes_are_used_for_overlap_checks(self):
        scheme = {
            'components': [
                {'id': 'U1', 'type': 'ic', 'x': 100, 'y': 100, 'width': 240, 'height': 160},
                {'id': 'R1', 'type': 'resistor', 'x': 210, 'y': 100, 'width': 80, 'height': 40},
            ],
            'connections': [],
        }

        report = analyze_schematic_layout(scheme)

        self.assertTrue(any(item['code'] == 'component_overlaps' for item in report['findings']), report)
