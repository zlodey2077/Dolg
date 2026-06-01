"""DolgAIPipeline — main entry point для всех AI-задач.

4 задачи (соответствуют UI-кнопкам в /simulation/ AI-panel):

1. find_analogs(product, top_k=5)
   Поиск похожих компонентов в каталоге по параметрам.
   Метод: cosine-similarity на нормализованных feature-векторах
   (Phase 2: learned embeddings).

2. detect_anomalies(scheme_data)
   DRC++ — продвинутая проверка ошибок:
   - Несвязные подграфы
   - Циклы без активных элементов
   - Подозрительная топология (e.g. battery без ground)
   Метод: pattern-matching на графе схемы
   (Phase 2: GNN-классификатор аномалий).

3. explain_scheme(scheme_data)
   Генерация естественно-языкового описания схемы.
   Метод: template-engine + topology heuristics
   (Phase 2: small Transformer fine-tuned на корпусе DOLG demo-схем).

4. recommend_next_component(scheme_data)
   Предсказывает следующий компонент на основе текущей топологии.
   Метод: правила топологии + статистика по существующим схемам
   (Phase 2: GNN с обучением next-component prediction).
"""

from .embeddings import (
    find_similar_products,
)
from .heuristics import (
    count_components_by_type,
    find_cycles_without_active,
    find_isolated_nodes,
    generate_scheme_description,
    schema_to_graph,
    suggest_next_component_by_rules,
)


