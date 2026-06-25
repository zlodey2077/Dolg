"""Tests for the server-side engine router catalog."""

from __future__ import annotations

import json
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from Dolg_APP.models import EngineJob, ProjectEvent, SchematicProject, SimulationRun
from Dolg_APP.services.engine_ai import plan_engine_action
from Dolg_APP.services.engine_jobs import mark_stale_engine_jobs, run_due_engine_jobs
from Dolg_APP.services.server_engines import (
    recommend_server_engines,
    server_engine_ids,
    server_engine_payload,
)


def _rf_scheme():
    return {
        'components': [
            {'id': 'V1', 'type': 'battery', 'voltage': 1},
            {'id': 'R1', 'type': 'resistor', 'resistance': '50'},
            {'id': 'C1', 'type': 'capacitor', 'capacitance': '100n', 'label': 'RF filter'},
        ],
        'connections': [],
    }


def _divider_scheme():
    return {
        'components': [
            {'id': 'V1', 'type': 'battery', 'voltage': 10},
            {'id': 'R1', 'type': 'resistor', 'resistance': 1000},
            {'id': 'R2', 'type': 'resistor', 'resistance': 1000},
            {'id': 'GND', 'type': 'ground', 'ports': [{'id': '1'}]},
        ],
        'connections': [
            {'from': {'compId': 'V1', 'portId': '2'}, 'to': {'compId': 'GND', 'portId': '1'}},
            {'from': {'compId': 'V1', 'portId': '1'}, 'to': {'compId': 'R1', 'portId': '1'}},
            {'from': {'compId': 'R1', 'portId': '2'}, 'to': {'compId': 'R2', 'portId': '1'}},
            {'from': {'compId': 'R2', 'portId': '2'}, 'to': {'compId': 'GND', 'portId': '1'}},
        ],
    }


class ServerEngineCatalogTests(SimpleTestCase):
    def test_catalog_has_xyce_pyspice_and_router_profile(self):
        payload = server_engine_payload()
        engine_ids = {engine['id'] for engine in payload['engines']}
        self.assertIn('dolg-engine-router', engine_ids)
        self.assertIn('xyce', engine_ids)
        self.assertIn('pyspice', engine_ids)
        self.assertEqual(payload['router_profile']['primary_engine'], 'dolg-engine-router')
        self.assertEqual(payload['router_profile']['primary_external_engine'], 'xyce')
        self.assertIn('xyce-worker', payload['router_profile']['docker_services'])

    def test_xyce_is_primary_candidate(self):
        payload = server_engine_payload()
        xyce = next(engine for engine in payload['engines'] if engine['id'] == 'xyce')
        self.assertEqual(xyce['status'], 'primary-candidate')
        self.assertEqual(payload['summary']['primary_candidate'], 'xyce')

    def test_engine_ids_are_stable(self):
        ids = server_engine_ids()
        self.assertIn('xyce', ids)
        self.assertIn('pyspice', ids)
        self.assertIn('dolg-ngspice-wasm', ids)

    def test_recommender_prefers_rf_stack_for_rf_scheme(self):
        recommendations = recommend_server_engines(_rf_scheme(), limit=4)
        ids = [engine['id'] for engine in recommendations]
        self.assertIn('dolg-scikit-rf', ids)
        self.assertIn('xyce', ids)
        self.assertIn('ai_score', recommendations[0])

    def test_local_ai_plans_text_command_for_engine_job(self):
        plan = plan_engine_action('Прогони transient через pyspice 5 ms', scheme_data=_divider_scheme())

        self.assertTrue(plan['ok'])
        self.assertEqual(plan['intent'], 'queue_engine_job')
        self.assertEqual(plan['command']['engine_id'], 'pyspice')
        self.assertEqual(plan['command']['analysis_type'], 'transient')
        self.assertEqual(plan['job_payload']['source'], 'local_ai_command_planner')
        self.assertIn('explanation', plan)


