"""Compact 3D visualization payloads for Engineering Review pages.

The browser renderer stays deliberately dumb: it only receives numeric bars,
risk markers and human-readable labels.  All extraction from the review
snapshot happens here so the same payload can later be reused by PDF/export or
AI trace summaries without coupling them to the HTML template.
"""

from __future__ import annotations

from typing import Any

SEVERITY_COLORS = {
    'ok': '#72ffad',
    'info': '#7fdbff',
    'warning': '#ffd34d',
    'risk': '#ff8a3d',
    'critical': '#ff4f6d',
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return default
    text = str(value).strip().replace(',', '.')
    number = []
    started = False
    for char in text:
        if char.isdigit() or char in '.-+':
            number.append(char)
            started = True
        elif started:
            break
    try:
        return float(''.join(number)) if number else default
    except (TypeError, ValueError):
        return default


def _count(value: Any) -> int:
    if isinstance(value, dict):
        return len(value)
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return int(max(0, round(_safe_float(value))))


def _severity_for_risk(count: int, critical: bool = False) -> str:
    if count <= 0:
        return 'ok'
    if critical or count >= 4:
        return 'critical'
    if count >= 2:
        return 'risk'
    return 'warning'


def _bar(
    key: str,
    label: str,
    value: Any,
    *,
    category: str = 'metric',
    severity: str = 'info',
    scale: float = 1.0,
    max_height: float = 7.0,
    value_label: str | None = None,
) -> dict[str, Any]:
    numeric = max(0.0, _safe_float(value))
    height = min(max_height, 0.45 + numeric * scale)
    return {
        'key': key,
        'label': label,
        'value': numeric,
        'value_label': value_label if value_label is not None else f'{numeric:g}',
        'category': category,
        'severity': severity,
        'color': SEVERITY_COLORS.get(severity, SEVERITY_COLORS['info']),
        'height': round(height, 3),
    }


def _score_bar(score: Any) -> dict[str, Any]:
    numeric = max(0.0, min(100.0, _safe_float(score)))
    if numeric >= 85:
        severity = 'ok'
    elif numeric >= 65:
        severity = 'warning'
    elif numeric >= 40:
        severity = 'risk'
    else:
        severity = 'critical'
    return _bar(
        'health_score',
        'Design Health',
        numeric,
        category='score',
        severity=severity,
        scale=0.065,
        value_label=f'{numeric:g}/100',
    )


def build_review_3d_payload(review_payload: dict[str, Any] | None) -> dict[str, Any]:
    """Return a small, serializable 3D chart payload for a review snapshot."""

    if not isinstance(review_payload, dict):
        return {'enabled': False, 'columns': [], 'risk_points': [], 'legend': []}

    metrics = review_payload.get('metrics') or {}
    sections = review_payload.get('sections') or {}
    connectivity = sections.get('connectivity') if isinstance(sections, dict) else {}
    bom = sections.get('bom') if isinstance(sections, dict) else {}
    derating = sections.get('derating') if isinstance(sections, dict) else {}
    validity = sections.get('validity') if isinstance(sections, dict) else {}
    manufacturing = sections.get('manufacturing') if isinstance(sections, dict) else {}
    external_cad = sections.get('external_cad') if isinstance(sections, dict) else {}
    measurements = sections.get('measurements') if isinstance(sections, dict) else []

    error_count = _count(review_payload.get('errors'))
    warning_count = _count(review_payload.get('warnings'))
    expert_count = _count(review_payload.get('expert_findings'))
    derating_count = _count((derating or {}).get('issues') if isinstance(derating, dict) else [])
    validity_count = _count((validity or {}).get('issues') if isinstance(validity, dict) else [])
    bom_risk_count = _count((bom or {}).get('risks') if isinstance(bom, dict) else [])
    missing_readiness_count = _count(
        (manufacturing or {}).get('missing') if isinstance(manufacturing, dict) else []
    )
    external_count = _count((external_cad or {}).get('findings') if isinstance(external_cad, dict) else [])

    component_count = metrics.get('components', (connectivity or {}).get('component_count', 0))
    connection_count = metrics.get('connections', (connectivity or {}).get('connection_count', 0))
    simulation_count = metrics.get('simulations', 0)
    measurement_count = metrics.get('measurements', _count(measurements))
    cycle_count = metrics.get('cycle_count', (connectivity or {}).get('cycle_count', 0))
    floating_count = _count(
        (connectivity or {}).get('floating_components') if isinstance(connectivity, dict) else []
    )
    if not floating_count:
        floating_count = _count(
            (connectivity or {}).get('unconnected') if isinstance(connectivity, dict) else []
        )

    columns = [
        _score_bar(review_payload.get('score', 0)),
        _bar('components', 'Компоненты', component_count, scale=0.33, severity='info'),
        _bar('connections', 'Соединения', connection_count, scale=0.33, severity='info'),
        _bar(
            'measurements',
            'Измерения',
            measurement_count,
            scale=0.55,
            severity='ok' if _count(measurement_count) else 'warning',
        ),
        _bar(
            'simulations',
            'Симуляции',
            simulation_count,
            scale=0.55,
            severity='ok' if _count(simulation_count) else 'warning',
        ),
        _bar('cycles', 'Контуры', cycle_count, scale=0.65, severity='info'),
        _bar(
            'errors',
            'Ошибки',
            error_count,
            scale=1.2,
            severity=_severity_for_risk(error_count, critical=True),
            category='risk',
        ),
        _bar(
            'warnings',
            'Предупреждения',
            warning_count,
            scale=0.85,
            severity=_severity_for_risk(warning_count),
            category='risk',
        ),
        _bar(
            'expert',
            'Expert findings',
            expert_count,
            scale=0.8,
            severity=_severity_for_risk(expert_count),
            category='risk',
        ),
        _bar(
            'bom_risk',
            'BOM-риск',
            bom_risk_count,
            scale=1.0,
            severity=_severity_for_risk(bom_risk_count),
            category='risk',
        ),
        _bar(
            'derating',
            'Запас/нагрев',
            derating_count,
            scale=1.0,
            severity=_severity_for_risk(derating_count),
            category='risk',
        ),
        _bar(
            'validity',
            'Limits',
            validity_count,
            scale=1.0,
            severity=_severity_for_risk(validity_count),
            category='risk',
        ),
        _bar(
            'readiness',
            'Сборка',
            missing_readiness_count,
            scale=0.75,
            severity=_severity_for_risk(missing_readiness_count),
            category='risk',
        ),
        _bar(
            'external_cad',
            'CAD/ERC',
            external_count,
            scale=0.9,
            severity=_severity_for_risk(external_count),
            category='risk',
        ),
        _bar(
            'floating',
            'Floating',
            floating_count,
            scale=1.0,
            severity=_severity_for_risk(floating_count),
            category='risk',
        ),
    ]

    visible_columns = [
        item
        for item in columns
        if item['key'] in {'health_score', 'components', 'connections'} or item['value'] > 0
    ][:14]

    risk_points = [
        {
            'key': item['key'],
            'label': item['label'],
            'value': item['value'],
            'severity': item['severity'],
            'color': item['color'],
            'radius': round(0.28 + min(1.2, item['value'] * 0.12), 3),
        }
        for item in visible_columns
        if item['category'] == 'risk' and item['value'] > 0
    ]

    legend = [
        {'label': 'Норма', 'color': SEVERITY_COLORS['ok']},
        {'label': 'Информация', 'color': SEVERITY_COLORS['info']},
        {'label': 'Предупреждение', 'color': SEVERITY_COLORS['warning']},
        {'label': 'Риск', 'color': SEVERITY_COLORS['risk']},
        {'label': 'Критично', 'color': SEVERITY_COLORS['critical']},
    ]

    return {
        'enabled': bool(visible_columns),
        'title': '3D-карта инженерного анализа',
        'summary': {
            'score': _safe_float(review_payload.get('score', 0)),
            'status': review_payload.get('status'),
            'status_label': review_payload.get('status_label'),
            'topology': metrics.get('topology') or (connectivity or {}).get('topology') or 'generic',
            'risk_total': error_count
            + warning_count
            + expert_count
            + derating_count
            + validity_count
            + bom_risk_count
            + external_count,
        },
        'columns': visible_columns,
        'risk_points': risk_points,
        'legend': legend,
    }
