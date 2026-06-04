"""Populate catalog with ~300 additional products: radio components,
modules (Arduino/ESP/RPi), professional tools, consumables.

Все товары помечены ``parameters.catalog_version = 'v2'`` чтобы их можно
было быстро удалить и перегенерировать через ``--clear``. Идемпотентно:
``Product.objects.update_or_create(slug=...)`` — повторный запуск обновит
существующие, не создаст дубликатов.

Категории:
- Существующие РЭБ: resistors / capacitors / transistors / ics / diodes /
  inductors / connectors / relays
- Новые: modules / tools / consumables (создаются автоматически)
"""

import re
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from shop.models import Category, Product

# ============================================================================
# Helpers
# ============================================================================


def _make_slug(name):
    """Slug на латинице с фоллбэком на slugify для русских названий."""
    base = slugify(name, allow_unicode=False)
    if not base:
        # cyrillic fallback — простая транслитерация
        base = re.sub(r'[^a-z0-9-]+', '-', name.lower())
    return base.strip('-')[:80] or 'product'


def _resistor_e12_values():
    """E12 ряд в Ом — от 10 Ω до 10 МΩ."""
    e12 = [1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2]
    result = []
    for decade in (10, 100, 1_000, 10_000, 100_000, 1_000_000):
        for v in e12:
            result.append(int(v * decade))
    return result


def _format_resistance(ohm):
    if ohm >= 1_000_000:
        return f'{ohm / 1_000_000:g} МОм'
    if ohm >= 1_000:
        return f'{ohm / 1_000:g} кОм'
    return f'{ohm} Ом'


def _format_capacitance(picofarad):
    if picofarad >= 1_000_000:
        return f'{picofarad / 1_000_000:g} мкФ'
    if picofarad >= 1_000:
        return f'{picofarad / 1_000:g} нФ'
    return f'{picofarad:g} пФ'


# ============================================================================
# Item lists
# ============================================================================


def resistor_items(cats):
    """E12 × 3 корпуса × 2 серии = ~72 резистора. Берём подмножество E12
    (12 значений × 3 декады × 2 корпуса) = ~72."""
    items = []
    e12 = [1.0, 1.5, 2.2, 3.3, 4.7, 6.8]  # subset
    decades = [(100, '100 Ω'), (1_000, '1 кΩ'), (10_000, '10 кΩ'), (100_000, '100 кΩ')]
    packages = [
        ('SMD 0603', 'yageo', 'RC0603', Decimal('1.50'), 5000),
        ('SMD 0805', 'vishay', 'CRCW0805', Decimal('2.80'), 4000),
        ('THT axial', 'vishay', 'MF', Decimal('6.50'), 2000),
    ]
    for multi, _ in decades:
        for v in e12:
            ohm = int(v * multi)
            for pkg, mfr, prefix, price, stock in packages:
                code = f'{prefix}-{ohm}-1%'
                items.append(
                    {
                        'name': f'{mfr.title()} {code}',
                        'category': cats['resistors'],
                        'part_number': code,
                        'manufacturer': mfr,
                        'description': f'Резистор {_format_resistance(ohm)}, 1%, {pkg}. Серия для массового применения.',
                        'price': price,
                        'stock': stock,
                        'lifecycle_status': 'active',
                        'package_type': pkg,
                        'parameters': {
                            'resistance': _format_resistance(ohm),
                            'tolerance': '1%',
                            'power': '0.1 Вт' if 'SMD' in pkg else '0.25 Вт',
                            'mounting': 'SMD' if 'SMD' in pkg else 'THT',
                            'catalog_version': 'v2',
                        },
                    }
                )
    return items


