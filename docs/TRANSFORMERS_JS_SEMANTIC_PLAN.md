# План: семантика ассистента на Transformers.js v4 (обход §AJ wheel-блокера)

Дата: 2026-06-16. Источник идеи: ENGINEERING_NOTES §AJ/§AR. Связано: [[project-semantic-search]],
[[project-rag-roadmap]], [[local-ai-toolkit-l1-l5]].

## Проблема
Семантический поиск для ассистента откатывали: `sentence-transformers`/`torch`/`fastembed`
**не ставятся на Windows+py3.14** (wheel-блокер, [[project-semantic-search]]). Сейчас grounding =
server-side **TF-IDF + IDF** (`Dolg_APP/services/ai_retrieval.py`) — работает, но это лексика, не
семантика («ёмкость» ≠ «конденсатор» по смыслу не свяжет).

## Решение
**Transformers.js v4** (фев 2026) гоняет ONNX-эмбеддинги **в браузере** (WASM везде / WebGPU где
есть) — **Python не нужен вообще** → wheel-блокер обходится целиком. Полностью self-hosted:
ONNX-модель как локальный статик-ассет, remote-hub off.

- **Модель:** `Xenova/all-MiniLM-L6-v2` (384d, ~23 МБ int8) — дефолт; альтернатива `bge-small-en-v1.5`.
- **Принцип не меняется:** нейро-эмбеддинги — это **ранжирование grounding-контекста**, не вердикт
  (expert-first). Числа/факты по-прежнему из движков.

## Архитектура (гибрид, не ломая текущее)
1. **Корпус** (knowledge-статьи + glossary + expert_rules + demo-схемы) → эмбеддинги **один раз**.
   Т.к. в Python эмбеддингов нет — считаем либо (а) **Node-скриптом на transformers.js** на этапе
   сборки → отдаём `static/ai/corpus_embeddings.json`, либо (б) **в браузере** при первом заходе →
   кэш в IndexedDB. Рекомендую (а): детерминированно, без задержки у юзера.
2. **Запрос** юзера → эмбеддинг **вживую в браузере** (модель лениво грузится по требованию, кэш Cache API).
3. **Косинус** клиентски (query vs корпус) → top-K сниппетов → augment контекста `/api/ai/chat/`
   (или merge с серверным TF-IDF). **Фолбэк:** нет WebGPU/модели → текущий TF-IDF (никогда не хуже).

## Фазы и объём
- **Ф0. Вендоринг (S, ~0.5 дн):** `transformers.js` (npm→локальный static) + ONNX-модель в
  `shop/static/ai/models/` (hub off). Ленивая загрузка, кэш модели в Cache API.
- **Ф1. JS-модуль (S-M, ~0.5-1 дн):** `dolg-embeddings.js` — `loadModel()`, `embed(texts)→vec[]`,
  `cosine(a,b)`. Кэш корпус-эмбеддингов в IndexedDB, модели — в Cache API.
- **Ф2. Корпус-индекс (S, ~0.5 дн):** management-команда `export_ai_corpus --json` (текст
  knowledge/glossary/rules) + Node-скрипт `scripts/build_embeddings.mjs` → `corpus_embeddings.json`.
- **Ф3. Проводка в ассистент (M, ~0.5-1 дн):** в `dolg-ai-panel` считать query-эмбеддинг → косинус
  → top-K grounding → в `/api/ai/chat/` как `### CONTEXT ###`; фолбэк на TF-IDF; тесты.
- **Ф4 (post-defense). Intent-классификатор (M, ~1 дн):** zero-shot/мелкий классификатор в браузере
  → надёжная NL-классификация для планировщика Plan-then-Execute (§AI) вместо keyword-матчинга.

**Итог:** Ф0-Ф3 ≈ **2-3 дня** → семантический grounding на клиенте к защите. Ф4 — после.

## Точки касания
- `shop/static/ai/` (модель + corpus_embeddings.json + dolg-embeddings.js).
- `Dolg_APP/templates/tools/simulation.html` (dolg-ai-panel: вызов embed + косинус + фолбэк).
- `Dolg_APP/services/ai_retrieval.py` (оставить как фолбэк; опц. принять client-grounding в chat).
- `scripts/build_embeddings.mjs` + management `export_ai_corpus`.

## Риски/каветы
- **Вес модели ~23 МБ** → ленивая загрузка + кэш (Cache API); не блокировать UI.
- **Первая загрузка/латентность** → грузить по первому семантическому запросу, показывать прогресс.
- **WebGPU не везде** → WASM-фолбэк (медленнее, но работает); при отказе — TF-IDF.
- **Офлайн/демо-машина** → всё локально (hub off), интернет не нужен после вендоринга.
- **Node на этапе сборки** для Ф2 — разовый, не в рантайме (рантайм чисто браузер+Django).

## Питч для защиты
«Семантический поиск ассистента — **нейро-эмбеддинги целиком на клиенте** (Transformers.js/ONNX,
WebGPU), self-hosted, без облака и без серверных ML-зависимостей. Это обошло Python-wheel-блокер
(torch на Windows) и дало смысловой grounding поверх детерминированных движков (expert-first)».
