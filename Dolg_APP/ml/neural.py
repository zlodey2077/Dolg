"""Tiny PyTorch neural backend for DOLG circuit hints.

This is intentionally small and lazy-loaded. Django startup must not import
torch unless the neural backend is explicitly requested.
"""

from __future__ import annotations

import json
import math
import random
import importlib.util
from collections import Counter
from pathlib import Path

from django.conf import settings

COMPONENT_TYPES = [
    'battery',
    'ground',
    'resistor',
    'capacitor',
    'inductor',
    'led',
    'diode',
    'transistor',
    'ic',
    'button',
]

TOPOLOGY_LABELS = [
    'empty',
    'generic',
    'voltage_divider',
    'rc_network',
    'led_indicator',
]

NEXT_COMPONENT_LABELS = [
    'battery',
    'ground',
    'resistor',
    'capacitor',
    'led',
    'catalog_binding',
    'measurement_probe',
]

BASE_FEATURE_DIM = len(COMPONENT_TYPES) + 10
GRAPH_FEATURE_DIM = 10
FEATURE_DIM = BASE_FEATURE_DIM + GRAPH_FEATURE_DIM
MODEL_VERSION = '0.3.0-tiny-graph-pytorch'


class NeuralUnavailable(RuntimeError):
    pass


def torch_available():
    return importlib.util.find_spec('torch') is not None


def default_model_path():
    return Path(settings.MEDIA_ROOT) / 'ml' / 'tiny_circuit_ai.pt'


def _component_type(component):
    raw = str(component.get('type') or '').strip().lower()
    aliases = {
        'v': 'battery',
        'vsource': 'battery',
        'source': 'battery',
        'gnd': 'ground',
        'r': 'resistor',
        'res': 'resistor',
        'c': 'capacitor',
        'cap': 'capacitor',
        'q': 'transistor',
        'npn': 'transistor',
        'pnp': 'transistor',
        'u': 'ic',
    }
    if raw in aliases:
        return aliases[raw]
    if raw.startswith('res'):
        return 'resistor'
    if raw.startswith('cap'):
        return 'capacitor'
    if raw.startswith('bat'):
        return 'battery'
    return raw or 'unknown'


def _components(scheme_data):
    if not isinstance(scheme_data, dict):
        return []
    return [item for item in scheme_data.get('components') or [] if isinstance(item, dict)]


def _connections(scheme_data):
    if not isinstance(scheme_data, dict):
        return []
    return [item for item in scheme_data.get('connections') or [] if isinstance(item, dict)]


def _detect_teacher_topology(scheme_data):
    components = _components(scheme_data)
    if not components:
        return 'empty'
    counts = Counter(_component_type(item) for item in components)
    has_ground = counts.get('ground', 0) > 0
    has_source = counts.get('battery', 0) > 0
    if counts.get('led', 0) and counts.get('resistor', 0):
        return 'led_indicator'
    if counts.get('capacitor', 0) and counts.get('resistor', 0) and has_ground and has_source:
        return 'rc_network'
    if counts.get('resistor', 0) >= 2 and has_ground and has_source:
        return 'voltage_divider'
    return 'generic'


def _risk_teacher(scheme_data):
    components = _components(scheme_data)
    if not components:
        return 0.2
    counts = Counter(_component_type(item) for item in components)
    risk = 0.05
    if counts.get('battery', 0) and not counts.get('ground', 0):
        risk += 0.55
    if counts.get('led', 0) and not counts.get('resistor', 0):
        risk += 0.35
    if len(_connections(scheme_data)) == 0 and len(components) > 1:
        risk += 0.35
    return min(1.0, risk)


def _next_component_teacher(scheme_data):
    components = _components(scheme_data)
    counts = Counter(_component_type(item) for item in components)
    if not components:
        return 'battery'
    if counts.get('battery', 0) and not counts.get('ground', 0):
        return 'ground'
    if counts.get('led', 0) and not counts.get('resistor', 0):
        return 'resistor'
    if counts.get('battery', 0) and counts.get('resistor', 0) and not counts.get('capacitor', 0):
        return 'capacitor'
    if counts.get('resistor', 0) and counts.get('ground', 0):
        return 'measurement_probe'
    return 'catalog_binding'


