from __future__ import annotations

import functools
import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

GENERATED_IMAGE_DIR = 'products/generated'
GENERATED_IMAGE_SOURCE = 'local://dolg/generated-product-art'
GENERATED_IMAGE_POLICY = 'no-wikimedia'
LOCAL_PRODUCT_IMAGE_SOURCE = 'local://dolg/product-asset'
VERIFIED_IMAGE_DIR = 'products/verified'
VERIFIED_IMAGE_SOURCE = 'local://dolg/verified-product-photo'
LOCAL_ASSET_SUFFIXES = ('.png', '.jpg', '.jpeg', '.webp')
FORBIDDEN_IMAGE_PREFIXES = (
    'products/commons/',
    'products/curated/',
)
FORBIDDEN_IMAGE_HOST_TOKENS = (
    'wikimedia.org',
    'wikipedia.org',
)


@dataclass(frozen=True)
class GeneratedProductImage:
    relative_path: str
    absolute_path: Path
    source: str = GENERATED_IMAGE_SOURCE
    policy: str = GENERATED_IMAGE_POLICY


def is_forbidden_image_path(value: Any) -> bool:
    text = _image_name(value).lower().replace('\\', '/').strip()
    if not text:
        return False
    return text.startswith(FORBIDDEN_IMAGE_PREFIXES) or any(token in text for token in FORBIDDEN_IMAGE_HOST_TOKENS)


def is_generated_product_image(value: Any) -> bool:
    return _image_name(value).lower().replace('\\', '/').startswith(f'{GENERATED_IMAGE_DIR}/')


def find_local_product_asset(product) -> str:
    root = Path(settings.MEDIA_ROOT) / 'products'
    slug = _safe_slug(product.slug or product.name)
    for suffix in LOCAL_ASSET_SUFFIXES:
        relative_path = f'products/{slug}{suffix}'
        if (root / f'{slug}{suffix}').exists():
            return relative_path
    verified_root = Path(settings.MEDIA_ROOT) / VERIFIED_IMAGE_DIR
    for suffix in LOCAL_ASSET_SUFFIXES:
        relative_path = f'{VERIFIED_IMAGE_DIR}/{slug}{suffix}'
        if (verified_root / f'{slug}{suffix}').exists():
            return relative_path
    return ''


def is_local_product_asset(product, value: Any) -> bool:
    image_name = _image_name(value).replace('\\', '/')
    return bool(image_name) and image_name == find_local_product_asset(product)


def is_local_product_svg_asset(product, value: Any) -> bool:
    image_name = _image_name(value).replace('\\', '/').lower()
    return image_name.endswith('.svg') and is_local_product_asset(product, value)


def is_allowed_product_image(product, value: Any) -> bool:
    image_name = _image_name(value).replace('\\', '/')
    if not image_name or is_forbidden_image_path(image_name):
        return False
    return is_generated_product_image(image_name) or is_local_product_asset(product, image_name)


def generate_product_image(product, *, force: bool = False) -> GeneratedProductImage:
    target_dir = Path(settings.MEDIA_ROOT) / GENERATED_IMAGE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    relative_path = f'{GENERATED_IMAGE_DIR}/{_safe_slug(product.slug or product.name)}.png'
    absolute_path = Path(settings.MEDIA_ROOT) / relative_path

    if force or not absolute_path.exists():
        image = _render_product_image(product)
        image.save(absolute_path, format='PNG', optimize=True)

    return GeneratedProductImage(relative_path=relative_path, absolute_path=absolute_path)


def choose_product_image(product, *, force_generated: bool = False, force: bool = False) -> GeneratedProductImage:
    if not force_generated:
        local_asset = find_local_product_asset(product)
        if local_asset:
            source = VERIFIED_IMAGE_SOURCE if local_asset.startswith(f'{VERIFIED_IMAGE_DIR}/') else LOCAL_PRODUCT_IMAGE_SOURCE
            return GeneratedProductImage(
                relative_path=local_asset,
                absolute_path=Path(settings.MEDIA_ROOT) / local_asset,
                source=source,
                policy=GENERATED_IMAGE_POLICY,
            )
    return generate_product_image(product, force=force)


