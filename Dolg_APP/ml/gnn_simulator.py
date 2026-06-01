"""GNN Neural Circuit Simulator — Block A1 (master plan 3 weeks).

Skeleton MVP: GraphNN на ~50k параметров, который предсказывает напряжения узлов
по топологии и параметрам компонентов. Цель — 10× speedup над ngspice при <5%
relative error для типовых схем (резистивные делители, RC-filters, op-amp).

Архитектура (Phase 1 — MVP):
    Вход: feature-vectors на узлах (degree, neighbour-types) и edges (R/L/C value).
    Слои: 3× GraphConv → MLP head → predicted voltages per node.
    Train: на нашем 3060 датасете + ngspice-предсказания (offline labels).

Phase 2 (post-defense): расширение на токи ветвей + transient (RNN-aware GNN).

Использование:
    from Dolg_APP.ml.gnn_simulator import GNNSimulator
    sim = GNNSimulator.load(model_path='media/ml/gnn_v1.pt')
    voltages = sim.predict(scheme_data)
    # voltages = {'node_1': 3.21, 'node_2': 0.0, ...}

Fallback: если torch не установлен или модель не загружена — возвращаем None
и caller использует ngspice как обычно.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _require_torch():
    """Ленивая загрузка PyTorch — не падаем если torch не установлен."""
    try:
        import torch  # type: ignore
        from torch import nn  # type: ignore
        return torch, nn
    except ImportError as exc:
        raise RuntimeError(
            'PyTorch не установлен. Запустите: pip install -r requirements-ai.txt'
        ) from exc


# Размерности feature-векторов
NODE_FEATURE_DIM = 16   # degree + типы соседей + has_source + is_ground + ...
EDGE_FEATURE_DIM = 8    # R/L/C/V values normalized + component type one-hot
HIDDEN_DIM = 64
NUM_GRAPH_CONV_LAYERS = 3
MAX_NODES = 256         # cap for batch processing


def build_node_features(scheme_data: dict) -> tuple[list[list[float]], dict[str, int]]:
    """Преобразует scheme_data в матрицу node-features и mapping node→index.

    Каждая нода — это либо component_id, либо named net. Features:
        [0]    degree (число соединений)
        [1]    is_ground (1 если земля)
        [2]    is_source (1 если источник)
        [3]    is_passive (R/L/C)
        [4]    is_active (transistor/opamp)
        [5..9] component_type one-hot (R, C, L, D, V/GND)
        [10..15] reserved
    """
    components = scheme_data.get('components') or []
    connections = scheme_data.get('connections') or []

    # Step 1: map each component to a node index
    node_map = {}
    for i, c in enumerate(components):
        cid = c.get('id') or f'comp_{i}'
        node_map[cid] = i

    n_nodes = len(node_map)
    if n_nodes == 0:
        return [], {}

    # Step 2: count degrees
    degrees = [0] * n_nodes
    for conn in connections:
        f_id = (conn.get('from') or {}).get('compId')
        t_id = (conn.get('to') or {}).get('compId')
        if f_id in node_map:
            degrees[node_map[f_id]] += 1
        if t_id in node_map:
            degrees[node_map[t_id]] += 1

    # Step 3: build features per node
    features = []
    type_to_onehot = {
        'resistor': 0, 'capacitor': 1, 'inductor': 2,
        'diode': 3, 'battery': 4, 'ground': 4,
    }
    for c in components:
        cid = c.get('id') or ''
        ctype = (c.get('type') or '').lower()
        idx = node_map.get(cid, 0)
        deg = degrees[idx]
        is_ground = 1.0 if ctype == 'ground' else 0.0
        is_source = 1.0 if ctype in ('battery', 'current_source') else 0.0
        is_passive = 1.0 if ctype in ('resistor', 'capacitor', 'inductor') else 0.0
        is_active = 1.0 if ctype in ('npn', 'pnp', 'opamp', 'mosfet') else 0.0
        # one-hot — 5 slots
        onehot = [0.0] * 5
        if ctype in type_to_onehot:
            onehot[type_to_onehot[ctype]] = 1.0
        feat = [
            float(deg),
            is_ground, is_source,
            is_passive, is_active,
            *onehot,
            *([0.0] * 6),  # reserved (degree squared, neighbour sum, etc.)
        ]
        features.append(feat[:NODE_FEATURE_DIM])
    return features, node_map


def build_edge_features(scheme_data: dict, node_map: dict[str, int]) -> tuple[list[tuple[int, int]], list[list[float]]]:
    """Edge index + features. Каждый edge — connection между двумя компонентами.

    Edge features:
        [0]    resistance (normalized log10)
        [1]    capacitance (normalized log10)
        [2]    inductance (normalized log10)
        [3]    voltage (normalized)
        [4..7] reserved
    """
    components_by_id = {(c.get('id') or ''): c for c in scheme_data.get('components') or []}
    connections = scheme_data.get('connections') or []
    edges = []
    edge_features = []
    for conn in connections:
        f_id = (conn.get('from') or {}).get('compId')
        t_id = (conn.get('to') or {}).get('compId')
        if f_id not in node_map or t_id not in node_map:
            continue
        edges.append((node_map[f_id], node_map[t_id]))
        # Берём параметры edge — у соединения нет своих, но используем R/C/L from connecting comps
        f_comp = components_by_id.get(f_id) or {}
        r = float(f_comp.get('resistance') or 0)
        c = float(f_comp.get('capacitance') or 0)
        ind = float(f_comp.get('inductance') or 0)
        v = float(f_comp.get('voltage') or 0)
        feat = [
            _safe_log10(r),
            _safe_log10(c * 1e-6),    # uF → F
            _safe_log10(ind * 1e-3),  # mH → H
            v / 50.0,                  # voltage normalized по ~50В range
            *([0.0] * 4),
        ]
        edge_features.append(feat[:EDGE_FEATURE_DIM])
    return edges, edge_features


def _safe_log10(v):
    if v <= 0:
        return -10.0
    import math
    return math.log10(v) / 10.0  # normalize to ~[-1, 1]


def build_model():
    """Phase 1 GNN architecture — простая GraphConv → predict per-node voltage.

    GraphConv от scratch (без torch_geometric — оставляем зависимости лёгкими):
    h^(l+1)_i = ReLU(W * h^l_i + sum_{j in N(i)} V * (h^l_j || edge_features_ij))
    """
    torch, nn = _require_torch()

    class GraphConvLayer(nn.Module):
        def __init__(self, in_dim, out_dim, edge_dim=EDGE_FEATURE_DIM):
            super().__init__()
            self.lin_self = nn.Linear(in_dim, out_dim)
            self.lin_neigh = nn.Linear(in_dim + edge_dim, out_dim)
            self.activation = nn.ReLU()

        def forward(self, h, edges, edge_features):
            """h: (n_nodes, in_dim). edges: list of (i,j). edge_features: (n_edges, edge_dim)."""
            self_msg = self.lin_self(h)
            neigh_msg = torch.zeros_like(self_msg)
            if edges:
                for k, (i, j) in enumerate(edges):
                    if i >= h.shape[0] or j >= h.shape[0]:
                        continue
                    ef = edge_features[k]
                    msg = self.lin_neigh(torch.cat([h[j], ef], dim=-1))
                    neigh_msg[i] = neigh_msg[i] + msg
                    msg_back = self.lin_neigh(torch.cat([h[i], ef], dim=-1))
                    neigh_msg[j] = neigh_msg[j] + msg_back
            return self.activation(self_msg + neigh_msg)

    class GNNCircuitNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.node_embed = nn.Linear(NODE_FEATURE_DIM, HIDDEN_DIM)
            self.gconv1 = GraphConvLayer(HIDDEN_DIM, HIDDEN_DIM)
            self.gconv2 = GraphConvLayer(HIDDEN_DIM, HIDDEN_DIM)
            self.gconv3 = GraphConvLayer(HIDDEN_DIM, HIDDEN_DIM)
            # Per-node head: предсказываем voltage
            self.voltage_head = nn.Sequential(
                nn.Linear(HIDDEN_DIM, 32),
                nn.ReLU(),
                nn.Linear(32, 1),
            )

        def forward(self, node_features, edges, edge_features):
            h = self.node_embed(node_features)
            h = self.gconv1(h, edges, edge_features)
            h = self.gconv2(h, edges, edge_features)
            h = self.gconv3(h, edges, edge_features)
            voltages = self.voltage_head(h).squeeze(-1)
            return voltages

    return GNNCircuitNet()


class GNNSimulator:
    """Public-facing wrapper. Load + predict + (later) train."""

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

    def predict(self, scheme_data: dict) -> dict[str, float] | None:
        """Возвращает dict node_id → predicted voltage. None если нет модели."""
        if self.model is None:
            return None
        torch, _ = _require_torch()
        try:
            features, node_map = build_node_features(scheme_data)
            if not features:
                return None
            edges, edge_feats = build_edge_features(scheme_data, node_map)
            x = torch.tensor(features, dtype=torch.float32)
            ef = torch.tensor(edge_feats, dtype=torch.float32) if edge_feats else torch.zeros((0, EDGE_FEATURE_DIM))
            with torch.no_grad():
                voltages = self.model(x, edges, ef)
            # Map back to component IDs
            inv_map = {v: k for k, v in node_map.items()}
            return {inv_map[i]: float(voltages[i].item()) for i in range(len(features))}
        except Exception as exc:
            logger.warning('GNN predict failed: %s', exc)
            return None


def benchmark_against_ngspice(scheme_data: dict, ngspice_voltages: dict[str, float], model: GNNSimulator) -> dict:
    """Сравнение GNN-предсказаний с ngspice baseline.

    Возвращает: {mean_abs_err, max_abs_err, mean_rel_err}
    """
    pred = model.predict(scheme_data)
    if pred is None:
        return {'error': 'no_prediction'}
    common = set(pred.keys()) & set(ngspice_voltages.keys())
    if not common:
        return {'error': 'no_common_nodes'}
    errors = []
    rel_errors = []
    for k in common:
        diff = abs(pred[k] - ngspice_voltages[k])
        errors.append(diff)
        if abs(ngspice_voltages[k]) > 1e-6:
            rel_errors.append(diff / abs(ngspice_voltages[k]))
    mean_abs = sum(errors) / len(errors) if errors else 0
    max_abs = max(errors) if errors else 0
    mean_rel = sum(rel_errors) / len(rel_errors) if rel_errors else 0
    return {
        'mean_abs_err': mean_abs,
        'max_abs_err': max_abs,
        'mean_rel_err': mean_rel,
        'n_nodes': len(common),
    }
