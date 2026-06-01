// =============================================================================
// scheme-3d-components.js — процедурные модели типовых корпусов компонентов.
// =============================================================================
// Вынесено из scheme-3d.js (фаза 1.1 рефакторинга). Самостоятельный слой:
// все функции принимают компонент или footprint, возвращают THREE.Group.
// Не имеют доступа к scene/state главного модуля; внешняя GLTF-модель
// добавляется в дерево только через lib.sceneRoot, которое выставляется
// главным файлом в init() и обнуляется в dispose().
//
// Зависимости (через window._dolg3dLib, заполняется scheme-3d-materials.js):
//   - MAT, RESISTOR_BAND_COLORS, resistorBands, BOARD_DEFAULTS, UNIT_PER_MM
//
// Экспорт (в window._dolg3dLib):
//   _num, _round3, _snapUp                — math helpers
//   _normPackage, _pinCountFromPackage    — footprint parsing
//   footprintForComponent(comp)           → footprint descriptor
//   _componentCenterPx(comp)              → world XY центра компонента
//   _externalModelUrl(comp)               → URL внешней GLTF-модели или ''
//   makeForType(comp)                     → THREE.Group подходящего корпуса
//   sceneRoot (read/write)                — main выставляет в init/dispose,
//                                           чтобы tryAttachExternalModel мог
//                                           проверить, жива ли сцена
// =============================================================================

