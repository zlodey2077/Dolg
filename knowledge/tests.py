import json
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from knowledge.models import (
    Article,
    ArticleMaterial,
    KnowledgeCategory,
    LearningAttempt,
    LearningLesson,
    LearningProgress,
    LearningTask,
    LearningTrack,
)
from knowledge.services.circuit_svg import render_training_circuit
from knowledge.services.engineering_lab import calculate_lab
from knowledge.services.formula_steps import check_equivalent_expression, explain_formula
from knowledge.services.lab_measurements import compare_lab_measurement, run_lab_sweep
from knowledge.services.learning_grader import grade_circuit_task, grade_math_task, grade_simulation_task
from knowledge.services.legal_sources import (
    REQUIRED_TOPICS,
    find_legal_sources,
    load_legal_sources,
    sources_for_rule,
    summarize_legal_sources,
)
from shop.models import Category, Product


class KnowledgeArticleEnhancementTests(TestCase):
    def setUp(self):
        self.catalog_category = Category.objects.create(name='Резисторы', slug='resistors')
        self.product = Product.objects.create(
            name='Yageo RC0603FR-0710KL',
            slug='yageo-rc0603fr-0710kl',
            category=self.catalog_category,
            description='SMD resistor for divider and pull-up circuits',
            price=3,
            stock=250,
            manufacturer='yageo',
            part_number='RC0603FR-0710KL',
            lifecycle_status='active',
            package_type='0603',
            parameters={'resistance': '10 kOhm', 'power': '0.1 W', 'spice_model': 'R'},
        )
        self.knowledge_category = KnowledgeCategory.objects.create(
            name='Физика и теория',
            slug='physics',
            topic='physics',
        )
        self.article = Article.objects.create(
            category=self.knowledge_category,
            title='Закон Ома и делитель напряжения',
            slug='ohm-divider',
            summary='Расчет тока, сопротивления и делителя напряжения.',
            body='<p>Резистор, ток, напряжение, мощность и делитель напряжения.</p>',
            related_components_note='Резисторы для учебных схем.',
            is_published=True,
        )

    def test_article_has_practice_tools_and_catalog_products(self):
        response = self.client.get(reverse('knowledge:article', args=[self.article.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Практика по теме')
        self.assertContains(response, 'Открыть в CAD')
        self.assertContains(response, 'Проверить в симуляции')
        self.assertContains(response, 'Закон Ома')
        self.assertContains(response, 'Делитель напряжения')
        self.assertContains(response, 'Связанные товары из каталога')
        self.assertContains(response, self.product.name)


class LegalSourcesTests(TestCase):
    def setUp(self):
        self.knowledge_category = KnowledgeCategory.objects.create(
            name='Физика и теория',
            slug='physics',
            topic='physics',
        )
        self.article = Article.objects.create(
            category=self.knowledge_category,
            title='Закон Ома — фундамент электротехники',
            slug='закон-ома-фундамент-электротехники',
            summary='Базовая связь тока, напряжения и сопротивления.',
            body='<p>R, I, U.</p>',
            is_published=True,
        )

    def test_legal_sources_have_required_topics(self):
        sources = load_legal_sources()
        summary = summarize_legal_sources(sources)

        self.assertGreaterEqual(summary['count'], 12)
        self.assertFalse(REQUIRED_TOPICS.difference(summary['topics']))
        self.assertGreaterEqual(summary['learning_sources'], 6)
        self.assertGreaterEqual(summary['ai_sources'], 6)
        self.assertGreaterEqual(summary['sources_with_keywords'], 12)
        self.assertGreaterEqual(summary['sources_with_rules'], 6)
        self.assertGreaterEqual(summary['sources_with_learning_topics'], 6)

    def test_legal_source_retrieval_and_rule_bibliography(self):
        results = find_legal_sources('gnd spice', limit=5)
        result_ids = {item['id'] for item in results}

        self.assertIn('ngspice_docs', result_ids)
        self.assertIn('kicad_docs', result_ids)
        self.assertTrue(sources_for_rule('erc.missing_ground'))

    def test_seed_legal_sources_creates_overview_and_article_material(self):
        out = StringIO()
        call_command('seed_legal_sources', '--json', stdout=out)
        result = json.loads(out.getvalue())

        self.assertIn('overview_article', result)
        self.assertTrue(Article.objects.filter(slug='otkrytye-istochniki-i-dokumentatsiya-dolg').exists())
        self.assertTrue(
            ArticleMaterial.objects.filter(
                article=self.article,
                title__icontains='All About Circuits',
                url='https://www.allaboutcircuits.com/textbook/',
                is_public=True,
            ).exists()
        )
        self.assertGreaterEqual(result['learning_tasks'], 9)
        sourced_tasks = [
            task
            for task in LearningTask.objects.all()
            if isinstance(task.rubric, dict) and task.rubric.get('source_ids')
        ]
        self.assertGreaterEqual(len(sourced_tasks), 9)

        lesson = LearningLesson.objects.get(slug='source-backed-spice-gnd-drc')
        response = self.client.get(reverse('knowledge:learning_lesson', args=[lesson.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Материалы для проверки')
        self.assertContains(response, 'ngspice')


class LearningModelAndGraderTests(TestCase):
    def setUp(self):
        self.track = LearningTrack.objects.create(
            title='Базовый маршрут',
            slug='basic-track',
            summary='Практикум для старта.',
            level='basic',
        )
        self.lesson = LearningLesson.objects.create(
            track=self.track,
            title='Делитель напряжения',
            slug='divider-lesson',
            summary='Расчет и сборка делителя.',
            theory='<p>Два резистора задают Vout.</p>',
            formula='Vout = Vin × R2 / (R1 + R2)',
        )
        self.math_task = LearningTask.objects.create(
            lesson=self.lesson,
            task_type='math_numeric',
            title='Расчет Vout',
            prompt='Найдите Vout.',
            rubric={'expected_value': 2.88, 'unit': 'В', 'tolerance_abs': 0.05},
            order=10,
        )
        self.circuit_task = LearningTask.objects.create(
            lesson=self.lesson,
            task_type='circuit_build',
            title='Соберите делитель',
            prompt='Соберите источник, два резистора и GND.',
            rubric={
                'required_types': {'battery': 1, 'resistor': 2, 'ground': 1},
                'require_ground': True,
                'require_source': True,
                'min_connections': 3,
                'nominal_ranges': [
                    {'type': 'battery', 'field': 'voltage', 'min': 8.5, 'max': 9.5, 'unit': 'В'},
                    {'type': 'resistor', 'field': 'resistance', 'min': 6500, 'max': 7100, 'unit': 'Ом'},
                    {'type': 'resistor', 'field': 'resistance', 'min': 3000, 'max': 3400, 'unit': 'Ом'},
                ],
            },
            order=20,
        )
        self.simulation_task = LearningTask.objects.create(
            lesson=self.lesson,
            task_type='simulation_measure',
            title='Измерьте Vout',
            prompt='Отправьте DC-результат.',
            rubric={
                'required_analysis': 'dc',
                'metric': 'node_voltage',
                'node': 'out',
                'expected_value': 2.88,
                'unit': 'В',
                'tolerance_abs': 0.15,
            },
            order=30,
        )
        self.scheme = {
            'components': [
                {'id': 'v1', 'type': 'battery', 'voltage': '9V'},
                {'id': 'r1', 'type': 'resistor', 'resistance': '6.8kOhm'},
                {'id': 'r2', 'type': 'resistor', 'resistance': '3.2kOhm'},
                {'id': 'gnd', 'type': 'ground'},
            ],
            'connections': [
                {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
                {'from': {'compId': 'r1'}, 'to': {'compId': 'r2'}},
                {'from': {'compId': 'r2'}, 'to': {'compId': 'gnd'}},
            ],
        }

    def test_progress_marks_lesson_completed_after_required_tasks(self):
        user = get_user_model().objects.create_user(username='student', password='pass')
        progress = LearningProgress.objects.create(user=user, lesson=self.lesson)

        progress.mark_task_solved(self.math_task.id)
        self.assertFalse(progress.is_completed)

        progress.mark_task_solved(self.circuit_task.id)
        progress.mark_task_solved(self.simulation_task.id)

        self.assertTrue(progress.is_completed)
        self.assertEqual(
            progress.solved_task_ids, [self.math_task.id, self.circuit_task.id, self.simulation_task.id]
        )

    def test_grade_math_task_accepts_value_in_tolerance(self):
        result = grade_math_task(self.math_task, '2.90 В')

        self.assertTrue(result['correct'])
        self.assertEqual(result['score'], 100)

    def test_grade_math_task_rejects_wrong_value(self):
        result = grade_math_task(self.math_task, '3.4')

        self.assertFalse(result['correct'])

    def test_circuit_without_ground_fails(self):
        scheme = {
            'components': self.scheme['components'][:-1],
            'connections': self.scheme['connections'][:2],
        }

        result = grade_circuit_task(self.circuit_task, scheme)

        self.assertFalse(result['correct'])
        self.assertIn('GND', result['feedback'])

    def test_circuit_with_required_nominals_passes(self):
        result = grade_circuit_task(self.circuit_task, self.scheme)

        self.assertTrue(result['correct'])
        self.assertEqual(result['details']['component_counts']['resistor'], 2)

    def test_simulation_result_in_tolerance_passes(self):
        result = grade_simulation_task(
            self.simulation_task,
            self.scheme,
            {'type': 'dc', 'nodeVoltages': {'out': 2.91}},
        )

        self.assertTrue(result['correct'])

    def test_wrong_analysis_type_fails_simulation_task(self):
        result = grade_simulation_task(
            self.simulation_task,
            self.scheme,
            {'type': 'ac', 'nodeVoltages': {'out': 2.91}},
        )

        self.assertFalse(result['correct'])
        self.assertIn('dc', result['feedback'])

    def test_math_task_can_use_engineering_lab_formula(self):
        task = LearningTask.objects.create(
            lesson=self.lesson,
            task_type='math_numeric',
            title='Расчет NE555',
            prompt='Найдите частоту.',
            rubric={
                'unit': 'Гц',
                'tolerance_abs': 5,
                'lab': {
                    'kind': 'ne555_astable',
                    'inputs': {'r1_ohm': '10k', 'r2_ohm': '68k', 'capacitance_f': '100n'},
                    'output': 'frequency_hz',
                },
            },
        )

        result = grade_math_task(task, '99')

        self.assertTrue(result['correct'])

    def test_math_task_can_use_sympy_formula_steps(self):
        task = LearningTask.objects.create(
            lesson=self.lesson,
            task_type='math_numeric',
            title='Делитель',
            prompt='Найдите Vout.',
            rubric={
                'unit': 'V',
                'tolerance_abs': 0.05,
                'formula': {
                    'kind': 'voltage_divider',
                    'inputs': {'vin': 9, 'r1_ohm': 1000, 'r2_ohm': 2000},
                },
            },
        )

        result = grade_math_task(task, '6.0')

        self.assertTrue(result['correct'])
        self.assertIn('formula', result['details'])
        self.assertAlmostEqual(result['details']['formula']['expected_value'], 6)

    def test_math_task_accepts_equivalent_sympy_expression(self):
        task = LearningTask.objects.create(
            lesson=self.lesson,
            task_type='math_numeric',
            title='Формула делителя',
            prompt='Введите формулу.',
            rubric={
                'accept_expression': True,
                'formula': {'kind': 'voltage_divider'},
            },
        )

        result = grade_math_task(task, 'Vin * R2 / (R1 + R2)')

        self.assertTrue(result['correct'])
        self.assertIn('эквивалентна', result['feedback'])

    def test_circuit_task_supports_type_aliases_and_required_properties(self):
        task = LearningTask.objects.create(
            lesson=self.lesson,
            task_type='circuit_build',
            title='NE555 схема',
            prompt='Соберите NE555.',
            rubric={
                'required_types': {'ic': 1, 'button': 1, 'ground': 1},
                'require_ground': True,
                'required_properties': [
                    {'type': 'ic', 'field': 'part_number', 'op': 'contains', 'values': ['555']},
                ],
            },
        )
        scheme = {
            'components': [
                {'id': 'u1', 'type': 'ic', 'part_number': 'NE555P'},
                {'id': 's1', 'type': 'switch'},
                {'id': 'gnd', 'type': 'ground'},
            ],
            'connections': [],
        }

        result = grade_circuit_task(task, scheme)

        self.assertTrue(result['correct'])

    def test_circuit_task_can_require_connected_graph_and_output_node(self):
        task = LearningTask.objects.create(
            lesson=self.lesson,
            task_type='circuit_build',
            title='Делитель со связной схемой',
            prompt='Соберите делитель.',
            rubric={
                'required_types': {'battery': 1, 'resistor': 2, 'ground': 1, 'node': 1},
                'require_ground': True,
                'require_connected': True,
                'require_output_node': True,
            },
        )
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

        result = grade_circuit_task(task, scheme)

        self.assertTrue(result['correct'])
        self.assertEqual(result['details']['graph']['metrics']['topology'], 'voltage_divider')

    def test_simulation_task_accepts_lab_frequency_metric(self):
        task = LearningTask.objects.create(
            lesson=self.lesson,
            task_type='simulation_measure',
            title='Частота NE555',
            prompt='Измерьте частоту.',
            rubric={
                'required_analysis': 'tran',
                'metric': 'frequency',
                'unit': 'Гц',
                'tolerance_abs': 5,
                'lab': {
                    'kind': 'ne555_astable',
                    'inputs': {'r1_ohm': '10k', 'r2_ohm': '68k', 'capacitance_f': '100n'},
                    'output': 'frequency_hz',
                },
            },
        )

        result = grade_simulation_task(task, {}, {'type': 'tran', 'metrics': {'frequency': 98.6}})

        self.assertTrue(result['correct'])


class LightweightLearningLibraryTests(TestCase):
    def test_sympy_formula_explains_voltage_divider(self):
        result = explain_formula('voltage_divider', {'vin': 9, 'r1_ohm': 1000, 'r2_ohm': 2000})

        self.assertAlmostEqual(result['expected_value'], 6)
        self.assertEqual(result['unit'], 'V')
        self.assertGreaterEqual(len(result['steps']), 3)

    def test_sympy_accepts_equivalent_expression(self):
        result = check_equivalent_expression('rc_cutoff', '1/(2*pi*R*C)')

        self.assertTrue(result['correct'])

    def test_schemdraw_generates_training_svgs(self):
        for kind in ('led_indicator', 'voltage_divider', 'rc_filter'):
            svg = render_training_circuit(kind)

            self.assertIn('<svg', svg)
            self.assertIn('</svg>', svg)


class LearningViewsTests(TestCase):
    def setUp(self):
        self.track = LearningTrack.objects.create(
            title='Практикум',
            slug='practice-track',
            summary='Учебный маршрут.',
            level='basic',
        )
        self.lesson = LearningLesson.objects.create(
            track=self.track,
            title='Закон Ома',
            slug='ohm-learning',
            summary='Расчет тока.',
            theory='<p>Ток равен напряжению, деленному на сопротивление.</p>',
            formula='I = U / R',
        )
        self.task = LearningTask.objects.create(
            lesson=self.lesson,
            task_type='math_numeric',
            title='Ток через резистор',
            prompt='9 В / 3 кОм.',
            rubric={'expected_value': 3, 'unit': 'мА', 'tolerance_abs': 0.2},
        )

    def test_learning_index_is_public(self):
        response = self.client.get(reverse('knowledge:learning_index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Практикум')
        self.assertContains(response, self.lesson.title)

    def test_lesson_detail_shows_tasks(self):
        response = self.client.get(reverse('knowledge:learning_lesson', args=[self.lesson.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.task.title)

    def test_anonymous_can_check_answer_without_saved_progress(self):
        response = self.client.post(
            reverse('knowledge:learning_task_check', args=[self.lesson.slug, self.task.id]),
            data={'answer': '3'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['correct'])
        self.assertFalse(response.json()['saved'])
        self.assertEqual(LearningAttempt.objects.count(), 0)
        self.assertEqual(LearningProgress.objects.count(), 0)

    def test_logged_in_check_saves_attempt_and_progress(self):
        user = get_user_model().objects.create_user(username='learner', password='pass')
        self.client.force_login(user)

        response = self.client.post(
            reverse('knowledge:learning_task_check', args=[self.lesson.slug, self.task.id]),
            data={'answer': '3'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['correct'])
        self.assertTrue(response.json()['saved'])
        self.assertEqual(LearningAttempt.objects.filter(user=user, task=self.task).count(), 1)
        progress = LearningProgress.objects.get(user=user, lesson=self.lesson)
        self.assertTrue(progress.is_completed)


class EngineeringLabTests(TestCase):
    def test_transistor_switch_calculation_returns_engineering_assessment(self):
        result = calculate_lab(
            'transistor_switch',
            {
                'supply_voltage': 5,
                'load_voltage': 2,
                'load_current_ma': 20,
                'input_voltage': 5,
                'forced_beta': 10,
            },
        )

        self.assertTrue(result['ok'])
        self.assertEqual(result['status'], 'ok')
        self.assertIn(result['validation_backend'], {'python-engineering', 'builtin'})
        self.assertAlmostEqual(result['outputs']['base_resistor_ohm']['value'], 2150, delta=1)

    def test_linear_regulator_detects_thermal_risk(self):
        result = calculate_lab(
            'linear_regulator',
            {
                'vin': 12,
                'vout': 5,
                'load_current_ma': 500,
                'theta_ja': 50,
                'ambient_c': 25,
                'max_junction_c': 125,
            },
        )

        self.assertTrue(result['ok'])
        self.assertIn(result['status'], {'risk', 'overheat'})

    def test_lab_page_is_public(self):
        response = self.client.get(reverse('knowledge:engineering_lab'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Инженерная лаборатория')
        self.assertContains(response, 'Генератор NE555')

    def test_lab_api_calculates_ne555(self):
        response = self.client.post(
            reverse('knowledge:engineering_lab_api'),
            data=json.dumps(
                {
                    'kind': 'ne555_astable',
                    'inputs': {'r1_ohm': '10k', 'r2_ohm': '68k', 'capacitance_f': '100n'},
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertAlmostEqual(data['outputs']['frequency_hz']['value'], 98.6, delta=1)

    def test_lab_sweep_reuses_calculators_for_what_if(self):
        result = run_lab_sweep(
            'rc_debounce',
            {'resistance_ohm': '10k', 'capacitance_f': '100n'},
            'resistance_ohm',
            ['1k', '10k', '100k'],
            'time_constant_s',
        )

        self.assertTrue(result['ok'])
        self.assertEqual(result['trend'], 'up')
        self.assertEqual(len(result['points']), 3)

    def test_lab_measurement_comparison_accepts_expected_value(self):
        result = compare_lab_measurement(
            {
                'metric': 'frequency',
                'unit': 'Hz',
                'tolerance_abs': 5,
                'lab': {
                    'kind': 'ne555_astable',
                    'inputs': {'r1_ohm': '10k', 'r2_ohm': '68k', 'capacitance_f': '100n'},
                    'output': 'frequency_hz',
                },
            },
            {'type': 'tran', 'metrics': {'frequency': 98.7}},
        )

        self.assertTrue(result['correct'])
        self.assertEqual(result['status'], 'ok')


class PopulateKnowledgeLearningTests(TestCase):
    def test_seed_creates_diagnostics_learning_track(self):
        call_command('populate_knowledge', verbosity=0)

        track = LearningTrack.objects.get(slug='diagnostika-prostyh-shem')
        self.assertTrue(track.is_published)
        self.assertGreaterEqual(LearningLesson.objects.filter(track=track).count(), 2)
        self.assertGreaterEqual(LearningTask.objects.filter(lesson__track=track).count(), 4)

    def test_seed_creates_lab_backed_learning_track(self):
        call_command('populate_knowledge', verbosity=0)

        self.assertGreaterEqual(LearningTrack.objects.filter(is_published=True).count(), 2)
        self.assertGreaterEqual(
            LearningLesson.objects.filter(track__title='Прикладные узлы электроники').count(), 5
        )
        self.assertGreaterEqual(
            LearningTask.objects.filter(lesson__track__title='Прикладные узлы электроники').count(), 12
        )
        self.assertTrue(
            any(
                'lab' in (task.rubric or {})
                for task in LearningTask.objects.filter(lesson__track__title='Прикладные узлы электроники')
            )
        )
