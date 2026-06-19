/**
 * build_embeddings.mjs — строит corpus_embeddings.json из corpus.json (Transformers.js).
 *
 * Разовый build-шаг (не рантайм): эмбеддит текстовый корпус ассистента мультиязычной
 * моделью и сохраняет векторы для клиентского семантического grounding'а
 * (см. docs/TRANSFORMERS_JS_SEMANTIC_PLAN.md, Ф2). Рантайм — чисто браузер+Django.
 *
 * Подготовка корпуса:  python manage.py export_ai_corpus   → shop/static/ai/corpus.json
 * Зависимость (разово): npm i @huggingface/transformers
 * Запуск:               node scripts/build_embeddings.mjs
 *
 * Модель — мультиязычная (50+ языков вкл. русский): англо-only all-MiniLM путает
 * русские термины (проверено: конденсатор~резистор > конденсатор~ёмкость).
 */
import fs from 'node:fs';
import path from 'node:path';

const MODEL = process.env.DOLG_EMB_MODEL || 'Xenova/paraphrase-multilingual-MiniLM-L12-v2';
const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), '..');
const IN = path.join(ROOT, 'shop', 'static', 'ai', 'corpus.json');
const OUT = path.join(ROOT, 'shop', 'static', 'ai', 'corpus_embeddings.json');

async function main() {
  if (!fs.existsSync(IN)) {
    console.error(`Нет ${IN}. Сначала: python manage.py export_ai_corpus`);
    process.exit(1);
  }
  const { pipeline } = await import('@huggingface/transformers');
  const corpus = JSON.parse(fs.readFileSync(IN, 'utf-8'));
  const items = corpus.items || [];
  console.log(`Корпус: ${items.length} элементов. Загружаю ${MODEL}…`);
  const extractor = await pipeline('feature-extraction', MODEL);

  const out = [];
  const BATCH = 32;
  for (let i = 0; i < items.length; i += BATCH) {
    const batch = items.slice(i, i + BATCH);
    const res = await extractor(batch.map((it) => it.text), { pooling: 'mean', normalize: true });
    const dim = res.dims[res.dims.length - 1];
    for (let k = 0; k < batch.length; k++) {
      const vec = Array.from(res.data.slice(k * dim, (k + 1) * dim), (x) => Math.round(x * 1e5) / 1e5);
      out.push({ id: batch[k].id, source: batch[k].source, title: batch[k].title, url: batch[k].url, vec });
    }
    console.log(`  ${Math.min(i + BATCH, items.length)}/${items.length}`);
  }

  const dim = out.length ? out[0].vec.length : 0;
  fs.writeFileSync(
    OUT,
    JSON.stringify({ model: MODEL, dim, count: out.length, items: out }),
    'utf-8',
  );
  console.log(`Готово: ${out.length} эмбеддингов (${dim}d) → ${OUT}`);
}

main().catch((e) => {
  console.error('Ошибка:', e?.message || e);
  process.exit(1);
});
