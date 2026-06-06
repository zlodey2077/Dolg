"""Regression: expert-rules pack validity + expert-first metadata on findings.

Закрепляет «expert-first»: дефолтный пак правил валиден по JSON-схеме, а каждый
вывод (finding) несёт rule_id / severity / recommendation / confidence. Раньше
пак валидировался только в рантайме при загрузке — тестов не было, и он мог
тихо уехать из схемы.
"""

from __future__ import annotations

import pytest
from django.test import SimpleTestCase

from Dolg_APP.services.expert_rules import (
    build_expert_facts,
    evaluate_expert_rules,
    load_rule_pack,
    validate_rule_pack,
)

SEVERITY_ENUM = {'info', 'recommendation', 'warning', 'risk', 'error', 'critical'}
EXPERT_FIRST_FIELDS = ('rule_id', 'severity', 'recommendation', 'confidence')


class RulePackValidityTests(SimpleTestCase):
    def test_default_pack_loads_and_validates(self):
        pack = load_rule_pack()
        result = validate_rule_pack(pack)
        self.assertTrue(result['ok'])
        self.assertGreater(result['rules'], 0)

    def test_every_rule_has_required_fields_and_valid_severity(self):
        pack = load_rule_pack()
        for rule in pack['rules']:
            for field in ('id', 'severity', 'when', 'recommendation'):
                self.assertIn(field, rule, f'правило без поля {field}: {rule.get("id")}')
            self.assertIn(rule['severity'], SEVERITY_ENUM, rule['id'])
            conf = rule.get('confidence')
            if conf is not None:
                self.assertGreaterEqual(conf, 0.0)
                self.assertLessEqual(conf, 1.0)

    def test_rule_ids_unique(self):
        ids = [r['id'] for r in load_rule_pack()['rules']]
        self.assertEqual(len(ids), len(set(ids)), 'дублирующиеся rule_id в паке')

    def test_invalid_pack_rejected(self):
        bad = {'version': 1, 'rules': [{'id': 'broken'}]}  # нет severity/when/recommendation
        with pytest.raises(Exception):
            validate_rule_pack(bad)


class ExpertFirstFindingsTests(SimpleTestCase):
    def test_problem_scheme_yields_findings_with_full_metadata(self):
        facts = build_expert_facts(
            connectivity={
                'component_count': 3,
                'connection_count': 1,
                'has_ground': False,
                'has_source': False,
                'has_output_node': False,
                'is_connected': False,
                'floating_components': ['R1'],
            },
        )
        result = evaluate_expert_rules(facts)
        self.assertTrue(result['findings'], 'проблемная схема должна давать выводы')
        for finding in result['findings']:
            for field in EXPERT_FIRST_FIELDS:
                self.assertIn(field, finding, finding.get('rule_id'))
            self.assertIn(finding['severity'], SEVERITY_ENUM)
            self.assertIsInstance(finding['confidence'], float)
            self.assertTrue(finding['recommendation'])

    def test_clean_facts_produce_no_false_findings(self):
        facts = build_expert_facts(
            connectivity={
                'component_count': 3,
                'connection_count': 3,
                'has_ground': True,
                'has_source': True,
                'has_output_node': True,
                'is_connected': True,
            },
        )
        result = evaluate_expert_rules(facts)
        # допускаем info/recommendation, но не error/critical на чистой схеме
        hard = [f for f in result['findings'] if f['severity'] in {'error', 'critical'}]
        self.assertEqual(hard, [], hard)