def capacitor_items(cats):
    items = []
    # Керамика SMD MLCC (X7R) — основной номиналы
    ceramics = [
        (10, '10 пФ'),
        (22, '22 пФ'),
        (100, '100 пФ'),
        (470, '470 пФ'),
        (1_000, '1 нФ'),
        (10_000, '10 нФ'),
        (100_000, '100 нФ'),
        (1_000_000, '1 мкФ'),
        (10_000_000, '10 мкФ'),
    ]
    for pf, label in ceramics:
        for pkg, mfr, price, stock in [
            ('SMD 0603', 'murata', Decimal('3.20'), 8000),
            ('SMD 0805', 'kemet', Decimal('4.50'), 5000),
        ]:
            code = f'C{pkg.split()[-1]}-{label.replace(" ", "")}-X7R'
            items.append(
                {
                    'name': f'{mfr.title()} {code}',
                    'category': cats['capacitors'],
                    'part_number': code,
                    'manufacturer': mfr,
                    'description': f'Керамический конденсатор MLCC {label}, 50 В, X7R, ±10%, {pkg}.',
                    'price': price,
                    'stock': stock,
                    'lifecycle_status': 'active',
                    'package_type': pkg,
                    'parameters': {
                        'capacitance': label,
                        'voltage': '50 В',
                        'dielectric': 'X7R',
                        'tolerance': '±10%',
                        'mounting': 'SMD',
                        'catalog_version': 'v2',
                    },
                }
            )
    # Электролиты THT
    electrolytics = [
        (1, 50),
        (4.7, 50),
        (10, 50),
        (22, 50),
        (47, 35),
        (100, 35),
        (220, 25),
        (470, 25),
        (1000, 16),
        (2200, 10),
        (4700, 6.3),
    ]
    for cap_uf, voltage in electrolytics:
        code = f'E-{cap_uf}uF-{voltage}V'
        items.append(
            {
                'name': f'Nichicon UVR {cap_uf}мкФ/{voltage}В',
                'category': cats['capacitors'],
                'part_number': code,
                'manufacturer': 'nichicon',
                'description': f'Электролитический конденсатор {cap_uf} мкФ, {voltage} В, радиальный, 105°C.',
                'price': Decimal('3.50') + Decimal(str(cap_uf)) * Decimal('0.05'),
                'stock': 1500,
                'lifecycle_status': 'active',
                'package_type': 'THT radial',
                'parameters': {
                    'capacitance': f'{cap_uf} мкФ',
                    'voltage': f'{voltage} В',
                    'temp_max': '105°C',
                    'mounting': 'THT',
                    'catalog_version': 'v2',
                },
            }
        )
    return items


def diode_items(cats):
    rows = [
        ('1N4148', 'onsemi', 'Сигнальный диод, 100 В, 200 мА, быстрый, DO-35.', Decimal('3.50'), 3000),
        ('1N4001', 'onsemi', 'Выпрямительный диод 50 В, 1 А, DO-41.', Decimal('5.00'), 2500),
        ('1N4007', 'onsemi', 'Выпрямительный диод 1000 В, 1 А, DO-41.', Decimal('5.50'), 3000),
        ('1N5817', 'onsemi', 'Шоттки 20 В, 1 А, низкое падение, DO-41.', Decimal('8.00'), 1500),
        ('1N5819', 'onsemi', 'Шоттки 40 В, 1 А, DO-41.', Decimal('9.00'), 1500),
        ('1N5822', 'onsemi', 'Шоттки 40 В, 3 А, DO-201.', Decimal('14.00'), 800),
        ('BAT54', 'infineon', 'Шоттки SMD SOT-23, 30 В, 200 мА.', Decimal('4.50'), 2000),
        ('SS14', 'onsemi', 'Шоттки SMA, 40 В, 1 А.', Decimal('6.50'), 2200),
        ('BZX55C-3V3', 'vishay', 'Стабилитрон 3.3 В, 500 мВт, DO-35.', Decimal('4.20'), 2000),
        ('BZX55C-5V1', 'vishay', 'Стабилитрон 5.1 В, 500 мВт, DO-35.', Decimal('4.20'), 2000),
        ('BZX55C-12V', 'vishay', 'Стабилитрон 12 В, 500 мВт, DO-35.', Decimal('4.50'), 2000),
        # LED'ы
        ('LED-3MM-RED', 'kingbright', 'Светодиод 3 мм, красный, VF=2.0 В, 20 мА.', Decimal('4.00'), 3000),
        ('LED-3MM-GREEN', 'kingbright', 'Светодиод 3 мм, зелёный, VF=2.1 В.', Decimal('4.00'), 3000),
        ('LED-3MM-BLUE', 'kingbright', 'Светодиод 3 мм, синий, VF=3.2 В.', Decimal('5.50'), 2500),
        ('LED-5MM-RED', 'kingbright', 'Светодиод 5 мм, красный, VF=2.0 В.', Decimal('5.00'), 3000),
        ('LED-5MM-GREEN', 'kingbright', 'Светодиод 5 мм, зелёный, VF=2.1 В.', Decimal('5.00'), 3000),
        ('LED-5MM-BLUE', 'kingbright', 'Светодиод 5 мм, синий, VF=3.2 В.', Decimal('6.50'), 2500),
        ('LED-5MM-WHITE', 'kingbright', 'Светодиод 5 мм, белый, VF=3.0 В.', Decimal('7.00'), 2500),
        ('LED-RGB-COMMON-A', 'kingbright', 'RGB-светодиод 5 мм, общий анод.', Decimal('15.00'), 1500),
    ]
    return [_diode_dict(*row, cats) for row in rows]


