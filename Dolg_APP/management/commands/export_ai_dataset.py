import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from Dolg_APP.services.ai_training import export_ai_training_dataset


class Command(BaseCommand):
    help = 'Export validated AITrainingExample rows to JSONL.'

    def add_arguments(self, parser):
        default_path = (
            Path(settings.BASE_DIR) / 'Dolg_APP' / 'ml' / 'dataset' / 'exports' / 'ai_training_dataset.jsonl'
        )
        parser.add_argument('--output', default=str(default_path))
        parser.add_argument('--include-unvalidated', action='store_true')
        parser.add_argument('--no-scheme-data', action='store_true')
        parser.add_argument('--limit', type=int)
        parser.add_argument('--json', action='store_true', dest='as_json')

    def handle(self, *args, **options):
        result = export_ai_training_dataset(
            options['output'],
            validated_only=not options['include_unvalidated'],
            include_scheme_data=not options['no_scheme_data'],
            limit=options.get('limit'),
        )
        if options['as_json']:
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
            return
        self.stdout.write(self.style.SUCCESS(f'Exported {result["count"]} AI examples -> {result["path"]}'))
