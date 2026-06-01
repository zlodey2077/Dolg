// =============================================================================
// scheme-3d-materials.js — палитра, shared-материалы Three.js, board defaults.
// =============================================================================
// Вынесено из scheme-3d.js (фаза 1.1 рефакторинга) — это «чистый» слой без
// зависимостей от scene/state, поэтому его безопасно держать отдельным
// файлом. Главный файл забирает экспорт через `window._dolg3dLib`.
//
// Зависимости (глобальные UMD):
//   - THREE (shop/static/lib/three.min.js, r140)
//
// Экспорт (через window._dolg3dLib):
//   RESISTOR_BAND_COLORS  — палитра 4-полосного цветового кода EIA/ГОСТ
//   resistorBands(ohms)   → [digit1, digit2, multiplier]
//   MAT                   — shared MeshStandardMaterial-объекты по ролям
//   _sharedMat(opts)      → новый MeshStandardMaterial, помеченный userData._shared
//                           (dispose их не трогает, иначе следующий open() ловит
//                           поломанные шейдеры)
//   BOARD_DEFAULTS        — параметры PCB-подложки по умолчанию
//   UNIT_PER_MM           — масштаб мм → внутренние единицы (0.16)
// =============================================================================

(function (window) {
    'use strict';

    if (typeof THREE === 'undefined') {
        console.error('[scheme-3d-materials] THREE не загружен — добавь three.min.js до этого скрипта');
        return;
    }

    var lib = window._dolg3dLib = window._dolg3dLib || {};

    // --- Палитра 4-полосного цветового кода резистора по ГОСТ/EIA --------------
    var RESISTOR_BAND_COLORS = [
        0x000000, // 0 — чёрный
        0x6d4c1a, // 1 — коричневый
        0xd32f2f, // 2 — красный
        0xff6f00, // 3 — оранжевый
        0xffd600, // 4 — жёлтый
        0x388e3c, // 5 — зелёный
        0x1976d2, // 6 — синий
        0x6a1b9a, // 7 — фиолетовый
        0x616161, // 8 — серый
        0xf5f5f5, // 9 — белый
    ];

    // Раскладывает значение в Ом → 3 полосы (digit1, digit2, multiplier).
    // 4700 → [4, 7, 2] (yellow, violet, red — мультипликатор 10²).
    function resistorBands(ohms) {
        if (!ohms || ohms <= 0) return [0, 0, 0];
        var e = Math.max(0, Math.floor(Math.log10(ohms / 10)));
        var base = Math.round(ohms / Math.pow(10, e));
        return [Math.floor(base / 10), base % 10, e];
    }

    // Shared materials — переиспользуются между инстансами, помечены _shared
    // через userData. dispose() пропускает помеченные, иначе на повторный
    // open() рисуется поломанная сцена (программы шейдеров уже освобождены).
    function _sharedMat(opts) {
        var m = new THREE.MeshStandardMaterial(opts);
        m.userData._shared = true;
        return m;
    }

    var MAT = {
        beige:        _sharedMat({ color: 0xd6c08e, roughness: 0.7 }),
        wire:         _sharedMat({ color: 0xc0c0c0, metalness: 0.6, roughness: 0.4 }),
        pinSilver:    _sharedMat({ color: 0xb0b0b0, metalness: 0.7, roughness: 0.3 }),
        plasticBlack: _sharedMat({ color: 0x1a1a1a, roughness: 0.9 }),
        plasticGray:  _sharedMat({ color: 0x9e9e9e, roughness: 0.8 }),
        bobbin:       _sharedMat({ color: 0x4a3520, roughness: 0.9 }),
        electroBlue:  _sharedMat({ color: 0x0d1b3d, roughness: 0.5 }),
        electroBand:  _sharedMat({ color: 0xeeeeee, roughness: 0.4 }),
        ground:       _sharedMat({ color: 0x4caf50, metalness: 0.3 }),
        battery:      _sharedMat({ color: 0xc62828, roughness: 0.7 }),
        ledRed:       _sharedMat({ color: 0xff3344, transparent: true, opacity: 0.85, roughness: 0.2 }),
        switchTop:    _sharedMat({ color: 0x424242, roughness: 0.6 }),
        // Soldermask: глянцевый по IPC-A-610 (semi-gloss). Roughness 0.45 даёт
        // реалистичный пластиковый блеск, как у настоящего FR-4 board'а.
        pcbGreen:     _sharedMat({ color: 0x0e3d1b, roughness: 0.45, metalness: 0.05 }),
        // PCB edge — это срез FR-4 фиберглас + epoxy. Реальный цвет:
        // светло-бежевый / тан / brown-cream. Раньше был зелёный (как mask) —
        // выглядело «игрушечно». Сейчас по IPC-4101 (FR-4 стандарт).
        pcbEdge:      _sharedMat({ color: 0xc8a878, roughness: 0.88, metalness: 0.0 }),
        copperTop:    _sharedMat({ color: 0xc77b2a, metalness: 0.65, roughness: 0.34 }),
        copperBottom: _sharedMat({ color: 0x7ac7ff, metalness: 0.45, roughness: 0.45 }),
        // Pad — gold-finish ENIG по умолчанию (стандарт для современных PCB).
        // HASL/OSP добавим как варианты в setPadFinish().
        pad:          _sharedMat({ color: 0xd7a64a, metalness: 0.75, roughness: 0.28 }),
        hole:         _sharedMat({ color: 0x05070c, roughness: 0.95 }),
        // Silkscreen — белая краска epoxy. IPC-A-610: матовая (roughness 0.85).
        silkscreen:   _sharedMat({ color: 0xf4f8ff, roughness: 0.85, metalness: 0.0 }),
        dimension:    _sharedMat({ color: 0x7fdbff, emissive: 0x17384a, emissiveIntensity: 0.45, roughness: 0.4 }),
        warning:      _sharedMat({ color: 0xffcc4d, emissive: 0x3a2600, emissiveIntensity: 0.35, roughness: 0.55 }),
    };

    // ─── EDA-стандарт пресеты ─────────────────────────────────────────────
    // Soldermask 6 цветов по IPC-A-610 + индустриальные практики:
    //   green  — стандарт FR-4 (90% всех PCB), HASL/ENIG
    //   blue   — RoHS-mark часто; популярен для high-end
    //   red    — премиум / отладочные платы
    //   black  — luxury / эстетика, скрывает дорожки
    //   white  — RGB-LED ленты / фотоника
    //   purple — OSH Park, кастомные PCB
    var SOLDERMASK_PRESETS = {
        green:  { color: 0x0e3d1b, edge: 0xc8a878, label: 'Green (стандарт FR-4)' },
        blue:   { color: 0x0d2f5a, edge: 0xc8a878, label: 'Blue (high-end)' },
        red:    { color: 0x6f0e1b, edge: 0xc8a878, label: 'Red (premium/debug)' },
        black:  { color: 0x18181b, edge: 0x8c7050, label: 'Black (luxury)' },
        white:  { color: 0xe8e8e8, edge: 0xc8a878, label: 'White (LED strips)' },
        purple: { color: 0x3d1257, edge: 0xc8a878, label: 'Purple (OSH Park)' },
    };

    // Pad finish: HASL / ENIG / OSP (IPC-4552/4555/4561).
    //   HASL — Hot Air Solder Levelling, серебристый со свинцовым отливом
    //   ENIG — Electroless Nickel Immersion Gold, золотистый
    //   OSP  — Organic Solderability Preservative, медный
    var PAD_FINISH_PRESETS = {
        enig: { color: 0xd7a64a, metalness: 0.75, roughness: 0.28, label: 'ENIG (Au)' },
        hasl: { color: 0xc8c8d0, metalness: 0.82, roughness: 0.18, label: 'HASL (Sn/Pb)' },
        osp:  { color: 0xb87333, metalness: 0.55, roughness: 0.42, label: 'OSP (Cu)' },
    };

    // Silkscreen 3 цвета по IPC-A-610.
    var SILK_PRESETS = {
        white:  { color: 0xf4f8ff, label: 'White (стандарт)' },
        yellow: { color: 0xffe066, label: 'Yellow (на тёмной маске)' },
        black:  { color: 0x1a1a1a, label: 'Black (на светлой маске)' },
    };

    // Применяет soldermask preset — меняет color у pcbGreen и pcbEdge
    // shared-материалов. Сцена обновится автоматически.
    function applySoldermaskPreset(name) {
        var p = SOLDERMASK_PRESETS[name];
        if (!p) return false;
        MAT.pcbGreen.color.setHex(p.color);
        MAT.pcbEdge.color.setHex(p.edge);
        return true;
    }

    function applyPadFinishPreset(name) {
        var p = PAD_FINISH_PRESETS[name];
        if (!p) return false;
        MAT.pad.color.setHex(p.color);
        MAT.pad.metalness = p.metalness;
        MAT.pad.roughness = p.roughness;
        return true;
    }

    function applySilkPreset(name) {
        var p = SILK_PRESETS[name];
        if (!p) return false;
        MAT.silkscreen.color.setHex(p.color);
        return true;
    }

    var BOARD_DEFAULTS = {
        pxPerMm: 4,
        marginMm: 5,
        // Толщина дорожек удвоена (было 0.5 — слишком тонко на фоне корпусов).
        traceWidthMm: 1.0,
        clearanceMm: 1.5,
        thicknessMm: 1.6,
        gridMm: 5,
        padDiameterMm: 1.6,
        holeDiameterMm: 0.8,
        minBoardMm: 50,
    };
    var UNIT_PER_MM = 0.16;

    // ----- Экспорт в общий namespace -----
    lib.RESISTOR_BAND_COLORS = RESISTOR_BAND_COLORS;
    lib.resistorBands = resistorBands;
    lib._sharedMat = _sharedMat;
    lib.MAT = MAT;
    lib.BOARD_DEFAULTS = BOARD_DEFAULTS;
    lib.UNIT_PER_MM = UNIT_PER_MM;
    // EDA-стандарт пресеты
    lib.SOLDERMASK_PRESETS = SOLDERMASK_PRESETS;
    lib.PAD_FINISH_PRESETS = PAD_FINISH_PRESETS;
    lib.SILK_PRESETS = SILK_PRESETS;
    lib.applySoldermaskPreset = applySoldermaskPreset;
    lib.applyPadFinishPreset = applyPadFinishPreset;
    lib.applySilkPreset = applySilkPreset;
})(window);