def _diode_dict(pn, mfr, descr, price, stock, cats):
    return {
        'name': f'{mfr.title()} {pn}',
        'category': cats['diodes'],
        'part_number': pn,
        'manufacturer': mfr if mfr in {'onsemi', 'infineon', 'vishay', 'st', 'nxp'} else 'other',
        'description': descr,
        'price': price,
        'stock': stock,
        'lifecycle_status': 'active',
        'package_type': pn.split('-')[-1] if '-' in pn else 'DO-35',
        'parameters': {'catalog_version': 'v2'},
    }


def transistor_items(cats):
    rows = [
        ('BC547B', 'NPN сигнальный, 45 В, 100 мА, BF≈300, TO-92.', Decimal('5.00')),
        ('BC557B', 'PNP сигнальный, 45 В, 100 мА, TO-92.', Decimal('5.00')),
        ('2N2222A', 'NPN сигнальный/коммутационный, 40 В, 800 мА, TO-92.', Decimal('8.00')),
        ('2N2907A', 'PNP комплементарный к 2N2222, TO-92.', Decimal('8.00')),
        ('2N3904', 'NPN общего назначения, 40 В, 200 мА, TO-92.', Decimal('4.50')),
        ('2N3906', 'PNP общего назначения, 40 В, 200 мА, TO-92.', Decimal('4.50')),
        ('BC817-25', 'NPN SMD SOT-23, 45 В, 500 мА.', Decimal('3.50')),
        ('BC857B', 'PNP SMD SOT-23, 45 В, 100 мА.', Decimal('3.50')),
        ('IRF540N', 'N-канальный MOSFET, 100 В, 33 А, TO-220.', Decimal('45.00')),
        ('IRF9540N', 'P-канальный MOSFET, 100 В, 23 А, TO-220.', Decimal('55.00')),
        ('IRLZ44N', 'N-MOSFET логический уровень, 55 В, 47 А, TO-220.', Decimal('60.00')),
        ('AO3400', 'N-MOSFET SOT-23, 30 В, 5.7 А, для нагрузок до 12 В.', Decimal('8.00')),
        ('AO3401', 'P-MOSFET SOT-23, 30 В, 4 А.', Decimal('9.00')),
        ('BSS138', 'N-MOSFET SOT-23, 60 В, для level-shift.', Decimal('5.50')),
        ('TIP120', 'NPN Darlington, 60 В, 5 А, TO-220.', Decimal('25.00')),
    ]
    return [
        {
            'name': f'OnSemi {pn}',
            'category': cats['transistors'],
            'part_number': pn,
            'manufacturer': 'onsemi',
            'description': descr,
            'price': price,
            'stock': 1500,
            'lifecycle_status': 'active',
            'package_type': pn.rsplit('-', 1)[-1] if '-' in pn and pn[-3:].startswith('TO') else 'TO-92',
            'parameters': {'catalog_version': 'v2'},
        }
        for pn, descr, price in rows
    ]


