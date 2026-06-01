(function (window) {
    'use strict';

    function portKey(componentId, portId) {
        return String(componentId) + ':' + String(portId);
    }

    // ВНИМАНИЕ: union-find ниже продублирован в frontend/src/union-find.ts.
    // Меняешь логику здесь — синхронизируй с TS-версией (или ускорь миграцию).
    function createUnionFind() {
        var parent = new Map();

        function find(key) {
            if (!parent.has(key)) parent.set(key, key);
            while (parent.get(key) !== key) {
                parent.set(key, parent.get(parent.get(key)));
                key = parent.get(key);
            }
            return key;
        }

        function union(left, right) {
            var leftRoot = find(left);
            var rightRoot = find(right);
            if (leftRoot !== rightRoot) parent.set(leftRoot, rightRoot);
        }

        return {
            find: find,
            union: union,
            parent: parent,
        };
    }

    function registerComponentPorts(components, getComponentPorts, find) {
        (components || []).forEach(function (component) {
            (getComponentPorts(component.type) || []).forEach(function (port) {
                find(portKey(component.id, port.id));
            });
        });
    }

    function connectPorts(connections, union) {
        var usedPorts = new Set();
        // §3.1: net_label равные имена → объединяем эти net'ы в один
        // (KiCad/Eagle паттерн: VCC-провод в одном углу = VCC-провод в другом).
        // Делается ДО обычной union-связи чтобы label-объединение тоже учитывалось.
        var labelLeader = {};   // net_label → первый порт-якорь
        (connections || []).forEach(function (connection) {
            var left = portKey(connection.from.compId, connection.from.portId);
            var right = portKey(connection.to.compId, connection.to.portId);
            union(left, right);
            usedPorts.add(left);
            usedPorts.add(right);
            // Label-based объединение: все net'ы с одинаковым net_label склеиваем
            if (connection.net_label) {
                var lbl = String(connection.net_label).toUpperCase();
                if (labelLeader[lbl]) {
                    union(labelLeader[lbl], left);
                } else {
                    labelLeader[lbl] = left;
                }
            }
        });
        return usedPorts;
    }

    function findGroundRoots(components, find) {
        var roots = new Set();
        (components || []).filter(function (component) {
            return component.type === 'ground';
        }).forEach(function (ground) {
            roots.add(find(portKey(ground.id, 'a')));
        });
        return roots;
    }

    function addFirstAvailableGroundRoot(components, getComponentPorts, find, groundRoots) {
        // Приоритеты выбора неявной земли (когда компонента 'ground' нет):
        //   1) минусовой порт первой батареи — это естественная reference-точка
        //   2) эмиттер первого транзистора — типовая GND для усилителя
        //   3) любой первый порт первого компонента — крайний fallback
        // Без приоритетов земля могла случайно «прилипать» к плюсу батареи,
        // и все напряжения переворачивались относительно ожиданий пользователя.
        var comps = components || [];
        for (var i = 0; i < comps.length; i += 1) {
            if (comps[i].type === 'battery') {
                groundRoots.add(find(portKey(comps[i].id, '-')));
                return true;
            }
        }
        for (var j = 0; j < comps.length; j += 1) {
            if (comps[j].type === 'npn' || comps[j].type === 'pnp') {
                groundRoots.add(find(portKey(comps[j].id, 'e')));
                return true;
            }
        }
        for (var k = 0; k < comps.length; k += 1) {
            var ports = getComponentPorts(comps[k].type) || [];
            if (ports.length > 0) {
                groundRoots.add(find(portKey(comps[k].id, ports[0].id)));
                return true;
            }
        }
        return false;
    }

    function createNodeResolver(groundRoots, find) {
        var rootToNode = new Map();
        (groundRoots || new Set()).forEach(function (root) {
            rootToNode.set(root, 0);
        });
        var nextNodeId = 1;

        function getNode(componentId, portId) {
            var root = find(portKey(componentId, portId));
            if (!rootToNode.has(root)) {
                rootToNode.set(root, nextNodeId);
                nextNodeId += 1;
            }
            return rootToNode.get(root);
        }

        function getNextNodeId() {
            return nextNodeId;
        }

        return {
            getNode: getNode,
            getNextNodeId: getNextNodeId,
            rootToNode: rootToNode,
        };
    }

    function formatSpiceNumber(value) {
        var number = Number(value);
        if (!Number.isFinite(number)) return '0';
        if (number === 0) return '0';
        var abs = Math.abs(number);
        if (abs >= 1e-3 && abs < 1e6) return String(number);
        return number.toExponential(4);
    }

    function positiveParsedValue(parseEngValue, field, raw, fallback, scale) {
        var parser = typeof parseEngValue === 'function' ? parseEngValue : function (_, value) {
            return Number(value);
        };
        var value = parser(field, raw);
        var normalized = (isFinite(value) && value > 0) ? value : fallback;
        return normalized * (scale || 1);
    }

    function buildElementNetlist(options) {
        var opts = options || {};
        var components = opts.components || [];
        var getNode = opts.getNode;
        var parseEngValue = opts.parseEngValue;
        var fmt = opts.formatSpiceNumber || formatSpiceNumber;
        var lines = [];
        var errors = [];
        var circuitElements = [];
        var modelFlags = {
            needDiodeModel: false,
            needLedModel: false,
            needNpnModel: false,
            needPnpModel: false,
        };

        if (typeof getNode !== 'function') {
            return {
                lines: lines,
                errors: ['Резолвер узлов нетлиста не настроен.'],
                circuitElements: circuitElements,
                modelFlags: modelFlags,
            };
        }

        components.forEach(function (component) {
            var nA = function () { return getNode(component.id, 'a'); };
            var nB = function () { return getNode(component.id, 'b'); };

            switch (component.type) {
                case 'resistor': {
                    var resistorValue = positiveParsedValue(parseEngValue, 'resistance', component.resistance, 1000, 1);
                    lines.push('R' + component.id + ' ' + nA() + ' ' + nB() + ' ' + fmt(resistorValue));
                    circuitElements.push({ id: component.id, type: 'R', nodes: [nA(), nB()], value: resistorValue, label: 'R' + component.id });
                    break;
                }
                case 'capacitor': {
                    var capacitorValue = positiveParsedValue(parseEngValue, 'capacitance', component.capacitance, 1, 1e-6);
                    lines.push('C' + component.id + ' ' + nA() + ' ' + nB() + ' ' + fmt(capacitorValue));
                    circuitElements.push({ id: component.id, type: 'C', nodes: [nA(), nB()], value: capacitorValue, label: 'C' + component.id });
                    break;
                }
                case 'inductor': {
                    var inductorValue = positiveParsedValue(parseEngValue, 'inductance', component.inductance, 1, 1e-3);
                    lines.push('L' + component.id + ' ' + nA() + ' ' + nB() + ' ' + fmt(inductorValue));
                    circuitElements.push({ id: component.id, type: 'L', nodes: [nA(), nB()], value: inductorValue, label: 'L' + component.id });
                    break;
                }
                case 'diode': {
                    lines.push('D' + component.id + ' ' + nA() + ' ' + nB() + ' DMOD');
                    modelFlags.needDiodeModel = true;
                    circuitElements.push({ id: component.id, type: 'D', nodes: [nA(), nB()], value: 0.7, label: 'D' + component.id });
                    break;
                }
                case 'led': {
                    lines.push('D' + component.id + ' ' + nA() + ' ' + nB() + ' LEDMOD');
                    modelFlags.needLedModel = true;
                    circuitElements.push({ id: component.id, type: 'D', nodes: [nA(), nB()], value: 2.0, label: 'LED' + component.id });
                    break;
                }
                case 'battery': {
                    var parser = typeof parseEngValue === 'function' ? parseEngValue : function (_, value) {
                        return Number(value);
                    };
                    var voltage = parser('voltage', component.voltage);
                    var voltageValue = isFinite(voltage) ? voltage : 5;
                    // Если на источник применили виртуальный генератор сигналов
                    // (DolgLab → applyToBattery), вместо DC выдаём временной
                    // источник: SIN(off, amp, freq) — для синуса; PULSE(...) —
                    // для меандра. Треугольник пока не поддерживается ngspice
                    // одной строкой, fallback на DC. AC 1 оставляем для AC-анализа.
                    var sig = component._signalSource;
                    var sourceLine;
                    if (sig && sig.wave === 'sine' && sig.frequency > 0) {
                        sourceLine = 'SIN(' + fmt(sig.offset || 0) + ' ' +
                                     fmt(sig.amplitude || voltageValue) + ' ' +
                                     fmt(sig.frequency) + ')';
                    } else if (sig && sig.wave === 'square' && sig.frequency > 0) {
                        var amp = sig.amplitude || voltageValue;
                        var off = sig.offset || 0;
                        var period = 1 / sig.frequency;
                        sourceLine = 'PULSE(' + fmt(off - amp) + ' ' + fmt(off + amp) + ' 0 1n 1n ' +
                                     fmt(period / 2) + ' ' + fmt(period) + ')';
                    } else if (sig && sig.wave === 'triangle' && sig.frequency > 0) {
                        // Треугольник через PWL c R=0 (повтор): один период из 4 точек
                        // (0, 1/4, 3/4, 1)·T = (0, +amp, -amp, 0). За счёт R=0 ngspice
                        // зацикливает паттерн до конца TRAN-окна.
                        var ampT = sig.amplitude || voltageValue;
                        var offT = sig.offset || 0;
                        var pT = 1 / sig.frequency;
                        sourceLine = 'PWL(' +
                            '0 ' + fmt(offT) + ' ' +
                            fmt(pT * 0.25) + ' ' + fmt(offT + ampT) + ' ' +
                            fmt(pT * 0.75) + ' ' + fmt(offT - ampT) + ' ' +
                            fmt(pT)        + ' ' + fmt(offT) +
                            ') R=0';
                    } else {
                        sourceLine = 'DC ' + fmt(voltageValue);
                    }
                    lines.push('V' + component.id + ' ' + getNode(component.id, '+') + ' ' + getNode(component.id, '-') + ' ' + sourceLine + ' AC 1');
                    circuitElements.push({
                        id: component.id,
                        type: 'V',
                        nodes: [getNode(component.id, '+'), getNode(component.id, '-')],
                        value: voltageValue,
                        label: 'V' + component.id,
                        signalSource: sig || null,
                    });
                    break;
                }
                case 'current_source': {
                    // SPICE: Ixxx N+ N- value — независимый источник тока,
                    // положительное направление: ток вытекает из N+, входит в N-.
                    // Поле component.current задаётся в А (амперах).
                    var iParser = typeof parseEngValue === 'function' ? parseEngValue : function (_, value) {
                        return Number(value);
                    };
                    var iValue = iParser('current', component.current);
                    if (!isFinite(iValue)) iValue = 0.001;   // 1 мА по умолчанию
                    lines.push('I' + component.id + ' ' + getNode(component.id, '+') +
                               ' ' + getNode(component.id, '-') + ' ' + fmt(iValue));
                    circuitElements.push({
                        id: component.id,
                        type: 'I',
                        nodes: [getNode(component.id, '+'), getNode(component.id, '-')],
                        value: iValue,
                        label: 'I' + component.id,
                    });
                    break;
                }
                case 'switch': {
                    var closed = component.closed !== false;
                    if (closed) {
                        lines.push('R' + component.id + 'SW ' + nA() + ' ' + nB() + ' 1m');
                        circuitElements.push({ id: 1000 + component.id, type: 'R', nodes: [nA(), nB()], value: 1e-3, label: 'SW' + component.id });
                    } else {
                        lines.push('* S' + component.id + ' открыт (разомкнут) - ветка отключена');
                    }
                    break;
                }
                case 'npn':
                case 'pnp': {
                    var collectorNode = getNode(component.id, 'c');
                    var baseNode = getNode(component.id, 'b');
                    var emitterNode = getNode(component.id, 'e');
                    var model = component.type === 'npn' ? 'QNPN' : 'QPNP';
                    lines.push('Q' + component.id + ' ' + collectorNode + ' ' + baseNode + ' ' + emitterNode + ' ' + model);
                    if (component.type === 'npn') {
                        modelFlags.needNpnModel = true;
                    } else {
                        modelFlags.needPnpModel = true;
                    }
                    circuitElements.push({
                        id: component.id,
                        type: component.type === 'npn' ? 'QN' : 'QP',
                        nodes: [collectorNode, baseNode, emitterNode],
                        label: 'Q' + component.id,
                    });
                    break;
                }
                case 'ground':
                case 'node':
                    break;
                default:
                    errors.push('Неизвестный тип компонента: ' + component.type);
            }
        });

        return {
            lines: lines,
            errors: errors,
            circuitElements: circuitElements,
            modelFlags: modelFlags,
        };
    }

    function buildModelLines(modelFlags) {
        var flags = modelFlags || {};
        var lines = [];
        if (flags.needDiodeModel) lines.push('.model DMOD D (IS=1e-14 N=1)');
        if (flags.needLedModel) lines.push('.model LEDMOD D (IS=1e-14 N=2 BV=5)');
        if (flags.needNpnModel) lines.push('.model QNPN NPN (BF=200 IS=1e-14 VAF=100)');
        if (flags.needPnpModel) lines.push('.model QPNP PNP (BF=150 IS=1e-14 VAF=100)');
        return lines;
    }

    function buildAnalysisDirectives(options) {
        var opts = options || {};
        var fmt = opts.formatSpiceNumber || formatSpiceNumber;
        var analysisType = opts.analysisType || 'dc';
        var simTime = parseFloat(opts.simTime) || 1000;
        var nodeCount = Number(opts.nodeCount) || 0;
        var tStopSec = simTime * 1e-3;
        // Авто-расширение TRAN-окна: если на каком-либо источнике активен
        // _signalSource с известной частотой — автоматически выставляем
        // tStop = max(текущее, 5 периодов / freq), чтобы пользователю было
        // видно несколько циклов без ручного выставления simTime. Шаг — 1/200
        // периода для гладкой осциллограммы. Берём минимальную (самую
        // низкочастотную) частоту, чтобы охватить ВСЕ источники.
        var maxSignalPeriod = 0;
        if (Array.isArray(opts.components)) {
            for (var ci = 0; ci < opts.components.length; ci += 1) {
                var sig = opts.components[ci] && opts.components[ci]._signalSource;
                if (sig && sig.frequency > 0) {
                    var period = 1 / sig.frequency;
                    if (period > maxSignalPeriod) maxSignalPeriod = period;
                }
            }
        }
        if (maxSignalPeriod > 0 && (analysisType === 'pulse' || analysisType === 'transient')) {
            var auto = maxSignalPeriod * 5;
            if (auto > tStopSec) tStopSec = auto;
        }
        var tStepSec = Math.max(tStopSec / 1000, 1e-9);
        if (maxSignalPeriod > 0) {
            // Шаг не грубее 1/200 минимального периода — иначе осциллограмма
            // зубчатая. Но и не мельче 1 нс, чтобы ngspice не подавился.
            var sigStep = Math.max(maxSignalPeriod / 200, 1e-9);
            if (sigStep < tStepSec) tStepSec = sigStep;
        }
        var lines = [];

        switch (analysisType) {
            case 'dc':
                lines.push('.op');
                break;
            case 'ac': {
                lines.push('.ac DEC 20 1 1Meg');
                var acProbes = [];
                for (var node = 1; node < nodeCount; node += 1) {
                    acProbes.push('vdb(' + node + ')', 'vp(' + node + ')');
                }
                if (acProbes.length) lines.push('.print ac ' + acProbes.join(' '));
                break;
            }
            case 'pulse':
            case 'transient':
                lines.push('.tran ' + fmt(tStepSec) + ' ' + fmt(tStopSec));
                var tranProbes = [];
                for (var tranNode = 1; tranNode < nodeCount; tranNode += 1) {
                    tranProbes.push('v(' + tranNode + ')');
                }
                if (tranProbes.length) lines.push('.print tran ' + tranProbes.join(' '));
                break;
        }

        return {
            lines: lines,
            analysisType: analysisType,
            simTime: simTime,
            tStopSec: tStopSec,
            tStepSec: tStepSec,
        };
    }

    // Утилита для лаборатории и других потребителей: вернуть готовую карту
    // «compId:portId» → netId (тот же id, что и в result.nodeVoltages).
    // Это та же union-find, что строит buildElementNetlist, но без побочных
    // эффектов SPICE-генерации.
    function buildPortNetMap(components, connections, getComponentPorts) {
        var uf = createUnionFind();
        registerComponentPorts(components, getComponentPorts, uf.find);
        connectPorts(connections, uf.union);
        var groundRoots = findGroundRoots(components, uf.find);
        if (groundRoots.size === 0) {
            addFirstAvailableGroundRoot(components, getComponentPorts, uf.find, groundRoots);
        }
        var resolver = createNodeResolver(groundRoots, uf.find);
        var map = new Map();
        (components || []).forEach(function (component) {
            (getComponentPorts(component.type) || []).forEach(function (port) {
                map.set(portKey(component.id, port.id), String(resolver.getNode(component.id, port.id)));
            });
        });
        return map;
    }

    window.DolgSchemeNetlist = {
        addFirstAvailableGroundRoot: addFirstAvailableGroundRoot,
        buildAnalysisDirectives: buildAnalysisDirectives,
        buildElementNetlist: buildElementNetlist,
        buildModelLines: buildModelLines,
        buildPortNetMap: buildPortNetMap,
        connectPorts: connectPorts,
        createNodeResolver: createNodeResolver,
        createUnionFind: createUnionFind,
        findGroundRoots: findGroundRoots,
        formatSpiceNumber: formatSpiceNumber,
        portKey: portKey,
        registerComponentPorts: registerComponentPorts,
    };
})(window);
