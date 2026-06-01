"""Deterministic expert-system layer for project review and assistant.

Rules are data, not Python branches. jsonschema validates rule packs and
rule-engine evaluates safe expressions against a flat facts dictionary.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

RULE_PACK_SCHEMA = {
    'type': 'object',
    'required': ['version', 'rules'],
    'properties': {
        'version': {'type': 'string', 'minLength': 1},
        'description': {'type': 'string'},
        'rules': {
            'type': 'array',
            'minItems': 1,
            'items': {
                'type': 'object',
                'required': ['id', 'severity', 'when', 'recommendation'],
                'properties': {
                    'id': {'type': 'string', 'minLength': 1},
                    'title': {'type': 'string'},
                    'severity': {'enum': ['info', 'recommendation', 'warning', 'risk', 'error', 'critical']},
                    'when': {'type': 'string', 'minLength': 1},
                    'evidence_fields': {'type': 'array', 'items': {'type': 'string'}},
                    'recommendation': {'type': 'string', 'minLength': 1},
                    'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1},
                    'references': {'type': 'object'},
                },
                'additionalProperties': True,
            },
        },
    },
    'additionalProperties': True,
}


def _jsonschema_validate(instance, schema):
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda err: list(err.path))
    if errors:
        first = errors[0]
        path = '.'.join(str(item) for item in first.path) or '<root>'
        raise ValueError(f'rule pack schema error at {path}: {first.message}')


def _rule_engine_rule(expression):
    import rule_engine

    return rule_engine.Rule(expression)


def default_rule_pack_path() -> Path:
    return Path(__file__).resolve().parents[1] / 'expert_rules' / 'default_rules.json'


@lru_cache(maxsize=4)
def load_rule_pack(path: str | None = None) -> dict[str, Any]:
    rule_path = Path(path) if path else default_rule_pack_path()
    with rule_path.open('r', encoding='utf-8') as handle:
        data = json.load(handle)
    validate_rule_pack(data)
    return data


def validate_rule_pack(rule_pack: dict[str, Any]) -> dict[str, Any]:
    _jsonschema_validate(rule_pack, RULE_PACK_SCHEMA)
    for rule in rule_pack.get('rules') or []:
        try:
            _rule_engine_rule(rule['when'])
        except Exception as exc:
            raise ValueError(f'invalid rule expression {rule.get("id")}: {exc}') from exc
    return {'ok': True, 'version': rule_pack.get('version'), 'rules': len(rule_pack.get('rules') or [])}


def build_expert_facts(*, connectivity=None, bom=None, derating=None, measurements=None, import_summary=None, errors=None, warnings=None, scheme_data=None) -> dict[str, Any]:
    connectivity = connectivity or {}
    bom = bom or {}
    derating = derating or {}
    measurements = measurements or []
    import_summary = import_summary or {}
    errors = errors or []
    warnings = warnings or []

    floating = connectivity.get('floating_components') or []
    unconnected = connectivity.get('unconnected') or []
    missing_catalog = bom.get('missing_catalog') or []
    derating_issues = derating.get('issues') or []
    risk_count = sum(1 for item in derating_issues if item.get('severity') in {'risk', 'critical', 'error'})

    facts = {
        'component_count': int(connectivity.get('component_count') or 0),
        'connection_count': int(connectivity.get('connection_count') or 0),
        'topology': connectivity.get('topology') or 'generic',
        'has_ground': bool(connectivity.get('has_ground')),
        'has_source': bool(connectivity.get('has_source')),
        'has_output_node': bool(connectivity.get('has_output_node')),
        'is_connected': bool(connectivity.get('is_connected', True)),
        'connected_components_count': int(connectivity.get('connected_components_count') or 0),
        'floating_count': len(floating),
        'unconnected_count': len(unconnected),
        'bom_missing_count': len(missing_catalog),
        'derating_issue_count': len(derating_issues),
        'risk_count': risk_count,
        'has_measurements': bool(measurements),
        'unsupported_import_count': int((import_summary or {}).get('unsupported') or 0),
        'error_count': len(errors),
        'warning_count': len(warnings),
        # Defaults for topology detectors — keep declarative rules safe even
        # when scheme_data is not provided (legacy callers).
        'led_reverse_polarity_count': 0,
        'led_reverse_polarity_refs': [],
        'parallel_source_conflict_count': 0,
        'parallel_source_conflicts': [],
        'source_short_count': 0,
        'source_short_pairs': [],
        'dangling_named_net_count': 0,
        'dangling_named_net_refs': [],
        'transistor_pinout_swap_count': 0,
        'transistor_pinout_swap_refs': [],
    }
    if scheme_data is not None:
        try:
            from .expert_detectors import collect_topology_evidence

            facts.update(collect_topology_evidence(scheme_data))
        except Exception:
            # Detectors are advisory — silent fallback keeps the review pipeline
            # green for malformed scheme_data.
            pass
    return facts


def evaluate_expert_rules(facts: dict[str, Any], rule_pack: dict[str, Any] | None = None) -> dict[str, Any]:
    rule_pack = rule_pack or load_rule_pack()
    validate_rule_pack(rule_pack)
    findings = []

    for rule in rule_pack.get('rules') or []:
        try:
            matched = bool(_rule_engine_rule(rule['when']).matches(facts))
        except Exception as exc:
            findings.append({
                'rule_id': rule.get('id', 'invalid'),
                'title': rule.get('title') or rule.get('id', 'Invalid rule'),
                'severity': 'error',
                'evidence': {'expression': rule.get('when'), 'error': str(exc)},
                'recommendation': 'Исправьте условие экспертного правила.',
                'confidence': 1.0,
                'references': {},
            })
            continue
        if not matched:
            continue
        evidence_fields = rule.get('evidence_fields') or []
        evidence = {name: facts.get(name) for name in evidence_fields}
        references = rule.get('references') or {}
        source_references = []
        source_ids = references.get('source_ids') or []
        if source_ids:
            try:
                from knowledge.services.legal_sources import sources_by_ids

                source_references = [
                    {
                        'id': item.get('id'),
                        'title': item.get('title'),
                        'url': item.get('url'),
                        'topic': item.get('topic'),
                    }
                    for item in sources_by_ids(source_ids, limit=3)
                ]
            except Exception:
                source_references = []
        findings.append({
            'rule_id': rule['id'],
            'title': rule.get('title') or rule['id'],
            'severity': rule.get('severity', 'info'),
            'evidence': evidence,
            'recommendation': rule.get('recommendation', ''),
            'confidence': float(rule.get('confidence', 0.5)),
            'references': references,
            'source_references': source_references,
        })

    return {
        'ok': True,
        'rule_pack_version': rule_pack.get('version'),
        'facts': dict(facts),
        'findings': findings,
    }
