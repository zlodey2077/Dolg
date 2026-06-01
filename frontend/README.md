# DOLG Frontend (TypeScript + Vite)

Строит ES2020-bundle из `src/*.ts` модулей и кладёт его в `../shop/static/lib/dolg/index.js`.
Подключается одним `<script>` в `simulation.html`.

## Зачем

Главный шаблон симулятора — `Dolg_APP/templates/tools/simulation.html` (~7600
LOC), почти всё JS inline. Постепенно переносим логику в TS-модули с
типизацией и unit-тестами на Vitest. Это снижает риск регрессий и упрощает
рефакторинг.

## Что уже мигрировано

| Модуль                    | TS-версия                  | Статус |
|---------------------------|----------------------------|--------|
| Union-Find для узлов SPICE| `src/union-find.ts`        | ✅ proof of concept |
| scheme-netlist (целиком)  | —                          | ⏳ план |
| scheme-3d (Three.js wrap) | —                          | ⏳ план |
| scheme-lab (instruments)  | —                          | ⏳ план |
| simulation.html inline JS | —                          | ⏳ план |

## Запуск

```bash
cd frontend
npm install                 # 1 раз
npm run build               # сборка → ../shop/static/lib/dolg/index.js
npm run dev                 # watch-режим (на каждое сохранение)
npm test                    # vitest
npm run type-check          # tsc --noEmit (без сборки)
```

## Стратегия миграции

1. Каждый круг — переписываем 1-2 .js → .ts, добавляем тесты в `tests/`.
2. Сборка идёт в `iife` формат и публикует API в `window.Dolg.*` — это даёт
   обратную совместимость с inline-обработчиками (`onclick="..."`) в
   шаблонах. Шаблоны постепенно переходят на новый namespace.
3. Когда все JS-модули из `shop/static/simulation/` мигрированы — удаляем
   их и заменяем единственным `<script src="lib/dolg/index.js">`.
4. Финальный шаг — extract simulation.html inline-script в TS-файлы и
   рендерить через `{% include 'simulation_root.html' %}` + один script.

## Принципы

- **No breaking changes**: пока миграция не завершена, оригинальные .js
  работают параллельно. Шаблоны не трогаем без необходимости.
- **strict mode** (см. tsconfig.json) — `noUncheckedIndexedAccess`,
  `noImplicitReturns`, `noUnusedLocals/Parameters`. TypeScript сразу ловит
  баги «X is undefined», которые мы исправляли руками в JS.
- **Vitest** + jsdom — закрывает дыру в JS-coverage (раньше 0% покрытия,
  только Django-тесты на Python-стороне).

## Что не делаем сейчас

- **Полная миграция** — это 1-2 недели, не «фикс на месте»
- **Изменение формата bundle** (ESM, CDN) — IIFE проще для инлайн-шаблонов
- **TypeScript для Three.js моделей** — отдельная задача после migration
  основного `scheme-3d.js`
