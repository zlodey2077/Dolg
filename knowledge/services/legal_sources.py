import json
import re
from pathlib import Path
from typing import Any

from django.conf import settings


LEGAL_SOURCES_PATH = Path(settings.BASE_DIR) / 'knowledge' / 'data' / 'legal_sources.json'
REQUIRED_TOPICS = {
    'electronics',
    'physics',
    'cad_spice',
    'cad_pcb',
    'backend',
    'graph_formula',
    'units',
    'import_parsing',
    'constraints',
    'risk',
    'ai',
}

SOURCE_ID_ALIASES = {
    'all_about_circuits': 'all_about_circuits_textbook',
    'openstax': 'openstax_university_physics_2',
    'ngspice': 'ngspice_docs',
    'ltspice': 'ltspice_analog_devices',
    'kicad': 'kicad_docs',
    'networkx': 'networkx_algorithms',
    'sympy': 'sympy_docs',
    'pint': 'pint_docs',
    'lark': 'lark_docs',
    'z3': 'z3_guide',
    'fuzzy': 'scikit_fuzzy_docs',
    'pytorch': 'pytorch_tutorials',
    'd2l': 'dive_into_deep_learning',
}

RULE_SOURCE_DEFAULTS = {
    'erc.missing_ground': ['all_about_circuits_textbook', 'ngspice_docs', 'kicad_docs'],
    'erc.missing_source': ['ngspice_docs', 'kicad_docs'],
    'topology.floating_fragments': ['networkx_algorithms', 'kicad_docs'],
    'topology.divider_without_output': ['all_about_circuits_textbook', 'openstax_university_physics_2'],
    'bom.missing_catalog_binding': ['kicad_docs'],
    'derating.power_or_thermal_risk': ['all_about_circuits_textbook', 'pint_docs'],
    'simulation.no_saved_measurements': ['ngspice_docs', 'ltspice_analog_devices'],
    'import.unsupported_items': ['ngspice_docs', 'kicad_docs', 'lark_docs'],
    'erc.led_reverse_polarity': ['all_about_circuits_textbook'],
    'erc.parallel_voltage_sources': ['ngspice_docs', 'kicad_docs'],
    'erc.source_short_to_ground': ['all_about_circuits_textbook', 'ngspice_docs'],
    'erc.dangling_named_net': ['kicad_docs'],
    'topology.transistor_pinout_swap': ['all_about_circuits_textbook', 'openstax_university_physics_2'],
}

LEARNING_TOPIC_DEFAULTS = {
    'ohm': ['all_about_circuits_textbook', 'openstax_university_physics_2', 'sympy_docs'],
    'divider': ['all_about_circuits_textbook', 'openstax_university_physics_2', 'z3_guide'],
    'rc': ['all_about_circuits_textbook', 'openstax_university_physics_2', 'ngspice_docs', 'ltspice_analog_devices'],
    'gnd': ['all_about_circuits_textbook', 'ngspice_docs', 'kicad_docs'],
    'spice': ['ngspice_docs', 'ltspice_analog_devices', 'lark_docs'],
    'drc': ['kicad_docs', 'networkx_algorithms'],
    'units': ['pint_docs'],
    'constraints': ['z3_guide'],
    'ai': ['pytorch_tutorials', 'dive_into_deep_learning'],
}


def load_legal_sources(path: Path | None = None) -> list[dict[str, Any]]:
    source_path = path or LEGAL_SOURCES_PATH
    with source_path.open('r', encoding='utf-8') as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError('legal_sources.json must contain a list')
    return [normalize_source(item) for item in data]


