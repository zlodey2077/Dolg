"""
Наполняет Product.parameters для консьюмер-электроники.
Базовые спеки берутся по слагу категории, плюс частичные оверрайды
по подстроке в имени (для флагманов).

Usage:
  python manage.py enrich_product_parameters          # только где пусто
  python manage.py enrich_product_parameters --force  # перезаписать всё
"""

from django.core.management.base import BaseCommand

from shop.models import Product

# Типовое «применение» по slug категории — отображается отдельным блоком
# на product_detail.html (см. секцию «💡 Типичное применение»). Не лезет
# в чип-превью карточки каталога — слишком длинный текст. Per-product
# оверрайды живут в NAME_OVERRIDES (поле 'applications').
CATEGORY_APPLICATIONS = {
    'smartphones': 'Личное использование, фотография, мессенджеры, мобильные игры, навигация, мобильный банк.',
    'laptops': 'Офис, программирование, видеомонтаж, инженерные расчёты, удалённая работа.',
    'tablets': 'Скетчинг, чтение, заметки в учёбе, лёгкий офис, потоковое видео.',
    'accessories': 'Расширение функционала смартфона/ПК — зарядка, передача данных, подключение периферии.',
    'cpu': 'Игровые ПК, рабочие станции для рендера/CAD, виртуализация, домашние серверы.',
    'gpu': 'Игры в 4K, ML/AI inference и обучение, видеомонтаж, CAD и 3D-моделирование.',
    'ram': 'Многозадачность, виртуальные машины, тяжёлые DAW/CAD-приложения, ML-датасеты.',
    'ssd': 'Системный диск ОС, кеш игр AAA, рабочие проекты, NAS-кэш для видеомонтажа.',
    'psu': 'Питание игровых/рабочих ПК, серверов, рендер-ферм. Подбирается с запасом 30-50% от пиковой нагрузки.',
    'cooling': 'Охлаждение CPU в стресс-нагрузках — игры, рендер, компиляция, оверклокинг.',
    'monitors': 'Геймдев, дизайн (sRGB/AdobeRGB), программирование с длинным кодом, монтаж видео.',
    'motherboards': 'Основа сборки ПК — определяет сокет, поколение DDR, число M.2 и PCIe-линий.',
    # РЭБ — для учебных схем + DIY-проектов
    'resistors': 'Делители напряжения, ограничители тока для LED, pull-up/pull-down в цифровых схемах, шунты для измерения тока.',
    'capacitors': 'Фильтрация питания (блокировка пульсаций), развязка по питанию микросхем, времязадающие цепи RC, разделение DC/AC.',
    'inductors': 'DC-DC преобразователи, EMI-фильтры на входе питания, RF-цепи (тюнинг частоты), фильтры в БП.',
    'transistors': 'Усилители звука и сигналов, ключи для управления LED-лентами и моторами, генераторы, цифровая логика.',
    'diodes': 'Выпрямители в БП (мост Греца), защита от обратной полярности, ограничители напряжения, индикация (LED).',
    'ics': 'Цифровая логика (таймеры, счётчики), аналоговая обработка (операционные усилители, ADC/DAC), стабилизаторы (LDO), микроконтроллеры.',
    'connectors': 'Соединение модулей в DIY и прототипировании, отладка по UART/SPI/I2C, подача питания на платы.',
    'relays': 'Коммутация сильноточных нагрузок (220 В, моторы, лампы) от слаботочных управляющих сигналов 3.3/5/12 В.',
    'modules': 'Быстрое прототипирование: Arduino/Raspberry Pi/ESP, датчики, дисплеи, связь и учебные лабораторные стенды.',
    'tools': 'Измерение, пайка, отладка, диагностика плат, подготовка прототипов и проверка результатов схемотехнических расчетов.',
    'consumables': 'Расходные материалы для пайки, макетирования, изоляции, чистки, ESD-защиты и монтажа проводных соединений.',
}

# Базовые характеристики на категорию
CATEGORY_DEFAULTS = {
    'smartphones': {
        'screen_size': '6.5"',
        'display': 'OLED, 120 Hz',
        'ram': '8 ГБ',
        'storage': '256 ГБ',
        'battery': '4500 мА·ч',
        'os': 'Android / iOS',
        'connectivity': '5G, Wi-Fi 6, Bluetooth 5.3',
        'weight': '200 г',
    },
    'laptops': {
        'screen_size': '16"',
        'display': 'IPS, 144 Hz',
        'cpu': 'Intel Core i7 / Ryzen 7',
        'ram': '16 ГБ DDR5',
        'storage': '1 ТБ NVMe SSD',
        'gpu': 'Встроенная / дискретная',
        'battery': '65 Вт·ч',
        'weight': '1.8 кг',
        'os': 'Windows 11 / macOS',
    },
    'tablets': {
        'screen_size': '11"',
        'display': 'IPS / OLED',
        'ram': '8 ГБ',
        'storage': '256 ГБ',
        'battery': '8000 мА·ч',
        'connectivity': 'Wi-Fi 6, Bluetooth 5.2',
        'stylus': 'поддерживается',
    },
    'accessories': {
        'type': 'Аксессуар',
        'connectivity': 'USB-C / Bluetooth',
    },
    'cpu': {
        'cores': '16',
        'threads': '32',
        'base_clock': '3.5 ГГц',
        'boost_clock': '5.0 ГГц',
        'cache_l3': '32 МБ',
        'socket': 'LGA1700 / AM5',
        'tdp': '125 Вт',
        'process': 'Intel 7 / TSMC 5nm',
    },
    'gpu': {
        'gpu_chip': 'RTX 4080 / RX 7800 XT',
        'vram': '16 ГБ GDDR6X',
        'memory_bus': '256-бит',
        'interface': 'PCIe 4.0 x16',
        'outputs': 'HDMI 2.1, 3× DisplayPort 1.4',
        'tdp': '285 Вт',
        'power_conn': '1× 16-pin',
    },
    'ram': {
        'type': 'DDR5',
        'capacity': '32 ГБ (2×16)',
        'frequency': '6000 МГц',
        'latency': 'CL30',
        'voltage': '1.35 В',
        'form_factor': 'DIMM',
        'rgb': 'есть',
    },
    'ssd': {
        'capacity': '1 ТБ',
        'interface': 'PCIe 4.0 x4 (NVMe)',
        'form_factor': 'M.2 2280',
        'read_speed': '7000 МБ/с',
        'write_speed': '6000 МБ/с',
        'tbw': '600 ТБ',
        'dram_cache': 'есть',
    },
    'psu': {
        'wattage': '850 Вт',
        'form_factor': 'ATX',
        'certification': '80 Plus Gold',
        'modular': 'Полностью модульный',
        'efficiency': '92%',
        'fan_size': '135 мм',
    },
    'cooling': {
        'type': 'Воздушное / Жидкостное',
        'tdp_rated': '250 Вт',
        'fan_count': '2',
        'fan_size': '120 мм',
        'rgb': 'ARGB',
        'socket': 'Intel LGA1700 / AMD AM5',
    },
    'monitors': {
        'screen_size': '27"',
        'resolution': '2560×1440 (QHD)',
        'panel': 'IPS',
        'refresh_rate': '165 Hz',
        'response_time': '1 мс',
        'hdr': 'HDR400',
        'inputs': 'HDMI 2.1, DisplayPort 1.4',
    },
    'motherboards': {
        'socket': 'LGA1700 / AM5',
        'chipset': 'Z790 / X670',
        'form_factor': 'ATX',
        'ram_slots': '4× DIMM DDR5',
        'pcie': 'PCIe 5.0 x16',
        'm2_slots': '4× M.2',
        'network': '2.5 Gbps Ethernet',
    },
    'modules': {
        'type': 'Модуль',
        'supply_voltage': '3.3/5 В',
        'logic_level': '3.3/5 В',
        'interface': 'GPIO / I2C / SPI / UART',
        'mounting': 'module',
    },
    'tools': {
        'type': 'Инструмент',
    },
    'consumables': {
        'type': 'Расходник',
    },
}