def ic_items(cats):
    rows = [
        ('NE555', 'ti', 'Универсальный таймер NE555, DIP-8 / SOIC-8.', Decimal('18.00')),
        ('LM358', 'ti', 'Сдвоенный операционный усилитель, single-supply, DIP-8.', Decimal('22.00')),
        ('LM324', 'ti', 'Четверной ОУ, single-supply, DIP-14.', Decimal('28.00')),
        ('LM741', 'ti', 'Классический операционный усилитель.', Decimal('18.00')),
        ('TL072', 'ti', 'JFET-вход сдвоенный ОУ, низкошумящий.', Decimal('38.00')),
        ('LM386', 'ti', 'Усилитель мощности звука 1 Вт, 4–12 В.', Decimal('45.00')),
        ('LM7805', 'st', 'Линейный регулятор +5 В, 1 А, TO-220.', Decimal('22.00')),
        ('LM7812', 'st', 'Линейный регулятор +12 В, 1 А, TO-220.', Decimal('22.00')),
        ('LM7905', 'st', 'Линейный регулятор -5 В, 1 А.', Decimal('24.00')),
        ('LM7912', 'st', 'Линейный регулятор -12 В, 1 А.', Decimal('24.00')),
        ('LM317T', 'st', 'Регулируемый линейный регулятор 1.2–37 В, 1.5 А.', Decimal('25.00')),
        ('AMS1117-3.3', 'other', 'LDO 3.3 В, 1 А, SOT-223.', Decimal('14.00')),
        ('AMS1117-5.0', 'other', 'LDO 5.0 В, 1 А, SOT-223.', Decimal('14.00')),
        ('LM2596', 'ti', 'Step-down DC-DC контроллер 3 А.', Decimal('55.00')),
        ('XL6009', 'other', 'Step-up DC-DC 4 А.', Decimal('70.00')),
        ('ATMEGA328P-PU', 'other', 'AVR микроконтроллер 32 КБ Flash, DIP-28.', Decimal('320.00')),
        ('ATTINY85', 'other', 'AVR микроконтроллер 8 КБ Flash, DIP-8.', Decimal('180.00')),
        ('74HC04', 'nxp', 'Шесть инверторов CMOS, DIP-14 / SOIC-14.', Decimal('22.00')),
        ('74HC08', 'nxp', 'Четыре 2-вх AND CMOS.', Decimal('22.00')),
        ('74HC32', 'nxp', 'Четыре 2-вх OR CMOS.', Decimal('22.00')),
        ('74HC74', 'nxp', 'Двойной D-триггер CMOS.', Decimal('25.00')),
        ('74HC595', 'nxp', '8-битный shift-регистр, latch-выход.', Decimal('30.00')),
        ('74HC165', 'nxp', '8-битный shift-регистр PISO.', Decimal('32.00')),
        ('MCP23017', 'other', 'I²C 16-канальный GPIO-expander, DIP-28.', Decimal('150.00')),
        ('DS1307', 'other', 'I²C real-time clock с батарейкой, DIP-8.', Decimal('110.00')),
        ('DS18B20', 'other', 'Цифровой датчик температуры 1-Wire, TO-92.', Decimal('120.00')),
        ('AT24C32', 'other', 'I²C EEPROM 32 Кбит, DIP-8.', Decimal('40.00')),
    ]
    return [
        {
            'name': f'{mfr.upper() if mfr in {"ti", "st", "nxp"} else "Generic"} {pn}',
            'category': cats['ics'],
            'part_number': pn,
            'manufacturer': mfr,
            'description': descr,
            'price': price,
            'stock': 800,
            'lifecycle_status': 'active',
            'package_type': 'DIP-8' if 'DIP-8' in descr else ('TO-220' if 'TO-220' in descr else 'DIP'),
            'parameters': {'catalog_version': 'v2'},
        }
        for pn, mfr, descr, price in rows
    ]


def inductor_items(cats):
    rows = [
        ('CD43-1uH', '1 мкГн, 2 А, SMD CD43.', Decimal('12.00')),
        ('CD43-10uH', '10 мкГн, 1.5 А, SMD CD43.', Decimal('14.00')),
        ('CD43-100uH', '100 мкГн, 800 мА, SMD CD43.', Decimal('16.00')),
        ('CD43-470uH', '470 мкГн, 400 мА, SMD.', Decimal('18.00')),
        ('AXIAL-10mH', '10 мГн, 100 мА, осевой выводной.', Decimal('22.00')),
        ('AXIAL-100mH', '100 мГн, 50 мА, осевой выводной.', Decimal('28.00')),
        ('AXIAL-1mH', '1 мГн, 200 мА, осевой выводной.', Decimal('20.00')),
        ('TOR-220uH', 'Тороидальный 220 мкГн, 3 А.', Decimal('45.00')),
    ]
    return [
        {
            'name': f'Würth {pn}',
            'category': cats['inductors'],
            'part_number': pn,
            'manufacturer': 'wurth',
            'description': descr,
            'price': price,
            'stock': 800,
            'lifecycle_status': 'active',
            'package_type': pn.split('-')[0],
            'parameters': {'catalog_version': 'v2'},
        }
        for pn, descr, price in rows
    ]


