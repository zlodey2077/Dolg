/**
 * DOLG Save-CTA Banner — мягкая мотивация регистрации для guest.
 *
 * Появляется в редакторах (CAD / симулятор) когда guest:
 *   - сделал N=3 изменения схемы (порог configurable)
 *   - ИЛИ кликнул на disabled save-кнопку
 *   - ИЛИ открыл первую демо-схему и просмотрел 30 сек
 *
 * Прячется при:
 *   - клик «Скрыть» (помечается в sessionStorage — не вылезает в эту вкладку)
 *   - юзер залогинен (data-user-auth)
 *
 * API:
 *   window.DolgSaveBanner.notifyChange()  — клиент сигналит «была правка»
 *   window.DolgSaveBanner.show()          — форсировать показ
 *   window.DolgSaveBanner.hide()          — скрыть на эту сессию
 */
(function (window, document) {
    'use strict';

    const CHANGE_THRESHOLD = 3;
    const SESSION_DISMISS_KEY = 'dolg_save_banner_dismissed';

    let _changeCount = 0;
    let _shown = false;
    let _banner = null;

    function isGuest() {
        return document.body && document.body.dataset.userAuth !== '1';
    }
    function wasDismissed() {
        try { return sessionStorage.getItem(SESSION_DISMISS_KEY) === '1'; }
        catch (e) { return false; }
    }
    function setDismissed() {
        try { sessionStorage.setItem(SESSION_DISMISS_KEY, '1'); }
        catch (e) {}
    }

    function ensureStyle() {
        if (document.getElementById('dolg-save-cta-style')) return;
        const css = `
        .dolg-save-cta {
            position: fixed;
            left: 50%; bottom: 24px;
            transform: translateX(-50%) translateY(120%);
            z-index: 10800;
            background: linear-gradient(135deg, rgba(20, 30, 60, 0.98), rgba(8, 12, 30, 0.98));
            border: 1px solid var(--accent-cyan, #00d4ff);
            border-radius: 10px;
            padding: 0.85rem 1.15rem;
            box-shadow: 0 12px 32px rgba(0, 0, 0, 0.5), 0 0 22px rgba(0, 212, 255, 0.25);
            display: flex; align-items: center; gap: 0.85rem;
            max-width: calc(100% - 32px);
            color: #fff;
            transition: transform 0.32s cubic-bezier(.2, .8, .2, 1.05), opacity 0.25s;
            opacity: 0;
        }
        .dolg-save-cta.visible { transform: translateX(-50%) translateY(0); opacity: 1; }
        .dolg-save-cta__icon { font-size: 1.4rem; flex-shrink: 0; }
        .dolg-save-cta__text {
            font-size: 0.85rem; line-height: 1.4;
        }
        .dolg-save-cta__text strong { color: var(--accent-cyan, #00d4ff); }
        .dolg-save-cta__actions { display: flex; gap: 0.45rem; flex-shrink: 0; }
        .dolg-save-cta__btn {
            padding: 0.4rem 0.85rem;
            border-radius: 5px;
            font-size: 0.78rem;
            font-weight: 700;
            text-decoration: none;
            cursor: pointer;
            border: 1px solid transparent;
            white-space: nowrap;
            transition: filter 0.15s;
        }
        .dolg-save-cta__btn:hover { filter: brightness(1.15); }
        .dolg-save-cta__btn--primary {
            background: linear-gradient(135deg, var(--cosmic-blue, #2c7be5), var(--accent-cyan, #00d4ff));
            color: var(--cosmic-black, #0a0e27);
        }
        .dolg-save-cta__btn--ghost {
            background: rgba(255,255,255,0.05);
            color: rgba(255,255,255,0.75);
            border-color: rgba(255,255,255,0.18);
        }
        .dolg-save-cta__close {
            background: transparent; border: none; color: rgba(255,255,255,0.45);
            cursor: pointer; padding: 0 0.2rem; font-size: 1.1rem; line-height: 1;
        }
        .dolg-save-cta__close:hover { color: #fff; }
        @media (max-width: 580px) {
            .dolg-save-cta { flex-wrap: wrap; left: 12px; right: 12px; transform: translateY(120%); }
            .dolg-save-cta.visible { transform: translateY(0); }
        }
        `;
        const style = document.createElement('style');
        style.id = 'dolg-save-cta-style';
        style.textContent = css;
        document.head.appendChild(style);
    }

    function show() {
        if (!isGuest() || wasDismissed() || _shown) return;
        ensureStyle();
        const next = encodeURIComponent(window.location.pathname + window.location.search);
        const wrap = document.createElement('div');
        wrap.className = 'dolg-save-cta';
        wrap.setAttribute('role', 'status');
        wrap.innerHTML = `
            <span class="dolg-save-cta__icon">📌</span>
            <div class="dolg-save-cta__text">
                <strong>Эта схема существует только во вкладке.</strong>
                <br>Зарегистрируйтесь, чтобы сохранить.
            </div>
            <div class="dolg-save-cta__actions">
                <a class="dolg-save-cta__btn dolg-save-cta__btn--primary" href="/accounts/register/?next=${next}">📝 Регистрация</a>
                <a class="dolg-save-cta__btn dolg-save-cta__btn--ghost" href="/accounts/login/?next=${next}">Войти</a>
            </div>
            <button type="button" class="dolg-save-cta__close" aria-label="Скрыть до конца сессии">✕</button>
        `;
        document.body.appendChild(wrap);
        _banner = wrap;
        _shown = true;
        requestAnimationFrame(() => wrap.classList.add('visible'));
        wrap.querySelector('.dolg-save-cta__close').addEventListener('click', () => {
            setDismissed();
            hide();
        });
    }

    function hide() {
        if (!_banner) return;
        _banner.classList.remove('visible');
        const b = _banner;
        setTimeout(() => { if (b.parentNode) b.parentNode.removeChild(b); }, 320);
        _banner = null;
        _shown = false;
    }

    function notifyChange() {
        if (!isGuest() || wasDismissed()) return;
        _changeCount += 1;
        if (_changeCount >= CHANGE_THRESHOLD) show();
    }

    window.DolgSaveBanner = { notifyChange, show, hide };
})(window, document);