# Per-product оверрайды — по подстроке в name (case-insensitive)
NAME_OVERRIDES = [
    (
        'iphone 15 pro',
        {
            'chip': 'Apple A17 Pro',
            'screen_size': '6.1"',
            'display': 'Super Retina XDR, ProMotion 120 Hz',
            'camera': '48 MP главная + 12 MP ультраширокая + 12 MP телеобъектив',
            'storage': '256 ГБ',
            'ram': '8 ГБ',
            'battery': '3274 мА·ч',
            'charging': '20 Вт USB-C / 15 Вт MagSafe',
            'os': 'iOS 17',
            'weight': '187 г',
            'connectivity': '5G, Wi-Fi 6E, USB-C',
        },
    ),
    (
        'galaxy s24 ultra',
        {
            'chip': 'Snapdragon 8 Gen 3',
            'screen_size': '6.8"',
            'display': 'Dynamic AMOLED 2X, 120 Hz',
            'camera': '200 MP главная + 50 MP перископ + 10 MP + 12 MP',
            'storage': '512 ГБ',
            'ram': '12 ГБ',
            'battery': '5000 мА·ч',
            'charging': '45 Вт Super Fast / 15 Вт беспроводная',
            'os': 'Android 14, One UI 6.1',
            'weight': '232 г',
        },
    ),
    (
        'oneplus 12',
        {
            'chip': 'Snapdragon 8 Gen 3',
            'screen_size': '6.82"',
            'display': 'LTPO AMOLED, 120 Hz',
            'camera': '50 MP Hasselblad + 64 MP перископ + 48 MP',
            'storage': '256 ГБ',
            'ram': '12 ГБ',
            'battery': '5400 мА·ч',
            'charging': '100 Вт SuperVOOC + 50 Вт беспроводная',
        },
    ),
    (
        'macbook pro 16',
        {
            'cpu': 'Apple M3 Max (16C)',
            'gpu': 'Apple M3 Max (40C)',
            'ram': '36 ГБ объединённой памяти',
            'storage': '1 ТБ SSD',
            'screen_size': '16.2"',
            'display': 'Liquid Retina XDR Mini-LED, 120 Hz',
            'battery': '100 Вт·ч (до 22 ч)',
            'weight': '2.16 кг',
            'os': 'macOS Sonoma',
        },
    ),
    (
        'rog zephyrus g16',
        {
            'cpu': 'Intel Core i9-14900HX',
            'gpu': 'NVIDIA RTX 4090 Laptop (16 ГБ)',
            'ram': '32 ГБ DDR5-5600',
            'storage': '2 ТБ NVMe SSD',
            'screen_size': '16"',
            'display': 'QHD+ IPS, 240 Hz',
            'battery': '90 Вт·ч',
            'weight': '2.1 кг',
            'os': 'Windows 11 Pro',
        },
    ),
    (
        'thinkpad x1 carbon',
        {
            'cpu': 'Intel Core i7-1365U',
            'ram': '16 ГБ LPDDR5',
            'storage': '512 ГБ NVMe SSD',
            'screen_size': '14"',
            'display': 'IPS, 400 нит',
            'battery': '57 Вт·ч (до 15 ч)',
            'weight': '1.12 кг',
            'os': 'Windows 11 Pro',
            'chassis': 'Углеволокно',
        },
    ),
    (
        'ipad pro 12.9',
        {
            'chip': 'Apple M2',
            'screen_size': '12.9"',
            'display': 'Liquid Retina XDR Mini-LED, 120 Hz',
            'ram': '8 ГБ',
            'storage': '256 ГБ',
            'battery': '40.88 Вт·ч',
            'stylus': 'Apple Pencil Pro',
            'os': 'iPadOS 17',
            'weight': '682 г',
        },
    ),
    (
        'i9-14900k',
        {
            'cores': '24 (8P + 16E)',
            'threads': '32',
            'base_clock': '3.2 ГГц',
            'boost_clock': '6.0 ГГц',
            'cache_l3': '36 МБ',
            'socket': 'LGA1700',
            'tdp': '125 Вт (PL1) / 253 Вт (PL2)',
            'process': 'Intel 7',
            'igpu': 'UHD Graphics 770',
        },
    ),
    (
        'i7-14700k',
        {
            'cores': '20 (8P + 12E)',
            'threads': '28',
            'base_clock': '3.4 ГГц',
            'boost_clock': '5.6 ГГц',
            'cache_l3': '33 МБ',
            'socket': 'LGA1700',
            'tdp': '125 Вт (PL1) / 253 Вт (PL2)',
            'process': 'Intel 7',
            'igpu': 'UHD Graphics 770',
        },
    ),
    (
        'ryzen 9 7950x3d',
        {
            'cores': '16',
            'threads': '32',
            'base_clock': '4.2 ГГц',
            'boost_clock': '5.7 ГГц',
            'cache_l3': '128 МБ (3D V-Cache)',
            'socket': 'AM5',
            'tdp': '120 Вт',
            'process': 'TSMC 5nm',
            'chipset_support': 'X670E / B650',
        },
    ),
    (
        'ryzen 5 7600x',
        {
            'cores': '6',
            'threads': '12',
            'base_clock': '4.7 ГГц',
            'boost_clock': '5.3 ГГц',
            'cache_l3': '32 МБ',
            'socket': 'AM5',
            'tdp': '105 Вт',
            'process': 'TSMC 5nm',
        },
    ),
    # --- GPU --- (порядок важен: 'rtx 4080 super' до 'rtx 4080', иначе
    # super-карта получит обычные 4080-спеки)
    (
        'rtx 4090',
        {
            'gpu_chip': 'NVIDIA RTX 4090',
            'cuda_cores': '16384',
            'vram': '24 ГБ GDDR6X',
            'memory_bus': '384-бит',
            'base_clock': '2235 МГц',
            'boost_clock': '2520 МГц',
            'interface': 'PCIe 4.0 x16',
            'tdp': '450 Вт',
            'power_conn': '1× 16-pin (600 Вт)',
            'outputs': 'HDMI 2.1, 3× DisplayPort 1.4a',
        },
    ),
    (
        'rtx 4080 super',
        {
            'gpu_chip': 'NVIDIA RTX 4080 SUPER',
            'cuda_cores': '10240',
            'vram': '16 ГБ GDDR6X',
            'memory_bus': '256-бит',
            'boost_clock': '2550 МГц',
            'tdp': '320 Вт',
            'interface': 'PCIe 4.0 x16',
            'power_conn': '1× 16-pin',
            'outputs': 'HDMI 2.1, 3× DisplayPort 1.4a',
        },
    ),
    (
        'rtx 4080',
        {
            'gpu_chip': 'NVIDIA RTX 4080',
            'cuda_cores': '9728',
            'vram': '16 ГБ GDDR6X',
            'memory_bus': '256-бит',
            'boost_clock': '2505 МГц',
            'tdp': '320 Вт',
            'interface': 'PCIe 4.0 x16',
            'power_conn': '1× 16-pin',
            'outputs': 'HDMI 2.1, 3× DisplayPort 1.4a',
        },
    ),
    (
        'rtx 4070 ti',
        {
            'gpu_chip': 'NVIDIA RTX 4070 Ti',
            'cuda_cores': '7680',
            'vram': '12 ГБ GDDR6X',
            'memory_bus': '192-бит',
            'boost_clock': '2610 МГц',
            'tdp': '285 Вт',
            'interface': 'PCIe 4.0 x16',
            'power_conn': '1× 16-pin',
            'outputs': 'HDMI 2.1, 3× DisplayPort 1.4a',
        },
    ),
    (
        'rx 7900 xtx',
        {
            'gpu_chip': 'AMD Radeon RX 7900 XTX',
            'stream_processors': '6144',
            'vram': '24 ГБ GDDR6',
            'memory_bus': '384-бит',
            'boost_clock': '2500 МГц',
            'tdp': '355 Вт',
            'interface': 'PCIe 4.0 x16',
            'power_conn': '2× 8-pin',
            'outputs': 'HDMI 2.1, 2× DisplayPort 2.1, USB-C',
        },
    ),
    # --- Tablets ---
    (
        'galaxy tab s9 ultra',
        {
            'chip': 'Snapdragon 8 Gen 2 for Galaxy',
            'screen_size': '14.6"',
            'display': 'Dynamic AMOLED 2X, 120 Hz',
            'ram': '12 ГБ',
            'storage': '256 ГБ',
            'battery': '11200 мА·ч',
            'connectivity': 'Wi-Fi 6E, Bluetooth 5.3, опц. 5G',
            'stylus': 'S Pen (в комплекте)',
            'os': 'Android 13, One UI',
            'weight': '732 г',
        },
    ),
    # --- PSU --- (все 4 имели одинаковые "850 Вт / 92% / 80 Plus Gold")
    (
        'hx850 platinum',
        {
            'wattage': '850 Вт',
            'form_factor': 'ATX',
            'certification': '80 Plus Platinum',
            'modular': 'Полностью модульный',
            'efficiency': '92%',
            'fan_size': '135 мм',
        },
    ),
    (
        'supernova gt 1000',
        {
            'wattage': '1000 Вт',
            'form_factor': 'ATX',
            'certification': '80 Plus Gold',
            'modular': 'Полностью модульный',
            'efficiency': '90%',
            'fan_size': '130 мм',
        },
    ),
    (
        'focus plus 750',
        {
            'wattage': '750 Вт',
            'form_factor': 'ATX',
            'certification': '80 Plus Gold',
            'modular': 'Полностью модульный',
            'efficiency': '90%',
            'fan_size': '120 мм',
        },
    ),
    (
        'toughpower 650',
        {
            'wattage': '650 Вт',
            'form_factor': 'ATX',
            'certification': '80 Plus Gold',
            'modular': 'Полу-модульный',
            'efficiency': '89%',
            'fan_size': '140 мм',
        },
    ),
    # --- Cooling ---
    (
        'noctua nh-d15',
        {
            'type': 'Воздушное (dual-tower)',
            'tdp_rated': '220 Вт',
            'fan_count': '2',
            'fan_size': '140 мм',
            'rgb': 'нет (Chromax)',
            'socket': 'Intel LGA1700/1200/115x, AMD AM5/AM4',
        },
    ),
    (
        'h150i elite capellix',
        {
            'type': 'Жидкостное AIO (360 мм)',
            'tdp_rated': '280 Вт',
            'fan_count': '3',
            'fan_size': '120 мм',
            'rgb': 'iCUE Capellix',
            'socket': 'Intel LGA1700/1200, AMD AM5/AM4',
        },
    ),
    (
        'dark rock pro',
        {
            'type': 'Воздушное (dual-tower, тихое)',
            'tdp_rated': '250 Вт',
            'fan_count': '2',
            'fan_size': '120/135 мм',
            'rgb': 'нет',
            'socket': 'Intel LGA1700/1200/2066, AMD AM5/AM4',
        },
    ),
    (
        'freezer 50 tr',
        {
            'type': 'Воздушное (для Threadripper)',
            'tdp_rated': '300 Вт',
            'fan_count': '2',
            'fan_size': '140 мм',
            'rgb': 'ARGB',
            'socket': 'AMD sTRX4 / TR4 / sWRX8',
        },
    ),
    # --- Monitors ---
    (
        'samsung m7 smart monitor 32',
        {
            'screen_size': '32"',
            'resolution': '3840×2160 (4K UHD)',
            'panel': 'VA',
            'refresh_rate': '60 Hz',
            'response_time': '4 мс (GtG)',
            'hdr': 'HDR10',
            'inputs': 'HDMI 2.0, USB-C 65 Вт, SmartTV-режим',
        },
    ),
    (
        'lg ultrawide 34',
        {
            'screen_size': '34" (21:9)',
            'resolution': '3440×1440 (UWQHD)',
            'panel': 'IPS Nano',
            'refresh_rate': '160 Hz',
            'response_time': '1 мс (GtG)',
            'hdr': 'HDR10 (DisplayHDR 400)',
            'inputs': 'HDMI 2.0, 2× DisplayPort 1.4',
        },
    ),
    (
        'asus proart pa278qv',
        {
            'screen_size': '27"',
            'resolution': '2560×1440 (QHD)',
            'panel': 'IPS (100% sRGB / 100% Rec.709)',
            'refresh_rate': '75 Hz',
            'response_time': '5 мс (GtG)',
            'hdr': 'нет',
            'inputs': 'HDMI 1.4, DisplayPort 1.2, mini-DP, USB-hub',
        },
    ),
    (
        'g273qf',
        {
            'screen_size': '27"',
            'resolution': '2560×1440 (QHD)',
            'panel': 'IPS Rapid',
            'refresh_rate': '165 Hz',
            'response_time': '1 мс (GtG)',
            'hdr': 'HDR400',
            'inputs': 'HDMI 2.0, 2× DisplayPort 1.4',
        },
    ),
    # --- Motherboards ---
    (
        'rog maximus z890-e',
        {
            'socket': 'LGA1851',
            'chipset': 'Intel Z890',
            'form_factor': 'ATX',
            'ram_slots': '4× DIMM DDR5-8800 OC',
            'pcie': '1× PCIe 5.0 x16',
            'm2_slots': '5× M.2 (4× PCIe 5.0)',
            'network': '5 Гбит/с + Wi-Fi 7',
        },
    ),
    (
        'x870e-e',
        {
            'socket': 'AM5',
            'chipset': 'AMD X870E',
            'form_factor': 'ATX',
            'ram_slots': '4× DIMM DDR5-8000 OC',
            'pcie': '2× PCIe 5.0 x16',
            'm2_slots': '4× M.2 (PCIe 5.0)',
            'network': '5 Гбит/с + Wi-Fi 7',
        },
    ),
    (
        'b850 aorus master',
        {
            'socket': 'AM5',
            'chipset': 'AMD B850',
            'form_factor': 'ATX',
            'ram_slots': '4× DIMM DDR5-8000 OC',
            'pcie': '1× PCIe 5.0 x16',
            'm2_slots': '4× M.2 (PCIe 5.0)',
            'network': '2.5 Гбит/с + Wi-Fi 7',
        },
    ),
    (
        'pro b850-plus',
        {
            'socket': 'AM5',
            'chipset': 'AMD B850',
            'form_factor': 'ATX',
            'ram_slots': '4× DIMM DDR5-7200 OC',
            'pcie': '1× PCIe 5.0 x16',
            'm2_slots': '3× M.2 (PCIe 5.0)',
            'network': '2.5 Гбит/с Ethernet',
        },
    ),
    # --- RAM ---
    (
        'fury beast ddr5 32',
        {
            'type': 'DDR5',
            'capacity': '32 ГБ (2×16)',
            'frequency': '6000 МГц',
            'latency': 'CL36',
            'voltage': '1.35 В',
            'form_factor': 'DIMM',
            'rgb': 'нет',
        },
    ),
    (
        'dominator platinum ddr5 64',
        {
            'type': 'DDR5',
            'capacity': '64 ГБ (2×32)',
            'frequency': '6400 МГц',
            'latency': 'CL32',
            'voltage': '1.4 В',
            'form_factor': 'DIMM',
            'rgb': 'Capellix RGB (12 светодиодов)',
        },
    ),
    (
        'trident z5 ddr5 16',
        {
            'type': 'DDR5',
            'capacity': '16 ГБ (1×16)',
            'frequency': '7200 МГц',
            'latency': 'CL34',
            'voltage': '1.4 В',
            'form_factor': 'DIMM',
            'rgb': 'RGB-полоса',
        },
    ),
    (
        'hyperx fury ddr4',
        {
            'type': 'DDR4',
            'capacity': '16 ГБ (2×8)',
            'frequency': '3200 МГц',
            'latency': 'CL16',
            'voltage': '1.35 В',
            'form_factor': 'DIMM',
            'rgb': 'нет',
        },
    ),
    # --- SSD ---
    (
        'samsung 990 pro',
        {
            'capacity': '2 ТБ',
            'interface': 'PCIe 4.0 x4 (NVMe)',
            'form_factor': 'M.2 2280',
            'read_speed': '7450 МБ/с',
            'write_speed': '6900 МБ/с',
            'tbw': '1200 ТБ',
            'dram_cache': '2 ГБ LPDDR4',
        },
    ),
    (
        'sn850x',
        {
            'capacity': '1 ТБ',
            'interface': 'PCIe 4.0 x4 (NVMe)',
            'form_factor': 'M.2 2280',
            'read_speed': '7300 МБ/с',
            'write_speed': '6300 МБ/с',
            'tbw': '600 ТБ',
            'dram_cache': '1 ГБ DDR4',
        },
    ),
    (
        'p5 plus',
        {
            'capacity': '500 ГБ',
            'interface': 'PCIe 4.0 x4 (NVMe)',
            'form_factor': 'M.2 2280',
            'read_speed': '6600 МБ/с',
            'write_speed': '4000 МБ/с',
            'tbw': '300 ТБ',
            'dram_cache': '512 МБ',
        },
    ),
    (
        'kingston nv2',
        {
            'capacity': '2 ТБ',
            'interface': 'PCIe 4.0 x4 (NVMe)',
            'form_factor': 'M.2 2280',
            'read_speed': '3500 МБ/с',
            'write_speed': '2800 МБ/с',
            'tbw': '640 ТБ',
            'dram_cache': 'нет (HMB)',
        },
    ),
    # --- Accessories (кабели/зарядки) ---
    (
        'samsung 25w super fast',
        {
            'type': 'Зарядное устройство',
            'wattage': '25 Вт',
            'connectivity': 'USB-C (Super Fast Charging, USB-PD 3.0 PPS)',
            'charging': 'Super Fast Charging 25 Вт',
            'weight': '45 г',
        },
    ),
    (
        'usb-c кабель anker',
        {
            'type': 'Кабель USB-C ↔ USB-C',
            'length': '3 м',
            'connectivity': 'USB 2.0 (480 Мбит/с)',
            'wattage': 'до 100 Вт PD',
            'weight': '95 г',
        },
    ),
    (
        'модульные кабели corsair',
        {
            'type': 'Комплект модульных кабелей PSU',
            'length': '60 см',
            'connectivity': 'Совместим с Corsair RM/HX/AX',
            'rgb': 'оплётка Premium',
            'weight': '350 г',
        },
    ),
    (
        'hdmi 2.1 кабель',
        {
            'type': 'Кабель HDMI 2.1 (Ultra High Speed)',
            'length': '3 м',
            'connectivity': 'HDMI 2.1',
            'bandwidth': '48 Гбит/с',
            'resolution': 'до 8K@60 / 4K@120',
            'weight': '120 г',
        },
    ),
    (
        'displayport 1.4 кабель',
        {
            'type': 'Кабель DisplayPort 1.4',
            'length': '2 м',
            'connectivity': 'DisplayPort 1.4',
            'bandwidth': '32.4 Гбит/с (HBR3)',
            'resolution': 'до 8K@60 / 4K@120 HDR',
            'weight': '90 г',
        },
    ),
    (
        'airpods pro',
        {
            'type': 'Вставные TWS',
            'anc': 'Активное шумоподавление',
            'driver': 'Динамический',
            'codec': 'AAC',
            'battery_earbuds': '6 ч (с ANC)',
            'battery_case': '30 ч суммарно',
            'charging': 'USB-C / MagSafe / Qi',
            'weight': '5.3 г (наушник)',
        },
    ),
]


