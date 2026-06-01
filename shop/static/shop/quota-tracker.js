/**
 * DOLG Quota Tracker — live-counter «15/20 today» в редакторах для auth-юзера.
 *
 * Что делает:
 *   1) Опрашивает GET /api/usage/today/ каждую минуту (и при загрузке).
 *   2) Обновляет элементы [data-quota-counter="simulations|ai_requests|projects"]
 *      их текущим значением «X/Y» с цветовым кодом (зелёный → жёлтый → красный).
 *   3) Глобальный fetch-перехватчик: ответ 429 от любого endpoint → модал
 *      «Лимит исчерпан, сбросится в 00:00».
 *
 * Не требует никакого кода в страницах кроме <span data-quota-counter="..."></span>.
 */
(function (window, document) {
    'use strict';

    const POLL_INTERVAL_MS = 60_000;   // раз в минуту
    const USAGE_URL = '/api/usage/today/';

    function isGuest() {
        return document.body && document.body.dataset.userAuth !== '1';
    }

    function colorize(elem, current, limit) {
        if (!limit || limit === null) return;
        const ratio = current / limit;
        elem.classList.remove('quota-counter--ok', 'quota-counter--warn', 'quota-counter--full');
        if (ratio >= 1) elem.classList.add('quota-counter--full');
        else if (ratio >= 0.8) elem.classList.add('quota-counter--warn');
        else elem.classList.add('quota-counter--ok');
    }

    function applyToElements(summary) {
        if (!summary || !summary.limits || !summary.usage) return;
        const mapping = {
            simulations: ['usage.simulations_today', 'limits.simulations_per_day'],
            ai_requests: ['usage.ai_requests_today', 'limits.ai_requests_per_day'],
            projects:    ['usage.projects',          'limits.max_projects'],
            share_links: ['usage.active_share_links', 'limits.max_active_share_links'],
        };
        document.querySelectorAll('[data-quota-counter]').forEach(el => {
            const key = el.dataset.quotaCounter;
            const path = mapping[key];
            if (!path) return;
            const get = (obj, p) => p.split('.').reduce((o, k) => o && o[k], obj);
            const current = get(summary, path[0]);
            const limit = get(summary, path[1]);
            if (current == null) return;
            if (limit == null) {
                el.textContent = `${current} / ∞`;
            } else {
                el.textContent = `${current} / ${limit}`;
                colorize(el, current, limit);
            }
        });
    }

    async function fetchUsage() {
        try {
            const r = await fetch(USAGE_URL, {credentials: 'same-origin', headers: {Accept: 'application/json'}});
            if (!r.ok) return;
            const data = await r.json();
            applyToElements(data);
        } catch (e) {
            // молчим — не критично, в фоне
        }
    }

    // ── 429-перехватчик ────────────────────────────────────────────────
    // Оборачиваем глобальный fetch: при 429-ответе с известным JSON
    // показываем понятный модал. Используем DolgAuthModal как fallback,
    // иначе alert. Не сломает оригинальный fetch — он всё равно вернёт response.
    const origFetch = window.fetch;
    window.fetch = function (...args) {
        return origFetch.apply(this, args).then(async (resp) => {
            if (resp.status === 429) {
                let parsed = null;
                try {
                    // Клонируем чтобы не «съесть» body для caller'а
                    parsed = await resp.clone().json();
                } catch (e) { /* not JSON */ }
                if (parsed && parsed.error === 'quota_exceeded') {
                    showQuotaModal(parsed);
                }
            }
            return resp;
        });
    };

    function showQuotaModal(payload) {
        if (window.DolgQuotaModal && window.DolgQuotaModal._open) return;  // дедуп
        ensureModalStyle();
        const overlay = document.createElement('div');
        overlay.className = 'dolg-quota-overlay';
        const action = payload.action || 'действие';
        const limit = payload.limit || '?';
        const resetTime = payload.resets_at
            ? new Date(payload.resets_at).toLocaleString('ru-RU', {hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit'})
            : '00:00';
        overlay.innerHTML = `
            <div class="dolg-quota-modal" role="alertdialog" aria-modal="true">
                <button type="button" class="dolg-quota-close" aria-label="Закрыть">✕</button>
                <span class="dolg-quota-icon">⚡</span>
                <h3>Дневной лимит исчерпан</h3>
                <p>${payload.message || 'Достигнут лимит ' + limit + ' для действия «' + action + '».'}</p>
                <p class="dolg-quota-reset">Счётчик сбросится: <strong>${resetTime}</strong></p>
                <div class="dolg-quota-actions">
                    <button type="button" class="dolg-quota-btn dolg-quota-btn--ghost" data-action="close">Понятно</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        window.DolgQuotaModal = {_open: true};
        const close = () => {
            overlay.remove();
            window.DolgQuotaModal._open = false;
        };
        overlay.querySelector('.dolg-quota-close').addEventListener('click', close);
        overlay.querySelector('[data-action="close"]').addEventListener('click', close);
        overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
    }

    function ensureModalStyle() {
        if (document.getElementById('dolg-quota-modal-style')) return;
        const css = `
        .dolg-quota-overlay {
            position: fixed; inset: 0;
            background: rgba(5, 8, 20, 0.78); backdrop-filter: blur(4px);
            z-index: 11500;
            display: flex; align-items: center; justify-content: center;
            animation: dolg-quota-fade 0.18s ease-out;
        }
        @keyframes dolg-quota-fade { from {opacity:0;} to {opacity:1;} }
        .dolg-quota-modal {
            background: linear-gradient(135deg, #1a2540, #0a0e27);
            border: 1px solid #ffb84d;
            border-radius: 10px;
            padding: 1.6rem 1.8rem;
            max-width: 440px; width: calc(100% - 32px);
            color: #fff; text-align: center; position: relative;
            box-shadow: 0 16px 48px rgba(0, 0, 0, 0.5), 0 0 32px rgba(255, 184, 77, 0.18);
        }
        .dolg-quota-icon { font-size: 2.6rem; display: block; margin-bottom: 0.5rem; }
        .dolg-quota-modal h3 { color: #ffb84d; font-size: 1.15rem; margin: 0 0 0.5rem; }
        .dolg-quota-modal p { color: rgba(220, 240, 255, 0.85); font-size: 0.88rem; line-height: 1.5; margin: 0.3rem 0; }
        .dolg-quota-reset strong { color: #ffd093; }
        .dolg-quota-actions { display: flex; justify-content: center; gap: 0.5rem; margin-top: 1rem; }
        .dolg-quota-btn {
            padding: 0.55rem 1.1rem; border-radius: 6px; font-weight: 700;
            font-size: 0.85rem; cursor: pointer; border: 1px solid transparent;
        }
        .dolg-quota-btn--ghost { background: transparent; color: #fff; border-color: rgba(0, 212, 255, 0.4); }
        .dolg-quota-btn--ghost:hover { background: rgba(0, 212, 255, 0.12); }
        .dolg-quota-close {
            position: absolute; top: 0.5rem; right: 0.7rem;
            background: transparent; border: none; color: rgba(255,255,255,0.55);
            font-size: 1.4rem; cursor: pointer; line-height: 1;
        }
        .dolg-quota-close:hover { color: #fff; }

        /* Counter-чипы в редакторах */
        [data-quota-counter] {
            display: inline-block;
            padding: 0.18rem 0.55rem;
            border-radius: 999px;
            font-family: monospace; font-size: 0.78rem; font-weight: 600;
            background: rgba(80, 250, 123, 0.15);
            color: #50fa7b;
            border: 1px solid rgba(80, 250, 123, 0.4);
        }
        [data-quota-counter].quota-counter--warn {
            background: rgba(255, 184, 77, 0.15); color: #ffb84d; border-color: rgba(255, 184, 77, 0.4);
        }
        [data-quota-counter].quota-counter--full {
            background: rgba(255, 107, 107, 0.15); color: #ff6b6b; border-color: rgba(255, 107, 107, 0.45);
        }
        `;
        const style = document.createElement('style');
        style.id = 'dolg-quota-modal-style';
        style.textContent = css;
        document.head.appendChild(style);
    }

    // ── Init ──────────────────────────────────────────────────────────
    if (isGuest()) return;        // для guest квот через DailyUsage нет
    function init() {
        ensureModalStyle();
        fetchUsage();
        setInterval(fetchUsage, POLL_INTERVAL_MS);
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else { init(); }

    window.DolgQuotaTracker = {fetchUsage, showQuotaModal};
})(window, document);
