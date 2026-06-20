"""Обучение GNN-симулятора напряжений на физ-метках (MNA) — трек 1+5 плана нейронки.

Источники сэмплов: процедурные DC-схемы (всегда решаемы) + MNA-решаемые из реального
корпуса (стрим, без OOM). Метки = напряжения узлов из solve_dc. После обучения — бенч на
held-out test (rel-err vs MNA) + замер ускорения GNN над MNA на нескольких схемах.

    python manage.py train_gnn_simulator --max-schemes 4000 --procedural 400 --epochs 60
    python manage.py train_gnn_simulator --json
"""

from __future__ import annotations

import json
import random
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Обучает GNN-симулятор напряжений (физ-метки MNA, процедурные + реальный корпус).'

    def add_arguments(self, parser):
        parser.add_argument('--max-schemes', type=int, default=4000, help='Потолок схем из корпуса (стрим).')
        parser.add_argument(
            '--max-samples', type=int, default=1500, help='Потолок MNA-решаемых сэмплов из корпуса.'
        )
        parser.add_argument('--procedural', type=int, default=400, help='Сколько процедурных схем добавить.')
        parser.add_argument('--epochs', type=int, default=60)
        parser.add_argument('--batch-size', type=int, default=16)
        parser.add_argument('--lr', type=float, default=0.01)
        parser.add_argument('--seed', type=int, default=42)
        parser.add_argument('--out', type=str, default=None, help='Путь .pt (default media/ml/gnn_v1.pt).')
        parser.add_argument('--json', action='store_true', dest='as_json')

    def handle(self, *args, **opts):
        from Dolg_APP.ml import gnn_simulator as g
        from Dolg_APP.ml.neural import torch_available

        if not torch_available():
            raise CommandError('PyTorch недоступен. Установите: pip install -r requirements-ai.txt')

        from pathlib import Path

        out_path = Path(opts['out']) if opts['out'] else Path(settings.MEDIA_ROOT) / 'ml' / 'gnn_v1.pt'

        # 1) Процедурные схемы (физика всегда решаема MNA).
        samples = []
        if opts['procedural'] > 0:
            proc = g.generate_resistive_schemes(opts['procedural'], seed=opts['seed'])
            samples.extend(g._build_training_samples(proc))
        self.stdout.write(f'Процедурных решаемых сэмплов: {len(samples)}')

        # 2) Реальный корпус (стрим, физ-метки, без OOM).
        corpus_samples, scanned = g.build_corpus_training_samples(
            opts['max_schemes'], max_samples=opts['max_samples']
        )
        samples.extend(corpus_samples)
        self.stdout.write(
            f'Корпус: просмотрено {scanned} схем, MNA-решаемых +{len(corpus_samples)} '
            f'(итого сэмплов {len(samples)})'
        )
        if len(samples) < 8:
            raise CommandError(f'Слишком мало решаемых схем для обучения: {len(samples)}')

        # 3) Held-out test split по сэмплам.
        random.Random(opts['seed']).shuffle(samples)
        n_test = max(2, len(samples) // 10)
        test_samples = samples[:n_test]
        train_samples = samples[n_test:]

        # 4) Обучение (минибатчинг).
        t0 = time.perf_counter()
        model, metrics = g.train_gnn_on_samples(
            train_samples,
            epochs=opts['epochs'],
            lr=opts['lr'],
            seed=opts['seed'],
            batch_size=opts['batch_size'],
        )
        train_secs = round(time.perf_counter() - t0, 1)

        # 5) Бенч точности на held-out test + ускорение над MNA на процедурных схемах.
        accuracy = g.benchmark_samples(model, test_samples)
        speedups = []
        if opts['procedural'] > 0:
            sim = g.GNNSimulator(model)
            for scheme in g.generate_resistive_schemes(min(10, opts['procedural']), seed=opts['seed'] + 1):
                bench = g.benchmark_against_mna(scheme, sim)
                if isinstance(bench.get('speedup'), (int, float)):
                    speedups.append(bench['speedup'])
        mean_speedup = round(sum(speedups) / len(speedups), 2) if speedups else None

        # 6) Сохранение.
        g.save_model(model, out_path)

        result = {
            'ok': True,
            'model_path': str(out_path),
            'train_samples': len(train_samples),
            'test_samples': len(test_samples),
            'corpus_scanned': scanned,
            'corpus_solvable': len(corpus_samples),
            'train_seconds': train_secs,
            'best_val_loss': metrics.get('best_val_loss'),
            'final_train_loss': metrics.get('final_train_loss'),
            'test_mean_rel_err': accuracy.get('mean_rel_err'),
            'test_mean_abs_err': accuracy.get('mean_abs_err'),
            'test_nodes': accuracy.get('test_nodes'),
            'mean_speedup_vs_mna': mean_speedup,
        }

        if opts['as_json']:
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            rel = result['test_mean_rel_err']
            rel_pct = f'{rel * 100:.1f}%' if isinstance(rel, (int, float)) else 'n/a'
            self.stdout.write(
                self.style.SUCCESS(
                    f'GNN обучен: rel-err(test)={rel_pct}, abs-err={result["test_mean_abs_err"]} В, '
                    f'ускорение×{result["mean_speedup_vs_mna"]}, best_val={result["best_val_loss"]} '
                    f'-> {out_path}'
                )
            )
