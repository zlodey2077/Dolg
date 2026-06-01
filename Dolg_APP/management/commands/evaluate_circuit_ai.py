import json

from django.core.management.base import BaseCommand, CommandError

from Dolg_APP.ml.neural import (
    NeuralCircuitAdvisor,
    NeuralUnavailable,
    _detect_teacher_topology,
    _next_component_teacher,
    _risk_teacher,
    generate_synthetic_dataset,
)
from Dolg_APP.services.ai_training import curated_training_schemes


class Command(BaseCommand):
    help = 'Evaluate tiny PyTorch circuit AI against teacher heuristics.'

    def add_arguments(self, parser):
        parser.add_argument('--size', type=int, default=120)
        parser.add_argument('--include-curated', action='store_true')
        parser.add_argument('--max-curated', type=int, default=200)
        parser.add_argument('--json', action='store_true', dest='as_json')

    def handle(self, *args, **options):
        schemes = generate_synthetic_dataset(size=max(10, int(options['size'])), seed=777)
        if options['include_curated']:
            schemes.extend(curated_training_schemes(limit=max(1, int(options['max_curated']))))
        try:
            advisor = NeuralCircuitAdvisor()
            rows = []
            topology_ok = 0
            next_ok = 0
            risk_abs_total = 0.0
            for scheme in schemes:
                prediction = advisor.predict(scheme)
                expected_topology = _detect_teacher_topology(scheme)
                expected_next = _next_component_teacher(scheme)
                expected_risk = float(_risk_teacher(scheme))
                pred_next = (prediction.get('next_components') or [{}])[0].get('component_type')
                topology_ok += int(prediction.get('topology') == expected_topology)
                next_ok += int(pred_next == expected_next)
                risk_abs_total += abs(float(prediction.get('risk_score') or 0) - expected_risk)
                rows.append({
                    'expected_topology': expected_topology,
                    'predicted_topology': prediction.get('topology'),
                    'expected_next': expected_next,
                    'predicted_next': pred_next,
                    'expected_risk': round(expected_risk, 4),
                    'predicted_risk': prediction.get('risk_score'),
                })
        except NeuralUnavailable as exc:
            raise CommandError(str(exc)) from exc

        total = max(1, len(schemes))
        result = {
            'ok': True,
            'model_trained': advisor.trained,
            'model_path': str(advisor.model_path),
            'dataset_size': len(schemes),
            'topology_accuracy': round(topology_ok / total, 4),
            'next_component_accuracy': round(next_ok / total, 4),
            'risk_mae': round(risk_abs_total / total, 4),
            'sample': rows[:12],
            'meta': advisor.meta,
        }
        if options['as_json']:
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
            return
        self.stdout.write(self.style.SUCCESS(
            f"AI eval: topology_acc={result['topology_accuracy']} "
            f"next_acc={result['next_component_accuracy']} risk_mae={result['risk_mae']} "
            f"trained={result['model_trained']}"
        ))
