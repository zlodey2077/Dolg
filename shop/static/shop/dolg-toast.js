/* Единая тост-система DOLG (window.DolgToast) — общий фидбек на весь продукт.
 *
 * Заменяет зоопарк: нативные alert(), Django .alert-блоки, sim-showNotification, chat-toast.
 * Грузится в shop/base.html (58 шаблонов) и Dolg_APP/base.html → доступен везде.
 *
 * API:
 *   DolgToast.show(message, type='info', opts)  // type: info|success|warning|error
 *   DolgToast.success(msg, opts) / .error / .warning / .info
 *   DolgToast.fromDjangoMessages()              // мост: .messages-container .alert → тосты
 *
 * opts: { duration (мс), dismissible (bool) }. Уважает prefers-reduced-motion + aria-live.
 */
(function () {
  'use strict';

  var REDUCED = false;
  try {
    REDUCED = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch (e) {}

  var TYPES = { info: 'ℹ', success: '✓', warning: '⚠', error: '✕' };

  function ensureStyle() {
    if (document.getElementById('dolg-toast-style')) return;
    var s = document.createElement('style');
    s.id = 'dolg-toast-style';
    s.textContent =
      '#dolg-toast-container{position:fixed;top:76px;right:18px;z-index:99999;display:flex;' +
      'flex-direction:column;gap:10px;max-width:380px;pointer-events:none}' +
      '.dolg-toast{pointer-events:auto;display:flex;align-items:flex-start;gap:9px;padding:12px 16px;' +
      'border-radius:10px;color:#06121d;font-weight:600;font-size:13px;line-height:1.35;' +
      'box-shadow:0 8px 26px rgba(0,0,0,.45);cursor:pointer;position:relative;overflow:hidden;' +
      'border-left:4px solid rgba(0,0,0,.22);animation:dolgToastIn .32s cubic-bezier(.2,.9,.3,1)}' +
      '.dolg-toast.closing{animation:dolgToastOut .26s ease forwards}' +
      '.dolg-toast .dt-ic{font-size:15px;line-height:1.25;flex-shrink:0}' +
      '.dolg-toast .dt-bar{position:absolute;left:0;bottom:0;height:3px;width:100%;' +
      'background:rgba(0,0,0,.30);transform-origin:left;animation:dolgToastBar linear forwards}' +
      '.dolg-toast.info{background:linear-gradient(135deg,#34d8ff,#16b2e6)}' +
      '.dolg-toast.success{background:linear-gradient(135deg,#46e08a,#1fbf67)}' +
      '.dolg-toast.warning{background:linear-gradient(135deg,#ffd24a,#f3b015)}' +
      '.dolg-toast.error{background:linear-gradient(135deg,#ff6a6a,#e93636);color:#fff}' +
      '@keyframes dolgToastIn{from{opacity:0;transform:translateX(42px) scale(.95)}to{opacity:1;transform:none}}' +
      '@keyframes dolgToastOut{to{opacity:0;transform:translateX(42px) scale(.95);margin-top:-10px;max-height:0;padding-top:0;padding-bottom:0}}' +
      '@keyframes dolgToastBar{from{transform:scaleX(1)}to{transform:scaleX(0)}}' +
      '@media (prefers-reduced-motion: reduce){.dolg-toast,.dolg-toast.closing{animation:none!important}' +
      '.dolg-toast .dt-bar{animation:none!important;display:none}}';
    document.head.appendChild(s);
  }

  function container() {
    var c = document.getElementById('dolg-toast-container');
    if (!c) {
      ensureStyle();
      c = document.createElement('div');
      c.id = 'dolg-toast-container';
      c.setAttribute('role', 'status');
      c.setAttribute('aria-live', 'polite');
      c.setAttribute('aria-atomic', 'false');
      document.body.appendChild(c);
    }
    return c;
  }

  function show(message, type, opts) {
    if (!message) return null;
    opts = opts || {};
    var kind = TYPES[type] ? type : 'info';
    var dur = opts.duration != null ? opts.duration : kind === 'error' ? 5000 : 3200;
    var c = container();

    var t = document.createElement('div');
    t.className = 'dolg-toast ' + kind;
    var lead = String(message).trim().codePointAt(0) || 0;
    var hasGlyph = lead > 0x2100; // уже есть emoji/символ в начале — не дублируем иконку
    t.innerHTML =
      (hasGlyph ? '' : '<span class="dt-ic">' + TYPES[kind] + '</span>') +
      '<span class="dt-msg"></span>' +
      (REDUCED || dur <= 0 ? '' : '<span class="dt-bar" style="animation-duration:' + dur + 'ms"></span>');
    t.querySelector('.dt-msg').textContent = message;

    var closed = false;
    function close() {
      if (closed) return;
      closed = true;
      if (REDUCED) {
        t.remove();
      } else {
        t.classList.add('closing');
        setTimeout(function () { t.remove(); }, 270);
      }
    }
    if (opts.dismissible !== false) t.addEventListener('click', close);

    c.appendChild(t);
    while (c.children.length > 6) c.firstChild.remove();
    if (dur > 0) setTimeout(close, dur);
    return t;
  }

  function djangoType(tags) {
    tags = (tags || '').toLowerCase();
    if (tags.indexOf('error') >= 0 || tags.indexOf('danger') >= 0) return 'error';
    if (tags.indexOf('success') >= 0) return 'success';
    if (tags.indexOf('warning') >= 0) return 'warning';
    return 'info';
  }

  // Мост: серверные Django messages (.messages-container .alert) → тосты, контейнер убираем.
  function fromDjangoMessages() {
    var box = document.querySelector('.messages-container');
    if (!box) return;
    var alerts = box.querySelectorAll('.alert, [data-msg]');
    alerts.forEach(function (el) {
      var tags = el.getAttribute('data-tags') || el.className || '';
      show(el.textContent.trim(), djangoType(tags), { duration: 6000 });
    });
    box.remove();
  }

  window.DolgToast = {
    show: show,
    success: function (m, o) { return show(m, 'success', o); },
    error: function (m, o) { return show(m, 'error', o); },
    warning: function (m, o) { return show(m, 'warning', o); },
    info: function (m, o) { return show(m, 'info', o); },
    fromDjangoMessages: fromDjangoMessages,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', fromDjangoMessages);
  } else {
    fromDjangoMessages();
  }
})();
