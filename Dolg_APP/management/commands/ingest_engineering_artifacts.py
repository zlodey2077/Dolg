import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from Dolg_APP.models import AITrainingExample, SchematicProject
from Dolg_APP.services.artifact_ingestion import (
    EXTENSION_PARSERS,
    parse_artifact,
    save_artifact_report,
    training_examples_from_artifact,
)


class Command(BaseCommand):
    help = 'Parse engineering artifacts into structured facts for review, learning and AI memory.'

    def add_arguments(self, parser):
        parser.add_argument('paths', nargs='*', help='Files or directories to ingest.')
        parser.add_argument('--root', default='', help='Optional root directory to scan recursively.')
        parser.add_argument('--limit', type=int, default=50)
        parser.add_argument('--project-id', type=int, default=None)
        parser.add_argument('--user-id', type=int, default=None)
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--create-training', action='store_true')
        parser.add_argument('--json', action='store_true', dest='as_json')

    def handle(self, *args, **options):
        project = self._project(options.get('project_id'))
        user = self._user(options.get('user_id'))
        paths = self._collect_paths(options)
        if not paths:
            raise CommandError('No engineering artifacts found.')

        reports = []
        saved_count = 0
        training_count = 0
        for path in paths[: options['limit']]:
            report = parse_artifact(path)
            reports.append(report)
            artifact = None
            if not options['dry_run']:
                artifact = save_artifact_report(report, project=project, user=user)
                saved_count += 1
            if options['create_training']:
                examples = training_examples_from_artifact(report)
                if not options['dry_run'] and artifact is not None:
                    for example in examples:
                        AITrainingExample.objects.create(
                            artifact=artifact,
                            project=project,
                            user=user if getattr(user, 'is_authenticated', False) else None,
                            kind=example['kind'],
                            prompt=example['prompt'],
                            target=example['target'],
                            features=example.get('features') or {},
                        )
                training_count += len(examples)

        summary = {
            'ok': True,
            'dry_run': options['dry_run'],
            'found': len(paths),
            'processed': len(reports),
            'saved': saved_count,
            'training_examples': training_count,
            'artifacts': [
                {
                    'source_name': item.get('source_name'),
                    'artifact_type': item.get('artifact_type'),
                    'parser': item.get('parser'),
                    'status': item.get('status'),
                    'summary': item.get('summary'),
                    'warnings': item.get('warnings'),
                    'errors': item.get('errors'),
                }
                for item in reports
            ],
        }
        if options['as_json']:
            self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Processed {summary["processed"]} artifacts; saved={saved_count}; '
                    f'training_examples={training_count}'
                )
            )

    def _collect_paths(self, options):
        raw_paths = list(options.get('paths') or [])
        if options.get('root'):
            raw_paths.append(options['root'])
        result = []
        for raw in raw_paths:
            path = Path(raw)
            if path.is_file():
                if self._is_supported_artifact(path):
                    result.append(path)
                continue
            if path.is_dir():
                for item in path.rglob('*'):
                    if item.is_file() and self._is_supported_artifact(item):
                        result.append(item)
        return sorted(result, key=lambda item: str(item).lower())

    def _is_supported_artifact(self, path):
        if path.name.startswith('~$'):
            return False
        if path.name.startswith('.'):
            return False
        return path.suffix.lower() in EXTENSION_PARSERS

    def _project(self, pk):
        if not pk:
            return None
        return SchematicProject.objects.get(pk=pk)

    def _user(self, pk):
        if not pk:
            return None
        return get_user_model().objects.get(pk=pk)
