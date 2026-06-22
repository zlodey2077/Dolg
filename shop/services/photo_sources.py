"""Мульти-источниковый поиск РЕАЛЬНЫХ фото товаров (генерация UGO — только fallback).

Приоритет: курируемые official-CDN → Nexar/Octopart (по part_number, нужен ключ) → LCSC/EasyEDA
(поиск по MPN). Каждого кандидата прогоняем через гейт качества (resolution/entropy/edge — те же
пороги, что media_quality) — «некачественные» отбраковываются, пробуем следующий источник/кандидат.
Прошедшее фото сохраняется в products/verified/<slug>.<ext> и привязывается через media-policy.

Сеть/ключи — опциональны: без NEXAR_* источник Nexar просто пропускается; сетевые сбои гасятся
(источник возвращает пусто). Запускается батч-командой fetch_product_photos (НЕ в рантайме рендера).
Wikimedia/Commons НЕ используется (политика no-wikimedia сохранена).
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageFilter

from .product_images import VERIFIED_IMAGE_DIR

# Пороги качества для скачанных кандидатов (синхронизированы с media_quality.audit_product_image).
MIN_WIDTH = 320
MIN_HEIGHT = 220
MIN_ENTROPY = 1.0
MIN_LUMA_RANGE = 18
MIN_EDGE_DENSITY = 0.006
HTTP_TIMEOUT = 12
USER_AGENT = 'DOLG-catalog-bot/1.0 (diploma project; product photo fetch)'
RASTER_SUFFIXES = ('.png', '.jpg', '.jpeg', '.webp')


@dataclass(frozen=True)
class PhotoCandidate:
    url: str
    source: str  # 'official-cdn' | 'nexar' | 'lcsc'
    title: str = ''
    license: str = ''


@dataclass
class FetchResult:
    slug: str
    ok: bool = False
    source: str = ''
    url: str = ''
    relative_path: str = ''
    reason: str = ''
    tried: list[str] = field(default_factory=list)


# ── Курируемые official-CDN URL (расширяемый список; лицензионно-безопасные витрины) ──────────
# Ключ — product.slug. Значение — прямой URL на фото производителя/дистрибьютора.
OFFICIAL_CDN_PHOTOS: dict[str, str] = {
    'breadboard-400': 'https://cdn-shop.adafruit.com/970x728/64-06.jpg',
    'breadboard-830': 'https://cdn-shop.adafruit.com/970x728/239-03.jpg',
    'breadboard-2x830': 'https://cdn-shop.adafruit.com/970x728/239-05.jpg',
    'jumper-mm-65pcs': 'https://cdn-shop.adafruit.com/970x728/759-03.jpg',
    # ↑ существующие из import_official_product_photos. Ниже — место для расширения
    # (Mouser/Digikey/TI/SparkFun CDN). Добавлять по мере курирования.
}


def _http_get(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            if getattr(resp, 'status', 200) >= 400:
                return None
            return resp.read()
    except Exception:
        return None


def _http_json(url: str, *, data: bytes | None = None, headers: dict | None = None) -> dict | None:
    try:
        h = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, data=data, headers=h, method='POST' if data else 'GET')
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode('utf-8', errors='ignore'))
    except Exception:
        return None


def _mpn(product) -> str:
    return (getattr(product, 'part_number', '') or getattr(product, 'name', '') or '').strip()


# ── Источник 1: курируемые official-CDN ──────────────────────────────────────────────────────
def official_cdn_candidates(product) -> list[PhotoCandidate]:
    url = OFFICIAL_CDN_PHOTOS.get(getattr(product, 'slug', ''))
    if not url:
        return []
    return [PhotoCandidate(url=url, source='official-cdn', title='manufacturer/distributor photo')]


# ── Источник 2: Nexar (Octopart) GraphQL по part_number. Нужен NEXAR_CLIENT_ID/SECRET ─────────
_NEXAR_TOKEN_CACHE: dict[str, str] = {}


def _nexar_token() -> str:
    cid = os.getenv('NEXAR_CLIENT_ID', '')
    secret = os.getenv('NEXAR_CLIENT_SECRET', '')
    if not cid or not secret:
        return ''
    if _NEXAR_TOKEN_CACHE.get('token'):
        return _NEXAR_TOKEN_CACHE['token']
    body = urllib.parse.urlencode(
        {
            'grant_type': 'client_credentials',
            'client_id': cid,
            'client_secret': secret,
            'scope': 'supply.domain',
        }
    ).encode()
    data = _http_json(
        'https://identity.nexar.com/connect/token',
        data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    token = (data or {}).get('access_token', '')
    if token:
        _NEXAR_TOKEN_CACHE['token'] = token
    return token


def nexar_candidates(product) -> list[PhotoCandidate]:
    token = _nexar_token()
    mpn = _mpn(product)
    if not token or not mpn:
        return []
    query = 'query($q:String!){supSearchMpn(q:$q,limit:1){results{part{bestImage{url}images{url}}}}}'
    payload = json.dumps({'query': query, 'variables': {'q': mpn}}).encode()
    data = _http_json(
        'https://api.nexar.com/graphql',
        data=payload,
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
    )
    out: list[PhotoCandidate] = []
    try:
        results = data['data']['supSearchMpn']['results'] or []
        for r in results:
            part = r.get('part') or {}
            best = (part.get('bestImage') or {}).get('url')
            if best:
                out.append(PhotoCandidate(url=best, source='nexar', title='Octopart/Nexar bestImage'))
            for img in part.get('images') or []:
                if img.get('url'):
                    out.append(PhotoCandidate(url=img['url'], source='nexar', title='Octopart/Nexar image'))
    except Exception:
        return out
    return out


# ── Источник 3: LCSC/EasyEDA поиск по MPN (неофициальный API, best-effort) ────────────────────
def lcsc_candidates(product) -> list[PhotoCandidate]:
    mpn = _mpn(product)
    if not mpn:
        return []
    url = 'https://easyeda.com/api/products/search?' + urllib.parse.urlencode(
        {'wd': mpn, 'returnListStyle': 'classpath'}
    )
    data = _http_json(url)
    out: list[PhotoCandidate] = []
    try:
        products = (((data or {}).get('result') or {}).get('productList')) or []
        for item in products[:3]:
            img = item.get('images') or {}
            cand = img.get('900x900') or img.get('500x500') or item.get('image')
            if cand:
                out.append(PhotoCandidate(url=cand, source='lcsc', title='LCSC/EasyEDA product image'))
    except Exception:
        return out
    return out


SOURCES = {
    'official-cdn': official_cdn_candidates,
    'nexar': nexar_candidates,
    'lcsc': lcsc_candidates,
}
DEFAULT_ORDER = ['official-cdn', 'nexar', 'lcsc']


def iter_candidates(product, order: list[str] | None = None):
    for name in order or DEFAULT_ORDER:
        fn = SOURCES.get(name)
        if not fn:
            continue
        try:
            yield from fn(product)
        except Exception:
            continue


def image_quality_ok(path: Path) -> tuple[bool, str]:
    """Гейт качества скачанного фото: разрешение/энтропия/детализация. (ok, причина-отказа)."""
    try:
        with Image.open(path) as opened:
            image = opened.convert('RGB')
    except Exception as exc:
        return False, f'unreadable:{exc}'
    w, h = image.size
    if w < MIN_WIDTH or h < MIN_HEIGHT:
        return False, f'too_small:{w}x{h}'
    if float(image.entropy()) < MIN_ENTROPY:
        return False, 'near_blank_entropy'
    lo, hi = image.convert('L').getextrema()
    if int(hi - lo) < MIN_LUMA_RANGE:
        return False, 'near_blank_luma'
    edges = image.convert('L').resize((128, 128)).filter(ImageFilter.FIND_EDGES).histogram()
    edge_density = sum(c for v, c in enumerate(edges) if v >= 32) / float(128 * 128)
    if edge_density < MIN_EDGE_DENSITY:
        return False, 'low_detail'
    return True, ''


def _suffix_for(url: str, blob: bytes) -> str:
    lower = url.lower().split('?')[0]
    for s in RASTER_SUFFIXES:
        if lower.endswith(s):
            return '.jpg' if s == '.jpeg' else s
    if blob[:8].startswith(b'\x89PNG'):
        return '.png'
    if blob[:3] == b'\xff\xd8\xff':
        return '.jpg'
    if blob[:4] == b'RIFF':
        return '.webp'
    return '.jpg'


def find_and_apply_photo(product, *, order: list[str] | None = None, dry_run: bool = False) -> FetchResult:
    """Найти реальное фото (по приоритету источников), пройти гейт качества, сохранить в verified/
    и привязать через media-policy. Возвращает FetchResult. Генерацию НЕ трогает (это fallback)."""
    from .product_images import _safe_slug, apply_product_image_policy

    slug = _safe_slug(getattr(product, 'slug', None) or getattr(product, 'name', 'product'))
    result = FetchResult(slug=slug)
    verified_dir = Path(settings.MEDIA_ROOT) / VERIFIED_IMAGE_DIR
    verified_dir.mkdir(parents=True, exist_ok=True)

    for cand in iter_candidates(product, order):
        result.tried.append(f'{cand.source}:{cand.url[:60]}')
        if dry_run:
            result.ok = True
            result.source, result.url = cand.source, cand.url
            result.reason = 'dry-run (не скачивалось)'
            return result
        blob = _http_get(cand.url)
        if not blob or len(blob) < 1024:
            continue
        suffix = _suffix_for(cand.url, blob)
        dest = verified_dir / f'{slug}{suffix}'
        try:
            dest.write_bytes(blob)
        except Exception:
            continue
        ok, why = image_quality_ok(dest)
        if not ok:
            try:
                dest.unlink()
            except Exception:
                pass
            result.tried[-1] += f' [отбраковано: {why}]'
            continue
        # Прошло гейт — привязываем (apply_product_image_policy найдёт verified-ассет).
        apply_product_image_policy(product, force=False)
        result.ok = True
        result.source, result.url = cand.source, cand.url
        result.relative_path = f'{VERIFIED_IMAGE_DIR}/{slug}{suffix}'
        return result

    result.reason = 'не найдено качественных кандидатов (останется UGO-генерация)'
    return result
