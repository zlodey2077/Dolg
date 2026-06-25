from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from Dolg_APP.ml_admin_views import MLIMPORT_PROGRESS_KEY, MLTRAIN_PROGRESS_KEY
from Dolg_APP.models import MLJob, SchematicProject
from Dolg_APP.services.ops_metrics import collect_ops_snapshot

User = get_user_model()


class MLJobModelTests(TestCase):
    def test_mljob_lifecycle_helpers(self):
        job = MLJob.objects.create(job_type='training', source='synthetic')

        job.mark_running(message='start')
        job.refresh_from_db()
        self.assertEqual(job.status, 'running')
        self.assertIsNotNone(job.started_at)
        self.assertIsNotNone(job.heartbeat_at)

        job.update_progress(progress_percent=45, processed=9, message='epoch 9')
        job.refresh_from_db()
        self.assertEqual(job.progress_percent, 45)
        self.assertEqual(job.processed, 9)
        self.assertEqual(job.message, 'epoch 9')

        job.mark_success(message='done', result={'final_loss': 0.1})
        job.refresh_from_db()
        self.assertEqual(job.status, 'success')
        self.assertEqual(job.progress_percent, 100)
        self.assertEqual(job.result['final_loss'], 0.1)
        self.assertIsNotNone(job.finished_at)

    def test_mljob_error_helper(self):
        job = MLJob.objects.create(job_type='dataset_import', source='open_schematics')
        job.mark_error(error='network timeout', message='failed')
        job.refresh_from_db()

        self.assertEqual(job.status, 'error')
        self.assertIn('network timeout', job.error)
        self.assertEqual(job.message, 'failed')


class MLAdminViewsTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username='staff',
            email='staff@example.com',
            password='pass',
            is_staff=True,
        )
        self.client.force_login(self.staff)
        cache.clear()

    def test_training_status_returns_latest_job(self):
        job = MLJob.objects.create(
            job_type='training',
            status='running',
            progress_percent=12,
            source='synthetic',
            created_by=self.staff,
        )
        cache.set(
            MLTRAIN_PROGRESS_KEY,
            {
                'state': 'running',
                'job_id': job.pk,
                'epoch': 2,
                'total_epochs': 10,
                'message': 'epoch 2',
            },
        )

        response = self.client.get(reverse('hello:ml_training_status'))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['latest_job']['id'], job.pk)
        self.assertEqual(payload['latest_job']['progress_percent'], 20)

    def test_import_status_returns_latest_job(self):
        job = MLJob.objects.create(
            job_type='dataset_import',
            status='running',
            source='open_schematics',
            created_by=self.staff,
        )
        cache.set(
            MLIMPORT_PROGRESS_KEY,
            {
                'state': 'running',
                'processed': 25,
                'limit': 100,
                'imported': 8,
                'skipped': 2,
                'message': 'processed 25',
            },
        )

        response = self.client.get(reverse('hello:ml_dataset_import_status'))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['latest_job']['id'], job.pk)
        self.assertEqual(payload['latest_job']['progress_percent'], 25)
        self.assertEqual(payload['latest_job']['created_count'], 8)

    def test_reset_marks_running_jobs_cancelled(self):
        training = MLJob.objects.create(job_type='training', status='running')
        importing = MLJob.objects.create(job_type='dataset_import', status='queued')

        response = self.client.post(reverse('hello:ml_training_reset'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['jobs_cancelled'], 2)

        training.refresh_from_db()
        importing.refresh_from_db()
        self.assertEqual(training.status, 'cancelled')
        self.assertEqual(importing.status, 'cancelled')

    def test_staff_ops_dashboard_loads(self):
        MLJob.objects.create(job_type='training', status='success', progress_percent=100)

        response = self.client.get(reverse('hello:staff_ops_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'DOLG Ops Dashboard')
        self.assertContains(response, 'MLJob admin')
        self.assertContains(response, 'Runtime')
        self.assertContains(response, 'Live backend')

    def test_staff_data_console_loads(self):
        response = self.client.get(reverse('hello:staff_data_console'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'DOLG Data Console')
        self.assertContains(response, 'Database backend')
        self.assertContains(response, 'Media storage')
        self.assertContains(response, 'JSON fields')

    def test_staff_data_console_filters_and_json_preview(self):
        SchematicProject.objects.create(
            user=self.staff,
            name='Console project',
            scheme_data={'components': [{'id': 'r1', 'type': 'resistor'}], 'connections': []},
        )

        response = self.client.get(
            reverse('hello:staff_data_console'),
            {
                'model_q': 'SchematicProject',
                'table_q': 'schematicproject',
                'json_q': 'scheme_data',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dolg_APP.SchematicProject')
        self.assertContains(response, 'scheme_data')
        self.assertContains(response, 'Console project')
        self.assertContains(response, 'resistor')

    def test_django_admin_index_shows_ops_monitoring(self):
        self.staff.is_superuser = True
        self.staff.save(update_fields=['is_superuser'])

        response = self.client.get(reverse('admin:index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ops-дашборд')
        self.assertContains(response, 'Data-консоль')
        self.assertContains(response, 'Grafana')
        self.assertContains(response, 'Prometheus')

    def test_ops_snapshot_service_contains_core_sections(self):
        MLJob.objects.create(job_type='training', status='success', progress_percent=100)

        snapshot = collect_ops_snapshot(use_cache=False)

        self.assertIn(snapshot['health']['status'], {'ok', 'warning', 'critical'})
        self.assertIn('runtime', snapshot)
        self.assertIn('catalog', snapshot)
        self.assertIn('business', snapshot)
        self.assertIn('projects', snapshot)
        self.assertIn('ai_ml', snapshot)
        self.assertIn('moderation', snapshot)
        self.assertIn('security', snapshot)
        self.assertIn('process', snapshot['runtime'])
        self.assertIn('db', snapshot['runtime'])
        self.assertIn('cache', snapshot['runtime'])
        self.assertIn('runtime', snapshot['ai_ml'])
        self.assertIn(snapshot['ai_ml']['runtime']['backend'], {'ollama', 'rule_based', 'unknown'})
        self.assertIn('pytorch', snapshot['ai_ml']['runtime'])

    def test_staff_ops_snapshot_api_returns_json(self):
        response = self.client.get(reverse('hello:staff_ops_snapshot_api'))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertIn('snapshot', payload)
        self.assertIn('runtime', payload['snapshot'])
        self.assertIn('health', payload['snapshot'])