def connector_items(cats):
    rows = [
        ('USB-A-FEMALE-VERT', 'USB-A гнездо вертикальный THT.', Decimal('25.00')),
        ('USB-MICRO-B', 'USB Micro-B гнездо SMD.', Decimal('30.00')),
        ('USB-C-16PIN', 'USB Type-C гнездо 16 pin, SMD.', Decimal('55.00')),
        ('JST-XH-2P', 'Разъём JST XH 2-pin папа.', Decimal('8.00')),
        ('JST-XH-3P', 'Разъём JST XH 3-pin папа.', Decimal('10.00')),
        ('JST-XH-4P', 'Разъём JST XH 4-pin папа.', Decimal('12.00')),
        ('HEADER-1x40-2.54', 'Pin header 1×40, шаг 2.54 мм, ломается.', Decimal('25.00')),
        ('HEADER-2x40-2.54', 'Двухрядный pin header 2×40, шаг 2.54 мм.', Decimal('45.00')),
        ('HEADER-1x40-F-2.54', 'Female header 1×40, шаг 2.54 мм.', Decimal('30.00')),
        ('DUPONT-1x10-F', 'Дюпон 1×10 female.', Decimal('15.00')),
        ('DB9-MALE-THT', 'DB-9 вилка THT.', Decimal('45.00')),
        ('DB9-FEMALE-THT', 'DB-9 гнездо THT.', Decimal('45.00')),
        ('RJ45-8P8C', 'RJ45 гнездо THT, 8P8C.', Decimal('40.00')),
        ('DC-JACK-5.5x2.1', 'Разъём питания DC 5.5×2.1 мм.', Decimal('15.00')),
        ('SCREW-TERMINAL-2P', 'Винтовая клемма 2-pin, шаг 5.08 мм.', Decimal('18.00')),
        ('SCREW-TERMINAL-3P', 'Винтовая клемма 3-pin, шаг 5.08 мм.', Decimal('25.00')),
    ]
    return [
        {
            'name': pn.replace('-', ' '),
            'category': cats['connectors'],
            'part_number': pn,
            'manufacturer': 'other',
            'description': descr,
            'price': price,
            'stock': 1200,
            'lifecycle_status': 'active',
            'package_type': 'THT' if 'THT' in pn else 'SMD',
            'parameters': {'catalog_version': 'v2'},
        }
        for pn, descr, price in rows
    ]


def relay_items(cats):
    rows = [
        ('HL-1U-5V', 'Реле HL-1U 5 В, 1A, 1×NO, SPST.', Decimal('60.00')),
        ('SRD-05VDC-SL-C', 'Реле Songle 5 В, 10 А, SPDT.', Decimal('90.00')),
        ('SRD-12VDC-SL-C', 'Реле Songle 12 В, 10 А, SPDT.', Decimal('90.00')),
        ('JQX-105F-12V', 'Реле JQX-105F 12 В, 16 А, SPDT.', Decimal('140.00')),
        ('G5LE-1-12V', 'Реле Omron G5LE 12 В, 10 А.', Decimal('180.00')),
        ('SSR-25DA', 'Твёрдотельное реле DC-AC 25 А.', Decimal('350.00')),
    ]
    return [
        {
            'name': f'Реле {pn}',
            'category': cats['relays'],
            'part_number': pn,
            'manufacturer': 'other',
            'description': descr,
            'price': price,
            'stock': 400,
            'lifecycle_status': 'active',
            'package_type': 'THT',
            'parameters': {'catalog_version': 'v2'},
        }
        for pn, descr, price in rows
    ]


