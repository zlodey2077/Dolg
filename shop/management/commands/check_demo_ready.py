import json
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, ProgrammingError
from django.test import Client, override_settings
from django.urls import reverse

from knowledge.models import (
    Article,
    ArticleMaterial,
    KnowledgeCategory,
    LearningLesson,
    LearningTask,
    LearningTrack,
)
from shop.models import Category, Product
from shop.services.media_quality import audit_catalog_media_quality
from shop.services.product_images import (
    GENERATED_IMAGE_DIR,
    is_allowed_product_image,
    is_forbidden_image_path,
)


class Command(BaseCommand):
    help = 'Проверяет, готов ли DOLG к демонстрации: URL, данные, фото, материалы, static/media.'

    def add_arguments(self, parser):
        parser.add_argument('--strict', action='store_true', help='Считать предупреждения ошибками.')
        parser.add_argument('--json', action='store_true', help='Вывести результат в JSON.')

    def handle(self, *args, **options):
        report = {
            'ok': True,
            'errors': [],
            'warnings': [],
            'counts': {},
            'urls': [],
            'scientific_stack': {},
            'graph_stack': {},
            'formula_stack': {},
            'circuit_svg_stack': {},
            'expert_stack': {},
            'catalog_filter_stack': {},
            'datasheet_intelligence': {},
            'legal_sources_stack': {},
            'artifact_stack': {},
            'moderation_stack': {},
            'admin_monitoring_stack': {},
            'entitlement_stack': {},
            'neural_stack': {},
            'media_quality': {},
            'project_session': {},
        }

        self._check_counts(report)
        self._check_product_media(report)
        self._check_knowledge_materials(report)
        self._check_legal_sources_stack(report)
        self._check_files(report)
        self._check_scientific_stack(report)
        self._check_project_session_stack(report)
        self._check_lightweight_library_stack(report)
        self._check_expert_system_stack(report)
        self._check_catalog_filter_stack(report)
        self._check_datasheet_intelligence(report)
        self._check_artifact_stack(report)
        self._check_moderation_stack(report)
        self._check_admin_monitoring_stack(report)
        self._check_entitlement_stack(report)
        self._check_neural_stack(report)
        self._check_urls(report)

        if options['strict'] and report['warnings']:
            report['errors'].extend(f'warning-as-error: {item}' for item in report['warnings'])

        report['ok'] = not report['errors']

        if options['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            self._print_human(report)

        if report['errors']:
            raise CommandError('DOLG не готов к демонстрации: найдены ошибки.')

    def _check_counts(self, report):
        from Dolg_APP.models import (
            AITrainingExample,
            EngineeringArtifact,
            ProjectEvent,
            ProjectMeasurement,
            ProjectReview,
            SchematicProject,
        )

        counts = report['counts']
        counts['products'] = Product.objects.count()
        counts['reb_products'] = Product.objects.filter(category__slug__in=Category.REB_SLUGS).count()
        counts['categories'] = Category.objects.count()
        counts['knowledge_categories'] = KnowledgeCategory.objects.count()
        counts['published_articles'] = Article.objects.filter(is_published=True).count()
        counts['article_materials'] = ArticleMaterial.objects.filter(is_public=True).count()
        counts['learning_tracks'] = LearningTrack.objects.filter(is_published=True).count()
        counts['learning_lessons'] = LearningLesson.objects.filter(
            is_published=True, track__is_published=True
        ).count()
        counts['learning_tasks'] = LearningTask.objects.filter(
            lesson__is_published=True, lesson__track__is_published=True
        ).count()
        counts['demo_projects'] = SchematicProject.objects.filter(is_demo=True).count()
        try:
            counts['project_reviews'] = ProjectReview.objects.count()
            counts['project_measurements'] = ProjectMeasurement.objects.count()
            counts['project_events'] = ProjectEvent.objects.count()
            counts['engineering_artifacts'] = EngineeringArtifact.objects.count()
            counts['ai_training_examples'] = AITrainingExample.objects.count()
        except (OperationalError, ProgrammingError) as exc:
            counts['project_reviews'] = 0
            counts['project_measurements'] = 0
            counts['project_events'] = 0
            counts['engineering_artifacts'] = 0
            counts['ai_training_examples'] = 0
            report['errors'].append(f'review tables are not migrated: {exc}; run python manage.py migrate')

        minimums = {
            'products': 20,
            'reb_products': 20,
            'categories': 8,
            'knowledge_categories': 4,
            'published_articles': 9,
            'learning_tracks': 2,
            'learning_lessons': 10,
            'learning_tasks': 22,
            'demo_projects': 3,
        }
        for key, minimum in minimums.items():
            if counts[key] < minimum:
                report['errors'].append(f'{key}: {counts[key]} меньше минимального значения {minimum}')

        if not LearningTrack.objects.filter(slug='diagnostika-prostyh-shem', is_published=True).exists():
            report['warnings'].append('diagnostics learning track is missing: run populate_knowledge')

    def _check_scientific_stack(self, report):
        stack = report.setdefault('scientific_stack', {})
        package_imports = {
            'numpy': 'numpy',
            'scipy': 'scipy',
            'matplotlib': 'matplotlib',
            'pandas': 'pandas',
            'python-engineering': 'pyeng',
        }

        for package_name, import_name in package_imports.items():
            try:
                module = __import__(import_name)
                try:
                    package_version = version(package_name)
                except PackageNotFoundError:
                    package_version = getattr(module, '__version__', 'unknown')
                stack[package_name] = {'ok': True, 'version': package_version}
            except Exception as exc:
                stack[package_name] = {'ok': False, 'error': str(exc)}
                report['errors'].append(f'scientific stack package failed: {package_name} ({exc})')

        try:
            from Dolg_APP.services.cad_import import import_preview
            from Dolg_APP.services.simulation_analysis import (
                bode_plot,
                fft_spectrum,
                monte_carlo_tolerance,
                parameter_sweep,
                server_side_dc_fallback,
                signal_quality,
            )

            fft_result = fft_spectrum([0, 1, 0, -1] * 8, 4)
            bode_result = bode_plot(
                {
                    'kind': 'rc_lowpass',
                    'resistance_ohm': '10k',
                    'capacitance_f': '100n',
                    'start_hz': 10,
                    'stop_hz': 10000,
                    'points': 24,
                }
            )
            monte_carlo_result = monte_carlo_tolerance(
                {
                    'kind': 'voltage_divider',
                    'vin': 5,
                    'r1_ohm': '1k',
                    'r2_ohm': '1k',
                    'samples': 32,
                    'seed': 7,
                }
            )
            signal_quality_result = signal_quality([0, 1, 0, -1] * 8, 4)
            sweep_result = parameter_sweep(
                {
                    'kind': 'rc_cutoff',
                    'resistance_ohm': '10k',
                    'capacitance_f': '100n',
                    'parameter': 'resistance_ohm',
                    'points': 16,
                }
            )
            imported = import_preview('ltspice', 'V1 in 0 DC 5\nR1 in out 1k\nR2 out 0 2k')
            fallback_result = server_side_dc_fallback(imported.get('scheme_data'))

            service_checks = {
                'fft_svg': bool(fft_result.get('ok') and '<svg' in fft_result.get('svg', '')),
                'bode_svg': bool(bode_result.get('ok') and '<svg' in bode_result.get('svg', '')),
                'monte_carlo_svg': bool(
                    monte_carlo_result.get('ok') and '<svg' in monte_carlo_result.get('svg', '')
                ),
                'signal_quality_svg': bool(
                    signal_quality_result.get('ok') and '<svg' in signal_quality_result.get('svg', '')
                ),
                'parameter_sweep_svg': bool(sweep_result.get('ok') and '<svg' in sweep_result.get('svg', '')),
                'dc_fallback': bool(
                    imported.get('ok')
                    and fallback_result.get('ok')
                    and fallback_result.get('engine') == 'server_side_numpy_mna'
                ),
            }
            stack['service_checks'] = service_checks
            for name, passed in service_checks.items():
                if not passed:
                    report['errors'].append(f'scientific service check failed: {name}')
        except Exception as exc:
            stack['service_checks'] = {'ok': False, 'error': str(exc)}
            report['errors'].append(f'scientific service checks failed: {exc}')

    def _check_project_session_stack(self, report):
        session = report.setdefault('project_session', {})
        try:
            from Dolg_APP.models import ProjectEvent, SimulationRun
            from Dolg_APP.services.project_review import build_design_review
            from Dolg_APP.services.simulation_analysis import postprocess_simulation, simulation_result_to_csv

            post = postprocess_simulation(
                {
                    'points': [{'x': 0, 'y': 0}, {'x': 1, 'y': 1}, {'x': 2, 'y': 0}],
                    'unit': 'V',
                    'voltage': 5,
                    'current': 0.02,
                    'formulas': ['rms * 2'],
                }
            )
            csv_text = simulation_result_to_csv({'nodeVoltages': {'out': 3.3}})
            review = build_design_review(
                type(
                    'DemoProject',
                    (),
                    {
                        'name': 'demo session',
                        'scheme_data': {
                            'components': [
                                {'id': 'v1', 'type': 'battery', 'voltage': '5V'},
                                {
                                    'id': 'r1',
                                    'type': 'resistor',
                                    'rated_power_w': 0.25,
                                    'measured_power_w': 0.3,
                                },
                                {'id': 'gnd', 'type': 'ground'},
                            ],
                            'connections': [
                                {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
                                {'from': {'compId': 'r1'}, 'to': {'compId': 'gnd'}},
                            ],
                        },
                    },
                )(),
                simulation_runs=[],
                measurements=[],
            )
            service_checks = {
                'project_event_model': ProjectEvent._meta.get_field('payload').get_internal_type()
                == 'JSONField',
                'simulation_async_fields': all(
                    hasattr(SimulationRun, name)
                    for name in ('progress_percent', 'message', 'started_at', 'finished_at')
                ),
                'postprocess_measurements': bool(post.get('ok') and post.get('measurements')),
                'csv_export': 'node,voltage' in csv_text,
                'validity_guard': bool(review.get('sections', {}).get('validity', {}).get('issues')),
            }
            session['service_checks'] = service_checks
            for name, passed in service_checks.items():
                if not passed:
                    report['errors'].append(f'project session service check failed: {name}')
        except Exception as exc:
            session['service_checks'] = {'ok': False, 'error': str(exc)}
            report['errors'].append(f'project session service checks failed: {exc}')

    def _check_moderation_stack(self, report):
        stack = report.setdefault('moderation_stack', {})
        try:
            from django.contrib.auth.models import Group
            from django.urls import reverse

            from Dolg_APP.models import (
                ChatReply,
                ChatTopic,
                Comment,
                OrganizationMember,
                OrgConversationMessage,
            )
            from moderation.models import (
                ModerationAction,
                ModerationCase,
                ModerationReport,
                ModerationRule,
                UserRestriction,
            )
            from moderation.permissions import GLOBAL_GROUPS, GLOBAL_ROLE_PERMISSIONS

            existing_groups = set(Group.objects.filter(name__in=GLOBAL_GROUPS).values_list('name', flat=True))
            required_models = [
                ModerationCase,
                ModerationReport,
                ModerationAction,
                UserRestriction,
                ModerationRule,
            ]
            service_checks = {
                'global_groups': set(GLOBAL_GROUPS).issubset(existing_groups),
                'role_permissions': 'moderation.action'
                in GLOBAL_ROLE_PERMISSIONS.get('site_moderator', set()),
                'org_moderator_role': 'moderator'
                in {value for value, _label in OrganizationMember.ROLE_CHOICES},
                'soft_fields': all(
                    model._meta.get_field('moderation_status')
                    for model in (Comment, ChatTopic, ChatReply, OrgConversationMessage)
                ),
                'models_registered': all(model._meta.app_label == 'moderation' for model in required_models),
                'api_report_url': reverse('moderation:api_report') == '/api/moderation/report/',
                'api_queue_url': reverse('moderation:api_queue') == '/api/moderation/queue/',
                'dashboard_url': reverse('moderation:dashboard') == '/moderation/',
            }
            stack['service_checks'] = service_checks
            stack['groups'] = sorted(existing_groups)
            for name, passed in service_checks.items():
                if not passed:
                    report['errors'].append(f'moderation stack check failed: {name}')
        except Exception as exc:
            stack['service_checks'] = {'ok': False, 'error': str(exc)}
            report['errors'].append(f'moderation stack checks failed: {exc}')

    def _check_admin_monitoring_stack(self, report):
        stack = report.setdefault('admin_monitoring_stack', {})
        try:
            from Dolg_APP.services.ops_metrics import collect_ops_snapshot

            snapshot = collect_ops_snapshot(use_cache=False)
            required_sections = {
                'runtime',
                'catalog',
                'business',
                'projects',
                'ai_ml',
                'moderation',
                'security',
                'health',
            }
            stack['psutil'] = {
                'ok': snapshot.get('runtime', {}).get('process', {}).get('psutil_available', False),
                'version': version('psutil')
                if snapshot.get('runtime', {}).get('process', {}).get('psutil_available')
                else '',
            }
            stack['snapshot'] = {
                'ok': required_sections.issubset(snapshot.keys()),
                'health_status': snapshot.get('health', {}).get('status'),
                'alerts': len(snapshot.get('health', {}).get('alerts') or []),
                'sections': sorted(key for key in required_sections if key in snapshot),
            }
            stack['routes'] = {
                'dashboard': reverse('hello:staff_ops_dashboard'),
                'snapshot_api': reverse('hello:staff_ops_snapshot_api'),
            }
            nginx_conf = Path(settings.BASE_DIR) / 'deploy' / 'nginx.conf'
            nginx_text = (
                nginx_conf.read_text(encoding='utf-8', errors='ignore') if nginx_conf.exists() else ''
            )
            stack['nginx_metrics_blocked'] = (
                'location = /metrics' in nginx_text and 'return 403' in nginx_text
            )
            checks = {
                'psutil_available': stack['psutil']['ok'],
                'snapshot_sections': stack['snapshot']['ok'],
                'staff_ops_route': stack['routes']['dashboard'] == '/staff/ops/',
                'staff_ops_api_route': stack['routes']['snapshot_api'] == '/staff/ops/api/snapshot/',
                'nginx_metrics_blocked': stack['nginx_metrics_blocked'],
            }
            stack['service_checks'] = checks
            for name, passed in checks.items():
                if not passed:
                    report['errors'].append(f'admin monitoring stack check failed: {name}')
        except PackageNotFoundError as exc:
            stack['service_checks'] = {'ok': False, 'error': str(exc)}
            report['errors'].append('admin monitoring dependency is missing: install psutil')
        except Exception as exc:
            stack['service_checks'] = {'ok': False, 'error': str(exc)}
            report['errors'].append(f'admin monitoring stack checks failed: {exc}')

    def _check_entitlement_stack(self, report):
        stack = report.setdefault('entitlement_stack', {})
        try:
            from Dolg_APP.services.entitlements import (
                ENTERPRISE_FEATURES,
                FEATURE_MATRIX,
                FREE_FEATURES,
                PRO_FEATURES,
                check_feature,
                plan_features,
            )

            class DemoUser:
                is_authenticated = True
                is_staff = False
                is_superuser = False

            user = DemoUser()
            checks = {
                'free_ai_basic': 'ai_chat_basic' in FREE_FEATURES,
                'pro_scientific': {'pro_fft', 'pro_bode', 'pro_monte_carlo', 'pro_parameter_sweep'}.issubset(
                    PRO_FEATURES
                ),
                'enterprise_team_ai': 'enterprise_team_ai_memory' in ENTERPRISE_FEATURES,
                'free_blocks_pro_fft': not check_feature(user, 'pro_fft').allowed,
                'matrix_has_unlimited': 'unlimited' in FEATURE_MATRIX,
                'enterprise_inherits_pro': 'pro_fft' in plan_features('enterprise'),
            }
            stack['service_checks'] = checks
            stack['plans'] = {plan: len(features) for plan, features in FEATURE_MATRIX.items()}
            for name, passed in checks.items():
                if not passed:
                    report['errors'].append(f'entitlement stack check failed: {name}')
        except Exception as exc:
            stack['service_checks'] = {'ok': False, 'error': str(exc)}
            report['errors'].append(f'entitlement stack checks failed: {exc}')

    def _check_neural_stack(self, report):
        stack = report.setdefault('neural_stack', {})
        try:
            from Dolg_APP.ml.neural import default_model_path, torch_available

            stack['torch'] = {
                'ok': torch_available(),
                'version': version('torch') if torch_available() else '',
            }
            model_path = default_model_path()
            stack['tiny_circuit_model'] = {
                'ok': model_path.exists(),
                'path': str(model_path.relative_to(settings.BASE_DIR))
                if model_path.exists()
                else str(model_path),
            }
            if not stack['torch']['ok']:
                report['warnings'].append(
                    'PyTorch neural backend is optional and not installed: pip install -r requirements-ai.txt'
                )
            elif not model_path.exists():
                report['warnings'].append(
                    'PyTorch installed, but tiny circuit model is not trained: run train_tiny_circuit_ai'
                )
        except Exception as exc:
            stack['ok'] = False
            stack['error'] = str(exc)
            report['warnings'].append(f'neural stack check failed: {exc}')

    def _check_lightweight_library_stack(self, report):
        package_groups = {
            'graph_stack': {'networkx': 'networkx'},
            'formula_stack': {'sympy': 'sympy'},
            'circuit_svg_stack': {'schemdraw': 'schemdraw'},
        }
        for stack_name, packages in package_groups.items():
            stack = report.setdefault(stack_name, {})
            for package_name, import_name in packages.items():
                try:
                    module = __import__(import_name)
                    try:
                        package_version = version(package_name)
                    except PackageNotFoundError:
                        package_version = getattr(module, '__version__', 'unknown')
                    stack[package_name] = {'ok': True, 'version': package_version}
                except Exception as exc:
                    stack[package_name] = {'ok': False, 'error': str(exc)}
                    report['errors'].append(f'lightweight library failed: {package_name} ({exc})')

        try:
            from Dolg_APP.services.schematic_graph import analyze_graph_topology
            from knowledge.services.circuit_svg import render_training_circuit
            from knowledge.services.formula_steps import check_equivalent_expression, explain_formula

            divider = {
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
            graph = analyze_graph_topology(divider)
            formula = explain_formula('voltage_divider', {'vin': 9, 'r1_ohm': 1000, 'r2_ohm': 2000})
            equivalent = check_equivalent_expression('voltage_divider', 'Vin*R2/(R1 + R2)')
            svg = render_training_circuit('voltage_divider')

            service_checks = {
                'voltage_divider_topology': graph.get('metrics', {}).get('topology') == 'voltage_divider',
                'formula_expected_value': abs(formula.get('expected_value', 0) - 6) < 1e-9,
                'formula_equivalence': bool(equivalent.get('correct')),
                'schemdraw_svg': '<svg' in svg,
            }
            report['graph_stack']['service_checks'] = {
                'voltage_divider_topology': service_checks['voltage_divider_topology'],
            }
            report['formula_stack']['service_checks'] = {
                'formula_expected_value': service_checks['formula_expected_value'],
                'formula_equivalence': service_checks['formula_equivalence'],
            }
            report['circuit_svg_stack']['service_checks'] = {
                'schemdraw_svg': service_checks['schemdraw_svg'],
            }
            for name, passed in service_checks.items():
                if not passed:
                    report['errors'].append(f'lightweight service check failed: {name}')
        except Exception as exc:
            report['graph_stack']['service_checks'] = {'ok': False, 'error': str(exc)}
            report['formula_stack']['service_checks'] = {'ok': False, 'error': str(exc)}
            report['circuit_svg_stack']['service_checks'] = {'ok': False, 'error': str(exc)}
            report['errors'].append(f'lightweight service checks failed: {exc}')

    def _check_expert_system_stack(self, report):
        stack = report.setdefault('expert_stack', {})
        package_imports = {
            'jsonschema': 'jsonschema',
            'rule-engine': 'rule_engine',
            'pint': 'pint',
            'lark': 'lark',
            'z3-solver': 'z3',
            'scikit-fuzzy': 'skfuzzy',
        }
        for package_name, import_name in package_imports.items():
            try:
                module = __import__(import_name)
                try:
                    package_version = version(package_name)
                except PackageNotFoundError:
                    package_version = getattr(module, '__version__', 'unknown')
                stack[package_name] = {'ok': True, 'version': package_version}
            except Exception as exc:
                stack[package_name] = {'ok': False, 'error': str(exc)}
                report['errors'].append(f'expert stack package failed: {package_name} ({exc})')

        try:
            from Dolg_APP.services.cad_import import import_preview
            from Dolg_APP.services.constraint_solver import solve_design_constraints
            from Dolg_APP.services.engineering_units import parse_engineering_quantity
            from Dolg_APP.services.expert_rules import (
                build_expert_facts,
                evaluate_expert_rules,
                load_rule_pack,
            )
            from Dolg_APP.services.learning_by_review import learning_suggestions_from_review
            from Dolg_APP.services.review_i18n import build_metric_rows, localize_review_report
            from Dolg_APP.services.risk_scoring import assess_fuzzy_project_risk

            rule_pack = load_rule_pack()
            facts = build_expert_facts(
                connectivity={
                    'component_count': 3,
                    'connection_count': 2,
                    'has_ground': False,
                    'has_source': True,
                },
                bom={'missing_catalog': ['R1']},
                derating={'issues': []},
                measurements=[],
            )
            expert = evaluate_expert_rules(facts, rule_pack)
            unit = parse_engineering_quantity('10k', expected_unit='ohm')
            imported = import_preview('ltspice', 'V1 in 0 DC 5\nR1 in out 1k\nR2 out 0 2k\n.ac dec 10 1 1k')
            preview = imported.get('preview') or {}
            divider = solve_design_constraints('voltage_divider', {'vin': 9, 'target_vout': 3})
            fuzzy = assess_fuzzy_project_risk(
                thermal_margin_c=10, bom_risk_count=2, floating_count=1, warning_count=3
            )
            localized_review = localize_review_report(
                {
                    'status': 'critical',
                    'summary': '2 components, 1 connections, 1 errors, 0 warnings.',
                    'errors': ['Missing GND reference'],
                    'warnings': [],
                    'recommendations': ['Add GND before relying on simulation results.'],
                    'faults': [{'code': 'missing_ground', 'title': 'No ground reference'}],
                    'expert_findings': expert.get('findings', []),
                    'sections': {'expert_system': expert},
                }
            )
            metric_rows = build_metric_rows(
                {'components': 3, 'connections': 2, 'topology': 'voltage_divider'}
            )
            learning_suggestions = learning_suggestions_from_review(
                {
                    'errors': ['missing gnd'],
                    'warnings': [],
                    'recommendations': [],
                    'metrics': {'topology': 'voltage_divider'},
                }
            )

            service_checks = {
                'rule_pack': bool(rule_pack.get('rules')),
                'rule_engine_finding': any(
                    item.get('rule_id') == 'erc.missing_ground' for item in expert.get('findings', [])
                ),
                'pint_unit_parse': bool(unit.ok and abs(unit.value - 10000) < 1e-9),
                'lark_import_preview': bool(imported.get('ok') and imported.get('unsupported')),
                'cad_import_preview_details': bool(
                    preview.get('component_count') == 3
                    and preview.get('can_save_project')
                    and preview.get('analysis_directives')
                ),
                'learning_by_review': isinstance(learning_suggestions, list),
                'review_russian_i18n': bool(
                    localized_review.get('status_label') == 'критично'
                    and any('GND' in item and 'Нет' in item for item in localized_review.get('errors', []))
                    and any(
                        item.get('severity_label') == 'ошибка'
                        for item in localized_review.get('expert_findings', [])
                    )
                ),
                'review_metric_rows_ru': bool(
                    any(item.get('label') == 'Компоненты' for item in metric_rows)
                    and any(item.get('value') == 'делитель напряжения' for item in metric_rows)
                ),
                'z3_voltage_divider': bool(divider.get('ok') and divider.get('options')),
                'fuzzy_risk': bool(fuzzy.get('ok') and fuzzy.get('score') is not None),
            }
            stack['service_checks'] = service_checks
            for name, passed in service_checks.items():
                if not passed:
                    report['errors'].append(f'expert service check failed: {name}')
        except Exception as exc:
            stack['service_checks'] = {'ok': False, 'error': str(exc)}
            report['errors'].append(f'expert service checks failed: {exc}')

    def _check_catalog_filter_stack(self, report):
        stack = report.setdefault('catalog_filter_stack', {})
        try:
            from django.http import QueryDict

            from shop.services.catalog_filters import (
                apply_catalog_filters,
                build_active_filter_tags,
                parse_catalog_number,
                parse_range_expression,
                querystring_with,
            )

            checks = {
                'parse_10k': abs((parse_catalog_number('10k', 'ohm') or 0) - 10000) < 1e-9,
                'parse_10_kohm_ru': abs((parse_catalog_number('10 кОм', 'ohm') or 0) - 10000) < 1e-9,
                'parse_voltage_range': bool(parse_range_expression('V>=25')),
                'parse_power_range': bool(parse_range_expression('P 0.125..0.5')),
                'active_tag_url': 'manufacturer='
                not in build_active_filter_tags(
                    QueryDict('q=10k&manufacturer=vishay&mounting=SMD'),
                    '/',
                )[1]['remove_url'],
                'query_preserves_mounting': 'mounting=SMD'
                in querystring_with(
                    QueryDict('q=10k&mounting=SMD'),
                    'has_datasheet',
                    '1',
                ),
            }

            sample = list(Product.objects.select_related('category').all()[:50])
            if sample:
                filtered, _query = apply_catalog_filters(sample, QueryDict('has_datasheet=1'))
                checks['has_datasheet_filter'] = all(product.datasheet_url for product in filtered)
            else:
                checks['has_datasheet_filter'] = True

            stack['service_checks'] = checks
            for name, passed in checks.items():
                if not passed:
                    report['errors'].append(f'catalog filter service check failed: {name}')
        except Exception as exc:
            stack['service_checks'] = {'ok': False, 'error': str(exc)}
            report['errors'].append(f'catalog filter service checks failed: {exc}')

    def _check_datasheet_intelligence(self, report):
        stack = report.setdefault('datasheet_intelligence', {})
        try:
            from shop.services.datasheet_intelligence import dependency_status, extract_from_text

            deps = dependency_status()
            sample = extract_from_text(
                'NE555 precision timer. Pin configuration DIP-8. Absolute maximum ratings. '
                'Recommended operating conditions. Thermal resistance. Typical application circuit.',
                source_url='demo://ne555',
            )
            checks = {
                'pandas_available': deps.get('pandas', {}).get('ok', False),
                'metadata_extraction': sample.get('confidence', 0) >= 0.4,
                'pinout_keywords': bool(sample.get('fields', {}).get('pinout_keywords')),
                'absolute_maximum_ratings': bool(sample.get('fields', {}).get('absolute_maximum_ratings')),
            }
            stack['dependencies'] = deps
            stack['service_checks'] = checks
            for name, passed in checks.items():
                if not passed:
                    report['warnings'].append(f'datasheet intelligence optional check failed: {name}')
        except Exception as exc:
            stack['service_checks'] = {'ok': False, 'error': str(exc)}
            report['warnings'].append(f'datasheet intelligence optional checks failed: {exc}')

    def _check_artifact_stack(self, report):
        stack = report.setdefault('artifact_stack', {})
        package_imports = {
            'pypdf': 'pypdf',
            'python-docx': 'docx',
            'python-pptx': 'pptx',
            'ezdxf': 'ezdxf',
            'olefile': 'olefile',
        }
        for package_name, import_name in package_imports.items():
            try:
                module = __import__(import_name)
                try:
                    package_version = version(package_name)
                except PackageNotFoundError:
                    package_version = getattr(module, '__version__', 'unknown')
                stack[package_name] = {'ok': True, 'version': package_version}
            except Exception as exc:
                stack[package_name] = {'ok': False, 'error': str(exc)}
                report['errors'].append(f'artifact stack package failed: {package_name} ({exc})')

        try:
            import ezdxf

            from Dolg_APP.services.artifact_ingestion import (
                learning_tasks_from_artifact,
                parse_artifact,
                review_external_cad_artifacts,
                training_examples_from_artifact,
            )

            with tempfile.TemporaryDirectory() as tmpdir:
                tmp = Path(tmpdir)
                drc_path = tmp / 'demo.drc'
                drc_path.write_text(
                    'Error 1 -- Net VCC shorted to net GND at (10,20) R1-1\n'
                    '------\n'
                    '1 error(s) detected\n'
                    '0 warning(s) detected\n',
                    encoding='utf-8',
                )
                net_path = tmp / 'demo.net'
                net_path.write_text(
                    '[\nR1\n0805\n10k\n]\n'
                    '[\nC1\n0603\n100n\n]\n'
                    '(\nVCC\nR1-1\nC1-1\n)\n'
                    '(\nGND\nR1-2\nC1-2\n)\n',
                    encoding='utf-8',
                )
                dwg_path = tmp / 'demo.dwg'
                dwg_path.write_bytes(b'AC1027 demo dwg metadata only')
                ms14_path = tmp / 'demo.ms14'
                ms14_path.write_bytes(b'Multisim 14 demo payload')

                dxf_path = tmp / 'demo.dxf'
                doc = ezdxf.new('R2010')
                doc.modelspace().add_text('R1 10k').set_placement((0, 0))
                doc.modelspace().add_line((0, 0), (10, 0), dxfattribs={'layer': 'NET_VCC'})
                doc.saveas(dxf_path)

                drc = parse_artifact(drc_path)
                net = parse_artifact(net_path)
                dxf = parse_artifact(dxf_path)
                dwg = parse_artifact(dwg_path)
                ms14 = parse_artifact(ms14_path)

            external = review_external_cad_artifacts([drc, net, dxf, dwg, ms14])
            learning = learning_tasks_from_artifact(drc)
            training = training_examples_from_artifact(drc)
            drc_findings = ((drc.get('facts') or {}).get('check_report') or {}).get('findings') or []
            net_facts = (net.get('facts') or {}).get('cad_artifact') or {}
            dxf_facts = (dxf.get('facts') or {}).get('cad_artifact') or {}

            checks = {
                'pcad_drc_finding': bool(
                    drc_findings and drc_findings[0].get('rule_id') == 'external.pcad.short'
                ),
                'pcad_net_components': net_facts.get('component_count') == 2,
                'dxf_entities': dxf_facts.get('entity_count', 0) >= 2,
                'dwg_metadata_stub': dwg.get('status') == 'unsupported' and bool(dwg.get('warnings')),
                'ms14_metadata_stub': ms14.get('status') == 'unsupported' and bool(ms14.get('warnings')),
                'external_review_evidence': external.get('finding_count') == 1,
                'learning_by_artifact': bool(
                    learning and learning[0].get('rubric', {}).get('source_rule_id')
                ),
                'ai_training_examples': bool(training and training[0].get('kind') == 'drc_finding'),
            }
            stack['service_checks'] = checks
            for name, passed in checks.items():
                if not passed:
                    report['errors'].append(f'artifact service check failed: {name}')
        except Exception as exc:
            stack['service_checks'] = {'ok': False, 'error': str(exc)}
            report['errors'].append(f'artifact service checks failed: {exc}')

    def _check_product_media(self, report):
        products = list(Product.objects.select_related('category').all())
        missing = []
        broken = []
        forbidden = []
        image_usage = {}
        sample_images = []
        media_quality = audit_catalog_media_quality(products)
        report['media_quality'] = {
            'checked': media_quality['checked'],
            'ok': media_quality['ok'],
            'average_score': media_quality['average_score'],
            'error_count': media_quality['error_count'],
            'warning_count': media_quality['warning_count'],
            'imagehash_available': media_quality['imagehash_available'],
            'perceptual_duplicate_groups': media_quality['perceptual_duplicate_groups'],
        }

        for product in products:
            image_name = product.image.name if product.image else ''
            if not image_name:
                missing.append(product.slug)
                continue
            if not sample_images:
                sample_images.append(image_name)
            if image_name.startswith(f'{GENERATED_IMAGE_DIR}/') and image_name not in sample_images:
                sample_images.append(image_name)
            if is_forbidden_image_path(image_name):
                forbidden.append(f'{product.slug}: {image_name}')
            image_source = str((product.parameters or {}).get('image_source_url', '')).lower()
            if is_forbidden_image_path(image_source):
                forbidden.append(f'{product.slug}: {image_source}')
            if not is_allowed_product_image(product, image_name):
                forbidden.append(f'{product.slug}: not local/generated image policy ({image_name})')
            image_usage.setdefault(image_name, []).append(product.slug)
            path = Path(settings.MEDIA_ROOT) / image_name
            if not path.exists():
                broken.append(f'{product.slug}: {image_name}')

        if missing:
            report['warnings'].append(f'товары без фото: {len(missing)} ({", ".join(missing[:8])})')
        if broken:
            report['errors'].append(f'битые media-файлы товаров: {len(broken)} ({", ".join(broken[:6])})')
        if forbidden:
            report['errors'].append(
                f'товары нарушают no-Wikimedia image policy: {len(forbidden)} ({", ".join(forbidden[:6])})'
            )

        if media_quality['error_count']:
            sample = ', '.join(
                f'{item["slug"]}:{"/".join(item["errors"])}' for item in media_quality['errors'][:5]
            )
            report['errors'].append(f'media quality gate errors: {media_quality["error_count"]} ({sample})')
        if media_quality['warning_count']:
            report['warnings'].append(f'media quality gate warnings: {media_quality["warning_count"]}')
        if media_quality['perceptual_duplicate_groups']:
            report['warnings'].append(
                f'perceptual duplicate product images: {len(media_quality["perceptual_duplicate_groups"])}'
            )

        if sample_images and not broken:
            static_storage = {
                'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
            }
            with override_settings(
                ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'],
                STORAGES=static_storage,
                SECURE_SSL_REDIRECT=False,
                SESSION_COOKIE_SECURE=False,
                CSRF_COOKIE_SECURE=False,
            ):
                client = Client()
                for sample_image in sample_images[:2]:
                    response = client.get(f'{settings.MEDIA_URL}{sample_image}', follow=False)
                    if response.status_code != 200:
                        report['errors'].append(
                            f'media route does not serve product images: {settings.MEDIA_URL}{sample_image} -> HTTP {response.status_code}'
                        )

        duplicates = {image: slugs for image, slugs in image_usage.items() if len(slugs) > 1}
        if duplicates:
            sample = '; '.join(
                f'{image}: {", ".join(slugs[:4])}' for image, slugs in list(duplicates.items())[:4]
            )
            report['warnings'].append(f'повторяющиеся фото товаров: {len(duplicates)} ({sample})')

    def _check_knowledge_materials(self, report):
        broken_local = []
        for material in ArticleMaterial.objects.filter(is_public=True):
            href = material.href
            if not href:
                continue
            if href.startswith('/media/'):
                rel = href.replace(settings.MEDIA_URL, '', 1).lstrip('/')
                if not (Path(settings.MEDIA_ROOT) / rel).exists():
                    broken_local.append(f'{material.title}: {href}')
            elif href.startswith('/') and not self._looks_like_known_internal_route(href):
                report['warnings'].append(
                    f'подозрительная внутренняя ссылка материала: {material.title} -> {href}'
                )
        if broken_local:
            report['errors'].append(f'битые локальные материалы энциклопедии: {len(broken_local)}')

    def _check_legal_sources_stack(self, report):
        stack = report.setdefault('legal_sources_stack', {})
        try:
            from Dolg_APP.models import AITrainingExample
            from Dolg_APP.services.expert_rules import load_rule_pack
            from knowledge.services.legal_sources import (
                find_legal_sources,
                load_legal_sources,
                sources_for_rule,
                summarize_legal_sources,
                validate_source_ids,
            )
            from shop.views import _legal_source_results

            sources = load_legal_sources()
            summary = summarize_legal_sources(sources)
            urls = [item['url'] for item in sources]
            material_links = ArticleMaterial.objects.filter(
                is_public=True,
                url__in=urls,
            ).count()
            overview_exists = Article.objects.filter(
                slug='otkrytye-istochniki-i-dokumentatsiya-dolg',
                is_published=True,
            ).exists()
            stack.update(summary)
            stack['material_links'] = material_links
            stack['overview_article'] = overview_exists
            source_retrieval_ids = [item['id'] for item in find_legal_sources('gnd spice', limit=5)]
            rule_bibliography_sources = sources_for_rule('erc.missing_ground')
            rule_pack = load_rule_pack()
            rule_source_errors = []
            for rule in rule_pack.get('rules') or []:
                references = rule.get('references') if isinstance(rule.get('references'), dict) else {}
                missing = validate_source_ids(references.get('source_ids') or [])
                if missing:
                    rule_source_errors.append(
                        {
                            'rule_id': rule.get('id'),
                            'missing_source_ids': missing,
                        }
                    )
            learning_tasks_with_sources = 0
            for task in LearningTask.objects.filter(
                lesson__is_published=True, lesson__track__is_published=True
            ):
                rubric = task.rubric if isinstance(task.rubric, dict) else {}
                if rubric.get('source_ids'):
                    learning_tasks_with_sources += 1
            training_examples_with_sources = 0
            for example in AITrainingExample.objects.all()[:500]:
                features = example.features if isinstance(example.features, dict) else {}
                if (
                    features.get('source_ids')
                    or features.get('source_topics')
                    or features.get('teacher_rules')
                ):
                    training_examples_with_sources += 1
            source_search_results = _legal_source_results('ngspice')
            service_checks = {
                'source_retrieval': {'ngspice_docs', 'kicad_docs'}.issubset(source_retrieval_ids),
                'rule_bibliography': bool(rule_bibliography_sources),
                'rule_source_ids_valid': not rule_source_errors,
                'search_smoke': any(item.get('id') == 'ngspice_docs' for item in source_search_results),
                'learning_tasks_with_sources': learning_tasks_with_sources >= 8,
                'training_metadata': training_examples_with_sources >= 0,
            }
            stack['source_retrieval'] = source_retrieval_ids
            stack['rule_bibliography'] = [item.get('id') for item in rule_bibliography_sources]
            stack['rule_source_errors'] = rule_source_errors
            stack['search_smoke'] = bool(service_checks['search_smoke'])
            stack['learning_tasks_with_sources'] = learning_tasks_with_sources
            stack['training_examples_with_sources'] = training_examples_with_sources
            stack['service_checks'] = service_checks
            stack['ok'] = (
                summary['count'] >= 12
                and not summary['missing_topics']
                and summary['learning_sources'] >= 6
                and summary['ai_sources'] >= 6
                and overview_exists
                and material_links >= summary['count']
                and all(service_checks.values())
            )
            for name, passed in service_checks.items():
                if not passed:
                    report['errors'].append(f'legal sources service check failed: {name}')
            if summary['count'] < 12:
                report['errors'].append(f'legal sources count is too low: {summary["count"]}')
            if summary['missing_topics']:
                report['errors'].append(
                    'legal sources missing topics: ' + ', '.join(summary['missing_topics'])
                )
            if not overview_exists:
                report['warnings'].append('legal sources overview article is missing: run seed_legal_sources')
            if material_links < summary['count']:
                report['warnings'].append(
                    f'legal sources are not linked to knowledge materials: {material_links}/{summary["count"]}; '
                    'run seed_legal_sources'
                )
        except Exception as exc:
            stack['ok'] = False
            stack['error'] = str(exc)
            report['errors'].append(f'legal sources stack failed: {exc}')

    def _looks_like_known_internal_route(self, href):
        prefixes = (
            '/about/',
            '/demo/',
            '/search/',
            '/knowledge/',
            '/simulation/',
            '/cad/',
            '/projects/',
            '/cart/',
            '/compare/',
            '/category/',
            '/product/',
            settings.MEDIA_URL,
            settings.STATIC_URL if settings.STATIC_URL.startswith('/') else f'/{settings.STATIC_URL}',
        )
        return href.startswith(prefixes)

    def _check_files(self, report):
        base = Path(settings.BASE_DIR)
        required_files = [
            # Launcher-скрипты — переименованы 2026-05-25 (run_dolg.bat → start_local.bat,
            # Open_DOLG_Site.bat удалён как дубль). UI_CAD_SIM_AUDIT.md удалён 2026-05-25
            # как выполненный план (от 14.05).
            base / 'start_local.bat',
            base / 'start_public.bat',
            base / 'README.md',
            base / 'docs' / 'TESTS_AND_REPORTS.md',
            base / 'docs' / 'UNIFIED_ROADMAP_20260606.md',
            base / 'docs' / 'DEMO_SCENARIO.md',
            base / 'docs' / 'LEGAL_RESOURCE_MAP_20260526.md',
            base / 'knowledge' / 'data' / 'legal_sources.json',
            base / 'knowledge' / 'static' / 'knowledge' / 'legal_sources.svg',
            base / 'knowledge' / 'services' / 'legal_sources.py',
            base / 'knowledge' / 'management' / 'commands' / 'seed_legal_sources.py',
            base / 'Dolg_APP' / 'services' / 'project_review.py',
            base / 'Dolg_APP' / 'services' / 'expert_rules.py',
            base / 'Dolg_APP' / 'services' / 'engineering_units.py',
            base / 'Dolg_APP' / 'services' / 'constraint_solver.py',
            base / 'Dolg_APP' / 'services' / 'cad_parsers.py',
            base / 'Dolg_APP' / 'expert_rules' / 'default_rules.json',
            base / 'Dolg_APP' / 'services' / 'cad_import.py',
            base / 'Dolg_APP' / 'services' / 'learning_by_review.py',
            base / 'Dolg_APP' / 'services' / 'artifact_ingestion.py',
            base / 'Dolg_APP' / 'services' / 'artifact_learning.py',
            base / 'Dolg_APP' / 'management' / 'commands' / 'ingest_engineering_artifacts.py',
            base / 'Dolg_APP' / 'services' / 'rule_ai.py',
            base / 'Dolg_APP' / 'templates' / 'tools' / 'project_review.html',
            base / 'shop' / 'services' / 'media_quality.py',
            base / 'knowledge' / 'services' / 'lab_measurements.py',
            base / 'shop' / 'static' / 'simulation' / 'simulation-engine.js',
            base / 'shop' / 'static' / 'simulation' / 'scheme-netlist.js',
            base / 'shop' / 'static' / 'cad' / 'templates' / 'resistor-symbol.json',
        ]
        for path in required_files:
            if not path.exists():
                report['errors'].append(f'не найден обязательный файл: {path.relative_to(base)}')

        final_dir = base / 'docs' / 'final'
        if not final_dir.exists():
            report['warnings'].append('нет папки docs/final для финальных материалов')

    def _check_urls(self, report):
        urls = [
            reverse('shop:index'),
            reverse('shop:about'),
            reverse('shop:demo_route'),
            reverse('shop:global_search') + '?q=NE555',
            reverse('knowledge:index'),
            reverse('knowledge:engineering_lab'),
            reverse('knowledge:learning_index'),
            reverse('hello:simulation'),
            reverse('hello:cad'),
            reverse('hello:projects'),
            reverse('shop:cart'),
            reverse('shop:readyz'),
        ]

        static_storage = {
            'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
        }
        with override_settings(
            ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'],
            STORAGES=static_storage,
            SECURE_SSL_REDIRECT=False,
            SESSION_COOKIE_SECURE=False,
            CSRF_COOKIE_SECURE=False,
        ):
            client = Client()
            for url in urls:
                try:
                    response = client.get(url, follow=False)
                    status = response.status_code
                    report['urls'].append({'url': url, 'status': status})
                    if status >= 500:
                        report['errors'].append(f'{url}: HTTP {status}')
                    elif status in {404, 405}:
                        report['warnings'].append(f'{url}: HTTP {status}')
                except Exception as exc:
                    report['errors'].append(f'{url}: {exc}')

    def _print_human(self, report):
        self.stdout.write(self.style.SUCCESS('DOLG demo-ready report'))
        self.stdout.write('Counts:')
        for key, value in report['counts'].items():
            self.stdout.write(f'  {key}: {value}')
        self.stdout.write('URL smoke:')
        for item in report['urls']:
            self.stdout.write(f'  {item["status"]} {item["url"]}')
        if report.get('media_quality'):
            media = report['media_quality']
            self.stdout.write(
                f'Media quality: checked={media.get("checked")} '
                f'score={media.get("average_score")} '
                f'errors={media.get("error_count")} warnings={media.get("warning_count")}'
            )
        if report.get('scientific_stack'):
            self.stdout.write('Scientific stack:')
            for key, value in report['scientific_stack'].items():
                if key == 'service_checks':
                    service_status = ', '.join(f'{name}={passed}' for name, passed in value.items())
                    self.stdout.write(f'  service_checks: {service_status}')
                else:
                    self.stdout.write(f'  {key}: {value.get("version", "unknown")} ok={value.get("ok")}')
        if report.get('expert_stack'):
            self.stdout.write('Expert stack:')
            for key, value in report['expert_stack'].items():
                if key == 'service_checks':
                    service_status = ', '.join(f'{name}={passed}' for name, passed in value.items())
                    self.stdout.write(f'  service_checks: {service_status}')
                else:
                    self.stdout.write(f'  {key}: {value.get("version", "unknown")} ok={value.get("ok")}')
        if report['warnings']:
            self.stdout.write(self.style.WARNING('Warnings:'))
            for item in report['warnings']:
                self.stdout.write(f'  - {item}')
        if report['errors']:
            self.stdout.write(self.style.ERROR('Errors:'))
            for item in report['errors']:
                self.stdout.write(f'  - {item}')
        if report['ok']:
            self.stdout.write(self.style.SUCCESS('OK: критичных проблем для демонстрации не найдено.'))