TEXT_FIXUPS = {
    # В раннем seed попал тестовый товар "T1 OK". Оставляем slug для
    # совместимости ссылок, но превращаем карточку в нормальный внешний SSD.
    't1-ok': {
        'name': 'Samsung Portable SSD T7 1TB',
        'description': 'Внешний SSD USB-C для переноса проектов, резервных копий и инженерных архивов.',
        'manufacturer': 'samsung',
    },
    # Расходники: приводим seed-товары к нормальной витрине, без BREADBOARD/Consumable
    # в карточках. Сами характеристики остаются в Product.parameters.
    'pcb-protoboard-7x9': {
        'name': 'Макетная PCB 7×9 см',
        'package_type': 'Макетирование',
    },
    'pcb-protoboard-9x15': {
        'name': 'Макетная PCB 9×15 см',
        'package_type': 'Макетирование',
    },
    'breadboard-2x830': {
        'name': 'Набор макетных плат 2×830',
        'package_type': 'Макетирование',
    },
    'breadboard-400': {
        'name': 'Макетная плата 400 точек',
        'package_type': 'Макетирование',
    },
    'breadboard-830': {
        'name': 'Макетная плата 830 точек',
        'package_type': 'Макетирование',
    },
    'jumper-mm-65pcs': {
        'name': 'Перемычки Dupont M-M, 65 шт.',
        'package_type': 'Проводники',
    },
    'jumper-mf-65pcs': {
        'name': 'Перемычки Dupont M-F, 65 шт.',
        'package_type': 'Проводники',
    },
    'jumper-ff-65pcs': {
        'name': 'Перемычки Dupont F-F, 65 шт.',
        'package_type': 'Проводники',
    },
    'solder-paste-138': {
        'name': 'Паяльная паста Sn42Bi58, 138 °C',
        'package_type': 'Пайка',
    },
    'solder-lead-free-100g': {
        'name': 'Бессвинцовый припой SnAgCu, 100 г',
        'package_type': 'Пайка',
    },
    'solder-60-40-100g': {
        'name': 'Припой Sn60Pb40, 100 г',
        'package_type': 'Пайка',
    },
    'flux-no-clean': {
        'name': 'Безотмывочный флюс 10 мл',
        'package_type': 'Пайка',
    },
    'flux-rma-50ml': {
        'name': 'Флюс RMA 50 мл',
        'package_type': 'Пайка',
    },
    'flux-rosin-30g': {
        'name': 'Канифольный флюс 30 г',
        'package_type': 'Пайка',
    },
    'solder-tip-cleaner': {
        'name': 'Очиститель жала паяльника',
        'package_type': 'Пайка',
    },
    'alcohol-ipa-100ml': {
        'name': 'Изопропиловый спирт 99%, 100 мл',
        'package_type': 'Чистка',
    },
    'pcb-cleaner-200ml': {
        'name': 'Очиститель плат 200 мл',
        'package_type': 'Чистка',
    },
    'heat-shrink-2mm-1m': {
        'name': 'Термоусадка 2 мм, 1 м',
        'package_type': 'Изоляция',
    },
    'heat-shrink-kit': {
        'name': 'Набор термоусадки 1–10 мм',
        'package_type': 'Изоляция',
    },
    'electrical-tape-blk': {
        'name': 'Изолента черная 19 мм',
        'package_type': 'Изоляция',
    },
    'electrical-tape-color': {
        'name': 'Набор цветной изоленты',
        'package_type': 'Изоляция',
    },
    'wire-cu-22awg-red-5m': {
        'name': 'Провод монтажный 22 AWG, красный 5 м',
        'package_type': 'Провод',
    },
    'wire-cu-22awg-black-5m': {
        'name': 'Провод монтажный 22 AWG, черный 5 м',
        'package_type': 'Провод',
    },
    'wire-silicon-18awg-1m': {
        'name': 'Силиконовый провод 18 AWG, 1 м',
        'package_type': 'Провод',
    },
    'wire-pair-2x05mm': {
        'name': 'Двухжильный провод 2×0.5 мм²',
        'package_type': 'Провод',
    },
    'solder-wick-2mm': {
        'name': 'Оплетка для выпайки 2 мм',
        'package_type': 'Выпайка',
    },
    'solder-wick-3mm': {
        'name': 'Оплетка для выпайки 3 мм',
        'package_type': 'Выпайка',
    },
    'desolder-pump': {
        'name': 'Вакуумный оловоотсос',
        'package_type': 'Выпайка',
    },
    'esd-mat-30x60': {
        'name': 'Антистатический коврик 30×60 см',
        'package_type': 'ESD',
    },
    'esd-wrist-strap': {
        'name': 'Антистатический браслет',
        'package_type': 'ESD',
    },
}

