from django.contrib.admin.sites import AdminSite
from django.core.management import call_command
from django.test import TestCase

from Dolg_APP.admin import AITrainingExampleAdmin
from Dolg_APP.models import AITrainingExample
from Dolg_APP.services.ai_training import (
    curated_training_schemes,
    normalize_ai_training_example,
    normalize_ai_training_features,
    summarize_ai_training_examples,
)

SIMPLE_SCHEME = {
    'components': [
        {'id': 'V1', 'type': 'battery', 'voltage': '9V'},
        {'id': 'R1', 'type': 'resistor', 'value': '10k'},
        {'id': 'GND', 'type': 'ground'},
    ],
    'connections': [
        {'from': {'compId': 'V1'}, 'to': {'compId': 'R1'}},
        {'from': {'compId': 'R1'}, 'to': {'compId': 'GND'}},
    ],
}


class AIDatasetMetadataTests(TestCase):
    def test_text_only_example_is_retrieval_context(self):
        features = normalize_ai_training_features(
            {
                'source': 'learning_task',
                'evidence_kind': 'learning_task',
                'source_ids': ['ngspice_docs'],
            },
            kind='review_hint',
        )

        self.assertEqual(features['dataset_kind'], 'text_only')
        self.assertFalse(features['graph_training_ready'])
        self.assertEqual(features['training_role'], 'retrieval_context')

    def test_scheme_example_is_graph_ready(self):
        features = normalize_ai_training_features(
            {
                'source': 'demo_scheme',
                'evidence_kind': 'demo_scheme',
                'scheme_data': SIMPLE_SCHEME,
            },
            kind='review_hint',
        )

        self.assertEqual(features['dataset_kind'], 'scheme_backed')
        self.assertTrue(features['graph_training_ready'])
        self.assertEqual(features['training_role'], 'graph_training')
        self.assertIn('feature_vector', features)

    def test_normalize_example_updates_features(self):
        example = AITrainingExample.objects.create(
            kind='review_hint',
            prompt='Explain scheme',
            target='ok',
            features={'scheme_data': SIMPLE_SCHEME, 'evidence_kind': 'demo_scheme'},
            is_validated=True,
        )

        result = normalize_ai_training_example(example)
        example.refresh_from_db()

        self.assertTrue(result['changed'])
        self.assertEqual(example.features['dataset_kind'], 'scheme_backed')
        self.assertTrue(example.features['graph_training_ready'])

    def test_summary_and_curated_training_filter(self):
        AITrainingExample.objects.create(
            kind='review_hint',
            prompt='Learning text',
            target='answer',
            features={'source': 'learning_task', 'evidence_kind': 'learning_task'},
            is_validated=True,
        )
        scheme_example = AITrainingExample.objects.create(
            kind='review_hint',
            prompt='Scheme',
            target='answer',
            features=normalize_ai_training_features(
                {'scheme_data': SIMPLE_SCHEME, 'evidence_kind': 'demo_scheme'}
            ),
            is_validated=True,
        )

        summary = summarize_ai_training_examples()
        schemes = curated_training_schemes(limit=10)

        self.assertEqual(summary['by_dataset_kind']['text_only'], 1)
        self.assertEqual(summary['by_dataset_kind']['scheme_backed'], 1)
        self.assertEqual(summary['graph_training_ready'], 1)
        self.assertEqual(len(schemes), 1)
        self.assertEqual(
            schemes[0]['__training_metadata']['dataset_kind'], scheme_example.features['dataset_kind']
        )

    def test_management_command_normalizes_metadata(self):
        example = AITrainingExample.objects.create(
            kind='review_hint',
            prompt='Scheme',
            target='answer',
            features={'scheme_data': SIMPLE_SCHEME, 'evidence_kind': 'demo_scheme'},
            is_validated=True,
        )

        call_command('normalize_ai_dataset_metadata', '--validated-only')
        example.refresh_from_db()

        self.assertEqual(example.features['dataset_kind'], 'scheme_backed')
        self.assertTrue(example.features['graph_training_ready'])

    def test_admin_action_excludes_from_graph_training(self):
        example = AITrainingExample.objects.create(
            kind='review_hint',
            prompt='Scheme',
            target='answer',
            features=normalize_ai_training_features(
                {'scheme_data': SIMPLE_SCHEME, 'evidence_kind': 'demo_scheme'}
            ),
            is_validated=True,
        )
        model_admin = AITrainingExampleAdmin(AITrainingExample, AdminSite())
        model_admin.message_user = lambda *args, **kwargs: None

        model_admin.exclude_from_graph_training(None, AITrainingExample.objects.filter(pk=example.pk))
        example.refresh_from_db()

        self.assertFalse(example.features['graph_training_ready'])
        self.assertEqual(example.features['training_role'], 'retrieval_context')
        self.assertTrue(example.features['graph_excluded_by_admin'])
