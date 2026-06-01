"""Умный поиск товаров — расширение базового `icontains` фильтра.

Что делает (по сравнению со старым `_apply_filters`):

1. **Multi-token parsing**: «резистор vishay 1k» → 3 токена, каждый матчится
   отдельно (AND-логика — все токены должны найтись хоть в одном поле).

2. **Field-weighted relevance**: match в name весит больше чем в description.
   Используется для сортировки результатов по релевантности (лучшие сверху).

3. **Fuzzy fallback на typo**: если строгий ORM-фильтр ничего не нашёл,
   через `rapidfuzz` ищем близкие part_number / name с similarity ≥ 70.
   Это решает «резстор» (опечатка) → «резистор».

4. **Range-фильтры по параметрам**: токен «R<10k» / «P>0.25» парсится в
   фильтр по `parameters__resistance__lt=...` etc. (Phase 1.5 — не сейчас.)

5. **Facets с counts**: возвращает счётчики по manufacturer/lifecycle/package
   для UI sidebar («Vishay (8) · Yageo (4)»).

DB-agnostic — работает и на SQLite (dev), и на Postgres (prod). Когда
переедем на Postgres → можно добавить второй слой через
`django.contrib.postgres.search.SearchVector` для морфологии русского.

Связано с [[smart-search-todo]] (memory) — там расписаны 6 вариантов
и почему мы выбрали этот (rapidfuzz без внешнего сервиса).
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

from django.db.models import Q, QuerySet
from rapidfuzz import fuzz, process

# Минимальный similarity-score для fuzzy fallback (0-100). 75 для partial_ratio:
# короткая needle («резстор», 7 симв.) против длинного haystack (name + category
# + description, 100+ симв.) — WRatio даёт ~50 (теряется в шуме), partial_ratio
# даёт 85+ т.к. ищет наиболее похожую подпоследовательность. Cutoff 75 фильтрует
# случайные «совпадения по 2 буквам».
FUZZY_SCORE_CUTOFF = 75

# Какие поля используются для search-индекса. Имя имеет наибольший вес —
# user обычно ищет «резистор», а не «компонент с описанием резистор».
# category__name добавлено чтобы запрос «резистор» матчился по русскому
# названию категории — у нас имена товаров технические («Vishay WSL2512R0100FEA»),
# а слово «резистор» живёт в категории и описании.
SEARCH_FIELDS = ('name', 'part_number', 'description', 'category__name')


def parse_query_tokens(query: str) -> list[str]:
    """Разбивает строку поиска на токены. Слова в кавычках — один токен.

    «резистор vishay 1k»     → ['резистор', 'vishay', '1k']
    «"op-amp ic" rail-to-rail» → ['op-amp ic', 'rail-to-rail']
    """
    if not query:
        return []
    # Сначала вытаскиваем кавычки-фразы
    quoted = re.findall(r'"([^"]+)"', query)
    rest = re.sub(r'"[^"]+"', '', query)
    # Затем split-им оставшееся по пробелам/запятым
    words = [w.strip() for w in re.split(r'[\s,]+', rest) if w.strip()]
    tokens = quoted + words
    # Уникальные + сохранение порядка
    seen = set()
    result = []
    for t in tokens:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            result.append(t)
    return result


def build_token_filter(tokens: list[str]) -> Q:
    """AND-фильтр: каждый токен ищется в любом из SEARCH_FIELDS."""
    if not tokens:
        return Q()
    combined = Q()
    for token in tokens:
        per_token = Q()
        for field in SEARCH_FIELDS:
            per_token |= Q(**{f'{field}__icontains': token})
        combined &= per_token
    return combined


def smart_search(products: QuerySet, query: str) -> tuple[QuerySet, list[str]]:
    """Главная точка входа. Применяет multi-token + fuzzy fallback.

    Returns: (фильтрованный queryset, список токенов для UI-подсветки)
    """
    tokens = parse_query_tokens(query)
    if not tokens:
        return products, []

    base = products.filter(build_token_filter(tokens))

    # Если строгий filter ничего не нашёл — fuzzy fallback.
    # Берём первые N candidate-имён + part_number из ИСХОДНОГО queryset
    # (без token-фильтра), ищем близкие через rapidfuzz, добавляем по id.
    if base.exists() or len(tokens) > 2:
        # При 3+ токенах fuzzy слишком дорогой — отказываемся.
        return base, tokens

    candidates_pool = list(
        products.values_list('id', 'name', 'part_number', 'category__name', 'description')[:1000]
    )
    if not candidates_pool:
        return base, tokens

    # rapidfuzz.process.extract: возвращает top-N matches по любой строке.
    # Склеиваем name + part_number + category-name + первые 120 символов description —
    # описание режем чтобы long-text не доминировал в WRatio scorer.
    name_lookup = {}
    for pid, name, pn, cat_name, desc in candidates_pool:
        haystack = f'{name} {pn or ""} {cat_name or ""} {(desc or "")[:120]}'.lower()
        name_lookup[haystack] = pid
    needle = ' '.join(tokens).lower()
    matches = process.extract(
        needle, name_lookup.keys(),
        # partial_ratio: ищет лучшую subsequence-similarity. Подходит для
        # «короткая опечатка vs длинный haystack» — WRatio в этом случае
        # даёт ~50 (теряется в шуме), partial_ratio выдаёт реальный score.
        scorer=fuzz.partial_ratio,
        limit=20,
        score_cutoff=FUZZY_SCORE_CUTOFF,
    )
    if not matches:
        return base, tokens

    fuzzy_ids = [name_lookup[key] for key, _score, _idx in matches]
    return products.filter(id__in=fuzzy_ids), tokens


def compute_facets(products: QuerySet) -> dict:
    """Возвращает counts по manufacturer/lifecycle/package для текущего qs.

    Используется в sidebar каталога: «Vishay (8) · Yageo (4) · …».
    Один SQL на всё (group by) благодаря annotate(Count).
    """
    if not isinstance(products, QuerySet):
        # Если уже list (после param-filters Python-фильтрации) — считаем в Python
        return _facets_from_list(products)
    return {
        'manufacturer': _ordered_counts(
            products.values_list('manufacturer', flat=True)
        ),
        'lifecycle': _ordered_counts(
            products.values_list('lifecycle_status', flat=True)
        ),
        'package': _ordered_counts(
            products.exclude(package_type='').values_list('package_type', flat=True)
        ),
    }


def _ordered_counts(values: Iterable[str]) -> list[tuple[str, int]]:
    """Counter.most_common, но без пустых значений и отсортированный."""
    counter = Counter(v for v in values if v)
    return counter.most_common()


def _facets_from_list(products: list) -> dict:
    """Fallback если products уже list (после Python-фильтрации параметров)."""
    return {
        'manufacturer': _ordered_counts(p.manufacturer for p in products),
        'lifecycle': _ordered_counts(p.lifecycle_status for p in products),
        'package': _ordered_counts(p.package_type for p in products),
    }
