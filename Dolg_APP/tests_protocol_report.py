"""Тесты авто-протокола .md (Wave 0 #1)."""

from django.test import SimpleTestCase

from Dolg_APP.services.protocol_report import render_review_markdown


class ProtocolReportTests(SimpleTestCase):
    def _sample(self):
        return {
            'project_id': 7,
            'created': '2026-06-05T10:00:00',
            'score': 82,
            'status_label': 'Допустимо',
            'summary': 'Схема в целом исправна, есть замечания по допускам.',
            'errors': ['Отсутствует GND на узле N3'],
            'warnings': [
                {'title': 'Резистор R4 близок к пределу мощности', 'recommendation': 'Взять 0.5 Вт'}
            ],
            'faults': [{'title': 'LED включён обратной полярностью', 'recommendation': 'Развернуть D1'}],
            'recommendations': ['Добавить развязку по питанию'],
            'expert_findings': [
                {
                    'rule_id': 'GND_MISSING',
                    'severity_label': 'критично',
                    'title': 'Нет опорной земли',
                    'recommendation': 'Подключить GND',
                },
            ],
            'learning_suggestions': [{'title': 'Урок: зачем схеме земля'}],
            'metric_rows': [{'key': 'node_count', 'label': 'Узлов', 'value': '5'}],
            'measurement_rows': [
                {
                    'label': 'Напряжение на выходе',
                    'value': '3.28',
                    'unit': 'В',
                    'expected': '3.3',
                    'status': 'норма',
                },
            ],
        }

    def test_renders_all_sections(self):
        md = render_review_markdown(self._sample(), project=None)
        self.assertIn('# Протокол инженерной проверки схемы', md)
        self.assertIn('**Итоговая оценка:** 82/100 — Допустимо', md)
        self.assertIn('## 1. Сводка', md)
        self.assertIn('- Ошибок: 1', md)
        self.assertIn('## 2. Параметры и метрики', md)
        self.assertIn('| Узлов | 5 |', md)
        self.assertIn('## 3. Измерения', md)
        self.assertIn('3.28 В', md)
        self.assertIn('Отсутствует GND', md)
        self.assertIn('`GND_MISSING`', md)
        self.assertIn('## 5. Рекомендации', md)
        self.assertIn('## 6. Обучение', md)

    def test_handles_empty_review(self):
        md = render_review_markdown({}, project=None)
        self.assertIn('# Протокол инженерной проверки схемы', md)
        self.assertIn('- Ошибок: 0', md)
        self.assertIn('ошибок не обнаружено', md)

    def test_finding_accepts_plain_strings_and_dicts(self):
        md = render_review_markdown({'errors': ['строка-ошибка', {'title': 'dict-ошибка'}]}, project=None)
        self.assertIn('строка-ошибка', md)
        self.assertIn('**dict-ошибка**', md)
