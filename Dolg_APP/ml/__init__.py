"""DOLG AI Pipeline package.

Архитектура: Pipeline-pattern для inference.
- Фаза 1 (текущая): rule-based heuristics + cosine-similarity на parameter-vectors.
  Структура кода mirror'ит реальный ML pipeline (predict() interface),
  чтобы при переходе на Фазу 2 заменялся только backend.
- Фаза 2 (планируется): обученные на собственном корпусе схем модели
  - GNN (Graph Neural Network) — для DRC++ и рекомендации компонентов
  - Малый Transformer — для генерации описаний схем
  - Embedding-модель — для поиска аналогов (заменит cosine)

API:
    from Dolg_APP.ml import pipeline
    pipeline.find_analogs(product)
    pipeline.detect_anomalies(scheme_data)
    pipeline.explain_scheme(scheme_data)
    pipeline.recommend_next_component(scheme_data)
"""
import os

from .pipeline import DolgAIPipeline

# Глобальный singleton. По умолчанию heuristic, чтобы Django не тянул torch
# на старте. Для deep-hints: DOLG_AI_BACKEND=neural.
pipeline = DolgAIPipeline(backend=os.getenv('DOLG_AI_BACKEND', 'heuristic'))