GENERIC_PACKAGE_TYPE_FIXUPS = {
    'Consumable': 'Расходник',
    'Tool': 'Инструмент',
    'Module': 'Модуль',
}

REPLACEABLE_SEED_VALUES = {
    'type': {
        'breadboard',
        'consumable',
        'dev board',
        'module',
        'sensor',
        'tool',
    },
}

TEXT_FIXUPS.update(
    {
        # Инструменты: бейдж показывает не сырой Tool, а роль в лаборатории.
        'cutter-flush': {'name': 'Бокорезы заподлицо', 'package_type': 'Ручной инструмент'},
        'stripper-wire': {'name': 'Стриппер для проводов', 'package_type': 'Ручной инструмент'},
        'tweezers-esd': {'name': 'ESD-пинцет прямой', 'package_type': 'Ручной инструмент'},
        'tweezers-esd-curved': {'name': 'ESD-пинцет изогнутый', 'package_type': 'Ручной инструмент'},
        'helping-hands': {'name': 'Держатель "третья рука"', 'package_type': 'Оснастка'},
        'pcb-vice': {'name': 'Тиски для печатных плат', 'package_type': 'Оснастка'},
        'loupe-30x': {'name': 'Инспекционная лупа 30×', 'package_type': 'Оснастка'},
        'microscope-usb': {'name': 'USB-микроскоп', 'package_type': 'Оснастка'},
        'iron-60w-t12': {'name': 'Паяльник T12, 60 Вт', 'package_type': 'Пайка'},
        'iron-908s': {'name': 'Паяльник 908S', 'package_type': 'Пайка'},
        'station-936': {'name': 'Паяльная станция 936', 'package_type': 'Пайка'},
        'station-t12-oled': {'name': 'Паяльная станция T12 OLED', 'package_type': 'Пайка'},
        'hotair-858d': {'name': 'Термофен 858D', 'package_type': 'Пайка'},
        'rework-2in1': {'name': 'Ремонтная станция 2-в-1', 'package_type': 'Пайка'},
        'lab-psu-30v-5a': {'name': 'Лабораторный БП 30 В 5 А', 'package_type': 'Питание'},
        'lab-psu-60v-3a': {'name': 'Лабораторный БП 60 В 3 А', 'package_type': 'Питание'},
        'generator-fy6800': {'name': 'Генератор сигналов FY6800', 'package_type': 'Измерение'},
        'logic-analyzer-8ch': {'name': 'Логический анализатор 8 каналов', 'package_type': 'Измерение'},
        'multimeter-dt830b': {'name': 'Мультиметр DT830B', 'package_type': 'Измерение'},
        'multimeter-fluke-87v': {'name': 'Мультиметр Fluke 87V', 'package_type': 'Измерение'},
        'multimeter-ut61e': {'name': 'Мультиметр UNI-T UT61E', 'package_type': 'Измерение'},
        'osc-rigol-ds1054z': {'name': 'Осциллограф Rigol DS1054Z', 'package_type': 'Измерение'},
        'osc-usb-ds213': {'name': 'Портативный осциллограф DS213', 'package_type': 'Измерение'},
        'st-link-v2': {'name': 'Отладчик ST-Link V2', 'package_type': 'Отладка'},
        'usbasp': {'name': 'AVR-программатор USBasp', 'package_type': 'Отладка'},
        # Модули: название сразу объясняет назначение, а не только part number.
        'arduino-uno-r3': {'name': 'Отладочная плата Arduino Uno R3', 'package_type': 'Отладочная плата'},
        'arduino-nano': {'name': 'Отладочная плата Arduino Nano', 'package_type': 'Отладочная плата'},
        'arduino-mega-2560': {
            'name': 'Отладочная плата Arduino Mega 2560',
            'package_type': 'Отладочная плата',
        },
        'arduino-leonardo': {'name': 'Отладочная плата Arduino Leonardo', 'package_type': 'Отладочная плата'},
        'arduino-micro': {'name': 'Отладочная плата Arduino Micro', 'package_type': 'Отладочная плата'},
        'esp32-devkit': {'name': 'Отладочная плата ESP32 DevKit', 'package_type': 'Отладочная плата'},
        'esp32-s3': {'name': 'Отладочная плата ESP32-S3', 'package_type': 'Отладочная плата'},
        'esp32-cam': {'name': 'Камера-модуль ESP32-CAM', 'package_type': 'Отладочная плата'},
        'esp8266-nodemcu': {'name': 'Wi-Fi плата NodeMCU ESP8266', 'package_type': 'Отладочная плата'},
        'esp8266-d1-mini': {'name': 'Wi-Fi плата ESP8266 D1 Mini', 'package_type': 'Отладочная плата'},
        'stm32-bluepill': {'name': 'Отладочная плата STM32 Blue Pill', 'package_type': 'Отладочная плата'},
        'rpi-pico': {
            'name': 'Микроконтроллерная плата Raspberry Pi Pico',
            'package_type': 'Отладочная плата',
        },
        'rpi-pico-w': {
            'name': 'Микроконтроллерная плата Raspberry Pi Pico W',
            'package_type': 'Отладочная плата',
        },
        'rpi-4b-4gb': {'name': 'Одноплатный компьютер Raspberry Pi 4B 4GB', 'package_type': 'SBC'},
        'rpi-4b-8gb': {'name': 'Одноплатный компьютер Raspberry Pi 4B 8GB', 'package_type': 'SBC'},
        'rpi-zero-2w': {'name': 'Одноплатный компьютер Raspberry Pi Zero 2 W', 'package_type': 'SBC'},
        'bme280': {'name': 'Датчик BME280: температура, влажность, давление', 'package_type': 'Датчик'},
        'bmp280': {'name': 'Датчик BMP280: температура и давление', 'package_type': 'Датчик'},
        'dht11': {'name': 'Датчик температуры и влажности DHT11', 'package_type': 'Датчик'},
        'dht22': {'name': 'Датчик температуры и влажности DHT22', 'package_type': 'Датчик'},
        'hc-sr04': {'name': 'Ультразвуковой дальномер HC-SR04', 'package_type': 'Датчик'},
        'hc-sr501': {'name': 'PIR-датчик движения HC-SR501', 'package_type': 'Датчик'},
        'ldr-photores': {'name': 'Модуль фоторезистора LDR', 'package_type': 'Датчик'},
        'max30102': {'name': 'Датчик пульса MAX30102', 'package_type': 'Датчик'},
        'mpu6050': {'name': 'IMU MPU6050, 6 осей', 'package_type': 'Датчик'},
        'mpu9250': {'name': 'IMU MPU9250, 9 осей', 'package_type': 'Датчик'},
        'mq-2': {'name': 'Газовый датчик MQ-2', 'package_type': 'Датчик'},
        'mq-135': {'name': 'Датчик качества воздуха MQ-135', 'package_type': 'Датчик'},
        'tcs3200': {'name': 'Датчик цвета TCS3200', 'package_type': 'Датчик'},
        'lcd1602-i2c': {'name': 'LCD-дисплей 1602 I2C', 'package_type': 'Дисплей'},
        'lcd2004-i2c': {'name': 'LCD-дисплей 2004 I2C', 'package_type': 'Дисплей'},
        'oled-096-i2c': {'name': 'OLED-дисплей 0.96" I2C', 'package_type': 'Дисплей'},
        'oled-13-i2c': {'name': 'OLED-дисплей 1.3" I2C', 'package_type': 'Дисплей'},
        'tft-144-spi': {'name': 'TFT-дисплей 1.44" SPI', 'package_type': 'Дисплей'},
        'tft-24-touch': {'name': 'Сенсорный TFT-дисплей 2.4"', 'package_type': 'Дисплей'},
    }
)