def scheme_to_features(scheme_data):
    components = _components(scheme_data)
    connections = _connections(scheme_data)
    counts = Counter(_component_type(item) for item in components)
    total = max(1, len(components))
    features = [counts.get(name, 0) / total for name in COMPONENT_TYPES]

    used = set()
    for conn in connections:
        source = (conn.get('from') or {}).get('compId')
        target = (conn.get('to') or {}).get('compId')
        if source is not None:
            used.add(str(source))
        if target is not None:
            used.add(str(target))
    component_ids = {str(item.get('id')) for item in components if item.get('id') is not None}
    isolated_count = len(component_ids - used)
    has_ground = 1.0 if counts.get('ground', 0) else 0.0
    has_source = 1.0 if counts.get('battery', 0) else 0.0
    density = len(connections) / max(1, len(components))
    passive = counts.get('resistor', 0) + counts.get('capacitor', 0) + counts.get('inductor', 0)
    active = counts.get('battery', 0) + counts.get('led', 0) + counts.get('diode', 0) + counts.get('transistor', 0) + counts.get('ic', 0)

    features.extend([
        min(len(components), 20) / 20.0,
        min(len(connections), 30) / 30.0,
        has_ground,
        has_source,
        min(isolated_count, 10) / 10.0,
        min(density, 3.0) / 3.0,
        passive / total,
        active / total,
        1.0 if counts.get('led', 0) and not counts.get('resistor', 0) else 0.0,
        1.0 if has_source and not has_ground else 0.0,
    ])
    features.extend(_graph_features(scheme_data, total))
    return features


def _graph_features(scheme_data, total):
    """Small NetworkX-derived topology features; falls back to zeros."""
    try:
        from Dolg_APP.services.schematic_graph import analyze_graph_topology
        metrics = (analyze_graph_topology(scheme_data).get('metrics') or {})
    except Exception:
        return [0.0] * GRAPH_FEATURE_DIM
    topology = metrics.get('topology') or 'generic'
    connected_components = int(metrics.get('connected_components_count') or 0)
    isolated = len(metrics.get('isolated_components') or [])
    floating = len(metrics.get('floating_components') or [])
    cycle_count = int(metrics.get('cycle_count') or 0)
    paths = metrics.get('paths_to_ground') if isinstance(metrics.get('paths_to_ground'), dict) else {}
    path_coverage = 0.0
    if paths:
        path_coverage = sum(1 for path in paths.values() if path) / max(1, len(paths))
    return [
        min(connected_components, 10) / 10.0,
        min(isolated, 10) / 10.0,
        min(floating, 10) / 10.0,
        min(cycle_count, 5) / 5.0,
        1.0 if metrics.get('is_connected') else 0.0,
        1.0 if metrics.get('has_output_node') else 0.0,
        1.0 if topology == 'voltage_divider' else 0.0,
        1.0 if topology == 'rc_network' else 0.0,
        1.0 if topology == 'led_indicator' else 0.0,
        path_coverage,
    ]


def _require_torch():
    try:
        import torch
        from torch import nn
    except Exception as exc:
        raise NeuralUnavailable(
            'PyTorch не установлен. Установите optional AI-зависимости: '
            'pip install -r requirements-ai.txt'
        ) from exc
    return torch, nn


def _build_model():
    torch, nn = _require_torch()

    class TinyCircuitNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.trunk = nn.Sequential(
                nn.Linear(FEATURE_DIM, 32),
                nn.ReLU(),
                nn.Linear(32, 24),
                nn.ReLU(),
            )
            self.topology_head = nn.Linear(24, len(TOPOLOGY_LABELS))
            self.risk_head = nn.Linear(24, 1)
            self.next_head = nn.Linear(24, len(NEXT_COMPONENT_LABELS))

        def forward(self, x):
            h = self.trunk(x)
            return {
                'topology': self.topology_head(h),
                'risk': self.risk_head(h).squeeze(-1),
                'next': self.next_head(h),
            }

    return TinyCircuitNet()


def _softmax(values):
    max_value = max(values) if values else 0.0
    exps = [math.exp(value - max_value) for value in values]
    total = sum(exps) or 1.0
    return [value / total for value in exps]


def _risk_label(score):
    if score >= 0.65:
        return 'risk'
    if score >= 0.35:
        return 'watch'
    return 'ok'


def _risk_band(score):
    if score >= 0.65:
        return 'high'
    if score >= 0.35:
        return 'medium'
    return 'low'


