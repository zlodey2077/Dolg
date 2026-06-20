// Server-engine UI render helpers for simulation.html.
// Pure functions live here so the template keeps only DOM/API wiring.
(function (window) {
    'use strict';

    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function formatValue(value) {
        if (Array.isArray(value)) {
            return value.length ? `${formatValue(value[0])} ... (${value.length})` : '[]';
        }
        if (typeof value === 'number') {
            if (!Number.isFinite(value)) return String(value);
            const abs = Math.abs(value);
            if (abs > 0 && abs < 0.001) return value.toExponential(4);
            if (abs >= 100000) return value.toExponential(4);
            return Number(value.toPrecision(6)).toString();
        }
        if (typeof value === 'object' && value !== null) return JSON.stringify(value).slice(0, 80);
        return String(value);
    }

    function normalizeRows(rows, mapRows, valueKey, unit) {
        if (Array.isArray(rows)) {
            return rows.slice(0, 16).map(row => ({
                id: row.id || row.name || 'value',
                value: row[valueKey] !== undefined ? row[valueKey] : (row.value !== undefined ? row.value : row.samples),
                unit: row.unit || unit,
            }));
        }
        if (rows && typeof rows === 'object') {
            return Object.entries(rows).slice(0, 16).map(([id, value]) => ({ id, value, unit }));
        }
        if (mapRows && typeof mapRows === 'object') {
            return Object.entries(mapRows).slice(0, 16).map(([id, value]) => ({ id, value, unit }));
        }
        return [];
    }

    function renderWarnings(warnings) {
        const list = Array.isArray(warnings) ? warnings.filter(Boolean).slice(0, 6) : [];
        if (!list.length) return '';
        return list.map(warning => `<div style="color:#ffd38a;">! ${escapeHtml(warning)}</div>`).join('');
    }

    function renderTable(title, rows) {
        const body = rows.map(row => `
            <tr>
                <td><code>${escapeHtml(row.id)}</code></td>
                <td>${escapeHtml(formatValue(row.value))}</td>
                <td>${escapeHtml(row.unit || '')}</td>
            </tr>
        `).join('');
        return `
            <table class="server-engine-result-table">
                <thead><tr><th>${escapeHtml(title)}</th><th>Значение</th><th>Ед.</th></tr></thead>
                <tbody>${body}</tbody>
            </table>
        `;
    }

    function renderResult(result, job) {
        if (!result || typeof result !== 'object') return '';
        const nodes = normalizeRows(result.nodes, result.node_voltages, 'voltage_v', 'V');
        const branches = normalizeRows(result.branches, result.currents_a, 'current_a', 'A');
        const metrics = Object.entries(result.metrics || {})
            .filter(([, value]) => value !== null && value !== undefined && value !== '')
            .slice(0, 10)
            .map(([key, value]) => `<span>${escapeHtml(key)}: <code>${escapeHtml(formatValue(value))}</code></span>`)
            .join('');
        return `
            <div class="server-engine-result">
                <div class="server-engine-job-status__head">
                    <strong>${escapeHtml((job && job.engine_name) || result.engine_name || result.engine || 'server engine')}</strong>
                    <span class="server-engine-job-status__badge">${escapeHtml(result.analysis_type || (job && job.analysis_type) || 'result')}</span>
                </div>
                ${metrics ? `<div class="server-engine-result-metrics">${metrics}</div>` : ''}
                ${nodes.length ? renderTable('Узлы', nodes) : ''}
                ${branches.length ? renderTable('Ветви', branches) : ''}
                ${renderWarnings(result.warnings)}
            </div>
        `;
    }

    function renderSummary(summary, router) {
        const connected = (summary.by_status && summary.by_status.connected) || 0;
        const adapters = ((summary.by_status && summary.by_status['adapter-ready']) || 0)
            + ((summary.by_status && summary.by_status['primary-candidate']) || 0);
        return [
            ['Всего движков', summary.total || 0],
            ['Docker/REST готовы', summary.docker_rest_ready || adapters],
            ['Уже подключены', connected],
            ['Основной серверный', router.primary_engine || summary.primary_candidate || 'xyce'],
        ].map(([label, value]) => (
            `<div class="server-engine-stat"><small>${escapeHtml(label)}</small><strong>${escapeHtml(value)}</strong></div>`
        )).join('');
    }

    function renderRouter(router) {
        const docker = (router.docker_services || []).map(item => `<code>${escapeHtml(item)}</code>`).join(' ');
        const fallback = (router.fallback_order || []).map(item => `<code>${escapeHtml(item)}</code>`).join(' -> ');
        return `
            <strong>Единый контур:</strong> ${escapeHtml(router.strategy || 'engine-router выбирает backend под задачу.')}
            <br><strong>REST-контракт:</strong> <code>${escapeHtml((router.contract || {}).submit || 'POST /engines/{engine_id}/jobs')}</code>,
            <code>${escapeHtml((router.contract || {}).status || 'GET /engines/jobs/{job_id}')}</code>,
            <code>${escapeHtml((router.contract || {}).result || 'GET /engines/jobs/{job_id}/result')}</code>
            <br><strong>Fallback:</strong> ${fallback || '<code>xyce</code> -> <code>pyspice</code>'}
            <br><strong>Docker/Kubernetes:</strong> ${docker || '<code>engine-gateway</code> <code>xyce-worker</code>'}
        `;
    }

    function renderTabs(categories, active) {
        const safeActive = active || '';
        const all = `<button type="button" class="server-engine-tab ${safeActive ? '' : 'active'}" onclick="renderServerEngineCatalog('')">Все</button>`;
        const buttons = (categories || []).map(cat => (
            `<button type="button" class="server-engine-tab ${safeActive === cat.key ? 'active' : ''}" onclick="renderServerEngineCatalog('${escapeHtml(cat.key)}')">${escapeHtml(cat.label)}</button>`
        )).join('');
        return all + buttons;
    }

    function renderCard(engine, options) {
        const opts = options || {};
        const tags = (engine.tags || []).slice(0, 5).map(tag => `<span>${escapeHtml(tag)}</span>`).join('');
        const outputs = (engine.outputs || []).slice(0, 3).join(', ');
        const primary = engine.id === opts.primaryId || engine.status === 'primary-candidate';
        const recommended = Boolean(opts.recommended);
        return `
            <article class="server-engine-card ${primary ? 'server-engine-card--primary' : ''}">
                <header>
                    <h3>${escapeHtml(engine.name)}${recommended ? ' · рекомендован' : ''}</h3>
                    <span class="server-engine-status" data-status="${escapeHtml(engine.status || '')}">${escapeHtml(engine.status_label || engine.status || 'status')}</span>
                </header>
                <p>${escapeHtml(engine.task || '')}</p>
                <p>${escapeHtml(engine.fit || '')}</p>
                <dl>
                    <dt>Интеграция</dt><dd>${escapeHtml(engine.integration || '')}</dd>
                    <dt>Endpoint</dt><dd><code>${escapeHtml(engine.endpoint || '-')}</code></dd>
                    <dt>Выход</dt><dd>${escapeHtml(outputs || 'JSON/artifacts')}</dd>
                    <dt>Лицензия</dt><dd>${escapeHtml(engine.license || '-')}</dd>
                </dl>
                <button type="button" class="server-engine-card-action" onclick="selectServerEngine('${escapeHtml(engine.id)}')">Выбрать</button>
                <div class="server-engine-tags">${tags}</div>
            </article>
        `;
    }

    function renderQueueItem(job) {
        const status = String(job.status || 'queued');
        const title = `Job #${job.id || ''}`;
        const engine = job.engine_name || job.engine_id || '';
        const analysis = job.analysis_type || '';
        const progress = Number(job.progress_percent || 0);
        return `
            <button type="button" class="server-engine-queue__item" onclick="selectServerEngineJob(${Number(job.id) || 0})">
                <code>${escapeHtml(title)}</code>
                <span>${escapeHtml(engine)}</span>
                <span>${escapeHtml(analysis)} · ${Math.max(0, Math.min(progress, 100))}%</span>
                <span class="server-engine-queue__badge" data-status="${escapeHtml(status)}">${escapeHtml(status)}</span>
            </button>
        `;
    }

    function countJobs(jobs) {
        return (jobs || []).reduce((acc, job) => {
            const status = String(job.status || 'queued');
            acc[status] = (acc[status] || 0) + 1;
            return acc;
        }, {});
    }

    const api = {
        countJobs,
        escapeHtml,
        formatValue,
        normalizeRows,
        renderCard,
        renderQueueItem,
        renderResult,
        renderRouter,
        renderSummary,
        renderTable,
        renderTabs,
        renderWarnings,
    };

    window.DolgServerEngineUI = api;
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(window);
