from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shop.card_helpers import INTERNAL_PARAM_KEYS


FIELD_PATTERNS = {
    'pinout_keywords': (
        r'\bpin(?:out| configuration| description)?\b',
        r'\bterminal\b',
        r'\bDIP-?\d+\b',
        r'\bSOIC-?\d+\b',
    ),
    'absolute_maximum_ratings': (
        r'absolute maximum ratings?',
        r'maximum ratings?',
        r'limiting values?',
    ),
    'recommended_operating_conditions': (
        r'recommended operating conditions?',
        r'operating conditions?',
        r'electrical characteristics?',
    ),
    'package': (
        r'\bpackage\b',
        r'\bSOIC\b',
        r'\bDIP\b',
        r'\bSOT-?23\b',
        r'\bTO-?220\b',
    ),
    'thermal_data': (
        r'thermal resistance',
        r'junction temperature',
        r'\bRth\b',
        r'\btheta\b',
    ),
    'typical_application_hints': (
        r'typical application',
        r'application circuit',
        r'application information',
    ),
}

PARAM_FIELD_KEYS = {
    'pinout_keywords': ('pins', 'pin_count', 'package', 'package_type'),
    'absolute_maximum_ratings': (
        'voltage', 'supply_voltage', 'vds', 'vceo', 'vrrm', 'vz',
        'current', 'max_current', 'id', 'ic', 'if', 'output_current', 'contact_rating',
        'power', 'tdp_w', 'rated_power_w',
    ),
    'recommended_operating_conditions': (
        'resistance', 'capacitance', 'inductance', 'voltage', 'supply_voltage',
        'current', 'coil_voltage', 'freq', 'gbw', 'vf', 'rds_on',
    ),
    'package': ('package', 'package_type', 'mounting', 'form_factor'),
    'thermal_data': ('max_temp', 'temperature', 'junction_temperature', 'thermal_resistance', 'power', 'tdp_w'),
    'typical_application_hints': ('applications', 'type', 'family', 'interface'),
}


def dependency_status() -> dict[str, dict[str, Any]]:
    checks = {
        'PyMuPDF': 'fitz',
        'pdfplumber': 'pdfplumber',
        'pandas': 'pandas',
        'pypdf': 'pypdf',
    }
    result = {}
    for package, import_name in checks.items():
        try:
            __import__(import_name)
            result[package] = {'ok': True}
        except Exception as exc:
            result[package] = {'ok': False, 'error': str(exc)}
    return result


def extract_from_text(text: str, source_url: str = '') -> dict[str, Any]:
    text = text or ''
    fields = {}
    matched = 0
    for field, patterns in FIELD_PATTERNS.items():
        hits = _find_contexts(text, patterns)
        fields[field] = hits
        if hits:
            matched += 1

    confidence = 0.15 if text else 0.0
    if matched:
        confidence = min(0.95, 0.25 + matched * 0.12)

    return {
        'source_url': source_url,
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'confidence': round(confidence, 2),
        'fields': fields,
        'text_hash': hashlib.sha256(text[:200000].encode('utf-8', errors='ignore')).hexdigest() if text else '',
    }


def extract_from_pdf_path(path: str | Path, source_url: str = '') -> dict[str, Any]:
    path = Path(path)
    text = extract_pdf_text(path)
    result = extract_from_text(text, source_url=source_url)
    result['source_file'] = str(path)
    result['extractor'] = _best_available_extractor()
    return result


def build_product_datasheet_record(product, pdf_path: str | Path | None = None, fallback_text: str = '') -> dict[str, Any]:
    if pdf_path:
        result = extract_from_pdf_path(pdf_path, source_url=product.datasheet_url)
        return merge_product_metadata(result, product)
    text = fallback_text or product_metadata_text(product)
    result = extract_from_text(text, source_url=product.datasheet_url)
    result = merge_product_metadata(result, product)
    result['extractor'] = 'product_metadata_fallback'
    return result


def product_metadata_text(product) -> str:
    return ' '.join([
        product.name or '',
        product.part_number or '',
        product.description or '',
        product.package_type or '',
        ' '.join(
            f'{key}: {value}'
            for key, value in (product.parameters or {}).items()
            if key not in INTERNAL_PARAM_KEYS and not str(key).startswith('_')
        ),
    ])


def merge_product_metadata(record: dict[str, Any], product) -> dict[str, Any]:
    result = dict(record or {})
    fields = {key: list(value or []) for key, value in (result.get('fields') or {}).items()}
    inferred = infer_product_fields(product)
    inferred_count = 0
    for field, values in inferred.items():
        bucket = fields.setdefault(field, [])
        for value in values:
            if value and value not in bucket:
                bucket.append(value)
                inferred_count += 1
    result['fields'] = fields
    result['metadata_fallback_used'] = True
    result['metadata_inferred_fields'] = [
        key for key, value in inferred.items()
        if value
    ]
    if inferred_count:
        matched = len(result['metadata_inferred_fields'])
        result['confidence'] = max(float(result.get('confidence') or 0), min(0.9, 0.35 + matched * 0.1))
    return result


