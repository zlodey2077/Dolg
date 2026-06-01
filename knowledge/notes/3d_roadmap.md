# 3D-моделирование в DOLG — дорожная карта

Цель: превратить текущий 3D PCB-viewer ([scheme-3d.js](../../shop/static/simulation/scheme-3d.js), ~1680 строк, Three.js, 9 типов корпусов, процедурная подложка) в полноценный инструмент проектирования печатных плат — от расширения отображения до 3D-редактора с routing и связкой с симуляцией DOLG.

Подложка для исследовательской части — [3d_research.md](3d_research.md): академические источники, Three.js модули, сравнение open-source решений (KiCanvas, KiCad 3DViewer, Tracespace, Flux.ai) и форматы экспорта (GLB, STEP, IDF).

Карта разбита на 5 фаз. Фазы 1–3 — фундамент для всего остального и должны идти по порядку; Фазы 4–5 можно тасовать. Размеры: **XS** = часы, **S** = 1–2 дня, **M** = 3–7 дней, **L** = ~2 недели, **XL** = ~месяц чистого времени.

---

## Фаза 1 — Подготовка фундамента (S/M, ~1–2 недели)

Привести текущий монолит в форму, пригодную для расширения. Без этого Фаза 2+ превратится в спагетти.

| № | Задача | Размер | Зачем |
|---|---|---|---|
| 1.1 | **Расщепить scheme-3d.js на модули** — `scene-manager.js`, `component-library.js`, `layer-renderer.js`, `exporter.js`, `controls.js` через ES6 modules или namespace-объекты | M | Без этого все следующие фичи смешаются с rendering-кодом |
| 1.2 | **`InstancedMesh` для повторяющихся примитивов** (via, 0805 резисторов, пин-headers) | S | −100–500× draw-calls для крупных плат |
| 1.3 | **GLB-экспорт сцены** через `THREE.GLTFExporter({binary:true})` | S | Вставка 3D в дипломный отчёт через `<model-viewer>`, sharing |
| 1.4 | **`DirectionalLight` + baked AO** вместо point-shadows | S | Cost рендера −5–6× (discoverthreejs.com) |
| 1.5 | **`enableDamping=true` в OrbitControls + zoomSpeed/rotateSpeed config** | XS | Плавность вращения, profess-feel |
| 1.6 | **3D-снимок для отчёта review** — рендерить GLB+PNG при `build_design_review`, кэшировать в `media/projects/<id>/3d_thumbnail.png` | M | Закрывает backlog-пункт «миниатюра в PDF» из плана typed-mixing-hammock |

---

## Фаза 2 — Реальные компоненты и слои (M/L, ~2–4 недели)

Превратить процедурные коробочки в реальные модели и показать слои печатной платы.

| № | Задача | Размер | Зачем |
|---|---|---|---|
| 2.1 | **Библиотека real STEP-моделей** — топ-20 footprint'ов (SOIC-8, DIP-14, TQFP, SOT-23, 0805/0603, JST, USB-C, axial THT). Скачать с [SnapEDA](https://www.snapeda.com/)/[Ultra Librarian](https://www.ultralibrarian.com/), конвертировать оффлайн FreeCAD CLI в GLB, положить в `shop/static/3d_models/` | L | Главный визуальный апгрейд — «дипломный wow» |
| 2.2 | **`GLTFLoader` с fallback на процедурную модель** | S | Если для footprint нет реальной — рисуем коробку |
| 2.3 | **Multi-layer PCB stack-up** — top/bottom + inner-1/inner-2, толщина FR4, шёлкография, маска, медь. Каждый слой — отдельная Mesh-группа | M | Без этого «3D» это просто плоская картинка с торчащими компонентами |
| 2.4 | **Toggle верх/низ платы** (компоненты сверху/снизу, авто-flip) | S | Реальные платы двусторонние |
| 2.5 | **Прозрачность слоёв** — слайдер opacity для каждого слоя, или solo-mode «показать только медь» | S | Учебная фича: посмотреть, как соединяются дорожки внутри |
| 2.6 | **Layer animation (explode view)** — слои разъезжаются по нормали для презентации | S | Killer-кадр для диплома, ничего не ломает |
| 2.7 | **Cross-probing 2D↔3D** — клик в схеме `/simulation/` → подсветка компонента в 3D (через postMessage между iframe или общий store) | M | Связь модулей DOLG, реальная инженерная фича |

---

## Фаза 3 — 3D-редактор (L/XL, ~3–6 недель)

Превратить viewer в редактор: пользователь двигает, поворачивает, размещает компоненты прямо в 3D.

| № | Задача | Размер | Зачем |
|---|---|---|---|
| 3.1 | **Raycaster + click-to-select** — выбор компонента по клику, outline через `THREE.OutlineEffect` или цветную обводку | S | Без selection редактирование невозможно |
| 3.2 | **Drag-and-drop размещение на плате** — `DragControls` или custom raycaster onto board plane | M | Базовое placement, как у KiCad PCB editor |
| 3.3 | **Inspector panel выбранного компонента** — координаты X/Y/Z, rotation, layer (top/bot), footprint-инфо | M | Должна быть таблица с числовыми полями |
| 3.4 | **Rotate с шагом 45°/90° + snap к сетке 0.1мм/1мм** | S | Обязательно для realistic PCB layout |
| 3.5 | **Undo/Redo стек 3D-сцены** (по образцу [simulation.html](../../Dolg_APP/templates/tools/simulation.html) `snapshotScheme`) | M | Серьёзный редактор без undo не годится |
| 3.6 | **Сохранение PCB-layout в БД** — модель `PCBLayout` с JSON: components[{footprint, x, y, rot, layer}] + board outline + stack-up | M | Нужно для проекта, не временной демки |
| 3.7 | **Footprint-палитра** — sidebar с draggable-карточками компонентов из каталога DOLG, drag → drop на плату | M | Логичный мост: каталог товаров → 3D-проектирование |
| 3.8 | **Импорт BOM из schematic** — взять components из `scheme_data`, разложить как «to be placed», пользователь расставляет | M | Связка с редактором схем: «нарисовал схему → переходишь в 3D и раскладываешь» |

