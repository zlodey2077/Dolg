// =============================================================================
// DOLG — Worker для ngspice.wasm.
//
// Настоящий ngspice, скомпилированный в WebAssembly (порт danchitnis/ngspice,
// ngspice 33 + Emscripten 2.0.7). Реализует SPICE-анализы: .op, .dc, .ac, .tran.
//
// Особенность: Emscripten-билд НЕ модуляризован — Module живёт в global scope и
// main() запускается один раз при загрузке ngspice.js. Поэтому каждый запуск
// симуляции требует СВЕЖЕГО worker'а: главный поток создаёт worker,
// отправляет netlist, получает результат, terminate().
// =============================================================================

let capturedLines = [];
let msgId = null;
let analysisKind = 'op';

// Универсальный поиск FS в окружении Emscripten. В разных сборках FS
// экспортируется по-разному:
//  - self.FS — если EXPORT_NAME='Module' и FS на глобал (старые сборки);
//  - self.Module.FS — современный путь;
//  - переданный аргумент (preRun(FS_arg) в новых Emscripten).
function _resolveFS(arg) {
    return arg
        || (self.Module && self.Module.FS)
        || (typeof FS !== 'undefined' ? FS : null)
        || self.FS;
}

self.onmessage = function (ev) {
    const { id, netlist, analysis, assetsVersion } = ev.data || {};
    msgId = id;
    analysisKind = (analysis || 'op').toLowerCase();
    capturedLines = [];
    // Версия для cache-bust ngspice.js + ngspice.wasm. Прокидывается из main
    // потока, чтобы при бампе версии не забывать править worker отдельно.
    const ver = assetsVersion || 'dev';

    // Стратегия: НЕ запускаем main автоматически. После runtime-init пишем
    // netlist в файл (FS уже точно доступен), затем явно зовём callMain
    // с теми же аргументами. Это надёжнее, чем preRun, который в этой
    // сборке Emscripten срабатывает ДО инициализации FS.
    let _hasRun = false;
    let _postRunFired = false;

    function finalizeAndPost() {
        _postRunFired = true;
        try {
            const FS = _resolveFS();
            let acFileText = '';
            if (analysisKind === 'ac' && FS && FS.readFile) {
                try {
                    acFileText = FS.readFile('/ac_results.txt', { encoding: 'utf8' }) || '';
                } catch (e) { /* нет файла — норма */ }
            }
            const result = parseNgspiceOutput(capturedLines, analysisKind, netlist, acFileText);
            self.postMessage({
                id: msgId, ok: true, result,
                engineVersion: 'ngspice-33-wasm',
                rawOutput: capturedLines.join('\n'),
            });
        } catch (e) {
            sendError('Ошибка парсинга вывода ngspice: ' + e.message);
        }
    }

    self.Module = {
        arguments: ['-b', '/circuit.cir'],
        noInitialRun: true,
        locateFile: function (path) {
            // Cache-bust для ngspice.wasm — браузер мог закэшировать
            // старый wasm без поддержки нашего патченного callMain/FS.
            return '/static/simulation/' + path + '?v=' + ver;
        },
        // Запасной путь — если эта сборка ngspice игнорирует noInitialRun
        // и сама зовёт main: попытаемся записать файл здесь.
        preRun: [function (FS_arg) {
            try {
                const FS = _resolveFS(FS_arg);
                if (FS && FS.writeFile) FS.writeFile('/circuit.cir', netlist);
            } catch (e) { /* пропустим — попробуем в onRuntimeInitialized */ }
        }],
        onRuntimeInitialized: function () {
            try {
                const FS = _resolveFS();
                if (!FS || !FS.writeFile) {
                    return sendError('FS API недоступен после runtime init');
                }
                FS.writeFile('/circuit.cir', netlist);
                if (_hasRun) return;
                _hasRun = true;
                if (!self.Module.callMain) {
                    return sendError('callMain не экспортирован в этой сборке ngspice.js');
                }
                try {
                    self.Module.callMain(['-b', '/circuit.cir']);
                } catch (e) {
                    // ngspice вызывает exit(0) — Emscripten бросает ExitStatus, это норма.
                    if (!String(e).includes('ExitStatus')) {
                        return sendError('callMain: ' + (e && e.message || e));
                    }
                }
                // Если postRun не сработал сам — вызовем парсинг вручную.
                if (!_postRunFired) finalizeAndPost();
            } catch (e) {
                sendError('Не удалось записать netlist: ' + e.message);
            }
        },
        postRun: [function () {
            // postRun может сработать сам после callMain. Повторно не вызываем.
            if (!_postRunFired) finalizeAndPost();
        }],
        print: function (text) { capturedLines.push(text); },
        printErr: function (text) { capturedLines.push('ERR: ' + text); },
        onAbort: function (what) { sendError('ngspice abort: ' + what); },
    };

    try {
        // ВАЖНО: cache-bust для ngspice.js. Без него браузер подтянет
        // старую (непатченную) версию из кэша, и Module.callMain / Module.FS
        // снова окажутся undefined.
        importScripts('/static/simulation/ngspice.js?v=' + ver);
    } catch (e) {
        sendError('Не удалось загрузить ngspice.js: ' + e.message);
    }
};

