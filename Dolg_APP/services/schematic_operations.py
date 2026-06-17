"""Programmatic schematic operations.

This module is the safe bridge between AI/CAD commands and the canonical
``scheme_data`` shape used by the vector editor, validators and exporters.
"""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from .schematic_graph import normalize_component_type

MAX_OPERATIONS = 200

DEFAULT_PORTS: dict[str, list[str]] = {
    'resistor': ['1', '2'],
    'capacitor': ['1', '2'],
    'inductor': ['1', '2'],
    'battery': ['+', '-'],
    'current_source': ['+', '-'],
    'ground': ['a'],
    'node': ['a'],
    'diode': ['a', 'k'],
    'led': ['a', 'k'],
    'transistor': ['c', 'b', 'e'],
    'button': ['1', '2'],
    'switch': ['1', '2'],
    'relay': ['coil+', 'coil-', 'com', 'no', 'nc'],
    'connector': ['1'],
    'ic': ['1', '2'],
}

ID_PREFIXES: dict[str, str] = {
    'resistor': 'R',
    'capacitor': 'C',
    'inductor': 'L',
    'battery': 'V',
    'current_source': 'I',
    'ground': 'GND',
    'node': 'N',
    'diode': 'D',
    'led': 'LED',
    'transistor': 'Q',
    'button': 'SW',
    'switch': 'SW',
    'relay': 'K',
    'connector': 'J',
    'ic': 'U',
}

OPERATION_ALIASES = {
    'connect': 'add_wire',
    'add_connection': 'add_wire',
    'wire': 'add_wire',
    'delete_connection': 'delete_wire',
    'remove_wire': 'delete_wire',
    'remove_component': 'delete_component',
    'set_label': 'set_property',
}

RESERVED_COMPONENT_PROPERTIES = {'id', 'ports'}


def apply_schematic_operations(
    scheme_data: dict[str, Any] | None,
    operations: list[dict[str, Any]] | dict[str, Any] | None,
    *,
    atomic: bool = False,
) -> dict[str, Any]:
    """Apply a whitelisted operation log to a copy of ``scheme_data``.

    ``atomic=True`` rolls the whole batch back if any operation is rejected.
    With the default ``atomic=False`` each operation is still isolated: a
    rejected command cannot leave a half-mutated scheme behind.
    """

    original = _scheme_copy(scheme_data)
    state = _scheme_copy(scheme_data)
    ops = _coerce_operations(operations)
    report = {
        'ok': True,
        'atomic': bool(atomic),
        'operation_count': len(ops),
        'applied_count': 0,
        'rejected_count': 0,
        'applied': [],
        'rejected': [],
        'warnings': [],
    }

    if len(ops) > MAX_OPERATIONS:
        return _fatal_result(
            original,
            report,
            'too_many_operations',
            f'At most {MAX_OPERATIONS} operations can be applied at once.',
        )

    if operations is not None and not ops:
        return _fatal_result(
            original, report, 'invalid_operations', 'operations must be an object or an array.'
        )

    for index, operation in enumerate(ops):
        before = deepcopy(state)
        applied = _apply_one(state, operation)
        if applied.get('ok'):
            report['applied'].append(
                {
                    'index': index,
                    'operation': applied.get('operation'),
                    'target': applied.get('target'),
                }
            )
            report['applied_count'] += 1
            continue

        state = before
        rejection = {
            'index': index,
            'operation': _operation_name(operation),
            'code': applied.get('code') or 'operation_rejected',
            'message': applied.get('message') or 'Operation rejected.',
        }
        report['rejected'].append(rejection)
        report['rejected_count'] += 1
        report['ok'] = False
        if atomic:
            state = original
            report['applied'] = []
            report['applied_count'] = 0
            report['rolled_back'] = True
            break

    if report['applied_count']:
        _mark_programmatic_metadata(state, report)

    return {
        'ok': bool(report['ok']),
        'scheme_data': state,
        'report': report,
    }


