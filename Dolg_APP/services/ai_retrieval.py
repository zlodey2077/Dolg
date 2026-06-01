"""Small retrieval layer for Self AI.

This is not an LLM memory. It collects compact, evidence-backed snippets from
the local DOLG database so rule_ai can answer from project facts plus relevant
knowledge, learning, catalog and artifact context.
"""

from __future__ import annotations

import re
from typing import Any


STOPWORDS = {
    'and', 'the', 'for', 'with', 'what', 'why', 'how', 'this', 'that',
    'как', 'что', 'это', 'для', 'или', 'если', 'почему', 'можно', 'нужно',
    'схема', 'схему', 'схемы', 'проект', 'проверка', 'проверить',
}


def build_retrieval_context(
    message: str,
    *,
    intent: str = '',
    project=None,
    scheme: dict[str, Any] | None = None,
    review: dict[str, Any] | None = None,
    limit: int = 6,
) -> dict[str, Any]:
    tokens = _query_tokens(message, intent=intent, scheme=scheme, review=review)
    items: list[dict[str, Any]] = []
    items.extend(_artifact_items(project, tokens))
    items.extend(_training_items(project, tokens))
    items.extend(_legal_source_items(tokens))
    items.extend(_article_items(tokens))
    items.extend(_learning_items(tokens))
    items.extend(_product_items(tokens))
    ranked = _rank_items(items, tokens)[:limit]
    return {
        'query_tokens': tokens[:14],
        'items': ranked,
        'sources': sorted({item['source'] for item in ranked}),
        'counts': _counts_by_source(ranked),
    }


def retrieval_lines(context: dict[str, Any] | None, *, limit: int = 5) -> list[str]:
    lines = []
    for item in (context or {}).get('items') or []:
        title = item.get('title') or item.get('source') or 'context'
        snippet = item.get('snippet') or ''
        url = item.get('url') or ''
        prefix = {
            'article': 'статья',
            'learning': 'практикум',
            'catalog': 'каталог',
            'artifact': 'артефакт',
            'training_example': 'пример памяти',
            'legal_source': 'источник',
        }.get(item.get('source'), item.get('source') or 'контекст')
        line = f'{prefix}: {title}'
        if snippet:
            line += f' - {snippet}'
        if url:
            line += f' ({url})'
        lines.append(line[:320])
        if len(lines) >= limit:
            break
    return lines


def _query_tokens(message: str, *, intent: str, scheme: dict[str, Any] | None, review: dict[str, Any] | None) -> list[str]:
    chunks = [message or '', intent or '']
    metrics = (review or {}).get('metrics') or {}
    if metrics.get('topology'):
        chunks.append(str(metrics.get('topology')))
    sections = (review or {}).get('sections') or {}
    connectivity = sections.get('connectivity') or {}
    if connectivity.get('topology'):
        chunks.append(str(connectivity.get('topology')))
    if isinstance(scheme, dict):
        for component in (scheme.get('components') or [])[:20]:
            if not isinstance(component, dict):
                continue
            chunks.extend(str(component.get(key) or '') for key in ('type', 'label', 'ref', 'part_number', 'value'))
    text = ' '.join(chunks).lower()
    raw = re.findall(r'[a-zа-я0-9][a-zа-я0-9_+\-.]{1,}', text, flags=re.IGNORECASE)
    tokens = []
    for token in raw:
        token = token.strip('._-+').lower()
        if len(token) < 3 or token in STOPWORDS:
            continue
        if token not in tokens:
            tokens.append(token)
    return tokens[:24]


def _rank_items(items: list[dict[str, Any]], tokens: list[str]) -> list[dict[str, Any]]:
    unique = {}
    for item in items:
        key = (item.get('source'), item.get('id') or item.get('title'))
        score = _score_text(
            ' '.join(str(item.get(key) or '') for key in ('title', 'snippet', 'keywords')),
            tokens,
        )
        item = dict(item)
        item['score'] = item.get('score', 0) + score
        if item['score'] <= 0:
            continue
        previous = unique.get(key)
        if not previous or previous.get('score', 0) < item['score']:
            unique[key] = item
    return sorted(unique.values(), key=lambda item: item.get('score', 0), reverse=True)


def _score_text(text: str, tokens: list[str]) -> int:
    haystack = str(text or '').lower()
    score = 0
    for token in tokens:
        if token in haystack:
            score += 3 if len(token) >= 5 else 2
    return score


def _snippet(text: str, tokens: list[str], *, length: int = 180) -> str:
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    if len(text) <= length:
        return text
    lowered = text.lower()
    positions = [lowered.find(token) for token in tokens if token in lowered]
    start = min([pos for pos in positions if pos >= 0], default=0)
    start = max(0, start - 40)
    return text[start:start + length].strip()


