"""Safe AI training data collection for opted-in DOLG projects.

The live assistant never mutates its own model.  This service only prepares
curated examples that a human or a management command can later use for a
periodic PyTorch training run.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from django.contrib.auth import get_user_model
from django.utils import timezone

from Dolg_APP.ml.neural import (
    NEXT_COMPONENT_LABELS,
    TOPOLOGY_LABELS,
    _detect_teacher_topology,
    _next_component_teacher,
    _risk_teacher,
    scheme_to_features,
)
from Dolg_APP.models import AITrainingExample, EngineeringArtifact, Organization, ProjectEvent, ProjectReview, SchematicProject
from Dolg_APP.services.project_review import build_design_review
from knowledge.services.legal_sources import (
    source_ids_for_learning_topic,
    source_ids_for_rule,
    sources_by_ids,
    validate_source_ids,
)


def user_allows_ai_training(user) -> bool:
    try:
        return bool(user.profile.allow_ai_training)
    except Exception:
        return False


def project_can_feed_ai_training(project: SchematicProject) -> bool:
    if project is None or not getattr(project, 'pk', None):
        return False
    if project.deleted_at is not None:
        return False
    if not isinstance(project.scheme_data, dict):
        return False
    if not project.scheme_data.get('components'):
        return False
    return bool(project.is_demo or user_allows_ai_training(project.user))


def build_scheme_training_payload(project: SchematicProject) -> dict[str, Any]:
    scheme = project.scheme_data or {}
    review = build_design_review(project, simulation_runs=[], measurements=[])
    topology = _detect_teacher_topology(scheme)
    risk_score = round(float(_risk_teacher(scheme)), 4)
    next_component = _next_component_teacher(scheme)
    components = scheme.get('components') or []
    connections = scheme.get('connections') or []

    prompt = (
        f"Разбери схему `{project.name}`: компонентов {len(components)}, "
        f"соединений {len(connections)}. Определи топологию, риск и следующий шаг."
    )
    warnings = (review.get('warnings') or [])[:5]
    errors = (review.get('errors') or [])[:5]
    evidence = _source_metadata_from_review(review)
    target_parts = [
        f"topology={topology}",
        f"risk_score={risk_score}",
        f"next_component={next_component}",
        f"review_score={review.get('score', 0)}",
        f"status={review.get('status', '')}",
    ]
    if errors:
        target_parts.append('errors=' + '; '.join(str(item) for item in errors))
    if warnings:
        target_parts.append('warnings=' + '; '.join(str(item) for item in warnings))
    if evidence['teacher_rules']:
        target_parts.append('teacher_rules=' + ', '.join(evidence['teacher_rules'][:6]))
    if evidence['source_ids']:
        target_parts.append('source_ids=' + ', '.join(evidence['source_ids'][:6]))

    return {
        'kind': 'review_hint',
        'prompt': prompt,
        'target': '\n'.join(target_parts),
        'features': {
            'source': 'user_opt_in_scheme' if not project.is_demo else 'demo_scheme',
            'evidence_kind': 'review_rule' if evidence['teacher_rules'] else (
                'demo_scheme' if project.is_demo else 'user_opt_in_scheme'
            ),
            'project_id': project.id,
            'project_name': project.name,
            'scheme_data': scheme,
            'feature_vector': scheme_to_features(scheme),
            'topology': topology,
            'risk_score': risk_score,
            'next_component': next_component,
            'review_score': review.get('score', 0),
            'review_status': review.get('status', ''),
            'component_count': len(components),
            'connection_count': len(connections),
            'source_ids': evidence['source_ids'],
            'source_topics': evidence['source_topics'],
            'teacher_rules': evidence['teacher_rules'],
        },
        'review': review,
    }


def upsert_scheme_training_example(project: SchematicProject, *, validate: bool = True, dry_run: bool = False):
    payload = build_scheme_training_payload(project)
    if dry_run:
        return {
            'created': False,
            'updated': False,
            'dry_run': True,
            'project_id': project.id,
            'payload': payload,
        }

    existing = AITrainingExample.objects.filter(
        project=project,
        kind=payload['kind'],
        features__source=payload['features']['source'],
    ).first()
    if existing:
        existing.prompt = payload['prompt']
        existing.target = payload['target']
        existing.features = payload['features']
        existing.is_validated = bool(validate)
        existing.save(update_fields=['prompt', 'target', 'features', 'is_validated'])
        return {'created': False, 'updated': True, 'example': existing}

    example = AITrainingExample.objects.create(
        project=project,
        user=project.user,
        kind=payload['kind'],
        prompt=payload['prompt'],
        target=payload['target'],
        features=payload['features'],
        is_validated=bool(validate),
    )
    return {'created': True, 'updated': False, 'example': example}


def collect_opt_in_scheme_examples(*, user=None, limit: int = 100, validate: bool = True, dry_run: bool = False) -> dict[str, Any]:
    qs = (
        SchematicProject.all_objects
        .select_related('user', 'user__profile')
        .filter(deleted_at__isnull=True)
        .exclude(scheme_data={})
        .order_by('-updated_at')
    )
    if user is not None:
        qs = qs.filter(user=user)

    scanned = 0
    skipped = 0
    created = 0
    updated = 0
    examples = []
    for project in qs[: max(1, int(limit))]:
        scanned += 1
        if not project_can_feed_ai_training(project):
            skipped += 1
            continue
        if dry_run:
            scheme = project.scheme_data or {}
            components = scheme.get('components') or []
            connections = scheme.get('connections') or []
            examples.append({
                'project_id': project.id,
                'project': project.name,
                'created': False,
                'updated': False,
                'dry_run': True,
                'topology': _detect_teacher_topology(scheme),
                'risk_score': round(float(_risk_teacher(scheme)), 4),
                'next_component': _next_component_teacher(scheme),
                'component_count': len(components),
                'connection_count': len(connections),
            })
            continue
        result = upsert_scheme_training_example(project, validate=validate, dry_run=dry_run)
        created += int(bool(result.get('created')))
        updated += int(bool(result.get('updated')))
        example = result.get('example')
        examples.append({
            'project_id': project.id,
            'project': project.name,
            'created': bool(result.get('created')),
            'updated': bool(result.get('updated')),
            'example_id': getattr(example, 'id', None),
            'topology': (result.get('payload') or {}).get('features', {}).get('topology')
                if dry_run else (example.features or {}).get('topology'),
        })

    return {
        'ok': True,
        'scanned': scanned,
        'skipped': skipped,
        'created': created,
        'updated': updated,
        'dry_run': dry_run,
        'examples': examples,
    }


def collect_learning_task_examples(*, limit: int = 200, validate: bool = True, dry_run: bool = False) -> dict[str, Any]:
    """Create curated examples from learning tasks.

    The model does not train on copied external text.  It receives only local
    task prompts, rubrics and source metadata already stored in DOLG.
    """
    from knowledge.models import LearningTask

    qs = (
        LearningTask.objects
        .select_related('lesson', 'lesson__track')
        .filter(lesson__is_published=True, lesson__track__is_published=True)
        .order_by('lesson__track__order', 'lesson__order', 'order')[:max(1, int(limit))]
    )
    created = updated = skipped = scanned = 0
    rows = []
    for task in qs:
        scanned += 1
        rubric = task.rubric if isinstance(task.rubric, dict) else {}
        source_ids = list(dict.fromkeys(
            [str(item) for item in rubric.get('source_ids') or [] if str(item).strip()]
            + source_ids_for_learning_topic(rubric.get('source_topic') or task.lesson.slug or task.title)
        ))
        teacher_rules = [str(item) for item in rubric.get('teacher_rule', [])] if isinstance(rubric.get('teacher_rule'), list) else []
        if isinstance(rubric.get('teacher_rule'), str):
            teacher_rules.append(rubric['teacher_rule'])
        prompt = f'Реши или объясни учебное задание: {task.title}\n\n{task.prompt}'
        target = _learning_target(task, rubric)
        if not task.prompt or not target:
            skipped += 1
            continue
        payload = {
            'kind': 'review_hint',
            'prompt': prompt[:4000],
            'target': target[:4000],
            'features': {
                'source': 'learning_task',
                'evidence_kind': 'learning_task',
                'learning_task_id': task.id,
                'learning_lesson_id': task.lesson_id,
                'learning_track_id': task.lesson.track_id,
                'task_type': task.task_type,
                'source_ids': source_ids,
                'source_topics': [rubric.get('source_topic') or task.lesson.slug or task.task_type],
                'teacher_rules': list(dict.fromkeys(teacher_rules)),
            },
        }
        if dry_run:
            rows.append({'task_id': task.id, 'title': task.title, 'dry_run': True})
            continue
        example, was_created = AITrainingExample.objects.update_or_create(
            kind=payload['kind'],
            features__source='learning_task',
            features__learning_task_id=task.id,
            defaults={
                'prompt': payload['prompt'],
                'target': payload['target'],
                'features': payload['features'],
                'is_validated': bool(validate),
            },
        )
        created += int(was_created)
        updated += int(not was_created)
        rows.append({'task_id': task.id, 'example_id': example.id, 'created': was_created})
    return {
        'ok': True,
        'source': 'learning_tasks',
        'scanned': scanned,
        'skipped': skipped,
        'created': created,
        'updated': updated,
        'dry_run': dry_run,
        'examples': rows,
    }


def collect_review_examples(*, limit: int = 200, validate: bool = True, dry_run: bool = False) -> dict[str, Any]:
    """Create examples from saved ProjectReview snapshots."""
    qs = ProjectReview.objects.select_related('project', 'user').order_by('-created_at')[:max(1, int(limit))]
    created = updated = skipped = scanned = 0
    rows = []
    for review in qs:
        scanned += 1
        findings = _review_findings(review)
        if not findings:
            skipped += 1
            continue
        source_ids = []
        teacher_rules = []
        for finding in findings:
            rule_id = str(finding.get('rule_id') or finding.get('id') or '').strip()
            if rule_id:
                teacher_rules.append(rule_id)
                source_ids.extend(source_ids_for_rule(rule_id))
            references = finding.get('references') if isinstance(finding.get('references'), dict) else {}
            source_ids.extend(str(item) for item in references.get('source_ids') or [] if str(item).strip())
        source_ids = list(dict.fromkeys(source_ids))
        teacher_rules = list(dict.fromkeys(teacher_rules))
        first = findings[0]
        prompt = (
            f'Объясни engineering review для проекта `{review.project.name}`: '
            f'score={review.score}, status={review.status}.'
        )
        target = '\n'.join([
            f'rule={first.get("rule_id") or first.get("id") or "review"}',
            f'severity={first.get("severity") or review.status}',
            f'evidence={first.get("evidence") or first.get("title") or review.summary}',
            f'recommendation={first.get("recommendation") or "; ".join(review.recommendations or [])}',
        ])
        features = {
            'source': 'project_review',
            'evidence_kind': 'review_rule',
            'project_id': review.project_id,
            'review_id': review.id,
            'review_score': review.score,
            'review_status': review.status,
            'source_ids': source_ids,
            'source_topics': _source_topics(source_ids),
            'teacher_rules': teacher_rules,
            'scheme_data': review.scheme_data or review.project.scheme_data,
            'feature_vector': scheme_to_features(review.scheme_data or review.project.scheme_data),
            'topology': _detect_teacher_topology(review.scheme_data or review.project.scheme_data),
            'risk_score': round(float(_risk_teacher(review.scheme_data or review.project.scheme_data)), 4),
            'next_component': _next_component_teacher(review.scheme_data or review.project.scheme_data),
        }
        if dry_run:
            rows.append({'review_id': review.id, 'dry_run': True})
            continue
        example, was_created = AITrainingExample.objects.update_or_create(
            kind='drc_finding',
            project=review.project,
            features__source='project_review',
            features__review_id=review.id,
            defaults={
                'user': review.user,
                'prompt': prompt[:4000],
                'target': target[:4000],
                'features': features,
                'is_validated': bool(validate),
            },
        )
        created += int(was_created)
        updated += int(not was_created)
        rows.append({'review_id': review.id, 'example_id': example.id, 'created': was_created})
    return {
        'ok': True,
        'source': 'project_reviews',
        'scanned': scanned,
        'skipped': skipped,
        'created': created,
        'updated': updated,
        'dry_run': dry_run,
        'examples': rows,
    }


def collect_artifact_examples(*, limit: int = 200, validate: bool = False, dry_run: bool = False) -> dict[str, Any]:
    """Create examples from parsed engineering artifacts."""
    qs = EngineeringArtifact.objects.select_related('project', 'user').order_by('-created_at')[:max(1, int(limit))]
    created = updated = skipped = scanned = 0
    rows = []
    for artifact in qs:
        scanned += 1
        summary = (artifact.summary or '').strip()
        if not summary:
            skipped += 1
            continue
        features = {
            'source': 'engineering_artifact',
            'evidence_kind': 'artifact_summary',
            'artifact_id': artifact.id,
            'artifact_type': artifact.artifact_type,
            'parser': artifact.parser,
            'status': artifact.status,
            'warnings_count': len(artifact.warnings or []),
            'errors_count': len(artifact.errors or []),
        }
        if dry_run:
            rows.append({'artifact_id': artifact.id, 'dry_run': True})
            continue
        example, was_created = AITrainingExample.objects.update_or_create(
            artifact=artifact,
            kind='artifact_summary',
            defaults={
                'project': artifact.project,
                'user': artifact.user,
                'prompt': f'Кратко объясни инженерный артефакт: {artifact.source_name}',
                'target': summary[:4000],
                'features': features,
                'is_validated': bool(validate),
            },
        )
        created += int(was_created)
        updated += int(not was_created)
        rows.append({'artifact_id': artifact.id, 'example_id': example.id, 'created': was_created})
    return {
        'ok': True,
        'source': 'engineering_artifacts',
        'scanned': scanned,
        'skipped': skipped,
        'created': created,
        'updated': updated,
        'dry_run': dry_run,
        'examples': rows,
    }


CURATED_AI_CASES: list[dict[str, Any]] = [
    {
        'case_id': 'divider_9v_to_3v_ok',
        'title': 'Делитель 9 В -> около 3 В',
        'kind': 'review_hint',
        'rule_ids': ['topology.divider_without_output'],
        'source_topic': 'divider',
        'scheme_data': {
            'components': [
                {'id': 'v1', 'type': 'battery', 'voltage': '9V'},
                {'id': 'r1', 'type': 'resistor', 'resistance': '20k'},
                {'id': 'r2', 'type': 'resistor', 'resistance': '10k'},
                {'id': 'gnd', 'type': 'ground'},
            ],
            'connections': [
                {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
                {'from': {'compId': 'r1'}, 'to': {'compId': 'r2'}, 'node': 'vout'},
                {'from': {'compId': 'r2'}, 'to': {'compId': 'gnd'}},
            ],
        },
        'target_extra': 'expected_metric=Vout≈3V; next_step=измерить Vout и проверить нагрузку',
    },
    {
        'case_id': 'divider_missing_ground',
        'title': 'Делитель без общей земли',
        'kind': 'drc_finding',
        'rule_ids': ['erc.missing_ground'],
        'source_topic': 'gnd',
        'scheme_data': {
            'components': [
                {'id': 'v1', 'type': 'battery', 'voltage': '9V'},
                {'id': 'r1', 'type': 'resistor', 'resistance': '20k'},
                {'id': 'r2', 'type': 'resistor', 'resistance': '10k'},
            ],
            'connections': [
                {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
                {'from': {'compId': 'r1'}, 'to': {'compId': 'r2'}},
            ],
        },
        'target_extra': 'finding=нет GND; recommendation=добавить ground reference перед симуляцией',
    },
    {
        'case_id': 'led_indicator_ok',
        'title': 'LED-индикатор с токоограничивающим резистором',
        'kind': 'review_hint',
        'rule_ids': [],
        'source_topic': 'ohm',
        'scheme_data': {
            'components': [
                {'id': 'v1', 'type': 'battery', 'voltage': '5V'},
                {'id': 'r1', 'type': 'resistor', 'resistance': '330'},
                {'id': 'led1', 'type': 'led', 'forward_voltage': '2V'},
                {'id': 'gnd', 'type': 'ground'},
            ],
            'connections': [
                {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
                {'from': {'compId': 'r1'}, 'to': {'compId': 'led1'}},
                {'from': {'compId': 'led1'}, 'to': {'compId': 'gnd'}},
            ],
        },
        'target_extra': 'expected_metric=Iled≈9mA; next_step=проверить мощность резистора',
    },
    {
        'case_id': 'led_no_resistor',
        'title': 'LED без токоограничения',
        'kind': 'drc_finding',
        'rule_ids': ['derating.power_or_thermal_risk'],
        'source_topic': 'ohm',
        'scheme_data': {
            'components': [
                {'id': 'v1', 'type': 'battery', 'voltage': '5V'},
                {'id': 'led1', 'type': 'led', 'forward_voltage': '2V'},
                {'id': 'gnd', 'type': 'ground'},
            ],
            'connections': [
                {'from': {'compId': 'v1'}, 'to': {'compId': 'led1'}},
                {'from': {'compId': 'led1'}, 'to': {'compId': 'gnd'}},
            ],
        },
        'target_extra': 'finding=LED без резистора; recommendation=добавить токоограничивающий резистор',
    },
    {
        'case_id': 'rc_low_pass_1khz',
        'title': 'RC-фильтр НЧ около 1 кГц',
        'kind': 'review_hint',
        'rule_ids': ['simulation.no_saved_measurements'],
        'source_topic': 'rc',
        'scheme_data': {
            'components': [
                {'id': 'v1', 'type': 'battery', 'voltage': '5V'},
                {'id': 'r1', 'type': 'resistor', 'resistance': '1.6k'},
                {'id': 'c1', 'type': 'capacitor', 'capacitance': '100nF'},
                {'id': 'gnd', 'type': 'ground'},
            ],
            'connections': [
                {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
                {'from': {'compId': 'r1'}, 'to': {'compId': 'c1'}, 'node': 'vout'},
                {'from': {'compId': 'c1'}, 'to': {'compId': 'gnd'}},
            ],
        },
        'target_extra': 'expected_metric=fc≈995Hz; next_step=построить Bode и найти -3 dB',
    },
    {
        'case_id': 'floating_fragment',
        'title': 'Оторванный фрагмент схемы',
        'kind': 'drc_finding',
        'rule_ids': ['topology.floating_fragments'],
        'source_topic': 'drc',
        'scheme_data': {
            'components': [
                {'id': 'v1', 'type': 'battery', 'voltage': '5V'},
                {'id': 'r1', 'type': 'resistor', 'resistance': '1k'},
                {'id': 'gnd', 'type': 'ground'},
                {'id': 'c1', 'type': 'capacitor', 'capacitance': '100nF'},
            ],
            'connections': [
                {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
                {'from': {'compId': 'r1'}, 'to': {'compId': 'gnd'}},
            ],
        },
        'target_extra': 'finding=floating fragment; recommendation=подключить C1 к нужному узлу или удалить',
    },
    {
        'case_id': 'bare_source_short_to_ground',
        'title': 'Источник закорочен на землю',
        'kind': 'drc_finding',
        'rule_ids': ['erc.source_short_to_ground'],
        'source_topic': 'spice',
        'scheme_data': {
            'components': [
                {'id': 'v1', 'type': 'battery', 'voltage': '12V'},
                {'id': 'gnd', 'type': 'ground'},
            ],
            'connections': [
                {'from': {'compId': 'v1'}, 'to': {'compId': 'gnd'}},
            ],
        },
        'target_extra': 'finding=source short to ground; recommendation=разорвать короткое замыкание',
    },
    {
        'case_id': 'generic_ic_needs_bom_binding',
        'title': 'Микросхема без привязки к товару и модели',
        'kind': 'review_hint',
        'rule_ids': ['bom.missing_catalog_binding'],
        'source_topic': 'spice',
        'scheme_data': {
            'components': [
                {'id': 'v1', 'type': 'battery', 'voltage': '5V'},
                {'id': 'u1', 'type': 'ic', 'part_number': 'NE555'},
                {'id': 'r1', 'type': 'resistor', 'resistance': '10k'},
                {'id': 'c1', 'type': 'capacitor', 'capacitance': '100nF'},
                {'id': 'gnd', 'type': 'ground'},
            ],
            'connections': [
                {'from': {'compId': 'v1'}, 'to': {'compId': 'u1'}},
                {'from': {'compId': 'u1'}, 'to': {'compId': 'r1'}},
                {'from': {'compId': 'r1'}, 'to': {'compId': 'c1'}},
                {'from': {'compId': 'c1'}, 'to': {'compId': 'gnd'}},
            ],
        },
        'target_extra': 'recommendation=связать U1 с товаром, datasheet, SPICE-моделью и footprint',
    },
]


def seed_curated_ai_examples(*, validate: bool = True, dry_run: bool = False) -> dict[str, Any]:
    """Seed small, high-signal examples for the neural deep-hint baseline."""
    created = updated = 0
    rows = []
    for case in CURATED_AI_CASES:
        scheme = case['scheme_data']
        rule_ids = list(dict.fromkeys(case.get('rule_ids') or []))
        source_ids = []
        for rule_id in rule_ids:
            source_ids.extend(source_ids_for_rule(rule_id))
        source_ids.extend(source_ids_for_learning_topic(case.get('source_topic') or ''))
        source_ids = list(dict.fromkeys(source_ids))
        topology = _detect_teacher_topology(scheme)
        risk_score = round(float(_risk_teacher(scheme)), 4)
        next_component = _next_component_teacher(scheme)
        prompt = (
            f"Разбери curated-сценарий `{case['title']}`. "
            "Определи топологию, риск, следующий компонент или проверку."
        )
        target = '\n'.join([
            f'topology={topology}',
            f'risk_score={risk_score}',
            f'next_component={next_component}',
            case.get('target_extra') or '',
        ]).strip()
        features = {
            'source': 'curated_demo_case',
            'evidence_kind': 'curated_demo_case',
            'case_id': case['case_id'],
            'scheme_data': scheme,
            'feature_vector': scheme_to_features(scheme),
            'topology': topology,
            'risk_score': risk_score,
            'next_component': next_component,
            'component_count': len(scheme.get('components') or []),
            'connection_count': len(scheme.get('connections') or []),
            'source_ids': source_ids,
            'source_topics': _source_topics(source_ids) or [case.get('source_topic') or ''],
            'teacher_rules': rule_ids,
        }
        if dry_run:
            rows.append({
                'case_id': case['case_id'],
                'title': case['title'],
                'topology': topology,
                'risk_score': risk_score,
                'next_component': next_component,
                'dry_run': True,
            })
            continue
        example, was_created = AITrainingExample.objects.update_or_create(
            kind=case.get('kind') or 'review_hint',
            features__source='curated_demo_case',
            features__case_id=case['case_id'],
            defaults={
                'prompt': prompt,
                'target': target,
                'features': features,
                'is_validated': bool(validate),
            },
        )
        created += int(was_created)
        updated += int(not was_created)
        rows.append({
            'case_id': case['case_id'],
            'example_id': example.id,
            'created': was_created,
            'topology': topology,
            'risk_score': risk_score,
        })
    return {
        'ok': True,
        'source': 'curated_demo_cases',
        'scanned': len(CURATED_AI_CASES),
        'created': created,
        'updated': updated,
        'dry_run': dry_run,
        'examples': rows,
    }


def summarize_ai_training_examples() -> dict[str, Any]:
    """Dataset dashboard for admin, Grafana bridge and reports."""
    qs = AITrainingExample.objects.all().order_by('-created_at')
    total = qs.count()
    validated = qs.filter(is_validated=True).count()
    by_kind: Counter[str] = Counter()
    by_evidence: Counter[str] = Counter()
    by_topology: Counter[str] = Counter()
    by_source: Counter[str] = Counter()
    by_rule: Counter[str] = Counter()
    by_source_id: Counter[str] = Counter()
    by_family: Counter[str] = Counter()
    by_complexity: Counter[str] = Counter()
    by_quality: Counter[str] = Counter()
    with_scheme = 0
    with_sources = 0
    with_rules = 0
    for example in qs.only('kind', 'features', 'is_validated'):
        features = example.features if isinstance(example.features, dict) else {}
        by_kind[example.kind] += 1
        by_evidence[features.get('evidence_kind') or 'unknown'] += 1
        by_source[features.get('source') or 'unknown'] += 1
        topology = features.get('topology')
        if topology:
            by_topology[topology] += 1
        if features.get('family'):
            by_family[str(features['family'])] += 1
        if features.get('complexity_label'):
            by_complexity[str(features['complexity_label'])] += 1
        if features.get('quality_label'):
            by_quality[str(features['quality_label'])] += 1
        if isinstance(features.get('scheme_data'), dict):
            with_scheme += 1
        source_ids = features.get('source_ids') or []
        teacher_rules = features.get('teacher_rules') or []
        if source_ids:
            with_sources += 1
        if teacher_rules:
            with_rules += 1
        for source_id in source_ids:
            by_source_id[str(source_id)] += 1
        for rule_id in teacher_rules:
            by_rule[str(rule_id)] += 1
    latest = qs.first()
    return {
        'ok': True,
        'total': total,
        'validated': validated,
        'unvalidated': total - validated,
        'validation_ratio': round(validated / total, 4) if total else 0.0,
        'with_scheme_data': with_scheme,
        'with_source_ids': with_sources,
        'with_teacher_rules': with_rules,
        'by_kind': dict(by_kind.most_common()),
        'by_evidence_kind': dict(by_evidence.most_common()),
        'by_source': dict(by_source.most_common()),
        'by_topology': dict(by_topology.most_common()),
        'by_scheme_family': dict(by_family.most_common()),
        'by_complexity': dict(by_complexity.most_common()),
        'by_quality': dict(by_quality.most_common()),
        'top_rules': dict(by_rule.most_common(12)),
        'top_source_ids': dict(by_source_id.most_common(12)),
        'latest_example_at': latest.created_at.isoformat() if latest else '',
    }


def validate_ai_training_examples(*, include_unvalidated: bool = True, limit: int | None = None) -> dict[str, Any]:
    qs = AITrainingExample.objects.all().order_by('-created_at')
    if not include_unvalidated:
        qs = qs.filter(is_validated=True)
    if limit:
        qs = qs[:max(1, int(limit))]
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    scanned = 0
    for example in qs:
        scanned += 1
        features = example.features if isinstance(example.features, dict) else {}
        context = {'id': example.id, 'kind': example.kind}
        if not (example.prompt or '').strip():
            errors.append({**context, 'code': 'missing_prompt', 'message': 'AITrainingExample.prompt is empty'})
        if not (example.target or '').strip():
            errors.append({**context, 'code': 'missing_target', 'message': 'AITrainingExample.target is empty'})
        if not isinstance(example.features, dict):
            errors.append({**context, 'code': 'invalid_features', 'message': 'features must be JSON object'})
            continue
        unknown_sources = validate_source_ids(features.get('source_ids') or [])
        for source_id in unknown_sources:
            errors.append({**context, 'code': 'unknown_source_id', 'message': f'Unknown legal source id: {source_id}'})
        scheme = features.get('scheme_data')
        if scheme is not None:
            if not isinstance(scheme, dict):
                errors.append({**context, 'code': 'invalid_scheme_data', 'message': 'scheme_data must be object'})
            elif not scheme.get('components'):
                warnings.append({**context, 'code': 'empty_scheme_data', 'message': 'scheme_data has no components'})
            else:
                vector = features.get('feature_vector')
                if not isinstance(vector, list):
                    warnings.append({**context, 'code': 'missing_feature_vector', 'message': 'scheme example has no feature_vector'})
                elif len(vector) != len(scheme_to_features(scheme)):
                    warnings.append({
                        **context,
                        'code': 'stale_feature_vector',
                        'message': f'feature_vector length is {len(vector)}, expected {len(scheme_to_features(scheme))}',
                    })
        if features.get('topology') and features['topology'] not in TOPOLOGY_LABELS:
            warnings.append({**context, 'code': 'unknown_topology', 'message': f'Unknown topology label: {features["topology"]}'})
        if features.get('next_component') and features['next_component'] not in NEXT_COMPONENT_LABELS:
            warnings.append({**context, 'code': 'unknown_next_component', 'message': f'Unknown next component: {features["next_component"]}'})
        if example.is_validated and not features.get('evidence_kind'):
            warnings.append({**context, 'code': 'missing_evidence_kind', 'message': 'validated example has no evidence_kind'})
    return {
        'ok': not errors,
        'scanned': scanned,
        'errors_count': len(errors),
        'warnings_count': len(warnings),
        'errors': errors[:100],
        'warnings': warnings[:100],
        'summary': summarize_ai_training_examples(),
    }


def export_ai_training_dataset(
    path: str | Path,
    *,
    validated_only: bool = True,
    include_scheme_data: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    """Export dataset as JSONL for reproducible training/evaluation."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    qs = AITrainingExample.objects.all().order_by('id')
    if validated_only:
        qs = qs.filter(is_validated=True)
    if limit:
        qs = qs[:max(1, int(limit))]
    count = 0
    by_kind: Counter[str] = Counter()
    with out_path.open('w', encoding='utf-8') as fh:
        for example in qs:
            features = dict(example.features or {})
            if not include_scheme_data:
                features.pop('scheme_data', None)
            row = {
                'id': example.id,
                'kind': example.kind,
                'prompt': example.prompt,
                'target': example.target,
                'features': features,
                'is_validated': example.is_validated,
                'created_at': example.created_at.isoformat(),
            }
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
            count += 1
            by_kind[example.kind] += 1
    stats_path = out_path.with_suffix('.stats.json')
    stats = {
        'ok': True,
        'path': str(out_path),
        'stats_path': str(stats_path),
        'count': count,
        'validated_only': validated_only,
        'include_scheme_data': include_scheme_data,
        'by_kind': dict(by_kind.most_common()),
        'exported_at': timezone.now().isoformat(),
    }
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')
    return stats


