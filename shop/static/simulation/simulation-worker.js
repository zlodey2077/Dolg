// =============================================================================
// DOLG Simulation Web Worker.
// Принимает сообщения { id, cmd, circuit, analysis, params }, гоняет MNA-движок
// в изолированном потоке и отдаёт { id, ok, result | error }.
//
// Диплом (раздел 2.5, 2.7): вычислительное ядро должно жить в Web Worker, чтобы
// не блокировать рендер UI. Будущая интеграция ngspice.wasm заменит только
// importScripts ниже — контракт сообщений не меняется.
// =============================================================================

/* global importScripts, SimEngine */

// ?v=… — cache-bust, чтобы браузерный кэш не подсовывал старую сборку
// движка (с прежним AC-fallback'ом «показана DC-точка»).
const ENGINE_V = '20260426g';
try {
    importScripts('/static/simulation/simulation-engine.js?v=' + ENGINE_V);
} catch (e) {
    importScripts('./simulation-engine.js?v=' + ENGINE_V);
}

self.addEventListener('message', function (ev) {
    const msg = ev.data || {};
    const { id, cmd, circuit, analysis, params } = msg;

    if (cmd === 'ping') {
        self.postMessage({ id, ok: true, pong: true, engineVersion: SimEngine._version });
        return;
    }

    if (cmd !== 'run') {
        self.postMessage({ id, ok: false, error: 'Неизвестная команда: ' + cmd });
        return;
    }

    try {
        const t0 = Date.now();
        const result = SimEngine.runSimulation(circuit, analysis, params || {});
        const elapsedMs = Date.now() - t0;
        self.postMessage({ id, ok: true, result, elapsedMs, engineVersion: SimEngine._version });
    } catch (err) {
        self.postMessage({
            id,
            ok: false,
            error: err && err.message ? err.message : String(err),
            stack: err && err.stack ? err.stack : null,
        });
    }
});