def apply_generated_product_image(product, *, force: bool = False) -> bool:
    generated = generate_product_image(product, force=force)
    params = dict(product.parameters or {})
    params.update(
        {
            'image_source': 'generated technical product art',
            'image_source_url': generated.source,
            'image_source_policy': generated.policy,
        }
    )

    changed = product.image.name != generated.relative_path or product.parameters != params
    if changed:
        product.image.name = generated.relative_path
        product.parameters = params
        product.save(update_fields=['image', 'parameters'])
    return changed


def apply_product_image_policy(product, *, force: bool = False, force_generated: bool = False) -> bool:
    selected = choose_product_image(product, force_generated=force_generated, force=force)
    params = dict(product.parameters or {})
    if selected.source == GENERATED_IMAGE_SOURCE:
        params.update(
            {
                'image_source': 'manufacturer image pending; generated technical placeholder',
                'image_source_url': selected.source,
                'image_source_policy': selected.policy,
            }
        )
    else:
        is_verified_photo = selected.source == VERIFIED_IMAGE_SOURCE
        params.update(
            {
                'image_source': (
                    'verified real product photo'
                    if is_verified_photo else
                    'local product raster asset'
                ),
                'image_source_url': selected.source,
                'image_source_policy': selected.policy,
            }
        )

    changed = product.image.name != selected.relative_path or product.parameters != params
    if changed:
        product.image.name = selected.relative_path
        product.parameters = params
        product.save(update_fields=['image', 'parameters'])
    return changed


def _image_name(value: Any) -> str:
    if not value:
        return ''
    return getattr(value, 'name', str(value)) or ''


def _safe_slug(value: str) -> str:
    raw = (value or 'product').strip().lower()
    raw = re.sub(r'[^a-z0-9_-]+', '-', raw)
    raw = re.sub(r'-{2,}', '-', raw).strip('-')
    return raw or 'product'


def _render_product_image(product) -> Image.Image:
    width, height = 900, 620
    cat = getattr(product.category, 'slug', 'product')
    accent = _accent_color(product.slug or product.name)
    image = Image.new('RGB', (width, height), (9, 18, 36))
    draw = ImageDraw.Draw(image)

    _draw_background(draw, width, height, accent)
    _draw_category_art(draw, product, cat, accent, width, height)
    _draw_identity_marks(draw, product, accent, width, height)
    _draw_labels(draw, product, accent, width, height)
    return image


def _accent_color(seed: str) -> tuple[int, int, int]:
    digest = hashlib.sha256(seed.encode('utf-8', errors='ignore')).digest()
    palette = [
        (0, 209, 255),
        (32, 214, 149),
        (255, 191, 71),
        (139, 124, 255),
        (255, 91, 123),
        (68, 183, 255),
    ]
    return palette[digest[0] % len(palette)]


