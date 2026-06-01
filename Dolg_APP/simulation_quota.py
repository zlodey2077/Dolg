"""Квоты на запуск ngspice-симуляции.

Пока ngspice.wasm ещё не интегрирован, этот модуль — подготовка структуры.
Когда симулятор будет подключён, лимиты применяются на стороне сервера
(например, в API-эндпоинте, принимающем метаданные запуска расчёта).

Логика:
- Админ / staff         → безлимит (None);
- Авторизованный юзер    → 100 запусков / сутки;
- Аноним                 → 10 / сутки (клиентская мягкая квота).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationQuota:
    daily_runs: int | None   # None = безлимит
    max_nodes:  int | None   # None = безлимит
    max_tran_points: int | None  # Ограничение числа временных точек


QUOTA_ADMIN = SimulationQuota(daily_runs=None, max_nodes=None, max_tran_points=None)
QUOTA_USER  = SimulationQuota(daily_runs=100,  max_nodes=100,  max_tran_points=50_000)
QUOTA_GUEST = SimulationQuota(daily_runs=10,   max_nodes=30,   max_tran_points=5_000)


def get_quota(user) -> SimulationQuota:
    """Возвращает квоту для пользователя."""
    if user is None or not user.is_authenticated:
        return QUOTA_GUEST
    if user.is_staff or user.is_superuser:
        return QUOTA_ADMIN
    return QUOTA_USER


def quota_dict(user) -> dict:
    """Удобно отдавать во фронтенд / API — JSON-сериализуемо."""
    q = get_quota(user)
    return {
        'daily_runs':       q.daily_runs,
        'max_nodes':        q.max_nodes,
        'max_tran_points':  q.max_tran_points,
        'unlimited':        q.daily_runs is None,
    }
