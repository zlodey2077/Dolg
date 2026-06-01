# EDA simulator toolbar — 15 настроек + sane defaults для DOLG

Research collected on 2026-05-26 across LTspice / KiCad / EasyEDA / Falstad / Multisim / TINA-TI / Altium / ngspice / Three.js. Используется как референс для top + bottom toolbar и Settings-модалки в `/simulation/`.

## A. Топ-15 must-have настроек

| # | Setting | Где есть в industry | Зачем нам |
|---|---------|---------------------|-----------|
| 1 | **Grid show + size (snap step)** | Altium G-hotkey (1/2.5/5 mm), KiCad 50-mil ERC, EasyEDA 10/20/100 px | Любая EDA |
| 2 | **Snap on/off + distance** | EasyEDA: «всегда ON» | Off-grid компоненты тяжело восстановить |
| 3 | **Move / rotate step** | Все desktop EDA | Точное перемещение стрелками |
| 4 | **Integration method** (Trap / Modified Trap / Gear) | LTspice default = Modified Trap; Multisim Transient tab | Solver kernel |
| 5 | **Max timestep (TMAX)** | LTspice `.tran ... tmax`, Multisim Defaults | SMPS / fast digital |
| 6 | **RELTOL** | ngspice/LTspice default = 1e-3 | Скорость vs точность |
| 7 | **ABSTOL / VNTOL** | ngspice: 1 pA / 1 µV | 8 порядков ниже max signal |
| 8 | **GMIN + ITL1/ITL4** | ngspice: 1e-12, 100, 10 | Convergence rescue |
| 9 | **Simulation speed slider** | Falstad — главный slider | Live UX, decoupled от dt |
| 10 | **DRC/ERC realtime + severity** | KiCad Setup → Electrical Rules → Severity | On-the-fly checks |
| 11 | **Auto-route on/off** | EasyEDA per-edit setting | Конфликт с manual routing |
| 12 | **Probe display mode** (V/I/P + sig-digits) | KiCad OP overlay, Multisim probe-dialog | Читаемость values |
| 13 | **Wire / junction style** | KiCad Setup → General → Formatting | Visual readability |
| 14 | **Theme / font** | KiCad colour scheme + font | Dark/light, проектор-friendly |
| 15 | **Auto-save + undo depth + render (WebGL/Canvas/AA/FPS)** | Pragmatic web block | Three.js best-practice |

## B. Sane defaults для DOLG (education-first)

| Setting | Default | Источник |
|---|---|---|
| Grid | Visible, **5 mm dot** | Altium |
| Snap | **ON, ½ grid** | EasyEDA |
| Move step | **1 grid** | Industry |
| Rotate step | **90°** (Shift = 45°) | ГОСТ orthogonal |
| Integration | **Modified Trap** | LTspice default |
| Max timestep | **Auto** (cap = Tstop/1000) | LTspice/ngspice |
| RELTOL | **1e-3** | ngspice default |
| ABSTOL / VNTOL | **1 pA / 1 µV** | ngspice default |
| CHGTOL | **1e-14** (hidden) | «не менять» — LTspice docs |
| TRTOL | **1** | LTspice |
| GMIN | **1e-12** | Standard |
| ITL1 / ITL4 | **100 / 10** | ngspice; auto-bump до 500/2000 при non-convergence |
| Sim speed slider | **mid = 1× realtime** | Falstad |
| DRC realtime | **ON, severity = Warning** | Education-friendly |
| Auto-route | **OFF by default** | Beginners learn manual first |
| Probe sig-digits | **3** | KiCad |
| Junction dot | **medium (~40 mil)** | KiCad auto |
| Theme | **Light default, dark toggle** | Защита-projector |
| Auto-save | **60 s** | ngspice.wasm crash safety |
| Undo depth | **50** | Class work, low memory |
| Render | **Canvas2D + AA on**; WebGL > 300 components | altersquare.io |
| FPS cap | **60** | Three.js best-practice |

## C. UI Grouping (toolbar layout)

### Top toolbar (always visible, основная работа)
- **View** — Grid show, Grid size, Snap, Theme, Zoom-to-fit
- **Edit step** — Move step, Rotate step, Symbol library (ГОСТ / IEEE / Smart)
- **Run** — ▶ Simulate, ⏸ Pause, ⏹ Stop, Sim-speed slider