class DolgAIPipeline:
    """Гибридная AI-pipeline.

    Backend = 'heuristic' — текущая реализация (rule-based + cosine).
    Backend = 'neural'    — PyTorch deep-hints слой. Он не заменяет
                           heuristic/expert baseline, а добавляет
                           вероятностную подсказку.
    """
    SUPPORTED_BACKENDS = {'heuristic', 'neural'}

    def __init__(self, backend: str = 'heuristic'):
        if backend not in self.SUPPORTED_BACKENDS:
            raise ValueError(f'Unknown backend: {backend!r}. '
                             f'Supported: {sorted(self.SUPPORTED_BACKENDS)}')
        self.backend = backend
        self._neural = None
        self.neural_unavailable_reason = ''
        self._model_version = '0.1.0-heuristic'
        if backend == 'neural':
            try:
                from .neural import MODEL_VERSION, NeuralCircuitAdvisor
                self._neural = NeuralCircuitAdvisor()
                self._model_version = MODEL_VERSION
            except Exception as exc:
                self.neural_unavailable_reason = str(exc)
                self.backend = 'heuristic'

    # ── 1. Find analogs ───────────────────────────────────────────────
    def find_analogs(self, product, top_k: int = 5) -> list:
        """Возвращает top_k товаров наиболее похожих на product.

        Returns:
            list[dict] — каждый dict: {product, score, why}
                product — Product instance
                score — float 0..1, чем выше тем похожее
                why — human-readable объяснение «почему похож»
        """
        return find_similar_products(product, top_k=top_k)

    # ── 2. Detect anomalies (DRC++) ───────────────────────────────────
    def detect_anomalies(self, scheme_data: dict) -> list:
        """Находит подозрительные паттерны в схеме.

        Returns:
            list[dict] — каждый dict: {type, severity, message, component_ids}
                type — 'isolated_node' / 'cycle_no_active' / 'no_ground' / ...
                severity — 'info' / 'warning' / 'error'
                message — что не так (для UI)
                component_ids — какие компоненты затронуты (для подсветки)
        """
        if not scheme_data:
            return []
        graph = schema_to_graph(scheme_data)
        anomalies = []
        anomalies.extend(find_isolated_nodes(graph, scheme_data))
        anomalies.extend(find_cycles_without_active(graph, scheme_data))
        # Доп. эвристика: схема без ground = подозрительно
        types = count_components_by_type(scheme_data)
        if types.get('ground', 0) == 0 and len(scheme_data.get('components', [])) > 2:
            anomalies.append({
                'type': 'no_ground',
                'severity': 'warning',
                'message': 'В схеме нет ground-компонента. Узлы могут «плавать», '
                           'SPICE-симуляция вернёт ошибку.',
                'component_ids': [],
            })
        neural = self._neural_prediction(scheme_data)
        if neural and neural.get('risk_score', 0) >= 0.65:
            anomalies.append({
                'type': 'neural_deep_hint',
                'severity': 'warning',
                'message': (
                    'PyTorch deep-hint считает схему рискованной '
                    f"({neural.get('risk_score'):.2f}); проверьте GND, связи и BOM."
                ),
                'component_ids': [],
                'neural': neural,
            })
        return anomalies

    # ── 3. Explain scheme ─────────────────────────────────────────────
    def explain_scheme(self, scheme_data: dict) -> dict:
        """Генерирует описание схемы.

        Returns:
            dict: {
                'title': str — краткое название (например, «RC-фильтр»),
                'summary': str — описание из 2-3 предложений,
                'topology': str — тип топологии («ladder», «bridge», ...),
                'components_breakdown': dict — count по типам,
                'estimated_use_case': str — где используется,
            }
        """
        if not scheme_data or not scheme_data.get('components'):
            return {
                'title': 'Пустая схема',
                'summary': 'Схема ещё не содержит компонентов.',
                'topology': 'empty',
                'components_breakdown': {},
                'estimated_use_case': '',
            }
        result = generate_scheme_description(scheme_data)
        neural = self._neural_prediction(scheme_data)
        if neural:
            result['deep_hint'] = {
                'topology': neural.get('topology'),
                'topology_confidence': neural.get('topology_confidence'),
                'risk_score': neural.get('risk_score'),
                'risk_label': neural.get('risk_label'),
                'trained': neural.get('trained'),
                'expert_baseline': neural.get('expert_baseline') or {},
                'agreement_score': neural.get('agreement_score'),
                'calibrated_confidence': neural.get('calibrated_confidence'),
                'confidence_policy': neural.get('confidence_policy'),
                'evidence_sources': neural.get('evidence_sources') or [],
                'evidence_topics': neural.get('evidence_topics') or [],
            }
        return result

    # ── 4. Recommend next component ───────────────────────────────────
    def recommend_next_component(self, scheme_data: dict) -> list:
        """Предлагает компоненты, которые логично добавить дальше.

        Returns:
            list[dict] — top-3 рекомендации, каждый dict:
                {
                    'component_type': str — 'resistor' / 'capacitor' / ...,
                    'reason': str — «обычно после battery идёт ground»,
                    'confidence': float — 0..1,
                }
        """
        if not scheme_data:
            return [{
                'component_type': 'battery',
                'reason': 'Начните с источника питания.',
                'confidence': 0.9,
            }]
        recs = suggest_next_component_by_rules(scheme_data)
        neural = self._neural_prediction(scheme_data)
        if neural:
            seen = {item.get('component_type') for item in recs}
            for item in neural.get('next_components') or []:
                if item.get('component_type') in seen:
                    continue
                recs.append({
                    'component_type': item.get('component_type'),
                    'reason': 'PyTorch deep-hint: ' + item.get('reason', ''),
                    'confidence': item.get('confidence', 0.0),
                    'backend': 'neural',
                })
                seen.add(item.get('component_type'))
        return recs[:3]

    def _neural_prediction(self, scheme_data: dict) -> dict | None:
        if self._neural is None:
            return None
        try:
            return self._neural.predict(scheme_data)
        except Exception as exc:
            self.neural_unavailable_reason = str(exc)
            return None

    # ── Meta ──────────────────────────────────────────────────────────
    def info(self) -> dict:
        torch_available = False
        model_path = ''
        neural_ready = False
        neural_trained = False
        try:
            from .neural import default_model_path, torch_available as _torch_available
            torch_available = _torch_available()
            model_path = str(default_model_path())
            neural_ready = bool(self._neural is not None and torch_available)
            if self._neural is not None:
                neural_trained = bool(getattr(self._neural, 'model_path', None) and self._neural.model_path.exists())
        except Exception as exc:
            self.neural_unavailable_reason = str(exc)
        dataset = {}
        try:
            from Dolg_APP.services.ai_training import summarize_ai_training_examples
            dataset = summarize_ai_training_examples()
        except Exception:
            dataset = {'ok': False}
        return {
            'backend': self.backend,
            'model_version': self._model_version,
            'capabilities': ['find_analogs', 'detect_anomalies',
                             'explain_scheme', 'recommend_next_component'],
            'neural': {
                'torch_available': torch_available,
                'ready': neural_ready,
                'trained_model': neural_trained,
                'model_path': model_path,
                'unavailable_reason': self.neural_unavailable_reason,
                'note': 'PyTorch backend is deep-hints only; expert baseline remains final verdict.',
            },
            'dataset': dataset,
            'note': 'Hybrid expert-first AI. Neural backend adds probabilistic deep hints when enabled.',
        }
