from django.test import SimpleTestCase

from .services.review_visualization import build_review_3d_payload


class ReviewVisualizationPayloadTests(SimpleTestCase):
    def test_build_review_3d_payload_contains_score_metrics_and_risks(self):
        payload = build_review_3d_payload({
            'score': 72,
            'status': 'needs_review',
            'status_label': 'нужна проверка',
            'errors': ['missing gnd'],
            'warnings': ['no measurements'],
            'expert_findings': [{'rule_id': 'erc.missing_ground'}],
            'metrics': {
                'components': 5,
                'connections': 4,
                'simulations': 1,
                'measurements': 2,
                'cycle_count': 1,
                'topology': 'voltage_divider',
            },
            'sections': {
                'bom': {'risks': [{'kind': 'missing_model'}]},
                'derating': {'issues': []},
                'validity': {'issues': []},
                'manufacturing': {'missing': ['footprint']},
                'external_cad': {'findings': []},
                'connectivity': {'floating_components': ['r2']},
            },
        })

        self.assertTrue(payload['enabled'])
        keys = {item['key'] for item in payload['columns']}
        self.assertIn('health_score', keys)
        self.assertIn('components', keys)
        self.assertIn('errors', keys)
        self.assertGreaterEqual(len(payload['risk_points']), 1)
        self.assertEqual(payload['summary']['topology'], 'voltage_divider')
