(function (window) {
    'use strict';

    function asObject(value) {
        return value && typeof value === 'object' ? value : {};
    }

    function asNumber(value, fallback) {
        var parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : fallback;
    }

    function normalizeRotation(value) {
        var parsed = parseInt(value, 10) || 0;
        return ((parsed % 360) + 360) % 360;
    }

    function getPorts(type, deps) {
        if (typeof deps.getComponentPorts === 'function') {
            return deps.getComponentPorts(type) || [];
        }
        return [];
    }

    function getLabel(type, deps) {
        if (typeof deps.getComponentLabel === 'function') {
            return deps.getComponentLabel(type);
        }
        return type;
    }

    function normalizePortId(component, portId) {
        var raw = String(portId == null ? '' : portId);
        if (component.type === 'battery') {
            if (['positive', 'plus', 'pos'].includes(raw)) return '+';
            if (['negative', 'minus', 'neg'].includes(raw)) return '-';
        }
        if (component.type === 'ground' && ['gnd', 'ground', '0'].includes(raw)) {
            return 'a';
        }
        return raw;
    }

    function normalizeComponent(raw, index, deps) {
        var source = asObject(raw);
        var type = source.type || 'resistor';
        var ports = Array.isArray(source.ports) && source.ports.length
            ? source.ports
            : getPorts(type, deps);
        return Object.assign({}, source, {
            id: source.id == null ? index : source.id,
            type: type,
            x: asNumber(source.x, 0),
            y: asNumber(source.y, 0),
            rotation: normalizeRotation(source.rotation),
            resistance: source.resistance == null ? 1000 : source.resistance,
            capacitance: source.capacitance == null ? 1 : source.capacitance,
            inductance: source.inductance == null ? 1 : source.inductance,
            voltage: source.voltage == null ? 5 : source.voltage,
            label: source.label || getLabel(type, deps),
            ports: ports,
        });
    }

    function normalizeSchemeData(schemeData, deps) {
        var dependencies = deps || {};
        var source = asObject(schemeData);
        var rawComponents = Array.isArray(source.components) ? source.components : [];
        var normalizedComponents = rawComponents.map(function (raw, index) {
            return normalizeComponent(raw, index, dependencies);
        });

        var componentById = new Map(normalizedComponents.map(function (component) {
            return [component.id, component];
        }));
        var validIds = new Set(componentById.keys());

        function normalizeEndpoint(endpoint) {
            var component = componentById.get(endpoint.compId);
            return {
                compId: endpoint.compId,
                portId: component
                    ? normalizePortId(component, endpoint.portId)
                    : String(endpoint.portId == null ? '' : endpoint.portId),
            };
        }

        function hasKnownPort(endpoint) {
            var component = componentById.get(endpoint.compId);
            var ports = component && Array.isArray(component.ports) ? component.ports : [];
            return ports.some(function (port) {
                return port.id === endpoint.portId;
            });
        }

        var rawConnections = Array.isArray(source.connections) ? source.connections : [];
        var normalizedConnections = rawConnections
            .filter(function (wire) {
                return wire && wire.from && wire.to;
            })
            .filter(function (wire) {
                return validIds.has(wire.from.compId) && validIds.has(wire.to.compId);
            })
            .map(function (wire) {
                var from = normalizeEndpoint(wire.from);
                var to = normalizeEndpoint(wire.to);
                return {
                    id: wire.id == null ? null : wire.id,
                    from: from,
                    to: to,
                    waypoints: Array.isArray(wire.waypoints) ? wire.waypoints : [],
                };
            })
            .filter(function (wire) {
                return hasKnownPort(wire.from) && hasKnownPort(wire.to);
            });

        return Object.assign({}, source, {
            version: source.version || 2,
            components: normalizedComponents,
            connections: normalizedConnections,
            timestamp: source.timestamp || new Date().toISOString(),
        });
    }

    window.DolgSchemeNormalizer = {
        normalizePortId: normalizePortId,
        normalizeSchemeData: normalizeSchemeData,
    };
})(window);