def module_items(cats):
    """Modules: Arduino, ESP, RPi, displays, sensors."""
    rows = [
        ('ARDUINO-UNO-R3', 'Arduino Uno R3 на ATmega328P, USB-B, 14 GPIO.', Decimal('1450.00')),
        ('ARDUINO-NANO', 'Arduino Nano на ATmega328, miniUSB.', Decimal('850.00')),
        ('ARDUINO-MEGA-2560', 'Arduino Mega 2560 на ATmega2560, 54 GPIO.', Decimal('2200.00')),
        ('ARDUINO-LEONARDO', 'Arduino Leonardo на ATmega32U4, HID over USB.', Decimal('1650.00')),
        ('ARDUINO-MICRO', 'Arduino Micro форм-фактор Nano с USB HID.', Decimal('1800.00')),
        ('ESP32-DEVKIT', 'ESP32 DevKit v1, dual-core 240 МГц, Wi-Fi + BT.', Decimal('650.00')),
        ('ESP32-S3', 'ESP32-S3 DevKit, AI-инструкции, USB native.', Decimal('1100.00')),
        ('ESP32-CAM', 'ESP32-CAM с OV2640 камерой и слотом microSD.', Decimal('850.00')),
        ('ESP8266-NODEMCU', 'NodeMCU v3 на ESP8266, USB-Serial CH340.', Decimal('320.00')),
        ('ESP8266-D1-MINI', 'WeMos D1 Mini, 80 МГц, micro-USB.', Decimal('250.00')),
        ('RPI-4B-4GB', 'Raspberry Pi 4B 4 ГБ RAM, USB 3.0, HDMI ×2.', Decimal('7500.00')),
        ('RPI-4B-8GB', 'Raspberry Pi 4B 8 ГБ RAM.', Decimal('9800.00')),
        ('RPI-ZERO-2W', 'Raspberry Pi Zero 2 W, четыре ядра Cortex-A53.', Decimal('2200.00')),
        ('RPI-PICO', 'Raspberry Pi Pico на RP2040, 2 ядра M0+.', Decimal('450.00')),
        ('RPI-PICO-W', 'Raspberry Pi Pico W с Wi-Fi.', Decimal('650.00')),
        ('STM32-BLUEPILL', 'BluePill STM32F103C8T6, 72 МГц.', Decimal('380.00')),
        # Дисплеи
        ('OLED-0.96-I2C', 'OLED 0.96", 128×64, SSD1306, I²C.', Decimal('320.00')),
        ('OLED-1.3-I2C', 'OLED 1.3", 128×64, SH1106, I²C.', Decimal('420.00')),
        ('LCD1602-I2C', 'LCD 16×2 с переходником I²C.', Decimal('280.00')),
        ('LCD2004-I2C', 'LCD 20×4 с I²C-модулем.', Decimal('450.00')),
        ('TFT-1.44-SPI', 'TFT 1.44" 128×128, ST7735, SPI.', Decimal('550.00')),
        ('TFT-2.4-TOUCH', 'TFT 2.4" 320×240 с резистивным touch.', Decimal('850.00')),
        # Сенсоры
        ('DHT11', 'Датчик температуры и влажности DHT11, 5 В.', Decimal('120.00')),
        ('DHT22', 'Точный датчик температуры/влажности DHT22.', Decimal('250.00')),
        ('BMP280', 'Датчик давления и температуры I²C/SPI.', Decimal('220.00')),
        ('BME280', 'Давление, температура, влажность I²C.', Decimal('380.00')),
        ('MPU6050', 'Акселерометр + гироскоп 6-DoF, I²C.', Decimal('220.00')),
        ('MPU9250', 'IMU 9-DoF: акселерометр + гироскоп + магнетометр.', Decimal('450.00')),
        ('HC-SR04', 'Ультразвуковой датчик расстояния 2–400 см.', Decimal('120.00')),
        ('HC-SR501', 'PIR-датчик движения, 5 В.', Decimal('140.00')),
        ('LDR-PHOTORES', 'Фоторезистор GL5528.', Decimal('15.00')),
        ('TCS3200', 'Цветовой сенсор RGB.', Decimal('320.00')),
        ('MAX30102', 'Pulse oximeter и heart-rate сенсор I²C.', Decimal('380.00')),
        ('MQ-2', 'Датчик газа (дым / LPG / CO).', Decimal('180.00')),
        ('MQ-135', 'Датчик качества воздуха.', Decimal('220.00')),
    ]
    return [
        {
            'name': pn.replace('-', ' '),
            'category': cats['modules'],
            'part_number': pn,
            'manufacturer': 'other',
            'description': descr,
            'price': price,
            'stock': 200,
            'lifecycle_status': 'active',
            'package_type': 'Module',
            'parameters': {'catalog_version': 'v2'},
        }
        for pn, descr, price in rows
    ]


