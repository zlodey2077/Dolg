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
