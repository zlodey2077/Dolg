"""Smoke-suite для Dolg_APP — критичные пути и регрессионные сцены.

Покрытие тонкое (≈25 тестов на 6 направлений), но защищает от worst-case:
- HealthCheck не падает при моргании БД
- AIError-иерархия отдаёт правильный exit-code пользователю
- Проекты не утекают между юзерами (ownership)
- PCB layout строит валидный bbox
- Demo-проекты загружаются командой и не дублируются

Используется FAST_TESTS=1 для пропуска миграций (см. settings.IS_TESTING).
"""

import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from Dolg_APP.ml.neural import (
    FEATURE_DIM,
    compare_prediction_to_teacher,
    scheme_to_features,
    teacher_baseline,
)
from Dolg_APP.models import (
    AITrainingExample,
    EngineeringArtifact,
    ProjectEvent,
    ProjectMeasurement,
    ProjectReview,
    SchematicProject,
    SimulationRun,
    Subscription,
)
from Dolg_APP.pcb_layout import compute_pcb_layout, to_gerber_drill, to_gerber_top_copper
from Dolg_APP.services.cad_import import (
    import_eagle_xml,
    import_kicad_sexpr,
    import_preview,
    import_schematic_auto,
)
from Dolg_APP.services.constraint_solver import solve_design_constraints
from Dolg_APP.services.engineering_units import parse_engineering_quantity
from Dolg_APP.services.expert_rules import build_expert_facts, evaluate_expert_rules, load_rule_pack
from Dolg_APP.services.learning_by_review import learning_suggestions_from_review
from Dolg_APP.services.project_review import build_design_review
from Dolg_APP.services.risk_scoring import assess_fuzzy_project_risk
from Dolg_APP.services.rule_ai import build_ai_scheme_context, build_rule_based_reply
from Dolg_APP.services.schematic_graph import analyze_graph_topology
from Dolg_APP.services.simulation_analysis import (
    bode_plot,
    fft_spectrum,
    monte_carlo_tolerance,
    parameter_sweep,
    postprocess_simulation,
    server_side_dc_fallback,
    signal_quality,
    simulation_result_to_csv,
)
from knowledge.models import LearningLesson, LearningTrack

User = get_user_model()


class HealthzTests(TestCase):
    """healthz/ — k8s liveness/readiness; не должен лезть в БД."""

    def test_healthz_returns_200(self):
        resp = self.client.get('/healthz/')
        self.assertEqual(resp.status_code, 200)

    def test_healthz_no_db_query(self):
        # healthz должен отвечать даже при невалидной БД-конфигурации.
        # Проверяем что не лезет в auth_user (1 query допустим — auth middleware).
        with self.assertNumQueries(0):
            self.client.get('/healthz/')


class AIAssistantModuleTests(TestCase):
    """Модуль ai_assistant — конфиг агентов, иерархия исключений, fallback."""

    def test_ai_disabled_without_key(self):
        from django.test import override_settings

        from Dolg_APP import ai_assistant

        with override_settings(ANTHROPIC_API_KEY=''):
            self.assertFalse(ai_assistant.is_enabled())

    def test_agent_profiles_have_required_fields(self):
        from Dolg_APP.ai_assistant import AGENT_PROFILES

        self.assertIn('recommend', AGENT_PROFILES)
        for name, profile in AGENT_PROFILES.items():
            # Структура: title/model/temperature/max_tokens/persona/guidelines
            self.assertIn('persona', profile, f'{name} no persona')
            self.assertIn('temperature', profile, f'{name} no temperature')
            self.assertIn('model', profile, f'{name} no model')

    def test_error_hierarchy(self):
        from Dolg_APP.ai_assistant import (
            AIAuthError,
            AIError,
            AIRateLimitError,
            AIServerError,
        )

        self.assertTrue(issubclass(AIAuthError, AIError))
        self.assertTrue(issubclass(AIRateLimitError, AIError))
        self.assertTrue(issubclass(AIServerError, AIError))


