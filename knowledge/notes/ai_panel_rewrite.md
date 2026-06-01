# AI Assistant Panel — план переписывания

Текущая панель в `Dolg_APP/templates/tools/simulation.html` (~600 строк HTML+CSS+JS).
Pain-points от пользователя (2026-05-26):

1. **Sources и ML-техданные** забивают чат: `legal_source:all_about_circuits_textbook — All About Circuits Textbook (https://...)`
2. **Нет collapsible/folding** секций — всё видно сразу
3. **Чат узкий** относительно остальных блоков
4. **Нет гибкости под пользователя** — нельзя настроить layout

## Главный принцип

Layout должен быть **modular + persistent**: каждый блок (чат, pipeline, контекст,
quick actions, sources) — отдельный виджет с возможностями drag / resize / collapse / hide.
Состояние сохраняется в localStorage per-user.

## 4 архитектурных варианта (для compose)

### Mock A — Chat-first + collapsible all

```
┌────────────────────────────────────────┐
│ 🤖 DOLG AI                 ⚙ ⛶ ✕       │
├────────────────────────────────────────┤
│ ▶ Pipeline (DRC++ · След. компонент)   │  ← collapsed по умолчанию
│ ▶ Контекст схемы (26/37 · GND ✓)       │  ← collapsed
├────────────────────────────────────────┤
│                                        │
│  💬 Чат                                 │  ← 85% высоты
│                                        │
│   Вы: Что измерить?                    │
│   AI: для делителя Vout = 2.88 В       │
│        🔗 источники (3)  ⚡ actions (4) │  ← collapsed pill-кнопки
│                                        │
├────────────────────────────────────────┤
│ [+ Tools]  [Опишите задачу...] [➤]     │  ← + dropdown с инструментами
└────────────────────────────────────────┘
```

**Плюсы**: чат огромный, минимальный визуальный шум, как ChatGPT/Claude.
**Минусы**: pipeline и контекст по 2 клика далеко.

### Mock B — Tabbed

```
┌────────────────────────────────────────┐
│ 🤖 DOLG AI                 ⚙ ⛶ ✕       │
├────────────────────────────────────────┤
│ [💬 Чат] [📊 Анализ] [🧠 Pipeline] [🔗] │  ← 4 tab'а
├────────────────────────────────────────┤
│                                        │
│  Активная вкладка занимает всё         │  ← 90% высоты
│                                        │
│                                        │
├────────────────────────────────────────┤
│ [Опишите задачу.............] [➤]      │
└────────────────────────────────────────┘
```

**Плюсы**: чёткая иерархия, каждая вкладка получает полное место.
**Минусы**: переключение между tabs тратит фокус; нельзя одновременно видеть чат + контекст.

### Mock C — Sidebar split (Cursor-like)

```
┌────────────────────────────────┬───────┐
│                                │ Tools │
│       💬 Чат (70% width)       │       │
│                                │ ► DRC │
│  Вы: ...                       │ ► Ctx │
│  AI: ...                       │ ► Src │
│                                │       │
├────────────────────────────────┤       │
│ [Опишите задачу........] [➤]   │       │
└────────────────────────────────┴───────┘
```

**Плюсы**: всё одновременно на виду, привычно по IDE.
**Минусы**: требует широкой панели (>600 px), на мобильных не работает.

### Mock D — Modular grid (рекомендую) ⭐

```
┌──────────────────────────────────────────┐
│ 🤖 DOLG AI  [+ Виджет]   ⚙ ⛶ ✕            │
├──────────────────────────────────────────┤
│ ┌─💬 Чат─────────┐  ┌─📊 Контекст──┐      │
│ │                │  │ 26/37  GND✓  │      │
│ │  Вы: Что...    │  │ Делитель     │      │
│ │  AI: для...    │  └──────────────┘      │
│ │                │                        │
│ │                │  ┌─🧠 Pipeline──┐      │
│ │                │  │ ▶ DRC++       │      │
│ │                │  │ ▶ Next comp   │      │
│ │                │  │ ▶ Explain     │      │
│ │                │  └──────────────┘      │
│ │                │                        │
│ └────────────────┘                        │
│ [Опишите задачу...........] [➤]          │
└──────────────────────────────────────────┘
```

**Плюсы**: максимальная гибкость, каждый виджет drag/resize/hide, layout сохраняется.
**Минусы**: больше кода (~2× больше JS), сложнее на маленьких экранах.

## Архитектура реализации (Mock D, рекомендуемая)

### HTML (компоненты-виджеты)
- `<div class="ai-widget" data-widget-id="chat">` — каждый виджет имеет id
- `<div class="ai-widget__header">` — drag-handle + collapse-toggle + close
- `<div class="ai-widget__body">` — реальный контент
- `<div class="ai-widget__resize">` — corner-handle

### CSS Grid → CSS вручную позиционирование
- `position: absolute; left/top/width/height` для каждого виджета
- Координаты сохраняются в localStorage `dolg.aipanel.layout.<widgetId>`
- Snap to grid (32 px) при drag/resize для opryadnosti

### JS архитектура

```javascript
const widgets = {
    chat:        { x: 0, y: 0, w: 320, h: 400, collapsed: false, visible: true },
    context:     { x: 340, y: 0, w: 200, h: 120, collapsed: false, visible: true },
    pipeline:    { x: 340, y: 140, w: 200, h: 200, collapsed: false, visible: true },
    sources:     { x: 0, y: 0, w: 200, h: 200, collapsed: true, visible: false },  // optional
};

// Загрузка layout из localStorage, fallback на default
function loadLayout() { ... }

// Сохранение при каждом drag/resize/collapse
function saveLayout() { ... }

// «+ Виджет» dropdown с hidden widgets — добавляет visible: true
function showWidget(id) { ... }
```

