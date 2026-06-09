from __future__ import annotations

from django.test import SimpleTestCase

from Dolg_APP.services.schematic_graph import analyze_graph_topology
from Dolg_APP.services.schematic_operations import apply_schematic_operations


class SchematicOperationTests(SimpleTestCase):
    def test_builds_scheme_from_programmatic_operations(self):
        result = apply_schematic_operations(
            {},
            [
                {'operation': 'add_component', 'type': 'battery', 'id': 'V1', 'x': 40, 'y': 80, 'voltage': 9},
                {'operation': 'add_component', 'type': 'resistor', 'id': 'R1', 'x': 160, 'y': 80, 'resistance': 1000},
                {'operation': 'add_component', 'type': 'ground', 'id': 'GND1', 'x': 160, 'y': 180},
                {
                    'operation': 'add_wire',
                    'from': {'component': 'V1', 'port': '+'},
                    'to': {'component': 'R1', 'port': '1'},
                },
                {
                    'operation': 'add_wire',
                    'from': {'component': 'R1', 'port': '2'},
                    'to': {'component': 'GND1', 'port': '1'},
                    'net_label': 'GND',
                },
            ],
        )

        self.assertTrue(result['ok'], result['report'])
        scheme = result['scheme_data']
        self.assertEqual(len(scheme['components']), 3)
        self.assertEqual(len(scheme['connections']), 2)
        self.assertEqual(scheme['connections'][1]['to'], {'compId': 'GND1', 'portId': 'a'})
        self.assertEqual(scheme['metadata']['programmatic']['last_operation_count'], 5)

        topology = analyze_graph_topology(scheme)
        self.assertTrue(topology['metrics']['has_ground'])
        self.assertTrue(topology['metrics']['has_source'])
        self.assertEqual(topology['metrics']['connected_components_count'], 1)

    def test_generates_stable_ids_and_default_ports(self):
        result = apply_schematic_operations(
            {'components': [{'id': 'R1', 'type': 'resistor'}], 'connections': []},
            [
                {'operation': 'add_component', 'type': 'resistor'},
                {'operation': 'add_component', 'type': 'capacitor'},
            ],
        )

        self.assertTrue(result['ok'], result['report'])
        components = {item['id']: item for item in result['scheme_data']['components']}
        self.assertIn('R2', components)
        self.assertIn('C1', components)
        self.assertEqual(components['R2']['ports'], [{'id': '1'}, {'id': '2'}])

    def test_rejects_bad_wire_without_corrupting_scheme(self):
        result = apply_schematic_operations(
            {'components': [{'id': 'R1', 'type': 'resistor', 'ports': [{'id': '1'}, {'id': '2'}]}], 'connections': []},
            [
                {
                    'operation': 'add_wire',
                    'from': {'component': 'R1', 'port': '1'},
                    'to': {'component': 'MISSING', 'port': '1'},
                }
            ],
        )

        self.assertFalse(result['ok'])
        self.assertEqual(result['scheme_data']['connections'], [])
        self.assertEqual(result['report']['rejected'][0]['code'], 'missing_component')

    def test_atomic_mode_rolls_back_batch(self):
        result = apply_schematic_operations(
            {},
            [
                {'operation': 'add_component', 'type': 'resistor', 'id': 'R1'},
                {
                    'operation': 'add_wire',
                    'from': {'component': 'R1', 'port': '1'},
                    'to': {'component': 'MISSING', 'port': '1'},
                },
            ],
            atomic=True,
        )

        self.assertFalse(result['ok'])
        self.assertTrue(result['report']['rolled_back'])
        self.assertEqual(result['report']['applied_count'], 0)
        self.assertEqual(result['scheme_data']['components'], [])

    def test_delete_component_removes_attached_wires(self):
        scheme = {
            'components': [
                {'id': 'R1', 'type': 'resistor', 'ports': [{'id': '1'}, {'id': '2'}]},
                {'id': 'C1', 'type': 'capacitor', 'ports': [{'id': '1'}, {'id': '2'}]},
            ],
            'connections': [
                {
                    'id': 'W1',
                    'from': {'compId': 'R1', 'portId': '2'},
                    'to': {'compId': 'C1', 'portId': '1'},
                }
            ],
        }

        result = apply_schematic_operations(scheme, {'operation': 'delete_component', 'id': 'R1'})

        self.assertTrue(result['ok'], result['report'])
        self.assertEqual([item['id'] for item in result['scheme_data']['components']], ['C1'])
        self.assertEqual(result['scheme_data']['connections'], [])

    def test_move_rotate_and_set_property(self):
        scheme = {'components': [{'id': 'R1', 'type': 'resistor', 'x': 5, 'y': 6}], 'connections': []}
        result = apply_schematic_operations(
            scheme,
            [
                {'operation': 'move_component', 'id': 'R1', 'dx': 10, 'dy': -2},
                {'operation': 'rotate_component', 'id': 'R1'},
                {'operation': 'set_property', 'id': 'R1', 'property': 'resistance', 'value': 4700},
            ],
        )

        self.assertTrue(result['ok'], result['report'])
        component = result['scheme_data']['components'][0]
        self.assertEqual(component['x'], 15)
        self.assertEqual(component['y'], 4)
        self.assertEqual(component['rotation'], 90)
        self.assertEqual(component['resistance'], 4700)