---

## Фаза 4 — Routing и анализ (L/XL, ~4–8 недель)

Финальный шаг к полноценному EDA-инструменту. Можно делать частями, не обязательно все.

| № | Задача | Размер | Зачем |
|---|---|---|---|
| 4.1 | **Manual trace routing** — рисование дорожек в 3D, привязка к нетам из netlist, переход между слоями через via | L | Без routing PCB-редактор это симулятор перетаскивания |
| 4.2 | **Online DRC: clearance, trace width, via size** — подсветка нарушений красным в реальном времени | M | Учебная роль высокая, требует геометрию из 4.1 |
| 4.3 | **Auto-router (Lee algorithm)** — простой, не production-grade, но идеален для обучения | L | Дипломная фича; можно представить как алгоритмическую главу |
| 4.4 | **Thermal map overlay** — связка с [simulation_analysis.py](../../Dolg_APP/services/simulation_analysis.py) FFT/MC: цветовая карта температуры компонентов на 3D-плате | M | Прямая связь с уже сделанной Pro-аналитикой DOLG, минимум кода |
| 4.5 | **Current density на дорожках** — после симуляции цвет дорожки = ток | M | Визуализация SI/PI для учебного диплома |
| 4.6 | **Mechanical clearance: import enclosure GLB** + проверка height conflict с компонентами | M | Mechanical-фича, отличает DOLG от «просто симулятора» |
| 4.7 | **Pick-and-place экспорт** — CSV с координатами для PCBA-производства | S | Practical real-world фича, легко делать |
| 4.8 | **Gerber→3D рендеринг настоящего PCB** — взять реальные Gerber-файлы и нарисовать дорожки 1:1 | XL | Использовать [Tracespace](https://github.com/tracespace/tracespace) парсер; альтернатива — взять [KiCanvas](https://github.com/theacodes/kicanvas) как embedded viewer |

---

## Фаза 5 — Дипломные / учебные / wow-фичи (S/M, в любое время)

Отдельная корзина — небольшие фичи с высоким wow-эффектом для защиты. Не зависят от Фаз 1–4 жёстко, но качество выше при их наличии.

- **AR-предпросмотр через `<model-viewer>`** (Google) — QR-код в дипломной презентации, экспонируешь плату на телефон в AR (требует 1.3 — GLB-экспорт)
- **Walk-through animation** — авто-облёт камеры по выбранной траектории с close-up на компонентах, экспорт в MP4 через `CCapture.js`
- **3D-обучающие задания** — «соберите делитель напряжения в 3D», score за корректность; интеграция с `knowledge/learning/`
- **Сравнение топологий** — split-view: схема ↔ PCB layout ↔ 3D ↔ симуляция (4 окна одновременно)
- **Stress-map при изгибе платы** — учебная демонстрация механики
- **Animation: assembly sequence** — компоненты падают на плату по очереди по reflow-профилю

---

## Рекомендуемый порядок (мой совет)

1. **Сначала Фаза 1 целиком** — она маленькая, но без неё расширение будет хаотичным.
2. Из **Фазы 2** взять 2.1 (real models), 2.3 (multi-layer), 2.4 (top/bottom toggle), 2.7 (cross-probing). Это даёт «настоящий» viewer.
3. Из **Фазы 3** взять минимум: 3.1 (select), 3.2 (drag), 3.3 (inspector), 3.5 (undo), 3.6 (save). Это базовый редактор.
4. **Фазу 4.4 (thermal map)** сделать пораньше — она интегрируется с уже готовой Pro-аналитикой и даёт сильный демо-кадр.

---

## Архитектурные ориентиры

- **Модульный принцип**: каждая Фаза добавляет новый файл/модуль рядом с `scheme-3d.js`, а не пухнет внутри него. Цель — к концу Фазы 1 иметь 4–5 файлов вместо одного.
- **Источник истины — Django-модель** (Фаза 3.6 — `PCBLayout`). 3D-сцена это view, а не state. Сохранение через тот же `views.py` API, что и `SchematicProject`.
- **Связь с симулятором** — через postMessage или общий global store; не делать тесную связь через прямые вызовы JS-функций.
- **Production-grade образец — [KiCanvas](https://github.com/theacodes/kicanvas)** (MIT, vanilla TypeScript). Прямая модель для архитектуры «парсер → scene graph → renderer → exporter».
- **Footprint-библиотека**: оффлайн-pipeline `STEP → FreeCAD CLI → GLB`, складывать в `shop/static/3d_models/<footprint_name>.glb`, грузить `GLTFLoader` по имени.

---

## Что не входит (анти-scope)

- Реальный production-routing (autorouter mass-market уровня) — Фаза 4.3 даёт обучающую версию, не более.
- Полная mechanical-симуляция (FEM, thermal CFD) — DOLG это EDA, не SolidWorks.
- Поддержка всех KiCad/Eagle/Altium форматов — оставляем `.kicad_pcb` + Gerber как максимум.
- 3D-печать корпусов как самостоятельная фича — только импорт готовых STL/GLB enclosure для clearance-проверки.
