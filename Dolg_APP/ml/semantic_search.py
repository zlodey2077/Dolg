"""Семантический поиск товаров через TF-IDF + cosine similarity (Phase 2).

**ВАЖНО про выбор стека**: изначально хотели fastembed (ONNX, ~30 МБ), но
на Windows + Python 3.14 транзитивная зависимость `py-rust-stemmers`
требует Rust toolchain. Альтернатива sentence-transformers — ~2 ГБ
PyTorch.

Выбран компромисс: **sklearn `TfidfVectorizer` + `cosine_similarity`**.
Это не настоящие dense embeddings (нет «смысла» в эмбеддинге), НО:
- Pure Python + numpy/scipy (уже установлены)
- 0 МБ моделей, 0 GPU
- Работает мгновенно на 100-10000 товаров
- Лучше rule-based: ngrams ловят части слов, IDF понижает шум
- Достаточно для диплома (~100 товаров) и POC

При желании можно потом заменить функции `_encode()` и `build_index()` на
fastembed/sentence-transformers без изменения API — публичные функции
(`semantic_top_k`, `hybrid_search`, `is_semantic_available`) останутся теми же.

Связано с [[plugins-backlog]] (C), [[smart-search-todo]] (Phase 2 «семантика»).
"""
from __future__ import annotations

import json
import logging
import pickle
from pathlib import Path
from typing import Iterable

from django.conf import settings

logger = logging.getLogger(__name__)

# Параметры индекса. Файлы хранятся в media/search/.
_INDEX_DIR = Path(settings.MEDIA_ROOT) / 'search'
_VECTORIZER_FILE = _INDEX_DIR / 'tfidf_vectorizer.pkl'
_MATRIX_FILE = _INDEX_DIR / 'tfidf_matrix.npz'
_MAPPING_FILE = _INDEX_DIR / 'products.json'
# Marker-файл, который ставит shop.signals при save/delete Product —
# индекс устарел, нужен rebuild. См. comment в shop/signals.py.
_STALE_MARKER = _INDEX_DIR / '.stale'

# Lazy-init объекты
_vectorizer = None    # sklearn TfidfVectorizer
_matrix = None        # scipy.sparse матрица embeddings [N × V]
_id_mapping: list[int] = []   # позиция в матрице → Product.id


def is_semantic_available() -> bool:
    """True если sklearn установлен. Иначе rule-based fallback."""
    try:
        import sklearn  # noqa: F401
        return True
    except ImportError:
        return False


def is_index_stale() -> bool:
    """True если в media/search/.stale есть marker — Product был изменён
    после build_index. Использовать как сигнал «нужен rebuild_search_index».
    """
    return _STALE_MARKER.exists()


def _clear_stale_marker():
    """После успешного build_index убираем marker."""
    try:
        _STALE_MARKER.unlink(missing_ok=True)
    except Exception:
        pass


def _build_product_text(product) -> str:
    """Собирает текст для embedding'а из всех релевантных полей Product."""
    parts: list[str] = []
    parts.append(product.name or '')
    if product.part_number:
        parts.append(product.part_number)
    if product.description:
        parts.append(product.description)
    cat = getattr(product, 'category', None)
    if cat is not None:
        parts.append(cat.name or '')
    # Параметры — самые информативные для семантики
    if product.parameters:
        for key, value in product.parameters.items():
            if value and key not in {'image_source', 'image_source_url', 'image_source_policy'}:
                parts.append(f'{key} {value}')
    return ' '.join(p for p in parts if p)


# Russian morphology через pymorphy3. Lazy-import: если пакет не установлен,
# используется raw-tokenization (без леммы). С леммами «резисторы» = «резистор» —
# поиск становится толерантным к падежам и числам.
_morph = None
_morph_tried = False


def _get_morph():
    """Lazy-init pymorphy3.MorphAnalyzer. Если pymorphy3 не установлен, None."""
    global _morph, _morph_tried
    if _morph_tried:
        return _morph
    _morph_tried = True
    try:
        import pymorphy3
        _morph = pymorphy3.MorphAnalyzer()
    except ImportError:
        _morph = None
    return _morph


def _russian_lemma_analyzer(text):
    """Используется как `analyzer=...` в TfidfVectorizer.

    Если pymorphy3 не установлен, делает простой split по re. Иначе разбивает
    текст на токены и для каждого русского слова возвращает нормальную форму
    (лемму), для остальных — как есть.

    Latin/числа (LM358, 4.7uF, BC547B) НЕ нормализуются — лемматизация
    их сломает.
    """
    import re

    morph = _get_morph()
    tokens = re.findall(r"\b\w+\b", text.lower(), flags=re.UNICODE)
    if morph is None:
        return tokens
    result = []
    for tok in tokens:
        # Только русские слова (есть кириллица) лемматизируем
        if re.search(r'[а-яё]', tok):
            parsed = morph.parse(tok)
            if parsed:
                result.append(parsed[0].normal_form)
                continue
        result.append(tok)
    return result


