// =============================================================================
// scheme-lab.js — Виртуальная лаборатория приборов (killer-фича #5 диплома)
// =============================================================================
// Три инструмента в одной модалке:
//   1) Осциллограф (Oscilloscope) — отображает TRAN-результат как осциллограмму
//      с настройками V/div, t/div и выбором канала (узел схемы).
//   2) Мультиметр (Multimeter) — DC/AC/Ω режимы, выбор пары узлов,
//      7-сегментный LCD-дисплей.
//   3) Генератор сигналов (Signal Generator) — sine/square/triangle, амплитуда,
//      частота. «Применить к V1» меняет напряжение источника в схеме.
//
// Контракт:
//   DolgLab.init(rootEl, callbacks) — биндит UI к корневому DOM-узлу.
//     callbacks.getScheme()      → текущая схема {components, connections}
//     callbacks.getLastResult()  → последний результат симуляции (или null)
//     callbacks.applyToBattery(compId, payload) → выставляет voltage/source
//     callbacks.requestRerun()   → попросить хост перезапустить симуляцию
//   DolgLab.refresh()            — перерисовать показания (вызвать после run)
//   DolgLab.dispose()            — снять обработчики
// =============================================================================

(function (window) {
    'use strict';

    // --- Утилиты форматирования ------------------------------------------------
    function fmtVolts(v) {
        if (!isFinite(v)) return '----';
        const a = Math.abs(v);
        if (a < 1e-3) return (v * 1e6).toFixed(1) + ' мкВ';
        if (a < 1) return (v * 1000).toFixed(2) + ' мВ';
        if (a < 1000) return v.toFixed(3) + ' В';
        return (v / 1000).toFixed(2) + ' кВ';
    }
    function fmtOhm(r) {
        if (!isFinite(r) || r <= 0) return '----';
        if (r >= 1e6) return (r / 1e6).toFixed(2) + ' МΩ';
        if (r >= 1e3) return (r / 1e3).toFixed(2) + ' кΩ';
        return r.toFixed(1) + ' Ω';
    }
    function fmtFreq(f) {
        if (!isFinite(f) || f <= 0) return '0 Гц';
        if (f >= 1e6) return (f / 1e6).toFixed(2) + ' МГц';
        if (f >= 1e3) return (f / 1e3).toFixed(2) + ' кГц';
        return f.toFixed(0) + ' Гц';
    }
    function fmtTime(t) {
        if (!isFinite(t)) return '0';
        const a = Math.abs(t);
        if (a < 1e-6) return (t * 1e9).toFixed(0) + ' нс';
        if (a < 1e-3) return (t * 1e6).toFixed(0) + ' мкс';
        if (a < 1) return (t * 1000).toFixed(2) + ' мс';
        return t.toFixed(2) + ' с';
    }
    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
    function parseSelectId(value) {
        if (value === '' || value === null || value === undefined) return null;
        const n = Number(value);
        return Number.isFinite(n) ? n : value;
    }
    function sameId(left, right) {
        return String(left) === String(right);
    }
    function nodeLabel(node) {
        return String(node) === '0' ? 'GND (0)' : String(node);
    }
    function buildOption(value, label) {
        return `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`;
    }

    // --- Состояние лаборатории -------------------------------------------------
    const state = {
        // Осциллограф
        scope: {
            channel: null,      // имя узла схемы или null для авто
            vDiv: 1.0,          // вольт/деление
            tDiv: 1e-3,         // секунд/деление
            offset: 0,          // вертикальный сдвиг
            cursorT1: null,     // время T1 в секундах (Shift+Click)
            cursorT2: null,     // время T2 в секундах (Shift+Click повторно)
        },
        // Мультиметр
        multimeter: {
            mode: 'V',          // 'V' | 'V_RMS' | 'Ohm'
            nodeA: '0',
            nodeB: null,
        },
        // Генератор
        gen: {
            wave: 'sine',       // 'sine' | 'square' | 'triangle'
            amplitude: 5,       // В пик
            frequency: 1000,    // Гц
            offset: 0,          // DC
            targetCompId: null, // id источника (battery)
        },
    };

    let _root = null;
    let _cbs = null;
    let _bound = false;

    // --- HTML-разметка лаборатории --------------------------------------------
    const HTML = `
        <div class="dolg-lab-grid">
            <!-- Осциллограф -->
            <div class="dolg-lab-card dolg-lab-scope">
                <div class="dolg-lab-card-title">📺 Осциллограф</div>
                <canvas class="dolg-lab-scope-canvas" id="dolgLabScopeCanvas"
                        width="540" height="280"></canvas>
                <div class="dolg-lab-scope-info" id="dolgLabScopeInfo"></div>
                <div class="dolg-lab-controls">
                    <label>Канал:
                        <select id="dolgLabScopeChannel"></select>
                    </label>
                    <label>V/деление:
                        <select id="dolgLabScopeVDiv">
                            <option value="0.001">1 мВ</option>
                            <option value="0.01">10 мВ</option>
                            <option value="0.1">100 мВ</option>
                            <option value="0.5">500 мВ</option>
                            <option value="1" selected>1 В</option>
                            <option value="2">2 В</option>
                            <option value="5">5 В</option>
                        </select>
                    </label>
                    <label>t/деление:
                        <select id="dolgLabScopeTDiv">
                            <option value="0.000001">1 мкс</option>
                            <option value="0.00001">10 мкс</option>
                            <option value="0.0001">100 мкс</option>
                            <option value="0.001" selected>1 мс</option>
                            <option value="0.01">10 мс</option>
                            <option value="0.1">100 мс</option>
                        </select>
                    </label>
                </div>
            </div>

            <!-- Мультиметр -->
            <div class="dolg-lab-card dolg-lab-mm">
                <div class="dolg-lab-card-title">🔢 Мультиметр</div>
                <canvas class="dolg-lab-mm-gauge" id="dolgLabMmGauge"
                        width="320" height="160"
                        aria-label="Аналоговая стрелка мультиметра"></canvas>
                <div class="dolg-lab-mm-display" id="dolgLabMmDisplay">- - - -</div>
                <div class="dolg-lab-mm-unit" id="dolgLabMmUnit">В DC</div>
                <div class="dolg-lab-controls">
                    <label>Режим:
                        <select id="dolgLabMmMode">
                            <option value="V">V (DC)</option>
                            <option value="V_RMS">V (RMS)</option>
                            <option value="Ohm">Ω</option>
                            <option value="Cont">Прозвонка</option>
                            <option value="I">I (ток)</option>
                        </select>
                    </label>
                    <label>+ щуп:
                        <select id="dolgLabMmNodeA"></select>
                    </label>
                    <label>− щуп:
                        <select id="dolgLabMmNodeB"></select>
                    </label>
                </div>
            </div>

            <!-- Генератор сигналов -->
            <div class="dolg-lab-card dolg-lab-gen">
                <div class="dolg-lab-card-title">〰️ Генератор сигналов</div>
                <canvas class="dolg-lab-gen-preview" id="dolgLabGenPreview"
                        width="320" height="100"></canvas>
                <div class="dolg-lab-controls">
                    <label>Форма:
                        <select id="dolgLabGenWave">
                            <option value="sine">Синус</option>
                            <option value="square">Меандр</option>
                            <option value="triangle">Треугольник</option>
                        </select>
                    </label>
                    <label>Амплитуда (В):
                        <input type="number" id="dolgLabGenAmp" min="0.01" max="48" step="0.1" value="5">
                    </label>
                    <label>Частота (Гц):
                        <input type="number" id="dolgLabGenFreq" min="0.1" max="10000000" step="10" value="1000">
                    </label>
                    <label class="lab-control-offset">Смещение DC (В):
                        <input type="number" id="dolgLabGenOff" min="-24" max="24" step="0.1" value="0">
                    </label>
                    <label>Применить к источнику:
                        <select id="dolgLabGenTarget"></select>
                    </label>
                    <button type="button" id="dolgLabGenApply" class="dolg-lab-btn">▶ Применить + перезапустить</button>
                </div>
            </div>
        </div>
    `;

    function init(rootEl, callbacks) {
        _root = rootEl;
        _cbs = callbacks || {};
        rootEl.innerHTML = HTML;
        rebindAll();
        refresh();
        // 2026-06-01 recovery #4: ResizeObserver на scope card. Резизит
        // canvas под актуальный CSS-размер (с учётом DPI), чтобы scope не
        // оставался растянутым/размытым при изменении analysis-bottom высоты.
        try {
            if (rootEl._labResizeObserver) rootEl._labResizeObserver.disconnect();
            const scopeCanvas = rootEl.querySelector('#dolgLabScopeCanvas');
            const scopeCard = rootEl.querySelector('.dolg-lab-scope');
            if (scopeCanvas && scopeCard && typeof ResizeObserver !== 'undefined') {
                const ro = new ResizeObserver(() => {
                    const r = scopeCard.getBoundingClientRect();
                    const dpr = window.devicePixelRatio || 1;
                    const w = Math.max(200, Math.floor((r.width - 16) * dpr));
                    const h = Math.max(120, Math.floor(Math.min(r.height - 80, 280) * dpr));
                    if (scopeCanvas.width !== w) scopeCanvas.width = w;
                    if (scopeCanvas.height !== h) scopeCanvas.height = h;
                    try { drawScope(); } catch (_e) {}
                });
                ro.observe(scopeCard);
                rootEl._labResizeObserver = ro;
            }
        } catch (_e) { /* no-op */ }
    }

    function dispose() {
        if (_root) _root.innerHTML = '';
        _root = null; _cbs = null; _bound = false;
    }

    function rebindAll() {
        if (!_root) return;
        const $ = (id) => _root.querySelector('#' + id);

        $('dolgLabScopeChannel').addEventListener('change', e => {
            state.scope.channel = e.target.value || null;
            drawScope();
        });
        // T1/T2 курсоры — Shift+Click ставит/обновляет курсор на холсте.
        // Без Shift — обычный клик ничего не делает (canvas read-only).
        // Двойной клик сбрасывает оба курсора.
        const _scopeCanvas = $('dolgLabScopeCanvas');
        _scopeCanvas.addEventListener('click', (ev) => {
            if (!ev.shiftKey) return;
            const last = _placeScopeCursor(ev);
            if (last !== null) drawScope();
        });
        _scopeCanvas.addEventListener('dblclick', () => {
            state.scope.cursorT1 = null;
            state.scope.cursorT2 = null;
            drawScope();
        });
        $('dolgLabScopeVDiv').addEventListener('change', e => {
            state.scope.vDiv = parseFloat(e.target.value) || 1;
            drawScope();
        });
        $('dolgLabScopeTDiv').addEventListener('change', e => {
            state.scope.tDiv = parseFloat(e.target.value) || 1e-3;
            drawScope();
        });
        $('dolgLabMmMode').addEventListener('change', e => {
            state.multimeter.mode = e.target.value;
            updateMultimeter();
        });
        $('dolgLabMmNodeA').addEventListener('change', e => {
            state.multimeter.nodeA = e.target.value;
            updateMultimeter();
        });
        $('dolgLabMmNodeB').addEventListener('change', e => {
            state.multimeter.nodeB = e.target.value || null;
            updateMultimeter();
        });
        // §1.1 follow-up: auto-apply Generator при изменении любого поля.
        // Раньше нужно было нажать кнопку «Применить + запустить» — после её
        // скрытия в docked-режиме (юзер: «есть общая ▶ Запуск») applyToBattery
        // никогда не вызывалась, analysis-type оставался DC, scope не получал
        // points. Теперь debounced auto-apply на input/change.
        let _genApplyTimer = null;
        function _scheduleGenApply() {
            if (_genApplyTimer) clearTimeout(_genApplyTimer);
            _genApplyTimer = setTimeout(() => {
                try { applyGenerator(); } catch (e) { /* noop */ }
            }, 400);
        }
        $('dolgLabGenWave').addEventListener('change', e => {
            state.gen.wave = e.target.value; drawGenPreview(); _scheduleGenApply();
        });
        $('dolgLabGenAmp').addEventListener('input', e => {
            state.gen.amplitude = parseFloat(e.target.value) || 0; drawGenPreview(); _scheduleGenApply();
        });
        $('dolgLabGenFreq').addEventListener('input', e => {
            state.gen.frequency = parseFloat(e.target.value) || 0; drawGenPreview(); _scheduleGenApply();
        });
        $('dolgLabGenOff').addEventListener('input', e => {
            state.gen.offset = parseFloat(e.target.value) || 0; drawGenPreview(); _scheduleGenApply();
        });
        $('dolgLabGenTarget').addEventListener('change', e => {
            state.gen.targetCompId = parseSelectId(e.target.value); _scheduleGenApply();
        });
        $('dolgLabGenApply').addEventListener('click', applyGenerator);
        _bound = true;
    }

    function refresh() {
        if (!_root || !_bound) return;
        rebuildSelectors();
        drawScope();
        updateMultimeter();
        drawGenPreview();
    }

    // --- Списки выбора (узлы / источники) -------------------------------------
    // 2026-06-01 v17b: для Multimeter добавляем per-port опции (R1.A, V1.+) —
    // юзер может выбрать конкретный вывод компонента, даже если несколько
    // share один net. Resolver _resolvePortToNet превращает comp:port в net.
    function _buildPortOptions(scheme) {
        const portNetMap = getPortNetMapForScheme(scheme) || new Map();
        const opts = [];
        (scheme.components || []).forEach(c => {
            const label = c.label || (c.type ? c.type.charAt(0).toUpperCase() : '?') + c.id;
            const ports = c.ports || [];
            ports.forEach(p => {
                const portKey = c.id + ':' + p.id;
                const net = portNetMap.get(portKey);
                const text = label + '.' + (p.label || p.id) + (net != null ? ' →net ' + net : ' (висит)');
                opts.push(buildOption('port:' + portKey, text));
            });
        });
        return opts.join('');
    }
    function _resolvePortToNet(value, scheme) {
        if (typeof value !== 'string' || !value.startsWith('port:')) return value;
        const portKey = value.slice(5);
        const map = getPortNetMapForScheme(scheme);
        if (map && map.has(portKey)) return String(map.get(portKey));
        return value;
    }
    window._resolvePortToNet = _resolvePortToNet;
    function rebuildSelectors() {
        const $ = (id) => _root.querySelector('#' + id);
        const result = (_cbs.getLastResult && _cbs.getLastResult()) || null;
        const scheme = (_cbs.getScheme && _cbs.getScheme()) || { components: [], connections: [] };

        const nodes = collectNodeIds(scheme, result);
        const portOpts = _buildPortOptions(scheme);

        const channelSel = $('dolgLabScopeChannel');
        const aSel = $('dolgLabMmNodeA');
        const bSel = $('dolgLabMmNodeB');
        const tgtSel = $('dolgLabGenTarget');

        channelSel.innerHTML = buildOption('', '— авто —')
            + nodes.filter(n => n !== '0').map(n => buildOption(n, 'V(' + n + ')')).join('');
        // v17b: для A/B щупов — net'ы + список выводов компонентов через optgroup
        const netsOpts = nodes.length
            ? nodes.map(n => buildOption(n, nodeLabel(n))).join('')
            : buildOption('0', 'GND (0)');
        aSel.innerHTML = '<optgroup label="Узлы (net)">' + netsOpts + '</optgroup>' +
                        (portOpts ? '<optgroup label="Выводы компонентов">' + portOpts + '</optgroup>' : '');
        bSel.innerHTML = buildOption('', 'GND (0)')
            + '<optgroup label="Узлы (net)">' + nodes.filter(n => n !== '0').map(n => buildOption(n, nodeLabel(n))).join('') + '</optgroup>'
            + (portOpts ? '<optgroup label="Выводы компонентов">' + portOpts + '</optgroup>' : '');

        // Источники для генератора (battery-компоненты схемы)
        const batteries = (scheme.components || []).filter(c => (c.type || '').toLowerCase() === 'battery');
        tgtSel.innerHTML = batteries.length
            ? batteries.map(b => {
                const label = b.label || ('V' + b.id);
                const voltage = Number.isFinite(Number(b.voltage)) ? Number(b.voltage) : 0;
                return buildOption(b.id, label + ' (' + voltage + ')');  // v17c: убрана «В»
            }).join('')
            : buildOption('', 'нет источников в схеме');

        // Восстановить значения из state, если они валидны
        if (state.scope.channel && nodes.includes(state.scope.channel)) {
            channelSel.value = state.scope.channel;
        } else if (state.scope.channel && !nodes.includes(state.scope.channel)) {
            state.scope.channel = null;
        }
        // v17b: port:... тоже считаем валидным (port-уровневый щуп)
        const isPortFormat = (v) => typeof v === 'string' && v.startsWith('port:');
        if (!nodes.includes(state.multimeter.nodeA) && !isPortFormat(state.multimeter.nodeA)) {
            state.multimeter.nodeA = nodes.find(n => n !== '0') || nodes[0] || '0';
        }
        aSel.value = state.multimeter.nodeA;
        if (state.multimeter.nodeB === null) bSel.value = '';
        else if (nodes.includes(state.multimeter.nodeB) || isPortFormat(state.multimeter.nodeB)) {
            bSel.value = state.multimeter.nodeB;
        } else {
            state.multimeter.nodeB = null;
            bSel.value = '';
        }

        if (!batteries.length) {
            state.gen.targetCompId = null;
        } else if (
            state.gen.targetCompId == null ||
            !batteries.some(b => sameId(b.id, state.gen.targetCompId))
        ) {
            state.gen.targetCompId = batteries[0].id;
        }
        if (state.gen.targetCompId != null) tgtSel.value = String(state.gen.targetCompId);
    }

    function collectNodeIds(scheme, result) {
        const ids = new Set(['0']);
        if (result && result.nodeVoltages) {
            Object.keys(result.nodeVoltages).forEach(n => ids.add(String(n)));
        }
        if (result && result.points && result.points.length) {
            Object.keys(result.points[0]).forEach(k => {
                if (k !== 't' && k !== 'f' && !/^db_/.test(k) && !/^ph_/.test(k)) {
                    ids.add(String(k));
                }
            });
        }
        const map = getPortNetMapForScheme(scheme);
        if (map) {
            map.forEach(net => ids.add(String(net)));
        }
        return Array.from(ids).sort((a, b) => {
            const an = Number(a), bn = Number(b);
            if (Number.isFinite(an) && Number.isFinite(bn)) return an - bn;
            return String(a).localeCompare(String(b));
        });
    }

    // Конвертирует click event в время на оси t (секунды) и записывает в
    // cursorT1 (если оба пусты или оба заняты — стартуем заново) или cursorT2
    // (если занят только T1).
    function _placeScopeCursor(ev) {
        const result = (_cbs.getLastResult && _cbs.getLastResult()) || null;
        if (!result || result.type !== 'tran' || !result.points || !result.points.length) return null;
        const canvas = ev.currentTarget;
        const rect = canvas.getBoundingClientRect();
        const xPx = (ev.clientX - rect.left) * (canvas.width / rect.width);
        const tOrigin = result.points[0].t;
        const pxPerSec = canvas.width / (state.scope.tDiv * 10);
        const t = tOrigin + xPx / pxPerSec;
        if (state.scope.cursorT1 === null || (state.scope.cursorT1 !== null && state.scope.cursorT2 !== null)) {
            state.scope.cursorT1 = t;
            state.scope.cursorT2 = null;
        } else {
            state.scope.cursorT2 = t;
        }
        return t;
    }

    // --- Осциллограф -----------------------------------------------------------
    // §2.7 Phosphor-buffer: храним прошлую волну как массив [x,y] точек.
    // На следующем drawScope отрисуем её первой полупрозрачно (ghost-trace) —
    // создаёт характерный «послесвет» CRT при изменении параметров.
    let _scopePrevTrace = null;        // [[x,y], [x,y], ...]
    let _scopePrevClipped = false;     // флаг clipping предыдущего кадра
    let _scopeBlinkPhase = 0;          // для мигающего OVERFLOW

    function drawScope() {
        const canvas = _root && _root.querySelector('#dolgLabScopeCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const W = canvas.width, H = canvas.height;
        ctx.fillStyle = '#031918';
        ctx.fillRect(0, 0, W, H);

        // Сетка 10×8 делений
        ctx.strokeStyle = 'rgba(70, 200, 180, 0.18)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        for (let i = 1; i < 10; i++) {
            const x = (W * i) / 10;
            ctx.moveTo(x, 0); ctx.lineTo(x, H);
        }
        for (let i = 1; i < 8; i++) {
            const y = (H * i) / 8;
            ctx.moveTo(0, y); ctx.lineTo(W, y);
        }
        ctx.stroke();
        // Центральные оси
        ctx.strokeStyle = 'rgba(70, 200, 180, 0.45)';
        ctx.beginPath();
        ctx.moveTo(0, H / 2); ctx.lineTo(W, H / 2);
        ctx.moveTo(W / 2, 0); ctx.lineTo(W / 2, H);
        ctx.stroke();

        const result = (_cbs.getLastResult && _cbs.getLastResult()) || null;
        const info = _root.querySelector('#dolgLabScopeInfo');

        if (!result || result.type !== 'tran' || !result.points || !result.points.length) {
            info.textContent = '';  // v17c: убран лишний текст-подсказка
            return;
        }

        // Выбор канала: если задан вручную — берём его, иначе первый ненулевой узел
        const points = result.points;
        const sample = points[0];
        const allKeys = Object.keys(sample).filter(k => k !== 't');
        let channel = state.scope.channel;
        if (!channel || !allKeys.includes(channel)) {
            channel = allKeys.find(k => k !== '0') || allKeys[0];
        }
        if (!channel) {
            info.textContent = 'В TRAN-результате нет узлов для отображения.';
            return;
        }

        // Перевод (t, v) → (px, py) с учётом V/div и t/div.
        const tOrigin = points[0].t;
        const vDiv = state.scope.vDiv;
        const tDiv = state.scope.tDiv;
        const pxPerSec = W / (tDiv * 10);
        const pxPerVolt = H / (vDiv * 8);
        const yMid = H / 2;

        // §2.7 Phosphor (ghost-trace): рисуем предыдущую волну полупрозрачно,
        // ниже основной — даёт «послесвет» CRT при изменении параметров.
        if (_scopePrevTrace && _scopePrevTrace.length > 1) {
            ctx.save();
            ctx.strokeStyle = 'rgba(127, 255, 176, 0.28)';
            ctx.lineWidth = 1.2;
            ctx.beginPath();
            ctx.moveTo(_scopePrevTrace[0][0], _scopePrevTrace[0][1]);
            for (let i = 1; i < _scopePrevTrace.length; i++) {
                ctx.lineTo(_scopePrevTrace[i][0], _scopePrevTrace[i][1]);
            }
            ctx.stroke();
            ctx.restore();
        }

        // §2.7 Clipping: волна выходит за ±4 деления (предел экрана), эти
        // участки рисуем красным + накладываем hatch-полосу 45°.
        const Y_TOP_LIMIT = 0;           // верхний край canvas — clip
        const Y_BOT_LIMIT = H;           // нижний край canvas — clip
        let clippedNow = false;
        const trace = [];                // для phosphor-buffer на след. кадр

        // Pass 1: основная зелёная кривая (clamped в пределах canvas)
        ctx.strokeStyle = '#7fffb0';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        let drew = false;
        for (let i = 0; i < points.length; i++) {
            const x = (points[i].t - tOrigin) * pxPerSec;
            if (x > W) break;
            const v = points[i][channel];
            if (!isFinite(v)) continue;
            let y = yMid - v * pxPerVolt;
            // Clipping detection
            if (y < Y_TOP_LIMIT) { y = Y_TOP_LIMIT; clippedNow = true; }
            else if (y > Y_BOT_LIMIT) { y = Y_BOT_LIMIT; clippedNow = true; }
            trace.push([x, y]);
            if (!drew) { ctx.moveTo(x, y); drew = true; }
            else ctx.lineTo(x, y);
        }
        ctx.stroke();

        // Pass 2: «обрезанные» участки выделяем красным поверх зелёного
        if (clippedNow) {
            ctx.save();
            ctx.strokeStyle = '#ff4040';
            ctx.lineWidth = 2;
            ctx.beginPath();
            let inClip = false;
            for (let i = 0; i < points.length; i++) {
                const x = (points[i].t - tOrigin) * pxPerSec;
                if (x > W) break;
                const v = points[i][channel];
                if (!isFinite(v)) continue;
                const y = yMid - v * pxPerVolt;
                if (y < Y_TOP_LIMIT || y > Y_BOT_LIMIT) {
                    const clampedY = y < Y_TOP_LIMIT ? Y_TOP_LIMIT : Y_BOT_LIMIT;
                    if (!inClip) { ctx.moveTo(x, clampedY); inClip = true; }
                    else { ctx.lineTo(x, clampedY); }
                } else {
                    if (inClip) inClip = false;
                }
            }
            ctx.stroke();
            // Hatch-полоса 45° в clipping-zones
            ctx.strokeStyle = 'rgba(255, 64, 64, 0.18)';
            ctx.lineWidth = 1;
            for (let i = 0; i < points.length - 1; i++) {
                const x1 = (points[i].t - tOrigin) * pxPerSec;
                const x2 = (points[i + 1].t - tOrigin) * pxPerSec;
                if (x2 > W) break;
                const v1 = points[i][channel], v2 = points[i + 1][channel];
                const y1 = yMid - v1 * pxPerVolt;
                const y2 = yMid - v2 * pxPerVolt;
                if ((y1 < Y_TOP_LIMIT && y2 < Y_TOP_LIMIT) ||
                    (y1 > Y_BOT_LIMIT && y2 > Y_BOT_LIMIT)) {
                    const yClip = y1 < Y_TOP_LIMIT ? Y_TOP_LIMIT : Y_BOT_LIMIT;
                    const baseY = y1 < Y_TOP_LIMIT ? 0 : H - 20;
                    ctx.beginPath();
                    for (let xh = x1; xh < x2; xh += 6) {
                        ctx.moveTo(xh, baseY);
                        ctx.lineTo(xh + 6, baseY + 12);
                    }
                    ctx.stroke();
                }
            }
            // Мигающая надпись OVERFLOW
            _scopeBlinkPhase = (_scopeBlinkPhase + 1) % 2;
            if (_scopeBlinkPhase === 0) {
                ctx.fillStyle = '#ff4040';
                ctx.font = 'bold 13px monospace';
                ctx.textAlign = 'left';
                ctx.fillText('⚠ OVERFLOW', 10, 18);
            }
            ctx.restore();
        }

        // Сохраняем trace для phosphor на следующий кадр
        _scopePrevTrace = trace;
        _scopePrevClipped = clippedNow;

        // Stats
        let vmin = +Infinity, vmax = -Infinity, vsum = 0, vsum2 = 0, n = 0;
        for (const p of points) {
            const v = p[channel]; if (!isFinite(v)) continue;
            if (v < vmin) vmin = v;
            if (v > vmax) vmax = v;
            vsum += v; vsum2 += v * v; n++;
        }
        const vAvg = n ? vsum / n : 0;
        const vRms = n ? Math.sqrt(vsum2 / n) : 0;

        // T1/T2 курсоры (Shift+Click). Линии + надписи поверх кривой.
        const drawCursor = (t, label, color) => {
            const x = (t - tOrigin) * pxPerSec;
            if (x < 0 || x > W) return null;
            ctx.save();
            ctx.strokeStyle = color;
            ctx.lineWidth = 1.2;
            ctx.setLineDash([5, 4]);
            ctx.beginPath();
            ctx.moveTo(x, 0); ctx.lineTo(x, H);
            ctx.stroke();
            ctx.setLineDash([]);
            ctx.fillStyle = color;
            ctx.font = '11px monospace';
            ctx.fillText(label, x + 3, 12);
            // Значение V(channel) в момент t — линейная интерполяция по соседним точкам
            let i = 0;
            while (i < points.length - 1 && points[i + 1].t < t) i++;
            const v = points[i] ? points[i][channel] : 0;
            if (isFinite(v)) ctx.fillText(fmtVolts(v), x + 3, 24);
            ctx.restore();
            return v;
        };
        let cursorInfo = '';
        if (state.scope.cursorT1 !== null) {
            const v1 = drawCursor(state.scope.cursorT1, 'T1', '#ffd166');
            if (state.scope.cursorT2 !== null) {
                const v2 = drawCursor(state.scope.cursorT2, 'T2', '#ff6b6b');
                const dt = Math.abs(state.scope.cursorT2 - state.scope.cursorT1);
                const dv = (v2 != null && v1 != null) ? (v2 - v1) : null;
                const f  = dt > 0 ? 1 / dt : 0;
                cursorInfo = ` · T1→T2 Δt=${fmtTime(dt)}, Δv=${dv != null ? fmtVolts(dv) : '—'}, 1/Δt=${fmtFreq(f)}`;
            } else {
                cursorInfo = ` · T1=${fmtTime(state.scope.cursorT1 - tOrigin)} (Shift+Click для T2)`;
            }
        }

        // §2.7 OVERLOAD detection: |V| > 0.95 × screen-range или резкое dV/dt.
        // Создаёт небольшой шум по волне + помечает info-line.
        const fullRange = state.scope.vDiv * 4;     // от центра до края экрана
        const overloadV = (vmax > fullRange * 0.95) || (vmin < -fullRange * 0.95);
        let overloadDvDt = false;
        if (points.length > 4) {
            for (let i = 1; i < points.length; i++) {
                const dt = points[i].t - points[i - 1].t;
                if (dt <= 0) continue;
                const dv = (points[i][channel] - points[i - 1][channel]) / dt;
                if (Math.abs(dv) > state.scope.vDiv * 50 / state.scope.tDiv) {
                    overloadDvDt = true; break;
                }
            }
        }
        const overload = overloadV || overloadDvDt;

        info.textContent =
            `канал V(${channel}) · ${state.scope.vDiv}В/дел · ${fmtTime(state.scope.tDiv)}/дел · ` +
            `Vmin=${fmtVolts(vmin)}, Vmax=${fmtVolts(vmax)}, Vavg=${fmtVolts(vAvg)}, RMS=${fmtVolts(vRms)}` +
            cursorInfo +
            (overload ? '  · 🔴 OVERLOAD' : '');
    }

    // --- Мультиметр ------------------------------------------------------------
    // Аналоговая стрелка: храним текущий угол + целевой, лёрпуем в rAF.
    // _mmGauge.range — автоматически растёт до ближайшего «инженерного»
    // (1, 2, 5, 10, 20, 50, 100…) от max|value|. Никаких заранее
    // выставленных диапазонов — стрелка всегда «дышит» под текущий сигнал.
    const _mmGauge = {
        currentAngle: 0,          // отрисованный угол (рад, от -π/2 до +π/2)
        targetAngle: 0,           // куда стремится
        currentValue: 0,
        range: 1,                 // полный размах шкалы (на каждую сторону от 0)
        unit: 'В',
        valid: false,             // есть ли валидное измерение
        rafId: null,
    };

    function _engineerRange(v) {
        // Округление вверх до ближайшего 1/2/5 × 10^n. Шкала всегда «красивая».
        const a = Math.max(Math.abs(v) * 1.15, 0.1);   // 15% запаса по краю
        const exp = Math.floor(Math.log10(a));
        const base = Math.pow(10, exp);
        const norm = a / base;
        if (norm <= 1) return 1 * base;
        if (norm <= 2) return 2 * base;
        if (norm <= 5) return 5 * base;
        return 10 * base;
    }

    function _setMmTarget(value, unit, valid) {
        _mmGauge.unit = unit || '';
        _mmGauge.valid = !!valid;
        if (!valid || !isFinite(value)) {
            _mmGauge.targetAngle = 0;     // стрелка на «0»
            _mmGauge.currentValue = NaN;
            _scheduleMmGaugeAnim();
            return;
        }
        // Автомасштаб: расширяем диапазон если |v| вылез за текущий, сжимаем
        // только если |v| < 30% диапазона (избегаем «дрожания» границы).
        if (Math.abs(value) > _mmGauge.range) _mmGauge.range = _engineerRange(value);
        else if (Math.abs(value) < _mmGauge.range * 0.3 && _mmGauge.range > 1) {
            _mmGauge.range = Math.max(1, _engineerRange(value));
        }
        _mmGauge.currentValue = value;
        const ratio = Math.max(-1, Math.min(1, value / _mmGauge.range));
        _mmGauge.targetAngle = ratio * (Math.PI * 0.42);  // ±75° от вертикали
        _scheduleMmGaugeAnim();
    }

    function _scheduleMmGaugeAnim() {
        if (_mmGauge.rafId) return;
        const step = () => {
            // Лёрпуем 25% в кадр — даёт ~120ms полного хода, плавно но
            // не вяло. Для броска (delta > π/4) делаем «нервный» виброход.
            const delta = _mmGauge.targetAngle - _mmGauge.currentAngle;
            _mmGauge.currentAngle += delta * 0.25;
            _drawMmGauge();
            if (Math.abs(delta) > 0.001) {
                _mmGauge.rafId = requestAnimationFrame(step);
            } else {
                _mmGauge.currentAngle = _mmGauge.targetAngle;
                _mmGauge.rafId = null;
                _drawMmGauge();
            }
        };
        _mmGauge.rafId = requestAnimationFrame(step);
    }

    function _drawMmGauge() {
        const canvas = _root && _root.querySelector('#dolgLabMmGauge');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const W = canvas.width, H = canvas.height;
        ctx.clearRect(0, 0, W, H);

        // Фон-«пластина» прибора
        const grd = ctx.createLinearGradient(0, 0, 0, H);
        grd.addColorStop(0, '#1a2540');
        grd.addColorStop(1, '#0a0e27');
        ctx.fillStyle = grd;
        ctx.fillRect(0, 0, W, H);
        // Тонкая рамка
        ctx.strokeStyle = 'rgba(0, 212, 255, 0.25)';
        ctx.lineWidth = 1;
        ctx.strokeRect(0.5, 0.5, W - 1, H - 1);

        // Геометрия циферблата: pivot снизу, дуга сверху
        const cx = W / 2;
        const cy = H - 22;
        const radius = Math.min(W * 0.42, H * 0.85);

        // Дуга шкалы (от -75° до +75° от вертикали)
        const aStart = -Math.PI / 2 - Math.PI * 0.42;
        const aEnd   = -Math.PI / 2 + Math.PI * 0.42;
        ctx.lineWidth = 2;
        ctx.strokeStyle = 'rgba(0, 212, 255, 0.55)';
        ctx.beginPath();
        ctx.arc(cx, cy, radius, aStart, aEnd);
        ctx.stroke();

        // Опасные зоны слева и справа (последние 15%, красным)
        const dangerSpan = Math.PI * 0.42 * 0.15;
        ctx.strokeStyle = 'rgba(255, 100, 100, 0.65)';
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.arc(cx, cy, radius, aStart, aStart + dangerSpan);
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(cx, cy, radius, aEnd - dangerSpan, aEnd);
        ctx.stroke();

        // Тики и подписи (-range, -range/2, 0, range/2, range)
        const range = _mmGauge.range;
        const ticks = [-1, -0.5, 0, 0.5, 1];
        ctx.fillStyle = 'rgba(220, 240, 255, 0.85)';
        ctx.font = '10px monospace';
        ctx.textAlign = 'center';
        ticks.forEach(t => {
            const ang = -Math.PI / 2 + t * Math.PI * 0.42;
            const x1 = cx + Math.cos(ang) * (radius - 6);
            const y1 = cy + Math.sin(ang) * (radius - 6);
            const x2 = cx + Math.cos(ang) * (radius + 4);
            const y2 = cy + Math.sin(ang) * (radius + 4);
            ctx.strokeStyle = 'rgba(0, 212, 255, 0.85)';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(x1, y1); ctx.lineTo(x2, y2);
            ctx.stroke();
            // Подпись
            const lx = cx + Math.cos(ang) * (radius + 16);
            const ly = cy + Math.sin(ang) * (radius + 16) + 4;
            const label = (t * range).toFixed(range < 1 ? 2 : range < 10 ? 1 : 0);
            ctx.fillText(label, lx, ly);
        });

        // Иконка-шильдик единицы и шкалы (вверху)
        ctx.fillStyle = 'rgba(127, 219, 255, 0.7)';
        ctx.font = '11px sans-serif';
        ctx.fillText(`±${range.toFixed(range < 1 ? 2 : range < 10 ? 1 : 0)} ${_mmGauge.unit}`, cx, 16);

        // Стрелка
        const needleAng = -Math.PI / 2 + _mmGauge.currentAngle;
        const needleLen = radius - 4;
        const needleX = cx + Math.cos(needleAng) * needleLen;
        const needleY = cy + Math.sin(needleAng) * needleLen;
        // Тень стрелки
        ctx.strokeStyle = 'rgba(0, 0, 0, 0.5)';
        ctx.lineWidth = 3.5;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(cx + 1, cy + 1); ctx.lineTo(needleX + 1, needleY + 1);
        ctx.stroke();
        // Стрелка сама — градиент от пивота (тёмная) к концу (яркая)
        const ng = ctx.createLinearGradient(cx, cy, needleX, needleY);
        ng.addColorStop(0, '#ffcf3d');
        ng.addColorStop(1, '#ff6b6b');
        ctx.strokeStyle = _mmGauge.valid ? ng : 'rgba(150, 150, 150, 0.6)';
        ctx.lineWidth = 2.4;
        ctx.beginPath();
        ctx.moveTo(cx, cy); ctx.lineTo(needleX, needleY);
        ctx.stroke();
        // Пивот (металлическая капля)
        ctx.fillStyle = '#1a2540';
        ctx.strokeStyle = 'rgba(0, 212, 255, 0.8)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(cx, cy, 6, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = '#7fdbff';
        ctx.beginPath();
        ctx.arc(cx, cy, 2.5, 0, Math.PI * 2);
        ctx.fill();
    }

    function updateMultimeter() {
        const display = _root && _root.querySelector('#dolgLabMmDisplay');
        const unit = _root && _root.querySelector('#dolgLabMmUnit');
        if (!display) return;
        const result = (_cbs.getLastResult && _cbs.getLastResult()) || null;
        const scheme = (_cbs.getScheme && _cbs.getScheme()) || { components: [] };
        // v17b: resolve port:compId:portId → net через portNetMap
        const a = _resolvePortToNet(state.multimeter.nodeA, scheme);
        const b = state.multimeter.nodeB ? _resolvePortToNet(state.multimeter.nodeB, scheme) : null;

        if (state.multimeter.mode === 'Ohm') {
            const r = findResistorBetween(scheme, a, b || '0');
            display.textContent = r != null ? fmtOhm(r) : '----';
            unit.textContent = r != null ? 'Ω (из схемы)' : 'Ω — нет R между узлами';
            _setMmTarget(r, 'Ω', r != null);
            return;
        }

        // §1 (юзер) Прозвонка: пищит когда есть проводимость A↔B (R < 50 Ω).
        // Анализ через graph-connectivity (union-find портов через connections).
        // Учитывает switches (closed) как проводимые, capacitor/inductor как НЕ
        // проводимые на DC (как реальный мультиметр), резисторы как «зависит от R».
        if (state.multimeter.mode === 'Cont') {
            const verdict = _continuityCheck(scheme, a, b || '0');
            display.textContent = verdict.connected ? '⏵))) BEEP' : ' OPEN ';
            unit.textContent = verdict.detail;
            _setMmTarget(verdict.connected ? 1 : 0, '', verdict.connected);
            // Простой звуковой beep — короткий WebAudio sine. Браузер заблокирует
            // если не было user-gesture'а в самой странице — это OK, юзер уже
            // переключил режим вручную (=gesture).
            if (verdict.connected) _playBeep(800, 80);
            return;
        }

        // §2 (юзер) Ток через щуп A: если в schemе есть резистор между A и B,
        // и DC-результат содержит V — считаем I = (V_A - V_B) / R.
        // Используем V_RMS если TRAN. Альтернатива I_vsource из result.vCurrents.
        if (state.multimeter.mode === 'I') {
            const r = findResistorBetween(scheme, a, b || '0');
            if (!result || !result.nodeVoltages) {
                display.textContent = '----';
                unit.textContent = 'I (запусти симуляцию)';
                _setMmTarget(0, 'А', false);
                return;
            }
            const va = parseFloat(result.nodeVoltages[a] || 0);
            const vb = b ? parseFloat(result.nodeVoltages[b] || 0) : 0;
            if (r != null && r > 0) {
                const cur = (va - vb) / r;
                display.textContent = _fmtCurrent(cur);
                unit.textContent = 'A (через R=' + fmtOhm(r) + ')';
                _setMmTarget(cur, 'А', true);
            } else {
                // Нет резистора — ищем ток через V-источник между узлами
                const vSrcId = _findVSourceBetween(scheme, a, b || '0');
                const cur = vSrcId != null && result.vCurrents
                          ? parseFloat(result.vCurrents[vSrcId])
                          : NaN;
                display.textContent = isFinite(cur) ? _fmtCurrent(cur) : '----';
                unit.textContent = isFinite(cur)
                    ? 'A (через V-источник)'
                    : 'I (нет R или V между узлами)';
                _setMmTarget(cur, 'А', isFinite(cur));
            }
            return;
        }

        if (!result || !result.nodeVoltages) {
            display.textContent = '- - - -';
            unit.textContent = 'В';
            _setMmTarget(0, 'В', false);
            return;
        }
        const va = parseFloat(result.nodeVoltages[a] || 0);
        const vb = b ? parseFloat(result.nodeVoltages[b] || 0) : 0;

        if (state.multimeter.mode === 'V') {
            const v = va - vb;
            display.textContent = fmtVolts(v);
            unit.textContent = 'В DC';
            _setMmTarget(v, 'В', true);
        } else if (state.multimeter.mode === 'V_RMS') {
            if (result.type !== 'tran' || !result.points) {
                display.textContent = '----';
                unit.textContent = 'V_RMS (нет TRAN)';
                _setMmTarget(0, 'В RMS', false);
                return;
            }
            let s = 0, n = 0;
            for (const p of result.points) {
                const da = parseFloat(p[a] || 0);
                const db = b ? parseFloat(p[b] || 0) : 0;
                const d = da - db;
                if (isFinite(d)) { s += d * d; n++; }
            }
            const rms = n ? Math.sqrt(s / n) : NaN;
            display.textContent = isFinite(rms) ? fmtVolts(rms) : '----';
            unit.textContent = 'В RMS';
            _setMmTarget(rms, 'В RMS', isFinite(rms));
        }
    }

    // §1 Прозвонка: проверка цепи между узлами A и B на DC.
    // Connected если:
    //   а) A == B (тривиально, провод 0 Ω)
    //   б) есть резистор < 50 Ω в цепи (включая 0 Ω провода)
    //   в) есть прямой провод (union-find net'ов: nodeA == nodeB после связей)
    //   г) есть закрытый switch между узлами
    // NOT connected (open) если:
    //   - конденсатор/индуктор в роли единственного пути (на DC C=open, L=short
    //     но в реальном мультиметре L шунтирует постоянку — обработаем как
    //     connected с малым R)
    //   - reachable путь только через diode в обратной полярности
    function _continuityCheck(scheme, a, b) {
        if (a == null || b == null) return { connected: false, detail: 'нет щупов' };
        if (String(a) === String(b)) return { connected: true, detail: 'один и тот же узел' };
        const portNetMap = getPortNetMapForScheme(scheme);
        if (!portNetMap) return { connected: false, detail: 'нет схемы' };
        // Если netId на A == netId на B → провод
        if (String(a) === String(b)) return { connected: true, detail: 'провод 0 Ω' };
        // Ищем компоненты между этими netId'ами (резисторы / switches / индукторы)
        const comps = scheme.components || [];
        for (const c of comps) {
            const ports = c.ports || [];
            if (ports.length < 2) continue;
            const nets = ports.map(p => portNetMap.get(c.id + ':' + p.id));
            if (!nets.includes(String(a)) && !nets.includes(a) &&
                !nets.includes(String(b)) && !nets.includes(b)) continue;
            const hasA = nets.some(n => String(n) === String(a));
            const hasB = nets.some(n => String(n) === String(b));
            if (!hasA || !hasB) continue;
            const t = (c.type || '').toLowerCase();
            if (t === 'resistor') {
                const r = parseFloat(c.resistance || c.value || 0);
                if (r >= 0 && r < 50) {
                    return { connected: true, detail: 'R = ' + fmtOhm(r) + ' (< 50 Ω)' };
                } else if (r >= 50 && r < 1000) {
                    return { connected: false, detail: 'R = ' + fmtOhm(r) + ' слишком большой' };
                }
            } else if (t === 'switch') {
                const closed = c.closed !== false;
                if (closed) return { connected: true, detail: 'switch замкнут' };
            } else if (t === 'inductor') {
                return { connected: true, detail: 'L короткозамкнут на DC' };
            } else if (t === 'wire' || t === 'node') {
                return { connected: true, detail: 'провод' };
            }
        }
        return { connected: false, detail: 'OPEN — нет цепи' };
    }

    // Поиск V-источника между узлами (для режима «I через V»)
    function _findVSourceBetween(scheme, a, b) {
        const portNetMap = getPortNetMapForScheme(scheme);
        if (!portNetMap) return null;
        for (const c of (scheme.components || [])) {
            if ((c.type || '').toLowerCase() !== 'battery') continue;
            const ports = c.ports || [];
            if (ports.length < 2) continue;
            const nets = ports.map(p => portNetMap.get(c.id + ':' + p.id));
            const hasA = nets.some(n => String(n) === String(a));
            const hasB = nets.some(n => String(n) === String(b));
            if (hasA && hasB) return c.id;
        }
        return null;
    }

    // Форматирование тока для display
    function _fmtCurrent(i) {
        if (!isFinite(i)) return '----';
        const a = Math.abs(i);
        if (a < 1e-6) return (i * 1e9).toFixed(1) + ' нА';
        if (a < 1e-3) return (i * 1e6).toFixed(2) + ' мкА';
        if (a < 1) return (i * 1000).toFixed(2) + ' мА';
        return i.toFixed(3) + ' А';
    }

    // Beep через WebAudio. 800 Hz sine 80ms — характерный «прозвонка» звук.
    // Если AudioContext не создаётся (no user-gesture / iframe) — silent.
    let _audioCtx = null;
    function _playBeep(freq, durationMs) {
        try {
            if (!_audioCtx) _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            const ctx = _audioCtx;
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.value = freq || 800;
            gain.gain.value = 0.08;
            osc.connect(gain).connect(ctx.destination);
            osc.start();
            osc.stop(ctx.currentTime + (durationMs || 100) / 1000);
        } catch (e) { /* no audio context — ignore */ }
    }

    function getPortNetMapForScheme(scheme) {
        if (
            window.DolgSchemeNetlist &&
            typeof window.DolgSchemeNetlist.buildPortNetMap === 'function' &&
            _cbs &&
            typeof _cbs.getComponentPorts === 'function'
        ) {
            try {
                return window.DolgSchemeNetlist.buildPortNetMap(
                    scheme.components || [],
                    scheme.connections || [],
                    _cbs.getComponentPorts
                );
            } catch (e) {
                console.warn('[DolgLab] cannot build port-net map:', e);
            }
        }
        if (window._lastPortNetMap && window._lastPortNetMap.size) {
            return window._lastPortNetMap;
        }
        return null;
    }

    function findResistorBetween(scheme, a, b) {
        // Честный поиск через port→net карту, построенную тем же union-find
        // алгоритмом, что и SPICE-генератор. Резистор «между узлами a и b»
        // если его порты лежат на нетах с такими же netId. Несколько R в
        // параллель → возвращаем 1/(1/R1 + 1/R2 + ...).
        const map = getPortNetMapForScheme(scheme);
        if (!map) return null;
        const comps = scheme.components || [];
        let conductanceSum = 0;
        for (const comp of comps) {
            if ((comp.type || '').toLowerCase() !== 'resistor') continue;
            const r = parseFloat(comp.resistance);
            if (!isFinite(r) || r <= 0) continue;
            const netA = map.get(comp.id + ':a');
            const netB = map.get(comp.id + ':b');
            if (!netA || !netB) continue;
            // Целевая пара (a, b) или (b, a) — порядок не важен.
            const matched = (netA === a && netB === (b || '0')) ||
                            (netB === a && netA === (b || '0'));
            if (matched) conductanceSum += 1 / r;
        }
        return conductanceSum > 0 ? (1 / conductanceSum) : null;
    }

    // --- Генератор сигналов ----------------------------------------------------
    function drawGenPreview() {
        const canvas = _root && _root.querySelector('#dolgLabGenPreview');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const W = canvas.width, H = canvas.height;
        ctx.fillStyle = '#0a1828';
        ctx.fillRect(0, 0, W, H);
        ctx.strokeStyle = 'rgba(120, 140, 200, 0.25)';
        ctx.beginPath();
        ctx.moveTo(0, H / 2); ctx.lineTo(W, H / 2);
        ctx.stroke();
        // Рисуем ~3 периода
        const periods = 3;
        const samples = 200;
        const amp = state.gen.amplitude;
        const off = state.gen.offset;
        const yScale = (H * 0.4) / Math.max(0.01, amp + Math.abs(off));
        const yMid = H / 2 - off * yScale * 0.5;
        ctx.strokeStyle = '#7fdbff';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        for (let i = 0; i <= samples; i++) {
            const t = (i / samples) * periods;
            const phase = (t % 1);
            let v;
            if (state.gen.wave === 'square') {
                v = phase < 0.5 ? amp : -amp;
            } else if (state.gen.wave === 'triangle') {
                v = phase < 0.5 ? (amp * (4 * phase - 1)) : (amp * (3 - 4 * phase));
            } else {
                v = amp * Math.sin(2 * Math.PI * t);
            }
            const x = (i / samples) * W;
            const y = yMid - (v + off) * yScale;
            if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
        // Подпись
        ctx.fillStyle = '#aaa';
        ctx.font = '11px monospace';
        ctx.fillText(`${state.gen.wave}, A=${amp}В, f=${fmtFreq(state.gen.frequency)}, off=${off}В`, 6, H - 6);
    }

    function applyGenerator() {
        if (!_cbs.applyToBattery || state.gen.targetCompId == null) {
            if (_cbs.notify) _cbs.notify('⚠️ В схеме нет источника, к которому можно подключить генератор', 'warning');
            return;
        }
        _cbs.applyToBattery(state.gen.targetCompId, {
            wave: state.gen.wave,
            amplitude: state.gen.amplitude,
            frequency: state.gen.frequency,
            offset: state.gen.offset,
        });
        if (_cbs.requestRerun) _cbs.requestRerun();
    }

    // 2026-06-01 recovery #3: setProbeNet — выставляет net в scope/mm,
    // вызывается из probeThisWire (ПКМ на проводе). Раньше функция отсутствовала
    // и весь flow Probe ПКМ → Лаб не работал.
    function setProbeNet(netId) {
        if (netId == null || !_root) return;
        const key = String(netId);
        state.scope.channel = key;
        state.multimeter.nodeA = key;
        // Если есть селекторы — синхронизируем UI
        const $ = (id) => _root.querySelector('#' + id);
        const ch = $('dolgLabScopeChannel');
        if (ch) {
            // Если опция уже есть — просто выставляем; иначе добавляем
            if (![...ch.options].some(o => o.value === key)) {
                const opt = document.createElement('option');
                opt.value = key; opt.textContent = 'V(' + key + ')';
                ch.appendChild(opt);
            }
            ch.value = key;
        }
        const aSel = $('dolgLabMmNodeA');
        if (aSel) {
            if (![...aSel.options].some(o => o.value === key)) {
                const opt = document.createElement('option');
                opt.value = key; opt.textContent = 'node ' + key;
                aSel.appendChild(opt);
            }
            aSel.value = key;
        }
        refresh();
    }

    window.DolgLab = { init, refresh, dispose, setProbeNet };
})(window);
