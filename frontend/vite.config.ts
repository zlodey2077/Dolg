import { defineConfig } from 'vite';
import { resolve } from 'path';

/**
 * Vite-сборка для DOLG frontend.
 *
 * Стратегия миграции (постепенная, без breaking changes):
 *   1. Каждый JS-модуль из shop/static/simulation/*.js по очереди
 *      переписывается в src/*.ts и кладётся как точка входа.
 *   2. Vite собирает один bundle.js + sourcemaps в shop/static/lib/dolg/.
 *   3. simulation.html заменяет несколько <script src="...">
 *      одним <script type="module" src="{% static 'lib/dolg/index.js' %}">.
 *   4. Глобальные функции (window.DolgScheme3D и т.п.) сохраняем для
 *      обратной совместимости с inline-обработчиками в шаблонах.
 *
 * Пока что в src/ только один модуль (scheme-netlist) как proof.
 * Остальные .js остаются как есть и подключаются параллельно.
 */
export default defineConfig({
  build: {
    outDir: resolve(__dirname, '../shop/static/lib/dolg'),
    emptyOutDir: true,
    sourcemap: true,
    target: 'es2020',
    minify: 'esbuild',
    lib: {
      entry: resolve(__dirname, 'src/index.ts'),
      name: 'Dolg',
      fileName: () => 'index.js',
      formats: ['iife'],   // IIFE — никаких import-в-браузере, сразу globals
    },
    rollupOptions: {
      // Three.js / Pixi.js — внешние, подключаются отдельным <script> в шаблоне.
      external: ['three'],
      output: {
        globals: { three: 'THREE' },
      },
    },
  },
});
