import json

from django.core.management.base import BaseCommand

from Dolg_APP.services.ai_training import validate_ai_training_examples


class Command(BaseCommand):
    help = 'Validate AITrainingExample rows before PyTorch training.'

    def add_arguments(self, parser):
        parser.add_argument('--validated-only', action='store_true')
        parser.add_argument('--limit', type=int)
        parser.add_argument('--json', action='store_true', dest='as_json')

    def handle(self, *args, **options):
        result = validate_ai_training_examples(
            include_unvalidated=not options['validated_only'],
            limit=options.get('limit'),
        )
        if options['as_json']:
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
            return
        style = self.style.SUCCESS if result['ok'] else self.style.ERROR
        self.stdout.write(
            style(
                f'AI dataset validation: scanned={result["scanned"]} '
                f'errors={result["errors_count"]} warnings={result["warnings_count"]}'
            )
        )
        for row in result['errors'][:10]:
            self.stdout.write(self.style.ERROR(f'ERROR #{row["id"]} {row["code"]}: {row["message"]}'))
        for row in result['warnings'][:10]:
            self.stdout.write(self.style.WARNING(f'WARN #{row["id"]} {row["code"]}: {row["message"]}'))
