"""Экспорт текстового корпуса ассистента в JSON — вход для построения эмбеддингов.

Собирает glossary + опубликованные статьи + уроки/задания в плоский список
{id, source, title, text, url}. Этот JSON затем эмбеддит Node-скрипт
scripts/build_embeddings.mjs (Transformers.js) → corpus_embeddings.json для
клиентского семантического grounding'а (docs/TRANSFORMERS_JS_SEMANTIC_PLAN.md, §AJ).

    python manage.py export_ai_corpus            # → shop/static/ai/corpus.json
    python manage.py export_ai_corpus --out path.json
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand

DEFAULT_OUT = Path('shop/static/ai/corpus.json')
GLOSSARY_PATH = Path('knowledge/data/glossary.json')


def _clean(text: str, limit: int = 1200) -> str:
    """Сжать текст до limit символов, схлопнуть пробелы (эмбеддеру длинное не нужно)."""
    return ' '.join(str(text or '').split())[:limit]


def _glossary_items() -> list[dict]:
    try:
        entries = json.loads(GLOSSARY_PATH.read_text(encoding='utf-8'))
    except Exception:
        return []
    out = []
    for e in entries:
        term = e.get('term') or (e.get('id') or '')
        text = _clean(f'{term}. {e.get("definition", "")} {e.get("formula", "")}')
        if text:
            out.append(
                {
                    'id': f'glossary-{e.get("id")}',
                    'source': 'glossary',
                    'title': term,
                    'text': text,
                    'url': e.get('url') or '',
                }
            )
    return out


def _article_items() -> list[dict]:
    try:
        from knowledge.models import Article
    except Exception:
        return []
    out = []
    for a in Article.objects.filter(is_published=True).select_related('category')[:200]:
        text = _clean(f'{a.title}. {a.summary} {a.body}')
        if text:
            out.append(
                {
                    'id': f'article-{a.id}',
                    'source': 'article',
                    'title': a.title,
                    'text': text,
                    'url': f'/knowledge/articles/{a.slug}/',
                }
            )
    return out


def _learning_items() -> list[dict]:
    try:
        from knowledge.models import LearningLesson, LearningTask
    except Exception:
        return []
    out = []
    for lesson in LearningLesson.objects.filter(is_published=True, track__is_published=True).select_related(
        'track'
    )[:200]:
        text = _clean(f'{lesson.title}. {lesson.summary} {lesson.formula} {lesson.theory}')
        if text:
            out.append(
                {
                    'id': f'lesson-{lesson.id}',
                    'source': 'learning',
                    'title': lesson.title,
                    'text': text,
                    'url': f'/knowledge/learning/{lesson.slug}/',
                }
            )
    for task in LearningTask.objects.filter(
        lesson__is_published=True, lesson__track__is_published=True
    ).select_related('lesson')[:300]:
        text = _clean(f'{task.title}. {task.prompt}')
        if text:
            out.append(
                {
                    'id': f'task-{task.id}',
                    'source': 'learning',
                    'title': task.title,
                    'text': text,
                    'url': f'/knowledge/learning/{task.lesson.slug}/',
                }
            )
    return out


class Command(BaseCommand):
    help = 'Экспорт текстового корпуса ассистента (glossary+статьи+уроки) в JSON для эмбеддингов.'

    def add_arguments(self, parser):
        parser.add_argument('--out', type=str, default=str(DEFAULT_OUT))

    def handle(self, *args, **opts):
        items = _glossary_items() + _article_items() + _learning_items()
        by_source: dict[str, int] = {}
        for it in items:
            by_source[it['source']] = by_source.get(it['source'], 0) + 1
        out_path = Path(opts['out'])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps({'count': len(items), 'items': items}, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        self.stdout.write(self.style.SUCCESS(f'Корпус: {len(items)} элементов ({by_source}) -> {out_path}'))
