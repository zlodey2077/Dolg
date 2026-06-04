"""Graph helpers for schematic topology checks.

The service intentionally keeps NetworkX behind function calls so importing
Django views does not pull optional analysis dependencies into startup.
"""

from __future__ import annotations

from collections import Counter

TYPE_ALIASES = {
    'r': 'resistor',
    'res': 'resistor',
    'c': 'capacitor',
    'cap': 'capacitor',
    'l': 'inductor',
    'd': 'diode',
    'led': 'led',
    'v': 'battery',
    'vsource': 'battery',
    'voltage_source': 'battery',
    'dc_source': 'battery',
    'source': 'battery',
    'gnd': 'ground',
    '0': 'ground',
    'q': 'transistor',
    'npn': 'transistor',
    'pnp': 'transistor',
    'bjt': 'transistor',
    'ic': 'ic',
    'u': 'ic',
    'switch': 'button',
    'pushbutton': 'button',
    'button': 'button',
}


def normalize_component_type(value):
    raw = str(value or '').strip().lower()
    if raw in TYPE_ALIASES:
        return TYPE_ALIASES[raw]
    if raw.startswith('res'):
        return 'resistor'
    if raw.startswith('cap'):
        return 'capacitor'
    if raw.startswith('bat') or raw.startswith('source'):
        return 'battery'
    return raw


def _components(scheme_data):
    if not isinstance(scheme_data, dict):
        return []
    return [item for item in scheme_data.get('components') or [] if isinstance(item, dict)]


def _connections(scheme_data):
    if not isinstance(scheme_data, dict):
        return []
    return [item for item in scheme_data.get('connections') or [] if isinstance(item, dict)]


def _component_id(component):
    if component.get('id') is None:
        return None
    return str(component.get('id'))


def _component_label(component):
    return str(
        component.get('label')
        or component.get('ref')
        or component.get('part_number')
        or component.get('id')
        or component.get('type')
        or 'component'
    )


def _endpoint_id(endpoint):
    if isinstance(endpoint, dict) and endpoint.get('compId') is not None:
        return str(endpoint.get('compId'))
    return None


def _looks_like_output_node(component):
    label = _component_label(component).lower()
    return label in {'out', 'vout', 'output', 'v(out)'} or 'vout' in label


def build_schematic_graph(scheme_data):
    """Build a component-level undirected graph for topology analysis."""
    import networkx as nx

    graph = nx.Graph()
    id_to_component = {}
    errors = []

    for component in _components(scheme_data):
        cid = _component_id(component)
        if cid is None:
            errors.append('component_without_id')
            continue
        ctype = normalize_component_type(component.get('type'))
        id_to_component[cid] = component
        graph.add_node(
            cid,
            label=_component_label(component),
            type=ctype,
            raw=component,
            is_ground=ctype == 'ground',
            is_source=ctype in {'battery', 'current_source'},
            is_output=_looks_like_output_node(component),
        )

    for index, connection in enumerate(_connections(scheme_data)):
        source_id = _endpoint_id(connection.get('from') or {})
        target_id = _endpoint_id(connection.get('to') or {})
        if source_id not in id_to_component or target_id not in id_to_component:
            errors.append(f'connection_{index}_missing_component')
            continue
        if source_id == target_id:
            errors.append(f'connection_{index}_self_loop')
            continue
        graph.add_edge(source_id, target_id, connection=connection, index=index)

    return {
        'graph': graph,
        'components': id_to_component,
        'errors': errors,
    }


def analyze_graph_topology(scheme_data):
    """Return graph-level errors, warnings and metrics for DRC/review/AI."""
    import networkx as nx

    built = build_schematic_graph(scheme_data)
    graph = built['graph']
    components = built['components']
    errors = list(built['errors'])
    warnings = []

    counts = Counter(data.get('type') for _, data in graph.nodes(data=True))
    ground_nodes = [node for node, data in graph.nodes(data=True) if data.get('is_ground')]
    source_nodes = [node for node, data in graph.nodes(data=True) if data.get('is_source')]
    output_nodes = [node for node, data in graph.nodes(data=True) if data.get('is_output')]

    connected_components = (
        [sorted(group) for group in nx.connected_components(graph)] if graph.number_of_nodes() else []
    )
    isolated = sorted(nx.isolates(graph))
    floating_components = []
    paths_to_ground = {}

    for component_group in connected_components:
        has_ground = any(node in ground_nodes for node in component_group)
        if not has_ground:
            floating_components.extend(component_group)
        for node in component_group:
            if node in ground_nodes:
                paths_to_ground[node] = [node]
                continue
            shortest = None
            for ground in ground_nodes:
                try:
                    candidate = nx.shortest_path(graph, node, ground)
                except nx.NetworkXNoPath:
                    continue
                if shortest is None or len(candidate) < len(shortest):
                    shortest = candidate
            paths_to_ground[node] = shortest or []

    if graph.number_of_nodes() and not ground_nodes:
        warnings.append('В графе схемы нет GND: все компоненты считаются floating.')
    if graph.number_of_nodes() and len(connected_components) > 1:
        warnings.append(f'Схема разбита на несвязные части: {len(connected_components)}.')
    if isolated:
        labels = [_component_label(components[node]) for node in isolated[:8] if node in components]
        warnings.append(f'Есть изолированные компоненты: {", ".join(labels)}.')

    cycle_basis = nx.cycle_basis(graph)
    topology = 'generic'
    if counts.get('resistor', 0) >= 2 and ground_nodes and source_nodes:
        topology = 'voltage_divider'
    if counts.get('capacitor', 0) and counts.get('resistor', 0) and ground_nodes and source_nodes:
        topology = 'rc_network'
    if counts.get('led', 0) and counts.get('resistor', 0):
        topology = 'led_indicator'

    metrics = {
        'component_count': graph.number_of_nodes(),
        'connection_count': graph.number_of_edges(),
        'component_counts': dict(counts),
        'has_ground': bool(ground_nodes),
        'has_source': bool(source_nodes),
        'connected_components_count': len(connected_components),
        'connected_components': connected_components,
        'isolated_components': isolated,
        'floating_components': sorted(set(floating_components)),
        'cycle_count': len(cycle_basis),
        'cycles': cycle_basis[:8],
        'paths_to_ground': paths_to_ground,
        'output_nodes': output_nodes,
        'topology': topology,
    }
    metrics['is_connected'] = graph.number_of_nodes() == 0 or len(connected_components) == 1
    metrics['has_output_node'] = bool(output_nodes)

    return {
        'ok': not errors,
        'errors': errors,
        'warnings': warnings,
        'metrics': metrics,
    }
