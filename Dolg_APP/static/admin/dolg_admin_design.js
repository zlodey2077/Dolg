(function () {
  function ready(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn, { once: true });
    } else {
      fn();
    }
  }

  ready(function () {
    const appList = document.querySelector('#content-main .app-list, #content-main');
    if (!appList || document.querySelector('.dolg-admin-model-filter')) return;

    const rows = Array.from(document.querySelectorAll('#content-main .model, #content-main tr.model-*'));
    if (!rows.length) return;

    const filter = document.createElement('label');
    filter.className = 'dolg-admin-model-filter';
    filter.innerHTML = '<span>Быстрый фильтр</span><input type="search" placeholder="Модель, приложение, таблица..." autocomplete="off">';
    appList.insertBefore(filter, appList.firstElementChild);

    const input = filter.querySelector('input');
    input.addEventListener('input', function () {
      const query = input.value.trim().toLowerCase();
      rows.forEach(function (row) {
        const matched = !query || row.textContent.toLowerCase().includes(query);
        row.classList.toggle('dolg-admin-muted-row', !matched);
      });
    });
  });
})();