# Exact-value локализация для уже известных инженерных параметров. Команда
# применяет ее и к новым спекам, и к старым значениям в базе без --force.
VALUE_TRANSLATIONS = {
    # Modules
    'Dev board': 'Отладочная плата',
    'MCU board': 'Плата микроконтроллера',
    'Wi-Fi MCU board': 'Wi-Fi плата микроконтроллера',
    'Camera MCU board': 'Плата ESP32 с камерой',
    'SBC': 'Одноплатный компьютер',
    'module': 'Модуль',
    'sensor': 'Датчик',
    'gas sensor': 'Газовый датчик',
    'ultrasonic sensor': 'Ультразвуковой дальномер',
    'PIR sensor': 'PIR-датчик движения',
    'light sensor': 'Датчик освещенности',
    'color sensor': 'Датчик цвета',
    'temperature / humidity / pressure': 'температура / влажность / давление',
    'temperature / pressure': 'температура / давление',
    'temperature / humidity': 'температура / влажность',
    '6-axis accel/gyro': '6-осевой акселерометр/гироскоп',
    '9-axis accel/gyro/mag': '9-осевой IMU',
    'pulse oximeter / heart rate': 'пульсоксиметр / пульс',
    'LPG / smoke / methane': 'газ / дым / метан',
    'air quality / NH3 / NOx / CO2 proxy': 'качество воздуха / NH3 / NOx / CO2',
    'RGB reflected light': 'отраженный RGB-свет',
    'analog / digital': 'аналоговый / цифровой',
    'trigger/echo digital': 'trigger/echo, цифровой',
    '1-Wire-like digital': 'цифровой 1-Wire-like',
    'frequency output': 'частотный выход',
    'analog divider': 'аналоговый делитель',
    'digital output': 'цифровой выход',
    'SPI / parallel': 'SPI / параллельный',
    'около 150 мА heater': 'около 150 мА нагреватель',
    'LCD module': 'LCD-дисплей',
    'OLED module': 'OLED-дисплей',
    'TFT display': 'TFT-дисплей',
    'TFT touch display': 'TFT-дисплей с сенсором',
    # Tools
    'digital multimeter': 'Цифровой мультиметр',
    'industrial multimeter': 'Промышленный мультиметр',
    'digital oscilloscope': 'Цифровой осциллограф',
    'portable oscilloscope': 'Портативный осциллограф',
    'function generator': 'Генератор сигналов',
    'logic analyzer': 'Логический анализатор',
    'bench power supply': 'Лабораторный блок питания',
    'soldering iron': 'Паяльник',
    'soldering station': 'Паяльная станция',
    'hot air station': 'Термовоздушная станция',
    '2-in-1 rework station': 'Ремонтная станция 2-в-1',
    'programmer/debugger': 'Программатор/отладчик',
    'AVR programmer': 'AVR-программатор',
    'USB microscope': 'USB-микроскоп',
    'inspection loupe': 'Инспекционная лупа',
    'PCB holder': 'Держатель плат',
    'PCB vise': 'Тиски для плат',
    'wire stripper': 'Стриппер для проводов',
    'flush cutter': 'Бокорезы',
    'ESD tweezers': 'ESD-пинцет',
    'button cell': 'таблеточная батарейка',
    'straight': 'прямой',
    'curved': 'изогнутый',
    'flush cut': 'плоский срез',
    # Consumables
    'tip cleaner': 'Очиститель жала',
    'PCB cleaner': 'Очиститель плат',
    'cleaner': 'Очиститель',
    'solderless breadboard set': 'Набор макетных плат',
    'solderless breadboard': 'Макетная плата',
    'jumper wires': 'Перемычки Dupont',
    'prototype PCB': 'Макетная PCB',
    'solder paste': 'Паяльная паста',
    'solder wire': 'Припой в проволоке',
    'flux': 'Флюс',
    'rosin flux': 'Канифольный флюс',
    'heat-shrink tube': 'Термоусадочная трубка',
    'heat-shrink kit': 'Набор термоусадки',
    'hook-up wire': 'Монтажный провод',
    'silicone wire': 'Силиконовый провод',
    'paired wire': 'Двухжильный провод',
    'desoldering braid': 'Оплетка для выпайки',
    'desoldering pump': 'Вакуумный оловоотсос',
    'insulating tape': 'Изолента',
    'insulating tape set': 'Набор изоленты',
    'ESD mat': 'Антистатический коврик',
    'ESD wrist strap': 'Антистатический браслет',
    'aluminum / plastic': 'алюминий / пластик',
    'copper braid + flux': 'медная оплетка + флюс',
    'brass wool': 'латунная стружка',
    'polyolefin': 'полиолефин',
    'red': 'красный',
    'black': 'черный',
    'red/black': 'красный / черный',
    'multi': 'цветной набор',
    'RMA': 'RMA-флюс',
    'no-clean': 'безотмывочный',
    'PTFE nozzle': 'PTFE-носик',
    'T12 / 900M / Hakko-style tips': 'жала T12 / 900M / Hakko-совместимые',
    'жала T12 / 900M / Hakko-style': 'жала T12 / 900M / Hakko-совместимые',
    'banana / crocodile': 'банан / крокодил',
    'banana / крокодил': 'банан / крокодил',
    'dissipative rubber': 'рассеивающая резина',
    'copper PVC': 'медь + PVC',
    'tinned copper + silicone': 'луженая медь + силикон',
    'ABS + phosphor bronze': 'ABS + фосфористая бронза',
    'PCB / flux residues': 'PCB / остатки флюса',
    '1 МОм safety resistor': '1 МОм защитный резистор',
    '700 Вт hot air + 60 Вт iron': '700 Вт фен + 60 Вт паяльник',
    'sine/square/triangle/pulse': 'синус / меандр / треугольник / импульс',
    'basic ±0.05% DCV': 'базовая ±0.05% DCV',
    'basic ±0.1% DCV': 'базовая ±0.1% DCV',
    'basic ±0.5% DCV': 'базовая ±0.5% DCV',
    'DC/AC V, DC A, R, diode': 'DC/AC V, DC A, R, диод',
    'ABS / glass': 'ABS / стекло',
    # REB
    'rectifier diode': 'Выпрямительный диод',
    'small-signal diode': 'Сигнальный диод',
    'Schottky diode': 'Диод Шоттки',
    'Zener diode': 'Стабилитрон',
    'LED': 'Светодиод',
    'op-amp': 'Операционный усилитель',
    'dual op-amp': 'Двойной ОУ',
    'quad op-amp': 'Счетверенный ОУ',
    'dual JFET op-amp': 'Двойной JFET ОУ',
    'audio amplifier': 'Аудиоусилитель',
    'Timer': 'Таймер',
    'linear regulator': 'Линейный стабилизатор',
    'negative linear regulator': 'Отрицательный линейный стабилизатор',
    'adjustable linear regulator': 'Регулируемый линейный стабилизатор',
    'LDO regulator': 'LDO-стабилизатор',
    'buck regulator': 'Понижающий DC-DC',
    'boost regulator': 'Повышающий DC-DC',
    'AVR MCU': 'AVR-микроконтроллер',
    'I2C GPIO expander': 'I2C расширитель GPIO',
    'RTC': 'Часы реального времени',
    'temperature sensor': 'Датчик температуры',
    'I2C EEPROM': 'I2C EEPROM',
    '74HC CMOS logic': 'Логика 74HC CMOS',
    'SMD power inductor': 'SMD силовой дроссель',
    'axial inductor': 'Осевой дроссель',
    'toroidal inductor': 'Тороидальный дроссель',
    'power choke': 'силовой дроссель',
    'USB-C receptacle': 'Разъем USB-C',
    'USB Micro-B receptacle': 'Разъем USB Micro-B',
    'USB-A receptacle': 'Разъем USB-A',
    'JST XH connector': 'Разъем JST XH',
    'pin header': 'Штыревой разъем',
    'screw terminal block': 'Винтовая клемма',
    'D-Sub connector': 'Разъем D-Sub',
    'RJ45 connector': 'Разъем RJ45',
    'DC barrel jack': 'Разъем питания DC',
    'solid state relay': 'Твердотельное реле',
    'power relay': 'Силовое реле',
    'signal relay': 'Сигнальное реле',
    'Logic N-MOSFET': 'Логический N-MOSFET',
    'N-MOSFET': 'N-канальный MOSFET',
    'P-MOSFET': 'P-канальный MOSFET',
    'NPN Darlington': 'NPN Дарлингтон',
    'thick-film resistor': 'Толстопленочный резистор',
    'metal-film resistor': 'Металлопленочный резистор',
    'thick film': 'толстая пленка',
    'metal film': 'металлопленка',
    '30 А surge': '30 А имп.',
    '25 А surge': '25 А имп.',
    '80 А surge': '80 А имп.',
    '450 мА pulse': '450 мА имп.',
    '600 мА pulse': '600 мА имп.',
    '0.45 В typ': '0.45 В тип.',
    '0.5 В typ': '0.5 В тип.',
    '0.55 В typ': '0.55 В тип.',
    '0.6 В typ': '0.6 В тип.',
    '0.8 В max': '0.8 В макс.',
    '44 мОм typ': '44 мОм тип.',
    '117 мОм typ': '117 мОм тип.',
    '22 мОм typ': '22 мОм тип.',
    '52 мОм typ': '52 мОм тип.',
    '85 мОм typ': '85 мОм тип.',
    '3.5 Ом max': '3.5 Ом макс.',
    '1000 typ': '1000 тип.',
    '1.1 В typ': '1.1 В тип.',
    # Seed artifact cleanup
    'portable SSD': 'Внешний SSD',
    'external portable': 'внешний портативный',
}


