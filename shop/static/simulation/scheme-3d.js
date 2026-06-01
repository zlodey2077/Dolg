// =============================================================================
// scheme-3d.js — 3D-просмотр платы (killer-фича #4 диплома)
// =============================================================================
// Рендерит принципиальную схему как процедурную 3D-модель печатной платы:
// PCB-подложка + типовые корпуса (axial-резистор с цветовым кодом, LED-купол,
// электролитический конденсатор, DIP-микросхема, TO-92-транзистор, диод с
// катодной полосой, барабанный индуктор, ground-pad). Соединения — плоские
// медные дорожки на слоях платы, без "проводов" над поверхностью.
//
// Зависимости (глобальные UMD):
//   - THREE (shop/static/lib/three.min.js, r140)
//   - THREE.OrbitControls (shop/static/lib/OrbitControls.js, r140)
//   - THREE.GLTFExporter (shop/static/lib/GLTFExporter.js, r140) — опционально,
//     нужен только для exportGlb/downloadGlb. Если не загружен, эти функции
//     возвращают rejected Promise с понятной ошибкой.
//   - scheme-3d-materials.js  — палитра, shared-материалы, BOARD_DEFAULTS, UNIT_PER_MM
//   - scheme-3d-components.js — процедурные модели корпусов (makeForType и др.)
//
// Контракт:
//   DolgScheme3D.init(canvas, scheme)              — построить сцену
//   DolgScheme3D.tick()                            — один кадр (RAF-цикл)
//   DolgScheme3D.exportPng() → dataURL             — PNG-снимок
//   DolgScheme3D.exportGlb(opts) → Promise<Buffer> — GLB (binary glTF 2.0)
//   DolgScheme3D.downloadGlb(name) → Promise       — скачать .glb в браузере
//   DolgScheme3D.setThermalOverlay(powerMap)       — наложить тепловую карту
//   DolgScheme3D.clearThermalOverlay()             — убрать тепловую карту
//   DolgScheme3D.hasThermalOverlay() → bool        — есть ли overlay
//   DolgScheme3D.highlightComponent(id)            — cyan-обводка компонента
//   DolgScheme3D.clearHighlight()                  — снять подсветку
//   DolgScheme3D.setLayerOpacity(layer, opacity)   — прозрачность слоя [0..1]
//   DolgScheme3D.setSoloLayer(layer)               — solo-mode: только этот слой 100%
//   DolgScheme3D.resetLayerOpacity()               — сбросить все слои на 100%
//   DolgScheme3D.setExplodeFactor(factor)          — разнести слои [0..1.4]
//   DolgScheme3D.setFlipped(bool) / toggleFlipped()— перевернуть плату 180° по X
//   DolgScheme3D.dispose()                         — освободить GPU-ресурсы
// =============================================================================

