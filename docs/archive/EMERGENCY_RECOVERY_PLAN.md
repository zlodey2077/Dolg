# Экстренный план восстановления (2026-05-31)

**Контекст:** `simulation.html` повреждён до 797КБ нулевых байт (диск/sync сбой). Юзер откатил файл к 29 мая. Все остальные файлы целы.

**Объём:** ~50 точечных правок в одном файле `Dolg_APP/templates/tools/simulation.html`. Не нужно восстанавливать backend/JS-модули — они сохранились.

**Метод:** строго поэтапно, после каждого этапа `django check` + smoke load `/simulation/`. Если падает — откат этапа.

---

## Этап 0 — Подготовка (15 мин)

1. Сделать backup восстановленного файла:
   ```powershell
   Copy-Item Dolg_APP/templates/tools/simulation.html Dolg_APP/templates/tools/simulation.html.20260529.bak
   ```
2. Запустить runserver, открыть `/simulation/` — убедиться что 200 OK, базовый функционал работает.
3. Включить FAST_TESTS=1 для скорости.

---

## Этап 1 — P0 Критические баги (1-2 часа)

Без этих фиксов симулятор частично сломан.

### 1.1. Multi-sheet bug

`rebuildSheetTabs`: использовать `Set([0, currentSheet])` вместо `Set([0])`. Без фикса новый «+ Лист» не отображается пока пустой.

### 1.2. Status-bar не обновляется при выделении

В `selectComponent(id)` и `selectConnection(index)`: добавить `if (typeof updateStatusBar === 'function') updateStatusBar();`. Иначе поле «выделено: X» пустое после клика.

### 1.3. Lab data flow → Scope чёрный после ▶ Запуск

В `runSimulation` (обе ветки — ngspice success + JS-MNA success):

```js
window._lastSimResultForLab = r.result;
window._lastSimResult = r.result;
// ... renderSimResult ...
if (window.DolgLab) { try { window.DolgLab.refresh(); } catch (e) {} }
```

Без этого Лаб не получает данные → scope/multimeter висят на заглушках.

### 1.4. sheet_index в путях добавления компонента

В **5 местах** добавления компонентов: `addComponentFromContext` (ПКМ), node-creator, `duplicateSelectedComponent`, `pasteFromClipboard`. Добавить `sheet_index: currentSheet` в объект компонента. Иначе на «+ Лист» новые элементы попадают на Лист 1.

### 1.5. fitToContent + shortcut

Восстановить `function fitToContent()` (compute bbox, snap zoom 0.08-1.5, center). Биндинг в `onKeyDown`: Ctrl+0 и F.

### 1.6. ngspice timeout 15s → 4s

В `runOnNgspice`: `setTimeout(..., 4000)`. Чтобы юзер не ждал 15 секунд zip-fallback.

**После этапа 1:** ▶ Запуск работает, scope обновляется, листы переключаются.

---

## Этап 2 — P1 Большие функции (4-5 часов)

### 2.1. Voltage badges на канвасе после симуляции

- `_drawVoltageBadges(ctx)` — рисует cyan/yellow/red badges на портах с дедупликацией по net'у
- `_getComponentVoltageRating(comp)` — defaults: LED 5В, capacitor 25В, resistor 250В и т.д.
- `_fmtBadgeVoltage(v)` — формат «247mV», «5.00V», «150.0V»
- `_roundRect(ctx, x, y, w, h, r)` — helper
- В `drawCanvas` — вызов после рендера компонентов
- Toggle «👁 V» в верхнем toolbar + `toggleVoltageBadges` + `_voltageBadgesVisible` через localStorage

### 2.2. Net labels (KiCad-стиль)

- `setWireNetLabel()` — prompt с UPPERCASE+ASCII+16char
- `_drawNetLabel(pts, label)` — cyan-бэйдж на самом длинном сегменте
- Вызов в `drawConnectionPath` после стрелок токов
- ПКМ context-menu-wire: кнопка «🏷 Имя net'а»

### 2.3. Multi-select Ctrl+A/C/V/D

- `selectAllComponents()` — `selectedComponentIds.clear()` + добавить все на текущем листе
- `copySelectedToClipboard()` — JSON.stringify в `_multiClipboard`
- `pasteFromClipboard()` — restoid map id→newId + offset + sheet_index: currentSheet
- В `onKeyDown` Ctrl+modifier block: ловить A/C/V/D + кириллица ф/с/м/в

### 2.4. Inline net-label edit (двойной клик)

- В `canvas.addEventListener('dblclick'...)` после ветки comp: если `getConnectionAtPosition >= 0`, открыть input
- `_openInlineNetLabelEditor(clientX, clientY)` — fixed-position cyan input с z-index 99999
- Enter сохраняет, Esc отменяет

### 2.5. Wire hit-detection (clamp к сегменту)

- `pointToSegmentDistance(px, py, x1, y1, x2, y2)` — proper segment dist
- В `getConnectionAtPosition`: использовать новую функцию + adaptive tolerance `Math.max(4, Math.min(12, 8/Math.max(zoom, 0.3)))`
- Best-match selection (наименьшее расстояние)