def build_index(products: Iterable | None = None) -> int:
    """Перестраивает TF-IDF индекс по ВСЕМ Product. Сохраняет на диск.
    Возвращает количество проиндексированных товаров.
    """
    from scipy import sparse
    from sklearn.feature_extraction.text import TfidfVectorizer

    from shop.models import Product

    _INDEX_DIR.mkdir(parents=True, exist_ok=True)
    if products is None:
        products = list(Product.objects.select_related('category').all())
    else:
        products = list(products)
    if not products:
        logger.warning('No products to index')
        return 0

    texts = [_build_product_text(p) for p in products]
    # min_df=1 — допускаем редкие термины (каталог небольшой).
    # max_features=5000 — ограничение vocabulary, защита от взрыва памяти.
    # sublinear_tf=True — log-нормализация частоты (стандарт для TF-IDF).
    # analyzer=_russian_lemma_analyzer — если pymorphy3 установлен, лемматизация
    # русских слов: «резисторы» = «резистор», «диодов» = «диод».
    # ngram_range НЕ задаём — он несовместим с custom analyzer; биграммы
    # можно реализовать внутри analyzer'а, но для каталога 100-1000 товаров
    # униграмм с леммами достаточно.
    vectorizer = TfidfVectorizer(
        min_df=1,
        max_features=5000,
        sublinear_tf=True,
        analyzer=_russian_lemma_analyzer,
    )
    matrix = vectorizer.fit_transform(texts)

    # Сохраняем на диск
    with _VECTORIZER_FILE.open('wb') as f:
        pickle.dump(vectorizer, f)
    sparse.save_npz(_MATRIX_FILE, matrix)
    mapping = [int(p.id) for p in products]
    _MAPPING_FILE.write_text(json.dumps(mapping), encoding='utf-8')

    # Сбрасываем in-memory кеш
    global _vectorizer, _matrix, _id_mapping
    _vectorizer = vectorizer
    _matrix = matrix
    _id_mapping = mapping
    _clear_stale_marker()

    logger.info('Indexed %d products → %s', len(products), _VECTORIZER_FILE)
    return len(products)


def _load_index():
    """Lazy-load с диска. Возвращает (vectorizer, matrix, mapping) или (None, None, None)."""
    global _vectorizer, _matrix, _id_mapping
    if _vectorizer is not None and _matrix is not None:
        return _vectorizer, _matrix, _id_mapping
    if not _VECTORIZER_FILE.exists() or not _MATRIX_FILE.exists() or not _MAPPING_FILE.exists():
        return None, None, None
    from scipy import sparse
    with _VECTORIZER_FILE.open('rb') as f:
        _vectorizer = pickle.load(f)
    _matrix = sparse.load_npz(_MATRIX_FILE)
    _id_mapping = json.loads(_MAPPING_FILE.read_text(encoding='utf-8'))
    return _vectorizer, _matrix, _id_mapping


def semantic_top_k(query: str, k: int = 20) -> list[tuple[int, float]]:
    """Возвращает top-k Product.id с similarity score (0..1).

    Если индекс не построен → пустой список (caller fallback на rule-based).
    """
    if not query or not query.strip():
        return []
    vectorizer, matrix, mapping = _load_index()
    if vectorizer is None or matrix is None or not mapping:
        return []

    from sklearn.metrics.pairwise import cosine_similarity

    query_vec = vectorizer.transform([query])
    sims = cosine_similarity(query_vec, matrix)[0]   # shape (N,)
    # Top-k по убыванию similarity, отбрасываем zero-similarity
    import numpy as np

    top_k_idxs = np.argsort(-sims)[:k]
    result: list[tuple[int, float]] = []
    for idx in top_k_idxs:
        sim = float(sims[idx])
        if sim <= 0:
            break
        result.append((mapping[int(idx)], sim))
    return result


def hybrid_search(query: str, base_qs, k: int = 20) -> list:
    """Hybrid: TF-IDF top-K + rule-based smart_search через RRF.

    Reciprocal Rank Fusion (RRF): score = sum(1 / (rank + 60)).

    Returns: список Product (отсортированный по RRF score, top-k).
    """
    from shop.models import Product
    from shop.smart_search import smart_search

    K_RRF = 60

    semantic = semantic_top_k(query, k=k * 2)
    rule_qs, _ = smart_search(base_qs, query)
    rule_ids = list(rule_qs.values_list('id', flat=True)[:k * 2])

    scores: dict[int, float] = {}
    for rank, (pid, _sim) in enumerate(semantic):
        scores[pid] = scores.get(pid, 0.0) + 1.0 / (rank + K_RRF)
    for rank, pid in enumerate(rule_ids):
        scores[pid] = scores.get(pid, 0.0) + 1.0 / (rank + K_RRF)

    if not scores:
        return []

    sorted_ids = sorted(scores, key=lambda i: -scores[i])[:k]
    products_by_id = {p.id: p for p in Product.objects.filter(id__in=sorted_ids).select_related('category')}
    return [products_by_id[i] for i in sorted_ids if i in products_by_id]
