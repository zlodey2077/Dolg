"""Auto-fill empty fields на товарах каталога (БЕЗ photo-generation).

После bulk-imports много товаров остаются с пустыми полями: UPPERCASE-имена,
slug-style part_number'ы, manufacturer='other'. Карточки выглядят недоделанными.

Этот скрипт чинит:
  1. enrich_product_parameters → заполняет parameters по category-defaults.
  2. Нормализует UPPERCASE имена (`SOLDER TIP CLEANER` → `Solder Tip Cleaner`,
     но `USB`, `ESD`, `PCB`, `LED`, `IPA`, `SMD`, `THT` остаются в caps).
  3. Чистит slug-style part_number'ы (если part_number == slugify(name)
     и состоит только из ASCII-uppercase + `-` — обнуляет; настоящий
     part-number производителя имеет смысл, slug-strip нет).
  4. Для manufacturer='other' пытается угадать по подстроке в name (например
     `MURATA`/`KEMET`/`YAGEO`/`STM32F` → соответствующий мейкер). Если
     не угадывается — оставляет 'other'.

Photos НЕ генерируются — это работа отдельных команд по pipeline:
  - `import_product_photos` (drop файлы в media/products/incoming/<slug>.*)
  - `apply_verified_product_photos` (из media/products/verified/)

Usage:
  python manage.py enrich_catalog                # dry-run
  python manage.py enrich_catalog --apply         # реально записать
  python manage.py enrich_catalog --skip-params   # без enrich_product_parameters
  python manage.py enrich_catalog --slug R1206-10K # точечно
"""

from __future__ import annotations

import re
import sys
from collections import Counter

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from shop.models import Product

# Force UTF-8 stdout — Windows cp1251 ломается на ✓
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


# Аббревиатуры и бренды, которые должны остаться в UPPERCASE при title-case
PRESERVE_UPPER = {
    # Электроника-аббревиатуры
    'USB', 'ESD', 'PCB', 'LED', 'IPA', 'SMD', 'THT', 'RGB', 'TTL', 'CMOS',
    'NPN', 'PNP', 'JFET', 'MOSFET', 'BJT', 'IGBT', 'SCR', 'TRIAC',
    'IC', 'OPA', 'DAC', 'ADC', 'PWM', 'DC', 'AC', 'RMS', 'PCBA', 'TVS',
    # Часто встречаются в наименованиях каталога — оставляем UPPER
    'PSU', 'RMA', 'LAB', 'MAX', 'MIN', 'OSC', 'KIT', 'PRO',
    'AVR', 'PIC', 'ESP', 'MCU', 'PSP', 'PROM', 'EEPROM', 'EPROM', 'FLASH',
    'AWG', 'CU', 'PVC', 'CB',
    'DIP', 'SOP', 'SOIC', 'QFN', 'TQFP', 'LQFP', 'BGA', 'TO-92', 'TO-220',
    'SOT', 'MELF', 'DPAK', 'D2PAK',
    'I2C', 'SPI', 'UART', 'GPIO', 'JTAG', 'SWD', 'CAN', 'LIN',
    'GND', 'VCC', 'VDD', 'VSS',
    '3D', '2D', 'EMI', 'EMC', 'RF', 'AF', 'IR', 'UV',
    'OLED', 'TFT', 'LCD', 'EPD',
    # Брендовые имена (часто в каталоге)
    'NVIDIA', 'AMD', 'INTEL', 'RYZEN', 'EPYC', 'THREADRIPPER', 'XEON', 'CORE',
    'RTX', 'GTX', 'RX', 'GEFORCE', 'RADEON', 'ARC',
    'TSMC', 'GLOBALFOUNDRIES', 'SAMSUNG', 'LG', 'SK', 'SONY', 'CANON',
    'STM', 'STM32', 'NXP', 'TI', 'ARM', 'RISCV',
    'ESP32', 'ESP8266', 'RPI', 'PI', 'BBB',
    'IRF', 'IRFZ', 'IRFP', 'TIP', 'BC', 'BD', '2N', 'BSS', 'BSC',
    'NE555', 'LM358', 'LM741', 'LM317', 'LM7805', '74HC', 'CD4', 'MAX', 'TL',
    'MURATA', 'KEMET', 'YAGEO', 'VISHAY', 'TDK', 'WURTH', 'BOURNS', 'PANASONIC',
    'NICHICON', 'EPCOS', 'AVX',
    # Единицы измерения, остающиеся в верхнем регистре после числа
    'V', 'A', 'W', 'GHZ', 'MHZ', 'KHZ', 'HZ',
    'GB', 'TB', 'MB', 'KB', 'GHZ', 'GBPS', 'MBPS',
    'CPU', 'GPU', 'NPU', 'TPU', 'APU', 'SOC', 'FPGA', 'ASIC',
    'SSD', 'HDD', 'NVME', 'SATA', 'M.2',
    'OS', 'BIOS', 'UEFI', 'EFI', 'FAT', 'NTFS',
    'IP', 'TCP', 'UDP', 'HTTP', 'HTTPS', 'DNS', 'DHCP',
    'WIFI', 'WI-FI', 'BLE',
}

