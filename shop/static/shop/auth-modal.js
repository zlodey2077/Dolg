/**
 * DOLG Auth Modal — единое окно «Войдите / Зарегистрируйтесь» для guest.
 *
 * Использование:
 *   1) На любую кнопку, которая требует auth, повесить data-guest-locked="1".
 *   2) Этот скрипт перехватывает click capture-phase, если data-guest-locked
 *      есть И юзер не залогинен (флаг через body.dataset.userAuth) — показывает модал.
 *   3) Модал предлагает: «Войти» / «Зарегистрироваться» (с ?next=current_url).
 *
 * Также экспортирует API:
 *   window.DolgAuthModal.show(reason)   — показать модал явно (для AJAX-перехвата 403)
 *   window.DolgAuthModal.hide()
 */
(function (window, document) {
    'use strict';

    const REASONS = {
        save:        { icon: '💾', title: 'Войдите, чтобы сохранить',
                       text: 'Сохранение проектов доступно зарегистрированным пользователям. Бесплатно, до 10 проектов на аккаунт.' },
        load:        { icon: '📂', title: 'Войдите, чтобы открыть свои проекты',
                       text: 'Список ваших проектов хранится в аккаунте.' },
        import:      { icon: '📥', title: 'Войдите, чтобы импортировать',
                       text: 'Импортированные файлы сохраняются в ваши проекты.' },
        quota:       { icon: '⚡', title: 'Достигнут лимит для гостя',
                       text: 'Бесплатных симуляций исчерпано (5/5). Зарегистрируйтесь — получите 20 симуляций в день бесплатно.' },
        ai:          { icon: '🤖', title: 'AI-ассистент доступен с аккаунтом',
                       text: 'Войдите, чтобы получить 10 AI-запросов в день бесплатно.' },
        checkout:    { icon: '🛒', title: 'Войдите, чтобы оформить заказ',
                       text: 'Для оформления заказа нужен аккаунт — мы привязываем заказ к email и сохраняем историю.' },
        generic:     { icon: '🔒', title: 'Эта функция доступна с аккаунтом',
                       text: 'Регистрация занимает 30 секунд и не требует подтверждения email для большинства функций.' },
    };

    let _overlay = null;

    function ensureStyle() {
        if (document.getElementById('dolg-auth-modal-style')) return;
        const css = `
        .dolg-auth-modal-overlay {
            position: fixed; inset: 0;
            background: rgba(5, 8, 20, 0.78);
            backdrop-filter: blur(4px);
            z-index: 11500;
            display: flex; align-items: center; justify-content: center;
            animation: dolg-auth-fade-in 0.18s ease-out;
        }
        @keyframes dolg-auth-fade-in { from {opacity:0;} to {opacity:1;} }
        .dolg-auth-modal {
            background: linear-gradient(135deg, #1a2540, #0a0e27);
            border: 1px solid var(--accent-cyan, #00d4ff);
            border-radius: 10px;
            padding: 1.6rem 1.8rem;
            max-width: 440px;
            width: calc(100% - 32px);
            box-shadow: 0 16px 48px rgba(0, 0, 0, 0.5), 0 0 32px rgba(0, 212, 255, 0.18);
            color: #fff;
            text-align: center;
            position: relative;
        }
        .dolg-auth-modal__icon {
            font-size: 2.6rem;
            margin-bottom: 0.5rem;
            display: block;
        }
        .dolg-auth-modal__title {
            color: var(--accent-cyan, #00d4ff);
            font-size: 1.15rem;
            font-weight: 700;
            margin: 0 0 0.5rem;
        }
        .dolg-auth-modal__text {
            color: rgba(220, 240, 255, 0.85);
            font-size: 0.88rem;
            line-height: 1.5;
            margin: 0 0 1.2rem;
        }
        .dolg-auth-modal__actions {
            display: flex; gap: 0.6rem; justify-content: center;
            flex-wrap: wrap;
        }
        .dolg-auth-modal__btn {
            padding: 0.6rem 1.2rem;
            border-radius: 6px;
            font-weight: 700;
            font-size: 0.88rem;
            cursor: pointer;
            text-decoration: none;
            border: 1px solid transparent;
            display: inline-flex; align-items: center; gap: 0.35rem;
            transition: transform 0.1s, filter 0.15s;
        }
        .dolg-auth-modal__btn:hover { transform: translateY(-1px); filter: brightness(1.15); }
        .dolg-auth-modal__btn--primary {
            background: linear-gradient(135deg, var(--cosmic-blue, #2c7be5), var(--accent-cyan, #00d4ff));
            color: var(--cosmic-black, #0a0e27);
        }
        .dolg-auth-modal__btn--ghost {
            background: transparent; color: #fff;
            border-color: rgba(0, 212, 255, 0.4);
        }
        .dolg-auth-modal__close {
            position: absolute; top: 0.5rem; right: 0.7rem;
            background: transparent; border: none; color: rgba(255,255,255,0.55);
            font-size: 1.4rem; cursor: pointer; line-height: 1;
        }
        .dolg-auth-modal__close:hover { color: #fff; }
        `;
        const style = document.createElement('style');
        style.id = 'dolg-auth-modal-style';
        style.textContent = css;
        document.head.appendChild(style);
    }

    function show(reason) {
        ensureStyle();
        const r = REASONS[reason] || REASONS.generic;
        hide();
        const overlay = document.createElement('div');
        overlay.className = 'dolg-auth-modal-overlay';
        const next = encodeURIComponent(window.location.pathname + window.location.search);
        overlay.innerHTML = `
            <div class="dolg-auth-modal" role="dialog" aria-modal="true" aria-labelledby="dolgAuthTitle">
                <button type="button" class="dolg-auth-modal__close" aria-label="Закрыть">✕</button>
                <span class="dolg-auth-modal__icon">${r.icon}</span>
                <h3 id="dolgAuthTitle" class="dolg-auth-modal__title">${r.title}</h3>
                <p class="dolg-auth-modal__text">${r.text}</p>
                <div class="dolg-auth-modal__actions">
                    <!-- Принцип «одна точка входа»: только Войти.
                         На login-странице есть ссылка «📝 Регистрация →» в footer'е формы. -->
                    <a class="dolg-auth-modal__btn dolg-auth-modal__btn--primary" href="/accounts/login/?next=${next}">🔑 Войти</a>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        _overlay = overlay;
        const close = () => hide();
        overlay.querySelector('.dolg-auth-modal__close').addEventListener('click', close);
        overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
        document.addEventListener('keydown', escClose);
    }

    function escClose(e) { if (e.key === 'Escape') hide(); }

    function hide() {
        if (_overlay) { _overlay.remove(); _overlay = null; }
        document.removeEventListener('keydown', escClose);
    }

    // Capture-phase обработчик: перехватываем клик на любой [data-guest-locked]
    // до того, как сработает родной обработчик кнопки.
    function isGuest() {
        return document.body && document.body.dataset.userAuth !== '1';
    }
    document.addEventListener('click', function (e) {
        if (!isGuest()) return;
        const el = e.target.closest('[data-guest-locked]');
        if (!el) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        const reason = el.dataset.guestReason || el.id.replace(/Btn$/, '').toLowerCase() || 'generic';
        // Маппинг id → reason (если data-guest-reason не задан)
        let mapped = reason;
        if (/save/i.test(reason))    mapped = 'save';
        else if (/load/i.test(reason)) mapped = 'load';
        else if (/import/i.test(reason)) mapped = 'import';
        else if (/ai/i.test(reason)) mapped = 'ai';
        show(mapped);
    }, true);

    window.DolgAuthModal = { show, hide };
})(window, document);