SLUG_PARAMETER_OVERRIDES = {
    # Development boards
    'arduino-uno-r3': {
        'type': 'Dev board',
        'mcu': 'ATmega328P',
        'supply_voltage': '7...12 В / USB 5 В',
        'logic_level': '5 В',
        'clock': '16 МГц',
        'flash': '32 КБ',
        'gpio': '14 digital / 6 analog',
        'interface': 'USB-B, UART, I2C, SPI, PWM',
        'form_factor': 'Arduino Uno',
    },
    'arduino-nano': {
        'type': 'Dev board',
        'mcu': 'ATmega328P',
        'supply_voltage': '5 В / 7...12 В',
        'logic_level': '5 В',
        'clock': '16 МГц',
        'flash': '32 КБ',
        'gpio': '14 digital / 8 analog',
        'interface': 'Mini-USB, UART, I2C, SPI, PWM',
        'form_factor': 'Nano',
    },
    'arduino-mega-2560': {
        'type': 'Dev board',
        'mcu': 'ATmega2560',
        'supply_voltage': '7...12 В / USB 5 В',
        'logic_level': '5 В',
        'clock': '16 МГц',
        'flash': '256 КБ',
        'gpio': '54 digital / 16 analog',
        'interface': 'USB-B, UART x4, I2C, SPI, PWM',
        'form_factor': 'Arduino Mega',
    },
    'arduino-leonardo': {
        'type': 'Dev board',
        'mcu': 'ATmega32U4',
        'supply_voltage': '7...12 В / USB 5 В',
        'logic_level': '5 В',
        'clock': '16 МГц',
        'flash': '32 КБ',
        'gpio': '20 digital / 12 analog',
        'interface': 'USB HID, UART, I2C, SPI, PWM',
    },
    'arduino-micro': {
        'type': 'Dev board',
        'mcu': 'ATmega32U4',
        'supply_voltage': '5 В',
        'logic_level': '5 В',
        'clock': '16 МГц',
        'flash': '32 КБ',
        'gpio': '20 digital / 12 analog',
        'interface': 'Micro-USB, USB HID, UART, I2C, SPI',
    },
    'stm32-bluepill': {
        'type': 'Dev board',
        'mcu': 'STM32F103C8T6',
        'supply_voltage': '3.3 В / USB 5 В',
        'logic_level': '3.3 В',
        'clock': '72 МГц',
        'flash': '64 КБ',
        'ram': '20 КБ',
        'gpio': '37',
        'interface': 'USB, USART, I2C, SPI, SWD',
    },
    'rpi-pico': {
        'type': 'MCU board',
        'mcu': 'RP2040',
        'supply_voltage': '1.8...5.5 В',
        'logic_level': '3.3 В',
        'clock': '133 МГц',
        'flash': '2 МБ',
        'ram': '264 КБ',
        'gpio': '26',
        'interface': 'Micro-USB, UART, I2C, SPI, ADC',
    },
    'rpi-pico-w': {
        'type': 'MCU board',
        'mcu': 'RP2040',
        'supply_voltage': '1.8...5.5 В',
        'logic_level': '3.3 В',
        'clock': '133 МГц',
        'flash': '2 МБ',
        'ram': '264 КБ',
        'gpio': '26',
        'wireless': 'Wi-Fi 4 / Bluetooth',
        'interface': 'Micro-USB, UART, I2C, SPI, ADC',
    },
    'rpi-zero-2w': {
        'type': 'SBC',
        'mcu': 'Broadcom BCM2710A1',
        'supply_voltage': '5 В USB',
        'ram': '512 МБ',
        'gpio': '40-pin',
        'wireless': 'Wi-Fi 4 / Bluetooth 4.2',
        'interface': 'microSD, mini HDMI, CSI-2, USB OTG',
    },
    'rpi-4b-4gb': {
        'type': 'SBC',
        'mcu': 'Broadcom BCM2711',
        'supply_voltage': '5 В USB-C',
        'ram': '4 ГБ LPDDR4',
        'gpio': '40-pin',
        'wireless': 'Wi-Fi 5 / Bluetooth 5.0',
        'interface': '2x micro HDMI, CSI/DSI, Ethernet, USB 3.0',
    },
    'rpi-4b-8gb': {
        'type': 'SBC',
        'mcu': 'Broadcom BCM2711',
        'supply_voltage': '5 В USB-C',
        'ram': '8 ГБ LPDDR4',
        'gpio': '40-pin',
        'wireless': 'Wi-Fi 5 / Bluetooth 5.0',
        'interface': '2x micro HDMI, CSI/DSI, Ethernet, USB 3.0',
    },
    'esp32-devkit': {
        'type': 'Wi-Fi MCU board',
        'mcu': 'ESP32-WROOM',
        'supply_voltage': '5 В USB / 3.3 В',
        'logic_level': '3.3 В',
        'clock': '240 МГц',
        'flash': '4 МБ',
        'gpio': '30',
        'wireless': 'Wi-Fi 4 / Bluetooth',
        'interface': 'USB-UART, ADC, DAC, I2C, SPI, UART',
    },
    'esp32-s3': {
        'type': 'Wi-Fi MCU board',
        'mcu': 'ESP32-S3',
        'supply_voltage': '5 В USB / 3.3 В',
        'logic_level': '3.3 В',
        'clock': '240 МГц',
        'flash': '8 МБ',
        'gpio': '30+',
        'wireless': 'Wi-Fi 4 / Bluetooth LE',
        'interface': 'USB, ADC, I2C, SPI, UART',
    },
    'esp32-cam': {
        'type': 'Camera MCU board',
        'mcu': 'ESP32',
        'supply_voltage': '5 В',
        'logic_level': '3.3 В',
        'wireless': 'Wi-Fi 4 / Bluetooth',
        'camera': 'OV2640',
        'interface': 'microSD, UART, GPIO',
    },
    'esp8266-nodemcu': {
        'type': 'Wi-Fi MCU board',
        'mcu': 'ESP8266',
        'supply_voltage': '5 В USB / 3.3 В',
        'logic_level': '3.3 В',
        'clock': '80/160 МГц',
        'flash': '4 МБ',
        'gpio': '11',
        'wireless': 'Wi-Fi 4',
        'interface': 'USB-UART, ADC, I2C, SPI',
    },
    'esp8266-d1-mini': {
        'type': 'Wi-Fi MCU board',
        'mcu': 'ESP8266',
        'supply_voltage': '5 В USB / 3.3 В',
        'logic_level': '3.3 В',
        'clock': '80/160 МГц',
        'flash': '4 МБ',
        'gpio': '11',
        'wireless': 'Wi-Fi 4',
        'interface': 'Micro-USB, GPIO, ADC, I2C',
    },
    # Sensors and displays
    'bme280': {
        'type': 'sensor',
        'sensor_type': 'temperature / humidity / pressure',
        'supply_voltage': '1.8...3.6 В',
        'interface': 'I2C / SPI',
        'measurement_range': '-40...85 °C, 0...100% RH, 300...1100 hPa',
        'accuracy': '±1 °C / ±3% RH / ±1 hPa',
    },
    'bmp280': {
        'type': 'sensor',
        'sensor_type': 'temperature / pressure',
        'supply_voltage': '1.8...3.6 В',
        'interface': 'I2C / SPI',
        'measurement_range': '-40...85 °C, 300...1100 hPa',
        'accuracy': '±1 °C / ±1 hPa',
    },
    'dht11': {
        'type': 'sensor',
        'sensor_type': 'temperature / humidity',
        'supply_voltage': '3...5.5 В',
        'interface': '1-Wire-like digital',
        'measurement_range': '0...50 °C, 20...80% RH',
        'accuracy': '±2 °C / ±5% RH',
    },
    'dht22': {
        'type': 'sensor',
        'sensor_type': 'temperature / humidity',
        'supply_voltage': '3...5.5 В',
        'interface': '1-Wire-like digital',
        'measurement_range': '-40...80 °C, 0...100% RH',
        'accuracy': '±0.5 °C / ±2% RH',
    },
    'mpu6050': {
        'type': 'IMU',
        'sensor_type': '6-axis accel/gyro',
        'supply_voltage': '3.3...5 В',
        'interface': 'I2C',
        'measurement_range': '±2/4/8/16 g, ±250...2000 °/s',
    },
    'mpu9250': {
        'type': 'IMU',
        'sensor_type': '9-axis accel/gyro/mag',
        'supply_voltage': '3.3 В',
        'interface': 'I2C / SPI',
        'measurement_range': '±2...16 g, ±250...2000 °/s',
    },
    'max30102': {
        'type': 'sensor',
        'sensor_type': 'pulse oximeter / heart rate',
        'supply_voltage': '1.8/3.3 В',
        'interface': 'I2C',
        'current': 'до 20 мА LED',
    },
    'mq-2': {
        'type': 'gas sensor',
        'sensor_type': 'LPG / smoke / methane',
        'supply_voltage': '5 В',
        'interface': 'analog / digital',
        'current': 'около 150 мА heater',
    },
    'mq-135': {
        'type': 'gas sensor',
        'sensor_type': 'air quality / NH3 / NOx / CO2 proxy',
        'supply_voltage': '5 В',
        'interface': 'analog / digital',
        'current': 'около 150 мА heater',
    },
    'hc-sr04': {
        'type': 'ultrasonic sensor',
        'supply_voltage': '5 В',
        'interface': 'trigger/echo digital',
        'measurement_range': '2...400 см',
        'accuracy': 'около 3 мм',
    },
    'hc-sr501': {
        'type': 'PIR sensor',
        'supply_voltage': '5...20 В',
        'interface': 'digital output',
        'measurement_range': 'до 7 м',
        'delay': '0.3...300 с',
    },
    'ldr-photores': {
        'type': 'light sensor',
        'sensor_type': 'photoresistor',
        'resistance': '1...100 кОм',
        'interface': 'analog divider',
    },
    'tcs3200': {
        'type': 'color sensor',
        'sensor_type': 'RGB photodiode array',
        'supply_voltage': '2.7...5.5 В',
        'interface': 'frequency output',
        'measurement_range': 'RGB reflected light',
    },
    'lcd1602-i2c': {
        'type': 'LCD module',
        'display': '16×2 characters',
        'supply_voltage': '5 В',
        'interface': 'I2C',
        'controller': 'HD44780 + PCF8574',
    },
    'lcd2004-i2c': {
        'type': 'LCD module',
        'display': '20×4 characters',
        'supply_voltage': '5 В',
        'interface': 'I2C',
        'controller': 'HD44780 + PCF8574',
    },
    'oled-096-i2c': {
        'type': 'OLED module',
        'display': '0.96"',
        'resolution': '128×64',
        'supply_voltage': '3.3/5 В',
        'interface': 'I2C',
        'controller': 'SSD1306',
    },
    'oled-13-i2c': {
        'type': 'OLED module',
        'display': '1.3"',
        'resolution': '128×64',
        'supply_voltage': '3.3/5 В',
        'interface': 'I2C',
        'controller': 'SH1106 / SSD1306',
    },
    'tft-144-spi': {
        'type': 'TFT display',
        'display': '1.44"',
        'resolution': '128×128',
        'supply_voltage': '3.3 В',
        'interface': 'SPI',
    },
    'tft-24-touch': {
        'type': 'TFT touch display',
        'display': '2.4"',
        'resolution': '320×240',
        'supply_voltage': '3.3/5 В',
        'interface': 'SPI / parallel',
        'touch': 'resistive',
    },
    # Tools
    'multimeter-dt830b': {
        'type': 'digital multimeter',
        'measurement_range': 'DC/AC V, DC A, R, diode',
        'counts': '2000',
        'accuracy': 'basic ±0.5% DCV',
        'safety': 'CAT I / учебный',
    },
    'multimeter-ut61e': {
        'type': 'digital multimeter',
        'measurement_range': 'DC/AC V, A, R, C, Hz',
        'counts': '22000',
        'accuracy': 'basic ±0.1% DCV',
        'true_rms': 'AC True RMS',
    },
    'multimeter-fluke-87v': {
        'type': 'industrial multimeter',
        'measurement_range': 'DC/AC V, A, R, C, Hz, °C',
        'counts': '20000',
        'accuracy': 'basic ±0.05% DCV',
        'true_rms': 'AC True RMS',
        'safety': 'CAT III 1000 В / CAT IV 600 В',
    },
    'osc-rigol-ds1054z': {
        'type': 'digital oscilloscope',
        'channels': '4',
        'bandwidth': '50 МГц',
        'sample_rate': '1 Гвыб/с',
        'memory': '12 Mpts',
        'interface': 'USB/LAN',
    },
    'osc-usb-ds213': {
        'type': 'portable oscilloscope',
        'channels': '4',
        'bandwidth': '15 МГц',
        'sample_rate': '100 Мвыб/с',
        'memory': '8 МБ',
    },
    'generator-fy6800': {
        'type': 'function generator',
        'channels': '2',
        'bandwidth': '60 МГц',
        'sample_rate': '250 Мвыб/с',
        'signal': 'sine/square/triangle/pulse',
    },
    'logic-analyzer-8ch': {
        'type': 'logic analyzer',
        'channels': '8',
        'sample_rate': '24 Мвыб/с',
        'logic_level': '3.3/5 В',
        'interface': 'USB',
    },
    'lab-psu-30v-5a': {
        'type': 'bench power supply',
        'voltage': '0...30 В',
        'current': '0...5 А',
        'power': '150 Вт',
        'channels': '1',
        'mode': 'CV/CC',
    },
    'lab-psu-60v-3a': {
        'type': 'bench power supply',
        'voltage': '0...60 В',
        'current': '0...3 А',
        'power': '180 Вт',
        'channels': '1',
        'mode': 'CV/CC',
    },
    'iron-60w-t12': {
        'type': 'soldering iron',
        'power': '60 Вт',
        'temperature_range': '200...480 °C',
        'tip_type': 'T12',
        'supply_voltage': '24 В',
    },
    'iron-908s': {
        'type': 'soldering iron',
        'power': '60 Вт',
        'temperature_range': '200...450 °C',
        'tip_type': '900M',
        'supply_voltage': '220 В',
    },
    'station-936': {
        'type': 'soldering station',
        'power': '60 Вт',
        'temperature_range': '200...480 °C',
        'tip_type': '900M',
        'supply_voltage': '220 В',
    },
    'station-t12-oled': {
        'type': 'soldering station',
        'power': '72 Вт',
        'temperature_range': '180...480 °C',
        'tip_type': 'T12',
        'display': 'OLED',
    },
    'hotair-858d': {
        'type': 'hot air station',
        'power': '700 Вт',
        'temperature_range': '100...500 °C',
        'airflow': 'до 120 л/мин',
        'supply_voltage': '220 В',
    },
    'rework-2in1': {
        'type': '2-in-1 rework station',
        'power': '700 Вт hot air + 60 Вт iron',
        'temperature_range': '100...500 °C / 200...480 °C',
        'airflow': 'регулируемый',
        'tip_type': 'фен + паяльник',
    },
    'st-link-v2': {
        'type': 'programmer/debugger',
        'interface': 'SWD / SWIM / USB',
        'logic_level': '3.3 В',
        'compatibility': 'STM8 / STM32',
        'mode': 'отладка / прошивка',
    },
    'usbasp': {
        'type': 'AVR programmer',
        'interface': 'USB / ISP',
        'logic_level': '5 В / 3.3 В',
        'compatibility': 'AVR ATmega / ATtiny',
        'mode': 'прошивка ISP',
    },
    'microscope-usb': {
        'type': 'USB microscope',
        'magnification': '50...1000×',
        'resolution': 'до 1080p',
        'interface': 'USB',
        'light': 'LED-подсветка',
    },
    'loupe-30x': {
        'type': 'inspection loupe',
        'magnification': '30×',
        'light': 'LED',
        'material': 'ABS / glass',
        'battery': 'button cell',
    },
    'helping-hands': {
        'type': 'PCB holder',
        'material': 'металл',
        'configuration': 'крокодилы + лупа',
        'magnification': '2×',
        'board_size': 'малые платы',
    },
    'pcb-vice': {
        'type': 'PCB vise',
        'material': 'алюминий / пластик',
        'board_size': 'до 200 мм',
        'configuration': 'регулируемый зажим',
        'rotation': '360°',
    },
    'stripper-wire': {
        'type': 'wire stripper',
        'gauge': '0.2...6 мм²',
        'material': 'сталь',
        'length': '170 мм',
        'application': 'зачистка проводов',
    },
    'cutter-flush': {
        'type': 'flush cutter',
        'material': 'сталь',
        'length': '125 мм',
        'tip_type': 'flush cut',
        'application': 'выводы компонентов / провод',
    },
    'tweezers-esd': {
        'type': 'ESD tweezers',
        'material': 'нержавеющая сталь',
        'tip_type': 'straight',
        'length': '120 мм',
        'application': 'SMD монтаж',
    },
    'tweezers-esd-curved': {
        'type': 'ESD tweezers',
        'material': 'нержавеющая сталь',
        'tip_type': 'curved',
        'length': '120 мм',
        'application': 'SMD монтаж',
    },
    # Consumables
    'breadboard-400': {
        'type': 'solderless breadboard',
        'points': '400',
        'pitch': '2.54 мм',
        'power_rails': '2',
        'material': 'ABS + phosphor bronze',
    },
    'breadboard-830': {
        'type': 'solderless breadboard',
        'points': '830',
        'pitch': '2.54 мм',
        'power_rails': '4',
        'material': 'ABS + phosphor bronze',
    },
    'breadboard-2x830': {
        'type': 'solderless breadboard set',
        'points': '1660',
        'pitch': '2.54 мм',
        'power_rails': '8',
        'material': 'ABS + phosphor bronze',
    },
    'jumper-mm-65pcs': {
        'type': 'jumper wires',
        'configuration': 'M-M',
        'contact_count': '65 шт.',
        'length': '10...20 см',
        'pitch': '2.54 мм',
    },
    'jumper-mf-65pcs': {
        'type': 'jumper wires',
        'configuration': 'M-F',
        'contact_count': '65 шт.',
        'length': '10...20 см',
        'pitch': '2.54 мм',
    },
    'jumper-ff-65pcs': {
        'type': 'jumper wires',
        'configuration': 'F-F',
        'contact_count': '65 шт.',
        'length': '10...20 см',
        'pitch': '2.54 мм',
    },
    'pcb-protoboard-7x9': {
        'type': 'prototype PCB',
        'material': 'FR-4',
        'size': '7×9 см',
        'pitch': '2.54 мм',
        'hole_count': 'примерно 432',
    },
    'pcb-protoboard-9x15': {
        'type': 'prototype PCB',
        'material': 'FR-4',
        'size': '9×15 см',
        'pitch': '2.54 мм',
        'hole_count': 'примерно 780',
    },
    'solder-paste-138': {
        'type': 'solder paste',
        'material': 'Sn42Bi58',
        'melting_point': '138 °C',
        'weight': '30 г',
        'package': 'шприц',
    },
    'solder-lead-free-100g': {
        'type': 'solder wire',
        'material': 'SnAgCu',
        'diameter': '0.8 мм',
        'weight': '100 г',
        'flux_core': 'есть',
    },
    'solder-60-40-100g': {
        'type': 'solder wire',
        'material': 'Sn60Pb40',
        'diameter': '1.0 мм',
        'weight': '100 г',
        'flux_core': 'есть',
    },
    'flux-no-clean': {
        'type': 'flux',
        'material': 'no-clean',
        'volume': '10 мл',
        'application': 'SMD/THT пайка',
        'compatibility': 'микросхемы / SMD',
    },
    'flux-rma-50ml': {
        'type': 'flux',
        'material': 'RMA',
        'volume': '50 мл',
        'application': 'ремонт / ручная пайка',
        'compatibility': 'PCB / провода',
    },
    'flux-rosin-30g': {
        'type': 'rosin flux',
        'material': 'канифоль',
        'weight': '30 г',
        'application': 'лужение / пайка проводов',
        'compatibility': 'THT / провода',
    },
    'alcohol-ipa-100ml': {
        'type': 'cleaner',
        'material': 'изопропиловый спирт',
        'volume': '100 мл',
        'purity': '99%',
        'application': 'очистка плат',
    },
    'pcb-cleaner-200ml': {
        'type': 'PCB cleaner',
        'volume': '200 мл',
        'material': 'очиститель для электроники',
        'compatibility': 'PCB / flux residues',
        'application': 'удаление флюса / очистка плат',
    },
    'heat-shrink-2mm-1m': {
        'type': 'heat-shrink tube',
        'material': 'polyolefin',
        'diameter': '2 мм',
        'length': '1 м',
        'shrink_ratio': '2:1',
    },
    'heat-shrink-kit': {
        'type': 'heat-shrink kit',
        'material': 'polyolefin',
        'diameter': '1...10 мм',
        'shrink_ratio': '2:1',
        'color': 'multi',
    },
    'wire-cu-22awg-red-5m': {
        'type': 'hook-up wire',
        'material': 'copper PVC',
        'gauge': '22 AWG',
        'length': '5 м',
        'color': 'red',
    },
    'wire-cu-22awg-black-5m': {
        'type': 'hook-up wire',
        'material': 'copper PVC',
        'gauge': '22 AWG',
        'length': '5 м',
        'color': 'black',
    },
    'wire-silicon-18awg-1m': {
        'type': 'silicone wire',
        'material': 'tinned copper + silicone',
        'gauge': '18 AWG',
        'length': '1 м',
        'temperature_range': '-60...+200 °C',
    },
    'wire-pair-2x05mm': {
        'type': 'paired wire',
        'material': 'copper PVC',
        'section': '2×0.5 мм²',
        'length': '1 м',
        'color': 'red/black',
    },
    'solder-wick-2mm': {
        'type': 'desoldering braid',
        'material': 'copper braid + flux',
        'width': '2 мм',
        'length': '1.5 м',
        'flux_core': 'есть',
    },
    'solder-wick-3mm': {
        'type': 'desoldering braid',
        'material': 'copper braid + flux',
        'width': '3 мм',
        'length': '1.5 м',
        'flux_core': 'есть',
    },
    'desolder-pump': {
        'type': 'desoldering pump',
        'material': 'aluminum / plastic',
        'length': '190 мм',
        'tip_type': 'PTFE nozzle',
        'application': 'удаление припоя',
    },
    'solder-tip-cleaner': {
        'type': 'tip cleaner',
        'material': 'brass wool',
        'size': '65 мм',
        'compatibility': 'T12 / 900M / Hakko-style tips',
        'application': 'очистка жала',
    },
    'electrical-tape-blk': {
        'type': 'insulating tape',
        'material': 'PVC',
        'width': '19 мм',
        'length': '10 м',
        'color': 'black',
    },
    'electrical-tape-color': {
        'type': 'insulating tape set',
        'material': 'PVC',
        'width': '19 мм',
        'length': '5×10 м',
        'color': 'multi',
    },
    'esd-mat-30x60': {
        'type': 'ESD mat',
        'material': 'dissipative rubber',
        'size': '30×60 см',
        'resistance': '10^6...10^9 Ом',
        'safety': 'ESD',
    },
    'esd-wrist-strap': {
        'type': 'ESD wrist strap',
        'resistance': '1 МОм safety resistor',
        'length': '1.8 м',
        'connector': 'banana / crocodile',
        'safety': 'ESD / 1 МОм',
    },
    't1-ok': {
        'type': 'portable SSD',
        'capacity': '1 ТБ',
        'interface': 'USB 3.2 Gen 2 (USB-C)',
        'form_factor': 'external portable',
        'read_speed': 'до 1050 МБ/с',
        'write_speed': 'до 1000 МБ/с',
        'tbw': 'не заявлен',
        'dram_cache': 'не требуется',
        'weight': '58 г',
    },
}


