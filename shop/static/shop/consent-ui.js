/**
 * DOLG Cookie Consent — granular (necessary / analytics / marketing).
 *
 * Логика:
 * 1) При загрузке: если в localStorage нет 'dolg_cookie_consent' → показать banner.
 * 2) При accept: записать выбор + cookie 1 год + скрыть banner.
 * 3) Категория necessary — всегда true, disabled чекбокс.
 * 4) Аналитика / маркетинг — opt-in (по умолчанию выключены).
 * 5) Открыть настройки повторно — клик по «Настройки cookies» в футере.
 *
 * Никаких внешних трекеров до accept. После — checkConsent('analytics')
 * вернёт true/false для условной загрузки скриптов.
 */
(function (window, document) {
    'use strict';

    const STORAGE_KEY = 'dolg_cookie_consent';
    const COOKIE_NAME = 'dolg_cookie_consent';
    const TTL_DAYS = 365;

    const DEFAULTS = { necessary: true, analytics: false, marketing: false, version: 1 };

    function readConsent() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return null;
            const parsed = JSON.parse(raw);
            if (!parsed || typeof parsed !== 'object') return null;
            return Object.assign({}, DEFAULTS, parsed);
        } catch (e) { return null; }
    }

    function writeConsent(consent) {
        const data = Object.assign({}, DEFAULTS, consent, { necessary: true });
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
        } catch (e) { /* localStorage disabled — fallback на cookie */ }
        // Дублируем в cookie (на 1 год) — чтобы сервер тоже видел consent.
        const expires = new Date(Date.now() + TTL_DAYS * 86400 * 1000).toUTCString();
        document.cookie = COOKIE_NAME + '=' + encodeURIComponent(JSON.stringify(data)) +
                          '; expires=' + expires + '; path=/; SameSite=Lax';
        return data;
    }

    function buildBanner() {
        const wrap = document.createElement('div');
        wrap.className = 'dolg-cookie-banner';
        wrap.setAttribute('role', 'dialog');
        wrap.setAttribute('aria-label', 'Согласие на использование cookies');
        wrap.innerHTML = `
            <div class="dolg-cookie-banner__body">
                <div class="dolg-cookie-banner__text">
                    <strong>🍪 Мы используем cookies</strong>
                    <p>Необходимые cookies нужны для работы сайта (сессия, корзина).
                       Аналитика помогает улучшить продукт. Выберите, что разрешить —
                       без вашего согласия аналитика не загружается.
                       <a href="/cookies/" class="dolg-cookie-banner__link">Подробнее</a></p>
                </div>
                <div class="dolg-cookie-banner__options">
                    <label title="Без них сайт не работает (сессия, корзина, CSRF). Отключить нельзя.">
                        <input type="checkbox" checked disabled> Необходимые
                    </label>
                    <label title="Анонимные метрики использования. Без них работает, но не помогает нам улучшать сервис.">
                        <input type="checkbox" id="dolgCookieAnalytics"> Аналитика
                    </label>
                    <label title="Сейчас не используется — резерв на будущее. Будет выкл. по умолчанию.">
                        <input type="checkbox" id="dolgCookieMarketing"> Маркетинг
                    </label>
                </div>
                <div class="dolg-cookie-banner__actions">
                    <button type="button" class="dolg-cookie-banner__btn dolg-cookie-banner__btn--ghost" id="dolgCookieRejectAll">
                        Только необходимые
                    </button>
                    <button type="button" class="dolg-cookie-banner__btn dolg-cookie-banner__btn--ghost" id="dolgCookieSave">
                        Сохранить выбор
                    </button>
                    <button type="button" class="dolg-cookie-banner__btn dolg-cookie-banner__btn--primary" id="dolgCookieAcceptAll">
                        Принять всё
                    </button>
                </div>
            </div>
        `;
        return wrap;
    }

    function showBanner(force) {
        if (!force && readConsent()) return;     // уже сохранено
        const existing = document.querySelector('.dolg-cookie-banner');
        if (existing) existing.remove();

        const banner = buildBanner();
        document.body.appendChild(banner);

        // Восстановим текущий выбор (если переоткрыли)
        const current = readConsent() || DEFAULTS;
        banner.querySelector('#dolgCookieAnalytics').checked = !!current.analytics;
        banner.querySelector('#dolgCookieMarketing').checked = !!current.marketing;

        const close = () => banner.remove();

        banner.querySelector('#dolgCookieAcceptAll').addEventListener('click', () => {
            writeConsent({ analytics: true, marketing: true });
            close();
            window.dispatchEvent(new CustomEvent('dolg:consent-changed'));
        });
        banner.querySelector('#dolgCookieRejectAll').addEventListener('click', () => {
            writeConsent({ analytics: false, marketing: false });
            close();
            window.dispatchEvent(new CustomEvent('dolg:consent-changed'));
        });
        banner.querySelector('#dolgCookieSave').addEventListener('click', () => {
            writeConsent({
                analytics: banner.querySelector('#dolgCookieAnalytics').checked,
                marketing: banner.querySelector('#dolgCookieMarketing').checked,
            });
            close();
            window.dispatchEvent(new CustomEvent('dolg:consent-changed'));
        });
    }

    // Публичное API — для других скриптов: «можно ли мне грузиться?»
    window.DolgConsent = {
        get: readConsent,
        has: function (category) {
            const c = readConsent();
            return !!(c && c[category]);
        },
        openSettings: function () { showBanner(true); },
    };

    // Авто-показ на DOMContentLoaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => showBanner(false));
    } else {
        showBanner(false);
    }
})(window, document);