def _risk_reasons(scheme_data):
    components = _components(scheme_data)
    if not components:
        return ['empty_scheme']
    counts = Counter(_component_type(item) for item in components)
    reasons = []
    if counts.get('battery', 0) and not counts.get('ground', 0):
        reasons.append('missing_ground')
    if counts.get('led', 0) and not counts.get('resistor', 0):
        reasons.append('led_without_resistor')
    if len(_connections(scheme_data)) == 0 and len(components) > 1:
        reasons.append('no_connections')
    used = set()
    for conn in _connections(scheme_data):
        source = (conn.get('from') or {}).get('compId')
        target = (conn.get('to') or {}).get('compId')
        if source is not None:
            used.add(str(source))
        if target is not None:
            used.add(str(target))
    component_ids = {str(item.get('id')) for item in components if item.get('id') is not None}
    isolated = sorted(component_ids - used)
    if isolated:
        reasons.append('isolated_components:' + ','.join(isolated[:5]))
    return reasons or ['no_obvious_rule_risk']


def teacher_baseline(scheme_data):
    risk_score = round(float(_risk_teacher(scheme_data)), 4)
    next_component = _next_component_teacher(scheme_data)
    return {
        'topology': _detect_teacher_topology(scheme_data),
        'risk_score': risk_score,
        'risk_label': _risk_label(risk_score),
        'risk_band': _risk_band(risk_score),
        'next_component': next_component,
        'risk_reasons': _risk_reasons(scheme_data),
    }


def compare_prediction_to_teacher(scheme_data, prediction):
    baseline = teacher_baseline(scheme_data)
    prediction = prediction or {}
    top_next = ''
    ranked_next = prediction.get('next_components') or []
    if ranked_next:
        top_next = ranked_next[0].get('component_type') or ''
    predicted_next_types = [item.get('component_type') for item in ranked_next if item.get('component_type')]
    predicted_risk = float(prediction.get('risk_score') or 0.0)
    topology_match = prediction.get('topology') == baseline['topology']
    next_top_match = top_next == baseline['next_component']
    next_any_match = baseline['next_component'] in predicted_next_types
    risk_band_match = _risk_band(predicted_risk) == baseline['risk_band']

    agreement_score = 0.0
    agreement_score += 0.4 if topology_match else 0.0
    agreement_score += 0.3 if next_top_match else 0.18 if next_any_match else 0.0
    agreement_score += 0.3 if risk_band_match else 0.0

    topology_confidence = float(prediction.get('topology_confidence') or 0.0)
    next_confidence = float(ranked_next[0].get('confidence') or 0.0) if ranked_next else 0.0
    calibrated_confidence = round(
        max(0.0, min(1.0, (agreement_score * 0.55) + (topology_confidence * 0.25) + (next_confidence * 0.20))),
        4,
    )
    if not prediction.get('trained'):
        policy = 'baseline_only'
    elif agreement_score >= 0.75 and calibrated_confidence >= 0.45:
        policy = 'aligned_deep_hint'
    elif agreement_score >= 0.45:
        policy = 'review_required'
    else:
        policy = 'low_agreement_do_not_use_alone'

    return {
        'expert_baseline': baseline,
        'agreement': {
            'topology': topology_match,
            'next_component_top1': next_top_match,
            'next_component_top3': next_any_match,
            'risk_band': risk_band_match,
        },
        'agreement_score': round(agreement_score, 4),
        'calibrated_confidence': calibrated_confidence,
        'confidence_policy': policy,
        'final_control': 'expert_rules_plus_human',
    }


