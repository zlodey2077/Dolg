"""Реестр нейромоделей DOLG — основа нейронной части (зеркало `ai_algorithms`).

Единая точка, где регистрируются ВСЕ нейромодели (TinyCircuitNet, GNN, будущие
головы) с общим интерфейсом: метаданные (задача, какой сигнал учителя использует,
путь к весам), `predict(scheme)` и `status()`. Симметрично движковому ядру серверной
части (MNA `monte_carlo` + реестр `ai_algorithms`):

  • метки для обучения все модели берут из `neural_teacher` (сильный учитель = движки);
  • инференс и доступность спрашивают через этот реестр, а не у каждой модели отдельно.

Реестр аддитивен: НЕ меняет внутренности моделей, только сводит их под общий контракт.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NeuralModel:
    """Описание одной нейромодели в реестре.

    key       — стабильный идентификатор;
    task      — тип задачи ('voltage_regression' | 'circuit_hints' | …);
    teacher   — какие сигналы `neural_teacher` модель дистиллирует;
    model_path — fn() → Path к весам (.pt);
    predict   — fn(scheme_data) → результат предсказания (или None, если нет весов/torch);
    """

    key: str
    title: str
    task: str
    teacher: tuple[str, ...]
    model_path: Callable[[], Any] | None = None
    predict: Callable[[dict], Any] | None = None
    describe: str = ''
    extra: dict[str, Any] = field(default_factory=dict)


_REGISTRY: dict[str, NeuralModel] = {}


def register(model: NeuralModel) -> NeuralModel:
    _REGISTRY[model.key] = model
    return model


def get(key: str) -> NeuralModel | None:
    return _REGISTRY.get(key)


def all_models() -> list[NeuralModel]:
    return list(_REGISTRY.values())


def predict(key: str, scheme_data: dict) -> Any:
    """Инференс через реестр. None если модель неизвестна/недоступна."""
    model = _REGISTRY.get(key)
    if model is None or model.predict is None:
        return None
    try:
        return model.predict(scheme_data)
    except Exception:
        return None


def status() -> list[dict]:
    """Доступность каждой модели: есть ли torch и обученные веса на диске."""
    from Dolg_APP.ml.neural import torch_available

    torch_ok = torch_available()
    out = []
    for model in _REGISTRY.values():
        path = None
        trained = False
        if model.model_path is not None:
            try:
                path = model.model_path()
                trained = bool(path and path.exists())
            except Exception:
                trained = False
        out.append(
            {
                'key': model.key,
                'title': model.title,
                'task': model.task,
                'teacher': list(model.teacher),
                'torch': torch_ok,
                'trained': trained,
                'model_path': str(path) if path else None,
            }
        )
    return out


# ── Регистрация существующих моделей (без изменения их внутренностей) ──────────


def _tiny_predict(scheme_data: dict):
    from Dolg_APP.ml.neural import NeuralCircuitAdvisor

    return NeuralCircuitAdvisor().predict(scheme_data)


def _tiny_path():
    from Dolg_APP.ml.neural import default_model_path

    return default_model_path()


def _gnn_predict(scheme_data: dict):
    from Dolg_APP.ml.gnn_simulator import GNNSimulator

    return GNNSimulator.load(_gnn_path()).predict(scheme_data)


def _gnn_path():
    from pathlib import Path

    from django.conf import settings

    return Path(settings.MEDIA_ROOT) / 'ml' / 'gnn_v1.pt'


def register_defaults() -> None:
    """Идемпотентно регистрирует штатные модели DOLG."""
    register(
        NeuralModel(
            key='tiny_circuit_hints',
            title='TinyCircuitNet (подсказки по схеме)',
            task='circuit_hints',
            teacher=('topology', 'expert_risk', 'next_component'),
            model_path=_tiny_path,
            predict=_tiny_predict,
            describe='MLP: топология/риск/следующий компонент. Учитель → neural_teacher (движки).',
        )
    )
    register(
        NeuralModel(
            key='gnn_voltage',
            title='GNNCircuitNet (напряжения узлов)',
            task='voltage_regression',
            teacher=('voltages',),
            model_path=_gnn_path,
            predict=_gnn_predict,
            describe='GraphConv-суррогат DC: напряжения узлов. Учитель → solve_dc (MNA).',
        )
    )


register_defaults()
