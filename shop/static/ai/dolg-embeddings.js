/**
 * dolg-embeddings.js — клиентские нейро-эмбеддинги для ассистента (Transformers.js v3/v4).
 *
 * Гоняет ONNX-модель В БРАУЗЕРЕ (WASM/WebGPU) — без Python и серверных ML-зависимостей,
 * обходит wheel-блокер sentence-transformers на Windows+py3.14 (см.
 * docs/TRANSFORMERS_JS_SEMANTIC_PLAN.md, ENGINEERING_NOTES §AJ).
 *
 * Self-hosted: библиотека вендорится в /static/ai/lib/, модель — в /static/ai/models/
 * (allowRemoteModels=false). Пока модель не завендорена локально — фолбэк на Xenova-хаб.
 *
 * API:
 *   await DolgEmbeddings.ready()           — лениво грузит модель (кэш Cache API браузера)
 *   await DolgEmbeddings.embed(texts[])    — Float32Array[] нормализованных эмбеддингов (384d)
 *   DolgEmbeddings.cosine(a, b)            — косинусная близость двух векторов
 *   DolgEmbeddings.rank(queryVec, items)   — сортировка items[{vec,...}] по близости к запросу
 *   DolgEmbeddings.available()             — успела ли модель загрузиться (для фолбэка на TF-IDF)
 */
const DolgEmbeddings = (() => {
  const LIB_URL = '/static/ai/lib/transformers.min.js';
  // Мультиязычная (50+ языков вкл. РУССКИЙ), 384d. Англо-only all-MiniLM-L6-v2 на нашем
  // русском корпусе путает термины (проверено: «конденсатор»~«резистор» > «конденсатор»~«ёмкость»).
  const MODEL = 'Xenova/paraphrase-multilingual-MiniLM-L12-v2';
  const LOCAL_MODEL_PATH = '/static/ai/models/';
  const WASM_PATH = '/static/ai/lib/'; // сюда вендорить ort-*.wasm для полного офлайна

  let _extractorPromise = null;
  let _ok = false;

  async function _init() {
    const tjs = await import(LIB_URL).catch(() =>
      // фолбэк на ESM-CDN, если локальный бандл не завендорен
      import('https://cdn.jsdelivr.net/npm/@huggingface/transformers@3'),
    );
    const { pipeline, env } = tjs;
    // Self-host: сначала локальная модель, затем удалённый Xenova-хаб как фолбэк.
    env.allowLocalModels = true;
    env.localModelPath = LOCAL_MODEL_PATH;
    env.allowRemoteModels = true; // переключить на false, когда модель завендорена
    try {
      if (env.backends?.onnx?.wasm) env.backends.onnx.wasm.wasmPaths = WASM_PATH;
    } catch (_) {
      /* wasm-пути не критичны: библиотека возьмёт дефолтные */
    }
    const extractor = await pipeline('feature-extraction', MODEL, { quantized: true });
    _ok = true;
    return extractor;
  }

  function ready() {
    if (!_extractorPromise) _extractorPromise = _init();
    return _extractorPromise;
  }

  async function embed(texts) {
    const list = Array.isArray(texts) ? texts : [texts];
    if (!list.length) return [];
    const extractor = await ready();
    // mean-pooling + L2-нормализация → можно сравнивать косинусом (= dot).
    const output = await extractor(list, { pooling: 'mean', normalize: true });
    const dim = output.dims[output.dims.length - 1];
    const data = output.data;
    const vecs = [];
    for (let i = 0; i < list.length; i++) {
      vecs.push(Float32Array.from(data.slice(i * dim, (i + 1) * dim)));
    }
    return vecs;
  }

  function cosine(a, b) {
    let dot = 0;
    const n = Math.min(a.length, b.length);
    for (let i = 0; i < n; i++) dot += a[i] * b[i];
    return dot; // векторы уже L2-нормализованы → dot == cosine
  }

  function rank(queryVec, items, { topK = 6 } = {}) {
    return items
      .map((it) => ({ ...it, score: cosine(queryVec, it.vec) }))
      .sort((x, y) => y.score - x.score)
      .slice(0, topK);
  }

  function available() {
    return _ok;
  }

  return { ready, embed, cosine, rank, available };
})();

if (typeof window !== 'undefined') window.DolgEmbeddings = DolgEmbeddings;
export default DolgEmbeddings;