class NeuralCircuitAdvisor:
    def __init__(self, model_path=None):
        self.model_path = Path(model_path or default_model_path())
        self.model = None
        self.trained = False
        self.meta = {}

    def _load(self):
        if self.model is not None:
            return
        torch, _ = _require_torch()
        self.model = _build_model()
        if self.model_path.exists():
            payload = torch.load(self.model_path, map_location='cpu')
            try:
                self.model.load_state_dict(payload['state_dict'])
            except RuntimeError as exc:
                self.meta = {
                    'load_warning': 'Saved model is incompatible with current feature vector; using fresh baseline.',
                    'load_error': str(exc),
                }
                self.trained = False
            else:
                self.meta = payload.get('meta') or {}
                self.trained = True
        self.model.eval()

    def predict(self, scheme_data):
        torch, _ = _require_torch()
        self._load()
        features = torch.tensor([scheme_to_features(scheme_data)], dtype=torch.float32)
        with torch.no_grad():
            outputs = self.model(features)
            topology_logits = outputs['topology'][0].tolist()
            next_logits = outputs['next'][0].tolist()
            risk_score = float(torch.sigmoid(outputs['risk'][0]).item())

        topology_probs = _softmax(topology_logits)
        next_probs = _softmax(next_logits)
        topology_index = max(range(len(topology_probs)), key=lambda idx: topology_probs[idx])
        ranked_next = sorted(
            [
                {
                    'component_type': NEXT_COMPONENT_LABELS[index],
                    'confidence': round(float(prob), 4),
                    'reason': 'PyTorch tiny model probability',
                }
                for index, prob in enumerate(next_probs)
            ],
            key=lambda item: item['confidence'],
            reverse=True,
        )[:3]
        evidence_sources = (self.meta.get('curated_source_ids') or [])[:5]
        evidence_topics = (self.meta.get('curated_source_topics') or [])[:5]
        prediction = {
            'backend': 'pytorch',
            'model_version': MODEL_VERSION,
            'trained': self.trained,
            'topology': TOPOLOGY_LABELS[topology_index],
            'topology_confidence': round(float(topology_probs[topology_index]), 4),
            'risk_score': round(risk_score, 4),
            'risk_label': _risk_label(risk_score),
            'next_components': ranked_next,
            'features': {
                'feature_dim': FEATURE_DIM,
                'base_feature_dim': BASE_FEATURE_DIM,
                'graph_feature_dim': GRAPH_FEATURE_DIM,
                'components': len(_components(scheme_data)),
                'connections': len(_connections(scheme_data)),
            },
            'evidence_sources': evidence_sources,
            'evidence_topics': evidence_topics,
            'meta': self.meta,
        }
        prediction.update(compare_prediction_to_teacher(scheme_data, prediction))
        return prediction