def curated_training_schemes(*, limit: int = 200) -> list[dict[str, Any]]:
    schemes = []
    qs = AITrainingExample.objects.filter(
        is_validated=True,
        features__scheme_data__isnull=False,
    ).order_by('-created_at')[: max(1, int(limit))]
    for example in qs:
        scheme = (example.features or {}).get('scheme_data')
        if isinstance(scheme, dict) and scheme.get('components'):
            scheme_copy = json.loads(json.dumps(scheme))
            scheme_copy['__training_metadata'] = {
                'source_ids': (example.features or {}).get('source_ids') or [],
                'source_topics': (example.features or {}).get('source_topics') or [],
                'teacher_rules': (example.features or {}).get('teacher_rules') or [],
                'evidence_kind': (example.features or {}).get('evidence_kind') or '',
            }
            schemes.append(scheme_copy)
    return schemes


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    a = [float(item or 0.0) for item in left[:size]]
    b = [float(item or 0.0) for item in right[:size]]
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if not norm_a or not norm_b:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def find_similar_training_examples(
    scheme_data: dict[str, Any],
    *,
    limit: int = 3,
    validated_only: bool = True,
    scan_limit: int = 500,
) -> list[dict[str, Any]]:
    """Return nearest validated AI examples for explainable deep hints.

    This is deliberately a lightweight in-process search over structured
    features. It does not read external books or raw source texts.
    """
    if not isinstance(scheme_data, dict) or not scheme_data.get('components'):
        return []
    target_vector = scheme_to_features(scheme_data)
    qs = AITrainingExample.objects.all().order_by('-created_at')
    if validated_only:
        qs = qs.filter(is_validated=True)
    rows: list[dict[str, Any]] = []
    for example in qs.only('id', 'kind', 'prompt', 'target', 'features', 'is_validated')[:max(1, int(scan_limit))]:
        features = example.features if isinstance(example.features, dict) else {}
        scheme = features.get('scheme_data')
        if not isinstance(scheme, dict) or not scheme.get('components'):
            continue
        vector = features.get('feature_vector')
        if not isinstance(vector, list) or len(vector) != len(target_vector):
            vector = scheme_to_features(scheme)
        score = _cosine_similarity(target_vector, vector)
        if score <= 0:
            continue
        rows.append({
            'id': example.id,
            'kind': example.kind,
            'score': round(score, 4),
            'prompt': (example.prompt or '')[:180],
            'topology': features.get('topology') or '',
            'risk_score': features.get('risk_score'),
            'next_component': features.get('next_component') or '',
            'evidence_kind': features.get('evidence_kind') or '',
            'source_ids': (features.get('source_ids') or [])[:4],
            'teacher_rules': (features.get('teacher_rules') or [])[:4],
        })
    rows.sort(key=lambda item: item['score'], reverse=True)
    return rows[:max(1, int(limit))]