@functools.lru_cache(maxsize=32)
def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # lru_cache — каждый _font() ищет файл на диске. Без кеша на массовой
    # генерации 89+ товарных PNG это 89 × 5 разных размеров × Path.exists() —
    # сотни stat-вызовов. Кеш живёт в памяти процесса, копеечный.
    candidates = [
        'C:/Windows/Fonts/arialbd.ttf' if bold else 'C:/Windows/Fonts/arial.ttf',
        'C:/Windows/Fonts/segoeuib.ttf' if bold else 'C:/Windows/Fonts/segoeui.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    ]
    for path in candidates:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


FONT_TITLE = lambda: _font(44, bold=True)
FONT_META = lambda: _font(27, bold=True)
FONT_SMALL = lambda: _font(22)
FONT_TINY = lambda: _font(18)
FONT_MONO = lambda: _font(24, bold=True)


def _draw_background(draw: ImageDraw.ImageDraw, width: int, height: int, accent: tuple[int, int, int]) -> None:
    for y in range(height):
        blend = y / height
        color = (
            int(8 + blend * 9),
            int(17 + blend * 12),
            int(36 + blend * 18),
        )
        draw.line((0, y, width, y), fill=color)

    grid = (24, 53, 82)
    for x in range(40, width, 80):
        draw.line((x, 32, x, height - 32), fill=grid, width=1)
    for y in range(40, height, 80):
        draw.line((36, y, width - 36, y), fill=grid, width=1)

    # Чистый инженерный фон без декоративных дуг и рамок: карточка сама
    # задает контур, а изображение должно читаться как УГО/предметная схема.
    draw.line((52, height - 72, width - 52, height - 72), fill=_mix(accent, (30, 55, 80), 0.5), width=4)


def _draw_identity_marks(draw: ImageDraw.ImageDraw, product, accent: tuple[int, int, int], width: int, height: int) -> None:
    """Subtle non-text fingerprint so generated UGO images are not duplicates."""
    seed = f'{product.slug}|{product.part_number}|{product.name}|{product.package_type}'
    digest = hashlib.sha256(seed.encode('utf-8', errors='ignore')).digest()
    base_y = height - 46
    for idx in range(8):
        byte = digest[idx]
        x = 74 + idx * 92 + (byte % 21)
        y = base_y + ((byte >> 3) % 13)
        size = 4 + (byte % 3)
        color = _mix(accent, (155, 180, 205), 0.35 + (byte % 5) * 0.08)
        if byte & 1:
            draw.ellipse((x, y, x + size, y + size), fill=color)
        else:
            draw.rectangle((x, y, x + size, y + size), fill=color)

    for idx in range(3):
        byte = digest[12 + idx]
        x = width - 138 + idx * 28
        y = 58 + (byte % 22)
        color = _mix(accent, (40, 70, 96), 0.5)
        draw.line((x, y, x + 12 + (byte % 10), y), fill=color, width=2)


def _draw_category_art(draw: ImageDraw.ImageDraw, product, cat: str, accent: tuple[int, int, int], width: int, height: int) -> None:
    art_box = (78, 70, width - 78, height - 88)
    dispatch = {
        'resistors': _draw_resistor,
        'capacitors': _draw_capacitor,
        'transistors': _draw_transistor,
        'ics': _draw_ic,
        'diodes': _draw_diode,
        'inductors': _draw_inductor,
        'connectors': _draw_connector,
        'relays': _draw_relay,
        'cpu': _draw_cpu,
        'gpu': _draw_gpu,
        'ram': _draw_ram,
        'ssd': _draw_ssd,
        'psu': _draw_psu,
        'cooling': _draw_cooling,
        'monitors': _draw_monitor,
        'motherboards': _draw_motherboard,
        'smartphones': _draw_phone,
        'laptops': _draw_laptop,
        'tablets': _draw_tablet,
        'accessories': _draw_accessory,
    }
    dispatch.get(cat, _draw_generic_board)(draw, art_box, product, accent)


def _draw_labels(draw: ImageDraw.ImageDraw, product, accent: tuple[int, int, int], width: int, height: int) -> None:
    return None


def _manufacturer(product) -> str:
    try:
        value = product.get_manufacturer_display()
    except Exception:
        value = getattr(product, 'manufacturer', '')
    return value if value and value.lower() != 'other' else ''


def _fit_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    text = str(text or '').strip()
    if not text:
        return ''
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text
    ellipsis = '...'
    while text and draw.textbbox((0, 0), f'{text}{ellipsis}', font=font)[2] > max_width:
        text = text[:-1]
    return f'{text}{ellipsis}' if text else ellipsis


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], weight: float) -> tuple[int, int, int]:
    weight = max(0.0, min(1.0, weight))
    return tuple(int(a[i] * weight + b[i] * (1 - weight)) for i in range(3))


