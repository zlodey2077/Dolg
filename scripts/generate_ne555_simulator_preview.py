from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUT_DIR = Path('docs/final/generated')
SVG_PATH = OUT_DIR / 'ne555_internal_astable_preview.svg'
PNG_PATH = OUT_DIR / 'ne555_internal_astable_simulator_preview.png'

WIDTH = 1500
HEIGHT = 900

BLACK = '#111111'
WIRE = '#202020'
RAIL = '#0f3f8f'
GROUND = '#157347'
INNER = '#6b7280'
BLUE_FILL = '#eaf4ff'
CREAM_FILL = '#fff7e6'
GREEN_FILL = '#eaf8ef'
RED_FILL = '#fff0f0'


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    names = ['arialbd.ttf', 'arial.ttf'] if bold else ['arial.ttf', 'segoeui.ttf']
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


class Diagram:
    def __init__(self) -> None:
        self.image = Image.new('RGB', (WIDTH, HEIGHT), 'white')
        self.draw = ImageDraw.Draw(self.image)
        self.svg: list[str] = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
            '<rect width="100%" height="100%" fill="#ffffff"/>',
        ]
        self.fonts = {
            10: _font(10),
            11: _font(11),
            12: _font(12),
            13: _font(13),
            14: _font(14),
            16: _font(16),
            18: _font(18),
            22: _font(22, bold=True),
        }

    def save(self) -> None:
        self.svg.append('</svg>')
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        SVG_PATH.write_text('\n'.join(self.svg) + '\n', encoding='utf-8')
        self.image.save(PNG_PATH)

    def line(self, x1, y1, x2, y2, color=WIRE, width=2) -> None:
        self.draw.line((x1, y1, x2, y2), fill=color, width=width)
        self.svg.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}" stroke-linecap="round"/>'
        )

    def polyline(self, points, color=WIRE, width=2) -> None:
        if len(points) < 2:
            return
        self.draw.line(points, fill=color, width=width, joint='curve')
        pts = ' '.join(f'{x},{y}' for x, y in points)
        self.svg.append(
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>'
        )

    def rect(self, x, y, w, h, fill='white', outline=BLACK, width=2, radius=6) -> None:
        raster_width = max(1, int(round(width)))
        self.draw.rounded_rectangle((x, y, x + w, y + h), radius=radius, fill=fill, outline=outline, width=raster_width)
        self.svg.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{outline}" stroke-width="{width}"/>'
        )

    def circle(self, x, y, r=4, fill=BLACK, outline=None, width=1) -> None:
        self.draw.ellipse((x - r, y - r, x + r, y + r), fill=fill, outline=outline or fill, width=width)
        self.svg.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{outline or fill}" stroke-width="{width}"/>')

    def text(self, x, y, value, size=12, fill=BLACK, anchor=None, bold=False) -> None:
        font = _font(size, bold=bold) if size not in self.fonts or bold else self.fonts[size]
        if anchor == 'middle':
            bbox = self.draw.textbbox((0, 0), value, font=font)
            x -= (bbox[2] - bbox[0]) / 2
        if anchor == 'center':
            bbox = self.draw.textbbox((0, 0), value, font=font)
            x -= (bbox[2] - bbox[0]) / 2
            y -= (bbox[3] - bbox[1]) / 2
        self.draw.text((x, y), value, fill=fill, font=font)
        svg_anchor = 'middle' if anchor in {'middle', 'center'} else 'start'
        dy = '0.35em' if anchor == 'center' else '0'
        weight = '700' if bold else '400'
        self.svg.append(
            f'<text x="{x if svg_anchor == "start" else round(x, 2)}" y="{y}" fill="{fill}" font-family="Arial, sans-serif" '
            f'font-size="{size}" font-weight="{weight}" text-anchor="{svg_anchor}" dominant-baseline="{dy}">{escape(value)}</text>'
        )

    def label_box(self, x, y, w, h, title, subtitle='', fill=BLUE_FILL) -> None:
        self.rect(x, y, w, h, fill=fill, outline=BLACK, width=1.6, radius=4)
        self.text(x + w / 2, y + 14, title, size=11, anchor='middle', bold=True)
        if subtitle:
            self.text(x + w / 2, y + 29, subtitle, size=10, anchor='middle')

    def resistor(self, x, y, w, h, title, value='', fill=BLUE_FILL) -> tuple[int, int]:
        self.label_box(x, y, w, h, title, value, fill=fill)
        return x + w // 2, y + h // 2

    def cap_vertical(self, x, top, bottom, label, value='') -> tuple[int, int]:
        mid = (top + bottom) // 2
        self.line(x, top, x, mid - 18)
        self.line(x, mid + 18, x, bottom)
        self.line(x - 18, mid - 8, x + 18, mid - 8, width=3)
        self.line(x - 18, mid + 8, x + 18, mid + 8, width=3)
        self.text(x + 22, mid - 20, label, size=11, bold=True)
        self.text(x + 22, mid - 5, value, size=10)
        return x, mid

    def ground_symbol(self, x, y, label='GND') -> None:
        self.line(x - 18, y, x + 18, y, color=GROUND)
        self.line(x - 12, y + 7, x + 12, y + 7, color=GROUND)
        self.line(x - 6, y + 14, x + 6, y + 14, color=GROUND)
        self.text(x + 24, y - 4, label, size=11, fill=GROUND)

    def led(self, x, y, label='LED1') -> None:
        self.line(x, y - 30, x, y - 14)
        self.line(x, y + 18, x, y + 34)
        self.svg.append(f'<polygon points="{x-14},{y-14} {x+14},{y-14} {x},{y+12}" fill="none" stroke="{BLACK}" stroke-width="2"/>')
        self.draw.polygon([(x - 14, y - 14), (x + 14, y - 14), (x, y + 12)], outline=BLACK)
        self.line(x - 16, y + 14, x + 16, y + 14)
        self.line(x + 18, y - 16, x + 30, y - 28, width=1)
        self.line(x + 23, y - 4, x + 35, y - 16, width=1)
        self.text(x + 38, y - 20, label, size=11, bold=True)

    def npn(self, x, y, label) -> None:
        self.circle(x, y, 38, fill='white', outline=BLACK, width=2)
        self.line(x - 58, y, x - 12, y)
        self.line(x - 12, y, x + 18, y - 24)
        self.line(x - 12, y, x + 18, y + 24)
        self.line(x + 18, y - 24, x + 18, y - 62)
        self.line(x + 18, y + 24, x + 18, y + 62)
        self.line(x + 12, y + 12, x + 24, y + 24)
        self.text(x - 31, y + 47, label, size=11, bold=True)

    def pin(self, x, y, label, side) -> None:
        self.circle(x, y, 3)
        if side == 'left':
            self.text(x + 8, y - 7, label, size=11)
        elif side == 'right':
            self.text(x - 8, y - 7, label, size=11, anchor='middle')
        elif side == 'top':
            self.text(x - 18, y + 10, label, size=11)
        else:
            self.text(x - 18, y - 22, label, size=11)