(function (window) {
    'use strict';

    if (typeof THREE === 'undefined') {
        console.error('[scheme-3d] THREE не загружен — добавь three.min.js до этого скрипта');
        return;
    }

    // Импорт из выделенных подмодулей. Они IIFE-загружаются раньше нас по
    // порядку <script>-тегов в шаблоне (см. simulation.html).
    var _lib = window._dolg3dLib || {};
    if (!_lib.MAT || !_lib.makeForType) {
        console.error('[scheme-3d] подмодули materials/components не загружены — проверь порядок <script>');
        return;
    }
    var MAT = _lib.MAT;
    var RESISTOR_BAND_COLORS = _lib.RESISTOR_BAND_COLORS;
    var resistorBands = _lib.resistorBands;
    var BOARD_DEFAULTS = _lib.BOARD_DEFAULTS;
    var UNIT_PER_MM = _lib.UNIT_PER_MM;
    var _num = _lib._num;
    var _round3 = _lib._round3;
    var _snapUp = _lib._snapUp;
    var _normPackage = _lib._normPackage;
    var footprintForComponent = _lib.footprintForComponent;
    var _componentCenterPx = _lib._componentCenterPx;
    var _externalModelUrl = _lib._externalModelUrl;
    var makeForType = _lib.makeForType;

    // Materials и procedural component models вынесены в scheme-3d-materials.js + scheme-3d-components.js

    function _endpointCompId(endpoint) {
        return endpoint && (endpoint.compId || endpoint.componentId || endpoint.id || endpoint.component);
    }

    function _endpointPortId(endpoint) {
        return endpoint && (endpoint.portId || endpoint.pinId || endpoint.port || endpoint.pin || '');
    }

    function _padKey(compId, portId) {
        return `${compId || ''}::${portId || ''}`;
    }

    function _boardOptions(scheme, options) {
        const board = (scheme && scheme.board) || {};
        return {
            pxPerMm: _num(options && options.pxPerMm, _num(board.px_per_mm || board.pxPerMm, BOARD_DEFAULTS.pxPerMm)),
            marginMm: _num(options && options.marginMm, _num(board.margin_mm || board.marginMm, BOARD_DEFAULTS.marginMm)),
            traceWidthMm: _num(options && options.traceWidthMm, _num(board.trace_width_mm || board.traceWidthMm, BOARD_DEFAULTS.traceWidthMm)),
            clearanceMm: _num(options && options.clearanceMm, _num(board.clearance_mm || board.clearanceMm, BOARD_DEFAULTS.clearanceMm)),
            thicknessMm: _num(options && options.thicknessMm, _num(board.thickness_mm || board.thicknessMm, BOARD_DEFAULTS.thicknessMm)),
            gridMm: _num(options && options.gridMm, _num(board.grid_mm || board.gridMm, BOARD_DEFAULTS.gridMm)),
            padDiameterMm: _num(options && options.padDiameterMm, _num(board.pad_diameter_mm || board.padDiameterMm, BOARD_DEFAULTS.padDiameterMm)),
            holeDiameterMm: _num(options && options.holeDiameterMm, _num(board.hole_diameter_mm || board.holeDiameterMm, BOARD_DEFAULTS.holeDiameterMm)),
            minBoardMm: _num(options && options.minBoardMm, _num(board.min_board_mm || board.minBoardMm, BOARD_DEFAULTS.minBoardMm)),
        };
    }

    function _routePointKey(point) {
        return `${_round3(point.xMm)}:${_round3(point.yMm)}`;
    }

    function _axisAlignedSegments(points, routeIndex, clearanceMm) {
        const out = [];
        for (let i = 1; i < points.length; i++) {
            const a = points[i - 1];
            const b = points[i];
            if (Math.abs(a.xMm - b.xMm) < 0.001 || Math.abs(a.yMm - b.yMm) < 0.001) {
                out.push(b);
                continue;
            }
            const dx = Math.abs(a.xMm - b.xMm);
            const dy = Math.abs(a.yMm - b.yMm);
            const horizontalFirst = dx >= dy ? routeIndex % 3 !== 1 : routeIndex % 3 === 0;
            const elbow = horizontalFirst
                ? { xMm: b.xMm, yMm: a.yMm }
                : { xMm: a.xMm, yMm: b.yMm };
            const prevElbow = out.length ? out[out.length - 1] : a;
            if (Math.hypot(prevElbow.xMm - elbow.xMm, prevElbow.yMm - elbow.yMm) >= 0.05) out.push(elbow);
            const prev = out.length ? out[out.length - 1] : a;
            if (Math.hypot(prev.xMm - b.xMm, prev.yMm - b.yMm) >= 0.05) out.push(b);
        }
        return [points[0], ...out].filter((p, idx, arr) => {
            if (idx === 0) return true;
            const prev = arr[idx - 1];
            return Math.hypot(prev.xMm - p.xMm, prev.yMm - p.yMm) >= 0.05;
        });
    }

    function _typePrefix(type) {
        const t = String(type || '').toLowerCase();
        if (t === 'resistor') return 'R';
        if (t === 'capacitor') return 'C';
        if (t === 'diode' || t === 'led') return 'D';
        if (t === 'transistor' || t === 'npn' || t === 'pnp') return 'Q';
        if (t === 'ic') return 'U';
        if (t === 'inductor') return 'L';
        if (t === 'relay') return 'K';
        if (t === 'connector') return 'X';
        if (t === 'switch') return 'SA';
        if (t === 'battery') return 'V';
        if (t === 'ground') return 'GND';
        if (t === 'node') return 'N';
        return 'E';
    }

    // ----- Designator + silkscreen-метки на компонентах -----
    // Эти три функции остались в main, потому что зависят от closure-функции
    // `makeTextSprite` (использует _disposeFns для очистки canvas-текстур) и
    // от _typePrefix. При финальном расщеплении (silkscreen-renderer) их
    // можно будет вынести вместе с makeTextSprite в scheme-3d-text.js.
    function _hasExplicitGround(components) {
        return components.some((c) => {
            const text = `${c.type || ''} ${c.label || ''} ${c.name || ''} ${c.designator || ''}`.toLowerCase();
            return String(c.type || '').toLowerCase() === 'ground' || /\b(gnd|земля|общий)\b/i.test(text);
        });
    }

    function _displayRef(comp, counters, duplicateCounts) {
        const prefix = _typePrefix(comp.type);
        counters[prefix] = (counters[prefix] || 0) + 1;
        const raw = String(comp.label || comp.designator || comp.ref || '').trim();
        const match = raw.match(/^([A-Za-z]{1,4})\s*[-_ ]?(\d{1,4})\b/);
        if (match) return `${match[1].toUpperCase()}${match[2]}`;
        const generic = !raw || raw.toLowerCase() === String(comp.type || '').toLowerCase() || raw.toUpperCase() === prefix;
        const duplicated = raw && (duplicateCounts.get(raw) || 0) > 1 && !/[0-9]/.test(raw);
        return generic || duplicated ? `${prefix}${counters[prefix]}` : raw;
    }

    function _silkscreenText(text) {
        const g = new THREE.Group();
        const sprite = makeTextSprite(text, { compact: true, monochrome: true });
        if (!sprite) return g;
        sprite.scale.set(0.9, 0.24, 1);
        sprite.position.y = 0.02;
        g.add(sprite);
        return g;
    }

    function _maybeAddDesignator(model, comp) {
        const type = String(comp.type || '').toLowerCase();
        if (type === 'node' || type === 'ground') return;
        const ref = comp._dolg3dRef || '';
        if (!ref) return;
        const label = _silkscreenText(ref);
        label.position.set(0, 0.02, 0.42);
        model.add(label);
    }

    function _componentValue(comp) {
        const params = comp.parameters || comp.catalog_parameters || {};
        return (
            comp.part_number ||
            comp.partNumber ||
            comp.catalog_part_number ||
            params.part_number ||
            comp.resistance ||
            comp.capacitance ||
            comp.inductance ||
            params.value ||
            params.nominal ||
            params.resistance ||
            params.capacitance ||
            params.inductance ||
            ''
        );
    }

    function _componentHoverMeta(comp) {
        const params = comp.parameters || comp.catalog_parameters || {};
        return {
            ref: comp._dolg3dRef || comp.label || comp.designator || '',
            title: (
                comp.catalog_name ||
                comp.product_name ||
                comp.name ||
                comp.part_number ||
                comp.catalog_ref ||
                comp.label ||
                comp.type ||
                'Компонент'
            ),
            value: _componentValue(comp),
            package: comp.catalog_package || comp.package_type || params.package || params.footprint || '',
            manufacturer: comp.catalog_manufacturer || comp.manufacturer || params.manufacturer || '',
            typeLabel: _typePrefix(comp.type),
            catalogSlug: comp.catalog_slug || '',
        };
    }

    function _markHoverable(group, comp) {
        const meta = _componentHoverMeta(comp);
        group.traverse((obj) => {
            if (obj.isMesh || obj.isSprite) {
                obj.userData.dolgComponent = meta;
                _hoverables.push(obj);
            }
        });
    }

    function _componentDisplayLabel(comp, counters, duplicateCounts) {
        return _displayRef(comp, counters, duplicateCounts);
    }

    function computeBoardLayout(scheme, options) {
        const components = ((scheme && scheme.components) || []).filter(Boolean);
        const connections = ((scheme && scheme.connections) || []).filter(Boolean);
        const opts = _boardOptions(scheme || {}, options || {});
        if (!components.length) {
            return {
                board: {
                    widthMm: opts.minBoardMm,
                    heightMm: opts.minBoardMm,
                    thicknessMm: opts.thicknessMm,
                    marginMm: opts.marginMm,
                    traceWidthMm: opts.traceWidthMm,
                    clearanceMm: opts.clearanceMm,
                    pxPerMm: opts.pxPerMm,
                    originPx: { x: 0, y: 0 },
                    extraMarginMm: { x: 0, y: 0 },
                },
                components: [],
                pads: [],
                traces: [],
                vias: [],
                holes: [],
                groundZone: { present: false, label: 'Зона GND' },
                warnings: ['В схеме нет компонентов для 3D-платы'],
                stats: { components: 0, traces: 0, vias: 0, holes: 0, pads: 0, layers: 2, areaMm2: opts.minBoardMm * opts.minBoardMm },
            };
        }

        const compById = new Map();
        const rawComps = [];
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        const includePx = (x, y) => {
            minX = Math.min(minX, x);
            minY = Math.min(minY, y);
            maxX = Math.max(maxX, x);
            maxY = Math.max(maxY, y);
        };

        components.forEach((comp) => {
            const center = _componentCenterPx(comp);
            const fp = footprintForComponent(comp);
            const halfWpx = Math.max(8, fp.widthMm * opts.pxPerMm / 2);
            const halfHpx = Math.max(8, fp.heightMm * opts.pxPerMm / 2);
            includePx(center.x - halfWpx, center.y - halfHpx);
            includePx(center.x + halfWpx, center.y + halfHpx);
            (comp.ports || []).forEach((port) => {
                includePx(center.x + _num(port.x, 0), center.y + _num(port.y, 0));
            });
            const item = { source: comp, centerPx: center, footprint: fp };
            compById.set(comp.id, item);
            rawComps.push(item);
        });

        connections.forEach((conn) => {
            (conn.waypoints || []).forEach((p) => includePx(_num(p.x, 0), _num(p.y, 0)));
            (conn.vias || []).forEach((p) => includePx(_num(p.x, 0), _num(p.y, 0)));
        });

        const rawWidthMm = (maxX - minX) / opts.pxPerMm + opts.marginMm * 2;
        const rawHeightMm = (maxY - minY) / opts.pxPerMm + opts.marginMm * 2;
        const widthMm = _snapUp(Math.max(opts.minBoardMm, rawWidthMm), opts.gridMm);
        const heightMm = _snapUp(Math.max(opts.minBoardMm, rawHeightMm), opts.gridMm);
        const extraX = Math.max(0, (widthMm - rawWidthMm) / 2);
        const extraY = Math.max(0, (heightMm - rawHeightMm) / 2);
        const toMm = (x, y) => ({
            x: _round3((x - minX) / opts.pxPerMm + opts.marginMm + extraX),
            y: _round3((y - minY) / opts.pxPerMm + opts.marginMm + extraY),
        });

        const pads = [];
        const padsByEndpoint = new Map();
        const componentLayouts = rawComps.map(({ source, centerPx, footprint }) => {
            const centerMm = toMm(centerPx.x, centerPx.y);
            const portList = (source.ports && source.ports.length ? source.ports : [{ id: '1', x: -20, y: 0 }, { id: '2', x: 20, y: 0 }]);
            portList.forEach((port, index) => {
                const portId = port.id || port.name || String(index + 1);
                const p = toMm(centerPx.x + _num(port.x, index ? 20 : -20), centerPx.y + _num(port.y, 0));
                const pad = {
                    xMm: p.x,
                    yMm: p.y,
                    compId: source.id,
                    portId,
                    label: port.label || port.name || portId,
                    diameterMm: opts.padDiameterMm,
                    holeMm: opts.holeDiameterMm,
                    layer: source.side === 'bottom' ? 'bottom' : 'top',
                };
                pads.push(pad);
                padsByEndpoint.set(_padKey(source.id, portId), pad);
            });
            return {
                id: source.id,
                type: source.type || 'component',
                label: source.label || source.name || source.type || '',
                package: footprint.package,
                footprint,
                xMm: centerMm.x,
                yMm: centerMm.y,
                widthMm: footprint.widthMm,
                heightMm: footprint.heightMm,
                rotation: _num(source.rotation, 0),
                side: source.side || 'top',
                source,
            };
        });

        const padForEndpoint = (endpoint) => {
            const compId = _endpointCompId(endpoint);
            const portId = _endpointPortId(endpoint);
            let pad = padsByEndpoint.get(_padKey(compId, portId));
            if (pad) return pad;
            const comp = compById.get(compId);
            if (!comp) return null;
            const p = toMm(comp.centerPx.x, comp.centerPx.y);
            pad = { xMm: p.x, yMm: p.y, compId, portId: portId || 'center', diameterMm: opts.padDiameterMm, holeMm: opts.holeDiameterMm, layer: 'top' };
            pads.push(pad);
            padsByEndpoint.set(_padKey(compId, portId), pad);
            return pad;
        };

        const traces = [];
        const routeJoints = new Map();
        const vias = [];
        connections.forEach((conn, idx) => {
            const from = padForEndpoint(conn.from || {});
            const to = padForEndpoint(conn.to || {});
            if (!from || !to) return;
            const layer = conn.layer === 'bottom' ? 'bottom' : 'top';
            const width = _num(conn.width_mm || conn.widthMm, opts.traceWidthMm);
            const rawPoints = [
                { xMm: from.xMm, yMm: from.yMm },
                ...((conn.waypoints || []).map((p) => {
                    const mm = toMm(_num(p.x, 0), _num(p.y, 0));
                    return { xMm: mm.x, yMm: mm.y };
                })),
                { xMm: to.xMm, yMm: to.yMm },
            ];
            const points = _axisAlignedSegments(rawPoints, idx, opts.clearanceMm);
            for (let i = 1; i < points.length; i++) {
                traces.push({
                    id: conn.id || `conn-${idx}`,
                    from: points[i - 1],
                    to: points[i],
                    layer,
                    widthMm: width,
                });
            }
            points.slice(1, -1).forEach((p) => routeJoints.set(_routePointKey(p), p));
            (conn.vias || []).forEach((v) => {
                const mm = toMm(_num(v.x, 0), _num(v.y, 0));
                vias.push({ xMm: mm.x, yMm: mm.y, diameterMm: _num(v.diameter_mm || v.diameterMm, 1.1), holeMm: _num(v.hole_mm || v.holeMm, 0.45) });
            });
        });

        const holes = [];
        const holeInset = Math.min(5, widthMm / 8, heightMm / 8);
        if (widthMm >= 35 && heightMm >= 35) {
            [[holeInset, holeInset], [widthMm - holeInset, holeInset], [holeInset, heightMm - holeInset], [widthMm - holeInset, heightMm - holeInset]]
                .forEach(([x, y]) => holes.push({ xMm: _round3(x), yMm: _round3(y), diameterMm: 3.2, kind: 'mount' }));
        }

        const hasGround = _hasExplicitGround(components);
        const warnings = [];
        if (rawWidthMm < opts.minBoardMm || rawHeightMm < opts.minBoardMm) warnings.push('Расчет применил минимальный размер платы 50 мм для читаемости');
        if (!hasGround) warnings.push('Нет явной земли GND');
        if (!connections.length) warnings.push('Нет соединений между компонентами');
        const connectedCompIds = new Set();
        connections.forEach((conn) => {
            const a = _endpointCompId(conn.from || {});
            const b = _endpointCompId(conn.to || {});
            if (a) connectedCompIds.add(a);
            if (b) connectedCompIds.add(b);
        });
        components.forEach((comp) => {
            if (comp.type !== 'node' && comp.type !== 'ground' && !connectedCompIds.has(comp.id)) {
                warnings.push(`Компонент ${comp.label || comp.id || comp.type} не подключен`);
            }
        });
        for (let i = 0; i < componentLayouts.length; i++) {
            for (let j = i + 1; j < componentLayouts.length; j++) {
                const a = componentLayouts[i], b = componentLayouts[j];
                if (a.type === 'node' || b.type === 'node') continue;
                const dx = Math.abs(a.xMm - b.xMm) - (a.widthMm + b.widthMm) / 2;
                const dy = Math.abs(a.yMm - b.yMm) - (a.heightMm + b.heightMm) / 2;
                const gap = Math.max(dx, dy);
                if (gap < opts.clearanceMm) {
                    warnings.push(`Малый зазор: ${a.label || a.id} рядом с ${b.label || b.id}`);
                }
            }
        }

        return {
            board: {
                widthMm,
                heightMm,
                thicknessMm: opts.thicknessMm,
                marginMm: opts.marginMm,
                traceWidthMm: opts.traceWidthMm,
                clearanceMm: opts.clearanceMm,
                pxPerMm: opts.pxPerMm,
                originPx: { x: minX, y: minY },
                extraMarginMm: { x: _round3(extraX), y: _round3(extraY) },
            },
            components: componentLayouts,
            pads,
            traces,
            routeJoints: Array.from(routeJoints.values()),
            vias,
            holes,
            groundZone: {
                present: hasGround,
                label: 'Зона GND',
                xMm: _round3(widthMm / 2),
                yMm: _round3(heightMm / 2),
                widthMm: _round3(Math.max(0, widthMm - opts.marginMm * 2)),
                heightMm: _round3(Math.max(0, heightMm - opts.marginMm * 2)),
                clearanceMm: opts.clearanceMm,
            },
            warnings: warnings.slice(0, 8),
            stats: {
                components: componentLayouts.filter(c => c.type !== 'node').length,
                traces: traces.length,
                vias: vias.length,
                holes: holes.length,
                pads: pads.length,
                layers: 2,
                areaMm2: _round3(widthMm * heightMm),
            },
        };
    }

    function _worldPoint(layout, xMm, yMm, zLift) {
        return new THREE.Vector3(
            (xMm - layout.board.widthMm / 2) * UNIT_PER_MM,
            zLift || 0,
            (yMm - layout.board.heightMm / 2) * UNIT_PER_MM
        );
    }

    function _roundedShape(width, height, radius) {
        const w = width / 2, h = height / 2, r = Math.min(radius, w, h);
        const shape = new THREE.Shape();
        shape.moveTo(-w + r, -h);
        shape.lineTo(w - r, -h);
        shape.quadraticCurveTo(w, -h, w, -h + r);
        shape.lineTo(w, h - r);
        shape.quadraticCurveTo(w, h, w - r, h);
        shape.lineTo(-w + r, h);
        shape.quadraticCurveTo(-w, h, -w, h - r);
        shape.lineTo(-w, -h + r);
        shape.quadraticCurveTo(-w, -h, -w + r, -h);
        return shape;
    }

    function _addLine(group, a, b, radius, material) {
        const dist = a.distanceTo(b);
        if (dist < 0.01) return null;
        const mid = a.clone().add(b).multiplyScalar(0.5);
        const mesh = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, dist, 8), material);
        mesh.position.copy(mid);
        mesh.lookAt(b);
        mesh.rotateX(Math.PI / 2);
        group.add(mesh);
        return mesh;
    }

    function _addDisk(group, point, radius, height, material) {
        const disk = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, height, 28), material);
        disk.position.copy(point);
        group.add(disk);
        return disk;
    }

    function _addFlatTraceSegment(group, a, b, width, material) {
        const dx = b.x - a.x;
        const dz = b.z - a.z;
        const len = Math.hypot(dx, dz);
        if (len < 0.01) return null;
        const mesh = new THREE.Mesh(new THREE.BoxGeometry(len, 0.014, width), material);
        mesh.position.set((a.x + b.x) / 2, a.y, (a.z + b.z) / 2);
        mesh.rotation.y = -Math.atan2(dz, dx);
        group.add(mesh);
        return mesh;
    }


    function _addBoardGeometry(layout) {
        const boardW = layout.board.widthMm * UNIT_PER_MM;
        const boardD = layout.board.heightMm * UNIT_PER_MM;
        const thickness = layout.board.thicknessMm * UNIT_PER_MM;
        const shape = _roundedShape(boardW, boardD, Math.min(1.5 * UNIT_PER_MM, boardW * 0.08, boardD * 0.08));
        const boardGeom = new THREE.ExtrudeGeometry(shape, { depth: thickness, bevelEnabled: false, curveSegments: 8 });
        boardGeom.rotateX(Math.PI / 2);
        const board = new THREE.Mesh(boardGeom, MAT.pcbGreen);
        board.position.y = 0;
        _root.add(board);

        const topCopper = new THREE.Mesh(new THREE.ShapeGeometry(shape), MAT.copperTop);
        topCopper.geometry.rotateX(Math.PI / 2);
        topCopper.position.y = 0.012;
        topCopper.scale.set(0.985, 0.985, 0.985);
        topCopper.material = new THREE.MeshStandardMaterial({ color: 0x174e26, roughness: 0.82, transparent: true, opacity: 0.42 });
        _root.add(topCopper);

        _layerGroups.ground = new THREE.Group();
        if (layout.groundZone && layout.groundZone.present) {
            const zoneW = Math.max(0.2, layout.groundZone.widthMm * UNIT_PER_MM);
            const zoneD = Math.max(0.2, layout.groundZone.heightMm * UNIT_PER_MM);
            const groundShape = _roundedShape(zoneW, zoneD, Math.min(1.0 * UNIT_PER_MM, zoneW * 0.06, zoneD * 0.06));
            const ground = new THREE.Mesh(
                new THREE.ShapeGeometry(groundShape),
                new THREE.MeshStandardMaterial({ color: 0xc77b2a, metalness: 0.45, roughness: 0.45, transparent: true, opacity: 0.22 })
            );
            ground.geometry.rotateX(Math.PI / 2);
            ground.position.y = 0.026;
            _layerGroups.ground.add(ground);

            const label = makeTextSprite('Зона GND', { compact: true, monochrome: true });
            if (label) {
                label.scale.set(1.05, 0.24, 1);
                label.position.set(-zoneW / 2 + 0.72, 0.11, -zoneD / 2 + 0.32);
                _layerGroups.ground.add(label);
                _labelSprites.push(label);
            }

            const stitchRadius = Math.max(0.045, layout.board.traceWidthMm * UNIT_PER_MM * 0.45);
            const countX = Math.max(2, Math.floor(zoneW / 1.8));
            for (let i = 0; i <= countX; i++) {
                const x = -zoneW / 2 + (zoneW * i / countX);
                _addDisk(_layerGroups.ground, new THREE.Vector3(x, 0.055, -zoneD / 2 + 0.18), stitchRadius, 0.018, MAT.pad);
                _addDisk(_layerGroups.ground, new THREE.Vector3(x, 0.055, zoneD / 2 - 0.18), stitchRadius, 0.018, MAT.pad);
            }
        }
        _root.add(_layerGroups.ground);

        // Нижняя поверхность — зелёный soldermask (тот же FR4 + green mask
        // что и сверху). Раньше использовался синий MAT.copperBottom, из-за
        // чего вся нижняя сторона выглядела как сплошная медь, что не
        // соответствует стандартному PCB. Реальная плата с обеих сторон
        // покрыта green mask'ом; голубой copper-цвет используется только для
        // конкретных дорожек bottom-layer'а, которые рендерятся ниже через
        // _renderTraces (см. trace.layer === 'bottom').
        _layerGroups.bottom = new THREE.Group();
        const bottomMaskMat = new THREE.MeshStandardMaterial({ color: 0x174e26, roughness: 0.82, transparent: true, opacity: 0.42 });
        const bottom = new THREE.Mesh(new THREE.ShapeGeometry(shape), bottomMaskMat);
        bottom.geometry.rotateX(Math.PI / 2);
        bottom.position.y = -thickness - 0.012;
        bottom.scale.set(0.985, 0.985, 0.985);
        _layerGroups.bottom.add(bottom);
        _root.add(_layerGroups.bottom);

        const title = makeTextSprite('DOLG PCB', { compact: true });
        if (title) {
            title.scale.set(1.5, 0.38, 1);
            title.position.set(-boardW * 0.33, 0.16, -boardD * 0.42);
            _root.add(title);
            _labelSprites.push(title);
        }
    }

    function _renderPadsAndHoles(layout) {
        _layerGroups.top = _layerGroups.top || new THREE.Group();
        layout.pads.forEach((pad) => {
            const p = _worldPoint(layout, pad.xMm, pad.yMm, 0.045);
            _addDisk(_layerGroups.top, p, (pad.diameterMm * UNIT_PER_MM) / 2, 0.026, MAT.pad);
            _addDisk(_layerGroups.top, p.clone().setY(0.062), (pad.holeMm * UNIT_PER_MM) / 2, 0.032, MAT.hole);
        });
        layout.vias.forEach((via) => {
            const p = _worldPoint(layout, via.xMm, via.yMm, 0.07);
            _addDisk(_layerGroups.top, p, (via.diameterMm * UNIT_PER_MM) / 2, 0.03, MAT.pad);
            _addDisk(_layerGroups.top, p.clone().setY(0.09), (via.holeMm * UNIT_PER_MM) / 2, 0.035, MAT.hole);
        });
        layout.holes.forEach((hole) => {
            const p = _worldPoint(layout, hole.xMm, hole.yMm, 0.074);
            _addDisk(_layerGroups.top, p, (hole.diameterMm * UNIT_PER_MM) / 2, 0.04, MAT.hole);
        });
        _root.add(_layerGroups.top);
    }

    function _renderRouteJoints(layout) {
        _layerGroups.top = _layerGroups.top || new THREE.Group();
        (layout.routeJoints || []).forEach((joint) => {
            const p = _worldPoint(layout, joint.xMm, joint.yMm, 0.089);
            _addDisk(_layerGroups.top, p, Math.max(0.055, layout.board.traceWidthMm * UNIT_PER_MM * 0.62), 0.014, MAT.pad);
        });
    }

    function _renderTraces(layout) {
        _layerGroups.top = _layerGroups.top || new THREE.Group();
        _layerGroups.bottom = _layerGroups.bottom || new THREE.Group();
        const thickness = layout.board.thicknessMm * UNIT_PER_MM;
        layout.traces.forEach((trace) => {
            const group = trace.layer === 'bottom' ? _layerGroups.bottom : _layerGroups.top;
            const y = trace.layer === 'bottom' ? -thickness - 0.035 : 0.075;
            const a = _worldPoint(layout, trace.from.xMm, trace.from.yMm, y);
            const b = _worldPoint(layout, trace.to.xMm, trace.to.yMm, y);
            const mat = trace.layer === 'bottom' ? MAT.copperBottom : MAT.copperTop;
            const width = Math.max(0.07, trace.widthMm * UNIT_PER_MM);
            _addFlatTraceSegment(group, a, b, width, mat);
            _addDisk(group, a.clone().setY(y + 0.003), width / 2, 0.012, mat);
            _addDisk(group, b.clone().setY(y + 0.003), width / 2, 0.012, mat);
        });
        _renderRouteJoints(layout);
        if (!_layerGroups.top.parent) _root.add(_layerGroups.top);
        if (!_layerGroups.bottom.parent) _root.add(_layerGroups.bottom);
    }

    function _renderDimensions(layout) {
        _layerGroups.dimensions = new THREE.Group();
        const w = layout.board.widthMm * UNIT_PER_MM;
        const d = layout.board.heightMm * UNIT_PER_MM;
        const y = 0.18;
        const z = d / 2 + 0.7;
        const x = w / 2 + 0.7;
        _addLine(_layerGroups.dimensions, new THREE.Vector3(-w / 2, y, z), new THREE.Vector3(w / 2, y, z), 0.018, MAT.dimension);
        _addLine(_layerGroups.dimensions, new THREE.Vector3(x, y, -d / 2), new THREE.Vector3(x, y, d / 2), 0.018, MAT.dimension);
        const widthLabel = makeTextSprite(`${layout.board.widthMm} мм`, { compact: true });
        if (widthLabel) {
            widthLabel.scale.set(1.5, 0.34, 1);
            widthLabel.position.set(0, y + 0.22, z + 0.14);
            _layerGroups.dimensions.add(widthLabel);
        }
        const heightLabel = makeTextSprite(`${layout.board.heightMm} мм`, { compact: true });
        if (heightLabel) {
            heightLabel.scale.set(1.5, 0.34, 1);
            heightLabel.position.set(x + 0.2, y + 0.22, 0);
            _layerGroups.dimensions.add(heightLabel);
        }
        _root.add(_layerGroups.dimensions);
    }

    function _renderWarnings(layout) {
        _layerGroups.warnings = new THREE.Group();
        if (!layout.warnings.length) return;
        const boardW = layout.board.widthMm * UNIT_PER_MM;
        const boardD = layout.board.heightMm * UNIT_PER_MM;
        layout.warnings.slice(0, 4).forEach((text, index) => {
            const icon = new THREE.Mesh(new THREE.ConeGeometry(0.16, 0.36, 3), MAT.warning);
            icon.rotation.y = Math.PI / 6;
            icon.position.set(-boardW / 2 + 0.38 + index * 0.34, 0.38, boardD / 2 - 0.38);
            _layerGroups.warnings.add(icon);
            const sprite = makeTextSprite(index === 0 ? 'DRC' : String(index + 1), { compact: true });
            if (sprite) {
                sprite.scale.set(0.62, 0.18, 1);
                sprite.position.set(icon.position.x, 0.74, icon.position.z);
                _layerGroups.warnings.add(sprite);
            }
        });
        _root.add(_layerGroups.warnings);
    }

    // --- Основной модуль -------------------------------------------------------
    let _scene, _camera, _renderer, _controls, _root, _disposeFns = [];
    let _labelSprites = [];  // массив всех label-спрайтов для toggle visibility
    let _layerGroups = {};
    // Маппинг id компонента → mesh, чтобы overlay-фичи (thermal map, cross-probing)
    // могли быстро найти 3D-объект по id из 2D-схемы. Заполняется при построении
    // сцены, очищается в dispose().
    let _componentMeshes = {};
    // Накопитель thermal-overlay-мешей; очищается в clearThermalOverlay() и dispose().
    let _thermalOverlayObjects = [];
    // Cross-probing: id выбранного в 2D-схеме компонента и его overlay-mesh.
    let _highlightedId = null;
    let _highlightMesh = null;
    let _layoutReport = null;
    let _hoverables = [];
    let _raycaster = null;
    let _pointer = null;
    let _hoverCallback = null;
    let _selectCallback = null;

    function init(canvas, scheme, options) {
        const w = canvas.clientWidth || 800;
        const h = canvas.clientHeight || 600;
        _hoverCallback = options && typeof options.onHover === 'function' ? options.onHover : null;
        _selectCallback = options && typeof options.onSelect === 'function' ? options.onSelect : null;
        _hoverables = [];
        _raycaster = new THREE.Raycaster();
        _pointer = new THREE.Vector2();

        _scene = new THREE.Scene();
        _scene.background = new THREE.Color(0x1a1f2e);

        _camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 1000);
        _camera.position.set(0, 14, 18);
        _camera.lookAt(0, 0, 0);

        _renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
        _renderer.setSize(w, h, false);
        _renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));

        _controls = new THREE.OrbitControls(_camera, canvas);
        _controls.enableDamping = true;
        _controls.dampingFactor = 0.08;
        _controls.enablePan = true;
        _controls.screenSpacePanning = true;
        _controls.minDistance = 1.1;
        _controls.maxDistance = 180;
        _controls.zoomSpeed = 1.28;
        _controls.panSpeed = 1.08;
        _controls.rotateSpeed = 0.72;
        if ('zoomToCursor' in _controls) _controls.zoomToCursor = true;

        // Освещение
        _scene.add(new THREE.AmbientLight(0xffffff, 0.55));
        const dir = new THREE.DirectionalLight(0xffffff, 0.8);
        dir.position.set(8, 18, 6);
        _scene.add(dir);
        const fill = new THREE.DirectionalLight(0xb0c4de, 0.25);
        fill.position.set(-10, 6, -8);
        _scene.add(fill);

        _root = new THREE.Group();
        _scene.add(_root);
        // Сигналим подмодулю components, что сцена жива — это пускает
        // async GLTFLoader callbacks в tryAttachExternalModel.
        _lib.sceneRoot = _root;

        _layerGroups = {};
        _layoutReport = computeBoardLayout(scheme || {});
        const components = (scheme && scheme.components) || [];
        const connections = (scheme && scheme.connections) || [];
        _addBoardGeometry(_layoutReport);
        _renderPadsAndHoles(_layoutReport);
        _renderTraces(_layoutReport);
        _renderDimensions(_layoutReport);
        _renderWarnings(_layoutReport);
        if (!components.length) {
            fitBoard();
            return;
        }

        // Считаем степень каждого узла (сколько проводов в нём сходится).
        // Те же правила, что в 2D: рисуем mesh только при degree >= 3
        // (настоящий T/+-узел). Pass-through (2 провода) или одиночные
        // узлы — невидимые точки соединения, провода всё равно сходятся
        // в этой координате.
        const nodeDegree = new Map();
        connections.forEach(conn => {
            if (!conn.from || !conn.to) return;
            nodeDegree.set(conn.from.compId, (nodeDegree.get(conn.from.compId) || 0) + 1);
            nodeDegree.set(conn.to.compId, (nodeDegree.get(conn.to.compId) || 0) + 1);
        });

        // Bbox проверяет, попадает ли узел под другой компонент. Если да —
        // прячем узел: на реальной плате дорожки заходят на пятачки компонента
        // и место разветвления — это сам компонент, а не отдельная точка.
        function _isNodeUnderComponent(node) {
            const nx = (Number(node.x) || 0) + 30;
            const ny = (Number(node.y) || 0) + 20;
            for (const c of components) {
                if (c.id === node.id) continue;
                if (String(c.type || '').toLowerCase() === 'node') continue;
                const ccx = (Number(c.x) || 0) + 30;
                const ccy = (Number(c.y) || 0) + 20;
                const isVert = (((c.rotation || 0) % 180) + 180) % 180 === 90;
                const halfW = isVert ? 20 : 30;
                const halfH = isVert ? 30 : 20;
                if (Math.abs(nx - ccx) < halfW && Math.abs(ny - ccy) < halfH) return true;
            }
            return false;
        }

        const compLayoutById = new Map((_layoutReport.components || []).map(item => [item.id, item]));
        const duplicateCounts = new Map();
        components.forEach((comp) => {
            const key = String(comp.label || comp.designator || comp.ref || '').trim();
            if (key) duplicateCounts.set(key, (duplicateCounts.get(key) || 0) + 1);
        });
        const labelCounters = {};
        components.forEach(comp => {
            const placed = compLayoutById.get(comp.id);
            if (!placed) return;
            const typeName = String(comp.type || '').toLowerCase();
            // Пропускаем mesh у pass-through узлов и узлов под другими компонентами
            const isPassThroughNode = typeName === 'node' && (nodeDegree.get(comp.id) || 0) < 3;
            const isCoveredNode = typeName === 'node' && _isNodeUnderComponent(comp);
            if (isPassThroughNode || isCoveredNode) {
                return;
            }
            const p3 = _worldPoint(_layoutReport, placed.xMm, placed.yMm, 0);
            const label = _componentDisplayLabel(comp, labelCounters, duplicateCounts);
            comp._dolg3dRef = label;
            const mesh = makeForType(comp);
            _maybeAddDesignator(mesh, comp);
            mesh.position.set(p3.x, 0.08, p3.z);
            mesh.rotation.y = -(_num(comp.rotation, 0) * Math.PI / 180);
            if (comp.side === 'bottom') {
                mesh.scale.y *= -1;
                mesh.position.y = -_layoutReport.board.thicknessMm * UNIT_PER_MM - 0.08;
            }
            _root.add(mesh);
            // Сохраняем id на самом mesh для быстрого поиска при overlay-фичах
            // (thermal map, cross-probing подсветка). _componentHoverMeta его
            // не пишет, потому что hover показывает label/value, а не id.
            if (comp && comp.id !== undefined && comp.id !== null) {
                mesh.userData.dolgComponentId = comp.id;
                _componentMeshes[comp.id] = mesh;
            }
            _markHoverable(mesh, comp);

            if (typeName === 'node' || typeName === 'ground') return;
            const sprite = makeTextSprite(label, { compact: true });
            if (sprite) {
                sprite.position.set(p3.x, 1.86, p3.z);
                _root.add(sprite);
                _labelSprites.push(sprite);
            }
        });

        if (_hoverCallback) {
            const onMove = (event) => handleHoverMove(canvas, event);
            const onLeave = () => _hoverCallback(null);
            canvas.addEventListener('mousemove', onMove);
            canvas.addEventListener('mouseleave', onLeave);
            _disposeFns.push(() => {
                canvas.removeEventListener('mousemove', onMove);
                canvas.removeEventListener('mouseleave', onLeave);
            });
        }

        // Cross-probing reverse: клик в 3D → выбор того же компонента в 2D-схеме
        // через onSelect-callback. Подавляем клик при drag-вращении OrbitControls —
        // отслеживаем суммарный сдвиг мыши между mousedown и mouseup, и если он
        // больше порога — клик считаем drag-ом, а не выбором.
        if (_selectCallback) {
            let downX = 0, downY = 0, downAt = 0;
            const DRAG_THRESHOLD_PX = 4;
            const onDown = (event) => {
                downX = event.clientX;
                downY = event.clientY;
                downAt = Date.now();
            };
            const onUp = (event) => {
                const dx = Math.abs(event.clientX - downX);
                const dy = Math.abs(event.clientY - downY);
                if (dx + dy > DRAG_THRESHOLD_PX) return; // это был drag
                if (Date.now() - downAt > 600) return; // долгий клик — игнор
                // Measure mode: клик ставит точку на линейке, не выделяет компонент
                if (_handleMeasureClick(canvas, event)) return;
                const hit = pickComponentAt(canvas, event);
                if (hit && _selectCallback) {
                    try { _selectCallback(hit); } catch (e) { /* noop */ }
                }
            };
            canvas.addEventListener('mousedown', onDown);
            canvas.addEventListener('mouseup', onUp);
            _disposeFns.push(() => {
                canvas.removeEventListener('mousedown', onDown);
                canvas.removeEventListener('mouseup', onUp);
            });
        }

        fitBoard();
    }

    function pickComponentAt(canvas, event) {
        if (!_raycaster || !_pointer || !_camera || !_hoverables.length) return null;
        const rect = canvas.getBoundingClientRect();
        _pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        _pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
        _raycaster.setFromCamera(_pointer, _camera);
        const hits = _raycaster.intersectObjects(_hoverables, true);
        for (let i = 0; i < hits.length; i++) {
            const obj = hits[i].object;
            // Поднимаемся вверх по графу, пока не найдём mesh с dolgComponentId.
            let cursor = obj;
            while (cursor) {
                if (cursor.userData && cursor.userData.dolgComponentId !== undefined && cursor.userData.dolgComponentId !== null) {
                    return cursor.userData.dolgComponentId;
                }
                cursor = cursor.parent;
            }
        }
        return null;
    }

    // Measure tool: возвращает 3D-точку на поверхности платы (y=0 plane).
    // Используется для линейки — клик 2 точки → расстояние в мм.
    function pickWorldPointAt(canvas, event) {
        if (!_raycaster || !_pointer || !_camera) return null;
        const rect = canvas.getBoundingClientRect();
        _pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        _pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
        _raycaster.setFromCamera(_pointer, _camera);
        // Сначала пробуем попасть в сцену (любой объект)
        const hits = _raycaster.intersectObjects(_scene.children, true);
        if (hits.length > 0) {
            return hits[0].point.clone();
        }
        // Иначе пересекаем с плоскостью y=0 (поверхность PCB)
        const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
        const out = new THREE.Vector3();
        if (_raycaster.ray.intersectPlane(plane, out)) {
            return out;
        }
        return null;
    }

    // Measure tool state
    let _measureMode = false;
    let _measurePoint1 = null;  // THREE.Vector3 либо null
    let _measureLine = null;     // mesh линии между точками
    let _measureLabel = null;    // sprite с расстоянием в мм
    let _measureMarkers = [];    // sphere-markers в точках

    function _measureMakeMarker(pos) {
        const geom = new THREE.SphereGeometry(0.08, 12, 12);
        const mat = new THREE.MeshBasicMaterial({ color: 0xffd700 });
        const m = new THREE.Mesh(geom, mat);
        m.position.copy(pos);
        _scene.add(m);
        _measureMarkers.push(m);
        return m;
    }

    function _measureDrawLine(p1, p2) {
        // Удаляем старую линию если была
        if (_measureLine) { _scene.remove(_measureLine); _measureLine = null; }
        if (_measureLabel) { _scene.remove(_measureLabel); _measureLabel = null; }
        const geom = new THREE.BufferGeometry().setFromPoints([p1, p2]);
        const mat = new THREE.LineBasicMaterial({ color: 0xffd700, linewidth: 3 });
        _measureLine = new THREE.Line(geom, mat);
        _scene.add(_measureLine);
        // Подпись расстояния
        const distMm = p1.distanceTo(p2) / UNIT_PER_MM;
        const lbl = makeTextSprite(`📏 ${distMm.toFixed(2)} мм`, { compact: true });
        if (lbl) {
            lbl.position.copy(p1.clone().lerp(p2, 0.5));
            lbl.position.y += 0.4;
            _scene.add(lbl);
            _measureLabel = lbl;
        }
    }

    function _measureClear() {
        if (_measureLine) { _scene.remove(_measureLine); _measureLine = null; }
        if (_measureLabel) { _scene.remove(_measureLabel); _measureLabel = null; }
        for (const m of _measureMarkers) _scene.remove(m);
        _measureMarkers = [];
        _measurePoint1 = null;
    }

    function setMeasureMode(on) {
        _measureMode = !!on;
        if (!_measureMode) _measureClear();
    }
    function isMeasureMode() { return _measureMode; }

    // В onUp click handler'е добавляем ветку measure mode (см. ниже в init).
    function _handleMeasureClick(canvas, event) {
        if (!_measureMode) return false;
        const point = pickWorldPointAt(canvas, event);
        if (!point) return true;  // клик в пустоту — игнор
        if (!_measurePoint1) {
            _measureClear();
            _measurePoint1 = point;
            _measureMakeMarker(point);
        } else {
            _measureMakeMarker(point);
            _measureDrawLine(_measurePoint1, point);
            _measurePoint1 = null;  // следующий клик — новая измерение
        }
        return true;  // event обработан
    }

    // Лёгкая текстура с надписью (label) для спрайта над компонентом.
    function makeTextSprite(text, options) {
        if (!text) return null;
        const opts = options || {};
        const lines = String(text).split(/\n+/).filter(Boolean).slice(0, opts.compact ? 1 : 2);
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        canvas.width = opts.compact ? 512 : 288;
        canvas.height = opts.compact ? 112 : 72;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        if (!opts.compact) {
            ctx.fillStyle = 'rgba(20, 24, 40, 0.72)';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
        }
        lines.forEach((line, index) => {
            const first = index === 0;
            ctx.font = first
                ? `${opts.compact ? 52 : 38}px Arial`
                : '24px Arial';
            ctx.lineWidth = first ? 7 : 4;
            ctx.strokeStyle = opts.monochrome ? 'rgba(4, 8, 12, 0.98)' : 'rgba(5, 10, 20, 0.94)';
            ctx.fillStyle = opts.monochrome ? '#ffffff' : (first ? '#f4f8ff' : '#7fdbff');
            const y = lines.length === 1 ? canvas.height / 2 : (first ? canvas.height * 0.36 : canvas.height * 0.68);
            ctx.strokeText(line, canvas.width / 2, y);
            ctx.fillText(line, canvas.width / 2, y);
        });
        const tex = new THREE.CanvasTexture(canvas);
        tex.minFilter = THREE.LinearFilter;
        tex.anisotropy = 4;
        const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false, depthWrite: false });
        const sprite = new THREE.Sprite(mat);
        if (opts.compact) {
            sprite.scale.set(1.32, 0.30, 1);
        } else {
            sprite.scale.set(2, 0.5, 1);
        }
        sprite.renderOrder = 1000;
        _disposeFns.push(() => { tex.dispose(); mat.dispose(); });
        return sprite;
    }

    // Auto-rotate animation (для demo / защиты). При autoRotateEnabled
    // OrbitControls.autoRotate=true даёт плавное вращение вокруг target'а.
    let _autoRotateEnabled = false;
    function setAutoRotate(on, speed) {
        _autoRotateEnabled = !!on;
        if (_controls) {
            _controls.autoRotate = _autoRotateEnabled;
            _controls.autoRotateSpeed = typeof speed === 'number' ? speed : 2.0;
        }
    }
    function isAutoRotating() { return _autoRotateEnabled; }

    // Wireframe mode — все материалы переключаются в wireframe.
    // Сохраняем оригинальное состояние, чтобы можно было откатить.
    let _wireframeEnabled = false;
    const _wireframeBackup = new Map();
    function setWireframe(on) {
        _wireframeEnabled = !!on;
        if (!_scene) return;
        _scene.traverse((obj) => {
            if (obj.isMesh && obj.material) {
                const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
                mats.forEach((m, idx) => {
                    if (m.wireframe === undefined) return;
                    const key = obj.uuid + '|' + idx;
                    if (_wireframeEnabled) {
                        if (!_wireframeBackup.has(key)) _wireframeBackup.set(key, !!m.wireframe);
                        m.wireframe = true;
                    } else {
                        const prev = _wireframeBackup.get(key);
                        m.wireframe = prev != null ? prev : false;
                    }
                });
            }
        });
    }
    function isWireframe() { return _wireframeEnabled; }

    // Цвет фона сцены — dark/light/transparent для скриншотов под разные контексты.
    function setBackgroundColor(preset) {
        if (!_scene || !_renderer) return;
        // preset: 'dark' | 'light' | 'transparent' | '#hex'
        if (preset === 'transparent') {
            _scene.background = null;
            _renderer.setClearColor(0x000000, 0);
            return;
        }
        let color = 0x0e1320;  // dark default (DOLG cosmic)
        if (preset === 'light') color = 0xf5f7fb;
        else if (typeof preset === 'string' && preset.startsWith('#')) {
            color = parseInt(preset.slice(1), 16);
        }
        _scene.background = new THREE.Color(color);
        _renderer.setClearColor(color, 1.0);
    }

    // Batch screenshot: 4 канонических ракурса (iso/top/side/front), скачиваются
    // один за другим. Каждый — PNG ~50-200 КБ. Между сменой пресета нужно
    // дать 2 кадра renderer'у, иначе PNG зафиксирует предыдущую позицию.
    async function batchExportPng(prefix) {
        if (!_renderer || !_scene || !_camera) return [];
        const presets = ['iso', 'top', 'side', 'front'];
        const ts = new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-');
        const base = prefix || 'dolg-scheme-3d';
        const wasAutoRotate = _autoRotateEnabled;
        if (wasAutoRotate) setAutoRotate(false);  // фикс ракурса на время съёмки
        const out = [];
        for (const preset of presets) {
            setCameraPreset(preset);
            // 2 frame'а ожидания — пресет применён + контролы обновлены
            await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
            _renderer.render(_scene, _camera);
            const dataUrl = _renderer.domElement.toDataURL('image/png');
            const a = document.createElement('a');
            a.href = dataUrl;
            a.download = `${base}-${ts}-${preset}.png`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            out.push({ preset, dataUrl });
            // Небольшая пауза между загрузками, чтобы браузер не блокировал
            await new Promise(r => setTimeout(r, 400));
        }
        if (wasAutoRotate) setAutoRotate(true);
        return out;
    }

    function tick() {
        if (!_renderer || !_scene || !_camera) return;
        if (_controls) _controls.update();
        _renderer.render(_scene, _camera);
    }

    function handleHoverMove(canvas, event) {
        if (!_raycaster || !_pointer || !_camera || !_hoverables.length || !_hoverCallback) return;
        const rect = canvas.getBoundingClientRect();
        _pointer.x = ((event.clientX - rect.left) / Math.max(1, rect.width)) * 2 - 1;
        _pointer.y = -((event.clientY - rect.top) / Math.max(1, rect.height)) * 2 + 1;
        _raycaster.setFromCamera(_pointer, _camera);
        const hits = _raycaster.intersectObjects(_hoverables, true);
        const hit = hits.find(item => item.object && item.object.userData && item.object.userData.dolgComponent);
        if (!hit) {
            _hoverCallback(null);
            return;
        }
        _hoverCallback({
            ...hit.object.userData.dolgComponent,
            clientX: event.clientX,
            clientY: event.clientY,
        });
    }

    function resize(w, h) {
        if (!_renderer || !_camera) return;
        _camera.aspect = w / h;
        _camera.updateProjectionMatrix();
        _renderer.setSize(w, h, false);
    }

    function exportPng() {
        if (!_renderer) return null;
        // Принудительный render — иначе drawingBuffer может быть пустым.
        tick();
        return _renderer.domElement.toDataURL('image/png');
    }

    // GLB-экспорт: бинарный glTF 2.0 (ISO/IEC 12113:2022), один файл,
    // нативно открывается в <model-viewer> Google, Windows 3D-просмотрщике,
    // Blender/FreeCAD/Fusion 360. Используется для AR-предпросмотра, sharing
    // и вставки 3D в дипломный отчёт. Подписи-спрайты в экспорт не уходят:
    // GLTFExporter Sprite не сериализует, и это правильно — реальные CAD-tools
    // их всё равно не отобразят.
    //
    // Возвращает Promise<ArrayBuffer>; вызывающий сам решает,
    // делать ли Blob+URL.createObjectURL или скачивать через FileSaver.
    function exportGlb(options) {
        if (!_scene) return Promise.reject(new Error('Сцена 3D не инициализирована'));
        if (typeof THREE.GLTFExporter !== 'function') {
            return Promise.reject(new Error('THREE.GLTFExporter не загружен — добавьте lib/GLTFExporter.js'));
        }
        const opts = Object.assign({
            binary: true,
            // Спрайты-подписи не годятся для GLB; исключаем по умолчанию.
            // Caller может явно включить через onlySelected/visible-флаги.
        }, options || {});
        // Временно скрываем спрайты, чтобы они не попали в GLB.
        const restoreSprites = [];
        _scene.traverse((obj) => {
            if (obj && obj.isSprite) {
                restoreSprites.push({ obj: obj, visible: obj.visible });
                obj.visible = false;
            }
        });
        const exporter = new THREE.GLTFExporter();
        return new Promise(function (resolve, reject) {
            try {
                exporter.parse(_scene, function (result) {
                    restoreSprites.forEach(function (item) { item.obj.visible = item.visible; });
                    if (result instanceof ArrayBuffer) {
                        resolve(result);
                    } else {
                        // Текстовая форма glTF — превращаем в ArrayBuffer JSON-bytes.
                        const json = JSON.stringify(result);
                        const enc = new TextEncoder();
                        resolve(enc.encode(json).buffer);
                    }
                }, function (err) {
                    restoreSprites.forEach(function (item) { item.obj.visible = item.visible; });
                    reject(err);
                }, opts);
            } catch (e) {
                restoreSprites.forEach(function (item) { item.obj.visible = item.visible; });
                reject(e);
            }
        });
    }

    // ----- Thermal map overlay -----
    // Накладывает на 3D-сцену полупрозрачные «нимбы» вокруг компонентов,
    // окрашенные по P/TDP ratio из Pro-аналитики (см. simulation.html
    // `computeThermal()` и `_lastSimPowers`). powerMap имеет форму
    //   { compId: { power_w, limit_w, ratio, label, type } }
    // где ratio = power_w / limit_w. Цвет считается локально, чтобы не
    // зависеть от глобальной thermalRatioToColor из шаблона.
    //
    // Реализация умышленно НЕ меняет material компонентов (они shared,
    // см. _sharedMat выше). Вместо этого добавляем child-mesh — сфера-аура,
    // которая чистится по флагу userData._isThermal.
    function _thermalColorForRatio(ratio) {
        if (!isFinite(ratio) || ratio <= 0) return null;
        // 0–0.3 — зелёный; 0.3–0.7 — жёлтый; 0.7–1 — оранжевый; >1 — красный.
        if (ratio < 0.3) return new THREE.Color(0x2eb872);
        if (ratio < 0.7) return new THREE.Color(0xd6c93b);
        if (ratio < 1.0) return new THREE.Color(0xe6802b);
        return new THREE.Color(0xd93636);
    }

    function setThermalOverlay(powerMap) {
        if (!_scene || !_root || !powerMap) return { ok: false, applied: 0 };
        clearThermalOverlay();
        const box = new THREE.Box3();
        let applied = 0;
        Object.keys(powerMap).forEach((key) => {
            const entry = powerMap[key];
            if (!entry || !isFinite(entry.ratio) || entry.ratio <= 0) return;
            const mesh = _componentMeshes[key];
            if (!mesh) return;
            const color = _thermalColorForRatio(entry.ratio);
            if (!color) return;
            // Bounding box компонента в мировых координатах → нимб масштабируем
            // под него, чтобы аура не теряла связь с реальным размером.
            box.setFromObject(mesh);
            const size = new THREE.Vector3();
            box.getSize(size);
            const center = new THREE.Vector3();
            box.getCenter(center);
            const radius = Math.max(size.x, size.z) * 0.78 + 0.35;
            const geo = new THREE.SphereGeometry(radius, 24, 12);
            const mat = new THREE.MeshBasicMaterial({
                color: color,
                transparent: true,
                opacity: Math.min(0.55, 0.2 + entry.ratio * 0.35),
                depthWrite: false,
                blending: THREE.AdditiveBlending,
            });
            const halo = new THREE.Mesh(geo, mat);
            halo.position.set(center.x, Math.max(center.y, 0.4), center.z);
            halo.userData._isThermal = true;
            halo.userData.dolgComponentId = key;
            halo.userData.thermalEntry = {
                ratio: entry.ratio,
                power_w: entry.power_w,
                limit_w: entry.limit_w,
                label: entry.label,
            };
            _root.add(halo);
            _thermalOverlayObjects.push(halo);
            applied += 1;
        });
        return { ok: true, applied: applied };
    }

    function clearThermalOverlay() {
        _thermalOverlayObjects.forEach((obj) => {
            if (obj.parent) obj.parent.remove(obj);
            if (obj.geometry) obj.geometry.dispose();
            if (obj.material) obj.material.dispose();
        });
        _thermalOverlayObjects = [];
    }

    function hasThermalOverlay() {
        return _thermalOverlayObjects.length > 0;
    }

    // ----- Cross-probing 2D↔3D -----
    // 2D-схема вызывает highlightComponent(id) когда пользователь выбирает
    // компонент в редакторе. Мы рисуем светящийся cyan-каркас вокруг bbox
    // соответствующего mesh-а — visible через любую глубину сцены
    // (depthTest=false), чтобы пользователь не терял отметку при вращении.
    // Старый highlight удаляется автоматически.
    function highlightComponent(componentId) {
        if (!_scene || !_root) return false;
        if (componentId === null || componentId === undefined) {
            clearHighlight();
            return false;
        }
        const mesh = _componentMeshes[componentId] || _componentMeshes[String(componentId)];
        if (!mesh) {
            // Компонент мог не пройти в layout — это не ошибка, просто очищаем.
            clearHighlight();
            return false;
        }
        clearHighlight();
        const box = new THREE.Box3().setFromObject(mesh);
        const size = new THREE.Vector3();
        box.getSize(size);
        const center = new THREE.Vector3();
        box.getCenter(center);
        // Каркас немного больше bbox — на 0.25 ед. с каждой стороны.
        const w = size.x + 0.5;
        const h = size.y + 0.5;
        const d = size.z + 0.5;
        const geo = new THREE.BoxGeometry(w, h, d);
        const edges = new THREE.EdgesGeometry(geo);
        const mat = new THREE.LineBasicMaterial({
            color: 0x00e5ff,
            transparent: true,
            opacity: 0.95,
            depthTest: false,
        });
        const wire = new THREE.LineSegments(edges, mat);
        wire.position.set(center.x, Math.max(center.y, 0.4), center.z);
        wire.renderOrder = 999;
        wire.userData._isHighlight = true;
        wire.userData.dolgComponentId = componentId;
        // Геометрия box больше не нужна — мы используем только EdgesGeometry.
        geo.dispose();
        _root.add(wire);
        _highlightMesh = wire;
        _highlightedId = componentId;
        return true;
    }

    function clearHighlight() {
        if (_highlightMesh) {
            if (_highlightMesh.parent) _highlightMesh.parent.remove(_highlightMesh);
            if (_highlightMesh.geometry) _highlightMesh.geometry.dispose();
            if (_highlightMesh.material) _highlightMesh.material.dispose();
            _highlightMesh = null;
        }
        _highlightedId = null;
    }

    function getHighlightedComponentId() {
        return _highlightedId;
    }

    // Удобный shortcut: триггерит скачивание `.glb` файла в браузере.
    function downloadGlb(filename) {
        const name = (filename || 'dolg-pcb-3d.glb').replace(/[^a-zA-Z0-9._-]+/g, '_');
        return exportGlb({ binary: true }).then(function (buffer) {
            const blob = new Blob([buffer], { type: 'model/gltf-binary' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = name;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            // Освобождаем URL после клика — браузер уже инициировал загрузку.
            setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
            return { ok: true, size: buffer.byteLength, filename: name };
        });
    }

    // Пресеты камеры — три классических ракурса. Дистанция выбирается из
    // bbox корня сцены, чтобы влезала вся плата при любом её размере.
    function setCameraPreset(preset) {
        if (!_camera || !_root || !_controls) return;
        // Рассчитываем размер сцены через bounding box рекурсивно.
        const box = new THREE.Box3().setFromObject(_root);
        const size = new THREE.Vector3();
        box.getSize(size);
        const center = new THREE.Vector3();
        box.getCenter(center);
        const span = Math.max(size.x, size.z, 6);
        const d = span * 1.1;
        switch (preset) {
            case 'top':
                _camera.position.set(center.x, center.y + d * 1.4, center.z + 0.001);
                break;
            case 'side':
                _camera.position.set(center.x + d * 1.4, center.y + d * 0.2, center.z);
                break;
            case 'front':
                _camera.position.set(center.x, center.y + d * 0.3, center.z + d * 1.4);
                break;
            case 'iso':
            default:
                _camera.position.set(center.x + d * 0.7, center.y + d * 0.85, center.z + d * 0.9);
                break;
        }
        _controls.target.copy(center);
        _controls.update();
    }

    // Toggle видимости подписей-спрайтов. По умолчанию подписи on; вызвать
    // setLabelsVisible(false) — скрыть для «чистого» 3D-вида (например, для PNG-снимка).
    function setLabelsVisible(visible) {
        _labelSprites.forEach((s) => { s.visible = !!visible; });
    }

    function setLayerVisible(layer, visible) {
        if (layer === 'labels') {
            setLabelsVisible(visible);
            return;
        }
        const group = _layerGroups && _layerGroups[layer];
        if (group) group.visible = !!visible;
    }

    // ----- 2.5: Прозрачность слоёв (per-layer opacity) -----
    // Меняет opacity всех mesh-ей в группе слоя. Shared-материалы (MAT.*)
    // клонируются на лету, чтобы изменение opacity для слоя «верхняя медь»
    // не задело тот же материал, используемый в другом проекте после
    // dispose() и повторного open(). Помеченные `userData._layerClone = true`
    // клоны диспозятся при dispose() как обычные не-shared материалы.
    function setLayerOpacity(layer, opacity) {
        const group = _layerGroups && _layerGroups[layer];
        if (!group) return;
        const clamped = Math.max(0, Math.min(1, Number(opacity)));
        group.traverse((obj) => {
            if (!obj || !obj.isMesh || !obj.material) return;
            const mats = Array.isArray(obj.material) ? obj.material.slice() : [obj.material];
            const replaced = mats.map((m) => {
                if (m && m.userData && m.userData._shared) {
                    const clone = m.clone();
                    clone.userData = Object.assign({}, m.userData, { _shared: false, _layerClone: true });
                    return clone;
                }
                return m;
            });
            obj.material = Array.isArray(obj.material) ? replaced : replaced[0];
            replaced.forEach((m) => {
                if (!m) return;
                m.transparent = clamped < 0.999;
                m.opacity = clamped;
                m.depthWrite = clamped >= 0.999;
                m.needsUpdate = true;
            });
        });
    }

    // Solo-mode: оставить полную видимость одного слоя, остальные — 0.2.
    // Удобно для «покажи только медь верха» — учебная фича без отдельной кнопки
    // на каждый слой.
    function setSoloLayer(layer) {
        if (!_layerGroups) return;
        Object.keys(_layerGroups).forEach((key) => {
            setLayerOpacity(key, key === layer ? 1.0 : 0.2);
        });
    }

    // Сброс всех слоёв на opacity=1 — снимает solo-mode и любую частичную
    // прозрачность.
    function resetLayerOpacity() {
        if (!_layerGroups) return;
        Object.keys(_layerGroups).forEach((key) => setLayerOpacity(key, 1.0));
    }

    // ----- 2.6: Explode view (разнести слои в воздухе) -----
    // factor=0 — обычный вид; factor=1 — top и компоненты подняты на 6.5 ед.
    // вверх, bottom опущен на 3.5 вниз, dimensions сдвинуты ещё выше для
    // подписей. Промежуточные значения интерполируются. Сохраняем оригинальные
    // позиции в `userData._origY` при первом вызове, чтобы можно было
    // вернуться к нулю.
    function setExplodeFactor(factor) {
        if (!_root) return;
        const f = Math.max(0, Math.min(1.4, Number(factor) || 0));
        // Верхний слой PCB + всё, что НЕ нижнего слоя и НЕ подложка/размер/предупреждения
        // — это «вершина» стека. Поднимаем её.
        const TOP_LIFT = 6.5;
        const BOTTOM_DROP = 3.5;
        const DIM_LIFT = 9.0;

        const layerLift = {
            top: TOP_LIFT,
            bottom: -BOTTOM_DROP,
            ground: 0,         // ground-fill остаётся в плоскости подложки
            dimensions: DIM_LIFT,
            warnings: TOP_LIFT + 0.6,
        };

        Object.keys(layerLift).forEach((layer) => {
            const grp = _layerGroups[layer];
            if (!grp) return;
            if (grp.userData._origY === undefined) grp.userData._origY = grp.position.y;
            grp.position.y = grp.userData._origY + layerLift[layer] * f;
        });

        // Компоненты — это прямые дети _root, не члены layerGroups. Их
        // userData.dolgComponentId выставлен в init() (см. _componentMeshes).
        Object.keys(_componentMeshes).forEach((id) => {
            const m = _componentMeshes[id];
            if (!m) return;
            if (m.userData._origY === undefined) m.userData._origY = m.position.y;
            const isBottomSide = m.userData._isBottomSide === true;
            const lift = isBottomSide ? -BOTTOM_DROP : TOP_LIFT;
            m.position.y = m.userData._origY + lift * f;
        });

        // Сбрасываем thermal/highlight overlay — их Y расчитан от bbox исходного
        // mesh, который только что переехал. Caller должен обновить вручную
        // при необходимости.
        if (_thermalOverlayObjects && _thermalOverlayObjects.length) {
            // Простая стратегия — спрятать overlay при explode > 0.05.
            const hide = f > 0.05;
            _thermalOverlayObjects.forEach((obj) => { obj.visible = !hide; });
        }
    }

    // ----- 2.4 lite: Flip (перевернуть плату 180° по X) -----
    // Поворачивает корень сцены, чтобы посмотреть «снизу» — компоненты на
    // bottom side становятся видны сверху. Камера остаётся на месте, что
    // выгоднее для пользователя, чем вращение camera.
    function setFlipped(flipped) {
        if (!_root) return;
        const target = flipped ? Math.PI : 0;
        _root.rotation.x = target;
        // Камеру не двигаем — пользователь привык к OrbitControls и сам
        // докрутит, если нужно. Но обновим controls.target.y чтобы фокус
        // оставался по центру платы.
        if (_controls) _controls.update();
    }

    function isFlipped() {
        return _root ? Math.abs(_root.rotation.x) > 0.5 : false;
    }

    function toggleFlipped() {
        setFlipped(!isFlipped());
        return isFlipped();
    }

    function fitBoard() {
        setCameraPreset('iso');
    }

    function getBoardReport() {
        return _layoutReport ? JSON.parse(JSON.stringify(_layoutReport)) : null;
    }

    function dispose() {
        _disposeFns.forEach(fn => { try { fn(); } catch (e) {} });
        _disposeFns = [];
        if (_root) {
            _root.traverse(obj => {
                if (obj.geometry) obj.geometry.dispose();
                if (obj.material) {
                    const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
                    // Shared MAT.* помечены userData._shared — их не диспозим,
                    // иначе следующий open() получит сломанные шейдеры.
                    mats.forEach(m => {
                        if (!m.userData || !m.userData._shared) m.dispose();
                    });
                }
            });
        }
        if (_renderer) _renderer.dispose();
        _scene = _camera = _renderer = _controls = _root = null;
        // Сцена мертва — async GLTFLoader callbacks увидят null и не тронут DOM.
        _lib.sceneRoot = null;
        _labelSprites = [];
        _layerGroups = {};
        _componentMeshes = {};
        _thermalOverlayObjects = [];
        _highlightedId = null;
        _highlightMesh = null;
        _layoutReport = null;
        _hoverables = [];
        _raycaster = null;
        _pointer = null;
        _hoverCallback = null;
        _selectCallback = null;
    }

    window.DolgScheme3D = {
        init,
        tick,
        resize,
        exportPng,
        exportGlb,
        downloadGlb,
        setThermalOverlay,
        clearThermalOverlay,
        hasThermalOverlay,
        highlightComponent,
        clearHighlight,
        getHighlightedComponentId,
        dispose,
        setCameraPreset,
        setLabelsVisible,
        setLayerVisible,
        setLayerOpacity,
        setSoloLayer,
        resetLayerOpacity,
        setExplodeFactor,
        setFlipped,
        isFlipped,
        toggleFlipped,
        fitBoard,
        getBoardReport,
        computeBoardLayout,
        // Новые 3D-фичи (2026-05-29) для defense:
        setAutoRotate,
        isAutoRotating,
        setWireframe,
        isWireframe,
        setBackgroundColor,
        batchExportPng,
        // EDA-стандарт пресеты — пробрасываем из _dolg3dLib (materials.js)
        // для единого API на стороне UI/cad.
        setSoldermask: _lib.applySoldermaskPreset,
        setPadFinish: _lib.applyPadFinishPreset,
        setSilk: _lib.applySilkPreset,
        SOLDERMASK_PRESETS: _lib.SOLDERMASK_PRESETS,
        PAD_FINISH_PRESETS: _lib.PAD_FINISH_PRESETS,
        SILK_PRESETS: _lib.SILK_PRESETS,
        // Measure tool: клик 2 точки → расстояние в мм
        setMeasureMode,
        isMeasureMode,
    };
})(window);
