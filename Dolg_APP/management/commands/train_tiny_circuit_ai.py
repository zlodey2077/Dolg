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
        parser.add_argument(
            '--all-datasets',
            action='store_true',
            dest='all_datasets',
            help='Мультитренировка: объединить ВСЕ локальные JSON-датасеты из '
            'Dolg_APP/ml/dataset/ (включая external/) в обучение (битые JSON пропускаются).',
        )
        parser.add_argument('--json', action='store_true', dest='as_json')

    def handle(self, *args, **options):
        import json as _json
        from pathlib import Path

        dataset_root = Path('Dolg_APP/ml/dataset')

        def _load_schemes(path: Path) -> list:
            payload = _json.loads(path.read_text(encoding='utf-8'))
            items = payload if isinstance(payload, list) else (payload.get('schemes') or [])
            return [it for it in items if isinstance(it, dict) and it.get('components')]

        try:
            extra_schemes = []
            if options['include_curated']:
                from Dolg_APP.services.ai_training import curated_training_schemes

                extra_schemes.extend(curated_training_schemes(limit=options['max_curated']))

            # Мультизагрузка датасетов: --all-datasets (все JSON в dataset_root) ИЛИ
            # один --dataset. Единый путь, устойчивый к битым файлам при --all.
            if options.get('all_datasets'):
                dataset_paths = sorted(dataset_root.rglob('*.json'))
                if not dataset_paths:
                    self.stdout.write(self.style.WARNING(f'Нет JSON-датасетов в {dataset_root}'))
            elif options.get('dataset'):
                p = Path(options['dataset'])
                if not p.exists():
                    raise CommandError(f'Dataset не найден: {p}')
                dataset_paths = [p]
            else:
                dataset_paths = []

            total_added = 0
            for path in dataset_paths:
                try:
                    schemes = _load_schemes(path)
                except (_json.JSONDecodeError, OSError) as exc:
                    if options.get('all_datasets'):
                        self.stdout.write(self.style.WARNING(f'  ⚠ пропуск {path.name}: {exc}'))
                        continue
                    raise CommandError(f'Невалидный JSON в {path}: {exc}') from exc
                extra_schemes.extend(schemes)
                total_added += len(schemes)
                self.stdout.write(self.style.SUCCESS(f'Подгружено {len(schemes)} схем из {path}'))
            if len(dataset_paths) > 1:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Мультизагрузка: {len(dataset_paths)} датасетов, всего {total_added} схем '
                        f'+ {len(extra_schemes) - total_added} curated DB'
                    )
                )

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
