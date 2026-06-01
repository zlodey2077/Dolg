(function (window) {
    'use strict';

    function noop() {}

    function escapeXml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function downloadBlob(filename, blob, deps) {
        var documentRef = (deps && deps.document) || window.document;
        var urlFactory = (deps && deps.URL) || window.URL;
        var url = urlFactory.createObjectURL(blob);
        var anchor = documentRef.createElement('a');
        anchor.href = url;
        anchor.download = filename;
        documentRef.body.appendChild(anchor);
        anchor.click();
        documentRef.body.removeChild(anchor);
        urlFactory.revokeObjectURL(url);
    }

    function downloadTextFile(filename, text, type, deps) {
        var blob = new Blob([text], { type: type });
        downloadBlob(filename, blob, deps);
    }

    function buildSchemeSvg(options) {
        var opts = options || {};
        var components = Array.isArray(opts.components) ? opts.components : [];
        var connections = Array.isArray(opts.connections) ? opts.connections : [];
        if (components.length === 0) return '';

        var bounds = opts.bounds || {};
        var pad = bounds.PAD == null ? 50 : bounds.PAD;
        var minX = bounds.minX == null ? 0 : bounds.minX;
        var minY = bounds.minY == null ? 0 : bounds.minY;
        var width = bounds.width == null ? 100 : bounds.width;
        var height = bounds.height == null ? 100 : bounds.height;
        var componentWidth = opts.componentWidth || 60;
        var componentHeight = opts.componentHeight || 40;
        var getPortWorldPosition = typeof opts.getPortWorldPosition === 'function'
            ? opts.getPortWorldPosition
            : function () { return null; };
        var getComponentLabel = typeof opts.getComponentLabel === 'function'
            ? opts.getComponentLabel
            : function (type) { return type; };
        var getComponentName = typeof opts.getComponentName === 'function'
            ? opts.getComponentName
            : function (type) { return type; };
        var sx = function (x) { return x - minX + pad; };
        var sy = function (y) { return y - minY + pad; };
        var lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<svg xmlns="http://www.w3.org/2000/svg" width="' + width + '" height="' + height + '" viewBox="0 0 ' + width + ' ' + height + '">',
            '<rect width="100%" height="100%" fill="#ffffff"/>',
            '<g stroke="#111" fill="none" stroke-width="2" font-family="Arial, sans-serif" font-size="12">',
        ];

        connections.forEach(function (conn) {
            var fromComp = components.find(function (component) {
                return component.id === conn.from.compId;
            });
            var toComp = components.find(function (component) {
                return component.id === conn.to.compId;
            });
            if (!fromComp || !toComp) return;
            var fromPos = getPortWorldPosition(fromComp, conn.from.portId);
            var toPos = getPortWorldPosition(toComp, conn.to.portId);
            if (!fromPos || !toPos) return;
            var points = [fromPos].concat(conn.waypoints || []).concat([toPos]).map(function (point) {
                return sx(point.x) + ',' + sy(point.y);
            }).join(' ');
            lines.push('<polyline points="' + points + '" stroke="#222" fill="none"/>');
        });

        components.forEach(function (component) {
            var x = sx(component.x);
            var y = sy(component.y);
            var label = (component.label || getComponentLabel(component.type)) + component.id;
            lines.push('<rect x="' + x + '" y="' + y + '" width="' + componentWidth + '" height="' + componentHeight + '" rx="3" fill="#f8fbff" stroke="#111"/>');
            lines.push('<text x="' + (x + 6) + '" y="' + (y + 18) + '" fill="#111">' + escapeXml(label) + '</text>');
            lines.push('<text x="' + (x + 6) + '" y="' + (y + 36) + '" fill="#555">' + escapeXml(getComponentName(component.type)) + '</text>');
            if (component.catalog_ref) {
                lines.push('<text x="' + (x + 6) + '" y="' + (y + 54) + '" fill="#0066aa">' + escapeXml(component.catalog_ref) + '</text>');
            }
        });
        lines.push('</g></svg>');
        return lines.join('\n');
    }

    function exportSchemeSvg(options) {
        var opts = options || {};
        var components = Array.isArray(opts.components) ? opts.components : [];
        var notify = opts.notify || noop;
        if (components.length === 0) {
            notify('⚠️ Схема пуста', 'warning');
            return false;
        }
        var buildSvg = opts.buildSchemeSvg || function () { return buildSchemeSvg(opts); };
        var downloadText = opts.downloadTextFile || downloadTextFile;
        var now = opts.now || Date.now;
        downloadText('dolg_scheme_' + now() + '.svg', buildSvg(), 'image/svg+xml;charset=utf-8');
        notify('✓ Схема сохранена в SVG', 'success');
        return true;
    }

    async function exportSchemePdf(options) {
        var opts = options || {};
        var components = Array.isArray(opts.components) ? opts.components : [];
        var notify = opts.notify || noop;
        if (components.length === 0) {
            notify('⚠️ Схема пуста', 'warning');
            return false;
        }
        var fetchImpl = opts.fetch || window.fetch.bind(window);
        var getCsrfToken = opts.getCsrfToken || function () { return ''; };
        var buildSchemeData = opts.buildSchemeData || function () { return {}; };
        var now = opts.now || Date.now;
        var res = await fetchImpl(opts.exportPdfUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            credentials: 'same-origin',
            body: JSON.stringify({ scheme_data: buildSchemeData() }),
        });
        if (!res.ok) {
            notify('❌ Не удалось создать PDF', 'error');
            return false;
        }
        var blob = await res.blob();
        downloadBlob('dolg_scheme_' + now() + '.pdf', blob);
        notify('✓ Схема сохранена в PDF', 'success');
        return true;
    }

    window.DolgSchemeExport = {
        buildSchemeSvg: buildSchemeSvg,
        downloadBlob: downloadBlob,
        downloadTextFile: downloadTextFile,
        exportSchemePdf: exportSchemePdf,
        exportSchemeSvg: exportSchemeSvg,
    };
})(window);
