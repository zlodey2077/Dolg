import json

from django.core.management.base import BaseCommand, CommandError

from Dolg_APP.ml.neural import NeuralUnavailable, train_tiny_model


class Command(BaseCommand):
    help = 'Train tiny PyTorch circuit AI model for DOLG neural deep-hints.'

    def add_arguments(self, parser):
        parser.add_argument('--size', type=int, default=240)
        parser.add_argument('--epochs', type=int, default=120)
        parser.add_argument('--seed', type=int, default=42)
        parser.add_argument(
            '--include-curated',
            action='store_true',
            help='Add validated AITrainingExample rows from DB to the training set.',
        )
        parser.add_argument('--max-curated', type=int, default=200)
        parser.add_argument(
            '--dataset',
            type=str,
            default=None,
            help='Path to external dataset JSON file (см. Dolg_APP/ml/dataset/circuits.json '
            'для формата). Items добавляются в extra_schemes как curated data.',
        )
        parser.add_argument('--json', action='store_true', dest='as_json')

    def handle(self, *args, **options):
        import json as _json
        from pathlib import Path

        try:
            extra_schemes = []
            if options['include_curated']:
                from Dolg_APP.services.ai_training import curated_training_schemes

                extra_schemes.extend(curated_training_schemes(limit=options['max_curated']))

            dataset_path = options.get('dataset')
            if dataset_path:
                path = Path(dataset_path)
                if not path.exists():
                    raise CommandError(f'Dataset не найден: {path}')
                try:
                    payload = _json.loads(path.read_text(encoding='utf-8'))
                except _json.JSONDecodeError as exc:
                    raise CommandError(f'Невалидный JSON в {path}: {exc}') from exc
                # Поддерживаем два формата: список scheme'ов напрямую, либо
                # объект {schemes: [...], metadata: {...}}.
                items = payload if isinstance(payload, list) else payload.get('schemes') or []
                added = 0
                for item in items:
                    if isinstance(item, dict) and item.get('components'):
                        extra_schemes.append(item)
                        added += 1
                self.stdout.write(self.style.SUCCESS(f'Подгружено {added} схем из {path}'))

            result = train_tiny_model(
                size=max(30, int(options['size'])),
                epochs=max(1, int(options['epochs'])),
                seed=int(options['seed']),
                extra_schemes=extra_schemes,
            )
        except NeuralUnavailable as exc:
            raise CommandError(str(exc)) from exc

        if options['as_json']:
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Trained tiny circuit AI: loss={result["final_loss"]} -> {result["model_path"]}'
                )
            )
