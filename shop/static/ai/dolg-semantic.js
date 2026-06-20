/**
 * dolg-semantic.js — клиентский семантический поиск по базе знаний (Ф3).
 *
 * Грузит предпосчитанные эмбеддинги корпуса (corpus_embeddings.json) + считает
 * эмбеддинг запроса вживую через DolgEmbeddings (Transformers.js) → косинус-ранжирование.
 * Возвращает топ-K семантически близких статей/уроков/терминов для grounding'а ассистента.
 *
 * Деградирует штатно: если модель/эмбеддинги недоступны (нет WebGPU/сети) — search()
 * вернёт [] и ассистент работает как раньше (серверный TF-IDF остаётся). Модель тяжёлая
 * (~120 МБ) → грузится ЛЕНИВО при первом семантическом запросе, не блокирует обычный чат.
 *
 * API:  await DolgSemantic.search(query, topK=3) → [{id,source,title,url,score}]
 */
const DolgSemantic = (() => {
  const CORPUS_URL = '/static/ai/corpus_embeddings.json';
  let _corpusPromise = null;

  async function _corpus() {
    if (!_corpusPromise) {
      _corpusPromise = fetch(CORPUS_URL)
        .then((r) => (r.ok ? r.json() : { items: [] }))
        .catch(() => ({ items: [] }));
    }
    return _corpusPromise;
  }

  async function search(query, topK = 3) {
    const q = String(query || '').trim();
    if (q.length < 3 || typeof window === 'undefined' || !window.DolgEmbeddings) return [];
    let corpus;
    try {
      corpus = await _corpus();
    } catch (_) {
      return [];
    }
    const items = (corpus && corpus.items) || [];
    if (!items.length) return [];
    let qvec;
    try {
      const vecs = await window.DolgEmbeddings.embed([q]);
      qvec = vecs && vecs[0];
    } catch (_) {
      return []; // модель не загрузилась → тихий фолбэк
    }
    if (!qvec) return [];
    const cos = window.DolgEmbeddings.cosine;
    return items
      .map((it) => ({
        id: it.id,
        source: it.source,
        title: it.title,
        url: it.url,
        score: cos(qvec, it.vec),
      }))
      .sort((a, b) => b.score - a.score)
      .slice(0, topK);
  }

  return { search };
})();

if (typeof window !== 'undefined') window.DolgSemantic = DolgSemantic;
export default DolgSemantic;
