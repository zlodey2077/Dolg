/**
 * DOLG Comments widget — универсальный для проектов и статей.
 *
 * Использование:
 *   <div data-dolg-comments
 *        data-target-type="project|article"
 *        data-target-id="123"
 *        data-can-comment="1"  (есть ли auth)
 *        data-is-pro="1"       (Pro-юзер? — определяет Markdown vs plain)
 *   ></div>
 *
 * Подгружает /api/comments/?project=X или ?article=X, рендерит список,
 * показывает форму создания (если can-comment=1).
 */
(function (window, document) {
    'use strict';

    const MAX_LEN_FREE = 500;
    const MAX_LEN_PRO = 5000;

    function csrf() {
        const m = document.cookie.match(/csrftoken=([^;]+)/);
        return m ? m[1] : '';
    }

    function el(tag, attrs, ...children) {
        const e = document.createElement(tag);
        if (attrs) for (const k in attrs) {
            if (k === 'className') e.className = attrs[k];
            else if (k === 'innerHTML') e.innerHTML = attrs[k];
            else if (k.startsWith('on')) e.addEventListener(k.slice(2).toLowerCase(), attrs[k]);
            else e.setAttribute(k, attrs[k]);
        }
        for (const c of children) {
            if (c == null) continue;
            e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
        }
        return e;
    }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, c => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        })[c]);
    }

    function timeAgo(iso) {
        const d = new Date(iso); const now = new Date();
        const sec = Math.floor((now - d) / 1000);
        if (sec < 60) return 'только что';
        if (sec < 3600) return Math.floor(sec / 60) + ' мин назад';
        if (sec < 86400) return Math.floor(sec / 3600) + ' ч назад';
        return d.toLocaleDateString('ru-RU');
    }

    class CommentsWidget {
        constructor(container) {
            this.container = container;
            this.targetType = container.dataset.targetType;
            this.targetId = container.dataset.targetId;
            this.canComment = container.dataset.canComment === '1';
            this.isPro = container.dataset.isPro === '1';
            this.maxLen = this.isPro ? MAX_LEN_PRO : MAX_LEN_FREE;
            this.init();
        }

        async init() {
            this.render();
            await this.refresh();
        }

        render() {
            this.container.innerHTML = '';
            const root = el('div', { className: 'dolg-comments' },
                el('div', { className: 'dolg-comments-header' },
                    el('h3', null, '💬 Комментарии'),
                    el('span', { className: 'dolg-comments-count', id: 'dolgCmntCount' }, '...'),
                ),
                el('div', { className: 'dolg-comments-list', id: 'dolgCmntList' },
                    el('div', { className: 'dolg-comments-empty' }, 'Загрузка...'),
                ),
            );

            if (this.canComment) {
                const tierBadge = this.isPro
                    ? el('span', { className: 'dolg-cmnt-tier dolg-cmnt-tier--pro' }, '💎 Pro — Markdown + код')
                    : el('span', { className: 'dolg-cmnt-tier' }, 'Free — plain-text. ',
                        el('a', { href: '/billing/' }, 'Активировать Pro'),
                        ' для Markdown.');
                const form = el('form', { className: 'dolg-cmnt-form', onSubmit: e => this.onSubmit(e) },
                    tierBadge,
                    el('textarea', {
                        id: 'dolgCmntInput',
                        placeholder: this.isPro
                            ? '**bold** _italic_  `code`  ```python\nprint("hi")\n```'
                            : 'Ваш комментарий…',
                        rows: '3',
                        maxlength: String(this.maxLen),
                    }),
                    el('div', { className: 'dolg-cmnt-form-actions' },
                        el('span', { className: 'dolg-cmnt-counter', id: 'dolgCmntCounter' }, `0 / ${this.maxLen}`),
                        el('button', { type: 'submit', className: 'btn btn-primary btn-small' }, 'Отправить'),
                    ),
                );
                root.appendChild(form);

                // Live char counter
                const input = form.querySelector('#dolgCmntInput');
                input.addEventListener('input', () => {
                    form.querySelector('#dolgCmntCounter').textContent = `${input.value.length} / ${this.maxLen}`;
                });
            } else {
                root.appendChild(el('div', { className: 'dolg-cmnt-login-cta' },
                    el('a', { href: '/accounts/login/?next=' + encodeURIComponent(location.pathname) },
                        '🔑 Войдите чтобы оставить комментарий'),
                ));
            }
            this.container.appendChild(root);
        }

        async refresh() {
            const q = this.targetType === 'project'
                ? `?project=${this.targetId}`
                : `?article=${this.targetId}`;
            try {
                const r = await fetch('/api/comments/' + q, { credentials: 'same-origin' });
                const data = await r.json();
                this.renderList(data.comments || []);
            } catch (e) {
                this.container.querySelector('#dolgCmntList').innerHTML =
                    '<div class="dolg-comments-empty">Не удалось загрузить.</div>';
            }
        }

        renderList(comments) {
            const list = this.container.querySelector('#dolgCmntList');
            const count = this.container.querySelector('#dolgCmntCount');
            count.textContent = comments.length;
            if (comments.length === 0) {
                list.innerHTML = '<div class="dolg-comments-empty">Пока нет комментариев. Будьте первым!</div>';
                return;
            }
            list.innerHTML = comments.map(c => `
                <div class="dolg-cmnt dolg-cmnt-${c.is_rich ? 'rich' : 'plain'}" data-id="${c.id}">
                    <div class="dolg-cmnt-meta">
                        ${c.user.avatar_url
                            ? `<img class="dolg-cmnt-avatar" src="${escapeHtml(c.user.avatar_url)}" alt="">`
                            : '<span class="dolg-cmnt-avatar dolg-cmnt-avatar--placeholder">' + escapeHtml(c.user.username[0].toUpperCase()) + '</span>'
                        }
                        <strong>${escapeHtml(c.user.username)}</strong>
                        ${c.user.is_pro ? '<span class="dolg-cmnt-pro-badge">💎 Pro</span>' : ''}
                        <span class="dolg-cmnt-time">${timeAgo(c.created_at)}</span>
                    </div>
                    <div class="dolg-cmnt-body">${c.body_html}</div>
                </div>
            `).join('');
        }

        async onSubmit(e) {
            e.preventDefault();
            const input = this.container.querySelector('#dolgCmntInput');
            const body = (input.value || '').trim();
            if (!body) return;
            const payload = { body };
            if (this.targetType === 'project') payload.project = this.targetId;
            else payload.article = this.targetId;
            try {
                const r = await fetch('/api/comments/create/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
                    credentials: 'same-origin',
                    body: JSON.stringify(payload),
                });
                const data = await r.json();
                if (!data.ok) {
                    alert('Ошибка: ' + (data.message || data.error));
                    return;
                }
                input.value = '';
                this.container.querySelector('#dolgCmntCounter').textContent = `0 / ${this.maxLen}`;
                await this.refresh();
            } catch (err) {
                alert('Network error: ' + err.message);
            }
        }
    }

    function init() {
        document.querySelectorAll('[data-dolg-comments]').forEach(c => new CommentsWidget(c));
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else { init(); }

    window.DolgComments = { CommentsWidget };
})(window, document);