class ProjectsOwnershipTests(TestCase):
    """Проверка изоляции: пользователь A не видит/не редактирует проекты B."""

    def setUp(self):
        self.alice = User.objects.create_user('alice', 'a@x', 'pw1')
        self.bob = User.objects.create_user('bob', 'b@x', 'pw2')
        self.alice_proj = SchematicProject.objects.create(
            user=self.alice, name='Alice scheme', scheme_data={'components': []}
        )
        self.client = Client()

    def test_alice_can_load_own_project(self):
        self.client.force_login(self.alice)
        resp = self.client.get(f'/projects/api/{self.alice_proj.id}/load-scheme/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['project']['name'], 'Alice scheme')

    def test_bob_cannot_load_alice_project(self):
        self.client.force_login(self.bob)
        resp = self.client.get(f'/projects/api/{self.alice_proj.id}/load-scheme/')
        # 404 (not visible), не 403 — не подтверждаем существование чужого проекта.
        self.assertEqual(resp.status_code, 404)

    def test_unauthenticated_redirects_to_login(self):
        resp = self.client.get(f'/projects/api/{self.alice_proj.id}/load-scheme/')
        # @login_required → redirect 302 на login URL
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login', resp.url)


class ProjectsCreateUpdateTests(TestCase):
    """Создание / переименование / удаление проекта через API."""

    def setUp(self):
        self.user = User.objects.create_user('u', 'u@x', 'pw')
        self.client.force_login(self.user)

    def test_create_project_via_api(self):
        resp = self.client.post(
            '/projects/api/create/',
            data=json.dumps({'name': 'Test scheme', 'category': 'led', 'scheme_data': {'components': []}}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(SchematicProject.objects.filter(user=self.user, name='Test scheme').exists())

    def test_rename_project(self):
        proj = SchematicProject.objects.create(user=self.user, name='Old name')
        resp = self.client.post(
            f'/projects/api/{proj.id}/update/',
            data=json.dumps({'name': 'New name'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        proj.refresh_from_db()
        self.assertEqual(proj.name, 'New name')

    def test_delete_project(self):
        proj = SchematicProject.objects.create(user=self.user, name='To delete')
        resp = self.client.post(f'/projects/api/{proj.id}/delete/')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(SchematicProject.objects.filter(id=proj.id).exists())


class PCBLayoutTests(TestCase):
    """Чистый алгоритмический модуль pcb_layout.py — без БД, без сети."""

    def _basic_scheme(self):
        return {
            'components': [
                {'id': 1, 'type': 'resistor', 'x': 100, 'y': 100, 'rotation': 0},
                {'id': 2, 'type': 'led', 'x': 300, 'y': 100, 'rotation': 0},
                {'id': 3, 'type': 'battery', 'x': 200, 'y': 300, 'rotation': 0},
            ],
            'connections': [
                {'from': {'compId': 1, 'portId': 'b'}, 'to': {'compId': 2, 'portId': 'a'}},
            ],
        }

    def test_compute_layout_returns_dict(self):
        layout = compute_pcb_layout(self._basic_scheme())
        self.assertIsInstance(layout, dict)
        self.assertIn('comps', layout)
        self.assertIn('pads', layout)
        self.assertIn('pcb_w_mm', layout)

    def test_layout_bbox_positive(self):
        layout = compute_pcb_layout(self._basic_scheme())
        self.assertGreater(layout['pcb_w_mm'], 0)
        self.assertGreater(layout['pcb_h_mm'], 0)

    def test_layout_places_all_components(self):
        scheme = self._basic_scheme()
        layout = compute_pcb_layout(scheme)
        self.assertEqual(len(layout['comps']), len(scheme['components']))

    def test_gerber_top_copper_valid_format(self):
        layout = compute_pcb_layout(self._basic_scheme())
        gerber = to_gerber_top_copper(layout)
        # RS-274X должен начинаться с FS (format spec) и кончаться M02*
        self.assertIn('%FS', gerber)
        self.assertIn('M02*', gerber)

    def test_gerber_drill_excellon_format(self):
        layout = compute_pcb_layout(self._basic_scheme())
        drill = to_gerber_drill(layout)
        # Excellon NC drill format: header M48...M30
        self.assertIn('M48', drill)
        self.assertIn('M30', drill)

    def test_layout_empty_scheme_safe(self):
        layout = compute_pcb_layout({'components': [], 'connections': []})
        self.assertEqual(layout['comps'], [])


class DemoProjectsCommandTests(TestCase):
    """populate_demo_projects — массовая загрузка demo-схем в БД."""

    def test_command_runs_without_errors(self):
        User.objects.create_superuser('admin', 'a@x', 'pwd')
        from io import StringIO

        call_command('populate_demo_projects', '--owner=admin', stdout=StringIO())

    def test_command_creates_expected_count(self):
        from Dolg_APP.management.commands.populate_demo_projects import DEMO_PROJECTS

        User.objects.create_superuser('admin', 'a@x', 'pwd')
        from io import StringIO

        call_command('populate_demo_projects', '--owner=admin', stdout=StringIO())
        n = SchematicProject.objects.filter(is_demo=True).count()
        self.assertEqual(n, len(DEMO_PROJECTS))

    def test_demo_projects_have_schemes(self):
        User.objects.create_superuser('admin', 'a@x', 'pwd')
        from io import StringIO

        call_command('populate_demo_projects', '--owner=admin', stdout=StringIO())
        for proj in SchematicProject.objects.filter(is_demo=True):
            self.assertTrue(proj.scheme_data, f'Empty scheme in {proj.name}')
            self.assertIn('components', proj.scheme_data)

    def test_idempotent_second_run(self):
        User.objects.create_superuser('admin', 'a@x', 'pwd')
        from io import StringIO

        call_command('populate_demo_projects', '--owner=admin', stdout=StringIO())
        first_count = SchematicProject.objects.filter(is_demo=True).count()
        call_command('populate_demo_projects', '--owner=admin', stdout=StringIO())
        second_count = SchematicProject.objects.filter(is_demo=True).count()
        self.assertEqual(first_count, second_count)


class ProdSettingsCheckTests(TestCase):
    """check_prod_settings — сторожевая команда, блокирует кривой деплой."""

    def test_skipped_when_debug_true(self):
        from io import StringIO

        from django.test import override_settings

        # Django test runner ставит DEBUG=False по умолчанию (mimics prod).
        # Принудительно ставим True — проверяем dev-branch команды.
        with override_settings(DEBUG=True):
            out = StringIO()
            call_command('check_prod_settings', stdout=out)
            self.assertIn('skipped', out.getvalue().lower())

    def test_fails_with_default_secret_key(self):
        import os
        from io import StringIO

        from django.test import override_settings

        # При SKIP_PROD_CHECKS=1 команда не sys.exit — удобно тестировать.
        os.environ['SKIP_PROD_CHECKS'] = '1'
        try:
            with override_settings(
                DEBUG=False,
                SECRET_KEY='django-insecure-local-development-key-change-me',
            ):
                out, err = StringIO(), StringIO()
                call_command('check_prod_settings', stdout=out, stderr=err)
                output = out.getvalue() + err.getvalue()
                self.assertIn('SECRET_KEY', output)
        finally:
            os.environ.pop('SKIP_PROD_CHECKS', None)


class SimulationRunModelTests(TestCase):
    """SimulationRun — модель истории запусков."""

    def setUp(self):
        self.user = User.objects.create_user('u', 'u@x', 'pw')
        self.project = SchematicProject.objects.create(user=self.user, name='proj', scheme_data={})

    def test_create_simulation_run(self):
        run = SimulationRun.objects.create(
            project=self.project,
            user=self.user,
            analysis_type='dc',
            elapsed_ms=42,
            result_summary={'V1': 5.0, 'I1': 0.001},
        )
        self.assertEqual(run.analysis_type, 'dc')
        self.assertEqual(run.elapsed_ms, 42)
        self.assertIsNotNone(run.created_at)

    def test_simulation_run_ordering(self):
        SimulationRun.objects.create(project=self.project, user=self.user, analysis_type='dc')
        SimulationRun.objects.create(project=self.project, user=self.user, analysis_type='ac')
        runs = list(self.project.simulation_runs.all())
        # newest first (default Meta ordering)
        self.assertEqual(runs[0].analysis_type, 'ac')

    def test_async_status_fields_are_available(self):
        run = SimulationRun.objects.create(
            project=self.project,
            user=self.user,
            analysis_type='tran',
            status='running',
            progress_percent=35,
            message='FFT postprocess queued',
        )

        self.assertEqual(run.status, 'running')
        self.assertEqual(run.progress_percent, 35)
        self.assertEqual(run.message, 'FFT postprocess queued')


class ProjectSessionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('session-user', 'session@x', 'pw')
        Subscription.objects.create(user=self.user, tier='pro', status='active')
        self.client.force_login(self.user)
        self.scheme = {
            'components': [
                {'id': 'v1', 'type': 'battery', 'label': 'V1', 'voltage': '5V'},
                {'id': 'r1', 'type': 'resistor', 'label': 'R1', 'resistance': '1k'},
                {'id': 'gnd', 'type': 'ground', 'label': 'GND'},
            ],
            'connections': [
                {'from': {'compId': 'v1', 'portId': 'p'}, 'to': {'compId': 'r1', 'portId': 'a'}},
                {'from': {'compId': 'r1', 'portId': 'b'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            ],
        }
        self.project = SchematicProject.objects.create(
            user=self.user,
            name='Session demo',
            scheme_data=self.scheme,
        )

    def test_scheme_save_logs_project_event_and_dashboard_returns_session(self):
        response = self.client.post(
            reverse('hello:api_project_save_scheme', args=[self.project.id]),
            data=json.dumps({'scheme_data': self.scheme, 'change_note': 'session checkpoint'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        event = ProjectEvent.objects.get(project=self.project, event_type='scheme_saved')
        self.assertEqual(event.payload['components'], 3)

        dashboard = self.client.get(reverse('hello:api_project_dashboard', args=[self.project.id]))
        self.assertEqual(dashboard.status_code, 200)
        data = dashboard.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['project']['events_count'], 1)
        self.assertEqual(data['versions'][0]['change_note'], 'session checkpoint')
        self.assertEqual(data['events'][0]['event_type'], 'scheme_saved')

    def test_simulation_save_postprocess_and_csv_export_are_session_events(self):
        save_response = self.client.post(
            reverse('hello:api_project_save_simulation', args=[self.project.id]),
            data=json.dumps(
                {
                    'analysis_type': 'tran',
                    'engine': 'browser-ngspice',
                    'elapsed_ms': 12,
                    'result': {
                        'points': [{'x': 0, 'y': 0}, {'x': 0.001, 'y': 1}, {'x': 0.002, 'y': 0}],
                        'sample_rate_hz': 1000,
                    },
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(save_response.status_code, 200)
        run_id = save_response.json()['run']['id']

        post_response = self.client.post(
            reverse('hello:api_project_simulation_postprocess', args=[self.project.id]),
            data=json.dumps(
                {
                    'run_id': run_id,
                    'operations': ['fft'],
                    'unit': 'V',
                    'formulas': ['rms * 2'],
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(post_response.status_code, 200)
        post_data = post_response.json()
        self.assertTrue(post_data['ok'])
        self.assertGreaterEqual(len(post_data['measurements']), 3)
        self.assertEqual(
            ProjectMeasurement.objects.filter(project=self.project, source='postprocess').count(), 3
        )

        csv_response = self.client.get(
            reverse('hello:api_project_simulation_export_csv', args=[self.project.id, run_id])
        )
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn('x,y', csv_response.content.decode('utf-8'))
        self.assertGreaterEqual(ProjectEvent.objects.filter(project=self.project).count(), 3)


class EngineeringReviewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('reviewer', 'r@x', 'pw')
        Subscription.objects.create(user=self.user, tier='pro', status='active')
        self.client.force_login(self.user)
        self.scheme = {
            'components': [
                {'id': 'v1', 'type': 'battery', 'label': 'V1', 'voltage': '9V'},
                {'id': 'r1', 'type': 'resistor', 'label': 'R1', 'resistance': '1k', 'rated_power_w': 0.25},
                {'id': 'led1', 'type': 'led', 'label': 'LED1'},
                {'id': 'gnd', 'type': 'ground', 'label': 'GND'},
            ],
            'connections': [
                {'from': {'compId': 'v1', 'portId': 'p'}, 'to': {'compId': 'r1', 'portId': 'a'}},
                {'from': {'compId': 'r1', 'portId': 'b'}, 'to': {'compId': 'led1', 'portId': 'a'}},
                {'from': {'compId': 'led1', 'portId': 'k'}, 'to': {'compId': 'gnd', 'portId': 'a'}},
            ],
        }
        self.project = SchematicProject.objects.create(
            user=self.user,
            name='Review LED',
            scheme_data=self.scheme,
        )

    def _seed_diagnostics_lesson(self):
        track = LearningTrack.objects.create(
            title='Диагностика простых схем',
            slug='diagnostika-prostyh-shem',
            summary='Практика поиска типовых ошибок.',
            level='basic',
            order=1,
            is_published=True,
        )
        return LearningLesson.objects.create(
            track=track,
            title='Нет GND и плавающие узлы',
            slug='diagnostics-no-ground',
            summary='Как исправить схему без опорной точки.',
            theory='Добавьте GND и повторите review.',
            formula='',
            order=1,
            is_published=True,
        )

    def test_build_design_review_detects_missing_ground_fault(self):
        project = SchematicProject(
            name='No GND',
            scheme_data={
                'components': [
                    {'id': 'v1', 'type': 'battery', 'voltage': '5V'},
                    {'id': 'r1', 'type': 'resistor', 'resistance': '1k'},
                ],
                'connections': [
                    {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
                ],
            },
        )

        review = build_design_review(project, simulation_runs=[], measurements=[])

        self.assertEqual(review['status'], 'critical')
        self.assertTrue(any(item['code'] == 'missing_ground' for item in review['faults']))

    def test_design_validity_guard_warns_when_rating_is_exceeded(self):
        project = SchematicProject(
            name='Overloaded resistor',
            scheme_data={
                'components': [
                    {'id': 'v1', 'type': 'battery', 'voltage': '12V'},
                    {
                        'id': 'r1',
                        'type': 'resistor',
                        'label': 'R1',
                        'resistance': '100',
                        'rated_power_w': 0.25,
                        'measured_power_w': 0.4,
                    },
                    {'id': 'gnd', 'type': 'ground', 'label': 'GND'},
                ],
                'connections': [
                    {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
                    {'from': {'compId': 'r1'}, 'to': {'compId': 'gnd'}},
                ],
            },
        )

        review = build_design_review(project, simulation_runs=[], measurements=[])

        validity = review['sections']['validity']
        self.assertEqual(validity['metrics']['out_of_range'], 1)
        self.assertTrue(validity['issues'])
        self.assertIn('validity_issues', review['metrics'])

    def test_design_review_user_messages_are_localized_to_russian(self):
        project = SchematicProject(
            name='No GND localized',
            scheme_data={
                'components': [
                    {'id': 'v1', 'type': 'battery', 'voltage': '5V'},
                    {'id': 'r1', 'type': 'resistor', 'resistance': '1k'},
                ],
                'connections': [
                    {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
                ],
            },
        )

        review = build_design_review(project, simulation_runs=[], measurements=[])
        combined = ' '.join(review['errors'] + review['warnings'] + review['recommendations'])
        finding = next(item for item in review['expert_findings'] if item['rule_id'] == 'erc.missing_ground')

        self.assertEqual(review['status_label'], 'критично')
        self.assertIn('Нет опорного узла GND', combined)
        self.assertNotIn('Add a GND/reference node', combined)
        self.assertIn('Добавьте GND', finding['recommendation'])
        self.assertEqual(finding['severity_label'], 'ошибка')

    def test_review_api_saves_snapshot_and_returns_report_url(self):
        response = self.client.post(
            reverse('hello:api_project_review_create', args=[self.project.id]),
            data=json.dumps({}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertIn('/projects/review/', data['review']['url'])
        self.assertEqual(ProjectReview.objects.filter(project=self.project).count(), 1)

    def test_learning_by_review_suggests_diagnostics_lesson(self):
        lesson = self._seed_diagnostics_lesson()
        project = SchematicProject.objects.create(
            user=self.user,
            name='No GND training case',
            scheme_data={
                'components': [
                    {'id': 'v1', 'type': 'battery', 'voltage': '5V'},
                    {'id': 'r1', 'type': 'resistor', 'resistance': '1k'},
                ],
                'connections': [
                    {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
                ],
            },
        )
        report = build_design_review(project, simulation_runs=[], measurements=[])

        suggestions = learning_suggestions_from_review(report)

        self.assertTrue(any(item['lesson_slug'] == lesson.slug for item in suggestions))

    def test_review_page_and_pdf_are_available_to_owner(self):
        response = self.client.post(
            reverse('hello:api_project_review_create', args=[self.project.id]),
            data=json.dumps({}),
            content_type='application/json',
        )
        review_id = response.json()['review']['id']

        page = self.client.get(reverse('hello:project_review_page', args=[review_id]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Engineering Review')
        self.assertContains(page, 'review-3d-stage')
        self.assertContains(page, 'review/review-3d.js')
        self.assertContains(page, 'Экспертные правила')
        self.assertContains(page, 'Компоненты')

        pdf = self.client.get(reverse('hello:project_review_pdf', args=[review_id]))
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf['Content-Type'], 'application/pdf')

    def test_review_page_shows_learning_by_review_panel(self):
        self._seed_diagnostics_lesson()
        project = SchematicProject.objects.create(
            user=self.user,
            name='Review without ground',
            scheme_data={
                'components': [
                    {'id': 'v1', 'type': 'battery', 'voltage': '5V'},
                    {'id': 'r1', 'type': 'resistor', 'resistance': '1k'},
                ],
                'connections': [
                    {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
                ],
            },
        )
        response = self.client.post(
            reverse('hello:api_project_review_create', args=[project.id]),
            data=json.dumps({}),
            content_type='application/json',
        )
        review_id = response.json()['review']['id']

        page = self.client.get(reverse('hello:project_review_page', args=[review_id]))

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Learning by Review')
        self.assertContains(page, 'Нет GND')

    def test_measurement_api_saves_expected_vs_measured_status(self):
        response = self.client.post(
            reverse('hello:api_project_measurement_create', args=[self.project.id]),
            data=json.dumps(
                {
                    'metric': 'node_voltage',
                    'label': 'Vout',
                    'value': 3.02,
                    'expected_value': 3.0,
                    'tolerance_abs': 0.1,
                    'unit': 'V',
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['measurement']['status'], 'ok')
        self.assertEqual(ProjectMeasurement.objects.filter(project=self.project).count(), 1)

    def test_generate_protocol_returns_markdown_with_sections(self):
        response = self.client.post(
            reverse('hello:api_generate_protocol'),
            data=json.dumps(
                {
                    'title': 'Протокол LED',
                    'scheme_data': self.scheme,
                    'lab_calcs': [
                        {
                            'ok': True,
                            'title': 'Запас по нагрузке (derating)',
                            'status_label': 'риск',
                            'outputs': {
                                'load_percent': {
                                    'label': 'Загрузка',
                                    'value': 72,
                                    'unit': '%',
                                    'display': '72',
                                }
                            },
                        }
                    ],
                    'findings': [
                        {
                            'rule_id': 'pcb.x',
                            'severity': 'error',
                            'message': 'тест-ошибка',
                            'recommendation': 'починить',
                        }
                    ],
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertIn('# Протокол LED', data['markdown'])
        self.assertIn('Состав схемы', data['sections'])
        self.assertIn('Инженерные расчёты', data['sections'])
        self.assertIn('тест-ошибка', data['markdown'])

    def test_generate_protocol_download_returns_markdown_file(self):
        response = self.client.post(
            reverse('hello:api_generate_protocol'),
            data=json.dumps({'title': 'Скачать', 'scheme_data': self.scheme, 'download': True}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/markdown', response['Content-Type'])
        self.assertIn('attachment', response['Content-Disposition'])

    def test_cad_import_preview_parses_spice_subset(self):
        source = 'V1 in 0 DC 9\nR1 in out 1k\nR2 out 0 2k\n.ac dec 10 1 1k'
        result = import_preview('ltspice', source)

        self.assertTrue(result['ok'])
        types = {item['type'] for item in result['scheme_data']['components']}
        self.assertIn('battery', types)
        self.assertIn('resistor', types)
        self.assertIn('ground', types)
        self.assertEqual(result['preview']['component_count'], 3)
        self.assertIn('.ac dec 10 1 1k', result['preview']['analysis_directives'])

    def test_cad_import_kicad8_sexpr_extracts_instances(self):
        # KiCad 8 eeschema: инстансы (symbol (lib_id ...)), определения в
        # (lib_symbols ...) — их парсер игнорирует. Power-порт #PWR → ground.
        source = (
            '(kicad_sch (version 20231120) (generator "eeschema")\n'
            '  (lib_symbols\n'
            '    (symbol "Device:R" (property "Reference" "R")\n'
            '      (symbol "R_0_1" (rectangle (start 0 0) (end 1 1))))\n'
            '    (symbol "Device:C" (property "Reference" "C")))\n'
            '  (symbol (lib_id "Device:R") (at 50 50 0)\n'
            '    (property "Reference" "R1") (property "Value" "10k"))\n'
            '  (symbol (lib_id "Device:C") (at 80 50 0)\n'
            '    (property "Reference" "C1") (property "Value" "100n"))\n'
            '  (symbol (lib_id "power:GND") (at 50 90 0)\n'
            '    (property "Reference" "#PWR01") (property "Value" "GND"))\n'
            ')'
        )
        result = import_kicad_sexpr(source)
        self.assertTrue(result['ok'])
        comps = {
            c['label']: c['type'] for c in result['scheme_data']['components'] if c.get('type') != 'node'
        }
        # Извлечены ровно 3 инстанса, а не определения из lib_symbols.
        self.assertEqual(set(comps), {'R1', 'C1', '#PWR01'})
        self.assertEqual(comps['R1'], 'resistor')
        self.assertEqual(comps['C1'], 'capacitor')
        self.assertEqual(comps['#PWR01'], 'ground')  # power-порт, не ic

    def test_cad_import_kicad_sexpr_empty_when_no_instances(self):
        result = import_kicad_sexpr('(kicad_sch (version 20231120) (lib_symbols))')
        self.assertFalse(result['ok'])
        self.assertEqual(result['summary']['components'], 0)

    def test_cad_import_eagle_xml_extracts_parts_and_nets(self):
        # EAGLE .sch: parts → компоненты, net/pinref → соединения. Рамка FRAME — не компонент.
        source = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<!DOCTYPE eagle SYSTEM "eagle.dtd">\n'
            '<eagle version="9.6.2"><drawing><schematic><parts>\n'
            '  <part name="FRAME1" library="frames" deviceset="FRAME_A4" device=""/>\n'
            '  <part name="R1" library="rcl" deviceset="R-EU_0207" device="" value="10k"/>\n'
            '  <part name="C1" library="rcl" deviceset="C-EU" device="" value="100n"/>\n'
            '  <part name="GND1" library="supply" deviceset="GND" device=""/>\n'
            '</parts><sheets><sheet><nets>\n'
            '  <net name="N$1" class="0"><segment>\n'
            '    <pinref part="R1" pin="2"/><pinref part="C1" pin="1"/>\n'
            '  </segment></net>\n'
            '  <net name="GND" class="0"><segment>\n'
            '    <pinref part="C1" pin="2"/><pinref part="GND1" pin="GND"/>\n'
            '  </segment></net>\n'
            '</nets></sheet></sheets></schematic></drawing></eagle>'
        )
        result = import_eagle_xml(source)
        self.assertTrue(result['ok'])
        comps = {
            c['label']: c['type'] for c in result['scheme_data']['components'] if c.get('type') != 'node'
        }
        self.assertEqual(comps.get('R1'), 'resistor')
        self.assertEqual(comps.get('C1'), 'capacitor')
        self.assertEqual(comps.get('GND1'), 'ground')
        self.assertNotIn('FRAME1', comps)  # рамка отброшена
        self.assertTrue(result['scheme_data']['connections'])  # есть соединения из nets

    def test_cad_import_eagle_survives_malformed_xml(self):
        # Сырой & в text не должен ронять парсер (regex, не строгий ET).
        source = (
            '<eagle version="9.6.2"><drawing><schematic><parts>\n'
            '  <part name="R1" deviceset="R" value="1k"/>\n'
            '</parts><sheets><sheet>\n'
            '  <text>Power & Ground rail</text>\n'  # сырой & — ломает strict ET
            '</sheet></sheets></schematic></drawing></eagle>'
        )
        result = import_eagle_xml(source)
        self.assertTrue(result['ok'])
        self.assertEqual(result['summary']['components'], 1)

    def test_cad_import_auto_dispatches_eagle_vs_kicad(self):
        eagle = '<?xml version="1.0"?><!DOCTYPE eagle SYSTEM "eagle.dtd"><eagle version="9.6.2"><drawing><schematic><parts><part name="R1" deviceset="R" value="1k"/></parts></schematic></drawing></eagle>'
        kicad = '(kicad_sch (symbol (lib_id "Device:R") (property "Reference" "R1") (property "Value" "1k")))'
        self.assertEqual(import_schematic_auto(eagle)['format'], 'eagle_xml')
        self.assertEqual(import_schematic_auto(kicad)['format'], 'kicad_sexpr')

    def test_cad_import_api_can_save_project(self):
        self._seed_diagnostics_lesson()
        response = self.client.post(
            reverse('hello:api_cad_import_preview'),
            data=json.dumps(
                {
                    'format': 'ltspice',
                    'source': 'V1 in 0 DC 5\nR1 in 0 1k',
                    'save_project': True,
                    'name': 'Imported divider',
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertIn('project', data)
        self.assertIn('preview', data)
        self.assertIn('saved_review', data)
        self.assertIn('learning_suggestions', data['saved_review'])
        self.assertTrue(SchematicProject.objects.filter(user=self.user, name='Imported divider').exists())

    @override_settings(ANTHROPIC_API_KEY='')
    def test_ai_chat_uses_self_hosted_rule_engine_without_external_key(self):
        response = self.client.post(
            reverse('hello:api_ai_chat'),
            data=json.dumps(
                {
                    'mode': 'explain',
                    'message': 'explain errors and give fix plan',
                    'project_id': self.project.id,
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertTrue(data['self_hosted'])
        # Прежде тут было self.assertIn('Self AI', data['reply']) — но после расширения
        # rule_ai.OPENINGS (38 → 97 шаблонов) prefix «**Self AI:**» опциональный,
        # не во всех ответах. self_hosted=True (выше) уже подтверждает, что ответ
        # сгенерирован self-hosted rule-engine, а не внешним LLM.
        self.assertIn('Следующие действия', data['reply'])
        self.assertTrue(data['usage']['estimated'])
        self.assertGreater(data['usage']['output_tokens'], 0)
        self.assertIn('session_summary', data)
        self.assertIn('context_sources', data)
        self.assertIn('retrieval_context', data)
        self.assertIsInstance(data['quick_actions'][0], dict)

    @override_settings(ANTHROPIC_API_KEY='')
    def test_ai_chat_recommend_without_project_does_not_500(self):
        history = [{'role': 'user', 'content': f'old question {i}'} for i in range(25)]
        response = self.client.post(
            reverse('hello:api_ai_chat'),
            data=json.dumps(
                {
                    'mode': 'recommend',
                    'message': 'Делитель напряжения 12В->5В, ток 10мА',
                    'history': history,
                    'session_summary': 'Последний intent: recommend',
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertTrue(data['self_hosted'])
        self.assertEqual(data['intent'], 'recommend')
        self.assertTrue(data['usage']['estimated'])
        self.assertGreater(data['usage']['input_tokens'], 0)
        self.assertEqual(data['used_context']['history_messages'], 20)

    def test_self_ai_retrieves_local_knowledge_learning_and_catalog_context(self):
        from knowledge.models import Article, KnowledgeCategory, LearningTask
        from shop.models import Category, Product

        knowledge_category = KnowledgeCategory.objects.create(
            name='Retrieval practice',
            slug='retrieval-practice',
            topic='practice',
        )
        Article.objects.create(
            category=knowledge_category,
            title='Voltage divider article',
            slug='voltage-divider-article',
            summary='Voltage divider resistor ratio and output voltage.',
            body='Use Vout = Vin * R2 / (R1 + R2) and verify load current.',
            related_components_note='resistor voltage divider',
        )
        track = LearningTrack.objects.create(
            title='Retrieval learning track',
            slug='retrieval-learning-track',
            summary='Practice with voltage dividers.',
            level='basic',
            is_published=True,
        )
        lesson = LearningLesson.objects.create(
            track=track,
            title='Voltage divider lesson',
            slug='voltage-divider-lesson-retrieval',
            summary='Calculate and measure a divider.',
            theory='Choose R1 and R2, then compare expected and measured Vout.',
            formula='Vout=Vin*R2/(R1+R2)',
            is_published=True,
        )
        LearningTask.objects.create(
            lesson=lesson,
            task_type='math_numeric',
            title='Voltage divider task',
            prompt='Calculate Vout for a voltage divider with resistor values.',
            rubric={'expected_value': 3.0, 'unit': 'V'},
        )
        category = Category.objects.create(name='Retrieval Resistors')
        Product.objects.create(
            category=category,
            name='Vishay 10k divider resistor',
            description='Precision resistor for voltage divider practice.',
            price=1,
            stock=10,
            manufacturer='vishay',
            part_number='VISHAY-10K',
            package_type='SMD 0805',
            parameters={'nominal': '10k', 'tolerance': '1%'},
        )

        result = build_rule_based_reply(
            'voltage divider resistor task',
            mode='explain',
            project=self.project,
        )

        retrieval = result['retrieval_context']
        sources = set(retrieval['sources'])
        self.assertIn('article', sources)
        self.assertIn('learning', sources)
        self.assertIn('catalog', sources)
        self.assertIn('knowledge_base', result['context_sources'])
        self.assertIn('learning_practice', result['context_sources'])
        self.assertIn('catalog_snapshot', result['context_sources'])
        self.assertEqual(result['used_context']['retrieval_items'], len(retrieval['items']))
        self.assertIn('Voltage divider', result['reply'])

    def test_self_ai_answers_gnd_question_from_review_trace(self):
        project = SchematicProject.objects.create(
            user=self.user,
            name='AI no GND',
            scheme_data={
                'components': [
                    {'id': 'v1', 'type': 'battery', 'voltage': '5V'},
                    {'id': 'r1', 'type': 'resistor', 'resistance': '1k'},
                ],
                'connections': [
                    {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
                ],
            },
        )

        result = build_rule_based_reply('почему нужен GND?', mode='explain', project=project)

        self.assertEqual(result['intent'], 'gnd')
        self.assertIn('GND не найден', result['reply'])
        self.assertIn('Добавьте', result['reply'])
        self.assertIn('Опираюсь на', result['reply'])
        self.assertIn('Добавить GND', [item['label'] for item in result['quick_actions']])
        self.assertIn('expert_trace', result['context_sources'])
        self.assertTrue(any(item.startswith('legal_source:') for item in result['context_sources']))

    def test_self_ai_answers_measurement_question_with_saved_metric(self):
        ProjectMeasurement.objects.create(
            project=self.project,
            user=self.user,
            metric='node_voltage',
            label='Vout',
            value=3.02,
            expected_value=3.0,
            tolerance_abs=0.1,
            unit='V',
            status='ok',
        )

        result = build_rule_based_reply(
            'что измерить и как сравнить expected vs measured?', mode='explain', project=self.project
        )

        self.assertEqual(result['intent'], 'measurement')
        self.assertIn('Сохраненные измерения', result['reply'])
        self.assertIn('Vout', result['reply'])
        self.assertIn('Что измерить дальше', result['reply'])

    def test_self_ai_followup_uses_last_intent_and_summary(self):
        result = build_rule_based_reply(
            'а почему?',
            mode='explain',
            project=self.project,
            history=[
                {'role': 'user', 'content': 'что измерить?'},
                {'role': 'assistant', 'content': 'Нужно измерить Vout.'},
            ],
            session_summary='Последний intent: measurement',
            last_intent='measurement',
        )

        self.assertEqual(result['intent'], 'measurement')
        self.assertTrue(result['used_context']['session_summary'])
        self.assertIn('session_summary', result)

    def test_build_ai_scheme_context_for_project(self):
        context = build_ai_scheme_context(project=self.project)

        self.assertEqual(context['topology'], 'led_indicator')
        self.assertTrue(context['facts']['has_ground'])
        self.assertTrue(context['facts']['has_source'])
        self.assertIn('quick_prompts', context)

    def test_ai_context_api_accepts_inline_scheme(self):
        response = self.client.post(
            reverse('hello:api_ai_context'),
            data=json.dumps({'scheme': self.scheme}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['context']['topology'], 'led_indicator')
        self.assertTrue(data['context']['facts']['has_ground'])

    def test_ai_context_api_accepts_project_id(self):
        response = self.client.post(
            reverse('hello:api_ai_context'),
            data=json.dumps({'project_id': self.project.id}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['context']['facts']['components'], 4)

    def test_review_includes_networkx_topology_metrics(self):
        review = build_design_review(self.project, simulation_runs=[], measurements=[])

        self.assertEqual(review['sections']['connectivity']['topology'], 'led_indicator')
        self.assertEqual(review['metrics']['connected_components'], 1)
        self.assertIn('paths_to_ground', review['sections']['connectivity'])

    def test_review_includes_expert_findings_with_evidence(self):
        project = SchematicProject(
            name='Expert no gnd',
            scheme_data={
                'components': [
                    {'id': 'v1', 'type': 'battery', 'voltage': '5V'},
                    {'id': 'r1', 'type': 'resistor', 'resistance': '1k'},
                ],
                'connections': [
                    {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
                ],
            },
        )

        review = build_design_review(project, simulation_runs=[], measurements=[])
        finding = review['expert_findings'][0]

        self.assertEqual(finding['rule_id'], 'erc.missing_ground')
        self.assertIn('has_ground', finding['evidence'])
        self.assertIn('expert_system', review['sections'])
        self.assertIn('expert_risk', review['sections'])


class LightweightLibraryIntegrationTests(TestCase):
    def test_importing_views_does_not_eager_load_scientific_stack(self):
        script = (
            'import os, sys; '
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE','Dolg_PR.settings'); "
            'import django; django.setup(); '
            'import Dolg_APP.views; '
            "bad=[m for m in ('matplotlib','scipy','pandas','z3','skfuzzy','rule_engine','pint','lark') if m in sys.modules]; "
            "print(','.join(bad)); "
            'raise SystemExit(1 if bad else 0)'
        )
        env = os.environ.copy()
        env['DEBUG'] = 'True'
        result = subprocess.run(
            [sys.executable, '-c', script],
            cwd=os.getcwd(),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_importing_views_does_not_eager_load_torch(self):
        script = (
            'import os, sys; '
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE','Dolg_PR.settings'); "
            'import django; django.setup(); '
            'import Dolg_APP.views; '
            "bad='torch' in sys.modules; "
            'print(bad); '
            'raise SystemExit(1 if bad else 0)'
        )
        env = os.environ.copy()
        env['DEBUG'] = 'True'
        result = subprocess.run(
            [sys.executable, '-c', script],
            cwd=os.getcwd(),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_neural_scheme_features_are_fixed_size(self):
        features = scheme_to_features(
            {
                'components': [
                    {'id': 'v1', 'type': 'battery'},
                    {'id': 'r1', 'type': 'resistor'},
                    {'id': 'gnd', 'type': 'ground'},
                ],
                'connections': [
                    {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
                    {'from': {'compId': 'r1'}, 'to': {'compId': 'gnd'}},
                ],
            }
        )

        self.assertEqual(len(features), FEATURE_DIM)
        self.assertTrue(all(isinstance(item, float) for item in features))

    def test_neural_baseline_agreement_payload_is_explainable(self):
        scheme = {
            'components': [
                {'id': 'v1', 'type': 'battery'},
                {'id': 'led1', 'type': 'led'},
                {'id': 'gnd', 'type': 'ground'},
            ],
            'connections': [
                {'from': {'compId': 'v1'}, 'to': {'compId': 'led1'}},
                {'from': {'compId': 'led1'}, 'to': {'compId': 'gnd'}},
            ],
        }
        baseline = teacher_baseline(scheme)
        prediction = {
            'trained': True,
            'topology': baseline['topology'],
            'topology_confidence': 0.86,
            'risk_score': baseline['risk_score'],
            'next_components': [{'component_type': baseline['next_component'], 'confidence': 0.82}],
        }
        comparison = compare_prediction_to_teacher(scheme, prediction)

        self.assertEqual(baseline['next_component'], 'resistor')
        self.assertGreaterEqual(comparison['agreement_score'], 0.9)
        self.assertEqual(comparison['final_control'], 'expert_rules_plus_human')

    def test_ai_training_scores_scheme_quality_and_complexity(self):
        from Dolg_APP.services.ai_training import score_scheme_for_training

        scheme = {
            'components': [
                {'id': 'v1', 'type': 'battery'},
                {'id': 'r1', 'type': 'resistor'},
                {'id': 'r2', 'type': 'resistor'},
                {'id': 'gnd', 'type': 'ground'},
            ],
            'connections': [
                {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
                {'from': {'compId': 'r1'}, 'to': {'compId': 'r2'}},
                {'from': {'compId': 'r2'}, 'to': {'compId': 'gnd'}},
            ],
        }
        score = score_scheme_for_training(scheme)

        self.assertEqual(score['family'], 'voltage_divider')
        self.assertIn(score['complexity_label'], {'basic', 'medium', 'advanced'})
        self.assertGreaterEqual(score['quality_score'], 60)

    def test_ai_training_example_promotes_to_private_project(self):
        from Dolg_APP.services.ai_training import promote_ai_examples_to_projects

        user = get_user_model().objects.create_user('curator', password='x')
        scheme = {
            'components': [
                {'id': 'v1', 'type': 'battery'},
                {'id': 'r1', 'type': 'resistor'},
                {'id': 'r2', 'type': 'resistor'},
                {'id': 'gnd', 'type': 'ground'},
            ],
            'connections': [
                {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
                {'from': {'compId': 'r1'}, 'to': {'compId': 'r2'}},
                {'from': {'compId': 'r2'}, 'to': {'compId': 'gnd'}},
            ],
        }
        example = AITrainingExample.objects.create(
            user=user,
            kind='review_hint',
            prompt='curated divider',
            target='topology=voltage_divider',
            features={'source': 'unit_test', 'scheme_data': scheme},
            is_validated=True,
        )

        result = promote_ai_examples_to_projects(
            owner=user,
            example_ids=[example.id],
            visibility='private',
            min_quality=60,
        )

        self.assertEqual(result['created'], 1)
        project = SchematicProject.objects.get(user=user, name__startswith='AI curated')
        self.assertEqual(project.visibility, 'private')
        self.assertEqual(project.approval_state, 'draft')
        self.assertFalse(project.is_demo)
        self.assertTrue(project.events.filter(event_type='import_finished').exists())
        example.refresh_from_db()
        self.assertEqual(example.features['latest_promoted_project_id'], project.id)

    def test_neural_pipeline_info_is_lazy_and_safe(self):
        from Dolg_APP.ml.pipeline import DolgAIPipeline

        pipeline = DolgAIPipeline(backend='neural')
        info = pipeline.info()

        self.assertIn(info['backend'], {'heuristic', 'neural'})
        self.assertIn('neural', info)
        self.assertIn('torch_available', info['neural'])

    def test_networkx_detects_missing_ground_and_floating_nodes(self):
        scheme = {
            'components': [
                {'id': 'v1', 'type': 'battery'},
                {'id': 'r1', 'type': 'resistor'},
                {'id': 'r2', 'type': 'resistor'},
            ],
            'connections': [
                {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
            ],
        }

        result = analyze_graph_topology(scheme)

        self.assertFalse(result['metrics']['has_ground'])
        self.assertIn('r2', result['metrics']['isolated_components'])
        self.assertTrue(result['metrics']['floating_components'])

    def test_networkx_identifies_voltage_divider_topology(self):
        scheme = {
            'components': [
                {'id': 'v1', 'type': 'battery', 'label': 'Vin'},
                {'id': 'r1', 'type': 'resistor', 'label': 'R1'},
                {'id': 'out', 'type': 'node', 'label': 'Vout'},
                {'id': 'r2', 'type': 'resistor', 'label': 'R2'},
                {'id': 'gnd', 'type': 'ground', 'label': 'GND'},
            ],
            'connections': [
                {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
                {'from': {'compId': 'r1'}, 'to': {'compId': 'out'}},
                {'from': {'compId': 'out'}, 'to': {'compId': 'r2'}},
                {'from': {'compId': 'r2'}, 'to': {'compId': 'gnd'}},
            ],
        }

        result = analyze_graph_topology(scheme)

        self.assertTrue(result['metrics']['is_connected'])
        self.assertEqual(result['metrics']['topology'], 'voltage_divider')
        self.assertTrue(result['metrics']['has_output_node'])


class ArtifactIngestionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('artifact-user', 'artifact@x', 'pw')
        self.project = SchematicProject.objects.create(
            user=self.user,
            name='Artifact review project',
            scheme_data={
                'components': [
                    {'id': 'v1', 'type': 'battery', 'voltage': '5V'},
                    {'id': 'r1', 'type': 'resistor', 'resistance': '1k'},
                    {'id': 'gnd', 'type': 'ground'},
                ],
                'connections': [
                    {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
                    {'from': {'compId': 'r1'}, 'to': {'compId': 'gnd'}},
                ],
            },
        )

    def _write_artifact(self, suffix, content, *, binary=False):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / f'artifact{suffix}'
        if binary:
            path.write_bytes(content)
        else:
            path.write_text(content, encoding='utf-8')
        return path

    def test_pcad_drc_artifact_feeds_review_i18n_and_ai_context(self):
        from Dolg_APP.services.artifact_ingestion import (
            learning_tasks_from_artifact,
            parse_artifact,
            save_artifact_report,
            training_examples_from_artifact,
        )

        path = self._write_artifact(
            '.drc',
            'Error 1 -- Net VCC shorted to net GND at (10,20) R1-1\n'
            '------\n'
            '1 error(s) detected\n'
            '0 warning(s) detected\n',
        )
        report = parse_artifact(path)
        artifact = save_artifact_report(report, project=self.project, user=self.user)

        review = build_design_review(self.project, simulation_runs=[], measurements=[])
        external = review['sections']['external_cad']
        finding = external['findings'][0]
        context = build_ai_scheme_context(project=self.project)
        learning = learning_tasks_from_artifact(report)
        training = training_examples_from_artifact(report)

        self.assertEqual(EngineeringArtifact.objects.count(), 1)
        self.assertEqual(artifact.parser, 'pcad_drc')
        self.assertEqual(external['finding_count'], 1)
        self.assertEqual(finding['rule_id'], 'external.pcad.short')
        self.assertIn('title_ru', finding)
        self.assertIn('recommendation_ru', finding)
        self.assertEqual(review['metrics']['external_cad_findings'], 1)
        self.assertEqual(context['facts']['artifact_count'], 1)
        self.assertEqual(context['facts']['external_cad_findings'], 1)
        self.assertTrue(learning)
        self.assertEqual(training[0]['kind'], 'drc_finding')
        self.assertTrue(
            ProjectEvent.objects.filter(project=self.project, event_type='artifact_ingested').exists()
        )

    def test_pcad_net_and_closed_binary_stubs_are_normalized(self):
        from Dolg_APP.services.artifact_ingestion import parse_artifact

        net = parse_artifact(
            self._write_artifact(
                '.net',
                '[\nR1\n0805\n10k\n]\n[\nC1\n0603\n100n\n]\n(\nVCC\nR1-1\nC1-1\n)\n(\nGND\nR1-2\nC1-2\n)\n',
            )
        )
        dwg = parse_artifact(self._write_artifact('.dwg', b'AC1027 demo dwg metadata only', binary=True))
        ms14 = parse_artifact(self._write_artifact('.ms14', b'Multisim 14 demo payload', binary=True))

        self.assertEqual(net['parser'], 'pcad_net')
        self.assertEqual(net['facts']['cad_artifact']['component_count'], 2)
        self.assertEqual(net['facts']['cad_artifact']['net_count'], 2)
        self.assertEqual(dwg['status'], 'unsupported')
        self.assertTrue(dwg['facts']['cad_artifact']['requires_conversion'])
        self.assertEqual(ms14['status'], 'unsupported')
        self.assertTrue(ms14['facts']['cad_artifact']['requires_conversion'])

    def test_dxf_parser_extracts_layers_and_entities(self):
        import ezdxf

        from Dolg_APP.services.artifact_ingestion import parse_artifact

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'demo.dxf'
            doc = ezdxf.new('R2010')
            doc.modelspace().add_text('R1 10k').set_placement((0, 0))
            doc.modelspace().add_line((0, 0), (10, 0), dxfattribs={'layer': 'NET_VCC'})
            doc.saveas(path)
            report = parse_artifact(path)

        self.assertEqual(report['parser'], 'dxf')
        self.assertEqual(report['artifact_type'], 'cad_drawing')
        self.assertGreaterEqual(report['facts']['cad_artifact']['entity_count'], 2)
        self.assertIn('NET_VCC', report['facts']['cad_artifact']['layers'])


class ExpertSystemLibraryTests(TestCase):
    def test_rule_pack_validation_and_rule_engine_predicate(self):
        rule_pack = load_rule_pack()
        facts = build_expert_facts(
            connectivity={'component_count': 2, 'has_ground': False, 'has_source': True},
            bom={'missing_catalog': []},
            derating={'issues': []},
            measurements=[],
        )
        result = evaluate_expert_rules(facts, rule_pack)

        self.assertTrue(result['ok'])
        self.assertTrue(any(item['rule_id'] == 'erc.missing_ground' for item in result['findings']))

    def test_pint_unit_parser_supports_engineering_suffixes(self):
        parsed = parse_engineering_quantity('10k', expected_unit='ohm')
        current = parse_engineering_quantity('2.5mA', expected_unit='ampere')
        capacitance = parse_engineering_quantity('100n', expected_unit='farad')

        self.assertTrue(parsed.ok)
        self.assertAlmostEqual(parsed.value, 10000)
        self.assertAlmostEqual(current.value, 0.0025)
        self.assertAlmostEqual(capacitance.value, 100e-9)

    def test_z3_solver_finds_voltage_divider_options(self):
        result = solve_design_constraints('voltage_divider', {'vin': 9, 'target_vout': 3})

        self.assertTrue(result['ok'])
        self.assertEqual(result['engine'], 'z3+e12')
        self.assertTrue(result['options'])
        self.assertLessEqual(result['options'][0]['error_percent'], 5)

    def test_lark_spice_parser_keeps_unsupported_directives(self):
        result = import_preview('ltspice', 'V1 in 0 DC 5\nR1 in out 1k\nR2 out 0 2k\n.ac dec 10 1 1k')

        self.assertTrue(result['ok'])
        self.assertEqual(result['summary']['components'], 3)
        self.assertEqual(result['summary']['unsupported'], 1)
        self.assertIn('.ac dec 10 1 1k', result['unsupported'])

    def test_scikit_fuzzy_risk_scores_soft_signals(self):
        result = assess_fuzzy_project_risk(
            thermal_margin_c=10,
            bom_risk_count=2,
            floating_count=1,
            warning_count=3,
        )

        self.assertTrue(result['ok'])
        self.assertEqual(result['engine'], 'scikit-fuzzy')
        self.assertGreater(result['score'], 0)


class SimulationAnalysisLibraryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('pro-sim', 'pro@x', 'pw')
        Subscription.objects.create(user=self.user, tier='pro', status='active')
        self.client.force_login(self.user)

    def test_fft_service_finds_signal_peak(self):
        samples = [math.sin(2 * math.pi * 50 * i / 1000) for i in range(1000)]
        result = fft_spectrum(samples, 1000)

        self.assertTrue(result['ok'])
        self.assertAlmostEqual(result['peak_frequency_hz'], 50, delta=1)
        self.assertIn('<svg', result['svg'])

    def test_bode_service_generates_rc_plot(self):
        result = bode_plot(
            {
                'kind': 'rc_lowpass',
                'resistance_ohm': '10k',
                'capacitance_f': '100n',
                'start_hz': 10,
                'stop_hz': 10000,
            }
        )

        self.assertTrue(result['ok'])
        self.assertIsNotNone(result['cutoff_frequency_hz'])
        self.assertIn('<svg', result['svg'])

    def test_monte_carlo_voltage_divider_returns_statistics(self):
        result = monte_carlo_tolerance(
            {
                'kind': 'voltage_divider',
                'vin': 9,
                'r1_ohm': '1k',
                'r2_ohm': '2k',
                'samples': 250,
            }
        )

        self.assertTrue(result['ok'])
        self.assertAlmostEqual(result['mean'], 6, delta=0.4)
        self.assertIn('<svg', result['svg'])

    def test_signal_quality_returns_distortion_metrics(self):
        samples = [
            math.sin(2 * math.pi * 50 * i / 1000) + 0.05 * math.sin(2 * math.pi * 150 * i / 1000)
            for i in range(1000)
        ]
        result = signal_quality(samples, 1000)

        self.assertTrue(result['ok'])
        self.assertAlmostEqual(result['fundamental_frequency_hz'], 50, delta=1)
        self.assertGreater(result['thd_percent'], 1)
        self.assertIn('harmonics', result)
        self.assertIn('<svg', result['svg'])

    def test_parameter_sweep_voltage_divider_returns_svg_and_target(self):
        result = parameter_sweep(
            {
                'kind': 'voltage_divider',
                'vin': 9,
                'r1_ohm': '1k',
                'r2_ohm': '1k',
                'parameter': 'r2_ohm',
                'start': 500,
                'stop': 3000,
                'target_min': 5.5,
                'target_max': 7.0,
                'points': 40,
            }
        )

        self.assertTrue(result['ok'])
        self.assertEqual(result['metric'], 'vout')
        self.assertIsNotNone(result['target_fraction'])
        self.assertIn('<svg', result['svg'])

    def test_server_side_dc_fallback_solves_imported_divider(self):
        imported = import_preview('ltspice', 'V1 in 0 DC 5\nR1 in out 1k\nR2 out 0 2k')
        result = server_side_dc_fallback(imported['scheme_data'])

        self.assertTrue(result['ok'])
        self.assertAlmostEqual(result['nodeVoltages']['out'], 10 / 3, delta=0.05)

    def test_postprocess_simulation_returns_measurements_markers_and_formulas(self):
        result = postprocess_simulation(
            {
                'points': [{'x': 0, 'y': 0}, {'x': 1, 'y': 3}, {'x': 2, 'y': -3}],
                'unit': 'V',
                'markers': [{'x': 1.2, 'label': 'near peak'}],
                'formulas': ['rms * 2'],
                'voltage': 5,
                'current': 0.02,
            }
        )

        self.assertTrue(result['ok'])
        self.assertEqual(result['points_count'], 3)
        self.assertAlmostEqual(result['metrics']['power_w'], 0.1, delta=1e-9)
        self.assertEqual(result['markers'][0]['label'], 'near peak')
        self.assertTrue(result['formulas'][0]['ok'])
        self.assertTrue(any(item['metric'] == 'component_power' for item in result['measurements']))

    def test_simulation_result_to_csv_exports_points(self):
        csv_text = simulation_result_to_csv({'points': [{'x': 0, 'y': 1}, {'x': 1, 'y': 2}]})

        self.assertIn('x,y', csv_text)
        self.assertIn('0,1', csv_text)

    def test_fft_api_is_pro_only_and_returns_svg(self):
        free = User.objects.create_user('free-sim', 'free@x', 'pw')
        self.client.force_login(free)
        response = self.client.post(
            reverse('hello:api_simulation_fft'),
            data=json.dumps({'sample_rate_hz': 1000, 'samples': [0, 1, 0, -1] * 8}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.user)
        response = self.client.post(
            reverse('hello:api_simulation_fft'),
            data=json.dumps({'sample_rate_hz': 1000, 'samples': [0, 1, 0, -1] * 8}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertIn('<svg', response.json()['svg'])

    def test_bode_and_monte_carlo_apis_are_pro_only_and_return_svg(self):
        free = User.objects.create_user('free-pro-analysis', 'free-pro@x', 'pw')
        self.client.force_login(free)
        response = self.client.post(
            reverse('hello:api_simulation_bode'),
            data=json.dumps({'kind': 'rc_lowpass', 'resistance_ohm': '10k', 'capacitance_f': '100n'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.user)
        response = self.client.post(
            reverse('hello:api_simulation_bode'),
            data=json.dumps({'kind': 'rc_lowpass', 'resistance_ohm': '10k', 'capacitance_f': '100n'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertIn('<svg', response.json()['svg'])

        response = self.client.post(
            reverse('hello:api_simulation_monte_carlo'),
            data=json.dumps({'kind': 'voltage_divider', 'vin': 9, 'r1_ohm': '1k', 'r2_ohm': '2k'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertIn('<svg', response.json()['svg'])

    def test_signal_quality_and_parameter_sweep_apis_are_pro_only(self):
        free = User.objects.create_user('free-signal-quality', 'free-sq@x', 'pw')
        self.client.force_login(free)
        response = self.client.post(
            reverse('hello:api_simulation_signal_quality'),
            data=json.dumps({'sample_rate_hz': 1000, 'samples': [0, 1, 0, -1] * 8}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.user)
        response = self.client.post(
            reverse('hello:api_simulation_signal_quality'),
            data=json.dumps({'sample_rate_hz': 1000, 'samples': [0, 1, 0, -1] * 8}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertIn('<svg', response.json()['svg'])

        response = self.client.post(
            reverse('hello:api_simulation_parameter_sweep'),
            data=json.dumps(
                {
                    'kind': 'rc_cutoff',
                    'resistance_ohm': '10k',
                    'capacitance_f': '100n',
                    'parameter': 'resistance_ohm',
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertIn('<svg', response.json()['svg'])

    def test_server_side_fallback_api_is_pro_only(self):
        free = User.objects.create_user('free-fallback', 'free-fallback@x', 'pw')
        self.client.force_login(free)
        imported = import_preview('ltspice', 'V1 in 0 DC 5\nR1 in out 1k\nR2 out 0 2k')

        response = self.client.post(
            reverse('hello:api_simulation_fallback_solve'),
            data=json.dumps({'scheme_data': imported['scheme_data']}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json().get('plan_required'), 'pro')

        self.client.force_login(self.user)
        response = self.client.post(
            reverse('hello:api_simulation_fallback_solve'),
            data=json.dumps({'scheme_data': imported['scheme_data']}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['engine'], 'server_side_numpy_mna')
        self.assertAlmostEqual(data['nodeVoltages']['out'], 10 / 3, delta=0.05)

    @override_settings(
        STORAGES={
            'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
        },
        SECURE_SSL_REDIRECT=False,
        ALLOWED_HOSTS=['testserver'],
    )
    def test_simulation_page_contains_pro_analysis_actions(self):
        response = self.client.get(reverse('hello:simulation'))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('dolg-pro-analysis', html)
        self.assertIn('runProFft', html)
        self.assertIn('runProBode', html)
        self.assertIn('runProMonteCarlo', html)
        self.assertIn('runSignalQuality', html)
        self.assertIn('runParameterSweep', html)
        self.assertIn('runServerFallbackSolve', html)
        self.assertIn('saveLatestProMetric', html)
        self.assertIn('measurementCreate', html)

    def test_measurement_api_preserves_pro_analysis_result_payload(self):
        project = SchematicProject.objects.create(user=self.user, name='Pro metric project')

        response = self.client.post(
            reverse('hello:api_project_measurement_create', args=[project.id]),
            data=json.dumps(
                {
                    'metric': 'dominant_frequency',
                    'label': 'FFT peak V(out)',
                    'value': 50,
                    'unit': 'Hz',
                    'source': 'pro_fft',
                    'result': {'peak_magnitude': 0.9, 'sample_count': 1000},
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        measurement = ProjectMeasurement.objects.get(project=project)
        self.assertEqual(measurement.source, 'pro_fft')
        self.assertEqual(measurement.result['peak_magnitude'], 0.9)

    def test_pandas_stats_endpoint_returns_slowest_runs(self):
        project = SchematicProject.objects.create(user=self.user, name='Stats project')
        SimulationRun.objects.create(project=project, user=self.user, analysis_type='dc', elapsed_ms=20)
        SimulationRun.objects.create(project=project, user=self.user, analysis_type='tran', elapsed_ms=120)

        response = self.client.get(reverse('hello:api_project_simulation_stats', args=[project.id]))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['slowest_runs'][0]['elapsed_ms'], 120)


class ShareTokenTests(TestCase):
    """Public read-only share-link через token."""

    def setUp(self):
        self.owner = User.objects.create_user('owner', 'o@x', 'pw')
        self.proj = SchematicProject.objects.create(
            user=self.owner,
            name='Shared',
            scheme_data={'components': []},
        )

    def test_share_toggle_generates_token(self):
        self.client.force_login(self.owner)
        resp = self.client.post(f'/projects/api/{self.proj.id}/share/')
        self.assertEqual(resp.status_code, 200)
        self.proj.refresh_from_db()
        self.assertTrue(self.proj.share_token)
        self.assertGreaterEqual(len(self.proj.share_token), 10)

    def test_shared_view_accessible_without_login(self):
        self.proj.share_token = 'abc123def456'
        self.proj.save()
        # Read-only страница доступна без логина.
        resp = self.client.get(reverse('hello:shared_scheme', kwargs={'token': self.proj.share_token}))
        self.assertEqual(resp.status_code, 200)

    def test_invalid_share_token_404(self):
        resp = self.client.get(reverse('hello:shared_scheme', kwargs={'token': 'invalidtoken123'}))
        self.assertEqual(resp.status_code, 404)

    def test_malformed_share_token_404(self):
        resp = self.client.get(reverse('hello:shared_scheme', kwargs={'token': 'short'}))
        self.assertEqual(resp.status_code, 404)