### 2.6. Cross-probing finding → канвас

- `_extractCompIdFromFinding(text)` — regex `\b(R|C|L|D|V|I|LED|Q|GND|SW)\d+\b` → находит comp по label
- `_renderFinding(text, severityClass)` — обёртка с data-comp-id + clickable class + подсказка
- `_crossProbeToCanvas(compId)` — _dolgDrcMarkers + panX/panY recalc + closeModal + notification
- В `showEngineeringReview` finding render → использовать `_renderFinding` для errors/warnings
- CSS `.er-finding-clickable` — hover slide + cyan-glow

### 2.7. Score breakdown drill-down

- В Review summary `<details class="er-breakdown-details" open>` с rows для errors/warnings/faults/risks
- Каждая row с `data-jump-tab="errors"` — клик переключает tab + scroll
- CSS `.er-breakdown-row.er-clickable:hover` background highlight

### 2.8. Onboarding overlay

- HTML `<div id="dolg-onboarding-overlay">` в конец template (перед `{% endblock %}`)
- 6-карточный grid с demo проектами (fetch через PROJECTS_API.list filter is_demo)
- Кнопка «Пустой канвас →» + checkbox «Больше не показывать»
- `localStorage.dolg.onboarded` гейт
- Skip для IS_GUEST_DEMO / IS_SHARED_VIEW / есть открытый проект

### 2.9. runQuickDRC (frontend DRC)

- 15 правил: GND, source, ports, single-connection, parallel batteries, LED-no-R, voltage-rating, dup designator, R≤0, unlabeled, unbound, LED-chain-no-CC, inductive-no-diode, isolated GND, duplicate wires
- `_dolgDrcMarkers` Map + анимированный halo через `_drawDrcMarkers` в drawCanvas
- Кнопка «🔍 DRC» в toolbar (заменить старую Review) — `onclick="runQuickDRC(); showEngineeringReview();"`

**После этапа 2:** все P1-фичи восстановлены, плотный wow-эффект.

---

## Этап 3 — P2 Среднее (3-4 часа)

### 3.1. ПКМ-палитра расширения

- В `context-menu-empty` добавить: NPN транзистор, PNP транзистор, Узел (Node), ⟳ Источник тока (I)
- (`addComponentFromContext` уже работает с этими типами после Этапа 1)

### 3.2. Current source: визуальный рендер

- `drawCurrentSource(x1, y1, x2, y2)` — круг 12px + стрелка внутри + «+/−» подписи
- В `drawComponent` switch: `case 'current_source': drawCurrentSource(...)`
- `getComponentLabel`: добавить `current_source: 'I'`
- `getComponentPorts`: `current_source: [{id:'+'...}, {id:'-'...}]`
- `getComponentName`: `current_source: 'Источник тока'`

### 3.3. Mirror компонента

- `mirrorSelectedComponent(axis)` — flip портов по X/Y + waypoints reset
- ПКМ context-menu-component: кнопки «↔ Зеркало гориз.» / «↕ Зеркало верт.»

### 3.4. Probe через ПКМ на проводе

- `probeThisWire()` — получить netId из `_lastPortNetMap` или `conn.net_label`, выставить в multimeter+scope через DolgLab callback
- ПКМ context-menu-wire: кнопка «📍 Probe этот net»

### 3.5. Sim cache (мгновенный re-run)

- `_simCache = new Map()`, LRU 8 записей
- `_hashScheme(scheme, analysis)` — FNV-1a hash JSON-серилизации (только relevant поля)
- В `runSimulation` start: проверка кэша → если hit, return из кэша
- В обоих success-ветках: store cache

### 3.6. Review history sparkline

- В `showEngineeringReview` после render: `localStorage('dolg.reviewHistory')` last 5
- Sparkline + delta «↑/↓ +N от прошлой проверки» под score ring
- 7-day expiry

### 3.7. Smart auto-route при move

- `_dragStartCompX/Y` + `_dragStartWaypoints` Map при mousedown
- `SMART_REROUTE_THRESHOLD = 50` px
- В drag move: если dist < threshold → сдвигать waypoints на delta, иначе reset

### 3.8. Lab init + visibility

- Вынести config из `open()` в `_buildLabBindings()`
- `initLabIfNeeded()` public + вызов из migration code
- `_setupLabResizeObserver` + `_resyncLabCanvases` с devicePixelRatio
- `_setupLabToggles` для 📺/🔢/〰

### 3.9. Bode plot -3dB cutoff marker

- В `drawAcGraph` `drawPanelBase` для magnitude panel: найти max dB, найти точку -3 dB через линейную интерполяцию
- Жёлтый пунктир от точки до X-axis + подпись «−3 dB @ X кГц»

**После этапа 3:** все P2-фичи готовы.

---

## Этап 4 — P3 Polish (2-3 часа)

### 4.1. Top-toolbar обновления