def _rect_center(box: tuple[int, int, int, int], w: int, h: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    return (cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2)


def _draw_pin_row(draw, start_x: int, y: int, count: int, pitch: int, direction: int, color: tuple[int, int, int]) -> None:
    for i in range(count):
        x = start_x + i * pitch
        draw.rounded_rectangle((x, y, x + 12, y + direction * 42), radius=4, fill=color)


def _draw_ic(draw, box, product, accent):
    body = _rect_center(box, 330, 190)
    x1, y1, x2, y2 = body
    pin_color = (202, 218, 227)
    _draw_pin_row(draw, x1 + 28, y1 - 34, 8, 36, 1, pin_color)
    _draw_pin_row(draw, x1 + 28, y2 - 8, 8, 36, 1, pin_color)
    draw.rounded_rectangle(body, radius=22, fill=(18, 25, 34), outline=accent, width=5)
    draw.ellipse((x1 + 22, y1 + 22, x1 + 44, y1 + 44), fill=accent)
    draw.arc((x1 + 54, y1 + 66, x1 + 120, y1 + 132), 180, 360, fill=_mix(accent, (230, 245, 255), 0.65), width=5)


def _draw_resistor(draw, box, product, accent):
    x1, y1, x2, y2 = _rect_center(box, 560, 116)
    mid_y = (y1 + y2) // 2
    draw.line((x1 - 70, mid_y, x1, mid_y), fill=(210, 220, 222), width=8)
    draw.line((x2, mid_y, x2 + 70, mid_y), fill=(210, 220, 222), width=8)
    draw.rounded_rectangle((x1, y1, x2, y2), radius=34, fill=(218, 191, 139), outline=accent, width=5)
    bands = [(92, 55, 42), (30, 29, 31), accent, (214, 170, 50)]
    for idx, color in enumerate(bands):
        x = x1 + 120 + idx * 62
        draw.rectangle((x, y1 + 8, x + 26, y2 - 8), fill=color)


def _draw_capacitor(draw, box, product, accent):
    x1, y1, x2, y2 = _rect_center(box, 430, 180)
    is_electro = 'electro' in str(product.description).lower() or 'uf' in str(product.parameters).lower()
    if is_electro:
        draw.rounded_rectangle((x1 + 120, y1 - 20, x2 - 120, y2 + 45), radius=28, fill=(28, 46, 60), outline=accent, width=5)
        draw.rectangle((x1 + 146, y1 - 18, x1 + 175, y2 + 44), fill=(226, 232, 238))
        draw.text((x1 + 194, y1 + 40), '+', fill=accent, font=FONT_TITLE())
        draw.line((x1 + 60, y2 + 45, x1 + 60, y2 + 104), fill=(215, 224, 225), width=8)
        draw.line((x2 - 60, y2 + 45, x2 - 60, y2 + 104), fill=(215, 224, 225), width=8)
    else:
        draw.rounded_rectangle((x1, y1 + 40, x2, y2), radius=24, fill=(176, 128, 92), outline=accent, width=5)
        draw.rectangle((x1 + 22, y1 + 66, x2 - 22, y2 - 26), fill=(208, 154, 112))


def _draw_transistor(draw, box, product, accent):
    pkg = (product.package_type or '').upper()
    if 'TO-220' in pkg or 'L7805' in (product.part_number or '').upper():
        x1, y1, x2, y2 = _rect_center(box, 260, 250)
        draw.rounded_rectangle((x1, y1, x2, y2), radius=24, fill=(26, 29, 35), outline=accent, width=5)
        draw.ellipse((x1 + 94, y1 + 22, x1 + 166, y1 + 94), outline=(185, 202, 208), width=8)
        for x in (x1 + 58, x1 + 124, x1 + 190):
            draw.rounded_rectangle((x, y2 - 8, x + 18, y2 + 96), radius=6, fill=(207, 216, 220))
    else:
        x1, y1, x2, y2 = _rect_center(box, 250, 220)
        draw.pieslice((x1, y1, x2, y2 + 74), 180, 360, fill=(24, 28, 34), outline=accent, width=5)
        draw.rectangle((x1, y1 + 110, x2, y2), fill=(24, 28, 34), outline=accent, width=5)
        for x in (x1 + 45, x1 + 116, x1 + 187):
            draw.line((x, y2, x, y2 + 80), fill=(207, 216, 220), width=9)


def _draw_diode(draw, box, product, accent):
    x1, y1, x2, y2 = _rect_center(box, 520, 116)
    mid_y = (y1 + y2) // 2
    draw.line((x1 - 75, mid_y, x2 + 75, mid_y), fill=(210, 220, 222), width=8)
    if 'LED' in (product.part_number + product.name).upper():
        draw.ellipse((x1 + 170, y1 - 50, x1 + 350, y2 + 50), fill=_mix(accent, (255, 255, 255), 0.34), outline=accent, width=5)
        draw.line((x1 + 382, y1 - 42, x1 + 424, y1 - 84), fill=accent, width=6)
        draw.line((x1 + 428, y1 - 12, x1 + 470, y1 - 54), fill=accent, width=6)
    else:
        draw.rounded_rectangle((x1, y1, x2, y2), radius=28, fill=(33, 36, 40), outline=accent, width=5)
        draw.rectangle((x2 - 110, y1 + 9, x2 - 76, y2 - 9), fill=(233, 235, 238))


def _draw_inductor(draw, box, product, accent):
    x1, y1, x2, y2 = _rect_center(box, 420, 220)
    draw.rounded_rectangle((x1, y1, x2, y2), radius=42, fill=(37, 46, 48), outline=accent, width=5)
    for i in range(6):
        cx = x1 + 68 + i * 58
        draw.arc((cx, y1 + 52, cx + 86, y2 - 34), 180, 360, fill=(229, 165, 79), width=12)


def _draw_connector(draw, box, product, accent):
    x1, y1, x2, y2 = _rect_center(box, 470, 190)
    draw.rounded_rectangle((x1, y1, x2, y2), radius=22, fill=(25, 55, 70), outline=accent, width=5)
    for i in range(5):
        sx = x1 + 44 + i * 78
        draw.rounded_rectangle((sx, y1 + 42, sx + 42, y2 - 42), radius=8, fill=(210, 218, 220))
    draw.line((x1 + 38, y2 + 20, x2 - 38, y2 + 20), fill=(200, 216, 219), width=8)


def _draw_relay(draw, box, product, accent):
    x1, y1, x2, y2 = _rect_center(box, 390, 210)
    draw.rounded_rectangle((x1, y1, x2, y2), radius=24, fill=(29, 55, 74), outline=accent, width=5)
    draw.arc((x1 + 58, y1 + 60, x1 + 148, y1 + 150), 90, 270, fill=(205, 230, 240), width=7)
    draw.line((x1 + 210, y1 + 68, x1 + 300, y1 + 140), fill=(205, 230, 240), width=8)
    for x in range(x1 + 44, x2 - 44, 68):
        draw.rounded_rectangle((x, y2 - 6, x + 18, y2 + 78), radius=6, fill=(207, 216, 220))


def _draw_cpu(draw, box, product, accent):
    x1, y1, x2, y2 = _rect_center(box, 260, 260)
    for x in range(x1 - 34, x2 + 1, 26):
        draw.rectangle((x, y1 - 20, x + 10, y1 + 8), fill=(214, 185, 83))
        draw.rectangle((x, y2 - 8, x + 10, y2 + 20), fill=(214, 185, 83))
    for y in range(y1 - 34, y2 + 1, 26):
        draw.rectangle((x1 - 20, y, x1 + 8, y + 10), fill=(214, 185, 83))
        draw.rectangle((x2 - 8, y, x2 + 20, y + 10), fill=(214, 185, 83))
    draw.rounded_rectangle((x1, y1, x2, y2), radius=28, fill=(62, 73, 82), outline=accent, width=5)
    draw.rounded_rectangle((x1 + 48, y1 + 52, x2 - 48, y2 - 52), radius=18, fill=(171, 184, 187))


def _draw_gpu(draw, box, product, accent):
    x1, y1, x2, y2 = _rect_center(box, 560, 220)
    draw.rounded_rectangle((x1, y1, x2, y2), radius=24, fill=(26, 56, 61), outline=accent, width=5)
    draw.rectangle((x1 - 44, y1 + 70, x1, y1 + 136), fill=(209, 180, 74))
    for cx in (x1 + 180, x1 + 370):
        draw.ellipse((cx - 68, y1 + 42, cx + 68, y1 + 178), fill=(15, 21, 29), outline=(185, 205, 211), width=5)
        for angle in range(0, 360, 60):
            px = cx + math.cos(math.radians(angle)) * 48
            py = y1 + 110 + math.sin(math.radians(angle)) * 48
            draw.line((cx, y1 + 110, px, py), fill=accent, width=5)


def _draw_ram(draw, box, product, accent):
    x1, y1, x2, y2 = _rect_center(box, 600, 150)
    draw.rounded_rectangle((x1, y1, x2, y2), radius=18, fill=(24, 80, 66), outline=accent, width=5)
    for i in range(8):
        sx = x1 + 42 + i * 62
        draw.rounded_rectangle((sx, y1 + 28, sx + 44, y2 - 34), radius=7, fill=(16, 27, 35))
    for i in range(24):
        sx = x1 + 34 + i * 22
        draw.rectangle((sx, y2 - 9, sx + 10, y2 + 18), fill=(221, 184, 73))


def _draw_ssd(draw, box, product, accent):
    x1, y1, x2, y2 = _rect_center(box, 570, 160)
    draw.rounded_rectangle((x1, y1, x2, y2), radius=20, fill=(21, 85, 73), outline=accent, width=5)
    draw.rectangle((x2 - 58, y1 + 36, x2 + 26, y2 - 36), fill=(220, 184, 74))
    for i in range(4):
        sx = x1 + 50 + i * 82
        draw.rounded_rectangle((sx, y1 + 36, sx + 56, y2 - 38), radius=8, fill=(18, 27, 35))


def _draw_psu(draw, box, product, accent):
    x1, y1, x2, y2 = _rect_center(box, 410, 230)
    draw.rounded_rectangle((x1, y1, x2, y2), radius=26, fill=(35, 42, 49), outline=accent, width=5)
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    draw.ellipse((cx - 82, cy - 82, cx + 82, cy + 82), outline=(205, 219, 222), width=8)
    for angle in range(0, 360, 45):
        px = cx + math.cos(math.radians(angle)) * 76
        py = cy + math.sin(math.radians(angle)) * 76
        draw.line((cx, cy, px, py), fill=accent, width=4)


def _draw_cooling(draw, box, product, accent):
    x1, y1, x2, y2 = _rect_center(box, 450, 230)
    for i in range(9):
        x = x1 + i * 34
        draw.rectangle((x, y1 + 26, x + 18, y2 - 20), fill=(144, 166, 174))
    cx, cy = x2 - 95, (y1 + y2) // 2
    draw.ellipse((cx - 88, cy - 88, cx + 88, cy + 88), fill=(18, 25, 35), outline=accent, width=5)
    for angle in range(0, 360, 72):
        px = cx + math.cos(math.radians(angle)) * 66
        py = cy + math.sin(math.radians(angle)) * 66
        draw.line((cx, cy, px, py), fill=(220, 232, 235), width=8)


def _draw_monitor(draw, box, product, accent):
    x1, y1, x2, y2 = _rect_center(box, 520, 250)
    draw.rounded_rectangle((x1, y1, x2, y2), radius=26, fill=(11, 18, 30), outline=accent, width=6)
    draw.rounded_rectangle((x1 + 30, y1 + 28, x2 - 30, y2 - 44), radius=14, fill=(33, 73, 101))
    draw.line((x1 + 180, y2 + 4, x2 - 180, y2 + 4), fill=(204, 217, 222), width=12)
    draw.line(((x1 + x2) // 2, y2, (x1 + x2) // 2, y2 + 72), fill=(204, 217, 222), width=12)
    draw.rounded_rectangle(((x1 + x2) // 2 - 86, y2 + 68, (x1 + x2) // 2 + 86, y2 + 86), radius=8, fill=(204, 217, 222))


def _draw_motherboard(draw, box, product, accent):
    x1, y1, x2, y2 = _rect_center(box, 450, 280)
    draw.rounded_rectangle((x1, y1, x2, y2), radius=28, fill=(20, 79, 68), outline=accent, width=5)
    draw.rounded_rectangle((x1 + 42, y1 + 40, x1 + 150, y1 + 148), radius=12, fill=(72, 91, 94))
    for i in range(4):
        draw.rounded_rectangle((x1 + 190, y1 + 42 + i * 35, x2 - 34, y1 + 64 + i * 35), radius=6, fill=(18, 29, 37))
    for i in range(3):
        draw.rectangle((x1 + 55, y2 - 94 + i * 30, x2 - 50, y2 - 78 + i * 30), fill=(203, 215, 220))


def _draw_phone(draw, box, product, accent):
    x1, y1, x2, y2 = _rect_center(box, 210, 300)
    draw.rounded_rectangle((x1, y1, x2, y2), radius=38, fill=(15, 22, 34), outline=accent, width=6)
    draw.rounded_rectangle((x1 + 18, y1 + 20, x2 - 18, y2 - 20), radius=26, fill=(31, 70, 95))
    draw.ellipse((x2 - 62, y1 + 34, x2 - 32, y1 + 64), fill=(17, 24, 35))


def _draw_laptop(draw, box, product, accent):
    x1, y1, x2, y2 = _rect_center(box, 520, 260)
    draw.rounded_rectangle((x1 + 48, y1, x2 - 48, y2 - 74), radius=22, fill=(11, 18, 30), outline=accent, width=6)
    draw.rounded_rectangle((x1 + 82, y1 + 28, x2 - 82, y2 - 104), radius=12, fill=(31, 70, 95))
    draw.polygon([(x1, y2 - 58), (x2, y2 - 58), (x2 - 46, y2), (x1 + 46, y2)], fill=(190, 202, 207), outline=accent)


def _draw_tablet(draw, box, product, accent):
    x1, y1, x2, y2 = _rect_center(box, 340, 260)
    draw.rounded_rectangle((x1, y1, x2, y2), radius=34, fill=(12, 19, 30), outline=accent, width=6)
    draw.rounded_rectangle((x1 + 24, y1 + 20, x2 - 24, y2 - 20), radius=22, fill=(32, 72, 99))


def _draw_accessory(draw, box, product, accent):
    text = f'{product.name} {product.part_number}'.lower()
    if 'hdmi' in text or 'displayport' in text or 'usb' in text:
        x1, y1, x2, y2 = _rect_center(box, 520, 190)
        draw.arc((x1, y1, x2, y2 + 120), 185, 355, fill=(204, 216, 220), width=16)
        draw.rounded_rectangle((x1 + 22, y1 + 86, x1 + 132, y1 + 148), radius=16, fill=(32, 44, 52), outline=accent, width=4)
        draw.rounded_rectangle((x2 - 132, y1 + 86, x2 - 22, y1 + 148), radius=16, fill=(32, 44, 52), outline=accent, width=4)
    else:
        _draw_generic_board(draw, box, product, accent)


def _draw_generic_board(draw, box, product, accent):
    x1, y1, x2, y2 = _rect_center(box, 430, 250)
    draw.rounded_rectangle((x1, y1, x2, y2), radius=28, fill=(22, 79, 76), outline=accent, width=5)
    for i in range(7):
        draw.line((x1 + 40, y1 + 42 + i * 28, x2 - 38, y1 + 42 + i * 28), fill=(38, 112, 107), width=3)
    for i in range(5):
        cx = x1 + 70 + i * 74
        draw.ellipse((cx, y2 - 68, cx + 24, y2 - 44), fill=(215, 183, 76))
    draw.rounded_rectangle((x1 + 90, y1 + 66, x1 + 230, y1 + 166), radius=14, fill=(17, 27, 35))