def generate_synthetic_dataset(size=240, seed=42):
    rng = random.Random(seed)
    schemes = []
    templates = ['empty', 'divider', 'rc', 'led', 'missing_gnd', 'led_no_resistor', 'generic']
    for index in range(size):
        kind = templates[index % len(templates)]
        jitter = rng.randint(0, 2)
        if kind == 'empty':
            scheme = {'components': [], 'connections': []}
        elif kind == 'divider':
            scheme = {
                'components': [
                    {'id': 'v1', 'type': 'battery'},
                    {'id': 'r1', 'type': 'resistor'},
                    {'id': 'r2', 'type': 'resistor'},
                    {'id': 'gnd', 'type': 'ground'},
                ],
                'connections': [
                    {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
                    {'from': {'compId': 'r1'}, 'to': {'compId': 'r2'}},
                    {'from': {'compId': 'r2'}, 'to': {'compId': 'gnd'}},
                ],
            }
        elif kind == 'rc':
            scheme = {
                'components': [
                    {'id': 'v1', 'type': 'battery'},
                    {'id': 'r1', 'type': 'resistor'},
                    {'id': 'c1', 'type': 'capacitor'},
                    {'id': 'gnd', 'type': 'ground'},
                ],
                'connections': [
                    {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
                    {'from': {'compId': 'r1'}, 'to': {'compId': 'c1'}},
                    {'from': {'compId': 'c1'}, 'to': {'compId': 'gnd'}},
                ],
            }
        elif kind == 'led':
            scheme = {
                'components': [
                    {'id': 'v1', 'type': 'battery'},
                    {'id': 'r1', 'type': 'resistor'},
                    {'id': 'led1', 'type': 'led'},
                    {'id': 'gnd', 'type': 'ground'},
                ],
                'connections': [
                    {'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}},
                    {'from': {'compId': 'r1'}, 'to': {'compId': 'led1'}},
                    {'from': {'compId': 'led1'}, 'to': {'compId': 'gnd'}},
                ],
            }
        elif kind == 'missing_gnd':
            scheme = {
                'components': [
                    {'id': 'v1', 'type': 'battery'},
                    {'id': 'r1', 'type': 'resistor'},
                    {'id': 'r2', 'type': 'resistor'},
                ],
                'connections': [{'from': {'compId': 'v1'}, 'to': {'compId': 'r1'}}],
            }
        elif kind == 'led_no_resistor':
            scheme = {
                'components': [
                    {'id': 'v1', 'type': 'battery'},
                    {'id': 'led1', 'type': 'led'},
                    {'id': 'gnd', 'type': 'ground'},
                ],
                'connections': [
                    {'from': {'compId': 'v1'}, 'to': {'compId': 'led1'}},
                    {'from': {'compId': 'led1'}, 'to': {'compId': 'gnd'}},
                ],
            }
        else:
            scheme = {
                'components': [
                    {'id': 'v1', 'type': 'battery'},
                    {'id': 'u1', 'type': 'ic'},
                    {'id': 'gnd', 'type': 'ground'},
                ],
                'connections': [{'from': {'compId': 'v1'}, 'to': {'compId': 'u1'}}],
            }
        for extra in range(jitter):
            cid = f'x{index}_{extra}'
            scheme['components'].append({'id': cid, 'type': rng.choice(['resistor', 'capacitor', 'button'])})
        schemes.append(scheme)
    return schemes


def train_tiny_model(
    size=240,
    epochs=120,
    seed=42,
    model_path=None,
    extra_schemes=None,
    *,
    validation_split=0.15,
    early_stopping_patience=25,
    lr_scheduler='cosine',  # 'cosine' | 'step' | 'none'
    initial_lr=0.015,
    weight_decay=1e-4,
    augmentation=True,
    progress_callback=None,
):
    """Train tiny PyTorch model with passive quality+speed features.

    Passive features (no UI changes):
    - validation_split: held-out set, не идёт в backprop
    - early_stopping_patience: остановка если val_loss не улучшается N epochs
    - lr_scheduler: 'cosine' (рекомендуется), 'step', 'none'
    - weight_decay: L2 регуляризация
    - augmentation: jitter компонентных значений (R±20%, C±20%) — каждую epoch
      синтетический dataset немного отличается
    - progress_callback: optional fn(epoch, train_loss, val_loss) для admin UI

    Returns: dict с финальными метриками + best_epoch + история.
    """
    torch, nn = _require_torch()
    model_path = Path(model_path or default_model_path())
    model_path.parent.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(seed)
    random.seed(seed)
    schemes = generate_synthetic_dataset(size=size, seed=seed)
    curated_source_ids = []
    curated_source_topics = []
    curated_teacher_rules = []
    if extra_schemes:
        for item in extra_schemes:
            if not isinstance(item, dict) or not item.get('components'):
                continue
            metadata = item.get('__training_metadata') if isinstance(item.get('__training_metadata'), dict) else {}
            for source_id in metadata.get('source_ids') or []:
                if source_id not in curated_source_ids:
                    curated_source_ids.append(source_id)
            for topic in metadata.get('source_topics') or []:
                if topic not in curated_source_topics:
                    curated_source_topics.append(topic)
            for rule_id in metadata.get('teacher_rules') or []:
                if rule_id not in curated_teacher_rules:
                    curated_teacher_rules.append(rule_id)
            schemes.append(item)

    # ---- Validation split -----------------------------------------------
    val_split = max(0.0, min(0.4, float(validation_split)))
    indices = list(range(len(schemes)))
    random.Random(seed).shuffle(indices)
    val_count = int(len(indices) * val_split)
    val_idx = set(indices[:val_count])
    train_schemes = [s for i, s in enumerate(schemes) if i not in val_idx]
    val_schemes = [s for i, s in enumerate(schemes) if i in val_idx]

    def _to_tensors(schemes_subset):
        if not schemes_subset:
            return None, None, None, None
        x = torch.tensor([scheme_to_features(item) for item in schemes_subset], dtype=torch.float32)
        y_topology = torch.tensor([
            TOPOLOGY_LABELS.index(_detect_teacher_topology(item))
            for item in schemes_subset
        ], dtype=torch.long)
        y_risk = torch.tensor([_risk_teacher(item) for item in schemes_subset], dtype=torch.float32)
        y_next = torch.tensor([
            NEXT_COMPONENT_LABELS.index(_next_component_teacher(item))
            for item in schemes_subset
        ], dtype=torch.long)
        return x, y_topology, y_risk, y_next

    x_train_base, yt_train, yr_train, yn_train = _to_tensors(train_schemes)
    x_val, yt_val, yr_val, yn_val = _to_tensors(val_schemes) if val_schemes else (None, None, None, None)

    # ---- Model + Optimizer + Scheduler ----------------------------------
    model = _build_model()
    optimizer = torch.optim.Adam(model.parameters(), lr=initial_lr, weight_decay=weight_decay)
    if lr_scheduler == 'cosine':
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=int(epochs))
    elif lr_scheduler == 'step':
        scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=max(10, epochs // 5), gamma=0.5)
    else:
        scheduler = None

    loss_topology = nn.CrossEntropyLoss()
    loss_next = nn.CrossEntropyLoss()
    loss_risk = nn.MSELoss()

    # ---- Augmentation: jitter R/C/V на каждой epoch ----------------------
    def _augment_features(base_x):
        if not augmentation:
            return base_x
        # ±5% noise — для tiny модели сильный jitter мешает сходиться
        noise = torch.randn_like(base_x) * 0.05
        return base_x + noise

    # ---- Train loop with early stopping ---------------------------------
    history = []
    best_val_loss = float('inf')
    best_state_dict = None
    best_epoch = 0
    patience_left = early_stopping_patience
    final_train_loss = 0.0
    final_val_loss = float('inf')

    for epoch in range(int(epochs)):
        model.train()
        optimizer.zero_grad()
        x_train = _augment_features(x_train_base)
        outputs = model(x_train)
        risk_pred = torch.sigmoid(outputs['risk'])
        train_loss = (
            loss_topology(outputs['topology'], yt_train)
            + loss_next(outputs['next'], yn_train)
            + loss_risk(risk_pred, yr_train)
        )
        train_loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
        optimizer.step()
        if scheduler is not None:
            scheduler.step()
        final_train_loss = float(train_loss.item())

        # Validation pass (без gradient)
        val_loss_value = None
        if x_val is not None and len(x_val) > 0:
            model.eval()
            with torch.no_grad():
                val_out = model(x_val)
                val_risk = torch.sigmoid(val_out['risk'])
                val_loss = (
                    loss_topology(val_out['topology'], yt_val)
                    + loss_next(val_out['next'], yn_val)
                    + loss_risk(val_risk, yr_val)
                )
                val_loss_value = float(val_loss.item())
                final_val_loss = val_loss_value

                # Early stopping + best checkpoint
                if val_loss_value < best_val_loss - 1e-5:
                    best_val_loss = val_loss_value
                    best_state_dict = {k: v.detach().clone() for k, v in model.state_dict().items()}
                    best_epoch = epoch + 1
                    patience_left = early_stopping_patience
                else:
                    patience_left -= 1

        history.append({
            'epoch': epoch + 1,
            'train_loss': round(final_train_loss, 6),
            'val_loss': round(val_loss_value, 6) if val_loss_value is not None else None,
            'lr': round(optimizer.param_groups[0]['lr'], 6),
        })

        # Progress callback (для admin UI)
        if progress_callback is not None:
            try:
                progress_callback(epoch + 1, int(epochs), final_train_loss, val_loss_value)
            except Exception:
                pass

        # Early stop
        if patience_left <= 0 and val_loss_value is not None:
            break

    # Restore best checkpoint (если был validation)
    if best_state_dict is not None:
        model.load_state_dict(best_state_dict)
        final_loss = best_val_loss
    else:
        final_loss = final_train_loss

    payload = {
        'state_dict': model.state_dict(),
        'meta': {
            'model_version': MODEL_VERSION,
            'dataset_size': len(schemes),
            'synthetic_size': size,
            'curated_size': max(0, len(schemes) - size),
            'epochs': epochs,
            'seed': seed,
            'final_loss': round(final_loss, 6),
            'best_val_loss': round(best_val_loss, 6) if best_state_dict is not None else None,
            'best_epoch': best_epoch,
            'final_train_loss': round(final_train_loss, 6),
            'validation_split': validation_split,
            'lr_scheduler': lr_scheduler,
            'augmentation': augmentation,
            'early_stopping_patience': early_stopping_patience,
            'epochs_completed': len(history),
            'component_types': COMPONENT_TYPES,
            'feature_dim': FEATURE_DIM,
            'base_feature_dim': BASE_FEATURE_DIM,
            'graph_feature_dim': GRAPH_FEATURE_DIM,
            'topology_labels': TOPOLOGY_LABELS,
            'next_component_labels': NEXT_COMPONENT_LABELS,
            'curated_source_ids': curated_source_ids[:40],
            'curated_source_topics': curated_source_topics[:20],
            'curated_teacher_rules': curated_teacher_rules[:40],
        },
    }
    torch.save(payload, model_path)
    return {
        'ok': True,
        'model_path': str(model_path),
        'dataset_size': len(schemes),
        'synthetic_size': size,
        'curated_size': max(0, len(schemes) - size),
        'epochs_requested': epochs,
        'epochs_completed': len(history),
        'early_stopped': len(history) < int(epochs),
        'best_epoch': best_epoch,
        'best_val_loss': round(best_val_loss, 6) if best_state_dict is not None else None,
        'final_loss': round(final_loss, 6),
        'final_train_loss': round(final_train_loss, 6),
        'model_version': MODEL_VERSION,
        'history': history,
    }
