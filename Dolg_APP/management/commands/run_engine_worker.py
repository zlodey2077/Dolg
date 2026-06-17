"""Run queued server-engine jobs."""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand

from Dolg_APP.services.engine_jobs import default_worker_id, run_due_engine_jobs


class Command(BaseCommand):
    help = 'Run queued EngineJob records via local engine adapters.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Run one polling pass and exit.')
        parser.add_argument('--limit', type=int, default=1, help='Jobs to process per polling pass.')
        parser.add_argument('--sleep', type=float, default=2.0, help='Sleep seconds between polling passes.')
        parser.add_argument(
            '--max-loops', type=int, default=0, help='Stop after N polling passes; 0 means forever.'
        )
        parser.add_argument('--worker-id', default='', help='Stable worker name stored on EngineJob.worker.')
        parser.add_argument(
            '--engine',
            action='append',
            dest='engines',
            default=None,
            help='Engine id to process. Defaults to local adapters only.',
        )

    def handle(self, *args, **options):
        worker_id = options.get('worker_id') or default_worker_id()
        limit = max(1, int(options.get('limit') or 1))
        sleep_s = max(0.1, float(options.get('sleep') or 2.0))
        max_loops = max(0, int(options.get('max_loops') or 0))
        engines = options.get('engines')

        loop = 0
        while True:
            loop += 1
            outcome = run_due_engine_jobs(limit=limit, worker_id=worker_id, engine_ids=engines)
            processed = outcome['processed']
            if processed:
                self.stdout.write(self.style.SUCCESS(f'processed={processed} worker={worker_id}'))
                for job in outcome['jobs']:
                    self.stdout.write(
                        f'  #{job["id"]} {job["engine_id"]} {job["analysis_type"]} -> {job["status"]}'
                    )
            else:
                self.stdout.write(f'no queued jobs for worker={worker_id}')

            if options.get('once') or (max_loops and loop >= max_loops):
                return
            time.sleep(sleep_s)