(function (window) {
    'use strict';

    if (typeof THREE === 'undefined') {
        console.error('[scheme-3d-components] THREE не загружен');
        return;
    }

    var lib = window._dolg3dLib = window._dolg3dLib || {};

    // ----- Импорт из materials-модуля -----
    var MAT = lib.MAT;
    var RESISTOR_BAND_COLORS = lib.RESISTOR_BAND_COLORS;
    var resistorBands = lib.resistorBands;
    var BOARD_DEFAULTS = lib.BOARD_DEFAULTS;
    var UNIT_PER_MM = lib.UNIT_PER_MM;

    if (!MAT) {
        console.error('[scheme-3d-components] MAT не загружен — подключите scheme-3d-materials.js до этого скрипта');
        return;
    }

    // ----- Math helpers -----
    function _num(value, fallback) {
        var n = Number(value);
        return Number.isFinite(n) ? n : fallback;
    }

    function _round3(value) {
        return Math.round(value * 1000) / 1000;
    }

    function _snapUp(value, grid) {
        var g = Math.max(1, _num(grid, BOARD_DEFAULTS.gridMm));
        return Math.ceil(value / g) * g;
    }

    // ----- Footprint detection -----
    function _normPackage(comp) {
        var params = comp.catalog_parameters || comp.parameters || {};
        return String(
            comp.package ||
            comp.footprint ||
            comp.catalog_package ||
            comp.package_type ||
            params.package ||
            params.footprint ||
            params.package_type ||
            ''
        ).trim().toUpperCase();
    }

    function _pinCountFromPackage(pkg, fallback) {
        var m = String(pkg || '').match(/(?:DIP|SOIC|SOP|TSSOP|SSOP|QFP|QFN|SOT)-?\s*(\d+)/i);
        return m ? Math.max(2, parseInt(m[1], 10)) : fallback;
    }

    function footprintForComponent(comp) {
        var type = String(comp.type || '').toLowerCase();
        var pkg = _normPackage(comp);
        var params = comp.catalog_parameters || comp.parameters || {};
        var body = params.body_mm || comp.body_mm;
        if (body && Number(body.w || body.width) && Number(body.h || body.height)) {
            return {
                kind: 'custom',
                package: pkg || 'CUSTOM',
                widthMm: _num(body.w || body.width, 8),
                heightMm: _num(body.h || body.height, 5),
                height3d: _num(body.z || body.height_z || body.depth, 1.2),
                pins: _pinCountFromPackage(pkg, 2),
            };
        }
        if (/0805|0603|1206|1210|0402|SMD|CHIP/.test(pkg)) {
            var dims = pkg.indexOf('1206') >= 0 ? [3.2, 1.6] : pkg.indexOf('0603') >= 0 ? [1.6, 0.8] : [2.0, 1.25];
            return { kind: 'smd-chip', package: pkg || 'SMD', widthMm: dims[0], heightMm: dims[1], height3d: 0.6, pins: 2 };
        }
        if (/DIP/.test(pkg) || type === 'ic') {
            var pins = _pinCountFromPackage(pkg, 8);
            return { kind: 'dip', package: pkg || ('DIP-' + pins), widthMm: Math.max(9, pins * 1.3), heightMm: 7.6, height3d: 3.2, pins: pins };
        }
        if (/SOIC|SOP|TSSOP|SSOP/.test(pkg)) {
            var pinsS = _pinCountFromPackage(pkg, 8);
            return { kind: 'soic', package: pkg, widthMm: Math.max(5, pinsS * 0.75), heightMm: /TSSOP|SSOP/.test(pkg) ? 4.4 : 5.4, height3d: 1.3, pins: pinsS };
        }
        if (/TO-220/.test(pkg)) return { kind: 'to220', package: pkg, widthMm: 10.2, heightMm: 4.6, height3d: 9.5, pins: 3 };
        if (/TO-92/.test(pkg) || type === 'transistor' || type === 'npn' || type === 'pnp') {
            return { kind: 'to92', package: pkg || 'TO-92', widthMm: 5.2, heightMm: 4.2, height3d: 5.0, pins: 3 };
        }
        if (/SOT-23/.test(pkg)) return { kind: 'sot23', package: pkg, widthMm: 2.9, heightMm: 1.6, height3d: 1.1, pins: 3 };
        if (/CONNECTOR|HEADER|TERMINAL|КЛЕММ|РАЗЪ/.test(pkg) || /connector|terminal/.test(type)) {
            var pinsT = _pinCountFromPackage(pkg, Math.max(2, (comp.ports || []).length || 2));
            return { kind: 'terminal', package: pkg || 'TERMINAL', widthMm: pinsT * 5.0, heightMm: 8.0, height3d: 5.0, pins: pinsT };
        }
        var byType = {
            resistor:   { kind: 'axial', package: pkg || 'AXIAL', widthMm: 10, heightMm: 3.2, height3d: 2.8, pins: 2 },
            diode:      { kind: 'axial-diode', package: pkg || 'DO-41', widthMm: 8, heightMm: 3, height3d: 2.4, pins: 2 },
            capacitor:  { kind: 'radial-cap', package: pkg || 'RADIAL', widthMm: 5, heightMm: 5, height3d: 8, pins: 2 },
            led:        { kind: 'led', package: pkg || 'LED-5MM', widthMm: 5, heightMm: 5, height3d: 7, pins: 2 },
            inductor:   { kind: 'axial-inductor', package: pkg || 'AXIAL', widthMm: 9, heightMm: 4, height3d: 3.4, pins: 2 },
            battery:    { kind: 'battery', package: pkg || 'BATTERY', widthMm: 18, heightMm: 12, height3d: 8, pins: 2 },
            switch:     { kind: 'switch', package: pkg || 'SWITCH', widthMm: 10, heightMm: 6, height3d: 4, pins: 2 },
            ground:     { kind: 'ground', package: 'GND', widthMm: 4, heightMm: 4, height3d: 1, pins: 1 },
            node:       { kind: 'node', package: 'JUNCTION', widthMm: 2, heightMm: 2, height3d: 0.4, pins: 1 },
        };
        return byType[type] || { kind: 'generic', package: pkg || 'GENERIC', widthMm: 8, heightMm: 5, height3d: 2, pins: Math.max(2, (comp.ports || []).length || 2) };
    }

    function _componentCenterPx(comp) {
        return {
            x: _num(comp.x, 0) + 30,
            y: _num(comp.y, 0) + 20,
        };
    }

    function _externalModelUrl(comp) {
        var params = comp.catalog_parameters || comp.parameters || {};
        return comp.model_3d_url || params.model_3d_url || params.model3d || '';
    }

    // ----- Procedural component models -----
    // Загнутая ножка through-hole компонента: тонкий торец вдоль оси корпуса,
    // потом 90° вниз в плату.
    function _addBentLead(group, axEnd, bodyY, radius) {
        var r = radius || 0.05;
        var sign = axEnd >= 0 ? 1 : -1;
        var stubLen = 0.25;
        var bendX = axEnd + sign * stubLen;
        var stub = new THREE.Mesh(new THREE.CylinderGeometry(r, r, stubLen, 8), MAT.wire);
        stub.rotation.z = Math.PI / 2;
        stub.position.set(axEnd + sign * stubLen / 2, bodyY, 0);
        group.add(stub);
        var bend = new THREE.Mesh(new THREE.SphereGeometry(r * 1.05, 8, 6), MAT.wire);
        bend.position.set(bendX, bodyY, 0);
        group.add(bend);
        var drop = new THREE.Mesh(new THREE.CylinderGeometry(r, r, bodyY, 8), MAT.wire);
        drop.position.set(bendX, bodyY / 2, 0);
        group.add(drop);
    }

    function makeResistor(value) {
        var g = new THREE.Group();
        var R = 0.3, L = 1.6;
        var body = new THREE.Mesh(new THREE.CylinderGeometry(R, R, L, 20), MAT.beige);
        body.rotation.z = Math.PI / 2;
        body.position.y = 0.35;
        g.add(body);
        var bands = resistorBands(value);
        bands.forEach(function (digit, i) {
            var c = RESISTOR_BAND_COLORS[Math.min(9, Math.max(0, digit))];
            var stripe = new THREE.Mesh(
                new THREE.CylinderGeometry(R * 1.02, R * 1.02, 0.12, 16),
                new THREE.MeshStandardMaterial({ color: c })
            );
            stripe.rotation.z = Math.PI / 2;
            stripe.position.set(-L * 0.3 + i * 0.27, 0.35, 0);
            g.add(stripe);
        });
        var tol = new THREE.Mesh(
            new THREE.CylinderGeometry(R * 1.02, R * 1.02, 0.12, 16),
            new THREE.MeshStandardMaterial({ color: 0xc9a227 })
        );
        tol.rotation.z = Math.PI / 2;
        tol.position.set(L * 0.4, 0.35, 0);
        g.add(tol);
        _addBentLead(g, -L / 2, 0.35, 0.05);
        _addBentLead(g,  L / 2, 0.35, 0.05);
        return g;
    }

    function makeLED(color) {
        var g = new THREE.Group();
        var mat = new THREE.MeshStandardMaterial({
            color: color || 0xff3344, transparent: true, opacity: 0.85, roughness: 0.2,
            emissive: color || 0xff3344, emissiveIntensity: 0.25,
        });
        var body = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.3, 0.8, 20), mat);
        body.position.y = 0.4;
        g.add(body);
        var dome = new THREE.Mesh(
            new THREE.SphereGeometry(0.3, 20, 12, 0, Math.PI * 2, 0, Math.PI / 2),
            mat
        );
        dome.position.y = 0.8;
        g.add(dome);
        var leads = [-0.12, 0.12];
        for (var i = 0; i < leads.length; i++) {
            var lead = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.4, 8), MAT.wire);
            lead.position.set(leads[i], 0.2, 0);
            g.add(lead);
        }
        return g;
    }

    function makeCapacitor(value) {
        var g = new THREE.Group();
        var radius = 0.36 + Math.min(0.25, Math.log10(Math.max(1, value || 1)) * 0.04);
        var height = 0.85 + Math.min(0.7, Math.log10(Math.max(1, value || 1)) * 0.08);
        var body = new THREE.Mesh(
            new THREE.CylinderGeometry(radius, radius, height, 20),
            MAT.electroBlue
        );
        body.position.y = height / 2;
        g.add(body);
        var stripeH = height * 0.18;
        var stripe = new THREE.Mesh(
            new THREE.CylinderGeometry(radius * 1.01, radius * 1.01, stripeH, 20, 1, true,
                                       Math.PI * 0.6, Math.PI * 0.8),
            MAT.electroBand
        );
        stripe.position.y = height * 0.4;
        g.add(stripe);
        var rotations = [0, Math.PI / 2];
        for (var r = 0; r < rotations.length; r++) {
            var notch = new THREE.Mesh(
                new THREE.BoxGeometry(radius * 1.6, 0.04, 0.06),
                new THREE.MeshStandardMaterial({ color: 0x222244 })
            );
            notch.position.y = height + 0.02;
            notch.rotation.y = rotations[r];
            g.add(notch);
        }
        var leadXs = [-0.2, 0.2];
        for (var li = 0; li < leadXs.length; li++) {
            var lead = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.4, 6), MAT.wire);
            lead.position.set(leadXs[li], -0.2, 0);
            g.add(lead);
        }
        return g;
    }

    function makeDiode() {
        var g = new THREE.Group();
        var R = 0.2, L = 1.0;
        var body = new THREE.Mesh(
            new THREE.CylinderGeometry(R, R, L, 16),
            new THREE.MeshStandardMaterial({ color: 0x1a1a1a, roughness: 0.6 })
        );
        body.rotation.z = Math.PI / 2;
        body.position.y = 0.3;
        g.add(body);
        var band = new THREE.Mesh(
            new THREE.CylinderGeometry(R * 1.04, R * 1.04, 0.10, 16),
            new THREE.MeshStandardMaterial({ color: 0xeeeeee })
        );
        band.rotation.z = Math.PI / 2;
        band.position.set(L * 0.32, 0.3, 0);
        g.add(band);
        _addBentLead(g, -L / 2, 0.3, 0.04);
        _addBentLead(g,  L / 2, 0.3, 0.04);
        return g;
    }

    function makeBattery() {
        var g = new THREE.Group();
        var body = new THREE.Mesh(new THREE.BoxGeometry(1.6, 1.0, 0.7), MAT.battery);
        body.position.y = 0.5;
        g.add(body);
        var termXs = [-0.6, 0.6];
        for (var i = 0; i < termXs.length; i++) {
            var term = new THREE.Mesh(
                new THREE.CylinderGeometry(0.10, 0.10, 0.2, 12),
                MAT.pinSilver
            );
            term.position.set(termXs[i], 1.1, 0);
            g.add(term);
        }
        var signMat = new THREE.MeshStandardMaterial({ color: 0xffffff });
        var plusH = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.03, 0.03), signMat);
        plusH.position.set(-0.6, 1.22, 0);
        g.add(plusH);
        var plusV = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.03, 0.2), signMat);
        plusV.position.set(-0.6, 1.22, 0);
        g.add(plusV);
        var minus = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.03, 0.03), signMat);
        minus.position.set(0.6, 1.22, 0);
        g.add(minus);
        return g;
    }

    function makeIC() {
        var g = new THREE.Group();
        var body = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.3, 1.1), MAT.plasticBlack);
        body.position.y = 0.3;
        g.add(body);
        var key = new THREE.Mesh(
            new THREE.SphereGeometry(0.06, 8, 4, 0, Math.PI * 2, 0, Math.PI / 2),
            new THREE.MeshStandardMaterial({ color: 0x333333 })
        );
        key.position.set(-0.7, 0.45, -0.4);
        g.add(key);
        for (var side = 0; side < 2; side++) {
            for (var i = 0; i < 4; i++) {
                var pin = new THREE.Mesh(
                    new THREE.BoxGeometry(0.10, 0.4, 0.06),
                    MAT.pinSilver
                );
                pin.position.set(-0.7 + i * 0.5, 0.1, side === 0 ? -0.6 : 0.6);
                g.add(pin);
            }
        }
        return g;
    }

    function makeInductor() {
        var g = new THREE.Group();
        var R = 0.3, L = 1.0;
        var body = new THREE.Mesh(
            new THREE.CylinderGeometry(R, R, L, 16),
            MAT.bobbin
        );
        body.rotation.z = Math.PI / 2;
        body.position.y = 0.35;
        g.add(body);
        for (var i = 0; i < 5; i++) {
            var turn = new THREE.Mesh(
                new THREE.TorusGeometry(R * 1.05, 0.025, 6, 16),
                MAT.wire
            );
            turn.rotation.y = Math.PI / 2;
            turn.position.set(-L * 0.4 + i * (L * 0.2), 0.35, 0);
            g.add(turn);
        }
        _addBentLead(g, -L / 2, 0.35, 0.04);
        _addBentLead(g,  L / 2, 0.35, 0.04);
        return g;
    }

    function makeTransistor() {
        var g = new THREE.Group();
        var R = 0.34;
        var H = 0.82;
        var shape = new THREE.Shape();
        shape.moveTo(0, -R);
        shape.lineTo(0, R);
        shape.absarc(0, 0, R, Math.PI / 2, 3 * Math.PI / 2, false);
        shape.closePath();
        var body = new THREE.Mesh(
            new THREE.ExtrudeGeometry(shape, { depth: H, bevelEnabled: true, bevelSize: 0.025, bevelThickness: 0.02, curveSegments: 18 }),
            MAT.plasticBlack
        );
        body.rotation.x = -Math.PI / 2;
        body.position.set(0, H + 0.05, -H / 2);
        g.add(body);

        var front = new THREE.Mesh(new THREE.BoxGeometry(0.08, H * 0.78, H * 0.92), MAT.plasticBlack);
        front.position.set(0.03, H + 0.05, -H / 2);
        g.add(front);

        var leadXs = [-0.22, 0, 0.22];
        for (var li = 0; li < leadXs.length; li++) {
            var x = leadXs[li];
            var lead = new THREE.Mesh(new THREE.CylinderGeometry(0.026, 0.026, 0.62, 8), MAT.pinSilver);
            lead.position.set(x, 0.31, 0.08);
            g.add(lead);
            var foot = new THREE.Mesh(new THREE.BoxGeometry(0.045, 0.035, 0.34), MAT.pinSilver);
            foot.position.set(x, 0.025, 0.24);
            g.add(foot);
        }

        var mark = new THREE.Mesh(new THREE.BoxGeometry(0.33, 0.02, 0.035), MAT.silkscreen);
        mark.position.set(0, H * 1.58, -0.16);
        g.add(mark);
        return g;
    }

    function makeTO220() {
        var g = new THREE.Group();
        var tab = new THREE.Mesh(new THREE.BoxGeometry(1.28, 1.38, 0.16), MAT.pinSilver);
        tab.position.set(0, 1.05, -0.12);
        g.add(tab);
        var hole = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.13, 0.18, 24), MAT.hole);
        hole.rotation.x = Math.PI / 2;
        hole.position.set(0, 1.35, -0.22);
        g.add(hole);
        var body = new THREE.Mesh(new THREE.BoxGeometry(1.18, 0.78, 0.48), MAT.plasticBlack);
        body.position.set(0, 0.55, 0.08);
        g.add(body);
        var bevel = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.035, 0.42), MAT.plasticGray);
        bevel.position.set(0, 0.93, 0.095);
        g.add(bevel);
        var pinXs = [-0.36, 0, 0.36];
        for (var i = 0; i < pinXs.length; i++) {
            var x = pinXs[i];
            var pin = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.72, 0.06), MAT.pinSilver);
            pin.position.set(x, 0.02, 0.20);
            g.add(pin);
            var foot = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.035, 0.36), MAT.pinSilver);
            foot.position.set(x, 0.02, 0.38);
            g.add(foot);
        }
        return g;
    }

    function makeSwitch() {
        var g = new THREE.Group();
        var body = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.35, 0.7), MAT.plasticGray);
        body.position.y = 0.18;
        g.add(body);
        var lever = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.4, 0.2), MAT.switchTop);
        lever.position.y = 0.55;
        g.add(lever);
        return g;
    }

    function makeGround() {
        var g = new THREE.Group();
        var widths = [0.5, 0.34, 0.18];
        widths.forEach(function (w, i) {
            var bar = new THREE.Mesh(
                new THREE.BoxGeometry(w, 0.04, 0.04),
                MAT.ground
            );
            bar.position.set(0, 0.04 + (widths.length - 1 - i) * 0.10, 0);
            g.add(bar);
        });
        var stem = new THREE.Mesh(
            new THREE.CylinderGeometry(0.04, 0.04, 0.18, 6),
            MAT.wire
        );
        stem.position.y = 0.31;
        g.add(stem);
        return g;
    }

    function makeNode() {
        var g = new THREE.Group();
        var sphere = new THREE.Mesh(
            new THREE.SphereGeometry(0.06, 10, 6),
            new THREE.MeshStandardMaterial({ color: 0x7fdbff, metalness: 0.3, roughness: 0.5 })
        );
        sphere.position.y = 0.08;
        g.add(sphere);
        return g;
    }

    function makeSmdChip(comp, footprint) {
        var g = new THREE.Group();
        var w = Math.max(0.45, footprint.widthMm * UNIT_PER_MM);
        var d = Math.max(0.22, footprint.heightMm * UNIT_PER_MM);
        var h = Math.max(0.08, footprint.height3d * UNIT_PER_MM);
        var bodyMat = /capacitor/i.test(comp.type || '') ?
            new THREE.MeshStandardMaterial({ color: 0xd5d7df, roughness: 0.72 }) :
            new THREE.MeshStandardMaterial({ color: 0x27313c, roughness: 0.82 });
        var body = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), bodyMat);
        body.position.y = h / 2 + 0.03;
        g.add(body);
        var sides = [-1, 1];
        for (var i = 0; i < sides.length; i++) {
            var pad = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.035, d * 0.9), MAT.pad);
            pad.position.set(sides[i] * (w / 2 + 0.06), 0.035, 0);
            g.add(pad);
        }
        return g;
    }

    function makeChipPackage(footprint, isSmd) {
        var g = new THREE.Group();
        var pins = Math.max(4, footprint.pins || 8);
        var w = footprint.widthMm * UNIT_PER_MM;
        var d = footprint.heightMm * UNIT_PER_MM;
        var h = footprint.height3d * UNIT_PER_MM;
        var body = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), MAT.plasticBlack);
        body.position.y = h / 2 + 0.05;
        g.add(body);
        var notch = new THREE.Mesh(new THREE.CylinderGeometry(0.10, 0.10, 0.018, 18), MAT.plasticGray);
        notch.rotation.x = Math.PI / 2;
        notch.position.set(-w * 0.42, h + 0.065, 0);
        g.add(notch);
        var perSide = Math.ceil(pins / 2);
        var pitch = w / Math.max(2, perSide);
        for (var side = 0; side < 2; side++) {
            for (var i = 0; i < perSide; i++) {
                var x = -w / 2 + pitch * (i + 0.5);
                var z = side === 0 ? -d / 2 - 0.10 : d / 2 + 0.10;
                var pin = new THREE.Mesh(
                    new THREE.BoxGeometry(Math.min(0.12, pitch * 0.45), isSmd ? 0.035 : 0.24, 0.08),
                    MAT.pinSilver
                );
                pin.position.set(x, isSmd ? 0.04 : 0.12, z);
                g.add(pin);
            }
        }
        return g;
    }

    function makeSot23() {
        var g = new THREE.Group();
        var body = new THREE.Mesh(new THREE.BoxGeometry(0.54, 0.22, 0.36), MAT.plasticBlack);
        body.position.y = 0.14;
        g.add(body);
        var chamfer = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.018, 0.03), MAT.silkscreen);
        chamfer.position.set(-0.16, 0.265, -0.15);
        g.add(chamfer);
        var pinPos = [{ x: -0.17, z: -0.29 }, { x: 0.17, z: -0.29 }, { x: 0, z: 0.29 }];
        for (var i = 0; i < pinPos.length; i++) {
            var p = pinPos[i];
            var pin = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.035, 0.20), MAT.pinSilver);
            pin.position.set(p.x, 0.045, p.z);
            g.add(pin);
            var toe = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.025, 0.08), MAT.pinSilver);
            toe.position.set(p.x, 0.025, p.z + (p.z > 0 ? 0.10 : -0.10));
            g.add(toe);
        }
        return g;
    }

    function makeTerminalBlock(footprint) {
        var g = new THREE.Group();
        var pins = Math.max(2, footprint.pins || 2);
        var w = Math.max(0.9, footprint.widthMm * UNIT_PER_MM);
        var d = Math.max(0.8, footprint.heightMm * UNIT_PER_MM);
        var h = Math.max(0.55, footprint.height3d * UNIT_PER_MM);
        var body = new THREE.Mesh(
            new THREE.BoxGeometry(w, h, d),
            new THREE.MeshStandardMaterial({ color: 0x1f8f57, roughness: 0.76 })
        );
        body.position.y = h / 2;
        g.add(body);
        var pitch = w / pins;
        for (var i = 0; i < pins; i++) {
            var x = -w / 2 + pitch * (i + 0.5);
            var well = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.13, 0.025, 18), MAT.hole);
            well.position.set(x, h + 0.02, 0);
            g.add(well);
            var screw = new THREE.Mesh(new THREE.CylinderGeometry(0.11, 0.11, 0.03, 18), MAT.pinSilver);
            screw.position.set(x, h + 0.045, -d * 0.18);
            g.add(screw);
        }
        return g;
    }

    function makeTechnicalFallback(footprint) {
        var g = new THREE.Group();
        var w = Math.max(0.65, footprint.widthMm * UNIT_PER_MM);
        var d = Math.max(0.42, footprint.heightMm * UNIT_PER_MM);
        var h = Math.max(0.22, footprint.height3d * UNIT_PER_MM);
        var body = new THREE.Mesh(
            new THREE.BoxGeometry(w, h, d),
            new THREE.MeshStandardMaterial({ color: 0x66758a, roughness: 0.72, metalness: 0.08 })
        );
        body.position.y = h / 2 + 0.04;
        g.add(body);
        var stripe = new THREE.Mesh(new THREE.BoxGeometry(w * 0.82, 0.025, 0.045), MAT.silkscreen);
        stripe.position.set(0, h + 0.07, -d * 0.18);
        g.add(stripe);
        var pins = Math.max(2, footprint.pins || 2);
        var pitch = w / Math.max(2, pins - 1);
        for (var i = 0; i < pins; i++) {
            var pin = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 0.32, 8), MAT.pinSilver);
            pin.position.set(-w / 2 + pitch * i, 0.12, d / 2 + 0.08);
            g.add(pin);
        }
        return g;
    }

    // Внешняя GLTF-модель (опционально). lib.sceneRoot выставляет main-модуль
    // в init() и обнуляет в dispose() — это сигнал «жива ли сцена» для async
    // GLTFLoader callback, который может прилететь после закрытия 3D-просмотра.
    function tryAttachExternalModel(comp, group, fallback) {
        var url = _externalModelUrl(comp);
        if (!url || !THREE.GLTFLoader) return false;
        try {
            var loader = new THREE.GLTFLoader();
            loader.load(url, function (gltf) {
                if (!lib.sceneRoot || !group.parent) return;
                var model = gltf.scene || (gltf.scenes && gltf.scenes[0]);
                if (!model) return;
                var box = new THREE.Box3().setFromObject(model);
                var size = new THREE.Vector3();
                box.getSize(size);
                var maxSide = Math.max(size.x, size.y, size.z, 1);
                model.scale.multiplyScalar(1.4 / maxSide);
                model.position.y = 0.04;
                fallback.visible = false;
                group.add(model);
            }, undefined, function () {
                fallback.visible = true;
            });
            return true;
        } catch (e) {
            fallback.visible = true;
            return false;
        }
    }

    function makeForType(comp) {
        var footprint = footprintForComponent(comp);
        var model;
        switch (footprint.kind) {
            case 'smd-chip':
                model = makeSmdChip(comp, footprint);
                break;
            case 'dip':
                model = makeChipPackage(footprint, false);
                break;
            case 'soic':
                model = makeChipPackage(footprint, true);
                break;
            case 'to220':
                model = makeTO220();
                break;
            case 'sot23':
                model = makeSot23();
                break;
            case 'terminal':
                model = makeTerminalBlock(footprint);
                break;
            default:
                model = null;
        }
        if (model) {
            var wrapperA = new THREE.Group();
            wrapperA.add(model);
            tryAttachExternalModel(comp, wrapperA, model);
            return wrapperA;
        }
        switch ((comp.type || '').toLowerCase()) {
            case 'resistor':    model = makeResistor(parseFloat(comp.resistance) || 1000); break;
            case 'led':         model = makeLED(comp._3dColor); break;
            case 'capacitor':   model = makeCapacitor(parseFloat(comp.capacitance) || 1); break;
            case 'diode':       model = makeDiode(); break;
            case 'battery':     model = makeBattery(); break;
            case 'ic':          model = makeIC(); break;
            case 'inductor':    model = makeInductor(); break;
            case 'transistor':
            case 'npn': case 'pnp':
                model = makeTransistor(); break;
            case 'switch':      model = makeSwitch(); break;
            case 'ground':      model = makeGround(); break;
            case 'node':        model = makeNode(); break;
            default:
                model = makeTechnicalFallback(footprint);
                break;
        }
        var wrapper = new THREE.Group();
        wrapper.add(model);
        tryAttachExternalModel(comp, wrapper, model);
        return wrapper;
    }

    // ----- Экспорт -----
    lib._num = _num;
    lib._round3 = _round3;
    lib._snapUp = _snapUp;
    lib._normPackage = _normPackage;
    lib._pinCountFromPackage = _pinCountFromPackage;
    lib.footprintForComponent = footprintForComponent;
    lib._componentCenterPx = _componentCenterPx;
    lib._externalModelUrl = _externalModelUrl;
    lib.makeForType = makeForType;
    // sceneRoot — выставляется main-модулем при init/dispose, мы только читаем.
    lib.sceneRoot = lib.sceneRoot || null;
})(window);
