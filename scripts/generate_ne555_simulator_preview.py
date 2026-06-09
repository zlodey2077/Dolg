from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUT_DIR = Path('docs/final/generated')
EXTERNAL_SVG = OUT_DIR / 'ne555_internal_astable_preview.svg'
EXTERNAL_PNG = OUT_DIR / 'ne555_internal_astable_simulator_preview.png'
INTERNAL_SVG = OUT_DIR / 'ne555_internal_block_preview.svg'
INTERNAL_PNG = OUT_DIR / 'ne555_internal_block_preview.png'

W = 1500
H = 900

BLACK = '#101010'
WIRE = '#161616'
VCC = '#123f91'
GND = '#157347'
FILL = '#f7fbff'
IC_FILL = '#fffdf4'
BLOCK_FILL = '#fff7e6'
NOTE_FILL = '#f8fafc'


def font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    names = ['arialbd.ttf', 'arial.ttf'] if bold else ['arial.ttf', 'segoeui.ttf']
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def esc(text: object) -> str:
    return (
        str(text)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
    )


class Canvas:
    def __init__(self, title: str, subtitle: str) -> None:
        self.image = Image.new('RGB', (W, H), 'white')
        self.draw = ImageDraw.Draw(self.image)
        self.svg = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
            '<rect width="100%" height="100%" fill="#ffffff"/>',
        ]
        self.text(42, 34, title, 22, bold=True)
        self.text(43, 64, subtitle, 13, fill='#555555')

    def save(self, svg_path: Path, png_path: Path) -> None:
        self.svg.append('</svg>')
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        svg_path.write_text('\n'.join(self.svg) + '\n', encoding='utf-8')
        self.image.save(png_path)

    def line(self, x1: int, y1: int, x2: int, y2: int, color: str = WIRE, width: int = 2) -> None:
        self.draw.line((x1, y1, x2, y2), fill=color, width=width)
        self.svg.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}" stroke-linecap="round"/>'
        )

    def poly(self, points: list[tuple[int, int]], color: str = WIRE, width: int = 2) -> None:
        if len(points) < 2:
            return
        self.draw.line(points, fill=color, width=width, joint='curve')
        pts = ' '.join(f'{x},{y}' for x, y in points)
        self.svg.append(
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>'
        )

    def rect(self, x: int, y: int, w: int, h: int, fill: str = 'white', outline: str = BLACK, width: int = 2, radius: int = 5) -> None:
        self.draw.rounded_rectangle((x, y, x + w, y + h), radius=radius, fill=fill, outline=outline, width=width)
        self.svg.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{outline}" stroke-width="{width}"/>'
        )

    def text(self, x: int, y: int, value: str, size: int = 12, fill: str = BLACK, anchor: str = 'start', bold: bool = False) -> None:
        fnt = font(size, bold=bold)
        px = x
        py = y
        if anchor in {'middle', 'center'}:
            box = self.draw.textbbox((0, 0), value, font=fnt)
            px = int(x - (box[2] - box[0]) / 2)
        if anchor == 'center':
            box = self.draw.textbbox((0, 0), value, font=fnt)
            py = int(y - (box[3] - box[1]) / 2)
        self.draw.text((px, py), value, fill=fill, font=fnt)
        svg_anchor = 'middle' if anchor in {'middle', 'center'} else 'start'
        weight = '700' if bold else '400'
        baseline = 'middle' if anchor == 'center' else 'auto'
        self.svg.append(
            f'<text x="{x if svg_anchor == "middle" else px}" y="{y if anchor == "center" else py}" '
            f'fill="{fill}" font-family="Arial, sans-serif" font-size="{size}" font-weight="{weight}" '
            f'text-anchor="{svg_anchor}" dominant-baseline="{baseline}">{esc(value)}</text>'
        )

    def node(self, x: int, y: int, color: str = BLACK, r: int = 4) -> None:
        self.draw.ellipse((x - r, y - r, x + r, y + r), fill=color, outline=color)
        self.svg.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}" stroke="{color}"/>')

    def open_node(self, x: int, y: int, label: str = '') -> None:
        self.draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill='white', outline=BLACK, width=2)
        self.svg.append(f'<circle cx="{x}" cy="{y}" r="6" fill="white" stroke="{BLACK}" stroke-width="2"/>')
        if label:
            self.text(x + 10, y - 8, label, 13, bold=True)

    def ground(self, x: int, y: int, label: str = '') -> None:
        self.line(x - 18, y, x + 18, y, GND)
        self.line(x - 12, y + 7, x + 12, y + 7, GND)
        self.line(x - 6, y + 14, x + 6, y + 14, GND)
        if label:
            self.text(x + 24, y - 4, label, 11, GND)

    def resistor_h(self, x1: int, y: int, x2: int, label: str, value: str) -> None:
        cx = (x1 + x2) // 2
        self.line(x1, y, cx - 34, y)
        self.line(cx + 34, y, x2, y)
        self.rect(cx - 34, y - 17, 68, 34, FILL, width=2)
        self.text(cx, y - 12, label, 11, anchor='middle', bold=True)
        self.text(cx, y + 2, value, 9, anchor='middle')

    def resistor_v(self, x: int, y1: int, y2: int, label: str, value: str, variable: bool = False) -> None:
        cy = (y1 + y2) // 2
        self.line(x, y1, x, cy - 34)
        self.line(x, cy + 34, x, y2)
        self.rect(x - 34, cy - 34, 68, 68, FILL, width=2)
        self.text(x, cy - 12, label, 11, anchor='middle', bold=True)
        self.text(x, cy + 4, value, 9, anchor='middle')
        if variable:
            self.line(x - 48, cy + 35, x + 45, cy - 35, width=2)
            self.line(x + 45, cy - 35, x + 37, cy - 17, width=2)
            self.line(x + 45, cy - 35, x + 26, cy - 34, width=2)

    def capacitor_v(self, x: int, y1: int, y2: int, label: str, value: str) -> None:
        cy = (y1 + y2) // 2
        self.line(x, y1, x, cy - 18)
        self.line(x, cy + 18, x, y2)
        self.line(x - 20, cy - 8, x + 20, cy - 8, width=3)
        self.line(x - 20, cy + 8, x + 20, cy + 8, width=3)
        self.text(x + 28, cy - 18, label, 11, bold=True)
        self.text(x + 28, cy - 2, value, 10)

    def switch_to_ground(self, node_x: int, node_y: int, x: int, gnd_y: int, label: str) -> None:
        self.poly([(node_x, node_y), (x + 40, node_y)])
        self.line(x + 40, node_y, x + 15, node_y + 30)
        self.line(x - 15, node_y + 38, x - 45, node_y + 38)
        self.line(x - 45, node_y + 38, x - 45, gnd_y, GND)
        self.node(x - 45, gnd_y, GND)
        self.text(x - 62, node_y + 15, label, 12, bold=True)

    def led_v(self, x: int, y1: int, y2: int, label: str) -> None:
        cy = (y1 + y2) // 2
        self.line(x, y1, x, cy - 22)
        self.line(x, cy + 22, x, y2)
        points = [(x - 16, cy - 18), (x + 16, cy - 18), (x, cy + 14)]
        self.draw.polygon(points, outline=BLACK)
        self.svg.append(f'<polygon points="{x-16},{cy-18} {x+16},{cy-18} {x},{cy+14}" fill="white" stroke="{BLACK}" stroke-width="2"/>')
        self.line(x - 18, cy + 16, x + 18, cy + 16)
        self.line(x + 22, cy - 23, x + 38, cy - 39, width=1)
        self.line(x + 27, cy - 8, x + 43, cy - 24, width=1)
        self.text(x + 48, cy - 16, label, 11, bold=True)

    def npn(self, x: int, y: int, label: str) -> dict[str, tuple[int, int]]:
        r = 40
        self.draw.ellipse((x - r, y - r, x + r, y + r), fill='white', outline=BLACK, width=2)
        self.svg.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="white" stroke="{BLACK}" stroke-width="2"/>')
        self.line(x - 62, y, x - 14, y)
        self.line(x - 14, y, x + 18, y - 25)
        self.line(x - 14, y, x + 18, y + 25)
        self.line(x + 18, y - 25, x + 18, y - 72)
        self.line(x + 18, y + 25, x + 18, y + 72)
        self.line(x + 9, y + 12, x + 22, y + 26)
        self.text(x - 36, y + 50, label, 11, bold=True)
        return {'base': (x - 62, y), 'collector': (x + 18, y - 72), 'emitter': (x + 18, y + 72)}

    def block(self, x: int, y: int, w: int, h: int, title: str, subtitle: str = '') -> None:
        self.rect(x, y, w, h, BLOCK_FILL, width=2, radius=5)
        self.text(x + w // 2, y + 18, title, 12, anchor='middle', bold=True)
        if subtitle:
            self.text(x + w // 2, y + 36, subtitle, 10, anchor='middle')


def draw_external() -> None:
    c = Canvas(
        'NE555 astable/load schematic - simulator target view',
        'External sheet: NE555 is a subcircuit symbol; pins, rails and parts are explicit and orthogonal.',
    )
    rail_y = 105
    gnd_y = 765
    c.line(70, rail_y, 1430, rail_y, VCC, 3)
    c.text(78, rail_y - 24, 'VCC 9-12V', 13, VCC, bold=True)
    c.line(70, gnd_y, 1430, gnd_y, GND, 3)
    c.text(78, gnd_y + 12, 'GND', 13, GND, bold=True)

    # NE555 symbol.
    ix, iy, iw, ih = 620, 245, 280, 360
    c.rect(ix, iy, iw, ih, IC_FILL, width=3, radius=8)
    c.text(ix + iw // 2, iy + 42, 'NE555', 24, anchor='middle', bold=True)
    c.text(ix + iw // 2, iy + 72, 'subcircuit', 12, anchor='middle', fill='#555555')
    pins = {
        '2': (ix, 335),
        '6': (ix, 420),
        '7': (ix, 495),
        '4': (710, iy),
        '8': (810, iy),
        '1': (760, iy + ih),
        '3': (ix + iw, 335),
        '5': (ix + iw, 485),
    }
    for num, name in [('2', 'TRIG'), ('6', 'THR'), ('7', 'DISCH')]:
        x, y = pins[num]
        c.node(x, y)
        c.text(x + 10, y - 8, f'{num} {name}', 12)
    for num, name in [('3', 'OUT'), ('5', 'CTRL')]:
        x, y = pins[num]
        c.node(x, y)
        c.text(x - 8, y - 8, f'{num} {name}', 12, anchor='middle')
    for num, name in [('4', 'RESET'), ('8', 'VCC')]:
        x, y = pins[num]
        c.node(x, y)
        c.text(x - 25, y + 12, f'{num} {name}', 12)
    x, y = pins['1']
    c.node(x, y)
    c.text(x - 26, y - 26, '1 GND', 12)

    # Supply pins.
    c.poly([(pins['4'][0], rail_y), pins['4']], VCC, 2)
    c.poly([(pins['8'][0], rail_y), pins['8']], VCC, 2)
    c.node(pins['4'][0], rail_y, VCC)
    c.node(pins['8'][0], rail_y, VCC)
    c.poly([pins['1'], (pins['1'][0], gnd_y)], GND, 2)
    c.node(pins['1'][0], gnd_y, GND)

    # Left trigger/timing networks.
    trig = (270, 335)
    timing = (430, 420)
    c.resistor_v(trig[0], rail_y, trig[1], 'R2', '100k')
    c.node(trig[0], rail_y, VCC)
    c.node(*trig)
    c.poly([trig, (560, trig[1]), pins['2']])
    c.switch_to_ground(trig[0], trig[1], 185, gnd_y, 'S1')

    c.resistor_v(timing[0], rail_y, timing[1], 'R1', '5M', variable=True)
    c.node(timing[0], rail_y, VCC)
    c.node(*timing)
    c.capacitor_v(timing[0], timing[1], gnd_y, 'C1', '47uF')
    c.node(timing[0], gnd_y, GND)
    c.poly([timing, (555, timing[1]), pins['6']])
    c.poly([timing, (500, timing[1]), (500, pins['7'][1]), pins['7']])
    c.text(timing[0] + 18, timing[1] - 18, 'timing node', 11, '#555555')
    c.text(trig[0] + 18, trig[1] - 18, 'trigger node', 11, '#555555')

    # Control pin.
    c.poly([pins['5'], (970, pins['5'][1]), (970, 565)])
    c.capacitor_v(970, 565, gnd_y, 'C2', '10nF')
    c.node(970, gnd_y, GND)

    # Output load.
    out_node = (980, pins['3'][1])
    c.poly([pins['3'], out_node])
    c.node(*out_node)
    c.open_node(out_node[0], out_node[1] - 45, 'OUT')
    c.line(out_node[0], out_node[1] - 39, out_node[0], out_node[1])
    c.resistor_h(out_node[0], out_node[1], 1110, 'R3', '1k')
    q = c.npn(1210, 455, 'T1 NPN')
    c.poly([(1110, out_node[1]), (1148, out_node[1]), (1148, q['base'][1]), q['base']])
    c.poly([q['emitter'], (q['emitter'][0], gnd_y)], GND)
    c.node(q['emitter'][0], gnd_y, GND)
    collector_bus = (q['collector'][0], 305)
    c.poly([q['collector'], collector_bus])
    c.node(*collector_bus)
    c.led_v(collector_bus[0], rail_y, 205, 'LED1')
    c.resistor_v(collector_bus[0], 205, collector_bus[1], 'R4', '1.5k')
    c.node(collector_bus[0], rail_y, VCC)

    # Decoupling and connector.
    c.capacitor_v(1340, rail_y, gnd_y, 'C3', '100nF')
    c.node(1340, rail_y, VCC)
    c.node(1340, gnd_y, GND)
    c.capacitor_v(1420, rail_y, gnd_y, 'C4', '100uF')
    c.node(1420, rail_y, VCC)
    c.node(1420, gnd_y, GND)
    c.rect(1272, 48, 86, 48, '#eaf8ef', width=2)
    c.text(1315, 64, 'POWER', 11, anchor='middle', bold=True)
    c.text(1315, 80, '9-12V', 10, anchor='middle')
    c.poly([(1272, 72), (1228, 72), (1228, rail_y)], VCC)
    c.node(1228, rail_y, VCC)

    c.rect(42, 812, 640, 50, NOTE_FILL, '#cbd5e1', 1)
    c.text(58, 826, 'Correct construction rule:', 12, bold=True)
    c.text(58, 845, 'external schematic uses the NE555 subcircuit symbol; internal structure belongs on a separate sheet with matching ports 1-8.', 11, '#444444')
    c.ground(1180, 780, 'main ground')
    c.save(EXTERNAL_SVG, EXTERNAL_PNG)


def draw_internal() -> None:
    c = Canvas(
        'NE555 internal functional subcircuit - pins 1-8',
        'Internal sheet: functional 555 model with divider, comparators, SR latch, discharge transistor and output driver.',
    )
    rail_y = 105
    gnd_y = 770
    c.line(90, rail_y, 1410, rail_y, VCC, 3)
    c.text(100, rail_y - 24, 'VCC / pin 8', 13, VCC, bold=True)
    c.line(90, gnd_y, 1410, gnd_y, GND, 3)
    c.text(100, gnd_y + 12, 'GND / pin 1', 13, GND, bold=True)

    # Ports.
    ports = {
        '6 THR': (110, 295),
        '2 TRIG': (110, 430),
        '5 CTRL': (110, 240),
        '4 RESET': (110, 560),
        '7 DISCH': (1390, 560),
        '3 OUT': (1390, 400),
    }
    for label, (x, y) in ports.items():
        c.open_node(x, y, label)

    # Divider.
    div_x = 365
    c.resistor_v(div_x, rail_y, 260, 'R', '5k')
    c.resistor_v(div_x, 260, 420, 'R', '5k')
    c.resistor_v(div_x, 420, gnd_y, 'R', '5k')
    hi = (div_x, 260)
    lo = (div_x, 420)
    c.node(*hi)
    c.node(*lo)
    c.text(div_x + 22, hi[1] - 14, '2/3 VCC', 12, '#555555')
    c.text(div_x + 22, lo[1] - 14, '1/3 VCC', 12, '#555555')
    c.poly([ports['5 CTRL'], (260, ports['5 CTRL'][1]), (260, hi[1]), hi])

    # Comparators.
    c.block(560, 245, 150, 78, 'Threshold', 'comparator')
    c.text(548, 274, '+', 16, bold=True)
    c.text(548, 304, '-', 16, bold=True)
    c.block(560, 392, 150, 78, 'Trigger', 'comparator')
    c.text(548, 421, '+', 16, bold=True)
    c.text(548, 451, '-', 16, bold=True)
    c.poly([ports['6 THR'], (505, ports['6 THR'][1]), (505, 274), (560, 274)])
    c.poly([hi, (500, hi[1]), (500, 304), (560, 304)])
    c.poly([lo, (500, lo[1]), (500, 421), (560, 421)])
    c.poly([ports['2 TRIG'], (505, ports['2 TRIG'][1]), (505, 451), (560, 451)])

    # Latch/reset/output.
    c.block(825, 330, 130, 105, 'SR latch', 'set/reset memory')
    c.text(812, 360, 'R', 13, bold=True)
    c.text(812, 412, 'S', 13, bold=True)
    c.poly([(710, 284), (770, 284), (770, 360), (825, 360)])
    c.poly([(710, 431), (770, 431), (770, 412), (825, 412)])
    c.poly([ports['4 RESET'], (760, ports['4 RESET'][1]), (760, 392), (825, 392)])

    c.block(1070, 345, 150, 92, 'Output', 'push-pull driver')
    c.poly([(955, 382), (1070, 382)])
    c.poly([(1220, 392), ports['3 OUT']])
    c.poly([(1120, rail_y), (1120, 345)], VCC)
    c.node(1120, rail_y, VCC)
    c.poly([(1120, 437), (1120, gnd_y)], GND)
    c.node(1120, gnd_y, GND)

    q = c.npn(1070, 590, 'discharge NPN')
    c.poly([(955, 415), (1010, 415), (1010, q['base'][1]), q['base']])
    c.poly([ports['7 DISCH'], (1230, ports['7 DISCH'][1]), (1230, q['collector'][1]), q['collector']])
    c.poly([q['emitter'], (q['emitter'][0], gnd_y)], GND)
    c.node(q['emitter'][0], gnd_y, GND)

    c.rect(42, 812, 720, 50, NOTE_FILL, '#cbd5e1', 1)
    c.text(58, 826, 'Functional abstraction:', 12, bold=True)
    c.text(58, 845, 'this is the readable subcircuit a simulator/editor should expand from the NE555 symbol, not a literal chip-die schematic.', 11, '#444444')
    c.ground(1160, 785, 'pin 1 reference')
    c.save(INTERNAL_SVG, INTERNAL_PNG)


def main() -> None:
    draw_external()
    draw_internal()
    print(EXTERNAL_SVG)
    print(EXTERNAL_PNG)
    print(INTERNAL_SVG)
    print(INTERNAL_PNG)


if __name__ == '__main__':
    main()