function sendError(msg) {
    try {
        self.postMessage({
            id: msgId, ok: false, error: msg,
            rawOutput: capturedLines.join('\n'),
        });
    } catch (e) { /* worker уже терминирован */ }
}

// =============================================================
// Парсер stdout ngspice. Формат зависит от анализа:
//   .op   → таблица Node/Voltage (+ v*#branch для токов источников)
//   .tran → таблица Index Time V(1) V(2) … по блокам (каждый блок = набор строк)
//   .ac   → формат со столбцом frequency
// Универсальный подход: разбираем блоки заголовок+строки и извлекаем
// узлы по именам столбцов.
// =============================================================
function parseNgspiceOutput(lines, analysis, netlist, acFileText) {
    const text = lines.join('\n');
    const warnings = [];

    // Ошибки ngspice (сингулярная матрица, нет сходимости и т.п.)
    const errorRe = /(Error:.*|no such node|singular matrix|.error:.*|doAnalyses:.*)/i;
    const errorMatch = text.match(errorRe);
    if (errorMatch) warnings.push('ngspice: ' + errorMatch[0].trim());

    if (analysis === 'op' || analysis === 'dc') {
        return parseDcOutput(text, warnings);
    }
    if (analysis === 'tran' || analysis === 'transient' || analysis === 'pulse') {
        return parseTranOutput(text, warnings);
    }
    if (analysis === 'ac') {
        return parseAcOutput(acFileText || '', warnings, text);
    }
    // Неизвестный тип анализа — возвращаем сырой текст.
    return { type: analysis, nodeVoltages: {0:0}, vCurrents: {}, diodeCurrents: {}, warnings, raw: text };
}

