"""Schematic layout quality guardrails.

Electrical schematics are not generic node-link graphs. This module flags
layouts that look like graph hairballs: direct diagonal wires, missing
orthogonal waypoints, avoidable crossings, overlapping symbols and flattened
internal/external subcircuits on one sheet.
"""

from __future__ import annotations

from itertools import combinations
from math import hypot
from typing import Any

from .schematic_graph import normalize_component_type

WIRE_TOLERANCE = 4
MIN_WIRE_LENGTH = 16
LONG_WIRE = 120

INTERNAL_TYPES = {
    'comparator',
    'sr_latch',
    'output_driver',
    'pin',
}
INTERNAL_ID_PREFIXES = ('P', 'RINT', 'N_REF', 'CMP_', 'SR_', 'Q_DISCH', 'OUT_DRIVER')
EXTERNAL_TYPES = {
    'battery',
    'resistor',
    'capacitor',
    'inductor',
    'diode',
    'led',
    'transistor',
    'button',
    'switch',
    'connector',
    'potentiometer',
}

SIZE_BY_TYPE = {
    'node': (18, 18),
    'ground': (44, 28),
    'pin': (54, 26),
    'resistor': (82, 38),
    'potentiometer': (90, 42),
    'capacitor': (70, 46),
    'battery': (86, 46),
    'connector': (88, 40),
    'transistor': (86, 68),
    'led': (72, 46),
    'comparator': (116, 58),
    'sr_latch': (86, 64),
    'output_driver': (110, 64),
}

ESKD_REF_PREFIXES = {
    'resistor': ('R',),
    'potentiometer': ('R',),
    'capacitor': ('C',),
    'inductor': ('L',),
    'battery': ('GB', 'G'),
    'current_source': ('G',),
    'diode': ('VD',),
    'led': ('HL', 'VD'),
    'transistor': ('VT',),
    'button': ('SB',),
    'switch': ('S', 'SA', 'SB'),
    'connector': ('X', 'XP', 'XS'),
    'ic': ('DA', 'DD', 'D'),
    'relay': ('K',),
}

ESKD_SYMBOL_STANDARDS = {
    'resistor': ('ГОСТ 2.728', 'GOST 2.728'),
    'potentiometer': ('ГОСТ 2.728', 'GOST 2.728'),
    'capacitor': ('ГОСТ 2.728', 'GOST 2.728'),
    'diode': ('ГОСТ 2.730', 'GOST 2.730'),
    'led': ('ГОСТ 2.730', 'GOST 2.730'),
    'transistor': ('ГОСТ 2.730', 'GOST 2.730'),
    'button': ('ГОСТ 2.755', 'GOST 2.755'),
    'switch': ('ГОСТ 2.755', 'GOST 2.755'),
    'connector': ('ГОСТ 2.755', 'GOST 2.755'),
    'battery': ('ГОСТ 2.768', 'GOST 2.768'),
    'ic': ('ГОСТ 2.743', 'GOST 2.743', 'ГОСТ 2.721', 'GOST 2.721'),
}

ESKD_VALUE_REQUIRED_TYPES = {
    'resistor': ('Ом', 'кОм', 'МОм', 'ohm', 'kohm', 'mohm'),
    'potentiometer': ('Ом', 'кОм', 'МОм', 'ohm', 'kohm', 'mohm'),
    'capacitor': ('пФ', 'нФ', 'мкФ', 'Ф', 'pf', 'nf', 'uf'),
    'inductor': ('мкГн', 'мГн', 'Гн', 'uh', 'mh'),
    'battery': ('В', 'V'),
}

ESKD_BLACK_COLORS = {'', 'black', '#000', '#000000', '#111', '#111111', 'none'}