@override_settings(ALLOWED_HOSTS=['*'])
class ServerEngineApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='engineer', password='pass')

    def test_catalog_api_is_public(self):
        response = self.client.get('/api/sim/server-engines/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['router_profile']['primary_engine'], 'dolg-engine-router')

    def test_recommend_api_accepts_in_memory_scheme(self):
        response = self.client.post(
            '/api/sim/server-engines/recommend/',
            data=json.dumps(
                {
                    'scheme_data': _rf_scheme(),
                    'limit': 3,
                    'message': 'Подбери движок для RF AC sweep',
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertLessEqual(len(data['engines']), 3)
        self.assertIn('xyce', data['router_profile']['fallback_order'])
        self.assertEqual(data['action_plan']['command']['analysis_type'], 'ac')
        self.assertIn('job_payload', data['action_plan'])

    def test_engine_job_submit_creates_queued_record(self):
        self.client.force_login(self.user)
        response = self.client.post(
            '/api/sim/jobs/',
            data=json.dumps(
                {
                    'engine_id': 'xyce',
                    'analysis_type': 'tran',
                    'netlist': '* demo\n.tran 1u 1m\n.end',
                    'scheme_data': _rf_scheme(),
                    'options': {'timeout_s': 30},
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['job']['engine_id'], 'xyce')
        self.assertEqual(data['job']['status'], 'queued')
        self.assertEqual(EngineJob.objects.count(), 1)
        job = EngineJob.objects.get()
        self.assertEqual(job.user, self.user)
        self.assertEqual(job.analysis_type, 'tran')
        self.assertEqual(job.reason, 'queued')
        self.assertEqual(job.max_retries, 2)
        self.assertEqual(job.audit_log[0]['action'], 'queued')
        self.assertIn('xyce', data['router_profile']['fallback_order'])

    def test_engine_job_submit_accepts_text_command(self):
        self.client.force_login(self.user)
        response = self.client.post(
            '/api/sim/jobs/',
            data=json.dumps(
                {
                    'command_text': 'Прогони DC через локальный numpy',
                    'scheme_data': _divider_scheme(),
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['job']['engine_id'], 'dolg-numpy-mna')
        self.assertEqual(data['job']['analysis_type'], 'dc')
        job = EngineJob.objects.get(pk=data['job']['id'])
        self.assertTrue(job.input_payload['ai_command_plan']['ok'])

    def test_engine_job_detail_and_pending_result(self):
        self.client.force_login(self.user)
        job = EngineJob.objects.create(
            user=self.user, engine_id='xyce', engine_name='Xyce', analysis_type='dc'
        )

        detail = self.client.get(f'/api/sim/jobs/{job.id}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()['job']['id'], job.id)

        result = self.client.get(f'/api/sim/jobs/{job.id}/result/')
        self.assertEqual(result.status_code, 202)
        data = result.json()
        self.assertFalse(data['ok'])
        self.assertTrue(data['pending'])

    def test_engine_job_list_is_user_scoped(self):
        other = get_user_model().objects.create_user(username='other', password='pass')
        EngineJob.objects.create(user=self.user, engine_id='xyce', engine_name='Xyce')
        EngineJob.objects.create(user=other, engine_id='pyspice', engine_name='PySpice')
        self.client.force_login(self.user)

        response = self.client.get('/api/sim/jobs/')
        self.assertEqual(response.status_code, 200)
        jobs = response.json()['jobs']
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['engine_id'], 'xyce')

    def test_engine_job_rejects_unknown_engine(self):
        self.client.force_login(self.user)
        response = self.client.post(
            '/api/sim/jobs/',
            data=json.dumps({'engine_id': 'not-a-real-engine'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['ok'])

    def test_local_numpy_worker_processes_dc_job(self):
        job = EngineJob.objects.create(
            user=self.user,
            engine_id='dolg-numpy-mna',
            engine_name='NumPy MNA',
            analysis_type='dc',
            scheme_data=_divider_scheme(),
        )

        outcome = run_due_engine_jobs(limit=1, worker_id='pytest-worker')

        self.assertEqual(outcome['processed'], 1)
        job.refresh_from_db()
        self.assertEqual(job.status, 'success')
        self.assertEqual(job.worker, 'pytest-worker')
        self.assertEqual(job.progress_percent, 100)
        self.assertTrue(job.result['ok'])
        self.assertEqual(job.result['analysis_type'], 'dc')
        self.assertIn('local_ai', job.result)
        self.assertTrue(job.result['metrics']['local_ai_attached'])
        voltages = [float(value) for value in job.result['node_voltages'].values()]
        self.assertTrue(any(abs(value - 5.0) < 1e-6 for value in voltages))
        self.assertEqual(job.result['contract']['kind'], 'dolg.engine.result')
        self.assertEqual(job.result['contract']['version'], 1)
        self.assertTrue(any(item['action'] == 'success' for item in job.audit_log))

    def test_local_engine_router_delegates_to_numpy_mna(self):
        job = EngineJob.objects.create(
            user=self.user,
            engine_id='dolg-engine-router',
            engine_name='DOLG Engine Router',
            analysis_type='dc',
            scheme_data=_divider_scheme(),
        )

        outcome = run_due_engine_jobs(limit=1, worker_id='pytest-router')

        self.assertEqual(outcome['processed'], 1)
        job.refresh_from_db()
        self.assertEqual(job.status, 'success')
        self.assertEqual(job.worker, 'pytest-router')
        self.assertEqual(job.result['contract']['kind'], 'dolg.engine.result')
        self.assertEqual(job.result['engine_router']['delegated_engine'], 'dolg-numpy-mna')
        self.assertEqual(job.result['metrics']['router_engine'], 'dolg-engine-router')
        self.assertTrue(any(item.get('kind') == 'route' for item in job.artifacts))

    def test_mark_stale_engine_jobs_uses_heartbeat(self):
        old = timezone.now() - timezone.timedelta(minutes=10)
        job = EngineJob.objects.create(
            user=self.user,
            engine_id='dolg-engine-router',
            engine_name='DOLG Engine Router',
            analysis_type='dc',
            status='running',
            progress_percent=50,
            started_at=old,
            heartbeat_at=old,
            worker='lost-worker',
        )

        outcome = mark_stale_engine_jobs(max_age_seconds=60, actor='pytest-stale')

        self.assertEqual(outcome['marked'], 1)
        job.refresh_from_db()
        self.assertEqual(job.status, 'stale')
        self.assertIn('Heartbeat stale', job.reason)
        self.assertTrue(any(item['action'] == 'stale' for item in job.audit_log))

    def test_retry_endpoint_requeues_terminal_job(self):
        self.client.force_login(self.user)
        job = EngineJob.objects.create(
            user=self.user,
            engine_id='dolg-engine-router',
            engine_name='DOLG Engine Router',
            analysis_type='dc',
            status='error',
            progress_percent=100,
            reason='adapter failed',
            error='adapter failed',
            retry_count=0,
            max_retries=2,
        )

        response = self.client.post(
            f'/api/sim/jobs/{job.id}/retry/',
            data=json.dumps({'reason': 'try router again'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertTrue(data['ok'])
        job.refresh_from_db()
        self.assertEqual(job.status, 'queued')
        self.assertEqual(job.retry_count, 1)
        self.assertEqual(job.reason, 'try router again')
        self.assertEqual(job.error, '')
        self.assertTrue(any(item['action'] == 'retry' for item in job.audit_log))

    def test_local_worker_persists_project_simulation_run(self):
        project = SchematicProject.objects.create(
            user=self.user,
            name='Engine project',
            scheme_data=_divider_scheme(),
        )
        job = EngineJob.objects.create(
            project=project,
            user=self.user,
            engine_id='dolg-numpy-mna',
            engine_name='NumPy MNA',
            analysis_type='dc',
            scheme_data=_divider_scheme(),
        )

        outcome = run_due_engine_jobs(limit=1, worker_id='pytest-worker')

        self.assertEqual(outcome['processed'], 1)
        job.refresh_from_db()
        self.assertEqual(job.status, 'success')
        run = SimulationRun.objects.get()
        self.assertEqual(run.project, project)
        self.assertEqual(run.user, self.user)
        self.assertEqual(run.analysis_type, 'dc')
        self.assertEqual(run.engine, 'dolg-numpy-mna')
        self.assertEqual(run.status, 'success')
        self.assertEqual(run.result_summary['type'], 'dc')
        self.assertEqual(run.result_summary['node_count'], job.result['metrics']['node_count'])
        self.assertIn('node_voltages', run.result_data)
        event = ProjectEvent.objects.get(event_type='simulation_run')
        self.assertEqual(event.payload['engine_job_id'], job.id)
        self.assertEqual(event.payload['run_id'], run.id)

    def test_local_worker_leaves_external_engine_queued_by_default(self):
        job = EngineJob.objects.create(
            user=self.user,
            engine_id='xyce',
            engine_name='Xyce',
            analysis_type='dc',
            scheme_data=_divider_scheme(),
        )

        outcome = run_due_engine_jobs(limit=1, worker_id='pytest-worker')

        self.assertEqual(outcome['processed'], 0)
        job.refresh_from_db()
        self.assertEqual(job.status, 'queued')

    def test_external_engine_errors_when_explicitly_claimed_without_adapter(self):
        job = EngineJob.objects.create(
            user=self.user,
            engine_id='xyce',
            engine_name='Xyce',
            analysis_type='dc',
            scheme_data=_divider_scheme(),
        )

        outcome = run_due_engine_jobs(limit=1, worker_id='pytest-worker', engine_ids=['xyce'])

        self.assertEqual(outcome['processed'], 1)
        job.refresh_from_db()
        self.assertEqual(job.status, 'error')
        self.assertIn('No local adapter', job.error)

    def test_management_command_runs_one_worker_pass(self):
        job = EngineJob.objects.create(
            user=self.user,
            engine_id='dolg-numpy-mna',
            engine_name='NumPy MNA',
            analysis_type='dc',
            scheme_data=_divider_scheme(),
        )
        output = StringIO()

        call_command(
            'run_engine_worker', '--once', '--limit', '1', '--worker-id', 'pytest-cmd', stdout=output
        )

        job.refresh_from_db()
        self.assertEqual(job.status, 'success')
        self.assertIn('processed=1', output.getvalue())