### Виджеты-минимум для MVP

1. **Chat** — input + сообщения (ядро)
2. **Context** — текущий разбор схемы (что показывает «Разбор схемы» сейчас)
3. **Pipeline** — DRC++ / След. компонент / Объясни (текущие dropdown'ы)
4. **Sources** — список источников из последнего ответа (collapsed по умолчанию)
5. **Quick actions** — pinned actions из последнего ответа

### Особые требования

- **Sources внутри ответа** — превратить в **🔗 N**-кнопку в углу сообщения. Клик
  открывает виджет Sources с deep-link на ту строку
- **ML-техданные** (`legal_source: ...`) — скрыть из видимого ответа полностью,
  выводить только через виджет Sources
- **Сообщения чата** должны переноситься по ширине, не вылезать
- **Авто-открытие виджетов** при первом упоминании: пользователь спросил
  «найди ошибки» → виджет Context auto-show

## Стек реализации

- **Vanilla JS** (без библиотек) — соответствует существующей кодовой базе
- **Pointer events** (mousedown/mousemove/mouseup) для drag/resize — уже есть
  в `_wireDragHandle` / `_wireResizeHandle` (см. `simulation.html` ~9400, использую
  для Floating Properties/Results окон)
- **localStorage** для persistence — уже используется
- **CSS Grid не нужен** — каждый виджет position: absolute с собственными
  координатами

## Объём работы

- HTML markup: ~150 строк (5 виджетов × ~30 строк)
- CSS: ~200 строк (один paint per widget + states collapsed/visible/dragging)
- JS логика: ~400 строк (layout state + drag/resize/collapse + persistence +
  миграция content из старого panel'а)
- Backend: 0 — все API endpoints `/api/ai/chat/`, `/api/ai/pipeline/...` остаются
  как есть, меняется только UI

**Итого ~750 строк, оценка 3-4 часа чистой работы**. Совместимо с уже существующими
функциями (renderText, applyQuickAction, refreshAiContext) — миграция через рефактор,
не переписывание.

## Выбор пользователя (2026-05-26)

✅ **Mock D — Modular grid** утверждён + дополнительное требование: **«максимальная
пользовательская настройка»**. Каждый user должен сам решать что показать и где
разместить. Это меняет план реализации:

### Дополнительные требования к Mock D

- **Add/remove виджетов** через dropdown «+ Виджет» в header — пользователь
  включает/выключает любой из 5+ виджетов
- **Drag/resize/collapse** каждого виджета — независимо
- **Preset-режимы** для быстрого переключения:
  - **«Минимум»** — только Chat
  - **«Стандарт»** — Chat + Context + Quick actions
  - **«Полный»** — Chat + Context + Pipeline + Sources + Quick actions
  - **«Пользовательский»** — сохранённая раскладка
- **Lock-layout-toggle** — кнопка 🔒 в header. Заблокирует drag/resize чтобы
  случайно не сдвинуть виджеты во время работы
- **Reset layout** — сброс к Стандарту, на случай если пользователь «уронил»
  все виджеты за границу экрана

### Дополнительные виджеты (опциональные)

- **Schematic preview** — мини-превью текущей схемы (svg от schemdraw), полезно
  при ответе AI про конкретные компоненты
- **Token usage counter** — для Pro, считает токены сессии Anthropic API
- **Session history** — список прошлых вопросов, клик → перейти к ответу

### Расширенные данные сохранения

```javascript
// localStorage 'dolg.ai-panel.layout'
{
    preset: 'custom',  // 'minimum' | 'standard' | 'full' | 'custom'
    locked: false,
    widgets: {
        chat:       { x: 0, y: 0, w: 320, h: 400, collapsed: false, visible: true },
        context:    { x: 340, y: 0, w: 200, h: 120, collapsed: false, visible: true },
        pipeline:   { x: 340, y: 140, w: 200, h: 200, collapsed: true,  visible: true },
        sources:    { x: 0, y: 420, w: 280, h: 100, collapsed: true,  visible: false },
        actions:    { x: 290, y: 420, w: 250, h: 100, collapsed: false, visible: true },
    },
}
```

## Следующие шаги

1. ✅ **Mock D утверждён** с максимальной кастомизацией
2. **Spike**: ~30 мин — построить базовый skeleton виджета (drag/resize/collapse). Если ок — продолжить
3. **Реализация**: ~3 часа последовательно: chat → context → pipeline → sources → polish
4. **Тестирование**: render-тест + ручная проверка drag в Chrome/Firefox
5. **Migration**: убедиться что старый panel закомментирован, не удалён сразу (rollback safety)

## Что НЕ переписывать

- **Backend API endpoints** (`/api/ai/chat/`, `/api/ai/pipeline/anomalies/`,
  `/api/ai/pipeline/explain/`, `/api/ai/pipeline/recommend/`, `/api/ai/context/`) — работают,
  ломать нет смысла
- **Thinking + typewriter animation** — только что добавлены, рабочие
- **History persistence** (`histories[currentMode]` + sessionStorage) — рабочее
- **CSRF + guest-mode handling** — рабочее
- **Quick actions backend mapping** (`actionLabel`, `actionPrompt`, `applyQuickAction`) — рабочее
