"""Local AI bridge for server-side engines.

This module turns natural-language requests into safe EngineJob payloads and
adds neural/rule hints to engine recommendations and results. It never returns
raw shell commands: the output is a constrained JSON action contract that the
web API can queue or display.
"""

from __future__ import annotations

import re
from typing import Any

from .server_engines import get_server_engine, recommend_server_engines

LOCAL_ENGINE_ALIASES = {
    'router': 'dolg-engine-router',
    'engine router': 'dolg-engine-router',
    'dolg': 'dolg-engine-router',
    'numpy': 'dolg-numpy-mna',
    'mna': 'dolg-numpy-mna',
    'local': 'dolg-numpy-mna',
    'pyspice': 'pyspice',
    'ngspice': 'pyspice',
    'xyce': 'xyce',
    'gnucap': 'gnucap',
    'scikit-rf': 'dolg-scikit-rf',
    'skrf': 'dolg-scikit-rf',
    'rf': 'dolg-scikit-rf',
    'openmodelica': 'openmodelica',
    'sigrok': 'sigrok',
}

ANALYSIS_ALIASES = {
    'dc': 'dc',
    'op': 'dc',
    'operating point': 'dc',
    'рабоч': 'dc',
    'постоян': 'dc',
    'tran': 'transient',
    'transient': 'transient',
    'time': 'transient',
    'переход': 'transient',
    'импульс': 'transient',
    'ac': 'ac',
    'sweep': 'ac',
    'частот': 'ac',
    'ачх': 'ac',
    'rf': 'ac',
    'monte': 'tolerance',
    'tolerance': 'tolerance',
    'worst': 'tolerance',
    'допуск': 'tolerance',
    'разброс': 'tolerance',
}


def build_local_ai_engine_context(scheme_data: dict[str, Any] | None) -> dict[str, Any]:
    """Collect local rule/PyTorch context for engine routing."""
    scheme_data = scheme_data if isinstance(scheme_data, dict) else {}
    neural = {'available': False, 'reason': 'not_checked'}
    try:
        from Dolg_APP.services.rule_ai import _deep_hint_for_scheme

        neural = _deep_hint_for_scheme(scheme_data)
    except Exception as exc:
        neural = {'available': False, 'reason': str(exc)[:180]}

    components = scheme_data.get('components') if isinstance(scheme_data, dict) else []
    connections = scheme_data.get('connections') if isinstance(scheme_data, dict) else []
    component_types = [
        str(item.get('type') or '').strip().lower() for item in components or [] if isinstance(item, dict)
    ]
    return {
        'backend': 'local',
        'layers': ['rule_ai', 'pytorch_deep_hint', 'ollama_text'],
        'component_count': len(components or []),
        'connection_count': len(connections or []),
        'component_types': component_types,
        'neural_hint': neural,
    }


