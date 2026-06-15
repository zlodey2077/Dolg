import re
import xml.etree.ElementTree as ET

from .cad_parsers import parse_spice_component_line
from .project_review import normalize_component_type, parse_number

SPICE_TYPE_MAP = {
    'R': 'resistor',
    'C': 'capacitor',
    'L': 'inductor',
    'V': 'battery',
    'D': 'diode',
    'Q': 'transistor',
    'M': 'transistor',
    'U': 'ic',
    'X': 'ic',
}


def _clean_lines(source):
    text = (source or '').replace('\r\n', '\n').replace('\r', '\n')
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(('*', '#', ';')):
            continue
        yield line


def _is_directive(line, prefix=''):
    """Case-insensitive directive check.

    SPICE/LTspice are not case-sensitive (.TRAN ≡ .tran). The original code
    used ``line.startswith('.')`` for filtering (preserves case) and
    ``line.lower().startswith('.tran'...)`` for classification — which created
    a mismatch where ``.TRAN`` was filed under ``unsupported`` but ``.tran``
    landed in ``analysis_directives``. This helper unifies both paths.
    """
    if not isinstance(line, str):
        return False
    text = line.strip().lower()
    if not text.startswith('.'):
        return False
    if not prefix:
        return True
    return text.startswith(prefix.lower())


# Well-known SPICE/LTspice BJT models that the netlist exporter recognises
# without ``unsupported`` complaints. Anything else falls back to QNPN/QPNP but
# users get an explicit preview warning so the silent substitution is
# documented at import time.
_KNOWN_BJT_MODELS = {
    'qnpn',
    'qpnp',
    'q2n2222',
    'q2n2907',
    'q2n3904',
    'q2n3906',
    'qbc547',
    'qbc557',
    'd_npn',
    'd_pnp',
    'npn',
    'pnp',
}


def _spice_component_type(ref):
    first = (ref or '')[:1].upper()
    if ref.upper().startswith('LED'):
        return 'led'
    return SPICE_TYPE_MAP.get(first, 'ic')


def _value_field(component_type):
    return {
        'resistor': 'resistance',
        'capacitor': 'capacitance',
        'inductor': 'inductance',
        'battery': 'voltage',
    }.get(component_type, 'value')


def _node_component(node_name, x, y):
    if _is_ground(node_name):
        return {'id': 'gnd', 'type': 'ground', 'label': 'GND', 'x': x, 'y': y}
    safe = _safe_id(f'node_{node_name}')
    return {'id': safe, 'type': 'node', 'label': str(node_name), 'x': x, 'y': y}


def _safe_id(value):
    text = re.sub(r'[^0-9a-zA-Z_]+', '_', str(value or '').strip())
    return text or 'node'


def _is_ground(node_name):
    return str(node_name or '').strip().lower() in {'0', 'gnd', 'ground'}


def _connect_to_node(connections, ref, pin, node_id):
    connections.append(
        {
            'from': {'compId': ref, 'portId': str(pin)},
            'to': {'compId': node_id, 'portId': 'a'},
        }
    )


