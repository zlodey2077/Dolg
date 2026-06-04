"""Schemdraw-backed SVG snippets for learning and review reports."""

from __future__ import annotations


def _schemdraw():
    import schemdraw
    import schemdraw.elements as elm

    return schemdraw, elm


def _svg_from_drawing(drawing):
    return drawing._repr_svg_()


def render_training_circuit(kind, params=None):
    params = params or {}
    schemdraw, elm = _schemdraw()
    drawing = schemdraw.Drawing(file=None)
    drawing.config(unit=2.2)

    if kind == 'led_indicator':
        drawing += elm.SourceV().up().label(str(params.get('vin', 'Vcc')))
        drawing += elm.Resistor().right().label(str(params.get('resistor', 'R')))
        drawing += elm.LED().down().label('LED')
        drawing += elm.Line().left()
        drawing += elm.Ground()
        return _svg_from_drawing(drawing)

    if kind == 'voltage_divider':
        drawing += elm.SourceV().up().label(str(params.get('vin', 'Vin')))
        drawing += elm.Resistor().right().label(str(params.get('r1', 'R1')))
        drawing += elm.Dot(open=True).label('Vout', loc='right')
        drawing += elm.Resistor().down().label(str(params.get('r2', 'R2')))
        drawing += elm.Line().left()
        drawing += elm.Ground()
        return _svg_from_drawing(drawing)

    if kind == 'rc_filter':
        drawing += elm.SourceV().up().label(str(params.get('vin', 'Vin')))
        drawing += elm.Resistor().right().label(str(params.get('resistor', 'R')))
        drawing += elm.Dot(open=True).label('Vout', loc='right')
        drawing += elm.Capacitor().down().label(str(params.get('capacitor', 'C')))
        drawing += elm.Line().left()
        drawing += elm.Ground()
        return _svg_from_drawing(drawing)

    if kind == 'transistor_switch':
        drawing += elm.SourceV().up().label(str(params.get('vcc', 'Vcc')))
        drawing += elm.Resistor().right().label(str(params.get('load', 'Load')))
        drawing += elm.BjtNpn().down().label('NPN')
        drawing += elm.Ground()
        drawing += elm.Line().at((1.2, 1.2)).left()
        drawing += elm.Resistor().left().label(str(params.get('base', 'Rb')))
        return _svg_from_drawing(drawing)

    if kind == 'ne555_astable':
        drawing += elm.Ic(
            pins=[
                elm.IcPin(name='GND', pin='1', side='left'),
                elm.IcPin(name='TRIG', pin='2', side='left'),
                elm.IcPin(name='OUT', pin='3', side='right'),
                elm.IcPin(name='VCC', pin='8', side='right'),
            ],
            label='NE555',
        )
        drawing += elm.Capacitor().down().label(str(params.get('capacitor', 'C')))
        drawing += elm.Ground()
        return _svg_from_drawing(drawing)

    raise ValueError(f'Unknown circuit SVG kind: {kind}')


# Маппинг идентификаторов топологии из ProjectReview (`connectivity.topology`)
# к доступным kind-ам ``render_training_circuit``. Возвращает SVG-строку или
# None, если детектор не распознал топологию (тогда review-страница
# отобразит текстовый fallback и кнопку «Открыть в симуляторе»).
_TOPOLOGY_THUMBNAIL_MAP = {
    'voltage_divider': 'voltage_divider',
    'rc_network': 'rc_filter',
    'led_indicator': 'led_indicator',
}


def thumbnail_for_topology(topology, params=None):
    """Render a tidy SVG thumbnail for a detected schematic topology.

    Used by ProjectReview HTML/PDF to show a schematic preview in the hero
    card instead of a raw text dump of components. Returns None for unknown
    topologies — caller decides whether to show a placeholder.
    """
    kind = _TOPOLOGY_THUMBNAIL_MAP.get(str(topology or '').strip().lower())
    if not kind:
        return None
    try:
        return render_training_circuit(kind, params or {})
    except Exception:
        # Schemdraw failures are non-fatal for the review report.
        return None