def normalize_source(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError('legal source item must be an object')
    source_id = str(item.get('id', '')).strip()
    title = str(item.get('title', '')).strip()
    url = str(item.get('url', '')).strip()
    topic = str(item.get('topic', '')).strip()
    if not source_id or not title or not url or not topic:
        raise ValueError(f'legal source has required field missing: {item!r}')
    if not url.startswith('https://'):
        raise ValueError(f'legal source must use https URL: {source_id}')
    related_slugs = item.get('related_article_slugs') or []
    if not isinstance(related_slugs, list):
        raise ValueError(f'related_article_slugs must be a list: {source_id}')
    return {
        'id': source_id,
        'title': title[:160],
        'url': url[:300],
        'topic': topic,
        'description': str(item.get('description', '')).strip()[:300],
        'license_note': str(item.get('license_note', '')).strip()[:300],
        'usable_for_learning': bool(item.get('usable_for_learning', False)),
        'usable_for_ai': bool(item.get('usable_for_ai', False)),
        'related_article_slugs': [str(slug).strip() for slug in related_slugs if str(slug).strip()],
        'keywords': _list_field(item.get('keywords')),
        'rule_ids': _list_field(item.get('rule_ids')),
        'learning_topics': _list_field(item.get('learning_topics')),
        'order': int(item.get('order') or 100),
    }


def summarize_legal_sources(sources: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    items = sources if sources is not None else load_legal_sources()
    topics = sorted({item['topic'] for item in items})
    missing_topics = sorted(REQUIRED_TOPICS.difference(topics))
    return {
        'count': len(items),
        'topics': topics,
        'missing_topics': missing_topics,
        'learning_sources': sum(1 for item in items if item.get('usable_for_learning')),
        'ai_sources': sum(1 for item in items if item.get('usable_for_ai')),
        'related_links': sum(len(item.get('related_article_slugs') or []) for item in items),
        'sources_with_keywords': sum(1 for item in items if item.get('keywords')),
        'sources_with_rules': sum(1 for item in items if item.get('rule_ids')),
        'sources_with_learning_topics': sum(1 for item in items if item.get('learning_topics')),
    }


def find_legal_sources(query: str, topics: list[str] | tuple[str, ...] | set[str] | None = None, limit: int = 5) -> list[dict[str, Any]]:
    sources = load_legal_sources()
    allowed_topics = {str(topic).strip() for topic in (topics or []) if str(topic).strip()}
    tokens = _tokens(query)
    scored = []
    for item in sources:
        if allowed_topics and item['topic'] not in allowed_topics:
            continue
        text = _source_search_text(item)
        score = 0
        for token in tokens:
            if token in text:
                score += 4 if len(token) >= 5 else 2
        if not tokens:
            score = 1
        if score > 0:
            row = dict(item)
            row['score'] = score
            scored.append(row)
    scored.sort(key=lambda row: (row.get('score', 0), -row.get('order', 100)), reverse=True)
    return scored[: max(1, int(limit or 5))]


def sources_by_ids(source_ids: list[str] | tuple[str, ...] | set[str], *, limit: int | None = None) -> list[dict[str, Any]]:
    wanted = [_canonical_source_id(source_id) for source_id in source_ids if str(source_id).strip()]
    if not wanted:
        return []
    by_id = {item['id']: item for item in load_legal_sources()}
    result = [by_id[source_id] for source_id in wanted if source_id in by_id]
    return result[:limit] if limit else result


def source_ids_for_rule(rule_id: str) -> list[str]:
    rule_id = str(rule_id or '').strip()
    if not rule_id:
        return []
    result = []
    for item in load_legal_sources():
        if rule_id in (item.get('rule_ids') or []):
            result.append(item['id'])
    result.extend(RULE_SOURCE_DEFAULTS.get(rule_id, []))
    return list(dict.fromkeys(_canonical_source_id(source_id) for source_id in result))


def sources_for_rule(rule_id: str, *, limit: int = 3) -> list[dict[str, Any]]:
    return sources_by_ids(source_ids_for_rule(rule_id), limit=limit)


def source_ids_for_learning_topic(topic_or_slug: str) -> list[str]:
    text = str(topic_or_slug or '').strip().lower()
    if not text:
        return []
    matched_topics = []
    for topic in LEARNING_TOPIC_DEFAULTS:
        if topic in text:
            matched_topics.append(topic)
    result = []
    for item in load_legal_sources():
        if text in (item.get('learning_topics') or []):
            result.append(item['id'])
        elif any(topic in (item.get('learning_topics') or []) for topic in matched_topics):
            result.append(item['id'])
    for topic in matched_topics:
        result.extend(LEARNING_TOPIC_DEFAULTS.get(topic, []))
    return list(dict.fromkeys(_canonical_source_id(source_id) for source_id in result))


def sources_for_learning_topic(topic_or_slug: str, *, limit: int = 5) -> list[dict[str, Any]]:
    source_ids = source_ids_for_learning_topic(topic_or_slug)
    if source_ids:
        return sources_by_ids(source_ids, limit=limit)
    return find_legal_sources(topic_or_slug, limit=limit)


def format_source_context(sources: list[dict[str, Any]] | None) -> list[str]:
    lines = []
    for item in sources or []:
        source_id = item.get('id') or 'source'
        title = item.get('title') or source_id
        url = item.get('url') or ''
        topic = item.get('topic') or ''
        lines.append(f'legal_source:{source_id} — {title} ({topic}) {url}'.strip())
    return lines


def validate_source_ids(source_ids: list[str] | tuple[str, ...] | set[str]) -> list[str]:
    known = {item['id'] for item in load_legal_sources()}
    return [
        source_id
        for source_id in (_canonical_source_id(item) for item in source_ids)
        if source_id and source_id not in known
    ]


def all_source_ids() -> set[str]:
    return {item['id'] for item in load_legal_sources()}


def _list_field(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, (list, tuple, set)):
        raw = value
    else:
        return []
    return [str(item).strip().lower() for item in raw if str(item).strip()]


def _canonical_source_id(source_id: str) -> str:
    raw = str(source_id or '').strip().lower()
    return SOURCE_ID_ALIASES.get(raw, raw)


def _tokens(text: str) -> list[str]:
    raw = re.findall(r'[a-zа-я0-9][a-zа-я0-9_+\-.]{1,}', str(text or '').lower(), flags=re.IGNORECASE)
    result = []
    for token in raw:
        token = token.strip('._-+').lower()
        if len(token) < 2:
            continue
        if token not in result:
            result.append(token)
    return result


def _source_search_text(item: dict[str, Any]) -> str:
    chunks = [
        item.get('id'),
        item.get('title'),
        item.get('url'),
        item.get('topic'),
        item.get('description'),
        item.get('license_note'),
        ' '.join(item.get('keywords') or []),
        ' '.join(item.get('rule_ids') or []),
        ' '.join(item.get('learning_topics') or []),
        ' '.join(item.get('related_article_slugs') or []),
    ]
    return ' '.join(str(chunk or '').lower() for chunk in chunks)