def _build_scheme(parsed_components, net_map, unsupported):
    components = []
    connections = []
    node_ids = {}

    for idx, node_name in enumerate(sorted(net_map.keys(), key=str)):
        node = _node_component(node_name, 120 + idx * 80, 320)
        node_ids[node_name] = node['id']
        if node['id'] not in {item.get('id') for item in components}:
            components.append(node)

    for idx, item in enumerate(parsed_components):
        ctype = normalize_component_type(item['type'])
        ref = _safe_id(item['ref'])
        component = {
            'id': ref,
            'type': ctype,
            'label': item['ref'],
            'x': 120 + (idx % 5) * 120,
            'y': 120 + (idx // 5) * 90,
        }
        value = item.get('value')
        if value:
            field = _value_field(ctype)
            component[field] = value
            component['value'] = value
            if ctype == 'ic':
                component['part_number'] = value
        components.append(component)

        for pin_index, node_name in enumerate(item.get('nodes', []), start=1):
            node_id = node_ids.get(node_name)
            if node_id:
                _connect_to_node(connections, ref, pin_index, node_id)

    return {
        'components': components,
        'connections': connections,
        'metadata': {
            'imported': True,
            'unsupported': unsupported,
        },
    }


def import_spice_netlist(source):
    parsed = []
    net_map = {}
    unsupported = []

    for line in _clean_lines(source):
        if _is_directive(line):
            unsupported.append(line)
            continue
        parsed_line = parse_spice_component_line(line)
        if not parsed_line.get('ok'):
            unsupported.append(line)
            continue
        parts = parsed_line['tokens']
        ref = parts[0]
        ctype = _spice_component_type(ref)
        if ctype == 'transistor':
            nodes = parts[1:4]
            value = parts[4] if len(parts) > 4 else ''
            # Surface unknown SPICE BJT models so the silent QNPN/QPNP
            # substitution at export time is visible in preview.
            if value and value.strip().lower() not in _KNOWN_BJT_MODELS:
                unsupported.append(
                    f'{ref}: неизвестная модель транзистора "{value}", будет использована модель QNPN/QPNP по умолчанию.'
                )
        elif ctype == 'ic':
            nodes = parts[1:-1]
            value = parts[-1] if len(parts) > 1 else ''
        else:
            nodes = parts[1:3]
            if ctype == 'battery' and len(parts) >= 5 and parts[3].upper() == 'DC':
                value = parts[4]
            else:
                value = parts[3]
        parsed.append({'ref': ref, 'type': ctype, 'nodes': nodes, 'value': value})
        for node in nodes:
            net_map.setdefault(node, []).append(ref)

    scheme = _build_scheme(parsed, net_map, unsupported)
    return {
        'ok': True,
        'format': 'spice',
        'scheme_data': scheme,
        'summary': {
            'components': len(parsed),
            'nets': len(net_map),
            'unsupported': len(unsupported),
        },
        'unsupported': unsupported,
    }


def _find_text(element, name):
    found = element.find(name)
    return found.text.strip() if found is not None and found.text else ''


def import_kicad_xml(source):
    parsed = []
    net_map = {}
    unsupported = []
    try:
        root = ET.fromstring(source or '')
    except ET.ParseError:
        return import_kicad_sexpr(source)

    comps = {}
    for comp in root.findall('.//comp'):
        ref = comp.attrib.get('ref') or _find_text(comp, 'ref')
        value = _find_text(comp, 'value')
        if not ref:
            continue
        ctype = _spice_component_type(ref)
        comps[ref] = {'ref': ref, 'type': ctype, 'nodes': [], 'value': value}

    for net in root.findall('.//net'):
        net_name = net.attrib.get('name') or net.attrib.get('code') or f'net_{len(net_map) + 1}'
        for node in net.findall('node'):
            ref = node.attrib.get('ref')
            if ref in comps:
                comps[ref]['nodes'].append(net_name)
                net_map.setdefault(net_name, []).append(ref)

    parsed = list(comps.values())
    scheme = _build_scheme(parsed, net_map, unsupported)
    return {
        'ok': True,
        'format': 'kicad_xml',
        'scheme_data': scheme,
        'summary': {
            'components': len(parsed),
            'nets': len(net_map),
            'unsupported': len(unsupported),
        },
        'unsupported': unsupported,
    }


_KICAD_LIB_ID = re.compile(r'\(lib_id\s+"([^"]+)"')
_KICAD_PROP = re.compile(r'\(property\s+"([^"]+)"\s+"([^"]*)"')


def import_kicad_sexpr(source):
    """Быстрый парсер KiCad-схем (формат sexpr, в т.ч. KiCad 8 `eeschema`).

    Старая реализация была одной regex с `.*?` и re.S по всему файлу — на схемах
    в сотни КБ это давало катастрофический бэктрекинг (секунды на файл) И не
    матчила инстансы KiCad 8 `(symbol (lib_id ...))`, давая 0 компонентов.

    Здесь — без посимвольного скана скобок (он на чистом Python стоил десятки мс
    на 178-КБ схему). Якорь = `(lib_id "…")`: он есть ТОЛЬКО у инстансов символов,
    а определения в `(lib_symbols …)` его не содержат — значит библиотека
    отсеивается даром. Между соседними lib_id C-level regex'ом берём Reference/
    Value этого инстанса. На реальном open-schematics: 0→десятки компонентов,
    секунды→единицы мс на файл.
    """
    text = source or ''
    parsed = []
    net_map = {}
    unsupported = []

    libids = list(_KICAD_LIB_ID.finditer(text))
    idx = 0
    for i, lib_match in enumerate(libids):
        lib_name = lib_match.group(1)
        # Тело инстанса — от его lib_id до начала следующего инстанса (или конца
        # файла). Reference/Value этого символа лежат здесь, до следующего lib_id.
        seg_start = lib_match.end()
        seg_end = libids[i + 1].start() if i + 1 < len(libids) else len(text)
        segment = text[seg_start:seg_end]
        ref = ''
        value = ''
        for prop_match in _KICAD_PROP.finditer(segment):
            key, val = prop_match.group(1), prop_match.group(2)
            if key == 'Reference':
                ref = val
            elif key == 'Value':
                value = val
            if ref and value:
                break
        if not ref:
            continue  # графика без Reference — не компонент
        # Power-порты (#PWR…) и ERC-флаги (#FLG…) — это якоря питания/земли, не
        # приборы. KiCad помечает их lib_id 'power:GND'/'power:+5V' и ссылкой #PWR.
        # Без спец-обработки _spice_component_type('#…') свалил бы их в 'ic' и
        # раздул статистику ИС — критичный шум для обучающего корпуса.
        if lib_name.startswith('power:') or ref.startswith('#FLG'):
            ctype = 'ground'
        elif ref.startswith('#PWR'):
            ctype = 'ground'
        else:
            short = lib_name.split(':')[-1]
            ctype = normalize_component_type(short)
            if ctype == short.lower():
                ctype = _spice_component_type(ref)
        idx += 1
        node = f'N{idx}'
        parsed.append({'ref': ref, 'type': ctype, 'nodes': [node], 'value': value})
        net_map.setdefault(node, []).append(ref)

    if not parsed:
        unsupported.append('Не удалось распознать ни одного компонента KiCad.')
    scheme = _build_scheme(parsed, net_map, unsupported)
    return {
        'ok': bool(parsed),
        'format': 'kicad_sexpr',
        'scheme_data': scheme,
        'summary': {
            'components': len(parsed),
            'nets': len(net_map),
            'unsupported': len(unsupported),
        },
        'unsupported': unsupported,
    }


def import_cad_text(format_name, source):
    fmt = str(format_name or '').strip().lower()
    if fmt in {'ltspice', 'spice', 'netlist', 'asc'}:
        return import_spice_netlist(source)
    if fmt in {'kicad', 'kicad_xml', 'xml', 'kicad_sch'}:
        return import_kicad_xml(source)
    return {
        'ok': False,
        'format': fmt,
        'scheme_data': {'components': [], 'connections': []},
        'summary': {'components': 0, 'nets': 0, 'unsupported': 1},
        'unsupported': [f'Неподдерживаемый CAD-формат: {fmt or "неизвестный"}'],
    }


def import_preview(format_name, source):
    result = import_cad_text(format_name, source)
    for component in result.get('scheme_data', {}).get('components', []):
        if component.get('type') == 'battery' and parse_number(component.get('voltage'), None) is None:
            component['voltage'] = 5
    result['preview'] = build_import_preview_details(result)
    return result


def _component_value(component):
    for key in ('value', 'resistance', 'capacitance', 'inductance', 'voltage', 'current', 'part_number'):
        value = component.get(key)
        if value not in (None, ''):
            return str(value)
    return ''


def build_import_preview_details(result):
    """Build a compact UI/API preview for imported CAD data.

    The importer returns internal ``scheme_data`` for downstream review. This
    helper extracts only user-facing facts: component list, net labels,
    unsupported statements and counts. Keeping this in the service layer lets
    CAD UI, demo checks and tests use the same interpretation.
    """
    scheme = result.get('scheme_data') or {}
    components = list(scheme.get('components') or [])
    connections = list(scheme.get('connections') or [])
    unsupported = list(result.get('unsupported') or [])

    electrical_components = []
    nodes = []
    grounds = 0
    type_counts = {}
    for item in components:
        comp_type = normalize_component_type(item.get('type') or '')
        label = item.get('label') or item.get('ref') or item.get('id') or comp_type
        if comp_type == 'node':
            nodes.append(str(label))
            continue
        if comp_type == 'ground':
            grounds += 1
            nodes.append('GND')
            type_counts[comp_type] = type_counts.get(comp_type, 0) + 1
            continue
        type_counts[comp_type] = type_counts.get(comp_type, 0) + 1
        electrical_components.append(
            {
                'id': item.get('id'),
                'ref': label,
                'type': comp_type,
                'value': _component_value(item),
                'catalog_ref': item.get('catalog_ref') or item.get('part_number') or '',
            }
        )

    unique_nodes = []
    for node in nodes:
        if node and node not in unique_nodes:
            unique_nodes.append(node)

    analysis_directives = [
        line
        for line in unsupported
        if any(_is_directive(line, prefix) for prefix in ('.ac', '.tran', '.op', '.dc'))
    ]
    unsupported_elements = [line for line in unsupported if line not in analysis_directives]

    warnings = []
    if not grounds:
        warnings.append('В импортированной схеме не найдена ссылка GND.')
    if unsupported_elements:
        warnings.append('Часть элементов CAD/SPICE не поддерживается текущим импортёром.')
    if analysis_directives:
        warnings.append(
            'Директивы анализа сохранены как предупреждения; запустите симуляцию DOLG после сохранения.'
        )

    return {
        'components': electrical_components,
        'component_count': len(electrical_components),
        'connection_count': len(connections),
        'nodes': unique_nodes,
        'node_count': len(unique_nodes),
        'type_counts': type_counts,
        'unsupported': unsupported_elements,
        'analysis_directives': analysis_directives,
        'warnings': warnings,
        'can_save_project': bool(result.get('ok') and electrical_components),
    }
