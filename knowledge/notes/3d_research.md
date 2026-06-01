# 3D PCB-viewer DOLG — библиография и техническая база

Рабочий конспект для дипломного текста и расширения `shop/static/simulation/scheme-3d.js`.
Собран на 2026-05-25. Все ссылки проверены агентом-исследователем.

## Часть A. Аннотированный список ссылок

### 1. Дипломная библиография (академические/инженерные источники)

- [Three-Dimensional Visualization of Product Manufacturing Information in a Web Browser Based on STEP AP242 and WebGL (2025)](https://www.researchgate.net/publication/396402745_Three-Dimensional_Visualization_of_Product_Manufacturing_Information_in_a_Web_Browser_Based_on_STEP_AP242_and_WebGL) — Прямой пример браузерной 3D-визуализации инженерных моделей из STEP, прецедент для главы про экспорт DOLG.
- [DECODE-3DViz: Efficient WebGL-Based High-Fidelity Visualization (2025, NCBI PMC)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12701164/) — LOD и chunk-streaming для крупных WebGL-сцен; обоснование производительной части DOLG.
- [Interactive WebGL-based 3D Visualizations for Situated Mathematics Teaching (IEEE Xplore)](https://ieeexplore.ieee.org/document/6671038) — Цитируемое доказательство дидактической ценности WebGL-визуализаций.
- [Using WebGL in Developing Interactive Virtual Laboratories for Distance Engineering Education (ASEE peer-reviewed)](https://peer.asee.org/board-60-using-webgl-in-developing-interactive-virtual-laboratories-for-distance-engineering-education.pdf) — Методология построения интерактивных 3D-лабораторий именно для engineering-курсов.
- [Improving Effectiveness Of E-Learning In Maintenance Using Interactive 3D (arXiv)](https://arxiv.org/pdf/0909.4202) — Эмпирические данные о снижении времени обучения и росте эффективности при интерактивном 3D.
- [An Evaluation of HTML5 and WebGL for Medical Imaging Applications (NCBI PMC)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6136584/) — Сравнение HTML5/WebGL-подходов; полезно для оправдания технологического выбора (browser-first, без плагинов).
- [A Survey of Research in Large Language Models for Electronic Design Automation (arXiv 2501.09655)](https://arxiv.org/pdf/2501.09655) — Современный обзор EDA-инструментария, ставит контекст «где сейчас находится EDA».
- [Enhancing engineering student engagement through WebVR and wearable sensors (Springer, 2025)](https://link.springer.com/article/10.1007/s43621-025-01436-x) — Поддержка тезиса о вовлечённости студентов через web-3D.

### 2. Three.js / WebGL документация

- [Three.js Docs — root](https://threejs.org/docs/) — Точка входа в API (Scene, Mesh, BufferGeometry, материалы).
- [Three.js Docs — InstancedMesh](https://threejs.org/docs/pages/InstancedMesh.html) — Ключ к снижению draw-calls при рендере 50–200 однотипных корпусов.
- [Three.js Docs — OrbitControls](https://threejs.org/docs/pages/OrbitControls.html) — Официальная страница того контрола, который уже используется в `scheme-3d.js`.
- [Three.js Docs — GLTFExporter](https://threejs.org/docs/pages/GLTFExporter.html) — API для экспорта текущей сцены в `.glb` (см. раздел 4 ниже).
- [Three.js Example — exporter gltf](https://threejs.org/examples/misc_exporter_gltf.html) — Рабочий пример экспорта, готовый шаблон для DOLG.
- [Discover three.js — Tips and Tricks](https://discoverthreejs.com/tips-and-tricks/) — Современный гайд по перфомансу (lights, shadows, BufferGeometry).
- [Discover three.js — Built-In Geometries](https://discoverthreejs.com/book/first-steps/built-in-geometries/) — Каталог геометрий, которые уже используются в `scheme-3d.js` (Box/Cylinder).
- [Three.js Instances — Codrops, 2025](https://tympanus.net/codrops/2025/07/10/three-js-instances-rendering-multiple-objects-simultaneously/) — Свежий практический гайд по instancing.
- [Three.js Journey — Bruno Simon](https://threejs-journey.com/) — Курс с разделами по продвинутым сценам и оптимизации.
- [WebGL Performance Optimization — PixelFreeStudio](https://blog.pixelfreestudio.com/webgl-performance-optimization-techniques-and-tips/) — Сводка по LOD, normal maps, draw-calls.

### 3. Open-source 3D-визуализация PCB

- [KiCanvas — github.com/theacodes/kicanvas](https://github.com/theacodes/kicanvas) — Браузерный viewer KiCad на vanilla TypeScript + Canvas/WebGL, MIT. Прямой архитектурный референс.
- [KiCanvas — официальный сайт](https://kicanvas.org/) — Демо и embedding API.
- [KiCad — New 3DViewer (kicad.org)](https://www.kicad.org/blog/2016/07/New-3DViewer/) — Описание OpenGL-рендера KiCad, модель «WRL для просмотра + STEP для MCAD».
- [Tracespace — github.com/tracespace/tracespace](https://github.com/tracespace/tracespace) — MIT-лицензированный Gerber-renderer (2D SVG); парсер Gerber можно переиспользовать.
- [Mayhew Labs 3D Gerber Viewer](https://mayhewlabs.com/3dpcb) — Браузерный 3D Gerber viewer (HTML5+WebGL); UX-референс.
- [EasyEDA — 3D Preview docs](https://prodocs.easyeda.com/en/pcb/view-preview-3d/) — Что показывает коммерческий web-EDA в 3D-режиме.
- [Flux.ai — design PCBs](https://www.flux.ai/) — Production-grade web-EDA на react-three-fiber.
- [SnapMagic Search / SnapEDA](https://www.snapeda.com/) — Бесплатные STEP-модели миллионов компонентов.
- [Ultra Librarian — 3D STEP models](https://www.ultralibrarian.com/cad-vendors/3d-step-models/) — 16M+ верифицированных моделей, 30+ форматов.

### 4. Форматы 3D и экспорт

- [glTF 2.0 Specification — Khronos Registry](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html) — Каноническая спецификация, теперь ISO/IEC 12113:2022.
- [glTF — Runtime 3D Asset Delivery (Khronos)](https://www.khronos.org/gltf/) — Обзор формата, GLB-расшифровка.
- [Three.js GLTFExporter API](https://threejs.org/docs/pages/GLTFExporter.html) — Параметры `{ binary: true }` для `.glb`-экспорта.
- [Intermediate Data Format — Wikipedia](https://en.wikipedia.org/wiki/Intermediate_Data_Format) — Описание EMN/EMP-структуры IDF для ECAD↔MCAD-моста.
- [Unlocking PCB Board Outlines: IDF vs DXF — Siemens (2025)](https://blogs.sw.siemens.com/xcelerator-academy/2025/02/26/unlocking-pcb-board-outlines-idf-vs-dxf-explained/) — Современное сравнение, объясняет, когда выбирать IDF vs DXF vs STEP.
- [ConvertMesh — 3D File Formats Guide](https://www.convertmesh.com/formats) — Таблица STL/OBJ/3MF/STEP/glTF с use-cases.

---

## Часть B. Конспект ключевых тем

### 1. Дипломная позиционирование

Литература устойчиво подтверждает три тезиса, на которые удобно опереться в тексте диплома. Во-первых, WebGL стал де-факто платформой для интерактивных 3D-визуализаций инженерных моделей в браузере — свежие работы 2025 года описывают рендер STEP AP242 прямо в браузере (ResearchGate, *Three-Dimensional Visualization … STEP AP242 and WebGL*) и LOD-стратегии для крупных сцен (DECODE-3DViz). Во-вторых, для образования эффект документально измерен: ASEE-paper по WebGL-лабораториям в дистанционном engineering-курсе, IEEE-публикация про обучение математике через WebGL и широко цитируемая arXiv-работа про e-learning maintenance с интерактивным 3D показывают сокращение времени обучения и рост вовлечённости. В-третьих, обзорные работы по EDA (arXiv 2501.09655) описывают тренд на «shift-left» и web-friendly инструменты — DOLG попадает в актуальный научный контекст.

Для библиографии практично взять 5–7 ссылок: одну про STEP+WebGL (доказательство feasibility), одну про LOD/перфоманс, две про образовательный эффект, одну обзорную по EDA, одну сравнительную (HTML5/WebGL medical) — это даёт сбалансированную картину «технология + дидактика + контекст отрасли».

### 2. Three.js — какие модули нужны для расширения scheme-3d.js

Существующий код (~1680 строк) уже использует базовый стек: `Scene/PerspectiveCamera/WebGLRenderer/OrbitControls/Mesh/BoxGeometry/CylinderGeometry/MeshStandardMaterial`. Из официальных доков и discoverthreejs.com следует, что для масштабирования (50–200 компонентов на плате) узким местом станут draw-calls, а не геометрия. Ключевые модули для миграции:

- **`InstancedMesh`** — обязательный шаг для одинаковых корпусов. Документация явно указывает: «render a large number of objects with the same geometry and material» через одну отрисовку. У Codrops/Wael Yasmina есть готовые рецепты, в том числе динамическое скрытие через перестановку индексов (frustum culling для instances вручную).
- **`BufferGeometry`** напрямую — у DOLG он уже стоит через built-in primitives, но при кастомных корпусах (SOIC pins, SOT-23 leads) дешевле собрать одну геометрию с merged attributes, чем композиции из 10+ Mesh.
- **`GLTFLoader`** — для загрузки реальных STEP-моделей из SnapEDA/Ultra Librarian (через серверную конвертацию STEP→GLB).
- **`GLTFExporter`** — для экспорта сцены DOLG как `.glb` (см. ниже).
- **Lights/Shadows** — гайд Discover three.js предупреждает: каждый point light с тенями = 6 рендеров, поэтому для PCB достаточно одного `DirectionalLight` + `AmbientLight` или вовсе baked-shadow на текстуре подложки.
- **OrbitControls** уже подключены; стоит включить `enableDamping=true` для плавности — это общепринятая практика.

### 3. Сравнение open-source решений

| Проект | Лицензия | Стек | Что взять для DOLG |
|---|---|---|---|
| **KiCanvas** | MIT | TypeScript + Canvas/WebGL (vanilla) | Парсер KiCad-форматов, архитектура embed-able viewer'а |
| **KiCad 3DViewer** | GPL | C++/OpenGL, WRL+STEP | Модель «два формата на компонент»: лёгкий для просмотра, точный для экспорта |
| **Tracespace** | MIT | Node.js, SVG из Gerber | Готовый Gerber-парсер, идея SVG-fallback для печати |
| **Mayhew Labs 3D Gerber** | Closed (бесплатный) | HTML5 + WebGL | UX-референс: stackup-вид, 360° обзор, no-upload-storage |
| **EasyEDA 3D Preview** | Closed (commercial) | Web-native | Какие интеракции пользователь ожидает (top/bottom toggle, contour view, transparent export) |
| **Flux.ai** | Closed | React + react-three-fiber | Доказательство, что production-grade web-EDA на Three.js реален |
| **SnapMagic / Ultra Librarian** | Free download, mixed licenses на модели | STEP/STL/WRL | Источник реальных 3D-моделей для замены процедурных корпусов |

Самый прямой образец для DOLG — **KiCanvas**: MIT-лицензия, vanilla-стек без React, embed-able. Его архитектура «парсер → scene graph → WebGL renderer» — это ровно то, что должен будет иметь DOLG, если решит читать `.kicad_pcb`-файлы. Для 3D-моделей корпусов оптимально комбинировать: процедурная генерация (как сейчас) как fallback + загрузка реальной GLB из библиотеки SnapEDA/Ultra Librarian для топ-100 популярных footprint'ов.

### 4. Форматы 3D — рекомендация

Для DOLG нужны **два формата**, не один:

- **GLB (binary glTF 2.0)** — основной формат экспорта. Khronos называет его «JPEG для 3D», стандартизован как ISO/IEC 12113:2022. Преимущества: один файл, PBR-материалы, прямо грузится в GPU-буфер, нативно поддержан `THREE.GLTFExporter` (`{ binary: true }` → ArrayBuffer). Размер обычно в 5–20 раз меньше эквивалентного STEP. Подходит для: вставки в дипломную работу как 3D-объект, AR-предпросмотра, sharing.
- **STEP (ISO 10303-242)** — для интероперабельности с MCAD (Fusion 360, SolidWorks, FreeCAD). Сохраняет параметрику и точную геометрию. Минус: большой размер и сложная генерация в браузере. На стороне DOLG разумнее хранить STEP-модели компонентов как ассеты, а саму PCB-сборку отдавать как GLB; STEP-экспорт сделать как «отправь Gerber + IDF на сервер и получи STEP».
- **STL** — только для 3D-печати корпуса (механический enclosure), у электронных компонентов смысла нет.
- **3MF** — улучшенная альтернатива STL для печати, можно отложить.
- **IDF (.emn/.emp)** — узкий мост ECAD↔MCAD, передаёт board outline + part placements + heights; добавлять только если будет реальный workflow «отдать механику инженеру SolidWorks».

**Рекомендация: GLB сейчас, IDF/STEP — фаза 2.**

### 5. Конкретные next steps для DOLG

1. **Внедрить `InstancedMesh` для повторяющихся корпусов** (резисторы 0805, конденсаторы, vias). Самый дешёвый «зелёный» шаг по перфомансу — для via-массивов выигрыш в draw-calls 100–500×. Ориентир — [Three.js Instances guide на Codrops](https://tympanus.net/codrops/2025/07/10/three-js-instances-rendering-multiple-objects-simultaneously/).
2. **Добавить GLB-экспорт сцены** через `GLTFExporter({ binary: true })` — ~30 строк кода, и сразу даёт две фичи: вставка 3D в дипломный отчёт (через `<model-viewer>` от Google) + sharing PCB между пользователями.
3. **Опциональная загрузка реальных STEP-моделей через GLB-конвертацию** — для топ-20 footprint'ов (SOIC-8, DIP-14, TQFP, SOT-23 и т.д.) скачать STEP с SnapEDA/Ultra Librarian, конвертировать офлайн в GLB через FreeCAD CLI, положить как статические ассеты в `shop/static`. Это убирает «процедурную аппроксимацию» для самых видимых компонентов.
4. **Заменить point-light shadows на single `DirectionalLight` + baked AO-текстуру на подложке** — снизит cost рендеринга в 5–6× по теням, как явно рекомендует discoverthreejs.com.
5. **Документировать архитектуру по образцу KiCanvas** в дипломном тексте: «парсер схемы → scene graph → instanced renderer → exporter» — это сравнение даёт хорошее место в главе «обзор аналогов».