def infer_product_fields(product) -> dict[str, list[str]]:
    params = {
        key: value
        for key, value in (product.parameters or {}).items()
        if key not in INTERNAL_PARAM_KEYS and not str(key).startswith('_')
    }
    category = getattr(getattr(product, 'category', None), 'slug', '')
    fields = {key: [] for key in FIELD_PATTERNS}

    package_values = _collect_values(product, params, PARAM_FIELD_KEYS['package'])
    if product.package_type and product.package_type not in package_values:
        package_values.insert(0, product.package_type)
    if package_values:
        fields['package'].append('Корпус / монтаж: ' + ', '.join(package_values[:4]))

    pin_values = _collect_values(product, params, PARAM_FIELD_KEYS['pinout_keywords'])
    if pin_values:
        fields['pinout_keywords'].append('Выводы и корпус: ' + ', '.join(pin_values[:4]))
    elif product.package_type:
        fields['pinout_keywords'].append(f'Корпус {product.package_type}; выводы уточняются по datasheet.')

    abs_values = _collect_labeled_values(params, PARAM_FIELD_KEYS['absolute_maximum_ratings'])
    if abs_values:
        fields['absolute_maximum_ratings'].append('Предельные значения из карточки: ' + '; '.join(abs_values[:8]))

    operating_values = _collect_labeled_values(params, PARAM_FIELD_KEYS['recommended_operating_conditions'])
    if operating_values:
        fields['recommended_operating_conditions'].append('Рабочие параметры из карточки: ' + '; '.join(operating_values[:8]))

    thermal_values = _collect_labeled_values(params, PARAM_FIELD_KEYS['thermal_data'])
    if thermal_values:
        fields['thermal_data'].append('Тепловые/мощностные данные: ' + '; '.join(thermal_values[:6]))

    application_values = _collect_values(product, params, PARAM_FIELD_KEYS['typical_application_hints'])
    if application_values:
        fields['typical_application_hints'].append('Тип применения: ' + ', '.join(application_values[:4]))
    else:
        hint = _category_application_hint(category)
        if hint:
            fields['typical_application_hints'].append(hint)

    return fields


def _collect_values(product, params: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    values = []
    for key in keys:
        if key == 'package_type' and getattr(product, 'package_type', ''):
            values.append(str(product.package_type))
        value = params.get(key)
        if value not in (None, ''):
            values.append(str(value))
    return _dedupe(values)


def _collect_labeled_values(params: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    values = []
    for key in keys:
        value = params.get(key)
        if value in (None, ''):
            continue
        values.append(f'{_label_key(key)}={value}')
    return _dedupe(values)


def _dedupe(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        clean = str(value).strip()
        if not clean or clean.lower() in seen:
            continue
        seen.add(clean.lower())
        result.append(clean)
    return result


def _label_key(key: str) -> str:
    return {
        'vds': 'VDS',
        'max_voltage': 'Umax',
        'vceo': 'VCEO',
        'vrrm': 'VRRM',
        'vz': 'Vz',
        'max_current': 'Imax',
        'output_current': 'Iout',
        'id': 'ID',
        'ic': 'IC',
        'if': 'IF',
        'vf': 'VF',
        'rds_on': 'RDS(on)',
        'gbw': 'GBW',
        'tdp_w': 'Pmax',
        'rated_power_w': 'Pmax',
        'contact_rating': 'contact rating',
    }.get(key, key)


def _category_application_hint(category: str) -> str:
    return {
        'resistors': 'Типовое применение: ограничение тока, делители напряжения, подтяжки и шунты.',
        'capacitors': 'Типовое применение: фильтрация, развязка питания, RC-цепи и времязадающие узлы.',
        'transistors': 'Типовое применение: ключи нагрузки, усилители, согласование уровней.',
        'ics': 'Типовое применение: функциональные узлы схемы; режим включения уточняется по datasheet.',
        'diodes': 'Типовое применение: выпрямление, защита, индикация или стабилизация.',
        'inductors': 'Типовое применение: фильтры, DC/DC-преобразователи и подавление помех.',
        'connectors': 'Типовое применение: подключение питания, сигналов и внешних модулей.',
        'relays': 'Типовое применение: коммутация нагрузок и гальваническая развязка управления.',
    }.get(category, '')


def extract_pdf_text(path: Path) -> str:
    for extractor in (_extract_with_pymupdf, _extract_with_pdfplumber, _extract_with_pypdf):
        try:
            text = extractor(path)
        except Exception:
            text = ''
        if text and text.strip():
            return text
    return ''


def cache_path_for_url(media_root: str | Path, url: str) -> Path:
    digest = hashlib.sha256((url or '').encode('utf-8')).hexdigest()[:24]
    return Path(media_root) / 'datasheets' / 'cache' / f'{digest}.pdf'


def _extract_with_pymupdf(path: Path) -> str:
    import fitz

    pieces = []
    with fitz.open(path) as doc:
        for page in doc[:20]:
            pieces.append(page.get_text('text'))
    return '\n'.join(pieces)


def _extract_with_pdfplumber(path: Path) -> str:
    import pdfplumber

    pieces = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages[:20]:
            pieces.append(page.extract_text() or '')
            tables = page.extract_tables() or []
            for table in tables[:5]:
                for row in table[:40]:
                    pieces.append(' | '.join(str(cell or '') for cell in row))
    return '\n'.join(pieces)


def _extract_with_pypdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return '\n'.join((page.extract_text() or '') for page in reader.pages[:20])


def _best_available_extractor() -> str:
    status = dependency_status()
    for name in ('PyMuPDF', 'pdfplumber', 'pypdf'):
        if status.get(name, {}).get('ok'):
            return name
    return 'none'


def _find_contexts(text: str, patterns: tuple[str, ...]) -> list[str]:
    if not text:
        return []
    contexts = []
    compact = re.sub(r'\s+', ' ', text)
    for pattern in patterns:
        for match in re.finditer(pattern, compact, flags=re.IGNORECASE):
            start = max(0, match.start() - 90)
            end = min(len(compact), match.end() + 160)
            snippet = compact[start:end].strip()
            if snippet and snippet not in contexts:
                contexts.append(snippet)
            if len(contexts) >= 5:
                return contexts
    return contexts