- Удалить кнопку «📦 Компоненты» через `style="display:none"` (юзер: есть в ПКМ)
- Добавить «🎬 3D», «👁 V», «🔍 DRC», «🎲 Monte Carlo» (если ещё нет)

### 4.2. Dropdown event-delegation (hamburger fix)

- В `_initToolbarDropdowns` заменить forEach по кнопкам на `document.addEventListener('click', ..., true)` (capture phase)
- Сразу `e.preventDefault()` + `e.stopPropagation()`

### 4.3. CSS-переменные для контейнера

- На `.simulator-container`: `--sim-gap`, `--sim-padding`, `--sim-radius`, `--sim-margin-top`, `--sim-min-height: auto`, `--sim-toolbar-height`, `--canvas-min-height: 600px`, `--analysis-default: clamp(420px, 50vh, 560px)`
- `border: 1px solid rgba(0, 212, 255, 0.45)` (было 2px + glow)
- `overflow: visible` (было hidden — обрезало dropdown'ы)
- `min-height: var(--sim-min-height)` (было фикс 1000px)

### 4.4. Удалить legacy media queries

- `@media (max-width: 1400px)` и `@media (max-width: 1100px)` которые переопределяли `grid-template-columns` на 3-колонный layout → удалить полностью

### 4.5. Drag-resize handles

- `.sim-dock-resize::after { content: '⋯' }` + `.analysis-bottom-resize::after` — индикатор по центру
- Subtle gradient background всегда виден (не только hover)

### 4.6. Lab cards layout v3

- `.analysis-bottom-content .dolg-lab-grid`: `grid-template-areas: "scope gen" "scope mm"` `grid-template-columns: 2fr 1fr` `grid-template-rows: minmax(0, 0.75fr) minmax(0, 1.25fr)`
- Card overflow: hidden, padding 5-7px
- Container queries для `.dolg-lab-mm`: `container-type: inline-size`
- `.dolg-lab-mm-display`: `font-size: clamp(18px, 12cqi, 48px)`
- `.dolg-lab-gen-preview { display: none }` (упрощение генератора)
- Удалить `.dolg-lab-body--docked .dolg-lab-grid` override который перебивает

### 4.7. Hamburger collapse

- CSS: `.hm-section.is-collapsed > .hm-section-body { display: none }` + `::after` rotation
- `_initHamburgerCollapse()` JS + вызов в DOMContentLoaded
- localStorage `dolg.hm.collapsed`

### 4.8. UI dup audit

- Из context-menu-empty убрать: «Очистить холст», «Сохранить схему», «Загрузить схему», «Импорт SPICE» (есть в hamburger)
- Заменить на единую «☰ Все настройки» внизу

### 4.9. Cache-bump всех скриптов

- В верхних `<script src=…?v=…>` обновить на `?v=20260531-recovery1`

### 4.10. Кнопка Review/MC в toolbar (если их нет)

- `<button class="tool-btn tool-btn--review" onclick="runQuickDRC(); showEngineeringReview();">🔍 DRC</button>`
- `<button class="tool-btn tool-btn--mc" onclick="runMonteCarlo()">🎲 Monte Carlo</button>`

**После этапа 4:** UI полностью соответствует версии до сбоя.

---

## Этап 5 — Финальный smoke (30 мин)

1. `python -m django check` — 0 issues
2. `node -c` на extracted JS — 0 errors
3. Открыть `/simulation/`:
   - Пустая схема → onboarding overlay
   - Добавить делитель напряжения через ПКМ → ▶ Запуск → voltage badges + Lab data
   - DRC: ПКМ «Очистить холст»? — должно быть нету (убрали). Hamburger «🧹 Очистить» — есть
   - Двойной клик по проводу → inline net-label
   - Перетащить компонент 5px → провода тянутся; 100px → пересчитываются
   - Ctrl+A → все выделены; Ctrl+C → Ctrl+V → дубликат группы
   - Ctrl+0 / F → fit-to-content
   - Multi-sheet: «+ Лист» → переключение → ПКМ добавить R → R на новом листе
4. Cache-bump на финальный `?v=20260531-recovery-final`
5. Snapshot файла в `Dolg_APP/templates/tools/simulation.html.20260531.recovered`

---

## Альтернатива: ускоренное восстановление

Если **критически** срочно (защита завтра), можно сделать **только Этап 1 + 2** (P0 + P1). Это 5-7 часов работы, восстанавливает 80% важного функционала. P2/P3 после защиты.

---

## Связано

- `docs/IMPROVEMENT_PLAN_20260531.md` — план который мы только что выполнили (источник правок)
- `docs/SIMULATOR_LIVENESS_PLAN.md` — предыдущий план (часть восстановлений оттуда)
- `docs/ACCUMULATED_ISSUES_2026-05-30.md` — багаудит (большинство пунктов восстанавливаются вместе с фиксами)
- `scripts/expand_drc_rules.py`, `finalize_drc_rules.py`, `enable_drc_rules.py` — audit trail для DRC (уже применены к default_rules.json, не нужно перезапускать)
