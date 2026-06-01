(function (window) {
    'use strict';

    function noop() {}

    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function money(value) {
        return Number(value || 0).toFixed(2);
    }

    function calculateGrandTotal(matches) {
        return (matches || []).reduce(function (sum, match) {
            return sum + (match.product ? Number(match.line_total || 0) : 0);
        }, 0);
    }

    function renderBomHtml(data) {
        var matches = data && Array.isArray(data.matches) ? data.matches : [];
        if (matches.length === 0) {
            return {
                bodyHtml: '<p class="picker-empty">Нет компонентов для анализа</p>',
                showFooter: false,
                grandTotal: 0,
            };
        }

        var rows = matches.map(function (match, index) {
            var label = escapeHtml(match.label);
            var warnings = (match.warnings || []).map(function (warning) {
                return '<div class="bom-warning">⚠ ' + escapeHtml(warning) + '</div>';
            }).join('');

            if (!match.product) {
                return [
                    '<tr>',
                    '<td>' + label + warnings + '</td>',
                    '<td class="bom-qty">' + match.count + '</td>',
                    '<td colspan="3"><span class="bom-missing">нет в каталоге</span></td>',
                    '</tr>',
                ].join('');
            }

            var options = (match.alternatives || []).map(function (alt) {
                return [
                    '<option value="' + escapeHtml(alt.slug) + '" data-price="' + escapeHtml(alt.price) + '"',
                    alt.slug === match.product.slug ? ' selected' : '',
                    '>',
                    escapeHtml(alt.part_number || alt.name) + ' — ' + alt.price + ' ₽',
                    '</option>',
                ].join('');
            }).join('');

            return [
                '<tr data-idx="' + index + '">',
                '<td>' + label + warnings + '</td>',
                '<td class="bom-qty">' + match.count + '</td>',
                '<td>',
                '<select class="bom-select" onchange="onBomAltChange(' + index + ', this)">',
                options,
                '</select>',
                '<div class="bom-part">' + escapeHtml(match.product.manufacturer) + '</div>',
                '</td>',
                '<td class="bom-price" data-unit-price="' + match.product.price + '">' + money(match.product.price) + ' ₽</td>',
                '<td class="bom-total">' + money(match.line_total) + ' ₽</td>',
                '</tr>',
            ].join('');
        }).join('');

        return {
            bodyHtml: [
                '<p style="color:#888; font-size:0.85rem; margin-bottom:10px;">',
                'Всего компонентов: <strong style="color:#fff;">' + (data.total_components || 0) + '</strong>',
                '</p>',
                '<table class="bom-table">',
                '<thead>',
                '<tr>',
                '<th>Тип</th>',
                '<th style="text-align:center;">Кол-во</th>',
                '<th>Товар в каталоге</th>',
                '<th style="text-align:right;">Цена</th>',
                '<th style="text-align:right;">Сумма</th>',
                '</tr>',
                '</thead>',
                '<tbody>' + rows + '</tbody>',
                '</table>',
            ].join(''),
            showFooter: true,
            grandTotal: calculateGrandTotal(matches),
        };
    }

    function applyAlternative(matches, index, selectedSlug) {
        var entry = matches && matches[index];
        if (!entry) return null;
        var alt = (entry.alternatives || []).find(function (candidate) {
            return candidate.slug === selectedSlug;
        });
        if (!alt) return null;
        entry.product = alt;
        entry.line_total = +(Number(alt.price || 0) * Number(entry.count || 0)).toFixed(2);
        return entry;
    }

    function escapeCsv(value) {
        var text = value == null ? '' : String(value);
        return /[",\n;]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
    }

    function buildBomCsv(matches) {
        var header = ['Тип', 'Кол-во', 'Производитель', 'Part Number', 'Название', 'Цена за шт', 'Сумма'];
        var rows = (matches || []).map(function (match) {
            if (!match.product) return [match.label, match.count, '', '', 'нет в каталоге', '', '0'];
            return [
                match.label,
                match.count,
                match.product.manufacturer || '',
                match.product.part_number || '',
                match.product.name || '',
                money(match.product.price),
                money(match.line_total),
            ];
        });
        rows.push(['', '', '', '', 'ИТОГО', '', money(calculateGrandTotal(matches))]);
        return '\ufeff' + [header].concat(rows).map(function (row) {
            return row.map(escapeCsv).join(';');
        }).join('\r\n');
    }

    function buildCartItems(matches) {
        return (matches || [])
            .filter(function (match) { return match.product; })
            .map(function (match) {
                return { slug: match.product.slug, quantity: match.count };
            });
    }

    function downloadBomCsv(options) {
        var opts = options || {};
        var matches = Array.isArray(opts.matches) ? opts.matches : [];
        var notify = opts.notify || noop;
        if (!matches.length) {
            notify('⚠️ BOM пуст', 'warning');
            return false;
        }
        var downloadTextFile = opts.downloadTextFile || (window.DolgSchemeExport && window.DolgSchemeExport.downloadTextFile);
        if (typeof downloadTextFile !== 'function') {
            throw new Error('downloadTextFile is not available');
        }
        var today = opts.today || new Date().toISOString().slice(0, 10);
        downloadTextFile('BOM_' + today + '.csv', buildBomCsv(matches), 'text/csv;charset=utf-8');
        notify('✓ BOM сохранён в CSV', 'success');
        return true;
    }

    async function downloadBomXlsx(options) {
        var opts = options || {};
        var components = Array.isArray(opts.components) ? opts.components : [];
        var notify = opts.notify || noop;
        if (components.length === 0) {
            notify('⚠️ Схема пуста', 'warning');
            return false;
        }
        var fetchImpl = opts.fetch || window.fetch.bind(window);
        var getCsrfToken = opts.getCsrfToken || function () { return ''; };
        var downloadBlob = opts.downloadBlob || (window.DolgSchemeExport && window.DolgSchemeExport.downloadBlob);
        if (typeof downloadBlob !== 'function') {
            throw new Error('downloadBlob is not available');
        }
        var res = await fetchImpl(opts.exportXlsxUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            credentials: 'same-origin',
            body: JSON.stringify({ components: components }),
        });
        if (!res.ok) {
            var data = await res.json().catch(function () { return {}; });
            throw new Error(data.error || 'HTTP ' + res.status);
        }
        var blob = await res.blob();
        var today = opts.today || new Date().toISOString().slice(0, 10);
        downloadBlob('BOM_' + today + '.xlsx', blob);
        notify('✓ BOM сохранён в XLSX', 'success');
        return true;
    }

    async function addAllToCart(options) {
        var opts = options || {};
        var matches = Array.isArray(opts.matches) ? opts.matches : [];
        var notify = opts.notify || noop;
        var items = buildCartItems(matches);
        if (items.length === 0) {
            notify('⚠️ Нечего добавлять', 'warning');
            return { ok: false, items: [] };
        }
        var apiFetch = opts.apiFetch;
        if (typeof apiFetch !== 'function') {
            throw new Error('apiFetch is not available');
        }
        var payload = { items: items };
        if (opts.projectContext) {
            payload.project = opts.projectContext;
            payload.source = opts.source || 'simulation';
        }
        var data = await apiFetch(opts.addAllUrl, {
            method: 'POST',
            body: JSON.stringify(payload),
        });
        return { ok: true, data: data, items: items };
    }

    window.DolgSchemeBom = {
        applyAlternative: applyAlternative,
        buildBomCsv: buildBomCsv,
        buildCartItems: buildCartItems,
        calculateGrandTotal: calculateGrandTotal,
        downloadBomCsv: downloadBomCsv,
        downloadBomXlsx: downloadBomXlsx,
        addAllToCart: addAllToCart,
        renderBomHtml: renderBomHtml,
    };
})(window);
