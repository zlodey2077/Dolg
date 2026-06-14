"""L2: декларативный реестр «готовых алгоритмов» локального AI.

Каждый алгоритм = {key, title, intents, run}. `run()` вызывает движок (ai_toolkit)
и возвращает строки с реальными числами+источником. `sections_for_intent()`
собирает применимые непустые секции для интента — единая точка расширения вместо
хардкода ветвей в rule_ai. Добавить новый «навык» = добавить запись в ALGORITHMS.

Self-hosted: все движки локальные (MNA, Monte Carlo, scikit-rf, арифметика).
"""

from __future__ import annotations

from typing import Callable, NamedTuple

from . import ai_toolkit


class Algorithm(NamedTuple):
    key: str
    title: str
    intents: frozenset[str]
    run: Callable[[dict | None, str | None], list[str]]


ALGORITHMS: list[Algorithm] = [
    Algorithm(
        'dc_voltages',
        'Расчёт DC движком (MNA)',
        frozenset({'measurement', 'overview', 'scheme_overview'}),
        lambda scheme, topology: ai_toolkit.dc_voltage_lines(scheme),
    ),
    Algorithm(
        'power',
        'Мощность на резисторах (MNA)',
        frozenset({'thermal'}),
        lambda scheme, topology: ai_toolkit.power_lines(scheme),
    ),
    Algorithm(
        'formula',
        'Расчёт по схеме (движок)',
        frozenset({'formula'}),
        lambda scheme, topology: ai_toolkit.formula_compute(scheme, topology),
    ),
    Algorithm(
        'rf_filter',
        'RF-анализ фильтра (scikit-rf)',
        frozenset({'formula', 'measurement'}),
        lambda scheme, topology: ai_toolkit.rf_filter_lines(scheme),
    ),
    Algorithm(
        'tolerance',
        'Анализ допусков (worst-case)',
        frozenset({'thermal', 'why_failed'}),
        lambda scheme, topology: ai_toolkit.tolerance_lines(scheme),
    ),
    Algorithm(
        'derating',
        'Запас по мощности (derating)',
        frozenset({'thermal', 'why_failed'}),
        lambda scheme, topology: ai_toolkit.derating_lines(scheme),
    ),
    Algorithm(
        'tiny_ai',
        'Нейроподсказка (tiny-AI)',
        frozenset({'overview', 'scheme_overview', 'recommend'}),
        lambda scheme, topology: ai_toolkit.neural_hint_lines(scheme),
    ),
]


def sections_for_intent(
    intent: str, scheme_data: dict | None, topology: str | None = None
) -> list[tuple[str, list[str]]]:
    """[(title, lines)] для применимых к интенту алгоритмов, у которых есть результат."""
    sections: list[tuple[str, list[str]]] = []
    for algo in ALGORITHMS:
        if intent not in algo.intents:
            continue
        try:
            lines = algo.run(scheme_data, topology)
        except Exception:
            lines = []
        if lines:
            sections.append((algo.title, lines))
    return sections


def available_algorithms(intent: str | None = None) -> list[dict]:
    """Манифест алгоритмов (для UI/диагностики/skills-каталога)."""
    return [
        {'key': a.key, 'title': a.title, 'intents': sorted(a.intents)}
        for a in ALGORITHMS
        if intent is None or intent in a.intents
    ]
