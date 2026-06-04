"""Topology detectors for expert review rules.

Each ``detect_*`` function reads ``scheme_data`` and returns a small evidence
dict (counts, refs, paths). The dict is merged into the facts namespace that
``expert_rules.evaluate_expert_rules`` consumes, so new rules in
``default_rules.json`` can fire on declarative ``when`` expressions without
hard-coded Python branches in the review pipeline.

The detectors operate at the *net* level: a tiny UnionFind groups
``(component_id, port_id)`` pairs into shared nets, mirroring the JS
netlist solver in ``shop/static/simulation/scheme-netlist.js``.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .schematic_graph import normalize_component_type


class _UnionFind:
    def __init__(self):
        self._parent: dict[str, str] = {}

    def find(self, key: str) -> str:
        parent = self._parent.setdefault(key, key)
        if parent == key:
            return key
        root = self.find(parent)
        self._parent[key] = root
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb


def _component_dict(scheme_data: Any) -> dict[str, dict]:
    if not isinstance(scheme_data, dict):
        return {}
    out = {}
    for component in scheme_data.get('components') or []:
        if not isinstance(component, dict):
            continue
        cid = component.get('id')
        if cid is None:
            continue
        out[str(cid)] = component
    return out


def _connections(scheme_data: Any):
    if not isinstance(scheme_data, dict):
        return []
    return [c for c in scheme_data.get('connections') or [] if isinstance(c, dict)]


def _port_key(comp_id: Any, port_id: Any) -> str:
    return f'{comp_id}::{port_id or "a"}'


def _label(component: dict) -> str:
    return str(
        component.get('label')
        or component.get('ref')
        or component.get('part_number')
        or component.get('id')
        or component.get('type')
        or 'элемент'
    )


def _parse_voltage(component: dict) -> float | None:
    for key in ('voltage', 'value'):
        raw = component.get(key)
        if raw in (None, ''):
            continue
        try:
            return float(raw)
        except TypeError, ValueError:
            continue
    return None


def build_net_union(scheme_data: Any) -> tuple[_UnionFind, dict[str, set]]:
    """Return UnionFind keyed by `f'{comp_id}::{port_id}'` plus net→members map."""
    uf = _UnionFind()
    components = _component_dict(scheme_data)

    # Node-typed components collapse all their pins into one net (junction dots).
    for cid, component in components.items():
        ctype = normalize_component_type(component.get('type'))
        if ctype in {'ground', 'node'}:
            anchor = _port_key(cid, 'a')
            uf.find(anchor)
            for port in ('b', 'c', 'd', 'in', 'out'):
                uf.union(anchor, _port_key(cid, port))

    for conn in _connections(scheme_data):
        src = conn.get('from') or {}
        dst = conn.get('to') or {}
        sa, sb = src.get('compId'), src.get('portId') or 'a'
        ta, tb = dst.get('compId'), dst.get('portId') or 'a'
        if sa is None or ta is None:
            continue
        uf.union(_port_key(sa, sb), _port_key(ta, tb))

    members: dict[str, set] = defaultdict(set)
    for key in list(uf._parent.keys()):
        members[uf.find(key)].add(key)
    return uf, members


def _ground_nets(scheme_data: Any, uf: _UnionFind) -> set[str]:
    nets = set()
    for cid, component in _component_dict(scheme_data).items():
        if normalize_component_type(component.get('type')) == 'ground':
            nets.add(uf.find(_port_key(cid, 'a')))
    return nets


def _battery_terminal_nets(component_id: str, uf: _UnionFind) -> tuple[str, str]:
    return uf.find(_port_key(component_id, 'a')), uf.find(_port_key(component_id, 'b'))


def detect_led_reverse_polarity(scheme_data: Any, uf: _UnionFind | None = None) -> dict[str, Any]:
    """LED with cathode tied to a positive source net (battery 'a') and anode to ground.

    LEDs in DOLG canvas use 'a' = anode (positive) and 'b' = cathode (negative).
    Reverse polarity = anode connected to ground while cathode is on a source net.
    """
    if uf is None:
        uf, _ = build_net_union(scheme_data)
    components = _component_dict(scheme_data)
    ground_nets = _ground_nets(scheme_data, uf)
    source_pos_nets = set()
    for cid, comp in components.items():
        if normalize_component_type(comp.get('type')) == 'battery':
            pos_net, _neg = _battery_terminal_nets(cid, uf)
            source_pos_nets.add(pos_net)

    refs = []
    for cid, comp in components.items():
        if normalize_component_type(comp.get('type')) != 'led':
            continue
        anode_net = uf.find(_port_key(cid, 'a'))
        cathode_net = uf.find(_port_key(cid, 'b'))
        # Reverse polarity = anode tied to ground while cathode sits on a
        # non-ground rail. The cathode does not have to touch the source net
        # directly — going through a current-limiting resistor is the usual
        # mistake. The anti-pattern is "anode on GND".
        if anode_net in ground_nets and cathode_net not in ground_nets:
            refs.append(_label(comp))
            continue
        # Symmetric case: cathode on a positive source net AND anode is not
        # ground — also a reverse hookup if there's a clear voltage gradient.
        if cathode_net in source_pos_nets and anode_net not in source_pos_nets:
            refs.append(_label(comp))
    return {'led_reverse_polarity_count': len(refs), 'led_reverse_polarity_refs': refs}


def detect_parallel_voltage_sources(scheme_data: Any, uf: _UnionFind | None = None) -> dict[str, Any]:
    """Two or more batteries sharing both terminal nets with different voltages."""
    if uf is None:
        uf, _ = build_net_union(scheme_data)
    components = _component_dict(scheme_data)
    batteries = []
    for cid, comp in components.items():
        if normalize_component_type(comp.get('type')) != 'battery':
            continue
        pos_net, neg_net = _battery_terminal_nets(cid, uf)
        voltage = _parse_voltage(comp)
        batteries.append({'id': cid, 'ref': _label(comp), 'pos': pos_net, 'neg': neg_net, 'v': voltage})

    conflicts = []
    for i in range(len(batteries)):
        for j in range(i + 1, len(batteries)):
            a, b = batteries[i], batteries[j]
            if a['pos'] == b['pos'] and a['neg'] == b['neg']:
                if a['v'] is not None and b['v'] is not None and abs(a['v'] - b['v']) > 1e-6:
                    conflicts.append({'refs': [a['ref'], b['ref']], 'voltages': [a['v'], b['v']]})
    return {
        'parallel_source_conflict_count': len(conflicts),
        'parallel_source_conflicts': conflicts,
    }


def detect_source_short_to_ground(scheme_data: Any, uf: _UnionFind | None = None) -> dict[str, Any]:
    """Battery whose positive terminal reaches ground without a resistor in the loop.

    A short = battery's positive net is connected to a ground net via at least
    one path that does NOT pass through a resistor. The return path
    (battery '-' terminal → GND) is normal and excluded from the check.

    Implementation: build a net-level graph where edges are non-limiting
    two-pin components (battery itself is excluded — we are looking for a
    parallel path that bypasses the load). The battery's own '-' terminal
    is the legitimate return; we only ask whether '+' terminal has another
    path to ground that avoids every resistor.
    """
    import networkx as nx

    if uf is None:
        uf, _ = build_net_union(scheme_data)
    components = _component_dict(scheme_data)
    ground_nets = _ground_nets(scheme_data, uf)
    if not ground_nets:
        return {'source_short_count': 0, 'source_short_pairs': []}

    # Net-level graph: edges = two-pin components that conduct without
    # limiting current (diode, led, inductor, capacitor in DC sense skipped).
    # Resistors are intentionally NOT added — they are the protection element.
    # Battery is also excluded — we look for bypass paths, not the battery
    # itself.
    PASS_TYPES = {'diode', 'led', 'inductor', 'button', 'switch', 'transistor', 'ic'}
    net_graph = nx.Graph()
    for cid, comp in components.items():
        ctype = normalize_component_type(comp.get('type'))
        if ctype not in PASS_TYPES:
            continue
        # Pick first two distinct port nets — covers the 2-pin case and the
        # transistor C/E for conservative shorting (B is excluded since
        # tying base to GND alone doesn't short the rail).
        ports = ('a', 'b') if ctype != 'transistor' else ('c', 'e')
        net_a = uf.find(_port_key(cid, ports[0]))
        net_b = uf.find(_port_key(cid, ports[1]))
        if net_a != net_b:
            net_graph.add_edge(net_a, net_b)

    # Also: direct wires (without any limiter) already collapse nets via UF,
    # so a battery '+' net that *equals* a ground net is the most direct short.

    shorts = []
    for cid, comp in components.items():
        if normalize_component_type(comp.get('type')) != 'battery':
            continue
        pos_net, _neg_net = _battery_terminal_nets(cid, uf)
        # Direct short: '+' is on the same net as ground.
        if pos_net in ground_nets:
            for ground_id, gcomp in components.items():
                if normalize_component_type(gcomp.get('type')) == 'ground':
                    if uf.find(_port_key(ground_id, 'a')) == pos_net:
                        shorts.append({'source': _label(comp), 'ground': _label(gcomp)})
                        break
            continue
        # Bypass short: a non-resistor path from '+' net to any ground net.
        if pos_net not in net_graph:
            continue
        for gnet in ground_nets:
            if gnet not in net_graph:
                continue
            if nx.has_path(net_graph, pos_net, gnet):
                shorts.append({'source': _label(comp), 'ground': 'GND'})
                break
    return {'source_short_count': len(shorts), 'source_short_pairs': shorts}


def detect_dangling_named_net(scheme_data: Any, uf: _UnionFind | None = None) -> dict[str, Any]:
    """Named-net `node` components with degree ≤ 1 — label without a real connection."""
    if uf is None:
        uf, _ = build_net_union(scheme_data)
    components = _component_dict(scheme_data)

    degree: dict[str, int] = defaultdict(int)
    for conn in _connections(scheme_data):
        for endpoint in (conn.get('from') or {}, conn.get('to') or {}):
            cid = endpoint.get('compId')
            if cid is not None and str(cid) in components:
                degree[str(cid)] += 1

    refs = []
    for cid, comp in components.items():
        ctype = normalize_component_type(comp.get('type'))
        if ctype != 'node':
            continue
        label = (comp.get('label') or '').strip()
        if not label or label in {'•', '·'}:
            continue
        if degree.get(cid, 0) <= 1:
            refs.append(label)
    return {'dangling_named_net_count': len(refs), 'dangling_named_net_refs': refs}


def detect_transistor_pinout_swap(scheme_data: Any, uf: _UnionFind | None = None) -> dict[str, Any]:
    """Heuristic: collector tied directly to ground, or emitter tied directly to a source net.

    DOLG canvas uses 'c'/'b'/'e' for NPN/PNP transistor pins. A swap is when:
      * NPN collector net == ground net (no current limiter)
      * NPN emitter net == battery positive net
      * (PNP heuristic kept symmetric — would be reversed; we report both.)
    """
    if uf is None:
        uf, _ = build_net_union(scheme_data)
    components = _component_dict(scheme_data)
    ground_nets = _ground_nets(scheme_data, uf)
    source_pos_nets = set()
    source_neg_nets = set()
    for cid, comp in components.items():
        if normalize_component_type(comp.get('type')) != 'battery':
            continue
        pos_net, neg_net = _battery_terminal_nets(cid, uf)
        source_pos_nets.add(pos_net)
        source_neg_nets.add(neg_net)

    refs = []
    for cid, comp in components.items():
        ctype = normalize_component_type(comp.get('type'))
        if ctype != 'transistor':
            continue
        c_net = uf.find(_port_key(cid, 'c'))
        e_net = uf.find(_port_key(cid, 'e'))
        if c_net in ground_nets or e_net in source_pos_nets:
            refs.append(_label(comp))
    return {'transistor_pinout_swap_count': len(refs), 'transistor_pinout_swap_refs': refs}


def collect_topology_evidence(scheme_data: Any) -> dict[str, Any]:
    """Run all detectors once. Returns a flat evidence dict for expert facts."""
    uf, _ = build_net_union(scheme_data)
    evidence: dict[str, Any] = {}
    evidence.update(detect_led_reverse_polarity(scheme_data, uf))
    evidence.update(detect_parallel_voltage_sources(scheme_data, uf))
    evidence.update(detect_source_short_to_ground(scheme_data, uf))
    evidence.update(detect_dangling_named_net(scheme_data, uf))
    evidence.update(detect_transistor_pinout_swap(scheme_data, uf))
    # 2026-05-31: бOльшой пак новых detector'ов для DRC v3 (103 правила).
    evidence.update(detect_connectivity_extras(scheme_data, uf))
    evidence.update(detect_power_extras(scheme_data, uf))
    evidence.update(detect_polarity_extras(scheme_data, uf))
    evidence.update(detect_rating_extras(scheme_data, uf))
    evidence.update(detect_topology_extras(scheme_data, uf))
    evidence.update(detect_docs_extras(scheme_data, uf))
    evidence.update(detect_simulation_extras(scheme_data, uf))
    evidence.update(detect_bom_extras(scheme_data, uf))
    return evidence


# ─── A. CONNECTIVITY EXTRAS ───────────────────────────────────────────────
def detect_connectivity_extras(scheme_data: Any, uf: _UnionFind | None = None) -> dict[str, Any]:
    """Single-port components, dangling ports, disjoint islands, duplicate wires,
    multiple GND nets, isolated GND, multiple outputs on one net."""
    if uf is None:
        uf, _ = build_net_union(scheme_data)
    comps = _component_dict(scheme_data)
    conns = list(_connections(scheme_data))
    evidence: dict[str, Any] = {}

    # conn.single_connection_component / dangling_port
    used_ports: set[tuple] = set()
    for c in conns:
        f = c.get('from') or {}
        t = c.get('to') or {}
        if f.get('compId') is not None:
            used_ports.add((f['compId'], f.get('portId')))
        if t.get('compId') is not None:
            used_ports.add((t['compId'], t.get('portId')))
    single_port = 0
    dangling = 0
    for cid, comp in comps.items():
        ports = comp.get('ports') or [{'id': 'a'}, {'id': 'b'}]
        if len(ports) < 2:
            continue
        used_count = sum(1 for p in ports if (cid, p.get('id')) in used_ports)
        if used_count == 1:
            single_port += 1
        if used_count < len(ports) and (comp.get('type') or '').lower() != 'ground':
            dangling += len(ports) - used_count
    evidence['single_port_components'] = single_port
    evidence['dangling_port_count'] = dangling

    # conn.disjoint_islands
    if comps:
        nets_by_comp: dict[str, set] = {}
        for cid, comp in comps.items():
            ports = comp.get('ports') or [{'id': 'a'}]
            nets_by_comp[cid] = {uf.find(_port_key(cid, p.get('id'))) for p in ports}
        # union-find на компонентах: соединяем те у которых есть общий net
        comp_uf = _UnionFind()
        for cid in comps:
            comp_uf.find(cid)
        comp_ids = list(comps.keys())
        for i in range(len(comp_ids)):
            for j in range(i + 1, len(comp_ids)):
                if nets_by_comp[comp_ids[i]] & nets_by_comp[comp_ids[j]]:
                    comp_uf.union(comp_ids[i], comp_ids[j])
        islands = {comp_uf.find(c) for c in comp_ids}
        evidence['connected_components_count'] = len(islands)
    else:
        evidence['connected_components_count'] = 0

    # conn.duplicate_wire
    pairs = set()
    dups = 0
    for c in conns:
        f = c.get('from') or {}
        t = c.get('to') or {}
        key = tuple(
            sorted(
                [
                    (f.get('compId'), f.get('portId')),
                    (t.get('compId'), t.get('portId')),
                ]
            )
        )
        if key in pairs:
            dups += 1
        else:
            pairs.add(key)
    evidence['duplicate_wires'] = dups

    # conn.multiple_gnd_different_nets
    ground_comps = [c for c in comps.values() if (c.get('type') or '').lower() == 'ground']
    gnd_nets = {uf.find(_port_key(c['id'], 'a')) for c in ground_comps}
    evidence['ground_net_count'] = len(gnd_nets)

    # connectivity.gnd_without_other_components — GND есть, но он одинокий
    isolated_gnd = 0
    if ground_comps:
        for gnd in ground_comps:
            gnd_net = uf.find(_port_key(gnd['id'], 'a'))
            # есть ли в этом net'е другие компоненты?
            others = 0
            for cid, comp in comps.items():
                if cid == gnd['id']:
                    continue
                ports = comp.get('ports') or []
                for p in ports:
                    if uf.find(_port_key(cid, p.get('id'))) == gnd_net:
                        others += 1
                        break
            if others == 0:
                isolated_gnd += 1
    evidence['isolated_ground_count'] = isolated_gnd

    # connectivity.multiple_outputs_on_one_net (для будущих IC; placeholder)
    evidence['multi_output_net_count'] = 0
    # connectivity.orphan_net_label_count
    labeled_nets = set()
    for c in conns:
        if c.get('net_label'):
            f = c.get('from') or {}
            labeled_nets.add((c['net_label'], uf.find(_port_key(f.get('compId'), f.get('portId')))))
    # Орфаны: label есть, но net пуст (нет компонентов кроме самого wire'а)
    evidence['orphan_net_label_count'] = 0  # TODO: точнее, требует port_count per net

    return evidence


# ─── B. POWER EXTRAS ──────────────────────────────────────────────────────
def detect_power_extras(scheme_data: Any, uf: _UnionFind | None = None) -> dict[str, Any]:
    if uf is None:
        uf, _ = build_net_union(scheme_data)
    comps = _component_dict(scheme_data)
    evidence: dict[str, Any] = {}

    batteries = [c for c in comps.values() if (c.get('type') or '').lower() == 'battery']
    current_sources = [c for c in comps.values() if (c.get('type') or '').lower() == 'current_source']

    # power.parallel_voltage_same_level: те же net'ы + равное напряжение
    same_level = 0
    for i in range(len(batteries)):
        for j in range(i + 1, len(batteries)):
            bi, bj = batteries[i], batteries[j]
            ni_p, ni_n = _battery_terminal_nets(bi['id'], uf)
            nj_p, nj_n = _battery_terminal_nets(bj['id'], uf)
            if ni_p == nj_p and ni_n == nj_n:
                vi, vj = _parse_voltage(bi), _parse_voltage(bj)
                if vi is not None and vj is not None and abs(vi - vj) < 0.01:
                    same_level += 1
    evidence['parallel_voltage_sources'] = same_level
    evidence['parallel_voltage_difference'] = 0  # для уверенности

    # power.source_no_return_path — нет общего net'а с GND (через любой путь)
    ground_set = _ground_nets(scheme_data, uf)
    no_return = 0
    for b in batteries:
        n_plus, n_minus = _battery_terminal_nets(b['id'], uf)
        if n_minus not in ground_set and n_plus not in ground_set:
            no_return += 1
    evidence['source_without_return'] = no_return

    # power.battery_reverse_polarity (heuristic): если + батареи напрямую к GND
    # и − не к GND — это вероятная обратная полярность нагрузки.
    reverse_pol = 0
    for b in batteries:
        n_plus, n_minus = _battery_terminal_nets(b['id'], uf)
        if n_plus in ground_set and n_minus not in ground_set:
            reverse_pol += 1
    evidence['reverse_battery_polarity'] = reverse_pol

    # power.current_source_open_loop — для current_source оба конца должны
    # иметь замкнутый путь. Простая проверка: оба net'а != одинаковый.
    open_loop = 0
    for cs in current_sources:
        ports = cs.get('ports') or [{'id': '+'}, {'id': '-'}]
        if len(ports) < 2:
            continue
        n1 = uf.find(_port_key(cs['id'], ports[0].get('id')))
        n2 = uf.find(_port_key(cs['id'], ports[1].get('id')))
        if n1 == n2:  # КЗ → не open loop
            continue
        # Эвристика: если ни одного из net'ов нет в GND-set И нет других
        # компонентов на них — open loop.
        # Полная проверка требует BFS, упрощаем.
        open_loop += 0  # placeholder; полная реализация в Phase 2
    evidence['current_source_open_loop'] = open_loop

    # Остальные placeholder'ы
    evidence['opposing_sources_count'] = 0
    evidence['active_components_without_decoupling'] = 0
    evidence['has_source_gnd_short'] = (
        bool(batteries)
        and ground_set
        and any(
            uf.find(_port_key(b['id'], '+')) in ground_set and uf.find(_port_key(b['id'], '-')) in ground_set
            for b in batteries
        )
    )
    evidence['short_circuit_path'] = 1 if evidence['has_source_gnd_short'] else 0
    evidence['has_ac_source'] = False
    evidence['has_dc_bias_component'] = bool(batteries)

    return evidence


# ─── C. POLARITY EXTRAS ───────────────────────────────────────────────────
def detect_polarity_extras(scheme_data: Any, uf: _UnionFind | None = None) -> dict[str, Any]:
    if uf is None:
        uf, _ = build_net_union(scheme_data)
    comps = _component_dict(scheme_data)
    evidence: dict[str, Any] = {}

    # polarity.electrolytic_reverse — конденсаторы тип electrolytic с обратным V
    rev_elec = 0
    rev_rect_diode = 0
    rev_led = 0
    forward_zener = 0
    for cid, comp in comps.items():
        t = (comp.get('type') or '').lower()
        params = comp.get('catalog_parameters') or comp.get('parameters') or {}
        sub = (params.get('subtype') or params.get('dielectric') or '').lower()
        if t == 'capacitor' and 'elec' in sub:
            # Без симуляции точно сказать нельзя — placeholder
            rev_elec += 0
        if t == 'diode':
            if 'zener' in sub:
                # Эвристика: zener должен быть в обратном смещении к GND
                forward_zener += 0
            else:
                rev_rect_diode += 0  # full check в Phase 2
        if t == 'led':
            rev_led += 0  # full check в Phase 2 — пока существующий detect_led_reverse_polarity
    evidence['reverse_electrolytic_count'] = rev_elec
    evidence['reverse_rectifier_diode_count'] = rev_rect_diode
    evidence['reverse_led_count'] = rev_led
    evidence['zener_forward_count'] = forward_zener
    evidence['has_tantalum'] = any(
        (c.get('catalog_parameters') or {}).get('dielectric', '').lower() == 'tantalum'
        for c in comps.values()
    )
    evidence['tantalum_derating'] = 1.0  # без catalog info предполагаем OK
    evidence['bjt_pinout_suspicious_count'] = 0  # покрыто старым detector'ом

    return evidence


# ─── D. RATING EXTRAS ─────────────────────────────────────────────────────
def detect_rating_extras(scheme_data: Any, uf: _UnionFind | None = None) -> dict[str, Any]:
    # rating evidence требует sim-result; frontend перебивает с реальными значениями
    evidence: dict[str, Any] = {}

    # rating.voltage_exceeded — требует sim result, frontend это считает.
    # Backend здесь даёт 0 как safe default; frontend перебивает.
    evidence['voltage_rating_violations'] = 0
    evidence['resistor_power_violation_count'] = 0
    evidence['cap_v_peak_exceeded'] = 0
    evidence['bjt_vceo_exceeded'] = 0
    evidence['diode_vbr_exceeded'] = 0
    evidence['led_overdrive_count'] = 0
    evidence['resistor_low_derating'] = 0
    evidence['inductor_isat_exceeded'] = 0
    evidence['high_power_no_heatsink_count'] = 0
    return evidence


# ─── E. TOPOLOGY EXTRAS ───────────────────────────────────────────────────
def detect_topology_extras(scheme_data: Any, uf: _UnionFind | None = None) -> dict[str, Any]:
    if uf is None:
        uf, _ = build_net_union(scheme_data)
    comps = _component_dict(scheme_data)
    evidence: dict[str, Any] = {}

    # LED-цепочка без CC — простая эвристика: если LED + резистор в одной цепи,
    # но нет источника тока I-source.
    leds = [c for c in comps.values() if (c.get('type') or '').lower() == 'led']
    cs_count = sum(1 for c in comps.values() if (c.get('type') or '').lower() == 'current_source')
    evidence['led_series_chain_no_cc_count'] = max(0, len(leds) - cs_count) if len(leds) >= 2 else 0

    # Реле/индуктивная нагрузка с транзистором → нужен freewheeling диод
    inductors = [c for c in comps.values() if (c.get('type') or '').lower() == 'inductor']
    transistors = [c for c in comps.values() if (c.get('type') or '').lower() in ('npn', 'pnp')]
    diodes = sum(1 for c in comps.values() if (c.get('type') or '').lower() == 'diode')
    evidence['inductive_load_no_diode_count'] = max(0, min(len(inductors), len(transistors)) - diodes)

    # Остальные — placeholder'ы для Phase 2
    evidence['opamp_no_feedback_count'] = 0
    evidence['opamp_input_rail_violations'] = 0
    evidence['floating_digital_inputs'] = 0
    evidence['ac_divider_asymmetry'] = 0
    evidence['rc_q_factor'] = 0
    evidence['crystal_without_load_caps'] = 0
    evidence['reset_pin_floating'] = False
    evidence['diff_pair_mismatch'] = 0
    evidence['estimated_snr_db'] = 60
    evidence['loop_gain_db'] = 0
    evidence['unprotected_external_input_count'] = 0
    evidence['opto_no_pulldown_count'] = 0

    return evidence


# ─── F. DOCS EXTRAS ───────────────────────────────────────────────────────
def detect_docs_extras(scheme_data: Any, uf: _UnionFind | None = None) -> dict[str, Any]:
    comps = _component_dict(scheme_data)
    evidence: dict[str, Any] = {}

    # docs.no_project_description — проверка снаружи (project model)
    evidence['project_description_empty'] = False  # backend project_review подставит

    # docs.unlabeled_components
    evidence['unlabeled_component_count'] = sum(
        1 for c in comps.values() if not (c.get('label') or '').strip()
    )

    # docs.no_net_labels
    conns = list(_connections(scheme_data))
    named_nets = sum(1 for c in conns if c.get('net_label'))
    evidence['named_net_count'] = named_nets
    evidence['schematic_title_block_empty'] = True  # пока всегда True (нет support'a)
    evidence['test_point_count'] = 0

    return evidence


# ─── G. SIMULATION EXTRAS ─────────────────────────────────────────────────
def detect_simulation_extras(scheme_data: Any, uf: _UnionFind | None = None) -> dict[str, Any]:
    """Большая часть требует runtime данных от simulation runs.
    Здесь placeholder с дефолтами; реальные значения подставляет
    project_review при наличии."""
    comps = _component_dict(scheme_data)
    evidence: dict[str, Any] = {}
    evidence['sim_run_count'] = 0  # подставит project_review
    evidence['dc_no_convergence'] = False
    evidence['tran_step_ratio'] = 0
    evidence['ac_sweep_decades'] = 5
    evidence['unrealistic_value_count'] = sum(
        1
        for c in comps.values()
        if (c.get('type') or '').lower() == 'resistor' and float(c.get('resistance') or 1) <= 0
    )
    evidence['tran_no_ic'] = False
    evidence['has_reactive_components'] = any(
        (c.get('type') or '').lower() in ('capacitor', 'inductor') for c in comps.values()
    )
    evidence['last_sim_warning_count'] = 0
    evidence['ideal_source_count'] = sum(
        1 for c in comps.values() if (c.get('type') or '').lower() == 'battery'
    )

    return evidence


# ─── H. BOM EXTRAS ────────────────────────────────────────────────────────
def detect_bom_extras(scheme_data: Any, uf: _UnionFind | None = None) -> dict[str, Any]:
    comps = _component_dict(scheme_data)
    evidence: dict[str, Any] = {}

    # bom.unbound_components — компоненты без catalog_ref
    unbound = sum(1 for c in comps.values() if not (c.get('catalog_ref') or '').strip())
    evidence['unbound_component_count'] = unbound

    # bom.duplicate_designators
    labels = [c.get('label') for c in comps.values() if c.get('label')]
    dup_count = len(labels) - len(set(labels))
    evidence['duplicate_designator_count'] = max(0, dup_count)

    # bom.active_components_without_spice
    active_no_spice = sum(
        1
        for c in comps.values()
        if (c.get('type') or '').lower() in ('npn', 'pnp', 'diode', 'led')
        and not (c.get('spice_model') or '').strip()
    )
    evidence['active_components_without_spice'] = active_no_spice

    # Placeholder'ы
    evidence['eol_component_count'] = 0
    evidence['oos_component_count'] = 0
    evidence['bom_category_mismatch_count'] = 0
    evidence['total_bom_cost'] = 0
    evidence['cost_dominant_share'] = 0
    # Compliance / signal / layout — внешние данные нужны
    for k in [
        'non_rohs_components',
        'emc_filter_present',
        'high_voltage_creepage_violations',
        'external_connector_count',
        'ce_protection_count',
        'has_power_input',
        'high_speed_unterminated',
        'clock_no_damping',
        'long_unbuffered_traces',
        'parallel_high_speed_pairs',
        'simultaneous_switching_outputs',
        'high_speed_stubs',
        'long_clock_line_count',
        'trace_width_violations',
        'clearance_violations',
        'small_via_count',
        'small_smd_pad_count',
        'silkscreen_overlap_count',
        'mounting_holes_count',
        'has_ground_pour',
        'ai_pattern_matches',
        'ai_anomaly_score',
        'crossing_count',
        'explicit_node_count',
        'min_wire_spacing_px',
        'min_segment_length_px',
    ]:
        if k not in evidence:
            evidence[k] = (
                0 if 'count' in k or k.endswith('_violations') else False if k.startswith('has_') else 0
            )

    return evidence
