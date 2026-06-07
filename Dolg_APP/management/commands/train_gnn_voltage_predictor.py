"""Обучение GNN-предсказателя напряжений узлов (Block A1) на процедурных схемах.

Генерирует резистивные DC-схемы, берёт ground-truth из NumPy MNA (solve_dc),
обучает GraphNN (residual + skip), сохраняет media/ml/gnn_v1.pt и печатает
метрики + бенч vs MNA на контрольном делителе.

    python manage.py train_gnn_voltage_predictor --schemes 400 --epochs 80 --json

Статус: коллапс к среднему устранён; узлы источника точны, средний узел делителя
~30% — точность дорабатывается (больше данных/раундов message-passing).
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Обучает GNN-предсказатель напряжений узлов (MNA как ground-truth).'

    def add_arguments(self, parser):
        parser.add_argument('--schemes', type=int, default=400, help='Сколько схем сгенерировать.')
        parser.add_argument('--epochs', type=int, default=80)
        parser.add_argument('--lr', type=float, default=0.02)
        parser.add_argument('--seed', type=int, default=42)
        parser.add_argument('--json', action='store_true', help='Вывести метрики в JSON.')

    def handle(self, *args, **options):
        try:
            from Dolg_APP.ml import gnn_simulator as gnn
        except Exception as exc:
            raise CommandError(f'GNN недоступен: {exc}') from exc

        try:
            gnn._require_torch()
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc

        schemes = gnn.generate_resistive_schemes(options['schemes'], seed=options['seed'])
        model, metrics = gnn.train_gnn(
            schemes, epochs=options['epochs'], lr=options['lr'], seed=options['seed']
        )

        model_path = Path(settings.MEDIA_ROOT) / 'ml' / 'gnn_v1.pt'
        gnn.save_model(model, model_path)

        # Бенч на контрольном делителе 9В/1k/2k.
        bench = gnn.benchmark_against_mna(gnn._divider_scheme(9.0, 1000, 2000), gnn.GNNSimulator(model))
        result = {
            'ok': True,
            'model_path': str(model_path),
            'samples': metrics['samples'],
            'epochs': metrics['epochs'],
            'final_train_loss': metrics['final_train_loss'],
            'best_val_loss': metrics['best_val_loss'],
            'bench_divider': bench,
        }

        if options['json']:
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            self.stdout.write(self.style.SUCCESS(f'GNN обучён → {model_path}'))
            self.stdout.write(
                f'  samples={result["samples"]} · train_loss={result["final_train_loss"]} · '
                f'val_loss={result["best_val_loss"]}'
            )
            self.stdout.write(f'  bench (делитель 9В/1k/2k): {bench}')