def tool_items(cats):
    rows = [
        ('IRON-60W-T12', 'Паяльник 60 Вт с керамическим нагревателем, картриджи T12.', Decimal('2200.00')),
        ('IRON-908S', 'Паяльник Yihua 908S 60 Вт.', Decimal('1450.00')),
        ('STATION-T12-OLED', 'Паяльная станция T12 с OLED-дисплеем, цифровая.', Decimal('5500.00')),
        ('STATION-936', 'Паяльная станция HAKKO 936-аналог, 60 Вт.', Decimal('3800.00')),
        ('HOTAIR-858D', 'Термовоздушная станция 858D, 700 Вт.', Decimal('4500.00')),
        ('REWORK-2IN1', 'Ремонтная станция 2-в-1: паяльник + термофен.', Decimal('8500.00')),
        ('MULTIMETER-DT830B', 'Мультиметр DT830B 3.5-разрядный, базовая модель.', Decimal('580.00')),
        ('MULTIMETER-UT61E', 'Мультиметр UNI-T UT61E True RMS, 22000 отсчётов.', Decimal('4800.00')),
        ('MULTIMETER-FLUKE-87V', 'Прецизионный мультиметр Fluke 87V.', Decimal('45000.00')),
        ('OSC-USB-DS213', 'Карманный USB-осциллограф DS213, 4 канала, 100 МГц.', Decimal('22000.00')),
        ('OSC-RIGOL-DS1054Z', 'Цифровой осциллограф Rigol DS1054Z, 50 МГц, 4 канала.', Decimal('38000.00')),
        ('GENERATOR-FY6800', 'Двухканальный функциональный генератор FeelTech FY6800.', Decimal('15500.00')),
        ('LAB-PSU-30V-5A', 'Лабораторный БП 30 В × 5 А, цифровой.', Decimal('8500.00')),
        ('LAB-PSU-60V-3A', 'Лабораторный БП 60 В × 3 А.', Decimal('11000.00')),
        ('USBASP', 'USB-программатор AVR USBasp.', Decimal('350.00')),
        ('ST-LINK-V2', 'ST-Link V2 для STM32/STM8.', Decimal('650.00')),
        ('LOGIC-ANALYZER-8CH', 'Логический анализатор 8 каналов, 24 МГц.', Decimal('1450.00')),
        ('TWEEZERS-ESD', 'Антистатический пинцет ESD-13 прямой.', Decimal('320.00')),
        ('TWEEZERS-ESD-CURVED', 'Антистатический пинцет ESD-15 изогнутый.', Decimal('320.00')),
        ('LOUPE-30X', 'Лупа 30× с LED-подсветкой.', Decimal('850.00')),
        ('MICROSCOPE-USB', 'USB-микроскоп 1000× для пайки SMD.', Decimal('3500.00')),
        ('CUTTER-FLUSH', 'Кусачки боковые flush-cut для радиоэлектроники.', Decimal('1100.00')),
        ('STRIPPER-WIRE', 'Стриппер для проводов 0.2–6 мм².', Decimal('850.00')),
        ('HELPING-HANDS', 'Подставка «третья рука» с лупой и LED.', Decimal('1500.00')),
        ('PCB-VICE', 'Тиски для печатных плат с поворотным зажимом.', Decimal('2200.00')),
    ]
    return [
        {
            'name': pn.replace('-', ' '),
            'category': cats['tools'],
            'part_number': pn,
            'manufacturer': 'other',
            'description': descr,
            'price': price,
            'stock': 80,
            'lifecycle_status': 'active',
            'package_type': 'Tool',
            'parameters': {'catalog_version': 'v2'},
        }
        for pn, descr, price in rows
    ]


def consumable_items(cats):
    rows = [
        ('SOLDER-60-40-100G', 'Припой Sn60/Pb40 с канифолью, Ø1.0 мм, катушка 100 г.', Decimal('850.00')),
        ('SOLDER-LEAD-FREE-100G', 'Бессвинцовый припой SnAgCu, Ø0.8 мм, 100 г.', Decimal('1200.00')),
        ('SOLDER-PASTE-138', 'Паяльная паста Sn42Bi58 (138°C), 30 г.', Decimal('1450.00')),
        ('FLUX-RMA-50ML', 'Флюс RMA в шприце, 50 мл.', Decimal('480.00')),
        ('FLUX-NO-CLEAN', 'Флюс no-clean для безотмывной пайки, 30 мл.', Decimal('420.00')),
        ('FLUX-ROSIN-30G', 'Канифоль сосновая, банка 30 г.', Decimal('120.00')),
        ('SOLDER-WICK-2MM', 'Оплётка для удаления припоя 2 мм × 1.5 м.', Decimal('220.00')),
        ('SOLDER-WICK-3MM', 'Оплётка для удаления припоя 3 мм × 1.5 м.', Decimal('260.00')),
        ('DESOLDER-PUMP', 'Помпа-демонтажник вакуумная.', Decimal('420.00')),
        ('HEAT-SHRINK-KIT', 'Термоусадка набор 1–10 мм, 5 цветов.', Decimal('480.00')),
        ('HEAT-SHRINK-2MM-1M', 'Термоусадка 2 мм × 1 м, чёрная.', Decimal('40.00')),
        ('ELECTRICAL-TAPE-BLK', 'Изолента ПВХ 19 мм × 20 м, чёрная.', Decimal('80.00')),
        ('ELECTRICAL-TAPE-COLOR', 'Изолента 6 цветов набор.', Decimal('320.00')),
        ('WIRE-CU-22AWG-RED-5M', 'Монтажный провод медный, 22 AWG, красный, 5 м.', Decimal('180.00')),
        ('WIRE-CU-22AWG-BLACK-5M', 'Монтажный провод медный, 22 AWG, чёрный, 5 м.', Decimal('180.00')),
        ('WIRE-SILICON-18AWG-1M', 'Силиконовый провод 18 AWG, термостойкий, 1 м.', Decimal('220.00')),
        ('WIRE-PAIR-2x0.5MM', 'Парный провод 2×0.5 мм², 5 м.', Decimal('320.00')),
        ('JUMPER-MM-65PCS', 'Перемычки M-M 65 шт, разноцветные, 15-25 см.', Decimal('320.00')),
        ('JUMPER-MF-65PCS', 'Перемычки M-F 65 шт.', Decimal('320.00')),
        ('JUMPER-FF-65PCS', 'Перемычки F-F 65 шт.', Decimal('320.00')),
        ('BREADBOARD-830', 'Макетная плата 830 точек MB-102.', Decimal('420.00')),
        ('BREADBOARD-400', 'Мини макетная плата 400 точек.', Decimal('220.00')),
        ('BREADBOARD-2x830', 'Большая макетная плата 2×830.', Decimal('780.00')),
        ('PCB-PROTOBOARD-7x9', 'Универсальная плата 70×90 мм, шаг 2.54.', Decimal('120.00')),
        ('PCB-PROTOBOARD-9x15', 'Универсальная плата 90×150 мм.', Decimal('180.00')),
        ('ESD-WRIST-STRAP', 'Антистатический браслет с проводом.', Decimal('250.00')),
        ('ESD-MAT-30x60', 'Антистатический коврик 30×60 см.', Decimal('1850.00')),
        ('ALCOHOL-IPA-100ML', 'Изопропиловый спирт 99.9%, 100 мл.', Decimal('320.00')),
        ('PCB-CLEANER-200ML', 'Очиститель плат после пайки, 200 мл.', Decimal('580.00')),
        ('SOLDER-TIP-CLEANER', 'Очиститель жала металлическая стружка.', Decimal('320.00')),
    ]
    return [
        {
            'name': pn.replace('-', ' '),
            'category': cats['consumables'],
            'part_number': pn,
            'manufacturer': 'other',
            'description': descr,
            'price': price,
            'stock': 500,
            'lifecycle_status': 'active',
            'package_type': 'Consumable',
            'parameters': {'catalog_version': 'v2'},
        }
        for pn, descr, price in rows
    ]


