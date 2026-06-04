import json

from django.core.management.base import BaseCommand

from Dolg_APP.services.ai_training import normalize_ai_dataset_metadata


class Command(BaseCommand):
    help = 'Normalize AITrainingExample.features metadata: dataset_kind and graph_training_ready.'

    def add_arguments(self, parser):
        parser.add_argument('--validated-only', action='store_true')
        parser.add_argument('--limit', type=int)
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--json', action='store_true', dest='as_json')

    def handle(self, *args, **options):
        result = normalize_ai_dataset_metadata(
            limit=options.get('limit'),
            validated_only=bool(options.get('validated_only')),
            dry_run=bool(options.get('dry_run')),
        )
        if options['as_json']:
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
            return
        self.stdout.write(
            self.style.SUCCESS(
                f'AI dataset metadata: scanned={result["scanned"]} changed={result["changed"]} '
                f'graph_ready={result["graph_training_ready"]} dry_run={result["dry_run"]}'
            )
        )
        for key, value in result['by_dataset_kind'].items():
            self.stdout.write(f'  {key}: {value}')