def _fatal_result(
    scheme_data: dict[str, Any], report: dict[str, Any], code: str, message: str
) -> dict[str, Any]:
    report['ok'] = False
    report['rejected_count'] += 1
    report['rejected'].append(
        {
            'index': None,
            'operation': '',
            'code': code,
            'message': message,
        }
    )
    return {'ok': False, 'scheme_data': scheme_data, 'report': report}


def _scheme_copy(scheme_data: dict[str, Any] | None) -> dict[str, Any]:
    data = deepcopy(scheme_data) if isinstance(scheme_data, dict) else {}
    if not isinstance(data.get('components'), list):
        data['components'] = []
    if not isinstance(data.get('connections'), list):
        data['connections'] = []
    data.setdefault('version', 2)
    return data


def _coerce_operations(operations: list[dict[str, Any]] | dict[str, Any] | None) -> list[dict[str, Any]]:
    if operations is None:
        return []
    if isinstance(operations, dict):
        return [operations]
    if isinstance(operations, list):
        return [item for item in operations if isinstance(item, dict)]
    return []


def _apply_one(state: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    name = _operation_name(operation)
    if name == 'add_component':
        return _add_component(state, operation)
    if name == 'move_component':
        return _move_component(state, operation)
    if name == 'rotate_component':
        return _rotate_component(state, operation)
    if name == 'set_property':
        return _set_property(state, operation)
    if name == 'add_wire':
        return _add_wire(state, operation)
    if name == 'delete_wire':
        return _delete_wire(state, operation)
    if name == 'delete_component':
        return _delete_component(state, operation)
    if name == 'set_net':
        return _set_net(state, operation)
    if name == 'validate':
        return _ok(name, 'scheme')
    return _reject('unknown_operation', f'Unsupported operation: {name or "<empty>"}')


def _operation_name(operation: dict[str, Any] | None) -> str:
    if not isinstance(operation, dict):
        return ''
    raw = operation.get('operation') or operation.get('op') or operation.get('type') or ''
    name = str(raw).strip().lower()
    return OPERATION_ALIASES.get(name, name)


def _add_component(state: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    component = deepcopy(operation.get('component')) if isinstance(operation.get('component'), dict) else {}
    ctype = normalize_component_type(
        component.get('type')
        or operation.get('component_type')
        or operation.get('kind')
        or operation.get('type')
    )
    if not ctype:
        return _reject('missing_component_type', 'add_component requires type/component_type.')

    component['type'] = ctype
    requested_id = component.get('id') or operation.get('id') or operation.get('component_id')
    component['id'] = _safe_id(requested_id) if requested_id is not None else _next_component_id(state, ctype)
    if _component_by_id(state, component['id']):
        return _reject('duplicate_component_id', f'Component {component["id"]} already exists.')

    component['label'] = component.get('label') or operation.get('label') or component['id']
    component['x'] = _as_number(component.get('x', operation.get('x')), 0)
    component['y'] = _as_number(component.get('y', operation.get('y')), 0)
    component['rotation'] = _normalize_rotation(component.get('rotation', operation.get('rotation', 0)))
    component['ports'] = _normalize_ports(
        component.get('ports') or operation.get('ports') or DEFAULT_PORTS.get(ctype, ['1', '2'])
    )

    properties = operation.get('properties')
    if isinstance(properties, dict):
        for key, value in properties.items():
            if key not in RESERVED_COMPONENT_PROPERTIES:
                component[str(key)] = deepcopy(value)

    for key in ('value', 'resistance', 'capacitance', 'inductance', 'voltage', 'part_number', 'catalog_ref'):
        if key in operation and key not in component:
            component[key] = deepcopy(operation[key])

    state['components'].append(component)
    return _ok('add_component', component['id'])


def _move_component(state: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    component = _require_component(state, operation)
    if not component.get('ok'):
        return component
    item = component['component']

    if 'x' in operation or 'y' in operation:
        if 'x' in operation:
            item['x'] = _as_number(operation.get('x'), _as_number(item.get('x'), 0))
        if 'y' in operation:
            item['y'] = _as_number(operation.get('y'), _as_number(item.get('y'), 0))
    else:
        item['x'] = _as_number(item.get('x'), 0) + _as_number(operation.get('dx'), 0)
        item['y'] = _as_number(item.get('y'), 0) + _as_number(operation.get('dy'), 0)
    return _ok('move_component', item.get('id'))


def _rotate_component(state: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    component = _require_component(state, operation)
    if not component.get('ok'):
        return component
    item = component['component']
    if 'rotation' in operation:
        item['rotation'] = _normalize_rotation(operation.get('rotation'))
    else:
        delta = _as_number(operation.get('angle', operation.get('delta')), 90)
        item['rotation'] = _normalize_rotation(_as_number(item.get('rotation'), 0) + delta)
    return _ok('rotate_component', item.get('id'))


def _set_property(state: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    component = _require_component(state, operation)
    if not component.get('ok'):
        return component
    item = component['component']
    properties = operation.get('properties')
    if not isinstance(properties, dict):
        key = operation.get('property') or operation.get('name') or operation.get('key')
        if _operation_name(operation) == 'set_property' and operation.get('operation') == 'set_label':
            key = 'label'
        if not key:
            return _reject('missing_property', 'set_property requires property/name/key or properties.')
        properties = {str(key): operation.get('value')}

    for key, value in properties.items():
        key = str(key)
        if key in RESERVED_COMPONENT_PROPERTIES:
            return _reject(
                'reserved_property', f'Component property {key} cannot be changed with set_property.'
            )
        item[key] = deepcopy(value)
    return _ok('set_property', item.get('id'))


def _add_wire(state: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    source = _normalize_endpoint(operation.get('from') or operation.get('source'))
    target = _normalize_endpoint(operation.get('to') or operation.get('target'))
    if not source or not target:
        return _reject('missing_endpoint', 'add_wire requires from/source and to/target endpoints.')

    source_component = _component_by_id(state, source['compId'])
    target_component = _component_by_id(state, target['compId'])
    if not source_component or not target_component:
        missing = source['compId'] if not source_component else target['compId']
        return _reject('missing_component', f'Endpoint component {missing} does not exist.')
    source = _canonical_endpoint_for_component(source, source_component)
    target = _canonical_endpoint_for_component(target, target_component)
    if source['compId'] == target['compId']:
        return _reject('self_connection', 'Wire endpoints must belong to different components.')
    if not _endpoint_port_exists(source_component, source['portId']):
        return _reject('missing_port', f'Port {source["portId"]} does not exist on {source["compId"]}.')
    if not _endpoint_port_exists(target_component, target['portId']):
        return _reject('missing_port', f'Port {target["portId"]} does not exist on {target["compId"]}.')
    if _connection_exists(state, source, target):
        return _reject('duplicate_wire', 'Wire with the same endpoints already exists.')

    wire_id = _safe_id(operation.get('id')) if operation.get('id') is not None else _next_wire_id(state)
    if _wire_by_id(state, wire_id):
        return _reject('duplicate_wire_id', f'Wire {wire_id} already exists.')

    wire = {
        'id': wire_id,
        'from': source,
        'to': target,
        'waypoints': _normalize_waypoints(operation.get('waypoints')),
    }
    for key in ('route', 'layer', 'net_label'):
        if operation.get(key) is not None:
            wire[key] = operation.get(key)
    state['connections'].append(wire)
    return _ok('add_wire', wire_id)


def _delete_wire(state: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    wire_id = operation.get('id') or operation.get('wire_id') or operation.get('connection_id')
    if wire_id is not None:
        wire = _wire_by_id(state, wire_id)
        if not wire:
            return _reject('missing_wire', f'Wire {wire_id} does not exist.')
        state['connections'] = [item for item in state['connections'] if item is not wire]
        return _ok('delete_wire', str(wire_id))

    source = _normalize_endpoint(operation.get('from') or operation.get('source'))
    target = _normalize_endpoint(operation.get('to') or operation.get('target'))
    if not source or not target:
        return _reject('missing_wire_selector', 'delete_wire requires id or from/to endpoints.')
    source_component = _component_by_id(state, source['compId'])
    target_component = _component_by_id(state, target['compId'])
    if source_component:
        source = _canonical_endpoint_for_component(source, source_component)
    if target_component:
        target = _canonical_endpoint_for_component(target, target_component)
    before = len(state['connections'])
    state['connections'] = [
        item for item in state['connections'] if not _same_connection(item, source, target)
    ]
    if len(state['connections']) == before:
        return _reject('missing_wire', 'Wire with the requested endpoints does not exist.')
    return _ok('delete_wire', 'endpoint_pair')


def _delete_component(state: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    component_id = _component_selector(operation)
    if component_id is None:
        return _reject('missing_component_id', 'delete_component requires id/component/component_id.')
    component = _component_by_id(state, component_id)
    if not component:
        return _reject('missing_component', f'Component {component_id} does not exist.')
    state['components'] = [item for item in state['components'] if item is not component]
    state['connections'] = [
        item
        for item in state['connections']
        if _endpoint_component_id(item.get('from')) != component_id
        and _endpoint_component_id(item.get('to')) != component_id
    ]
    return _ok('delete_component', component_id)


def _set_net(state: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    wire_id = operation.get('id') or operation.get('wire_id') or operation.get('connection_id')
    wire = _wire_by_id(state, wire_id) if wire_id is not None else None
    if wire is None:
        source = _normalize_endpoint(operation.get('from') or operation.get('source'))
        target = _normalize_endpoint(operation.get('to') or operation.get('target'))
        if source and target:
            source_component = _component_by_id(state, source['compId'])
            target_component = _component_by_id(state, target['compId'])
            if source_component:
                source = _canonical_endpoint_for_component(source, source_component)
            if target_component:
                target = _canonical_endpoint_for_component(target, target_component)
            wire = next(
                (item for item in state['connections'] if _same_connection(item, source, target)), None
            )
    if wire is None:
        return _reject('missing_wire', 'set_net requires an existing wire id or endpoint pair.')
    label = operation.get('net') or operation.get('net_label') or operation.get('label')
    if label is None:
        return _reject('missing_net_label', 'set_net requires net/net_label/label.')
    wire['net_label'] = str(label)
    return _ok('set_net', wire.get('id'))


def _component_selector(operation: dict[str, Any]) -> str | None:
    value = operation.get('component') or operation.get('component_id') or operation.get('id')
    if isinstance(value, dict):
        value = value.get('id') or value.get('component') or value.get('component_id')
    return str(value) if value is not None else None


def _require_component(state: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    component_id = _component_selector(operation)
    if component_id is None:
        return _reject('missing_component_id', 'Operation requires id/component/component_id.')
    component = _component_by_id(state, component_id)
    if not component:
        return _reject('missing_component', f'Component {component_id} does not exist.')
    return {'ok': True, 'component': component}


def _component_by_id(state: dict[str, Any], component_id: Any) -> dict[str, Any] | None:
    wanted = str(component_id)
    for item in state.get('components') or []:
        if isinstance(item, dict) and str(item.get('id')) == wanted:
            return item
    return None


def _wire_by_id(state: dict[str, Any], wire_id: Any) -> dict[str, Any] | None:
    wanted = str(wire_id)
    for item in state.get('connections') or []:
        if isinstance(item, dict) and str(item.get('id')) == wanted:
            return item
    return None


def _normalize_endpoint(endpoint: Any) -> dict[str, str] | None:
    if not isinstance(endpoint, dict):
        return None
    component = (
        endpoint.get('compId')
        or endpoint.get('component')
        or endpoint.get('component_id')
        or endpoint.get('id')
    )
    port = endpoint.get('portId') or endpoint.get('port') or endpoint.get('pin') or endpoint.get('terminal')
    if component is None or port is None:
        return None
    return {'compId': str(component), 'portId': str(port)}


def _endpoint_component_id(endpoint: Any) -> str | None:
    normalized = _normalize_endpoint(endpoint)
    return normalized.get('compId') if normalized else None


def _endpoint_port_exists(component: dict[str, Any], port_id: str) -> bool:
    ports = component.get('ports')
    if not isinstance(ports, list) or not ports:
        return True
    known = {str(port.get('id')) if isinstance(port, dict) else str(port) for port in ports}
    return str(port_id) in known


def _canonical_endpoint_for_component(endpoint: dict[str, str], component: dict[str, Any]) -> dict[str, str]:
    port_id = str(endpoint['portId'])
    ctype = normalize_component_type(component.get('type'))
    if ctype == 'battery':
        aliases = {
            'positive': '+',
            'plus': '+',
            'pos': '+',
            'negative': '-',
            'minus': '-',
            'neg': '-',
        }
        port_id = aliases.get(port_id.lower(), port_id)
    elif ctype == 'ground' and port_id.lower() in {'gnd', 'ground', '0', '1'}:
        port_id = 'a'
    return {'compId': endpoint['compId'], 'portId': port_id}


def _connection_exists(state: dict[str, Any], source: dict[str, str], target: dict[str, str]) -> bool:
    return any(_same_connection(item, source, target) for item in state.get('connections') or [])


def _same_connection(connection: dict[str, Any], source: dict[str, str], target: dict[str, str]) -> bool:
    left = _normalize_endpoint(connection.get('from'))
    right = _normalize_endpoint(connection.get('to'))
    return (left == source and right == target) or (left == target and right == source)


def _next_component_id(state: dict[str, Any], component_type: str) -> str:
    prefix = ID_PREFIXES.get(component_type, 'X')
    used = {str(item.get('id')) for item in state.get('components') or [] if isinstance(item, dict)}
    for index in range(1, 10000):
        candidate = f'{prefix}{index}'
        if candidate not in used:
            return candidate
    raise ValueError('Unable to allocate component id.')


def _next_wire_id(state: dict[str, Any]) -> str:
    used = {
        str(item.get('id'))
        for item in state.get('connections') or []
        if isinstance(item, dict) and item.get('id') is not None
    }
    for index in range(1, 10000):
        candidate = f'W{index}'
        if candidate not in used:
            return candidate
    raise ValueError('Unable to allocate wire id.')


def _safe_id(value: Any) -> str:
    text = re.sub(r'[^0-9A-Za-z_.:-]+', '_', str(value or '').strip())
    return text or 'item'


def _normalize_ports(ports: Any) -> list[dict[str, str]]:
    if not isinstance(ports, list):
        ports = ['1', '2']
    normalized = []
    seen = set()
    for item in ports:
        port_id = item.get('id') if isinstance(item, dict) else item
        if port_id is None:
            continue
        port_id = str(port_id)
        if port_id in seen:
            continue
        seen.add(port_id)
        normalized.append({'id': port_id})
    return normalized or [{'id': '1'}]


def _normalize_waypoints(value: Any) -> list[dict[str, float]]:
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if not isinstance(item, dict):
            continue
        out.append({'x': _as_number(item.get('x'), 0), 'y': _as_number(item.get('y'), 0)})
    return out


def _as_number(value: Any, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number.is_integer():
        return int(number)
    return number


def _normalize_rotation(value: Any) -> int:
    return int(_as_number(value, 0)) % 360


def _mark_programmatic_metadata(state: dict[str, Any], report: dict[str, Any]) -> None:
    metadata = state.setdefault('metadata', {})
    if not isinstance(metadata, dict):
        metadata = {}
        state['metadata'] = metadata
    programmatic = metadata.setdefault('programmatic', {})
    if not isinstance(programmatic, dict):
        programmatic = {}
        metadata['programmatic'] = programmatic
    programmatic['last_applied_at'] = datetime.now(UTC).isoformat()
    programmatic['last_operation_count'] = report.get('applied_count', 0)
    programmatic['last_rejected_count'] = report.get('rejected_count', 0)


def _ok(operation: str, target: Any) -> dict[str, Any]:
    return {'ok': True, 'operation': operation, 'target': target}


def _reject(code: str, message: str) -> dict[str, Any]:
    return {'ok': False, 'code': code, 'message': message}
