"""Embedding / similarity для поиска аналогов компонентов.

Phase 1: ручные feature-векторы из Product.parameters + cosine-similarity.
Phase 2: learned embeddings через autoencoder или contrastive learning.
"""
import math

# Какие параметры используем для feature-вектора. Каждый параметр
# нормализуется в log-space (т.к. R/C/V в DOLG варьируются по 6 порядков
# величины), что даёт более ровную similarity.
NUMERIC_FEATURES = {
    'resistance': 'log',
    'capacitance': 'log',
    'inductance': 'log',
    'voltage': 'log',
    'current': 'log',
    'power': 'log',
    'wattage': 'log',
    'capacity': 'log',         # SSD/RAM объём
    'frequency': 'log',
    'tdp': 'linear',
    'cores': 'linear',
    'vram_gb': 'linear',
}

CATEGORICAL_FEATURES = ['type', 'mounting', 'package', 'form_factor', 'dielectric']


def _parse_numeric(value) -> float | None:
    """Пытаемся выдернуть число из строки вроде '10 кОм', '4.7 мкФ', '5 В'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().lower().replace(',', '.')
    multipliers = {
        'к': 1e3, 'k': 1e3, 'м': 1e-3, 'm': 1e-3, 'мк': 1e-6, 'u': 1e-6,
        'н': 1e-9, 'n': 1e-9, 'п': 1e-12, 'p': 1e-12,
        'мег': 1e6, 'meg': 1e6, 'г': 1e9, 'g': 1e9, 'т': 1e12, 't': 1e12,
    }
    # Простой парсер: число + опционально префикс + опционально единица
    import re
    m = re.match(r'^([-+]?\d*\.?\d+)\s*([a-zа-я]*)', s)
    if not m:
        return None
    try:
        num = float(m.group(1))
    except ValueError:
        return None
    suffix = m.group(2)
    # Префиксы (к/м/мк/н/п/мег/г/т) могут быть приклеены к единице
    for prefix, mult in sorted(multipliers.items(), key=lambda x: -len(x[0])):
        if suffix.startswith(prefix):
            return num * mult
    return num


def extract_product_features(product) -> dict:
    """Извлекает feature-vector из Product. Возвращает dict {feature_name: value}.

    - Numeric features (resistance/voltage/...): log-нормализованные
    - Categorical (type/mounting): one-hot key
    """
    params = product.parameters or {}
    features = {}

    # Numeric: extract + normalize
    for key, mode in NUMERIC_FEATURES.items():
        raw = params.get(key)
        num = _parse_numeric(raw)
        if num is None or num <= 0:
            continue
        if mode == 'log':
            features[f'num_{key}'] = math.log10(num)
        else:
            features[f'num_{key}'] = num

    # Categorical: одна фича = строковая категория
    for key in CATEGORICAL_FEATURES:
        v = params.get(key)
        if v:
            features[f'cat_{key}'] = str(v).strip().lower()

    # Category-slug — обязательно учитываем
    if product.category_id:
        features['cat_category'] = product.category.slug

    # Manufacturer — учитываем
    if product.manufacturer:
        features['cat_manufacturer'] = product.manufacturer

    return features


def cosine_similarity(features_a: dict, features_b: dict) -> float:
    """Cosine-similarity между двумя feature-векторами.

    Numeric features: считаем как обычные float-координаты.
    Categorical: 1.0 если совпадают, 0.0 если нет.

    Returns: float 0..1.
    """
    # Соберём all keys
    all_keys = set(features_a.keys()) | set(features_b.keys())
    if not all_keys:
        return 0.0

    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0

    for k in all_keys:
        a = features_a.get(k)
        b = features_b.get(k)
        if k.startswith('num_'):
            av = a if a is not None else 0.0
            bv = b if b is not None else 0.0
            dot += av * bv
            norm_a += av * av
            norm_b += bv * bv
        elif k.startswith('cat_'):
            # 1 если совпали (после нормализации), 0 иначе
            av = 1.0 if a is not None else 0.0
            bv = 1.0 if b is not None else 0.0
            if a == b and a is not None:
                dot += 1.0
            norm_a += av * av
            norm_b += bv * bv

    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def find_similar_products(product, top_k: int = 5) -> list:
    """Возвращает top_k товаров наиболее похожих на product.

    Returns: list[dict]
        Каждый dict: {'product': Product, 'score': float, 'why': str}
    """
    # Lazy-import чтобы не делать circular (ml импортируется из views ↔ models)
    from shop.models import Product

    target_features = extract_product_features(product)
    if not target_features:
        return []

    # Берём кандидатов в той же категории (для других категорий cross-comparisons
    # обычно бесполезны: резистор и видеокарта не «аналоги»).
    candidates_qs = Product.objects.filter(
        category=product.category,
    ).exclude(pk=product.pk).exclude(stock=0)[:200]   # limit чтобы не perf-hit

    scored = []
    for candidate in candidates_qs:
        cfeats = extract_product_features(candidate)
        score = cosine_similarity(target_features, cfeats)
        if score <= 0:
            continue
        # «Почему похож» — какие категориальные совпали + ближайшие numeric
        why_parts = []
        for k in cfeats:
            if k.startswith('cat_') and cfeats[k] == target_features.get(k):
                pretty = k.replace('cat_', '').replace('_', ' ')
                why_parts.append(f'{pretty}: {cfeats[k]}')
        why = ', '.join(why_parts[:3]) or 'общая категория'
        scored.append({
            'product': candidate,
            'score': round(score, 3),
            'why': why,
        })

    scored.sort(key=lambda x: -x['score'])
    return scored[:top_k]