def _scheme_complexity_label(score: int) -> str:
    if score >= 80:
        return 'advanced'
    if score >= 45:
        return 'medium'
    return 'basic'


def classify_scheme_for_training(scheme_data: dict[str, Any]) -> dict[str, Any]:
    components = scheme_data.get('components') or [] if isinstance(scheme_data, dict) else []
    connections = scheme_data.get('connections') or [] if isinstance(scheme_data, dict) else []
    counts = Counter(_detect_component_type(item) for item in components if isinstance(item, dict))
    family = _detect_teacher_topology(scheme_data)
    if family == 'generic':
        if counts.get('ic') or counts.get('transistor'):
            family = 'active_node'
        elif counts.get('diode') or counts.get('led'):
            family = 'diode_node'
        elif counts.get('resistor') and counts.get('capacitor'):
            family = 'passive_filter'
        elif counts.get('battery') and counts.get('resistor'):
            family = 'resistive_network'
    type_diversity = len([key for key, value in counts.items() if value])
    complexity_score = int(min(100, (
        len(components) * 5
        + len(connections) * 4
        + type_diversity * 8
        + (10 if counts.get('ic') else 0)
        + (8 if counts.get('transistor') else 0)
    )))
    return {
        'family': family,
        'component_count': len(components),
        'connection_count': len(connections),
        'type_diversity': type_diversity,
        'component_types': dict(counts),
        'complexity_score': complexity_score,
        'complexity_label': _scheme_complexity_label(complexity_score),
    }