# Эвристика: подстрока → manufacturer choice
MANUFACTURER_HEURISTICS = [
    (re.compile(r'\b(MURATA|GRM)\b', re.I), 'murata'),
    (re.compile(r'\b(KEMET|C0G|C1206)\b', re.I), 'kemet'),
    (re.compile(r'\b(YAGEO|RC0805|RC0603)\b', re.I), 'yageo'),
    (re.compile(r'\b(VISHAY|MMA|MMS)\b', re.I), 'vishay'),
    (re.compile(r'\b(TDK|CGA)\b', re.I), 'tdk'),
    (re.compile(r'\b(STM32|ST7|STM8|STMicro)\b', re.I), 'st'),
    (re.compile(r'\b(ATmega|ATtiny|ATSAM|Atmel)\b', re.I), 'microchip' if False else 'other'),
    (re.compile(r'\b(NE555|LM358|LM741|SN74|TI )\b', re.I), 'ti'),
    (re.compile(r'\b(IRF\d|IRFZ|IR2)\b', re.I), 'infineon'),
    (re.compile(r'\b(BC[0-9]{3}|BD[0-9]{3}|TIP\d|2N\d)\b', re.I), 'onsemi'),
    (re.compile(r'\b(NXP|PCA|LPC)\b', re.I), 'nxp'),
    (re.compile(r'\b(NICHICON|UVZ|UPW)\b', re.I), 'nichicon'),
    (re.compile(r'\b(PANASONIC|EEU|ECW)\b', re.I), 'panasonic'),
    (re.compile(r'\b(WURTH|WE-|74435)\b', re.I), 'wurth'),
    (re.compile(r'\b(BOURNS|SRR|JW-)\b', re.I), 'bourns'),
]


VOWELS = set('AEIOUYaeiouy')


def _looks_like_acronym(word: str) -> bool:
    """True если слово ТОЧНО аббревиатура, не обычное слово.

    Слабая эвристика — лучше пропустить нормализацию реальной аббревиатуры
    (можно потом добавить в PRESERVE_UPPER), чем сломать «SOLDER TIP» в
    «Solder TIP». Только два чёткие критерия:
    - Содержит цифры (RTX4090, BC547, 2N3906, 5A, 30V) → spec/PN
    - Состоит из ≤2 букв (RF, IC, AI, ST, TI) → совсем короткие — почти всегда аббр
    - Нет ни одной гласной (TDK, NXP, JFET, BJT) → точно аббр

    Раньше было `len ≤ 4 + ≤1 vowel` — но это ловило слова FLUX, LAB, RMA,
    PSU, MAX и т.п. Часть из них акронимы (RMA/PSU), часть слова (FLUX/LAB).
    Не угадаешь автоматически — оставляем такие на whitelist (PRESERVE_UPPER).
    """
    if not word.isalpha():
        return True
    if len(word) <= 2:
        return True
    if not any(ch in VOWELS for ch in word):
        return True
    return False


def normalize_title_case(name: str) -> str:
    """`SOLDER TIP CLEANER` → `Solder Tip Cleaner`, сохраняя аббревиатуры.

    Если оригинал НЕ all-uppercase — возвращаем как есть (не считаем нужным
    нормализовать смешанный регистр; вдруг это `Würth Elektronik`).
    """
    if not name or name != name.upper():
        return name
    parts = []
    for word in re.split(r'(\s+|[-/])', name):
        if not word.strip() or word in (' ', '-', '/'):
            parts.append(word)
            continue
        upper = word.upper()
        # 1) Explicit whitelist
        if upper in PRESERVE_UPPER:
            parts.append(upper)
        # 2) Acronym по эвристикам
        elif _looks_like_acronym(word):
            parts.append(upper)
        else:
            parts.append(word.capitalize())
    return ''.join(parts)


