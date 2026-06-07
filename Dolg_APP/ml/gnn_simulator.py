"""GNN Neural Circuit Simulator — Block A1 (master plan 3 weeks).

Graph Neural Network, предсказывающий напряжения УЗЛОВ (электрических сетей) по
топологии и параметрам компонентов. Цель — быстрый сурогат DC-анализа: 10×+
speedup над MNA при <5% relative error на типовых линейных схемах.

Формулировка (физически корректная для цепей):
    - УЗЛЫ графа = электрические сети (как в MNA), net 0 = ground.
    - РЁБРА = компоненты (R/C/L/V/D), соединяющие две сети; их параметры —
      признаки ребра.
    - Метки (ground truth) = напряжения сетей из `monte_carlo.solve_dc` (NumPy MNA).

Это совпадает с узловым определением MNA, поэтому метки берутся напрямую из
solve_dc — без рассинхронизации «компонент vs сеть».

Архитектура: node-embed → 3× GraphConv (from scratch, без torch_geometric) →
per-node voltage head. Train: MSE(GNN_voltages, MNA_voltages).

Использование:
    from Dolg_APP.ml.gnn_simulator import GNNSimulator
    sim = GNNSimulator.load('media/ml/gnn_v1.pt')
    voltages = sim.predict(scheme_data)   # {net_idx: voltage}, net 0 = ground = 0

Fallback: если torch не установлен / модель не загружена — predict() → None,
caller использует MNA как обычно.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

logger = logging.getLogger(__name__)


def _require_torch():
    """Ленивая загрузка PyTorch — не падаем если torch не установлен."""
    try:
        import torch  # type: ignore
        from torch import nn  # type: ignore

        return torch, nn
    except ImportError as exc:
        raise RuntimeError('PyTorch не установлен. Запустите: pip install -r requirements-ai.txt') from exc


# Размерности feature-векторов
NODE_FEATURE_DIM = 12  # is_ground, degree, счётчики типов (R/C/L/V/D), touches_source, log(minR), ...
EDGE_FEATURE_DIM = 8  # type one-hot (R/C/L/V/D) + normalized value + reserved
HIDDEN_DIM = 64
NUM_GRAPH_CONV_LAYERS = 3
MAX_NODES = 256
# Нормировка напряжений: цели делим на это при обучении, умножаем при predict —
# MSE-loss становится хорошо масштабированным (генератор использует V ≤ 24).
VOLTAGE_SCALE = 24.0

# Тип элемента (из monte_carlo.scheme_to_circuit) → индекс one-hot.
_TYPE_IDX = {'R': 0, 'C': 1, 'L': 2, 'V': 3, 'D': 4}


def _safe_log10(value: float) -> float:
    if value <= 0:
        return -10.0
    return math.log10(value) / 10.0  # normalize to ~[-1, 1]


def _norm_edge_value(elem_type: str, value: float) -> float:
    """Нормализованное значение параметра ребра под тип компонента."""
    if elem_type == 'R':
        return _safe_log10(value)
    if elem_type == 'V':
        return float(value) / 50.0
    if elem_type in ('C', 'L'):
        return _safe_log10(value)
    return 0.0


def build_graph_from_circuit(circuit: dict):
    """Из MNA-circuit (monte_carlo.scheme_to_circuit) строит граф для GNN.

    Returns (node_features, edges, edge_features, n_nodes) либо None если узлов
    нет / только ground / слишком большой граф."""
    n_nodes = int(circuit.get('n_nodes') or 0)
    elements = circuit.get('elements') or []
    if n_nodes <= 1 or n_nodes > MAX_NODES:
        return None

    node_features = [[0.0] * NODE_FEATURE_DIM for _ in range(n_nodes)]
    for net in range(n_nodes):
        node_features[net][0] = 1.0 if net == 0 else 0.0  # is_ground

    edges: list[tuple[int, int]] = []
    edge_features: list[list[float]] = []
    min_r = [math.inf] * n_nodes

    for elem in elements:
        a, b = elem['nodes']
        etype = elem['type']
        value = float(elem.get('value') or 0.0)
        for net in (a, b):
            if 0 <= net < n_nodes:
                node_features[net][1] += 1.0  # degree
                if etype in _TYPE_IDX:
                    node_features[net][2 + _TYPE_IDX[etype]] += 1.0  # счётчик по типу (2..6)
                if etype == 'V':
                    node_features[net][7] = 1.0  # сеть касается источника
                if etype == 'R' and value > 0:
                    min_r[net] = min(min_r[net], value)
        if etype == 'V':
            # Величина источника прямо в node-features: V(a)-V(b)=value (MNA).
            if 0 <= a < n_nodes:
                node_features[a][9] += float(value) / 50.0
            if 0 <= b < n_nodes:
                node_features[b][9] -= float(value) / 50.0
        if a == b:
            continue  # self-loop не даёт ребра
        onehot = [0.0] * 5
        if etype in _TYPE_IDX:
            onehot[_TYPE_IDX[etype]] = 1.0
        feat = [*onehot, _norm_edge_value(etype, value), 0.0, 0.0]
        edges.append((a, b))
        edge_features.append(feat[:EDGE_FEATURE_DIM])

    for net in range(n_nodes):
        node_features[net][8] = _safe_log10(min_r[net]) if min_r[net] != math.inf else 0.0

    return node_features, edges, edge_features, n_nodes


def build_graph(scheme_data: dict):
    """scheme_data → граф для GNN (через monte_carlo.scheme_to_circuit)."""
    from Dolg_APP.services import monte_carlo

    circuit = monte_carlo.scheme_to_circuit(scheme_data)
    return build_graph_from_circuit(circuit)


def build_model():
    """GraphConv-сеть (from scratch): node-embed → 3× GraphConv → voltage head.

    h^(l+1)_i = ReLU(W·h^l_i + Σ_{j∈N(i)} V·(h^l_j ⊕ edge_ij))
    """
    torch, nn = _require_torch()

    class GraphConvLayer(nn.Module):
        def __init__(self, in_dim, out_dim, edge_dim=EDGE_FEATURE_DIM):
            super().__init__()
            self.lin_self = nn.Linear(in_dim, out_dim)
            self.lin_neigh = nn.Linear(in_dim + edge_dim, out_dim)
            self.activation = nn.ReLU()

        def forward(self, h, edge_index, edge_features):
            """h: (n,in). edge_index: (2,E) long. edge_features: (E,edge_dim)."""
            self_msg = self.lin_self(h)
            neigh_msg = torch.zeros_like(self_msg)
            if edge_index.numel():
                src, dst = edge_index[0], edge_index[1]
                # неориентированно: сообщения в обе стороны
                msg_fwd = self.lin_neigh(torch.cat([h[src], edge_features], dim=-1))
                neigh_msg = neigh_msg.index_add(0, dst, msg_fwd)
                msg_bwd = self.lin_neigh(torch.cat([h[dst], edge_features], dim=-1))
                neigh_msg = neigh_msg.index_add(0, src, msg_bwd)
            out = self.activation(self_msg + neigh_msg)
            # Residual против over-smoothing (на малых графах 3 раунда message-
            # passing гомогенизируют узлы → коллапс к среднему).
            if out.shape == h.shape:
                out = out + h
            return out

    class GNNCircuitNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.node_embed = nn.Linear(NODE_FEATURE_DIM, HIDDEN_DIM)
            self.gconv1 = GraphConvLayer(HIDDEN_DIM, HIDDEN_DIM)
            self.gconv2 = GraphConvLayer(HIDDEN_DIM, HIDDEN_DIM)
            self.gconv3 = GraphConvLayer(HIDDEN_DIM, HIDDEN_DIM)
            # Голова видит и GNN-эмбеддинг, и СЫРЫЕ node-features (skip) — чтобы
            # source-magnitude доходил до читалки напрямую (узел источника = V).
            self.voltage_head = nn.Sequential(
                nn.Linear(HIDDEN_DIM + NODE_FEATURE_DIM, 32),
                nn.ReLU(),
                nn.Linear(32, 1),
            )

        def forward(self, node_features, edge_index, edge_features):
            h = self.node_embed(node_features)
            h = self.gconv1(h, edge_index, edge_features)
            h = self.gconv2(h, edge_index, edge_features)
            h = self.gconv3(h, edge_index, edge_features)
            h = torch.cat([h, node_features], dim=-1)
            voltages = self.voltage_head(h).squeeze(-1)
            # net 0 = ground = 0 В: жёстко зануляем (физическое ограничение).
            if voltages.numel():
                mask = torch.ones_like(voltages)
                mask[0] = 0.0
                voltages = voltages * mask
            return voltages

    return GNNCircuitNet()


def _to_tensors(graph):
    """graph → (x, edge_index, edge_features) тензоры."""
    torch, _ = _require_torch()
    node_features, edges, edge_features, _ = graph
    x = torch.tensor(node_features, dtype=torch.float32)
    if edges:
        edge_index = torch.tensor(edges, dtype=torch.long).t().contiguous()
        ef = torch.tensor(edge_features, dtype=torch.float32)
    else:
        edge_index = torch.zeros((2, 0), dtype=torch.long)
        ef = torch.zeros((0, EDGE_FEATURE_DIM), dtype=torch.float32)
    return x, edge_index, ef


def _build_training_samples(schemes):
    """schemes → [(graph, label_voltages_list)] для решаемых MNA схем."""
    from Dolg_APP.services import monte_carlo

    samples = []
    for scheme in schemes:
        circuit = monte_carlo.scheme_to_circuit(scheme)
        graph = build_graph_from_circuit(circuit)
        if graph is None:
            continue
        try:
            voltages = monte_carlo.solve_dc(circuit)['voltages']
        except ValueError:
            continue  # вырожденная матрица — пропускаем
        n_nodes = graph[3]
        labels = [float(voltages.get(net, 0.0)) for net in range(n_nodes)]
        samples.append((graph, labels))
    return samples


def train_gnn(
    schemes,
    *,
    epochs: int = 60,
    lr: float = 0.01,
    seed: int = 42,
    val_split: float = 0.15,
) -> tuple:
    """Обучает GNN предсказывать напряжения узлов (MSE vs MNA solve_dc).

    Returns (model, metrics). metrics: {samples, train_loss, val_loss, history, ...}.
    """
    torch, nn = _require_torch()
    torch.manual_seed(seed)

    samples = _build_training_samples(schemes)
    if len(samples) < 4:
        raise ValueError(f'too few solvable schemes for training: {len(samples)}')

    tensors = [
        (_to_tensors(g), torch.tensor([v / VOLTAGE_SCALE for v in y], dtype=torch.float32))
        for g, y in samples
    ]
    n_val = max(1, int(len(tensors) * val_split))
    val_set = tensors[:n_val]
    train_set = tensors[n_val:]

    model = build_model()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    loss_fn = nn.MSELoss()

    history = []
    best_val = math.inf
    best_state = None
    for epoch in range(epochs):
        model.train()
        total = 0.0
        for (x, ei, ef), y in train_set:
            optimizer.zero_grad()
            pred = model(x, ei, ef)
            loss = loss_fn(pred, y)
            loss.backward()
            optimizer.step()
            total += float(loss.item())
        scheduler.step()

        model.eval()
        vtotal = 0.0
        with torch.no_grad():
            for (x, ei, ef), y in val_set:
                vtotal += float(loss_fn(model(x, ei, ef), y).item())
        train_loss = total / max(1, len(train_set))
        val_loss = vtotal / max(1, len(val_set))
        history.append(
            {'epoch': epoch + 1, 'train_loss': round(train_loss, 5), 'val_loss': round(val_loss, 5)}
        )
        if val_loss < best_val:
            best_val = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}

    if best_state is not None:
        model.load_state_dict(best_state)
    metrics = {
        'samples': len(samples),
        'train_samples': len(train_set),
        'val_samples': len(val_set),
        'epochs': epochs,
        'final_train_loss': history[-1]['train_loss'] if history else None,
        'best_val_loss': round(best_val, 5),
        'history': history,
    }
    return model, metrics


def save_model(model, model_path: str | Path) -> None:
    torch, _ = _require_torch()
    path = Path(model_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), str(path))


class GNNSimulator:
    """Public-facing wrapper: load + predict."""

    def __init__(self, model=None):
        self.model = model

    @classmethod
    def load(cls, model_path: str | Path) -> GNNSimulator:
        torch, _ = _require_torch()
        model = build_model()
        path = Path(model_path)
        if path.exists():
            try:
                model.load_state_dict(torch.load(str(path), map_location='cpu', weights_only=True))
                model.eval()
                logger.info('GNN model loaded from %s', path)
            except Exception as exc:
                logger.warning('GNN model load failed (%s) — using fresh init', exc)
        return cls(model)

    def predict(self, scheme_data: dict) -> dict[int, float] | None:
        """{net_idx: predicted voltage} (net 0 = ground = 0). None если нет модели/графа."""
        if self.model is None:
            return None
        torch, _ = _require_torch()
        try:
            graph = build_graph(scheme_data)
            if graph is None:
                return None
            x, ei, ef = _to_tensors(graph)
            with torch.no_grad():
                voltages = self.model(x, ei, ef)
            return {net: float(voltages[net].item()) * VOLTAGE_SCALE for net in range(graph[3])}
        except Exception as exc:
            logger.warning('GNN predict failed: %s', exc)
            return None


def benchmark_against_mna(scheme_data: dict, model: GNNSimulator) -> dict:
    """Сравнение GNN-предсказаний с MNA (solve_dc) + замер времени.

    Returns {mean_abs_err, max_abs_err, mean_rel_err, n_nodes, mna_ms, gnn_ms, speedup}.
    """
    import time

    from Dolg_APP.services import monte_carlo

    circuit = monte_carlo.scheme_to_circuit(scheme_data)
    t0 = time.perf_counter_ns()
    try:
        mna = monte_carlo.solve_dc(circuit)['voltages']
    except ValueError:
        return {'error': 'singular_matrix'}
    mna_ms = (time.perf_counter_ns() - t0) / 1e6

    t0 = time.perf_counter_ns()
    pred = model.predict(scheme_data)
    gnn_ms = (time.perf_counter_ns() - t0) / 1e6
    if pred is None:
        return {'error': 'no_prediction'}

    common = set(pred) & set(mna)
    if not common:
        return {'error': 'no_common_nodes'}
    abs_errs, rel_errs = [], []
    for net in common:
        diff = abs(pred[net] - mna[net])
        abs_errs.append(diff)
        if abs(mna[net]) > 1e-6:
            rel_errs.append(diff / abs(mna[net]))
    return {
        'mean_abs_err': round(sum(abs_errs) / len(abs_errs), 5),
        'max_abs_err': round(max(abs_errs), 5),
        'mean_rel_err': round(sum(rel_errs) / len(rel_errs), 5) if rel_errs else 0.0,
        'n_nodes': len(common),
        'mna_ms': round(mna_ms, 4),
        'gnn_ms': round(gnn_ms, 4),
        'speedup': round(mna_ms / gnn_ms, 2) if gnn_ms > 0 else None,
    }


# ─── Процедурный генератор обучающих схем (резистивные DC-цепи) ───────────
def generate_resistive_schemes(count: int = 200, *, seed: int = 42) -> list[dict]:
    """Генерирует разнообразные DC-схемы (делители, лестницы, последовательные
    цепочки) со случайными номиналами — все решаемы MNA. Для обучения GNN."""
    import random

    rng = random.Random(seed)
    schemes: list[dict] = []
    r_values = [100, 220, 470, 1000, 2200, 4700, 10000, 22000, 47000, 100000]

    for _ in range(count):
        kind = rng.choice(['divider', 'ladder', 'series'])
        v = rng.choice([3.3, 5.0, 9.0, 12.0, 24.0])
        if kind == 'divider':
            r1, r2 = rng.choice(r_values), rng.choice(r_values)
            schemes.append(_divider_scheme(v, r1, r2))
        elif kind == 'series':
            k = rng.randint(2, 4)
            schemes.append(_series_scheme(v, [rng.choice(r_values) for _ in range(k)]))
        else:
            schemes.append(_ladder_scheme(v, [rng.choice(r_values) for _ in range(rng.randint(3, 5))]))
    return schemes


def _divider_scheme(v, r1, r2):
    return {
        'components': [
            {'id': 'V1', 'type': 'battery', 'voltage': v, 'ports': [{'id': '+'}, {'id': '-'}]},
            {'id': 'R1', 'type': 'resistor', 'resistance': r1, 'ports': [{'id': '1'}, {'id': '2'}]},
            {'id': 'R2', 'type': 'resistor', 'resistance': r2, 'ports': [{'id': '1'}, {'id': '2'}]},
            {'id': 'G', 'type': 'ground', 'ports': [{'id': '1'}]},
        ],
        'connections': [
            {'from': {'compId': 'V1', 'portId': '+'}, 'to': {'compId': 'R1', 'portId': '1'}},
            {'from': {'compId': 'R1', 'portId': '2'}, 'to': {'compId': 'R2', 'portId': '1'}},
            {'from': {'compId': 'R2', 'portId': '2'}, 'to': {'compId': 'G', 'portId': '1'}},
            {'from': {'compId': 'V1', 'portId': '-'}, 'to': {'compId': 'G', 'portId': '1'}},
        ],
    }


def _series_scheme(v, resistors):
    comps = [{'id': 'V1', 'type': 'battery', 'voltage': v, 'ports': [{'id': '+'}, {'id': '-'}]}]
    conns = []
    prev = ('V1', '+')
    for i, r in enumerate(resistors):
        rid = f'R{i + 1}'
        comps.append({'id': rid, 'type': 'resistor', 'resistance': r, 'ports': [{'id': '1'}, {'id': '2'}]})
        conns.append({'from': {'compId': prev[0], 'portId': prev[1]}, 'to': {'compId': rid, 'portId': '1'}})
        prev = (rid, '2')
    comps.append({'id': 'G', 'type': 'ground', 'ports': [{'id': '1'}]})
    conns.append({'from': {'compId': prev[0], 'portId': prev[1]}, 'to': {'compId': 'G', 'portId': '1'}})
    conns.append({'from': {'compId': 'V1', 'portId': '-'}, 'to': {'compId': 'G', 'portId': '1'}})
    return {'components': comps, 'connections': conns}


def _ladder_scheme(v, resistors):
    """Лестница: последовательные R сверху + шунты на землю на каждом узле."""
    comps = [{'id': 'V1', 'type': 'battery', 'voltage': v, 'ports': [{'id': '+'}, {'id': '-'}]}]
    conns = []
    prev = ('V1', '+')
    half = max(1, len(resistors) // 2)
    series_rs, shunt_rs = resistors[:half], resistors[half:] or [resistors[-1]]
    nodes = []
    for i, r in enumerate(series_rs):
        rid = f'RS{i + 1}'
        comps.append({'id': rid, 'type': 'resistor', 'resistance': r, 'ports': [{'id': '1'}, {'id': '2'}]})
        conns.append({'from': {'compId': prev[0], 'portId': prev[1]}, 'to': {'compId': rid, 'portId': '1'}})
        prev = (rid, '2')
        nodes.append(rid)
    comps.append({'id': 'G', 'type': 'ground', 'ports': [{'id': '1'}]})
    for i, r in enumerate(shunt_rs):
        rid = f'RP{i + 1}'
        anchor = nodes[min(i, len(nodes) - 1)]
        comps.append({'id': rid, 'type': 'resistor', 'resistance': r, 'ports': [{'id': '1'}, {'id': '2'}]})
        conns.append({'from': {'compId': anchor, 'portId': '2'}, 'to': {'compId': rid, 'portId': '1'}})
        conns.append({'from': {'compId': rid, 'portId': '2'}, 'to': {'compId': 'G', 'portId': '1'}})
    conns.append({'from': {'compId': prev[0], 'portId': prev[1]}, 'to': {'compId': 'G', 'portId': '1'}})
    conns.append({'from': {'compId': 'V1', 'portId': '-'}, 'to': {'compId': 'G', 'portId': '1'}})
    return {'components': comps, 'connections': conns}
