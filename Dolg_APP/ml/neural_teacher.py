"""Движковый учитель для нейромоделей — единый источник «золотых» меток.

«Сильный учитель»: метки берём из РЕАЛЬНОГО ядра движков, а не из игрушечных
эвристик (`neural._risk_teacher` и т.п.). Нейросеть дистиллирует знание движков и
учится его адаптировать (обобщать на новые топологии, давать мягкие оценки, считать
быстрее), а не зубрить срабатывание захардкоженных правил.

Сигналы учителя:
  • voltages/currents — `monte_carlo.solve_dc` (MNA; та же физика, что у GNN);
  • topology — `schematic_graph.analyze_graph_topology` (реальный граф-анализ);
  • expert findings + risk — `expert_rules` (декларативный rule-pack: severity/confidence/rule_id).

Это «основа» нейронной части, симметричная движковому ядру серверной части
(MNA `monte_carlo` + реестр `ai_algorithms`). Все нейромодели (TinyCircuitNet, GNN,
будущие головы) должны брать метки отсюда — один источник правды.

Все движки опциональны и обёрнуты: если какой-то недоступен/падает на кривой схеме —
соответствующий сигнал = None, обучение использует, что есть (graceful degradation).
"""

from __future__ import annotations

# Вес серьёзности нарушения в риск-скоре (насыщается к 1.0 при множестве/тяжести).
_SEVERITY_WEIGHT = {
    'critical': 1.0,
    'error': 0.8,
    'risk': 0.6,
    'warning': 0.35,
    'recommendation': 0.15,
    'info': 0.05,
}


def dc_labels(scheme_data, *, engine: str = 'mna') -> dict | None:
    """Напряжения узлов + токи DC. None если схема неразрешима.

    Идёт через движковую абстракцию с fallback-порядком серверной части (`server_engines`:
    Xyce → PySpice → GnuCap → ngspice-wasm → NumPy MNA).

    engine:
      • 'mna' (по умолчанию) — NumPy MNA: быстро; на линейных схемах ngspice-идентичен
        (кросс-проверено: max|Δ|=0), поэтому дефолт — он;
      • 'pyspice' — индустриальный ngspice (gold SPICE): полезен на нелинейщине
        (диоды/транзисторы, реальные device-модели). Если PySpice не установлен — тихий
        фолбэк на MNA. Узловая нумерация совпадает, метки прямо сопоставимы.
    """
    return _dc_via_engine(scheme_data, engine=engine)


def _dc_via_engine(scheme_data, *, engine: str = 'mna') -> dict | None:
    """Решатель учителя: 'pyspice' (ngspice, если доступен) → NumPy MNA fallback."""
    if engine == 'pyspice':
        try:
            from Dolg_APP.services import monte_carlo, pyspice_engine

            if pyspice_engine.available():
                voltages = pyspice_engine.solve_dc(scheme_data)
                if voltages is not None:
                    n_nodes = int(monte_carlo.scheme_to_circuit(scheme_data).get('n_nodes') or 0)
                    return {
                        'voltages': voltages,
                        'currents': {},
                        'n_nodes': n_nodes,
                        'engine': 'pyspice-ngspice',
                    }
        except Exception:
            pass  # тихий фолбэк на MNA

    try:
        from Dolg_APP.services import monte_carlo

        circuit = monte_carlo.scheme_to_circuit(scheme_data)
        result = monte_carlo.solve_dc(circuit)
    except Exception:
        return None
    return {
        'voltages': result.get('voltages') or {},
        'currents': result.get('currents') or {},
        'n_nodes': int(circuit.get('n_nodes') or 0),
        'engine': 'dolg-numpy-mna',
    }


def topology_label(scheme_data) -> str:
    """Топология из реального граф-анализа (сильнее счётчиков `_detect_teacher_topology`)."""
    try:
        from Dolg_APP.services.schematic_graph import analyze_graph_topology

        metrics = analyze_graph_topology(scheme_data).get('metrics') or {}
        return metrics.get('topology') or 'generic'
    except Exception:
        return 'generic'


_SERIOUS = {'critical', 'error', 'risk'}


def expert_findings(scheme_data) -> list:
    """Реальные findings экспертных правил (severity/rule_id/recommendation/confidence).

    Facts собираем С реальной connectivity (`build_connectivity_metrics`): иначе
    `has_ground/has_source` уходят в дефолтный False и power-правила ложно срабатывают
    даже на корректной заземлённой схеме.
    """
    try:
        from Dolg_APP.services.expert_rules import build_expert_facts, evaluate_expert_rules
        from Dolg_APP.services.project_review import build_connectivity_metrics

        connectivity = build_connectivity_metrics(scheme_data)
        facts = build_expert_facts(connectivity=connectivity, scheme_data=scheme_data)
        return evaluate_expert_rules(facts).get('findings') or []
    except Exception:
        return []


def expert_risk_from_findings(findings) -> tuple[float, list[str]] | None:
    """Риск-скор [0,1] по СЕРЬЁЗНЫМ findings (critical/error/risk).

    Гигиена (docs/layout/bom-полнота как info/recommendation/warning) в риск не идёт —
    иначе сумма насыщается до 1.0 на любой минимальной схеме. Агрегация —
    вероятностное ИЛИ (1 − ∏(1−wᵢ)): растёт мягко, остаётся в [0,1]. None — если движок
    не дал findings вовсе (нет сигнала); 0.0 — findings есть, но электрического риска нет.
    """
    if not findings:
        return None
    serious = [f for f in findings if f.get('severity') in _SERIOUS]
    if not serious:
        return 0.0, []
    prob_ok = 1.0
    for finding in serious:
        weight = _SEVERITY_WEIGHT.get(finding.get('severity'), 0.1) * float(finding.get('confidence') or 0.5)
        prob_ok *= 1.0 - max(0.0, min(1.0, weight))
    reasons = [f.get('rule_id') for f in serious if f.get('rule_id')][:8]
    return round(1.0 - prob_ok, 4), reasons


def expert_risk(scheme_data) -> tuple[float, list[str]] | None:
    """Риск из движкового ядра (сильный учитель вместо игрушечного `_risk_teacher`)."""
    return expert_risk_from_findings(expert_findings(scheme_data))


def label(scheme_data) -> dict:
    """Полная «золотая» разметка схемы из движкового ядра (что доступно).

    Returns: {topology, voltages, currents, solvable, expert_risk, expert_reasons,
    expert_findings_count}. Любой недоступный сигнал = None/[]/False.
    """
    findings = expert_findings(scheme_data)
    risk = expert_risk_from_findings(findings)
    dc = dc_labels(scheme_data)
    return {
        'topology': topology_label(scheme_data),
        'voltages': dc.get('voltages') if dc else None,
        'currents': dc.get('currents') if dc else None,
        'solvable': dc is not None,
        'expert_risk': risk[0] if risk else None,
        'expert_reasons': risk[1] if risk else [],
        'expert_findings_count': len(findings),
    }