def _article_items(tokens: list[str]) -> list[dict[str, Any]]:
    try:
        from knowledge.models import Article

        qs = Article.objects.filter(is_published=True).select_related('category')[:80]
        return [
            {
                'source': 'article',
                'id': article.id,
                'title': article.title,
                'snippet': _snippet(f'{article.summary} {article.body}', tokens),
                'url': f'/knowledge/articles/{article.slug}/',
                'keywords': f'{article.category.name} {article.related_components_note}',
            }
            for article in qs
        ]
    except Exception:
        return []


def _learning_items(tokens: list[str]) -> list[dict[str, Any]]:
    try:
        from knowledge.models import LearningLesson, LearningTask

        lessons = LearningLesson.objects.filter(is_published=True, track__is_published=True).select_related('track')[:80]
        tasks = LearningTask.objects.filter(lesson__is_published=True, lesson__track__is_published=True).select_related('lesson')[:120]
        items = [
            {
                'source': 'learning',
                'id': f'lesson-{lesson.id}',
                'title': lesson.title,
                'snippet': _snippet(f'{lesson.summary} {lesson.formula} {lesson.theory}', tokens),
                'url': f'/knowledge/learning/{lesson.slug}/',
                'keywords': f'{lesson.track.title} {lesson.formula}',
            }
            for lesson in lessons
        ]
        items.extend(
            {
                'source': 'learning',
                'id': f'task-{task.id}',
                'title': task.title,
                'snippet': _snippet(task.prompt, tokens),
                'url': f'/knowledge/learning/{task.lesson.slug}/',
                'keywords': f'{task.task_type} {task.lesson.title}',
            }
            for task in tasks
        )
        return items
    except Exception:
        return []


def _product_items(tokens: list[str]) -> list[dict[str, Any]]:
    try:
        from shop.models import Product

        products = Product.objects.select_related('category')[:120]
        return [
            {
                'source': 'catalog',
                'id': product.id,
                'title': product.part_number or product.name,
                'snippet': _snippet(
                    f'{product.name}. {product.description}. {product.package_type}. {product.parameters}',
                    tokens,
                ),
                'url': f'/product/{product.slug}/',
                'keywords': f'{product.category.name} {product.manufacturer} {product.lifecycle_status}',
            }
            for product in products
        ]
    except Exception:
        return []


def _legal_source_items(tokens: list[str]) -> list[dict[str, Any]]:
    try:
        from knowledge.services.legal_sources import find_legal_sources

        query = ' '.join(tokens)
        return [
            {
                'source': 'legal_source',
                'id': item['id'],
                'source_id': item['id'],
                'title': item['title'],
                'snippet': item.get('description') or item.get('license_note') or '',
                'url': item.get('url') or '',
                'keywords': ' '.join([
                    item.get('topic') or '',
                    ' '.join(item.get('keywords') or []),
                    ' '.join(item.get('rule_ids') or []),
                    ' '.join(item.get('learning_topics') or []),
                ]),
                'score': item.get('score', 0) + 1,
            }
            for item in find_legal_sources(query, limit=3)
        ]
    except Exception:
        return []


def _artifact_items(project, tokens: list[str]) -> list[dict[str, Any]]:
    if project is None or not getattr(project, 'pk', None):
        return []
    try:
        artifacts = project.engineering_artifacts.all()[:30]
        return [
            {
                'source': 'artifact',
                'id': artifact.id,
                'title': artifact.source_name,
                'snippet': _snippet(f'{artifact.summary} {artifact.warnings} {artifact.errors} {artifact.facts}', tokens),
                'url': '',
                'keywords': f'{artifact.artifact_type} {artifact.parser} {artifact.status}',
            }
            for artifact in artifacts
        ]
    except Exception:
        return []


def _training_items(project, tokens: list[str]) -> list[dict[str, Any]]:
    try:
        from Dolg_APP.models import AITrainingExample

        qs = AITrainingExample.objects.all()
        if project is not None and getattr(project, 'pk', None):
            qs = qs.filter(project=project)
        qs = qs.order_by('-is_validated', '-created_at')[:50]
        rows = []
        for example in qs:
            features = example.features if isinstance(example.features, dict) else {}
            source_ids = ', '.join(features.get('source_ids') or [])
            teacher_rules = ', '.join(features.get('teacher_rules') or [])
            rows.append({
                'source': 'training_example',
                'id': example.id,
                'title': example.kind,
                'snippet': _snippet(f'{example.prompt} {example.target} {source_ids} {teacher_rules}', tokens),
                'url': '',
                'keywords': f'{example.kind} validated={example.is_validated} {source_ids} {teacher_rules}',
                'score': 2 if example.is_validated else 0,
            })
        return rows
    except Exception:
        return []


def _counts_by_source(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        source = item.get('source') or 'unknown'
        counts[source] = counts.get(source, 0) + 1
    return counts
