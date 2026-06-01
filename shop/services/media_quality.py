from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from django.conf import settings
from PIL import Image, ImageFilter

from .product_images import (
    is_allowed_product_image,
    is_forbidden_image_path,
    is_generated_product_image,
    is_local_product_asset,
    is_local_product_svg_asset,
)

MIN_WIDTH = 320
MIN_HEIGHT = 220
MAX_ASPECT_RATIO = 3.2
MIN_ASPECT_RATIO = 0.35
MIN_ENTROPY = 1.0
MIN_LUMA_RANGE = 18


def _image_name(value: Any) -> str:
    if not value:
        return ''
    return getattr(value, 'name', str(value)) or ''


def _source_type(product, image_name: str) -> str:
    if not image_name:
        return 'missing'
    if is_forbidden_image_path(image_name):
        return 'forbidden'
    if is_generated_product_image(image_name):
        return 'generated'
    if is_local_product_asset(product, image_name):
        return 'local_asset'
    return 'off_policy'


def _quality_score(errors: list[str], warnings: list[str]) -> int:
    return max(0, 100 - len(errors) * 35 - len(warnings) * 10)


def _image_hashes(image: Image.Image) -> dict[str, Any]:
    try:
        import imagehash
    except Exception as exc:
        return {'available': False, 'error': str(exc)}

    thumbnail = image.convert('RGB').resize((256, 256))
    return {
        'available': True,
        'average_hash': str(imagehash.average_hash(thumbnail)),
        'perceptual_hash': str(imagehash.phash(thumbnail)),
    }


def _edge_density(image: Image.Image) -> float:
    gray = image.convert('L').resize((128, 128))
    edges = gray.filter(ImageFilter.FIND_EDGES)
    histogram = edges.histogram()
    strong_edges = sum(count for value, count in enumerate(histogram) if value >= 32)
    return strong_edges / float(128 * 128)


def audit_product_image(product, *, media_root: Path | None = None) -> dict[str, Any]:
    """Inspect one product image without changing product data.

    The gate is intentionally conservative: it blocks broken/tiny/blank images
    and records perceptual hashes, while the existing no-Wikimedia policy remains
    the source of truth for allowed image provenance.
    """
    media_root = Path(media_root or settings.MEDIA_ROOT)
    image_name = _image_name(product.image)
    source_type = _source_type(product, image_name)
    report = {
        'slug': product.slug,
        'image': image_name,
        'source_type': source_type,
        'ok': True,
        'quality_score': 100,
        'errors': [],
        'warnings': [],
        'metrics': {},
        'hashes': {'available': False},
    }

    if not image_name:
        report['errors'].append('missing_image')
        report['ok'] = False
        report['quality_score'] = _quality_score(report['errors'], report['warnings'])
        return report

    if source_type in {'forbidden', 'off_policy'} or not is_allowed_product_image(product, image_name):
        report['errors'].append('image_policy_violation')

    image_path = media_root / image_name
    if not image_path.exists():
        report['errors'].append('missing_file')
        report['ok'] = False
        report['quality_score'] = _quality_score(report['errors'], report['warnings'])
        return report

    if image_path.suffix.lower() == '.svg':
        report['metrics'].update({'format': 'svg', 'vector': True})
        if not is_local_product_svg_asset(product, image_name):
            report['warnings'].append('svg_not_exact_product_asset')
        report['ok'] = not report['errors']
        report['quality_score'] = _quality_score(report['errors'], report['warnings'])
        return report

    try:
        with Image.open(image_path) as opened:
            image = opened.convert('RGB')
    except Exception as exc:
        report['errors'].append('unreadable_image')
        report['metrics']['open_error'] = str(exc)
        report['ok'] = False
        report['quality_score'] = _quality_score(report['errors'], report['warnings'])
        return report

    width, height = image.size
    aspect_ratio = width / height if height else 0
    entropy = float(image.entropy())
    gray = image.convert('L')
    luma_min, luma_max = gray.getextrema()
    luma_range = int(luma_max - luma_min)
    edge_density = _edge_density(image)

    report['metrics'].update({
        'width': width,
        'height': height,
        'aspect_ratio': round(aspect_ratio, 3),
        'entropy': round(entropy, 3),
        'luma_range': luma_range,
        'edge_density': round(edge_density, 4),
        'format': image_path.suffix.lower().lstrip('.'),
    })
    report['hashes'] = _image_hashes(image)

    if width < MIN_WIDTH or height < MIN_HEIGHT:
        report['errors'].append('image_too_small')
    if entropy < MIN_ENTROPY or luma_range < MIN_LUMA_RANGE:
        report['errors'].append('image_near_blank')
    if aspect_ratio < MIN_ASPECT_RATIO or aspect_ratio > MAX_ASPECT_RATIO:
        report['warnings'].append('extreme_aspect_ratio')
    if edge_density < 0.006:
        report['warnings'].append('low_visual_detail')

    report['ok'] = not report['errors']
    report['quality_score'] = _quality_score(report['errors'], report['warnings'])
    return report


def audit_catalog_media_quality(products: Iterable[Any], *, media_root: Path | None = None) -> dict[str, Any]:
    media_root = Path(media_root or settings.MEDIA_ROOT)
    reports = [audit_product_image(product, media_root=media_root) for product in products]
    errors = [item for item in reports if item['errors']]
    warnings = [item for item in reports if item['warnings']]

    phash_groups: dict[str, list[str]] = {}
    for item in reports:
        if item.get('source_type') == 'generated':
            continue
        phash = (item.get('hashes') or {}).get('perceptual_hash')
        if phash:
            phash_groups.setdefault(phash, []).append(f"{item['slug']}: {item['image']}")
    duplicate_phashes = {
        digest: refs for digest, refs in phash_groups.items() if len(refs) > 1
    }

    scores = [item['quality_score'] for item in reports]
    return {
        'checked': len(reports),
        'ok': not errors,
        'average_score': round(sum(scores) / len(scores), 2) if scores else 0,
        'error_count': len(errors),
        'warning_count': len(warnings),
        'errors': [
            {'slug': item['slug'], 'image': item['image'], 'errors': item['errors']}
            for item in errors
        ],
        'warnings': [
            {'slug': item['slug'], 'image': item['image'], 'warnings': item['warnings']}
            for item in warnings
        ],
        'perceptual_duplicate_groups': duplicate_phashes,
        'imagehash_available': any((item.get('hashes') or {}).get('available') for item in reports),
    }
