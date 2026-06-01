/**
 * DOLG ML toolbar — кнопки AI pipeline в симуляторе.
 *
 * 4 действия:
 *   - anomalies (Free): DRC++ — поиск аномалий в схеме
 *   - explain (Pro):    Естественно-языковое описание
 *   - recommend (Pro):  Что добавить следующим
 *   - analogs (используется на product-detail, не в симуляторе)
 *
 * Все запросы идут через fetch на /api/ai/pipeline/<action>/.
 * Результат выводится в #results-panel (заменяет содержимое).
 * Pro-only кнопки для Free-юзеров → перехватываются auth-modal через
 * data-pro-only, но мы делаем явный модал «Это Pro-фича».
 */
(function (window, document) {
    'use strict';

    const ENDPOINTS = {
        anomalies: '/api/ai/pipeline/anomalies/',
        explain:   '/api/ai/pipeline/explain/',
        recommend: '/api/ai/pipeline/recommend/',
    };

    function isGuest() {
        return document.body && document.body.dataset.userAuth !== '1';
    }

    function getCsrfToken() {
        const m = document.cookie.match(/csrftoken=([^;]+)/);
        return m ? m[1] : '';
    }

    function getCurrentSchemeData() {
        // Используем buildSchemeData() который определён в simulation.html
        if (typeof window.buildSchemeData === 'function') {
            return window.buildSchemeData();
        }
        // Fallback — собираем по глобалам если функция не экспортнулась
        return {
            components: window.components || [],
            connections: window.connections || [],
        };
    }

    function renderToPanel(html) {
        const panel = document.getElementById('results-panel');
        if (panel) panel.innerHTML = html;
    }

    function renderAnomalies(data) {
        const list = data.anomalies || [];
        if (list.length === 0) {
            return `<div class="dolg-ml-result dolg-ml-result--ok">
                <h4>⚠️ DRC++ (расширенная проверка)</h4>
                <p>✅ Аномалий не обнаружено. Схема выглядит корректной с точки зрения топологии.</p>
                <p class="dolg-ml-note">Pipeline: phase 1 (rule-based). В production здесь GNN-классификатор.</p>
            </div>`;
        }
        const items = list.map(a => `
            <div class="dolg-ml-anomaly dolg-ml-anomaly--${a.severity}">
                <strong>[${a.severity.toUpperCase()}]</strong> ${escapeHtml(a.type)}: ${escapeHtml(a.message)}
            </div>
        `).join('');
        return `<div class="dolg-ml-result">
            <h4>⚠️ DRC++ (расширенная проверка)</h4>
            <p>Найдено аномалий: <strong>${list.length}</strong></p>
            ${items}
            <p class="dolg-ml-note">Pipeline: phase 1 (rule-based). Phase 2 — GNN-классификатор на корпусе DOLG-схем.</p>
        </div>`;
    }

    function renderExplain(data) {
        const breakdown = Object.entries(data.components_breakdown || {})
            .map(([t, n]) => `${escapeHtml(t)}: ${n}`)
            .join(' · ');
        return `<div class="dolg-ml-result">
            <h4>📝 ${escapeHtml(data.title || 'Схема')}</h4>
            <p class="dolg-ml-topology">Топология: <code>${escapeHtml(data.topology || 'unknown')}</code></p>
            <p>${escapeHtml(data.summary || '')}</p>
            ${data.estimated_use_case ? `<p><strong>Применение:</strong> ${escapeHtml(data.estimated_use_case)}</p>` : ''}
            <p class="dolg-ml-breakdown">${breakdown}</p>
            <p class="dolg-ml-note">Pipeline: phase 1 (template-engine). Phase 2 — small Transformer fine-tuned на DOLG-corpus.</p>
        </div>`;
    }

    function renderRecommend(data) {
        const list = data.recommendations || [];
        const items = list.map(r => `
            <div class="dolg-ml-rec">
                <strong>${escapeHtml(r.component_type)}</strong>
                <span class="dolg-ml-conf">${Math.round((r.confidence || 0) * 100)}%</span>
                <span class="dolg-ml-reason">${escapeHtml(r.reason)}</span>
            </div>
        `).join('');
        return `<div class="dolg-ml-result">
            <h4>➕ Рекомендации компонентов</h4>
            ${items}
            <p class="dolg-ml-note">Pipeline: phase 1 (rule-based). Phase 2 — GNN с next-component prediction.</p>
        </div>`;
    }

    function renderError(msg, status) {
        return `<div class="dolg-ml-result dolg-ml-result--error">
            <h4>❌ Ошибка ${status || ''}</h4>
            <p>${escapeHtml(msg)}</p>
        </div>`;
    }

    function renderProOnly() {
        return `<div class="dolg-ml-result dolg-ml-result--pro">
            <h4>💎 Pro-фича</h4>
            <p>Эта функция доступна только для Pro-подписки.
               <a href="/billing/">Активировать trial бесплатно</a>.</p>
        </div>`;
    }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, c => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        })[c]);
    }

    async function callPipeline(action) {
        renderToPanel(`<p class="status-running">🧠 ML pipeline: ${action}...</p>`);

        const schemeData = getCurrentSchemeData();
        const url = ENDPOINTS[action];
        if (!url) {
            renderToPanel(renderError('Unknown action: ' + action));
            return;
        }

        try {
            const resp = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                credentials: 'same-origin',
                body: JSON.stringify({ scheme_data: schemeData }),
            });

            if (resp.status === 403) {
                const data = await resp.json().catch(() => ({}));
                if (data.error === 'pro_only' || data.error === 'plan_required') {
                    renderToPanel(renderProOnly());
                    return;
                }
            }
            if (!resp.ok) {
                const text = await resp.text();
                renderToPanel(renderError(text.slice(0, 300), resp.status));
                return;
            }

            const data = await resp.json();
            if (!data.ok) {
                renderToPanel(renderError(data.message || 'unknown error'));
                return;
            }

            // Роутим вывод по action
            if (action === 'anomalies') renderToPanel(renderAnomalies(data));
            else if (action === 'explain') renderToPanel(renderExplain(data));
            else if (action === 'recommend') renderToPanel(renderRecommend(data));
        } catch (e) {
            renderToPanel(renderError(e.message || 'network error'));
        }
    }

    // Init: подвешиваем onClick
    function init() {
        document.querySelectorAll('.dolg-ml-btn[data-ml-action]').forEach(btn => {
            btn.addEventListener('click', () => {
                const action = btn.dataset.mlAction;
                if (isGuest()) {
                    if (window.DolgAuthModal) window.DolgAuthModal.show('ai');
                    return;
                }
                callPipeline(action);
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else { init(); }

    window.DolgMlToolbar = { callPipeline };
})(window, document);