def localize_parameter_value(value):
    if isinstance(value, str):
        return VALUE_TRANSLATIONS.get(value, value)
    return value


def localize_specs(specs: dict) -> dict:
    return {key: localize_parameter_value(value) for key, value in specs.items()}


def build_product_specs(product) -> dict:
    slug = getattr(product.category, 'slug', '')
    specs = dict(CATEGORY_DEFAULTS.get(slug, {}))
    cat_app = CATEGORY_APPLICATIONS.get(slug)
    if cat_app:
        specs['applications'] = cat_app

    name_lower = str(product.name or '').lower()
    for needle, override in NAME_OVERRIDES:
        if needle in name_lower:
            specs.update(override)
            break

    specs.update(SLUG_PARAMETER_OVERRIDES.get(product.slug, {}))
    return localize_specs(specs)


def should_replace_seed_value(key: str, current, new_value) -> bool:
    """Allow slug-specific specs to replace old generic seed placeholders."""
    if new_value in (None, ''):
        return False
    seed_values = REPLACEABLE_SEED_VALUES.get(key, set())
    return str(current or '').strip().lower() in seed_values


def apply_text_fixups(product) -> list[str]:
    fix = TEXT_FIXUPS.get(product.slug)
    changed_fields = []
    fix_items = dict(fix or {})
    package_fix = GENERIC_PACKAGE_TYPE_FIXUPS.get(product.package_type)
    if package_fix and 'package_type' not in fix_items:
        fix_items['package_type'] = package_fix
    if not fix_items:
        return changed_fields
    for field, value in fix_items.items():
        if getattr(product, field) != value:
            setattr(product, field, value)
            changed_fields.append(field)
    return changed_fields


