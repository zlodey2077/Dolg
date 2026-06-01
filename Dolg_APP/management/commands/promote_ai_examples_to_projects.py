import json
import sys

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from Dolg_APP.models import Organization
from Dolg_APP.services.ai_training import promote_ai_examples_to_projects

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


class Command(BaseCommand):
    help = 'Promote curated AITrainingExample schemes into controlled SchematicProject records.'

    def add_arguments(self, parser):
        parser.add_argument('--owner', help='Username, email or numeric user id. Defaults to example user, then staff bot.')
        parser.add_argument('--organization-id', type=int, help='Attach created projects to an organization.')
        parser.add_argument('--visibility', choices=['private', 'team', 'public'], default='private')
        parser.add_argument('--approval-state', choices=['draft', 'pending_review', 'approved', 'rejected'])
        parser.add_argument('--demo', action='store_true', help='Create public approved demo projects.')
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--min-quality', type=int, default=68)
        parser.add_argument('--source', action='append', dest='sources', help='Filter by features.source/dataset_source/evidence_kind.')
        parser.add_argument('--example-id', action='append', type=int, dest='example_ids')
        parser.add_argument('--include-unvalidated', action='store_true')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--json', action='store_true', dest='as_json')

    def _resolve_owner(self, value):
        if not value:
            return None
        User = get_user_model()
        qs = User.objects.all()
        if str(value).isdigit():
            owner = qs.filter(id=int(value)).first()
        else:
            owner = qs.filter(username=value).first() or qs.filter(email=value).first()
        if owner is None:
            raise CommandError(f'User not found: {value}')
        return owner

    def _resolve_organization(self, org_id):
        if not org_id:
            return None
        org = Organization.objects.filter(id=org_id).first()
        if org is None:
            raise CommandError(f'Organization not found: {org_id}')
        return org

    def handle(self, *args, **options):
        result = promote_ai_examples_to_projects(
            owner=self._resolve_owner(options.get('owner')),
            organization=self._resolve_organization(options.get('organization_id')),
            visibility=options['visibility'],
            approval_state=options.get('approval_state'),
            is_demo=options['demo'],
            limit=options['limit'],
            min_quality=options['min_quality'],
            source_filters=options.get('sources') or None,
            example_ids=options.get('example_ids') or None,
            validated_only=not options['include_unvalidated'],
            dry_run=options['dry_run'],
        )
        if options['as_json']:
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
            return
        self.stdout.write(self.style.SUCCESS(
            f"Scanned {result['scanned']}; created {result['created']}; "
            f"updated {result['updated']}; skipped empty {result['skipped_empty']}; "
            f"skipped quality {result['skipped_quality']}."
        ))