def analyze_schematic_layout(scheme_data: dict[str, Any] | None, *, profile: str | None = None) -> dict[str, Any]:
    profile = _resolve_profile(scheme_data, profile)
    scopes = _layout_scopes(scheme_data)
    if not scopes:
        return _analyze_flat_schematic_layout(scheme_data, profile=profile)

    scoped_reports = []
    if _components(scheme_data) or _connections(scheme_data):
        scoped_reports.append(('root', _analyze_flat_schematic_layout(scheme_data, profile=profile)))
    for scope_name, scope_data in scopes:
        scoped_reports.append((scope_name, _analyze_flat_schematic_layout(scope_data, profile=profile)))
    return _merge_scoped_reports(scoped_reports, profile=profile)


def _analyze_flat_schematic_layout(scheme_data: dict[str, Any] | None, *, profile: str = 'generic') -> dict[str, Any]:
    components = _components(scheme_data)
    connections = _connections(scheme_data)
    by_id = {str(item.get('id')): item for item in components if item.get('id') is not None}
    findings: list[dict[str, Any]] = []

    missing_coordinates = [
        str(item.get('id') or index)
        for index, item in enumerate(components)
        if _center(item) is None
    ]
    if missing_coordinates:
        _finding(
            findings,
            'error',
            'missing_component_coordinates',
            'Components must have stable x/y coordinates before schematic layout can be accepted.',
            missing_coordinates[:12],
        )

    segments = []
    direct_diagonal_connections = []
    diagonal_segments = []
    unrouted_long_connections = []

    for index, connection in enumerate(connections):
        wire = _wire_points(connection, by_id)
        if not wire:
            continue
        points, source_id, target_id = wire
        if len(points) == 2 and _is_diagonal(points[0], points[1]) and _distance(points[0], points[1]) >= LONG_WIRE:
            direct_diagonal_connections.append(index)
            unrouted_long_connections.append(index)
        for left, right in zip(points, points[1:]):
            if _distance(left, right) < MIN_WIRE_LENGTH:
                continue
            segment = {
                'connection_index': index,
                'source_id': source_id,
                'target_id': target_id,
                'a': left,
                'b': right,
            }
            segments.append(segment)
            if _is_diagonal(left, right):
                diagonal_segments.append(segment)

    crossing_pairs = _wire_crossings(segments)
    crossings = len(crossing_pairs)
    overlaps = _component_overlaps(components)
    hierarchy_problem = _detect_flattened_hierarchy(components, scheme_data)
    diagonal_ratio = len(diagonal_segments) / len(segments) if segments else 0
    direct_diagonal_ratio = len(direct_diagonal_connections) / len(connections) if connections else 0

    if hierarchy_problem:
        _finding(
            findings,
            'error',
            'hierarchical_subcircuit_required',
            'Internal IC implementation and external wiring are flattened onto one sheet. Use a subcircuit sheet with ports instead.',
            hierarchy_problem,
        )

    if len(direct_diagonal_connections) >= 3 and direct_diagonal_ratio >= 0.18:
        _finding(
            findings,
            'error',
            'unrouted_direct_diagonal_wires',
            'Too many long direct diagonal wires. Add orthogonal waypoints or route through explicit rails/nets.',
            direct_diagonal_connections[:20],
        )
    elif direct_diagonal_connections:
        _finding(
            findings,
            'warning',
            'direct_diagonal_wires',
            'Some long wires are direct diagonals; simulator layouts should use orthogonal routes.',
            direct_diagonal_connections[:20],
        )

    if len(diagonal_segments) >= 8 and diagonal_ratio >= 0.25:
        _finding(
            findings,
            'error',
            'graph_like_wire_geometry',
            'The wire geometry looks graph-like: many segments are diagonal instead of schematic routes.',
            {
                'diagonal_segments': len(diagonal_segments),
                'segment_count': len(segments),
                'ratio': round(diagonal_ratio, 3),
            },
        )

    if crossings > max(12, len(connections) // 3):
        _finding(
            findings,
            'error',
            'too_many_wire_crossings',
            'The schematic has too many avoidable wire crossings for a simulator/editor preview.',
            crossing_pairs[:20],
        )
    elif crossings:
        _finding(
            findings,
            'warning',
            'wire_crossings',
            'There are wire crossings; verify junction dots and reroute where possible.',
            crossing_pairs[:20],
        )

    if overlaps:
        _finding(
            findings,
            'warning',
            'component_overlaps',
            'Some component bounding boxes overlap. Move symbols before accepting the layout.',
            overlaps[:20],
        )

    hub_findings = _hub_without_bus_routes(connections)
    if hub_findings:
        _finding(
            findings,
            'warning',
            'hub_without_bus_routes',
            'High fan-out nodes should be drawn as rails/buses, not as many center-to-center wires.',
            hub_findings,
        )

    if _is_eskd_profile(profile, scheme_data):
        _append_eskd_findings(findings, components, connections, scheme_data)

    errors = [item['message'] for item in findings if item['severity'] == 'error']
    warnings = [item['message'] for item in findings if item['severity'] == 'warning']
    return {
        'ok': not errors,
        'errors': errors,
        'warnings': warnings,
        'findings': findings,
        'metrics': {
            'component_count': len(components),
            'connection_count': len(connections),
            'segment_count': len(segments),
            'diagonal_segment_count': len(diagonal_segments),
            'diagonal_segment_ratio': round(diagonal_ratio, 3),
            'direct_diagonal_connection_count': len(direct_diagonal_connections),
            'direct_diagonal_connection_ratio': round(direct_diagonal_ratio, 3),
            'crossing_count': crossings,
            'overlap_count': len(overlaps),
            'missing_coordinate_count': len(missing_coordinates),
            'requires_hierarchy': bool(hierarchy_problem),
            'profile': profile,
        },
    }


def _resolve_profile(scheme_data: dict[str, Any] | None, profile: str | None) -> str:
    if profile:
        return str(profile).strip().lower()
    if isinstance(scheme_data, dict):
        metadata = scheme_data.get('metadata') if isinstance(scheme_data.get('metadata'), dict) else {}
        value = metadata.get('standard_profile') or metadata.get('standard') or ''
        if value:
            return str(value).strip().lower()
    return 'generic'


def _layout_scopes(scheme_data: dict[str, Any] | None) -> list[tuple[str, dict[str, Any]]]:
    if not isinstance(scheme_data, dict):
        return []
    scopes = []
    for index, sheet in enumerate(scheme_data.get('sheets') or []):
        if not isinstance(sheet, dict):
            continue
        name = sheet.get('id') or sheet.get('name') or sheet.get('title') or f'sheet_{index + 1}'
        scopes.append((f'sheet:{name}', sheet))
    for index, subcircuit in enumerate(scheme_data.get('subcircuits') or []):
        if not isinstance(subcircuit, dict):
            continue
        name = subcircuit.get('id') or subcircuit.get('name') or subcircuit.get('title') or f'subcircuit_{index + 1}'
        scopes.append((f'subcircuit:{name}', subcircuit))
    return scopes


def _merge_scoped_reports(scoped_reports: list[tuple[str, dict[str, Any]]], *, profile: str = 'generic') -> dict[str, Any]:
    findings = []
    metrics = {
        'scope_count': len(scoped_reports),
        'scopes': {},
        'component_count': 0,
        'connection_count': 0,
        'segment_count': 0,
        'diagonal_segment_count': 0,
        'direct_diagonal_connection_count': 0,
        'crossing_count': 0,
        'overlap_count': 0,
        'missing_coordinate_count': 0,
        'requires_hierarchy': False,
        'profile': profile,
    }
    for scope_name, report in scoped_reports:
        scope_metrics = report.get('metrics') or {}
        metrics['scopes'][scope_name] = scope_metrics
        for key in (
            'component_count',
            'connection_count',
            'segment_count',
            'diagonal_segment_count',
            'direct_diagonal_connection_count',
            'crossing_count',
            'overlap_count',
            'missing_coordinate_count',
        ):
            metrics[key] += int(scope_metrics.get(key) or 0)
        metrics['requires_hierarchy'] = metrics['requires_hierarchy'] or bool(scope_metrics.get('requires_hierarchy'))
        for finding in report.get('findings') or []:
            item = dict(finding)
            item['scope'] = scope_name
            item['message'] = f'{scope_name}: {item.get("message", "")}'
            findings.append(item)

    segment_count = metrics['segment_count'] or 1
    connection_count = metrics['connection_count'] or 1
    metrics['diagonal_segment_ratio'] = round(metrics['diagonal_segment_count'] / segment_count, 3)
    metrics['direct_diagonal_connection_ratio'] = round(
        metrics['direct_diagonal_connection_count'] / connection_count,
        3,
    )
    errors = [item['message'] for item in findings if item['severity'] == 'error']
    warnings = [item['message'] for item in findings if item['severity'] == 'warning']
    return {
        'ok': not errors,
        'errors': errors,
        'warnings': warnings,
        'findings': findings,
        'metrics': metrics,
    }


def _components(scheme_data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(scheme_data, dict):
        return []
    return [item for item in scheme_data.get('components') or [] if isinstance(item, dict)]


def _connections(scheme_data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(scheme_data, dict):
        return []
    return [item for item in scheme_data.get('connections') or [] if isinstance(item, dict)]


def _center(component: dict[str, Any]) -> tuple[float, float] | None:
    try:
        return float(component['x']), float(component['y'])
    except (KeyError, TypeError, ValueError):
        return None


def _wire_points(connection: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> tuple[list[tuple[float, float]], str, str] | None:
    source_endpoint = connection.get('from')
    target_endpoint = connection.get('to')
    source_id = _endpoint_id(source_endpoint)
    target_id = _endpoint_id(target_endpoint)
    if source_id not in by_id or target_id not in by_id:
        return None
    source = _endpoint_point(source_endpoint, by_id)
    target = _endpoint_point(target_endpoint, by_id)
    if source is None or target is None:
        return None
    waypoints = []
    for item in connection.get('waypoints') or []:
        if not isinstance(item, dict):
            continue
        try:
            waypoints.append((float(item['x']), float(item['y'])))
        except (KeyError, TypeError, ValueError):
            continue
    return [source, *waypoints, target], source_id, target_id


def _endpoint_id(endpoint: Any) -> str | None:
    if not isinstance(endpoint, dict):
        return None
    value = endpoint.get('compId') or endpoint.get('component') or endpoint.get('component_id')
    return str(value) if value is not None else None


def _endpoint_point(endpoint: Any, by_id: dict[str, dict[str, Any]]) -> tuple[float, float] | None:
    if not isinstance(endpoint, dict):
        return None
    if endpoint.get('x') is not None and endpoint.get('y') is not None:
        try:
            return float(endpoint['x']), float(endpoint['y'])
        except (TypeError, ValueError):
            return None
    component_id = _endpoint_id(endpoint)
    if component_id not in by_id:
        return None
    component = by_id[component_id]
    center = _center(component)
    if center is None:
        return None
    port_id = endpoint.get('portId') or endpoint.get('port') or endpoint.get('pin') or endpoint.get('terminal')
    if port_id is None:
        return center
    port = _find_port(component, str(port_id))
    if not port:
        return center
    if port.get('x') is not None and port.get('y') is not None:
        try:
            return float(port['x']), float(port['y'])
        except (TypeError, ValueError):
            return center
    if port.get('dx') is not None and port.get('dy') is not None:
        try:
            return center[0] + float(port['dx']), center[1] + float(port['dy'])
        except (TypeError, ValueError):
            return center
    return center


def _find_port(component: dict[str, Any], port_id: str) -> dict[str, Any] | None:
    for port in component.get('ports') or []:
        if isinstance(port, dict) and str(port.get('id')) == port_id:
            return port
    return None


def _is_diagonal(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return abs(a[0] - b[0]) > WIRE_TOLERANCE and abs(a[1] - b[1]) > WIRE_TOLERANCE


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return hypot(a[0] - b[0], a[1] - b[1])


def _wire_crossings(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    crossings = []
    for left, right in combinations(segments, 2):
        if left['connection_index'] == right['connection_index']:
            continue
        if {left['source_id'], left['target_id']} & {right['source_id'], right['target_id']}:
            continue
        if _segments_intersect(left['a'], left['b'], right['a'], right['b']):
            crossings.append(
                {
                    'left_connection_index': left['connection_index'],
                    'right_connection_index': right['connection_index'],
                    'left_endpoints': [left['source_id'], left['target_id']],
                    'right_endpoints': [right['source_id'], right['target_id']],
                }
            )
    return crossings


def _segments_intersect(a, b, c, d) -> bool:
    if _shared_endpoint(a, b, c, d):
        return False

    def orient(p, q, r):
        value = (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])
        if abs(value) <= WIRE_TOLERANCE:
            return 0
        return 1 if value > 0 else 2

    def on_segment(p, q, r):
        return (
            min(p[0], r[0]) - WIRE_TOLERANCE <= q[0] <= max(p[0], r[0]) + WIRE_TOLERANCE
            and min(p[1], r[1]) - WIRE_TOLERANCE <= q[1] <= max(p[1], r[1]) + WIRE_TOLERANCE
        )

    o1 = orient(a, b, c)
    o2 = orient(a, b, d)
    o3 = orient(c, d, a)
    o4 = orient(c, d, b)
    if o1 != o2 and o3 != o4:
        return True
    return (
        (o1 == 0 and on_segment(a, c, b))
        or (o2 == 0 and on_segment(a, d, b))
        or (o3 == 0 and on_segment(c, a, d))
        or (o4 == 0 and on_segment(c, b, d))
    )


def _shared_endpoint(a, b, c, d) -> bool:
    points = (a, b)
    other = (c, d)
    return any(_distance(left, right) <= WIRE_TOLERANCE for left in points for right in other)


def _component_overlaps(components: list[dict[str, Any]]) -> list[dict[str, str]]:
    boxes = []
    for component in components:
        center = _center(component)
        if center is None:
            continue
        ctype = normalize_component_type(component.get('type'))
        width, height = _component_size(component, ctype)
        if ctype in {'node', 'ground'}:
            continue
        x, y = center
        boxes.append(
            {
                'id': str(component.get('id')),
                'left': x - width / 2,
                'right': x + width / 2,
                'top': y - height / 2,
                'bottom': y + height / 2,
            }
        )

    overlaps = []
    for left, right in combinations(boxes, 2):
        if (
            left['left'] < right['right']
            and left['right'] > right['left']
            and left['top'] < right['bottom']
            and left['bottom'] > right['top']
        ):
            overlaps.append({'left': left['id'], 'right': right['id']})
    return overlaps


def _component_size(component: dict[str, Any], component_type: str) -> tuple[float, float]:
    layout = component.get('layout') if isinstance(component.get('layout'), dict) else {}
    width = component.get('width') or layout.get('width')
    height = component.get('height') or layout.get('height')
    try:
        if width is not None and height is not None:
            parsed_width = float(width)
            parsed_height = float(height)
            if parsed_width > 0 and parsed_height > 0:
                return parsed_width, parsed_height
    except (TypeError, ValueError):
        pass
    return SIZE_BY_TYPE.get(component_type, (76, 42))


def _detect_flattened_hierarchy(components: list[dict[str, Any]], scheme_data: dict[str, Any] | None) -> dict[str, int] | None:
    if isinstance(scheme_data, dict) and (scheme_data.get('sheets') or scheme_data.get('subcircuits')):
        return None
    internal = 0
    external = 0
    for component in components:
        cid = str(component.get('id') or '')
        ctype = normalize_component_type(component.get('type'))
        if ctype in INTERNAL_TYPES or cid.startswith(INTERNAL_ID_PREFIXES):
            internal += 1
        if ctype in EXTERNAL_TYPES and not cid.startswith(('RINT', 'Q_DISCH')):
            external += 1
    if internal >= 4 and external >= 6 and len(components) >= 18:
        return {'internal_component_count': internal, 'external_component_count': external}
    return None


def _hub_without_bus_routes(connections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    degree: dict[str, dict[str, Any]] = {}
    for connection in connections:
        waypoint_count = len(connection.get('waypoints') or [])
        for side in ('from', 'to'):
            cid = _endpoint_id(connection.get(side))
            if not cid:
                continue
            entry = degree.setdefault(cid, {'degree': 0, 'unrouted': 0})
            entry['degree'] += 1
            if waypoint_count == 0:
                entry['unrouted'] += 1
    out = []
    for cid, data in degree.items():
        if data['degree'] >= 8 and data['unrouted'] >= 5:
            out.append({'component': cid, **data})
    return out[:10]


def _is_eskd_profile(profile: str, scheme_data: dict[str, Any] | None) -> bool:
    text = (profile or '').lower()
    if 'eskd' in text or 'гост' in text or 'gost' in text:
        return True
    if isinstance(scheme_data, dict):
        metadata = scheme_data.get('metadata') if isinstance(scheme_data.get('metadata'), dict) else {}
        value = str(metadata.get('standard_profile') or metadata.get('standard') or '').lower()
        return 'eskd' in value or 'гост' in value or 'gost' in value
    return False


def _append_eskd_findings(
    findings: list[dict[str, Any]],
    components: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    scheme_data: dict[str, Any] | None,
) -> None:
    metadata = scheme_data.get('metadata') if isinstance(scheme_data, dict) and isinstance(scheme_data.get('metadata'), dict) else {}
    eskd = metadata.get('eskd') if isinstance(metadata.get('eskd'), dict) else {}
    scope_kind = str(eskd.get('scope_kind') or metadata.get('scope_kind') or 'principle').lower()

    if not eskd.get('scheme_code') and scope_kind in {'principle', 'external'}:
        _finding(
            findings,
            'warning',
            'eskd_missing_scheme_code',
            'ESKD sheet should declare scheme_code, for example E3/Э3 for an electrical schematic.',
            metadata,
        )

    if scope_kind in {'functional', 'internal_functional'}:
        _append_functional_eskd_findings(findings, components)
        return

    ref_errors = []
    value_errors = []
    symbol_errors = []
    style_errors = []

    for component in components:
        ctype = normalize_component_type(component.get('type'))
        if ctype in {'node', 'ground', 'pin'}:
            continue

        refdes = _component_refdes(component)
        allowed_prefixes = ESKD_REF_PREFIXES.get(ctype)
        if allowed_prefixes and not _refdes_matches(refdes, allowed_prefixes):
            ref_errors.append(
                {
                    'id': component.get('id'),
                    'type': ctype,
                    'refdes': refdes,
                    'expected_prefix': allowed_prefixes,
                }
            )

        required_units = ESKD_VALUE_REQUIRED_TYPES.get(ctype)
        if required_units and not _has_value_with_unit(component, required_units):
            value_errors.append(
                {
                    'id': component.get('id'),
                    'refdes': refdes,
                    'type': ctype,
                    'expected_units': required_units,
                }
            )

        expected_standards = ESKD_SYMBOL_STANDARDS.get(ctype)
        if expected_standards and not _has_symbol_standard(component, expected_standards):
            symbol_errors.append(
                {
                    'id': component.get('id'),
                    'refdes': refdes,
                    'type': ctype,
                    'expected': expected_standards,
                }
            )

        bad_style = _bad_eskd_style(component)
        if bad_style:
            style_errors.append({'id': component.get('id'), 'refdes': refdes, **bad_style})

    if ref_errors:
        _finding(
            findings,
            'error',
            'eskd_refdes_prefix_mismatch',
            'Component reference designators do not match ESKD-style letter prefixes.',
            ref_errors[:30],
        )
    if value_errors:
        _finding(
            findings,
            'error',
            'eskd_missing_nominal_units',
            'Nominal values must be written with units for ESKD-style electrical schematics.',
            value_errors[:30],
        )
    if symbol_errors:
        _finding(
            findings,
            'error',
            'eskd_missing_symbol_standard',
            'Components must declare the GOST/ESKD symbol standard used by their UGO.',
            symbol_errors[:30],
        )
    if style_errors:
        _finding(
            findings,
            'error',
            'eskd_non_monochrome_style',
            'ESKD output must not depend on simulator colors for electrical connections or symbols.',
            style_errors[:30],
        )

    missing_net_labels = [
        index
        for index, connection in enumerate(connections)
        if not (connection.get('net_label') or connection.get('net') or connection.get('label'))
    ]
    if missing_net_labels:
        _finding(
            findings,
            'warning',
            'eskd_unlabeled_connections',
            'Named nets are recommended for ESKD review/export; unlabeled connections make checking harder.',
            missing_net_labels[:30],
        )


def _append_functional_eskd_findings(findings: list[dict[str, Any]], components: list[dict[str, Any]]) -> None:
    unnamed_blocks = []
    for component in components:
        ctype = normalize_component_type(component.get('type'))
        if ctype in {'node', 'ground'}:
            continue
        label = str(component.get('label') or component.get('name') or '').strip()
        if not label:
            unnamed_blocks.append({'id': component.get('id'), 'type': ctype})
    if unnamed_blocks:
        _finding(
            findings,
            'error',
            'eskd_functional_block_without_name',
            'Functional ESKD-style sheets may use rectangles, but every functional block must be named.',
            unnamed_blocks[:30],
        )


def _component_refdes(component: dict[str, Any]) -> str:
    return str(component.get('refdes') or component.get('ref') or component.get('reference') or component.get('label') or component.get('id') or '').strip()


def _refdes_matches(refdes: str, prefixes: tuple[str, ...]) -> bool:
    if not refdes:
        return False
    upper = refdes.upper().replace(' ', '')
    for prefix in sorted(prefixes, key=len, reverse=True):
        if upper.startswith(prefix) and upper[len(prefix): len(prefix) + 1].isdigit():
            return True
    return False


def _has_value_with_unit(component: dict[str, Any], units: tuple[str, ...]) -> bool:
    candidates = [
        component.get('value_label'),
        component.get('nominal_label'),
        component.get('display_value'),
        component.get('value'),
        component.get('resistance'),
        component.get('capacitance'),
        component.get('inductance'),
        component.get('voltage'),
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        text = str(candidate).strip()
        if not text:
            continue
        lower = text.lower().replace(' ', '')
        if any(unit.lower().replace(' ', '') in lower for unit in units):
            return True
    return False


def _has_symbol_standard(component: dict[str, Any], expected: tuple[str, ...]) -> bool:
    values = []
    for key in ('symbol_standard', 'ugo_standard', 'standard'):
        value = component.get(key)
        if value:
            values.append(str(value))
    metadata = component.get('metadata') if isinstance(component.get('metadata'), dict) else {}
    for key in ('symbol_standard', 'ugo_standard', 'standard'):
        value = metadata.get(key)
        if value:
            values.append(str(value))
    normalized_values = [value.lower().replace(' ', '') for value in values]
    for expected_item in expected:
        normalized_expected = expected_item.lower().replace(' ', '')
        if any(normalized_expected in value for value in normalized_values):
            return True
    return False


def _bad_eskd_style(component: dict[str, Any]) -> dict[str, Any] | None:
    style = component.get('style') if isinstance(component.get('style'), dict) else {}
    colors = []
    for key in ('color', 'stroke', 'fill'):
        value = component.get(key)
        if value is not None:
            colors.append((key, str(value)))
        style_value = style.get(key)
        if style_value is not None:
            colors.append((f'style.{key}', str(style_value)))
    bad = [
        {'field': key, 'value': value}
        for key, value in colors
        if value.strip().lower() not in ESKD_BLACK_COLORS
    ]
    if bad:
        return {'bad_colors': bad}
    return None


def _finding(findings: list[dict[str, Any]], severity: str, code: str, message: str, evidence: Any) -> None:
    findings.append(
        {
            'severity': severity,
            'code': code,
            'message': message,
            'evidence': evidence,
        }
    )