// ngspice DC: «имя_узла  значение» в любой строке таблицы. Компилируем один раз.
const DC_LINE_RE = /^\s*([A-Za-z0-9#_.]+)\s+(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*$/;
const DC_NODE_NUM_RE = /^\d+$/;
const DC_BRANCH_RE = /^([vVdD])(\d+)#branch$/;
const TRAN_V_RE = /^V\((\d+)\)$/i;
const AC_CPLX_RE = /(-?\d+\.?\d*(?:[eE][+-]?\d+)?)\s*,\s*(-?\d+\.?\d*(?:[eE][+-]?\d+)?)/g;

function parseDcOutput(text, warnings) {
    const nodeVoltages = { 0: 0 };
    const vCurrents = {};
    const diodeCurrents = {};

    // ngspice печатает что-то вроде:
    //    Node            Voltage
    //    ----            -------
    //    1               9.00000e+00
    //    2               2.87755e+00
    //    v1#branch      -6.12245e-04
    // В разных версиях формат чуть разный, но строка «имя + число» общая.
    for (const raw of text.split('\n')) {
        const line = raw.trim();
        if (!line) continue;
        const m = DC_LINE_RE.exec(line);
        if (!m) continue;
        const name = m[1];
        const val = parseFloat(m[2]);
        if (!isFinite(val)) continue;

        if (DC_NODE_NUM_RE.test(name)) {
            nodeVoltages[+name] = val;
        } else {
            const br = DC_BRANCH_RE.exec(name);
            if (br) {
                const elemId = +br[2];
                const kind = br[1].toUpperCase();
                // ngspice печатает ток ИЗ плюсовой клеммы в +; инвертируем,
                // чтобы совпадало с нашей конвенцией (ток ИЗ источника в схему).
                if (kind === 'V') vCurrents[elemId] = -val;
                else if (kind === 'D') diodeCurrents[elemId] = -val;
            }
        }
    }

    return { type: 'dc', nodeVoltages, vCurrents, diodeCurrents, warnings };
}

function parseTranOutput(text, warnings) {
    // ngspice печатает .tran как таблицу:
    //    Index   time            v(1)            v(2)
    //    ------  --------------  --------------  --------------
    //    0       0.000000e+00    9.000000e+00    0.000000e+00
    //    1       1.000000e-06    9.000000e+00    1.234567e-02
    //    ...
    const points = [];
    const lines = text.split('\n');
    let headers = null;      // массив имён столбцов
    let inData = false;

    for (const raw of lines) {
        const line = raw.replace(/\t/g, ' ').trim();
        if (!line) { inData = false; continue; }

        // Заголовок таблицы начинается с "Index" или "time"
        if (/^Index\b/i.test(line) || /^\s*Index\b/i.test(raw)) {
            headers = line.split(/\s+/).map(s => s.toLowerCase());
            inData = false;
            continue;
        }
        if (/^-+/.test(line) && headers) { inData = true; continue; }
        if (!inData || !headers) continue;

        const cells = line.split(/\s+/);
        if (cells.length < headers.length) continue;

        // Ожидаем первый столбец Index (целое), второй — time
        const timeCol = headers.indexOf('time');
        if (timeCol < 0) continue;
        const t = parseFloat(cells[timeCol]);
        if (!isFinite(t)) continue;

        const sample = { t };
        for (let i = 0; i < headers.length; i++) {
            const h = headers[i];
            if (h === 'index' || h === 'time') continue;
            const v = parseFloat(cells[i]);
            if (isFinite(v)) {
                // ngspice пишет "v(2)" — нормализуем в "V(2)"
                const k = h.replace(/^v\(/, 'V(').replace(/^i\(/, 'I(');
                sample[k] = v;
            }
        }
        points.push(sample);
    }

    // Итоговая DC-точка — последняя из tran
    const nodeVoltages = { 0: 0 };
    if (points.length) {
        const last = points[points.length - 1];
        for (const k in last) {
            if (k === 't') continue;
            const nm = TRAN_V_RE.exec(k);
            if (nm) nodeVoltages[+nm[1]] = last[k];
        }
    }

    return { type: 'tran', nodeVoltages, vCurrents: {}, diodeCurrents: {}, points, warnings };
}

// Fallback-парсер стандартного stdout от ngspice для .ac.
// Формат: блоки таблицы с заголовком «Index frequency v(N)» и строками вида
//   0   1.000e+00   <real>,  <imag>
// (или magnitude,phase в зависимости от complex_method). Запятая отделяет
// real от imag — мы конвертируем в дБ и градусы.
function parseAcStdoutFallback(text, warnings) {
    if (!text) return [];
    // Поддерживаем ДВА формата вывода ngspice:
    //   а) `.print ac vdb(N) vp(N)` — таблица c явными колонками vdb/vp в дБ
    //      и градусах (числа real, без запятых):
    //         Index   frequency       vdb(2)        vp(2)
    //         0       1.000e+00      -1.45e-02     -3.18e+01
    //   б) дефолтный AC без .print — комплексные «real,imag» в одном столбце:
    //         Index   frequency       v(2)
    //         0       1.000e+00       9.99e-01,    -1.6e-04
    // Склеиваем «X, Y» → «X|Y» только для случая (б); в (а) запятых нет.
    const lines = text.split('\n');
    const byFreq = new Map();
    const orderF = [];
    let cols = [];   // массив {kind: 'db'|'ph'|'cplx', node: '2'}
    let inData = false;

    for (const raw of lines) {
        // Склеиваем «X, Y» (комплексное число) в «X|Y», чтобы split по \s+
        // не разрывал пары. Regex compile вынесен на module-level (AC_CPLX_RE).
        const cleaned = raw.replace(AC_CPLX_RE, '$1|$2');
        const line = cleaned.trim();
        if (!line) { inData = false; continue; }

        // Заголовок: есть «frequency» и хотя бы одна колонка v…(N).
        const isHeader = /\bfrequency\b/i.test(line) && /v[a-z]*\(\d+\)/i.test(line);
        if (isHeader) {
            const tokens = line.split(/\s+/).map(s => s.toLowerCase());
            cols = [];
            for (const t of tokens) {
                let m;
                if ((m = t.match(/^vdb\((\d+)\)$/))) cols.push({ kind: 'db', node: m[1] });
                else if ((m = t.match(/^vp\((\d+)\)$/))) cols.push({ kind: 'ph', node: m[1] });
                else if ((m = t.match(/^v\((\d+)\)$/))) cols.push({ kind: 'cplx', node: m[1] });
                else cols.push(null);
            }
            inData = false;
            continue;
        }
        if (/^-+/.test(line)) { inData = cols.some(Boolean); continue; }
        if (!inData) continue;

        const cells = line.split(/\s+/).filter(Boolean);
        // Найдём колонку с frequency: первый числовой > 0, который не Index.
        // ngspice печатает Index первым токеном, frequency — вторым.
        let fIdx = 0;
        if (cells[0].match(/^\d+$/) && cells.length > cols.length) fIdx = 1;
        const f = parseFloat(cells[fIdx]);
        if (!isFinite(f) || f <= 0) continue;

        let s = byFreq.get(f);
        if (!s) { s = { f }; byFreq.set(f, s); orderF.push(f); }

        // Перебираем именованные колонки в cols (index/frequency дают null).
        for (let i = 0; i < cols.length; i++) {
            const col = cols[i];
            if (!col) continue;
            const cell = cells[i];
            if (!cell) continue;
            if (col.kind === 'db') {
                const v = parseFloat(cell);
                if (isFinite(v)) s[`db_${col.node}`] = v;
            } else if (col.kind === 'ph') {
                const v = parseFloat(cell);
                if (isFinite(v)) s[`ph_${col.node}`] = v;
            } else if (col.kind === 'cplx') {
                const parts = cell.split('|');
                if (parts.length === 2) {
                    const re = parseFloat(parts[0]), im = parseFloat(parts[1]);
                    if (isFinite(re) && isFinite(im)) {
                        s[`db_${col.node}`] = 20 * Math.log10(Math.max(Math.hypot(re, im), 1e-30));
                        s[`ph_${col.node}`] = (Math.atan2(im, re) * 180) / Math.PI;
                    }
                }
            }
        }
    }

    return orderF.sort((a, b) => a - b).map(f => byFreq.get(f));
}

function parseAcOutput(text, warnings, stdoutText) {
    // wrdata пишет в формате: для каждого вектора два столбца — частота и значение.
    // Если у нас просили vdb(1) vp(1) vdb(2) vp(2), на каждой строке будет:
    //   f1 db1 f1 ph1 f2 db2 f2 ph2 ...   (одна строка на одну частоту)
    if (!text) {
        // Файл /ac_results.txt не написался (например, .control блок не сработал).
        // Пытаемся распарсить дефолтный stdout-output ngspice вида:
        //   Index   frequency       v(2)
        //   0       1.000000e+00    9.998424e-01,    -1.589e-04
        // где последний столбец — комплексный «real, imag».
        const fb = parseAcStdoutFallback(stdoutText || '', warnings);
        if (fb && fb.length) {
            return { type: 'ac', nodeVoltages: {0:0}, vCurrents: {}, diodeCurrents: {}, points: fb, warnings };
        }
        warnings.push('AC-анализ: ngspice не вернул данных. Проверьте, что в схеме есть батарея.');
        return { type: 'ac', nodeVoltages: {0:0}, vCurrents: {}, diodeCurrents: {}, points: [], warnings };
    }

    // Считаем число колонок по первой непустой строке.
    const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
    if (!lines.length) {
        warnings.push('AC-анализ: ac_results.txt пуст.');
        return { type: 'ac', nodeVoltages: {0:0}, vCurrents: {}, diodeCurrents: {}, points: [], warnings };
    }
    const firstCells = lines[0].split(/\s+/).filter(Boolean);
    const nCols = firstCells.length;
    const nProbes = nCols / 2;        // каждая «проба» — два столбца (f, value)
    if (nProbes < 1) {
        warnings.push('AC-анализ: неожиданный формат ac_results.txt.');
        return { type: 'ac', nodeVoltages: {0:0}, vCurrents: {}, diodeCurrents: {}, points: [], warnings };
    }

    // Чередование проб в wrdata: vdb(N1), vp(N1), vdb(N2), vp(N2), ... — для всех узлов 1..K.
    // К сожалению, файл сам имена не хранит. Восстанавливаем имя по порядку,
    // в котором мы запросили вектора в netlist: `vdb(1) vp(1) vdb(2) vp(2) ...`.
    // Отсюда: проба k (0-indexed) = (k%2==0 ? 'db' : 'ph')_(floor(k/2)+1).
    const points = [];
    for (const line of lines) {
        const cells = line.split(/\s+/).filter(Boolean).map(parseFloat);
        if (cells.length < nCols || !isFinite(cells[0]) || cells[0] <= 0) continue;
        const sample = { f: cells[0] };
        for (let k = 0; k < nProbes; k++) {
            const v = cells[k * 2 + 1];
            if (!isFinite(v)) continue;
            const node = Math.floor(k / 2) + 1;
            const kind = (k % 2 === 0) ? 'db' : 'ph';
            sample[`${kind}_${node}`] = v;
        }
        points.push(sample);
    }

    if (!points.length) {
        warnings.push('AC-анализ: ac_results.txt не содержит валидных строк.');
    }

    return { type: 'ac', nodeVoltages: { 0: 0 }, vCurrents: {}, diodeCurrents: {}, points, warnings };
}