def escape(value: str) -> str:
    return (
        str(value)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
    )


def draw_ne555() -> None:
    d = Diagram()
    d.text(42, 34, 'NE555 simulator-style schematic: internal functional blocks + external astable/load network', 22, bold=True)
    d.text(43, 62, 'Orthogonal rails/wires; functional internal model, not a die-level transistor netlist.', 13, fill='#555555')

    # Rails.
    d.line(70, 95, 1430, 95, color=RAIL, width=3)
    d.text(78, 72, 'VCC 9-12V', 13, fill=RAIL, bold=True)
    d.line(70, 765, 1430, 765, color=GROUND, width=3)
    d.text(80, 775, 'GND', 13, fill=GROUND, bold=True)
    d.ground_symbol(1180, 780, 'main ground')
    d.label_box(1340, 58, 86, 48, 'POWER', '9-12V', fill=GREEN_FILL)
    d.line(1340, 82, 1290, 82, color=RAIL)
    d.line(1290, 82, 1290, 95, color=RAIL)
    d.line(1383, 106, 1383, 765, color=GROUND)
    d.circle(1290, 95, fill=RAIL)
    d.circle(1383, 765, fill=GROUND)

    # External timing network.
    d.resistor(115, 137, 74, 34, 'R2', '100k')
    d.line(152, 95, 152, 137, color=RAIL)
    d.circle(152, 95, fill=RAIL)
    d.line(152, 171, 152, 315)
    d.circle(152, 315)
    d.resistor(252, 137, 78, 34, 'R1', '5M pot')
    d.line(291, 95, 291, 137, color=RAIL)
    d.circle(291, 95, fill=RAIL)
    d.line(291, 171, 291, 250)
    d.circle(291, 250)
    d.line(291, 250, 340, 250)
    d.line(340, 250, 340, 372)
    d.circle(340, 372)
    d.line(291, 250, 291, 372)
    d.line(291, 372, 340, 372)
    d.cap_vertical(270, 498, 765, 'C1', '47uF')
    d.line(270, 498, 270, 372)
    d.line(270, 372, 340, 372)
    d.line(270, 765, 270, 765, color=GROUND)
    d.circle(270, 765, fill=GROUND)
    d.label_box(105, 438, 82, 42, 'S1', 'trigger', fill=GREEN_FILL)
    d.line(146, 480, 146, 765, color=GROUND)
    d.line(187, 459, 340, 459)
    d.line(340, 459, 340, 372)
    d.circle(146, 765, fill=GROUND)
    d.text(350, 366, 'TIMING node', 11, fill='#555555')
    d.text(348, 244, 'DISCH node', 11, fill='#555555')

    # NE555 package and pins.
    ic_x, ic_y, ic_w, ic_h = 520, 178, 410, 455
    d.rect(ic_x, ic_y, ic_w, ic_h, fill='#fffdf7', outline=BLACK, width=2.4, radius=8)
    d.text(ic_x + ic_w / 2, ic_y + 22, 'NE555 internal functional model', 18, anchor='middle', bold=True)

    pins = {
        'P6': (ic_x, 282),
        'P2': (ic_x, 372),
        'P7': (ic_x, 464),
        'P4': (645, ic_y),
        'P8': (780, ic_y),
        'P1': (690, ic_y + ic_h),
        'P3': (ic_x + ic_w, 372),
        'P5': (ic_x + ic_w, 500),
    }
    d.pin(*pins['P6'], '6 THR', 'left')
    d.pin(*pins['P2'], '2 TRIG', 'left')
    d.pin(*pins['P7'], '7 DISCH', 'left')
    d.pin(*pins['P4'], '4 RESET', 'top')
    d.pin(*pins['P8'], '8 VCC', 'top')
    d.pin(*pins['P1'], '1 GND', 'bottom')
    d.pin(*pins['P3'], '3 OUT', 'right')
    d.pin(*pins['P5'], '5 CTRL', 'right')

    # External to pins.
    d.polyline([(340, 372), (455, 372), (455, pins['P2'][1]), pins['P2']])
    d.polyline([(340, 372), (455, 372), (455, pins['P6'][1]), pins['P6']])
    d.polyline([(340, 250), (430, 250), (430, pins['P7'][1]), pins['P7']])
    d.polyline([(645, 95), (645, ic_y)], color=RAIL)
    d.polyline([(780, 95), (780, ic_y)], color=RAIL)
    d.circle(645, 95, fill=RAIL)
    d.circle(780, 95, fill=RAIL)
    d.polyline([pins['P1'], (690, 710), (690, 765)], color=GROUND)
    d.circle(690, 765, fill=GROUND)

    # Internal blocks.
    d.resistor(585, 238, 72, 32, '5k', 'top', fill=CREAM_FILL)
    d.resistor(585, 318, 72, 32, '5k', 'mid', fill=CREAM_FILL)
    d.resistor(585, 398, 72, 32, '5k', 'bottom', fill=CREAM_FILL)
    d.line(621, ic_y + 58, 621, 238, color=INNER)
    d.line(621, 270, 621, 318, color=INNER)
    d.line(621, 350, 621, 398, color=INNER)
    d.line(621, 430, 621, ic_y + ic_h - 50, color=INNER)
    d.circle(621, 296, fill=BLACK)
    d.circle(621, 376, fill=BLACK)
    d.text(632, 288, '2/3 VCC', 10, fill='#555555')
    d.text(632, 368, '1/3 VCC', 10, fill='#555555')
    d.label_box(700, 247, 110, 48, 'Threshold', 'comparator', fill=CREAM_FILL)
    d.label_box(700, 355, 110, 48, 'Trigger', 'comparator', fill=CREAM_FILL)
    d.label_box(822, 305, 70, 52, 'SR', 'latch', fill=CREAM_FILL)
    d.label_box(820, 396, 86, 52, 'Output', 'driver', fill=CREAM_FILL)
    d.npn(650, 505, 'discharge NPN')

    # Internal wiring.
    d.polyline([(621, 296), (700, 271)], color=INNER)
    d.polyline([(pins['P6'][0] + 5, pins['P6'][1]), (675, pins['P6'][1]), (675, 260), (700, 260)], color=INNER)
    d.polyline([(621, 376), (700, 379)], color=INNER)
    d.polyline([(pins['P2'][0] + 5, pins['P2'][1]), (675, pins['P2'][1]), (675, 392), (700, 392)], color=INNER)
    d.polyline([(810, 271), (822, 320)], color=INNER)
    d.polyline([(810, 379), (822, 342)], color=INNER)
    d.polyline([(645, ic_y), (645, 305), (822, 305)], color=INNER)
    d.polyline([(892, 331), (820, 422)], color=INNER)
    d.polyline([(906, 422), (930, 422), (930, pins['P3'][1]), pins['P3']], color=INNER)
    d.polyline([(892, 350), (650, 467)], color=INNER)
    d.polyline([pins['P7'], (592, pins['P7'][1]), (592, 505)], color=INNER)
    d.polyline([(668, 567), (668, 690), (690, 690), (690, ic_y + ic_h)], color=INNER)
    d.polyline([pins['P5'], (892, pins['P5'][1]), (892, 474), (621, 296)], color=INNER)

    # Control capacitor.
    d.polyline([pins['P5'], (970, 500), (970, 575)])
    d.cap_vertical(970, 575, 765, 'C2', '10nF')
    d.circle(970, 765, fill=GROUND)

    # Output/load.
    d.polyline([pins['P3'], (985, 372)])
    d.circle(985, 372)
    d.text(988, 337, 'OUT', 13, bold=True)
    d.line(985, 372, 985, 330)
    d.circle(985, 330, r=5, fill='white', outline=BLACK, width=2)
    d.resistor(1015, 355, 78, 34, 'R3', '1k')
    d.line(985, 372, 1015, 372)
    d.line(1093, 372, 1115, 372)
    d.npn(1173, 455, 'T1 NPN')
    d.line(1115, 372, 1115, 455)
    d.line(1115, 455, 1115, 455)
    d.line(1191, 517, 1191, 765, color=GROUND)
    d.circle(1191, 765, fill=GROUND)
    d.line(1191, 393, 1191, 310)
    d.circle(1191, 310)
    d.led(1191, 150, 'LED1')
    d.line(1191, 95, 1191, 120, color=RAIL)
    d.circle(1191, 95, fill=RAIL)
    d.resistor(1152, 215, 78, 34, 'R4', '1.5k')
    d.line(1191, 184, 1191, 215)
    d.line(1191, 249, 1191, 310)

    # Decoupling caps.
    d.cap_vertical(1300, 180, 765, 'C3', '100nF')
    d.line(1300, 95, 1300, 180, color=RAIL)
    d.circle(1300, 95, fill=RAIL)
    d.circle(1300, 765, fill=GROUND)
    d.cap_vertical(1380, 180, 765, 'C4', '100uF')
    d.line(1380, 95, 1380, 180, color=RAIL)
    d.circle(1380, 95, fill=RAIL)
    d.circle(1380, 765, fill=GROUND)

    # Visual legend.
    d.rect(42, 812, 540, 50, fill='#f8fafc', outline='#cbd5e1', width=1, radius=5)
    d.text(58, 825, 'What changed vs the graph preview:', 12, bold=True)
    d.text(58, 844, 'rails are explicit; wires are orthogonal; NE555 pins are fixed; internal blocks are arranged by signal flow.', 11, fill='#444444')

    d.save()


if __name__ == '__main__':
    draw_ne555()
    print(SVG_PATH)
    print(PNG_PATH)
