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


# ── Plan-then-Execute: планировщик мульти-движкового ответа ──────────────────
# Для обзорных/диагностических запросов агент прогоняет НЕСКОЛЬКО движков сразу
# (а не один по intent) и собирает проверяемый ответ. Исполнитель — тот же реестр
# (детерминированные не-LLM движки). Узкие запросы остаются одно-движковыми.
_ANALYTICAL_INTENTS = frozenset({'overview', 'scheme_overview', 'why_failed', 'measurement', 'thermal'})
_COMPREHENSIVE_KW = (
    'провер',
    'все ',
    'всё',
    'безопас',
    'анализ',
    'health',
    'норм',
    'что не так',
    'оцени',
    'диагност',
    'всё ли',
    'ок?',
    'годен',
    'работает ли',
)
_FULL_PLAN = ('measurement', 'thermal', 'formula')


def plan_for(message: str | None, intent: str) -> list[str]:
    """Plan-then-Execute: список intent'ов-движков под запрос (порядок = логика проверки).

    Для обзорных/диагностических запросов — расширенный план (несколько движков),
    иначе — один primary intent (обратная совместимость).
    """
    msg = (message or '').lower()
    broad = intent in _ANALYTICAL_INTENTS or any(kw in msg for kw in _COMPREHENSIVE_KW)
    if not broad:
        return [intent]
    ordered = ([intent] if intent in _FULL_PLAN else []) + [i for i in _FULL_PLAN if i != intent]
    return ordered


def sections_for_plan(
    intents: list[str], scheme_data: dict | None, topology: str | None = None
) -> list[tuple[str, list[str]]]:
    """Объединение секций по нескольким intent'ам (дедуп по заголовку, порядок сохранён)."""
    seen: set[str] = set()
    out: list[tuple[str, list[str]]] = []
    for it in intents:
        for title, lines in sections_for_intent(it, scheme_data, topology):
            if title in seen:
                continue
            seen.add(title)
            out.append((title, lines))
    return out


def available_algorithms(intent: str | None = None) -> list[dict]:
    """Манифест алгоритмов (для UI/диагностики/skills-каталога)."""
    return [
        {'key': a.key, 'title': a.title, 'intents': sorted(a.intents)}
        for a in ALGORITHMS
        if intent is None or intent in a.intents
    ]