### Bottom toolbar / status bar (тонкая полоса)
- **Validation** — DRC realtime toggle, ERC severity, error counter
- **Behavior** — Auto-route, Auto-save interval, Undo limit
- **Status hints** — курсор X/Y, выбранный компонент, счётчик схемы

### Settings modal (gear icon — для редких глубоких настроек)
- **Solver** — Integration, Max timestep, RELTOL/ABSTOL/VNTOL/GMIN
- **Convergence** — ITL1/ITL4/TRTOL, alternate solver
- **Probes** — V/I/P display, units, sig-digits
- **Performance** — Render mode, AA, FPS cap, OffscreenCanvas worker
- **Display** — Junction dot, Hop-over, Wire width, Label font

Структура соответствует LTspice tabbed Control Panel (SPICE / Hacks / Drafting / Waveforms) + KiCad Setup → Formatting/ERC split, без overwhelm'а для новичка.

## D. Источники

- [LTspice Control Panel — LTwiki](https://ltwiki.org/index.php?title=Control_Panel) — tab-структура tolerances
- [LTspice .OPTIONS reference](https://ltwiki.org/LTspiceHelp/LTspiceHelp/_OPTIONS_Set_simulator_options.htm) — names + defaults
- [Spiceman: LTspice Control Panel Setting](https://spiceman.net/ltspice-control-panel-setting/) — Modified-Trap default
- [Rohm AN — LTspice convergence (PDF)](https://rohmfs-rohm-com-cn.oss-cn-shanghai.aliyuncs.com/en/products/databook/applinote/common/how_to_use_ltspice_models_tips_for_improving_convergence_an-e.pdf) — практический TMAX/GMIN/ITL guidance
- [Infineon: LTspice convergence challenges](https://community.infineon.com/t5/Knowledge-Base-Articles/Resolving-convergence-challenges-in-LTspice/ta-p/1053215) — «RELTOL/ABSTOL/VNTOL 8 порядков ниже max»
- [KiCad 9.0 Schematic Editor docs](https://docs.kicad.org/9.0/en/eeschema/eeschema.html) — junction dot, hop-over, font, ERC
- [KiCad 10.0 docs](https://docs.kicad.org/10.0/en/eeschema/eeschema.html) — OP-overlay sig-digits
- [kicad-sch-api ERC User Guide](https://kicad-sch-api.readthedocs.io/en/latest/ERC_USER_GUIDE.html) — Violation Severity panel
- [Multisim Live Convergence](https://www.multisim.com/help/simulation/convergence/) — RELTOL/ABSTOL/VNTOL/ITL1/ITL4/TMAX
- [NI Multisim Transient Analysis](https://knowledge.ni.com/KnowledgeArticleDetails?id=kA03q000000YH7lCAG) — integration method selector
- [Falstad CircuitJS overview](https://www.falstad.com/circuit/doc/overview.html) и [directions](https://www.falstad.com/circuit-java/directions.html) — timestep 5 µs, Simulation Speed slider
- [EasyEDA Schematic Canvas Settings](https://docs.easyeda.com/en/Schematic/Canvas-Settings/index.html) и [Snap docs](https://prodocs.easyeda.com/en/panel/edit-snap/) — snap-always-on
- [Altium: Schematic Grids and Preferences](https://www.altium.com/documentation/altium-designer/schematic-grids-preferences?version=19.0) — 1/2.5/5 mm preset, G-hotkey
- [TINA-TI Getting Started (PDF)](https://www.ti.com/lit/ug/sbou052a/sbou052a.pdf) — analysis-range, step-size, tolerance
- [Three.js antialiasing performance](https://discourse.threejs.org/t/performance-of-different-antialiasing-techniques/56740) — antialias-off, render-half-res
- [Codrops Three.js perf guide](https://tympanus.net/codrops/2025/02/11/building-efficient-three-js-scenes-optimize-performance-while-maintaining-quality/) — stats-gl FPS HUD
- [AlterSquare: WebGL vs Canvas for CAD](https://altersquare.io/webgl-vs-canvas-best-choice-for-browser-based-cad-tools/) — Canvas2D vs WebGL для 2D schematics
