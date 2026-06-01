import json
import sys

from django.core.management.base import BaseCommand

from Dolg_APP.services.ai_training import collect_good_project_schemes

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


class Command(BaseCommand):
    help = 'Promote high-quality demo/opted-in project schemes into AITrainingExample.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--min-quality', type=int, default=68)
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--unvalidated', action='store_true')
        parser.add_argument('--json', action='store_true', dest='as_json')

    def handle(self, *args, **options):
        result = collect_good_project_schemes(
            limit=options['limit'],
            min_quality=options['min_quality'],
            validate=not options['unvalidated'],
            dry_run=options['dry_run'],
        )
        if options['as_json']:
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
            return
        self.stdout.write(self.style.SUCCESS(
            f"Scanned {result['scanned']}; promoted {result['promoted']}; "
            f"updated {result['updated']}; skipped privacy {result['skipped_privacy']}; "
            f"skipped quality {result['skipped_quality']}."
        ))
