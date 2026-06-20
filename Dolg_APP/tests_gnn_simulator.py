"""Tests for the GNN voltage-predictor (net-based graph + train loop).

Точность ещё дорабатывается (коллапс к среднему устранён residual+skip; узлы
источника точны, средний узел делителя ~30%). Тесты проверяют ИНФРАСТРУКТУРУ:
граф, обучение без падения, форму предсказания, генератор — не абсолютную точность.
"""

from __future__ import annotations

from Dolg_APP.ml import gnn_simulator as g
from Dolg_APP.services import monte_carlo


def _divider(v=9.0, r1=1000, r2=2000):
    return g._divider_scheme(v, r1, r2)


def test_build_graph_net_based():
    graph = g.build_graph(_divider())
    assert graph is not None
    node_features, edges, edge_features, n_nodes = graph
    assert n_nodes == 3  # ground + 2 узла делителя
    assert len(node_features) == n_nodes
    assert len(edges) == len(edge_features)
    # net 0 = ground → is_ground=1
    assert node_features[0][0] == 1.0
    # какой-то узел несёт source-magnitude (index 9 != 0)
    assert any(abs(f[9]) > 0 for f in node_features)


def test_build_graph_empty_returns_none():
    assert g.build_graph({'components': [], 'connections': []}) is None


def test_generate_schemes_solvable():
    schemes = g.generate_resistive_schemes(12, seed=1)
    assert len(schemes) == 12
    solved = 0
    for s in schemes:
        try:
            monte_carlo.solve_dc(monte_carlo.scheme_to_circuit(s))
            solved += 1
        except ValueError:
            pass
    assert solved >= 10  # подавляющее большинство решается MNA


def test_train_smoke_and_predict():
    schemes = g.generate_resistive_schemes(12, seed=2)
    model, metrics = g.train_gnn(schemes, epochs=3, lr=0.02, seed=2)
    assert metrics['samples'] >= 4
    assert metrics['final_train_loss'] is not None
    sim = g.GNNSimulator(model)
    pred = sim.predict(_divider())
    assert isinstance(pred, dict)
    assert pred[0] == 0.0  # ground жёстко 0
    assert len(pred) == 3


def test_benchmark_shape():
    schemes = g.generate_resistive_schemes(12, seed=3)
    model, _ = g.train_gnn(schemes, epochs=3, lr=0.02, seed=3)
    bench = g.benchmark_against_mna(_divider(), g.GNNSimulator(model))
    assert 'mean_rel_err' in bench and 'n_nodes' in bench
    assert bench['n_nodes'] == 3


def test_predict_without_model_none():
    assert g.GNNSimulator(None).predict(_divider()) is None


def test_collate_graphs_block_diagonal():
    import torch

    g1 = g.build_graph(_divider(9.0, 1000, 2000))
    g2 = g.build_graph(_divider(5.0, 470, 470))
    s1 = (g._to_tensors(g1), torch.zeros(g1[3]))
    s2 = (g._to_tensors(g2), torch.zeros(g2[3]))
    (x, edge_index, edge_features, ground_mask), y = g.collate_graphs([s1, s2])
    assert x.shape[0] == g1[3] + g2[3]
    assert y.shape[0] == g1[3] + g2[3]
    # ground каждого подграфа занулён (локальный 0 → offset)
    assert float(ground_mask[0]) == 0.0
    assert float(ground_mask[g1[3]]) == 0.0
    assert float(ground_mask[1]) == 1.0
    # рёбра 2-го графа смещены на число узлов 1-го
    if edge_index.numel() and g2[1]:
        assert int(edge_index.max()) >= g1[3]


def test_train_on_samples_batched_and_predict():
    schemes = g.generate_resistive_schemes(20, seed=5)
    samples = g._build_training_samples(schemes)
    model, metrics = g.train_gnn_on_samples(samples, epochs=4, lr=0.02, seed=5, batch_size=4)
    assert metrics['batch_size'] == 4
    assert metrics['final_train_loss'] is not None
    pred = g.GNNSimulator(model).predict(_divider())
    assert pred[0] == 0.0 and len(pred) == 3


def test_iter_corpus_respects_cap(tmp_path):
    import json

    schemes = [g._divider_scheme(9.0, 1000, 2000) for _ in range(5)]
    (tmp_path / 'a.json').write_text(json.dumps(schemes), encoding='utf-8')
    (tmp_path / 'b.json').write_text(json.dumps({'schemes': schemes}), encoding='utf-8')
    out = list(g.iter_corpus_schemes(7, dataset_root=tmp_path))
    assert len(out) == 7  # 5 из первого + 2 из второго, кап соблюдён


def test_build_corpus_samples_physics_labels(tmp_path):
    import json

    schemes = [g._divider_scheme(9.0, 1000, 2000) for _ in range(6)]
    (tmp_path / 'x.json').write_text(json.dumps(schemes), encoding='utf-8')
    samples, scanned = g.build_corpus_training_samples(100, max_samples=10, dataset_root=tmp_path)
    assert scanned == 6
    assert len(samples) == 6
    _, labels = samples[0]
    # делитель 1k/2k от 9 В: средний узел = 9·2000/3000 = 6 В среди меток
    assert any(abs(v - 6.0) < 0.5 for v in labels)


def test_benchmark_samples_shape():
    schemes = g.generate_resistive_schemes(16, seed=7)
    samples = g._build_training_samples(schemes)
    model, _ = g.train_gnn_on_samples(samples, epochs=3, lr=0.02, seed=7, batch_size=8)
    bench = g.benchmark_samples(model, samples[:5])
    assert 'mean_rel_err' in bench and 'mean_abs_err' in bench
    assert bench['test_samples'] == 5
