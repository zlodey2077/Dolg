/**
 * DOLG TypeScript bundle — entry point.
 *
 * Этот файл — единственная точка входа для Vite. Всё, что собрано Vite,
 * экспортируется в `window.Dolg.*` (IIFE-режим). Шаблоны симулятора могут
 * пользоваться `window.Dolg.UnionFind` и т.п. вместо отдельных <script src=...>.
 *
 * Постепенная миграция:
 *   1. На каждый круг — переписываем 1-2 .js → .ts в src/.
 *   2. Дополняем этот index.ts экспортами.
 *   3. Bundle становится толще, но <script src> в шаблонах — меньше.
 *   4. По завершению — удаляем оригинальные .js.
 *
 * Сейчас здесь — Union-Find (proof of concept) и место для будущих
 * модулей (scheme-netlist, scheme-3d, scheme-lab).
 */

import { createUnionFind, portKey } from './union-find';

// Экспонируем как глобал для legacy-шаблонов и inline-обработчиков.
// Через год, когда templates переедут на ES-модули, этот блок удалим.
declare global {
    interface Window {
        Dolg?: {
            UnionFind: { create: typeof createUnionFind; portKey: typeof portKey };
            version: string;
        };
    }
}

window.Dolg = {
    UnionFind: { create: createUnionFind, portKey },
    version: '0.1.0',
};

export { createUnionFind, portKey };
