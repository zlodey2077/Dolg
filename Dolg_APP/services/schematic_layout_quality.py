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


def analyze_schematic_layout(scheme_data: dict[str, Any] | None) -> dict[str, Any]:
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

    crossings = _count_crossings(segments)
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
            crossings,
        )
    elif crossings:
        _finding(
            findings,
            'warning',
            'wire_crossings',
            'There are wire crossings; verify junction dots and reroute where possible.',
            crossings,
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
        },
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
    source_id = _endpoint_id(connection.get('from'))
    target_id = _endpoint_id(connection.get('to'))
    if source_id not in by_id or target_id not in by_id:
        return None
    source = _center(by_id[source_id])
    target = _center(by_id[target_id])
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


def _is_diagonal(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return abs(a[0] - b[0]) > WIRE_TOLERANCE and abs(a[1] - b[1]) > WIRE_TOLERANCE


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return hypot(a[0] - b[0], a[1] - b[1])


def _count_crossings(segments: list[dict[str, Any]]) -> int:
    count = 0
    for left, right in combinations(segments, 2):
        if left['connection_index'] == right['connection_index']:
            continue
        if {left['source_id'], left['target_id']} & {right['source_id'], right['target_id']}:
            continue
        if _segments_intersect(left['a'], left['b'], right['a'], right['b']):
            count += 1
    return count


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
        width, height = SIZE_BY_TYPE.get(ctype, (76, 42))
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


def _finding(findings: list[dict[str, Any]], severity: str, code: str, message: str, evidence: Any) -> None:
    findings.append(
        {
            'severity': severity,
            'code': code,
            'message': message,
            'evidence': evidence,
        }
    )
