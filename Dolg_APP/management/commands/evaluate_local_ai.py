from __future__ import annotations

import json
import time

from django.core.management.base import BaseCommand

from Dolg_APP import ai_assistant
from Dolg_APP.services.engine_ai import plan_engine_action


def _divider_scheme():
    return {
        'components': [
            {'id': 'V1', 'type': 'battery', 'voltage': 10},
            {'id': 'R1', 'type': 'resistor', 'resistance': 1000},
            {'id': 'R2', 'type': 'resistor', 'resistance': 1000},
            {'id': 'GND', 'type': 'ground'},
        ],
        'connections': [
            {'from': {'compId': 'V1'}, 'to': {'compId': 'R1'}},
            {'from': {'compId': 'R1'}, 'to': {'compId': 'R2'}},
            {'from': {'compId': 'R2'}, 'to': {'compId': 'GND'}},
        ],
    }


def _rc_scheme():
    return {
        'components': [
            {'id': 'V1', 'type': 'battery', 'voltage': 5},
            {'id': 'R1', 'type': 'resistor', 'resistance': 1000},
            {'id': 'C1', 'type': 'capacitor', 'capacitance': '100n'},
            {'id': 'GND', 'type': 'ground'},
        ],
        'connections': [
            {'from': {'compId': 'V1'}, 'to': {'compId': 'R1'}},
            {'from': {'compId': 'R1'}, 'to': {'compId': 'C1'}},
            {'from': {'compId': 'C1'}, 'to': {'compId': 'GND'}},
        ],
    }


def _led_without_resistor():
    return {
        'components': [
            {'id': 'V1', 'type': 'battery', 'voltage': 5},
            {'id': 'LED1', 'type': 'led'},
            {'id': 'GND', 'type': 'ground'},
        ],
        'connections': [
            {'from': {'compId': 'V1'}, 'to': {'compId': 'LED1'}},
            {'from': {'compId': 'LED1'}, 'to': {'compId': 'GND'}},
        ],
    }


def _missing_ground():
    return {
        'components': [
            {'id': 'V1', 'type': 'battery', 'voltage': 9},
            {'id': 'R1', 'type': 'resistor', 'resistance': 1000},
        ],
        'connections': [{'from': {'compId': 'V1'}, 'to': {'compId': 'R1'}}],
    }


SCENARIOS = [
    ('divider_dc', 'Прогони DC через локальный numpy', _divider_scheme),
    ('rc_transient', 'Прогони transient через pyspice 5 ms', _rc_scheme),
    ('rf_recommend', 'Подбери движок для RF AC sweep', _rc_scheme),
    ('led_risk', 'Проверь LED без резистора и предложи команду', _led_without_resistor),
    ('missing_ground', 'Проверь схему без земли и выбери движок', _missing_ground),
]


class Command(BaseCommand):
    help = 'Evaluate the local AI stack: Ollama status, PyTorch hints, and text-to-engine commands.'

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', help='Print machine-readable JSON.')
        parser.add_argument(
            '--live-ollama', action='store_true', help='Run one tiny Ollama generation smoke.'
        )
        parser.add_argument('--timeout', type=int, default=30, help='Ollama smoke timeout in seconds.')

    def handle(self, *args, **options):
        started = time.perf_counter()
        report = {
            'ok': True,
            'runtime': ai_assistant.runtime_status(timeout=2),
            'scenarios': [],
            'ollama_smoke': None,
        }

        for name, command_text, scheme_factory in SCENARIOS:
            plan = plan_engine_action(command_text, scheme_data=scheme_factory(), limit=4)
            neural = (plan.get('ai_context') or {}).get('neural_hint') or {}
            report['scenarios'].append(
                {
                    'name': name,
                    'command_text': command_text,
                    'intent': plan.get('intent'),
                    'engine_id': (plan.get('command') or {}).get('engine_id'),
                    'analysis_type': (plan.get('command') or {}).get('analysis_type'),
                    'options': (plan.get('command') or {}).get('options') or {},
                    'confidence': plan.get('confidence'),
                    'warnings': plan.get('warnings') or [],
                    'neural': {
                        'available': neural.get('available', False),
                        'topology': neural.get('topology'),
                        'risk_label': neural.get('risk_label'),
                        'confidence_policy': neural.get('confidence_policy'),
                    },
                    'explanation': plan.get('explanation'),
                }
            )

        if options['live_ollama']:
            report['ollama_smoke'] = self._ollama_smoke(timeout=options['timeout'])

        report['elapsed_ms'] = int((time.perf_counter() - started) * 1000)
        if options['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            return

        self.stdout.write(f'runtime={report["runtime"]["backend"]} live={report["runtime"]["live_enabled"]}')
        for scenario in report['scenarios']:
            self.stdout.write(
                f'{scenario["name"]}: {scenario["engine_id"]} / {scenario["analysis_type"]} '
                f'confidence={scenario["confidence"]} neural={scenario["neural"]}'
            )
        if report['ollama_smoke'] is not None:
            self.stdout.write(f'ollama_smoke={report["ollama_smoke"]}')

    def _ollama_smoke(self, *, timeout: int) -> dict:
        if not ai_assistant.live_enabled():
            return {'ok': False, 'reason': 'ollama_disabled'}
        try:
            result = ai_assistant.call_live(
                [{'role': 'user', 'content': 'Ответь одним коротким словом: готов?'}],
                'Ты локальный инженерный ассистент DOLG. Отвечай максимально кратко.',
                mode='recommend',
                timeout=max(5, int(timeout)),
                max_tokens=16,
            )
        except Exception as exc:
            return {'ok': False, 'error': str(exc)[:300]}
        return {
            'ok': True,
            'backend': result.get('backend'),
            'model': result.get('model'),
            'text': result.get('text'),
            'usage': result.get('usage') or {},
        }