def is_slug_style_pn(part_number: str, name: str) -> bool:
    """Возвращает True, если part_number — это просто slug от name."""
    if not part_number:
        return False
    # Slug-style: только ASCII-uppercase + цифры + дефисы
    if not re.fullmatch(r'[A-Z0-9\-]+', part_number):
        return False
    # Совпадает со слаговой версией имени (с заменой пробелов на дефисы)?
    expected_slug = re.sub(r'\s+', '-', name.upper().strip())
    return part_number == expected_slug


def guess_manufacturer(name: str, part_number: str, current: str) -> str | None:
    """Пытается угадать manufacturer по подстроке в name/part_number.

    Если current не 'other' — не трогаем.
    Если ничего не подходит — возвращаем None (без изменений).
    """
    if current and current != 'other':
        return None
    haystack = f'{name} {part_number or ""}'
    for pattern, mfr in MANUFACTURER_HEURISTICS:
        if pattern.search(haystack):
            return mfr
    return None


class Command(BaseCommand):
    help = 'Auto-fill empty fields на товарах: фото, name-case, slug-PN, manufacturer.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Реально записать изменения. Без флага — dry-run, печатает план.')
        parser.add_argument('--skip-params', action='store_true',
                            help='Не запускать enrich_product_parameters.')
        parser.add_argument('--slug', type=str, default=None,
                            help='Точечно один товар по slug (для теста).')
        parser.add_argument('--limit', type=int, default=0,
                            help='Ограничить выборку (для теста).')

    def handle(self, *args, **opts):
        apply = opts['apply']
        slug = opts.get('slug')
        limit = opts.get('limit') or 0

        prefix = '' if apply else '[dry-run] '
        self.stdout.write(self.style.SUCCESS(f'\n=== Enrich catalog {prefix}===\n'))

        # ── Этап 1: enrich_product_parameters ───────────────────────────
        if not opts['skip_params']:
            self.stdout.write('▸ Заполнение Product.parameters по category-defaults…')
            try:
                if apply:
                    call_command('enrich_product_parameters', verbosity=0, stdout=self.stdout)
                else:
                    empty = Product.objects.filter(parameters={}).count()
                    self.stdout.write(f'  будет обогащено: {empty} товаров')
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f'  ⚠ enrich_product_parameters упал: {exc}'))

        # ── Этап 2: name normalization + slug-PN + manufacturer ─────────
        self.stdout.write('▸ Нормализация name/PN/manufacturer…')
        qs = Product.objects.all().order_by('id')
        if slug:
            qs = qs.filter(slug=slug)
        if limit:
            qs = qs[:limit]

        name_fixed = 0
        pn_cleared = 0
        mfr_updated = 0
        mfr_changes: Counter = Counter()
        updates = []

        for p in qs:
            changed = False

            # Name: UPPERCASE → Title Case
            new_name = normalize_title_case(p.name)
            if new_name != p.name:
                name_fixed += 1
                if not apply:
                    self.stdout.write(f'  rename: {p.name!r} → {new_name!r}')
                p.name = new_name
                changed = True

            # Part number: убрать slug-style
            if is_slug_style_pn(p.part_number, p.name):
                pn_cleared += 1
                if not apply:
                    self.stdout.write(f'  pn-strip: {p.part_number!r} (slug of {p.name!r})')
                p.part_number = ''
                changed = True

            # Manufacturer guess
            guessed = guess_manufacturer(p.name, p.part_number, p.manufacturer)
            if guessed and guessed != p.manufacturer:
                mfr_updated += 1
                mfr_changes[guessed] += 1
                if not apply:
                    self.stdout.write(f'  mfr: {p.name[:40]!r} {p.manufacturer} → {guessed}')
                p.manufacturer = guessed
                changed = True

            if changed and apply:
                updates.append(p)

        if apply and updates:
            Product.objects.bulk_update(updates, ['name', 'part_number', 'manufacturer'])

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'✓ name normalized: {name_fixed} · pn cleared: {pn_cleared} · '
            f'manufacturer set: {mfr_updated}'
        ))
        if mfr_changes:
            for mfr, n in mfr_changes.most_common():
                self.stdout.write(f'  · {mfr}: {n}')
        if not apply:
            self.stdout.write(self.style.WARNING('\nDry-run — для записи перезапустите с --apply'))