def plan_engine_action(
    text: str,
    *,
    scheme_data: dict[str, Any] | None = None,
    preferred_engine: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Translate user text into a safe engine action contract."""
    text = str(text or '').strip()
    scheme_data = scheme_data if isinstance(scheme_data, dict) else {}
    ai_context = build_local_ai_engine_context(scheme_data)
    recommendations = recommend_server_engines(scheme_data, limit=max(1, min(int(limit or 5), 10)))
    engine_id, engine_reason = _select_engine(text, recommendations, preferred_engine=preferred_engine)
    analysis_type, analysis_reason = _select_analysis(text, ai_context)
    options = _extract_options(text, analysis_type)
    intent = _detect_intent(text)

    command = {
        'type': 'engine_job',
        'engine_id': engine_id,
        'analysis_type': analysis_type,
        'options': options,
        'source': 'local_ai_command_planner',
    }
    if engine_id == 'dolg-engine-router':
        delegated = _delegated_engine_for_router(text, recommendations)
        command['options']['target_engine'] = delegated

    engine = get_server_engine(engine_id) or {}
    return {
        'ok': True,
        'intent': intent,
        'command': command,
        'job_payload': {
            'engine_id': engine_id,
            'analysis_type': analysis_type,
            'scheme_data': scheme_data,
            'options': command['options'],
            'source': 'local_ai_command_planner',
        },
        'engine': {
            'id': engine_id,
            'name': engine.get('name') or engine_id,
            'status': engine.get('status') or '',
        },
        'recommendations': recommendations,
        'ai_context': ai_context,
        'explanation': _explain_plan(
            intent=intent,
            engine_id=engine_id,
            analysis_type=analysis_type,
            engine_reason=engine_reason,
            analysis_reason=analysis_reason,
            ai_context=ai_context,
        ),
        'warnings': _plan_warnings(engine_id, analysis_type, ai_context),
        'confidence': _plan_confidence(engine_id, analysis_type, ai_context),
    }


def attach_engine_ai_result(
    result: dict[str, Any],
    *,
    scheme_data: dict[str, Any] | None = None,
    engine_id: str = '',
    analysis_type: str = '',
) -> dict[str, Any]:
    """Attach local AI interpretation to a normalized engine result."""
    result = result if isinstance(result, dict) else {}
    context = build_local_ai_engine_context(scheme_data or {})
    summary = {
        'backend': 'local_ai',
        'engine_id': engine_id or result.get('engine') or '',
        'analysis_type': analysis_type or result.get('analysis_type') or '',
        'neural_hint': context.get('neural_hint') or {},
        'notes': _result_notes(result, context),
    }
    result['local_ai'] = summary
    metrics = result.setdefault('metrics', {})
    if isinstance(metrics, dict):
        metrics['local_ai_attached'] = True
    return result


def _detect_intent(text: str) -> str:
    low = text.lower()
    if any(token in low for token in ('запусти', 'прогони', 'run', 'simulate', 'посчитай')):
        return 'queue_engine_job'
    if any(token in low for token in ('выбери', 'подбери', 'recommend', 'какой движок')):
        return 'recommend_engine'
    if any(token in low for token in ('объясни', 'поясни', 'почему', 'explain')):
        return 'explain_engine_result'
    return 'plan_engine_job'


def _select_engine(
    text: str, recommendations: list[dict[str, Any]], *, preferred_engine: str | None
) -> tuple[str, str]:
    low = text.lower()
    if preferred_engine and get_server_engine(preferred_engine):
        return preferred_engine, 'user_preference'
    for alias, engine_id in LOCAL_ENGINE_ALIASES.items():
        if alias in low and get_server_engine(engine_id):
            return engine_id, f'text_alias:{alias}'
    if recommendations:
        return str(recommendations[0]['id']), 'ranked_recommendation'
    return 'dolg-engine-router', 'default_router'


def _select_analysis(text: str, ai_context: dict[str, Any]) -> tuple[str, str]:
    low = text.lower()
    for alias, analysis in ANALYSIS_ALIASES.items():
        if alias in low:
            return analysis, f'text_alias:{alias}'
    neural = ai_context.get('neural_hint') or {}
    topology = str(neural.get('topology') or '').lower()
    if topology == 'rc_network':
        return 'transient', 'neural_topology:rc_network'
    if topology in {'voltage_divider', 'led_indicator'}:
        return 'dc', f'neural_topology:{topology}'
    return 'dc', 'safe_default'


def _extract_options(text: str, analysis_type: str) -> dict[str, Any]:
    low = text.lower()
    options: dict[str, Any] = {}
    if analysis_type == 'transient':
        options.update({'t_stop': 1e-3, 'dt': 1e-5})
    elif analysis_type == 'ac':
        options.update({'f_start': 10, 'f_stop': 100000, 'points': 40})
    elif analysis_type == 'tolerance':
        options.update({'iterations': 1000, 'tolerance': 0.05})

    seconds = _first_number(low, r'(\d+(?:[.,]\d+)?)\s*(?:ms|мс)')
    if seconds is not None:
        options['t_stop'] = seconds / 1000.0
    points = _first_number(low, r'(\d+)\s*(?:points|точ)')
    if points is not None and analysis_type == 'ac':
        options['points'] = max(5, min(int(points), 400))
    return options


def _first_number(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1).replace(',', '.'))
    except ValueError:
        return None


def _delegated_engine_for_router(text: str, recommendations: list[dict[str, Any]]) -> str:
    low = text.lower()
    if 'pyspice' in low or 'ngspice' in low:
        return 'pyspice'
    if 'xyce' in low:
        return 'xyce'
    for engine in recommendations:
        engine_id = str(engine.get('id') or '')
        if engine_id in {'pyspice', 'xyce', 'dolg-numpy-mna'}:
            return engine_id
    return 'dolg-numpy-mna'


def _explain_plan(
    *,
    intent: str,
    engine_id: str,
    analysis_type: str,
    engine_reason: str,
    analysis_reason: str,
    ai_context: dict[str, Any],
) -> str:
    neural = ai_context.get('neural_hint') or {}
    topology = neural.get('topology') or 'unknown'
    risk = neural.get('risk_label') or 'unknown'
    return (
        f'Local AI planned {intent}: engine={engine_id}, analysis={analysis_type}. '
        f'Engine reason={engine_reason}; analysis reason={analysis_reason}. '
        f'PyTorch hint: topology={topology}, risk={risk}.'
    )


def _plan_warnings(engine_id: str, analysis_type: str, ai_context: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    neural = ai_context.get('neural_hint') or {}
    if not neural.get('available'):
        warnings.append(f'PyTorch hint unavailable: {neural.get("reason") or "unknown"}')
    if engine_id not in {'dolg-engine-router', 'dolg-numpy-mna', 'pyspice', 'dolg-scikit-rf'}:
        warnings.append('Selected engine may require an external Docker/CLI worker.')
    if analysis_type == 'ac' and engine_id == 'dolg-numpy-mna':
        warnings.append('AC route is local but limited; Xyce/PySpice is better for complex SPICE.')
    return warnings


def _plan_confidence(engine_id: str, analysis_type: str, ai_context: dict[str, Any]) -> float:
    confidence = 0.55
    if engine_id in {'dolg-engine-router', 'dolg-numpy-mna', 'pyspice', 'dolg-scikit-rf'}:
        confidence += 0.15
    if analysis_type in {'dc', 'transient', 'ac', 'tolerance'}:
        confidence += 0.10
    neural = ai_context.get('neural_hint') or {}
    if neural.get('available'):
        confidence += min(0.20, float(neural.get('calibrated_confidence') or 0.0) * 0.20)
    return round(min(confidence, 0.95), 3)


def _result_notes(result: dict[str, Any], context: dict[str, Any]) -> list[str]:
    notes = []
    analysis = result.get('analysis_type') or 'unknown'
    node_count = len(result.get('nodes') or result.get('node_voltages') or [])
    notes.append(f'{analysis} result contains {node_count} node values/rows.')
    neural = context.get('neural_hint') or {}
    if neural.get('available'):
        notes.append(
            f'PyTorch topology={neural.get("topology")} risk={neural.get("risk_label")} '
            f'policy={neural.get("confidence_policy")}.'
        )
    else:
        notes.append('PyTorch deep hint is unavailable; rule/numeric result remains authoritative.')
    return notes