# ============================================================================
# Command
# ============================================================================


class Command(BaseCommand):
    help = (
        'Populate catalog with ~300 v2 products: extended radio components, '
        'Arduino/ESP/RPi modules, professional tools and consumables.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Remove existing v2 products (parameters.catalog_version=v2) before re-adding.',
        )
        parser.add_argument('--dry-run', action='store_true', help='Show summary without writing to DB.')

    def handle(self, *args, **options):
        # Resolve / create categories
        category_specs = [
            ('Резисторы', 'resistors'),
            ('Конденсаторы', 'capacitors'),
            ('Транзисторы', 'transistors'),
            ('Микросхемы', 'ics'),
            ('Диоды', 'diodes'),
            ('Дроссели и катушки', 'inductors'),
            ('Разъёмы', 'connectors'),
            ('Реле', 'relays'),
            ('Модули и платы', 'modules'),
            ('Инструменты', 'tools'),
            ('Расходники', 'consumables'),
        ]
        cats = {}
        for name, slug in category_specs:
            cat, created = Category.objects.get_or_create(
                slug=slug,
                defaults={'name': name, 'description': f'Категория «{name}» — DOLG catalog v2.'},
            )
            cats[slug] = cat
            if created:
                self.stdout.write(f'+ Created category: {name} ({slug})')

        # Optional clear
        if options['clear']:
            qs = Product.objects.filter(parameters__catalog_version='v2')
            count = qs.count()
            if not options['dry_run']:
                qs.delete()
            self.stdout.write(
                self.style.WARNING(f'Removed {count} v2 products{" (dry-run)" if options["dry_run"] else ""}')
            )

        # Build all items
        all_items = (
            resistor_items(cats)
            + capacitor_items(cats)
            + diode_items(cats)
            + transistor_items(cats)
            + ic_items(cats)
            + inductor_items(cats)
            + connector_items(cats)
            + relay_items(cats)
            + module_items(cats)
            + tool_items(cats)
            + consumable_items(cats)
        )

        if options['dry_run']:
            self.stdout.write(
                self.style.SUCCESS(f'[dry-run] Would create/update {len(all_items)} v2 products.')
            )
            # Per-category breakdown
            from collections import Counter

            counter = Counter(item['category'].slug for item in all_items)
            for slug, n in counter.most_common():
                self.stdout.write(f'  · {slug}: {n}')
            return

        created_count = 0
        updated_count = 0
        with transaction.atomic():
            for item in all_items:
                slug = _make_slug(item['part_number'] or item['name'])
                defaults = dict(item)
                obj, created = Product.objects.update_or_create(slug=slug, defaults=defaults)
                if created:
                    created_count += 1
                else:
                    updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'v2 catalog: {created_count} created · {updated_count} updated · '
                f'{len(all_items)} total in 11 categories'
            )
        )
