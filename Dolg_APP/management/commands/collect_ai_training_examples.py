import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from Dolg_APP.services.ai_training import (
    collect_artifact_examples,
    collect_learning_task_examples,
    collect_opt_in_scheme_examples,
    collect_review_examples,
    seed_curated_ai_examples,
    summarize_ai_training_examples,
)


class Command(BaseCommand):
    help = 'Collect opted-in SchematicProject snapshots into AITrainingExample rows.'

    def add_arguments(self, parser):
        parser.add_argument('--user', help='Limit collection to username or numeric user id.')
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument(
            '--source',
            choices=('schemes', 'learning', 'reviews', 'artifacts', 'curated', 'all'),
            default='schemes',
        )
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--no-validate', action='store_true')
        parser.add_argument('--json', action='store_true', dest='as_json')

    def handle(self, *args, **options):
        user = None
        if options.get('user'):
            User = get_user_model()
            value = str(options['user']).strip()
            lookup = {'id': int(value)} if value.isdigit() else {'username': value}
            try:
                user = User.objects.get(**lookup)
            except User.DoesNotExist as exc:
                raise CommandError(f'User not found: {value}') from exc

        validate = not options['no_validate']
        source = options['source']
        results = []
        if source in {'schemes', 'all'}:
            results.append(
                collect_opt_in_scheme_examples(
                    user=user,
                    limit=options['limit'],
                    validate=validate,
                    dry_run=options['dry_run'],
                )
            )
        if source in {'curated', 'all'}:
            results.append(
                seed_curated_ai_examples(
                    validate=validate,
                    dry_run=options['dry_run'],
                )
            )
        if source in {'learning', 'all'}:
            results.append(
                collect_learning_task_examples(
                    limit=options['limit'],
                    validate=validate,
                    dry_run=options['dry_run'],
                )
            )
        if source in {'reviews', 'all'}:
            results.append(
                collect_review_examples(
                    limit=options['limit'],
                    validate=validate,
                    dry_run=options['dry_run'],
                )
            )
        if source in {'artifacts', 'all'}:
            results.append(
                collect_artifact_examples(
                    limit=options['limit'],
                    validate=validate,
                    dry_run=options['dry_run'],
                )
            )
        result = {
            'ok': all(item.get('ok') for item in results),
            'source': source,
            'results': results,
            'summary': summarize_ai_training_examples() if not options['dry_run'] else {},
        }
        if options['as_json']:
            payload = json.dumps(result, ensure_ascii=False, indent=2)
            try:
                self.stdout.write(payload)
            except UnicodeEncodeError:
                self.stdout.write(json.dumps(result, ensure_ascii=True, indent=2))
            return

        self.stdout.write(
            self.style.SUCCESS(
                'AI training collection: '
                f'source={source} '
                f'scanned={sum(item.get("scanned", 0) for item in results)} '
                f'skipped={sum(item.get("skipped", 0) for item in results)} '
                f'created={sum(item.get("created", 0) for item in results)} '
                f'updated={sum(item.get("updated", 0) for item in results)}'
            )
        )