def _detect_component_type(component: dict[str, Any]) -> str:
    raw = str(component.get('type') or '').strip().lower()
    aliases = {
        'v': 'battery',
        'vsource': 'battery',
        'source': 'battery',
        'gnd': 'ground',
        'r': 'resistor',
        'res': 'resistor',
        'c': 'capacitor',
        'cap': 'capacitor',
        'q': 'transistor',
        'npn': 'transistor',
        'pnp': 'transistor',
        'u': 'ic',
    }
    if raw in aliases:
        return aliases[raw]
    if raw.startswith('res'):
        return 'resistor'
    if raw.startswith('cap'):
        return 'capacitor'
    if raw.startswith('bat'):
        return 'battery'
    return raw or 'unknown'


def score_scheme_for_training(
    scheme_data: dict[str, Any],
    *,
    review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Expert-first quality score for automatic dataset curation."""
    scheme_data = scheme_data if isinstance(scheme_data, dict) else {}
    classes = classify_scheme_for_training(scheme_data)
    components = scheme_data.get('components') or []
    connections = scheme_data.get('connections') or []
    has_ground = False
    has_source = False
    isolated = []
    floating = []
    connected_components = 0
    try:
        from Dolg_APP.services.schematic_graph import analyze_graph_topology
        graph = analyze_graph_topology(scheme_data)
        metrics = graph.get('metrics') or {}
        has_ground = bool(metrics.get('has_ground'))
        has_source = bool(metrics.get('has_source'))
        isolated = list(metrics.get('isolated_components') or [])
        floating = list(metrics.get('floating_components') or [])
        connected_components = int(metrics.get('connected_components_count') or 0)
    except Exception:
        used = set()
        for conn in connections:
            source = (conn.get('from') or {}).get('compId')
            target = (conn.get('to') or {}).get('compId')
            if source is not None:
                used.add(str(source))
            if target is not None:
                used.add(str(target))
        ids = {str(item.get('id')) for item in components if item.get('id') is not None}
        isolated = sorted(ids - used)
        type_counts = classes['component_types']
        has_ground = bool(type_counts.get('ground'))
        has_source = bool(type_counts.get('battery'))
        connected_components = 1 if connections else len(components)

    score = 30
    score += min(20, classes['component_count'] * 3)
    score += min(15, classes['connection_count'] * 3)
    score += min(12, classes['type_diversity'] * 4)
    score += 12 if has_ground else -18
    score += 8 if has_source else -6
    score -= min(18, len(isolated) * 6)
    score -= min(12, len(floating) * 4)
    if review:
        review_score = int(review.get('score') or 0)
        # Review often penalizes demo schemes for missing saved simulation/BOM.
        # For dataset curation it should influence quality, not erase a clean
        # topology score for otherwise useful training examples.
        score = int((score * 0.85) + (review_score * 0.15))
    score = max(0, min(100, int(score)))
    if score >= 82:
        quality_label = 'excellent'
    elif score >= 68:
        quality_label = 'good'
    elif score >= 50:
        quality_label = 'needs_review'
    else:
        quality_label = 'weak'
    return {
        **classes,
        'quality_score': score,
        'quality_label': quality_label,
        'has_ground': has_ground,
        'has_source': has_source,
        'isolated_components': isolated[:10],
        'floating_components': floating[:10],
        'connected_components_count': connected_components,
        'topology': _detect_teacher_topology(scheme_data),
        'risk_score': round(float(_risk_teacher(scheme_data)), 4),
        'next_component': _next_component_teacher(scheme_data),
    }


def _ai_project_owner():
    User = get_user_model()
    owner = (
        User.objects.filter(is_superuser=True).order_by('id').first()
        or User.objects.filter(is_staff=True).order_by('id').first()
    )
    if owner is not None:
        return owner
    owner, _ = User.objects.get_or_create(
        username='ai_project_bot',
        defaults={'email': 'ai-project-bot@local.invalid', 'is_active': True},
    )
    owner.set_unusable_password()
    owner.save(update_fields=['password'])
    return owner


def _category_for_scheme_family(family: str) -> str:
    return {
        'led_indicator': 'led',
        'diode_node': 'led',
        'voltage_divider': 'power',
        'resistive_network': 'power',
        'rc_network': 'sensor',
        'passive_filter': 'sensor',
        'active_node': 'other',
    }.get(str(family or ''), 'other')


def _safe_project_difficulty(label: str) -> str:
    return label if label in {'basic', 'medium', 'advanced'} else 'basic'


def _scheme_from_training_example(example: AITrainingExample) -> dict[str, Any]:
    features = example.features if isinstance(example.features, dict) else {}
    scheme = features.get('scheme_data') or {}
    if isinstance(scheme, dict):
        return json.loads(json.dumps(scheme, ensure_ascii=False))
    return {}


def promote_ai_examples_to_projects(
    *,
    owner=None,
    organization: Organization | None = None,
    visibility: str = 'private',
    approval_state: str | None = None,
    is_demo: bool = False,
    limit: int = 100,
    min_quality: int = 68,
    source_filters: list[str] | None = None,
    example_ids: list[int] | None = None,
    validated_only: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Turn curated AI examples into real projects with controlled ownership.

    The function is intentionally conservative: by default it creates private
    projects, uses the example owner when available, and stores promotion
    metadata back on the AI example for auditability.
    """
    valid_visibility = {'private', 'team', 'public'}
    valid_approval = {'draft', 'pending_review', 'approved', 'rejected'}
    visibility = visibility if visibility in valid_visibility else 'private'
    if organization is not None and visibility == 'private':
        visibility = 'team'
    if is_demo:
        visibility = 'public'
    approval_state = approval_state or ('approved' if is_demo else 'draft')
    approval_state = approval_state if approval_state in valid_approval else 'draft'

    qs = AITrainingExample.objects.select_related('project', 'user').order_by('-created_at')
    if example_ids:
        qs = qs.filter(id__in=[int(item) for item in example_ids])
    if validated_only:
        qs = qs.filter(is_validated=True)
    if source_filters:
        # Portable fallback: JSONField contains/lookups differ by backend, so
        # filter in Python after taking a bounded queryset.
        source_filters = [str(item).strip() for item in source_filters if str(item).strip()]

    scanned = created = updated = skipped_quality = skipped_empty = 0
    rows: list[dict[str, Any]] = []
    for example in qs[:max(1, int(limit))]:
        scanned += 1
        features = example.features if isinstance(example.features, dict) else {}
        feature_source = str(features.get('source') or features.get('dataset_source') or '')
        evidence_kind = str(features.get('evidence_kind') or '')
        if source_filters and feature_source not in source_filters and evidence_kind not in source_filters:
            continue
        scheme = _scheme_from_training_example(example)
        if not scheme.get('components'):
            skipped_empty += 1
            continue
        score = score_scheme_for_training(scheme)
        if score['quality_score'] < int(min_quality):
            skipped_quality += 1
            rows.append({
                'example_id': example.id,
                'accepted': False,
                'reason': 'quality',
                'quality_score': score['quality_score'],
                'quality_label': score['quality_label'],
            })
            continue

        project_owner = owner or example.user or (example.project.user if example.project_id else None) or _ai_project_owner()
        promotion_key = f'ai-example:{example.id}:owner:{project_owner.id}:demo:{int(bool(is_demo))}:visibility:{visibility}'
        scheme.setdefault('metadata', {})
        if isinstance(scheme['metadata'], dict):
            scheme['metadata']['ai_promotion_key'] = promotion_key
            scheme['metadata']['ai_training_example_id'] = example.id
            scheme['metadata']['quality_score'] = score['quality_score']
            scheme['metadata']['scheme_family'] = score['family']

        source_name = features.get('project_name') or features.get('dataset_source') or feature_source or 'curated'
        name = f'AI curated #{example.id}: {score["family"]}'
        description = (
            f"Curated from AITrainingExample #{example.id}. "
            f"Source: {source_name}. Family: {score['family']}. "
            f"Complexity: {score['complexity_label']} ({score['complexity_score']}/100). "
            f"Quality: {score['quality_label']} ({score['quality_score']}/100). "
            "Neural result is a hint; final engineering control remains expert rules plus human review."
        )

        row = {
            'example_id': example.id,
            'accepted': True,
            'owner_id': project_owner.id,
            'owner': getattr(project_owner, 'username', ''),
            'visibility': visibility,
            'is_demo': bool(is_demo),
            'quality_score': score['quality_score'],
            'quality_label': score['quality_label'],
            'scheme_family': score['family'],
            'complexity_label': score['complexity_label'],
            'dry_run': dry_run,
        }
        if dry_run:
            rows.append(row)
            created += 1
            continue

        project = None
        promoted_id = features.get('latest_promoted_project_id')
        if promoted_id:
            project = SchematicProject.all_objects.filter(pk=promoted_id, user=project_owner).first()
        if project is None:
            project = SchematicProject.all_objects.filter(user=project_owner, name=name).first()

        defaults = {
            'organization': organization,
            'description': description,
            'category': _category_for_scheme_family(score['family']),
            'status': 'completed',
            'difficulty': _safe_project_difficulty(score['complexity_label']),
            'is_demo': bool(is_demo),
            'visibility': visibility,
            'approval_state': approval_state,
            'scheme_data': scheme,
            'deleted_at': None,
        }
        if project is None:
            project = SchematicProject.all_objects.create(user=project_owner, name=name, **defaults)
            created += 1
            event_type = 'project_created'
        else:
            for field, value in defaults.items():
                setattr(project, field, value)
            project.save(update_fields=[*defaults.keys(), 'updated_at'])
            updated += 1
            event_type = 'project_updated'

        ProjectEvent.log(
            project=project,
            user=project_owner,
            event_type=event_type,
            payload={
                'source': 'ai_training_example',
                'example_id': example.id,
                'promotion_key': promotion_key,
                'quality_score': score['quality_score'],
                'complexity_score': score['complexity_score'],
                'scheme_family': score['family'],
            },
        )
        ProjectEvent.log(
            project=project,
            user=project_owner,
            event_type='import_finished',
            payload={
                'source': 'ai_training_example',
                'example_id': example.id,
                'visibility': visibility,
                'approval_state': approval_state,
            },
        )

        features = dict(features)
        promoted_ids = list(features.get('promoted_project_ids') or [])
        if project.id not in promoted_ids:
            promoted_ids.append(project.id)
        features.update({
            'latest_promoted_project_id': project.id,
            'promoted_project_ids': promoted_ids[-20:],
            'promoted_at': timezone.now().isoformat(),
            'promotion_visibility': visibility,
            'promotion_owner_id': project_owner.id,
        })
        example.features = features
        example.save(update_fields=['features'])
        row['project_id'] = project.id
        rows.append(row)

    return {
        'ok': True,
        'scanned': scanned,
        'created': created,
        'updated': updated,
        'skipped_empty': skipped_empty,
        'skipped_quality': skipped_quality,
        'min_quality': int(min_quality),
        'visibility': visibility,
        'approval_state': approval_state,
        'is_demo': bool(is_demo),
        'dry_run': dry_run,
        'projects': rows[:100],
    }


def collect_good_project_schemes(
    *,
    limit: int = 100,
    min_quality: int = 68,
    validate: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Promote high-quality opted-in/demo project schemes into AITrainingExample."""
    qs = (
        SchematicProject.all_objects
        .select_related('user', 'user__profile')
        .filter(deleted_at__isnull=True)
        .exclude(scheme_data={})
        .order_by('-updated_at')
    )
    scanned = promoted = updated = skipped_privacy = skipped_quality = 0
    rows = []
    for project in qs[:max(1, int(limit))]:
        scanned += 1
        if not project_can_feed_ai_training(project):
            skipped_privacy += 1
            continue
        scheme = project.scheme_data if isinstance(project.scheme_data, dict) else {}
        if not scheme.get('components'):
            skipped_quality += 1
            continue
        review = build_design_review(project, simulation_runs=[], measurements=[])
        score = score_scheme_for_training(scheme, review=review)
        if score['quality_score'] < int(min_quality):
            skipped_quality += 1
            rows.append({
                'project_id': project.id,
                'project': project.name,
                'quality_score': score['quality_score'],
                'quality_label': score['quality_label'],
                'accepted': False,
            })
            continue
        source = 'auto_quality_scheme'
        prompt = (
            f"Разбери качественную схему `{project.name}`: тип {score['family']}, "
            f"сложность {score['complexity_label']}, score {score['quality_score']}."
        )
        target = '\n'.join([
            f"topology={score['topology']}",
            f"scheme_family={score['family']}",
            f"complexity_label={score['complexity_label']}",
            f"complexity_score={score['complexity_score']}",
            f"quality_label={score['quality_label']}",
            f"quality_score={score['quality_score']}",
            f"risk_score={score['risk_score']}",
            f"next_component={score['next_component']}",
            f"review_score={review.get('score', 0)}",
        ])
        features = {
            'source': source,
            'evidence_kind': 'auto_quality_scheme',
            'project_id': project.id,
            'project_name': project.name,
            'scheme_data': scheme,
            'feature_vector': scheme_to_features(scheme),
            'source_ids': [],
            'source_topics': ['project_session', score['family'], score['complexity_label']],
            'teacher_rules': [],
            'review_score': review.get('score', 0),
            **score,
        }
        row = {
            'project_id': project.id,
            'project': project.name,
            'quality_score': score['quality_score'],
            'quality_label': score['quality_label'],
            'scheme_family': score['family'],
            'complexity_label': score['complexity_label'],
            'accepted': True,
            'dry_run': dry_run,
        }
        if dry_run:
            rows.append(row)
            promoted += 1
            continue
        existing = AITrainingExample.objects.filter(
            project=project,
            kind='review_hint',
            features__source=source,
        ).first()
        if existing:
            existing.prompt = prompt
            existing.target = target
            existing.features = features
            existing.is_validated = bool(validate)
            existing.save(update_fields=['prompt', 'target', 'features', 'is_validated'])
            updated += 1
            row['example_id'] = existing.id
        else:
            example = AITrainingExample.objects.create(
                project=project,
                user=project.user,
                kind='review_hint',
                prompt=prompt,
                target=target,
                features=features,
                is_validated=bool(validate),
            )
            promoted += 1
            row['example_id'] = example.id
        rows.append(row)
    return {
        'ok': True,
        'scanned': scanned,
        'promoted': promoted,
        'updated': updated,
        'skipped_privacy': skipped_privacy,
        'skipped_quality': skipped_quality,
        'min_quality': int(min_quality),
        'dry_run': dry_run,
        'examples': rows[:100],
    }


def _learning_target(task, rubric: dict[str, Any]) -> str:
    task_type = task.task_type
    parts = [
        f'task_type={task_type}',
        f'lesson={task.lesson.title}',
    ]
    if task_type == 'math_numeric':
        if 'expected_value' in rubric:
            parts.append(f'expected_value={rubric.get("expected_value")}')
        if rubric.get('unit'):
            parts.append(f'unit={rubric.get("unit")}')
        if rubric.get('tolerance_percent') is not None:
            parts.append(f'tolerance_percent={rubric.get("tolerance_percent")}')
        parts.append('next_step=проверить единицы и допуск')
    elif task_type == 'circuit_build':
        required = rubric.get('required_components') or rubric.get('required_component_types') or []
        parts.append('required_components=' + ', '.join(str(item) for item in required))
        parts.append('next_step=проверить GND, источник, соединения и DRC')
    elif task_type == 'simulation_measure':
        metric = rubric.get('metric') or rubric.get('expected_metric') or rubric.get('metric_name') or ''
        parts.append(f'metric={metric}')
        parts.append(f'analysis_type={rubric.get("analysis_type") or rubric.get("required_analysis_type") or ""}')
        parts.append('next_step=сравнить expected vs measured')
    else:
        parts.append('next_step=разобрать условие и связать с review')
    return '\n'.join(part for part in parts if part)


def _review_findings(review: ProjectReview) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    sections = review.sections if isinstance(review.sections, dict) else {}
    expert = sections.get('expert_system') if isinstance(sections.get('expert_system'), dict) else {}
    for item in expert.get('findings') or []:
        if isinstance(item, dict):
            findings.append(item)
    for bucket_name in ('errors', 'warnings', 'recommendations', 'faults'):
        for item in getattr(review, bucket_name, None) or []:
            if isinstance(item, dict):
                findings.append(item)
            else:
                findings.append({
                    'rule_id': f'review.{bucket_name}',
                    'severity': 'error' if bucket_name == 'errors' else 'warning',
                    'title': str(item),
                    'evidence': str(item),
                    'recommendation': '',
                })
    return findings


def _source_topics(source_ids: list[str]) -> list[str]:
    topics = []
    for source in sources_by_ids(source_ids):
        topic = source.get('topic')
        if topic and topic not in topics:
            topics.append(topic)
    return topics


def _source_metadata_from_review(review: dict[str, Any]) -> dict[str, list[str]]:
    findings = []
    if isinstance(review, dict):
        findings.extend(review.get('expert_findings') or [])
        expert = (review.get('sections') or {}).get('expert_system') or {}
        findings.extend(expert.get('findings') or [])

    teacher_rules = []
    source_ids = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        rule_id = str(finding.get('rule_id') or finding.get('id') or '').strip()
        if rule_id and rule_id not in teacher_rules:
            teacher_rules.append(rule_id)
        references = finding.get('references') if isinstance(finding.get('references'), dict) else {}
        for source_id in references.get('source_ids') or []:
            if source_id not in source_ids:
                source_ids.append(source_id)
        for source in finding.get('source_references') or []:
            if isinstance(source, dict) and source.get('id') and source['id'] not in source_ids:
                source_ids.append(source['id'])
        if rule_id:
            for source_id in source_ids_for_rule(rule_id):
                if source_id not in source_ids:
                    source_ids.append(source_id)

    source_topics = []
    for source in sources_by_ids(source_ids):
        topic = source.get('topic')
        if topic and topic not in source_topics:
            source_topics.append(topic)

    return {
        'source_ids': source_ids,
        'source_topics': source_topics,
        'teacher_rules': teacher_rules,
    }