class Command(BaseCommand):
    help = 'Мягко наполнить Product.parameters инженерными параметрами и сохранить media metadata.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Обновить известные поля specs даже если они уже заполнены; неизвестные/служебные поля сохранить',
        )

    def _write(self, message: str) -> None:
        # На Windows stdout часто cp1251: бренды вроде Würth не должны ронять
        # всю нормализацию каталога.
        safe = str(message).encode('cp1251', errors='replace').decode('cp1251')
        self.stdout.write(safe)

    def handle(self, *args, **options):
        force = options['force']
        updated = 0
        skipped = 0
        applications_added = 0

        for p in Product.objects.select_related('category').all():
            text_fields = apply_text_fixups(p)
            original = dict(p.parameters or {})
            current = localize_specs(original)
            had_app = bool(current.get('applications'))
            specs = build_product_specs(p)
            if not specs:
                update_fields = list(text_fields)
                if current != original:
                    p.parameters = current
                    update_fields.append('parameters')
                if update_fields:
                    p.save(update_fields=update_fields)
                    updated += 1
                    self._write(f'  {p.name[:50]:<50} -> fixed: {", ".join(update_fields)}')
                else:
                    skipped += 1
                continue

            merged = dict(current)
            for key, value in specs.items():
                if value in (None, ''):
                    continue
                if (
                    force
                    or merged.get(key) in (None, '')
                    or should_replace_seed_value(key, merged.get(key), value)
                ):
                    merged[key] = value

            update_fields = list(text_fields)
            if merged != original:
                p.parameters = merged
                update_fields.append('parameters')

            if update_fields:
                p.save(update_fields=update_fields)
                updated += 1
                if not had_app and merged.get('applications'):
                    applications_added += 1
                added_keys = [key for key in merged if key not in current]
                self._write(
                    f'  {p.name[:50]:<50} -> +{len(added_keys)} полей'
                    + (f', fixed: {", ".join(text_fields)}' if text_fields else '')
                )
            else:
                skipped += 1

        if applications_added:
            self._write(f'  + applications дописано к {applications_added} товарам без --force')

        self._write(self.style.SUCCESS(f'\nГотово. Обновлено: {updated}, пропущено: {skipped}'))
