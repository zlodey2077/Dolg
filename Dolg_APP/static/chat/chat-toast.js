/* Минимальный toast-notifier для чата.
 * Заменил alert() на ненавязчивые тосты в правом нижнем углу.
 *
 * Использование:
 *   window.dolgToast('Сообщение');                  // info (синий)
 *   window.dolgToast('Ошибка', 'error');             // красный
 *   window.dolgToast('OK', 'success');               // зелёный
 *   window.dolgToast('Внимание', 'warning');         // жёлтый
 */
(function() {
    'use strict';
    let container = null;
    function getContainer() {
        if (container) return container;
        container = document.createElement('div');
        container.className = 'dolg-toast-container';
        document.body.appendChild(container);
        return container;
    }
    window.dolgToast = function(message, level) {
        const toast = document.createElement('div');
        toast.className = 'dolg-toast ' + (level || 'info');
        toast.textContent = message;
        getContainer().appendChild(toast);
        setTimeout(() => {
            toast.classList.add('fade-out');
            setTimeout(() => toast.remove(), 250);
        }, 4000);
    };
})();
