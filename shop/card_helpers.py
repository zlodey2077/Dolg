"""Чистая логика для shop-карточек: helpers, константы, форматирование.

Раньше всё это жило в `shop/templatetags/shop_extras.py` (38 KB). После
разделения 2026-05-19:
- ЛОГИКА (helpers + constants) переехала сюда.
- РЕГИСТРАЦИЯ template-фильтров/тегов осталась в `shop/templatetags/shop_extras.py`
  как тонкий слой (~60 строк), импортирует функции отсюда.

Все 8 шаблонов с `{% load shop_extras %}` продолжают работать без изменений.

Структура разделов:
  1. CATEGORY_ICONS + базовые helpers (get_item, category_icon, manufacturer_label)
  2. PARAM_LABELS / PARAM_GROUPS + group_parameters
  3. CARD_PARAM_ORDER / CARD_PARAM_LABELS / CARD_PARAM_EXCLUDE / CARD_PARAM_FILTER_MAP
     + chip_filter_name, chip_group, _COLOR_GROUPS
  4. STOCK_IMAGE_PATHS + is_stock_image, parameter_preview
  5. MANUFACTURER_BRANDS / NAME_TO_BRAND + brand_badge, delivery_hint
  6. _REVIEW_* + product_rating, product_reviews (seeded, без БД)
"""
import hashlib
import random

# ════════════════════════════════════════════════════════════════════
# 1. Базовые helpers + категория-иконки
# ════════════════════════════════════════════════════════════════════

def _seeded(product_id, salt=''):
    """Детерминированный RNG по product_id — между визитами рейтинг/отзывы
    одного и того же товара не меняются. Без БД-таблицы для отзывов
    (диплом-демо, не production)."""
    h = hashlib.md5(f'dolg-{product_id}-{salt}'.encode()).hexdigest()
    rng = random.Random(int(h[:8], 16))
    return rng


# slug категории → эмодзи-иконка. Единый источник истины для всех шаблонов.
CATEGORY_ICONS = {
    # РЭБ
    'resistors':    '⚡',
    'capacitors':   '🔋',
    'transistors':  '🔀',
    'ics':          '🔲',
    'diodes':       '➡️',
    'inductors':    '〰️',
    'connectors':   '🔗',
    'relays':       '🔄',
    # Потребительская
    'smartphones':  '📱',
    'laptops':      '💻',
    'tablets':      '🖥️',
    'accessories':  '🎧',
    'cpu':          '⚙️',
    'gpu':          '🎮',
    'ram':          '💾',
    'ssd':          '💿',
    'psu':          '🔌',
    'cooling':      '🌀',
    'monitors':     '🖥️',
    'motherboards': '🔧',
}


def get_item(mapping, key):
    """Возвращает mapping[key] или пустую строку. Для dict-lookup по переменной ключа."""
    if mapping is None:
        return ''
    try:
        return mapping.get(key, '')
    except AttributeError:
        return ''


def category_icon(slug, fallback='📦'):
    """Иконка по slug категории."""
    return CATEGORY_ICONS.get(slug, fallback)


def manufacturer_label(key, choices):
    """Display-имя производителя по slug-key из Product.MANUFACTURER_CHOICES."""
    if not choices:
        return key
    try:
        return choices.get(key, key)
    except AttributeError:
        return key


# ════════════════════════════════════════════════════════════════════
# 2. Человекочитаемые имена параметров + группы для product_detail.html
# ════════════════════════════════════════════════════════════════════

PARAM_LABELS = {
    # --- РЭБ ---
    'resistance':     'Сопротивление',
    'capacitance':    'Ёмкость',
    'inductance':     'Индуктивность',
    'dcr':            'Сопротивление обмотки',
    'srf':            'Собственная резонансная частота',
    'tolerance':      'Точность',
    'voltage':        'Напряжение',
    'max_voltage':    'Максимальное напряжение',
    'current':        'Ток',
    'max_current':    'Максимальный ток',
    'output_current': 'Выходной ток',
    'power':          'Мощность',
    'dielectric':     'Диэлектрик',
    'type':           'Тип',
    'package':        'Упаковка',
    'material':       'Материал',
    'temp_coef':      'Температурный коэф.',
    'max_temp':       'Макс. температура',
    'temp_max':       'Макс. температура',
    'min_temp':       'Мин. температура',
    'operating_temp': 'Рабочая температура',
    'mounting':       'Монтаж',
    'turns':          'Количество оборотов',
    'vceo':           'U-кэ (Vceo)',
    'ic':             'Ток коллектора (Ic)',
    'hfe':            'Коэфф. β (hFE)',
    'ft':             'Частота среза',
    'dropout':        'Падение стабилизатора',
    'vf':             'Падение напряжения (Vf)',
    'if':             'Прямой ток (If)',
    'vr':             'Обратное напряжение (Vr)',
    'trr':            'Время восстановления',
    'wavelength':     'Длина волны',
    'vz':             'Напряжение стабилизации',
    'saturation_voltage': 'Напряжение насыщения',
    'rds_on':         'Сопротивление открытого канала (RDS(on))',
    'coil_voltage':   'Напряжение катушки',
    'contact_current':'Ток контактов',
    'configuration':  'Конфигурация',
    'pin_count':      'Количество контактов',
    'pitch':          'Шаг',
    'frequency':      'Частота',
    'gain':           'Усиление',
    'supply_voltage': 'Напряжение питания',
    'family':         'Семейство',
    'channels':       'Каналы',
    'flash':          'Flash-память',
    'gbw':            'Полоса усиления',
    'slew_rate':      'Скорость нарастания',
    'contact_rating': 'Нагрузка контактов',
    'mcu':            'Микроконтроллер / SoC',
    'logic_level':    'Логический уровень',
    'clock':          'Тактовая частота',
    'gpio':           'GPIO',
    'wireless':       'Беспроводная связь',
    'sensor_type':    'Тип датчика',
    'measurement_range': 'Диапазон измерения',
    'accuracy':       'Точность',
    'controller':     'Контроллер',
    'sample_rate':    'Частота дискретизации',
    'memory':         'Память',
    'counts':         'Разрядность / отсчеты',
    'true_rms':       'True RMS',
    'safety':         'Категория безопасности',
    'temperature_range': 'Диапазон температуры',
    'tip_type':       'Тип жала / наконечника',
    'airflow':        'Воздушный поток',
    'compatibility':  'Совместимость',
    'magnification':  'Увеличение',
    'light':          'Подсветка',
    'board_size':     'Размер платы',
    'rotation':       'Поворот',
    'points':         'Контактные точки',
    'power_rails':    'Шины питания',
    'contact_count':  'Количество контактов',
    'orientation':    'Ориентация',
    'gender':         'Тип контакта',
    'contact_material':'Материал контактов',
    'melting_point':  'Температура плавления',
    'diameter':       'Диаметр',
    'volume':         'Объём',
    'purity':         'Чистота',
    'shrink_ratio':   'Коэффициент усадки',
    'gauge':          'Сечение / AWG',
    'color':          'Цвет',
    'section':        'Сечение',
    'width':          'Ширина',
    'hole_count':     'Количество отверстий',
    'flux_core':      'Флюсовая жила',
    'size':           'Размер',
    'connector':      'Разъём',
    'signal':         'Формы сигнала',
    'mode':           'Режим',
    'touch':          'Сенсор',
    'delay':          'Задержка',
    'application':    'Назначение',

    # --- Потребительская электроника ---
    'screen_size':    'Диагональ экрана',
    'display':        'Дисплей',
    'resolution':     'Разрешение',
    'panel':          'Тип матрицы',
    'refresh_rate':   'Частота обновления',
    'response_time':  'Время отклика',
    'hdr':            'HDR',
    'chip':           'Чипсет / SoC',
    'cpu':            'Процессор',
    'gpu':            'Видеокарта',
    'igpu':           'Встроенная графика',
    'gpu_chip':       'GPU-чип',
    'cuda_cores':     'CUDA-ядер',
    'stream_processors': 'Stream-процессоров',
    'ram':            'Оперативная память',
    'storage':        'Накопитель',
    'battery':        'Аккумулятор',
    'battery_case':   'Батарея (с кейсом)',
    'battery_earbuds':'Батарея (наушники)',
    'charging':       'Зарядка',
    'os':             'Операционная система',
    'weight':         'Вес',
    'camera':         'Камера',
    'connectivity':   'Беспроводная связь',
    'stylus':         'Поддержка стилуса',
    'cores':          'Ядер',
    'threads':        'Потоков',
    'base_clock':     'Базовая частота',
    'boost_clock':    'Турбо-частота',
    'cache_l3':       'L3 кэш',
    'socket':         'Сокет',
    'tdp':            'TDP',
    'process':        'Тех. процесс',
    'vram':           'Видеопамять',
    'memory_bus':     'Шина памяти',
    'interface':      'Интерфейс',
    'outputs':        'Видеовыходы',
    'power_conn':     'Разъёмы питания',
    'capacity':       'Объём',
    'form_factor':    'Форм-фактор',
    'read_speed':     'Скорость чтения',
    'write_speed':    'Скорость записи',
    'tbw':            'Ресурс записи (TBW)',
    'dram_cache':     'DRAM-кэш',
    'wattage':        'Мощность',
    'certification':  'Сертификация',
    'modular':        'Модульность',
    'efficiency':     'КПД',
    'fan_count':      'Количество вентиляторов',
    'fan_size':       'Размер вентилятора',
    'rgb':            'RGB-подсветка',
    'chipset':        'Чипсет',
    'chipset_support':'Поддержка чипсетов',
    'ram_slots':      'Слоты DIMM',
    'pcie':           'PCI Express',
    'm2_slots':       'M.2 слоты',
    'network':        'Сеть',
    'latency':        'Латентность',
    'anc':            'Шумоподавление',
    'driver':         'Излучатель',
    'codec':          'Аудиокодек',
    'tdp_rated':      'Расчётный TDP',
    'chassis':        'Корпус',
    'inputs':         'Входы',
}

# Группы параметров: (название группы, список ключей в порядке показа)
PARAM_GROUPS = [
    ('Процессор', [
        'cpu', 'chip', 'cores', 'threads', 'base_clock', 'boost_clock',
        'cache_l3', 'socket', 'tdp', 'process', 'igpu',
    ]),
    ('Графика', [
        'gpu', 'gpu_chip', 'cuda_cores', 'stream_processors',
        'vram', 'memory_bus', 'outputs', 'power_conn',
    ]),
    ('Память и накопитель', [
        'ram', 'storage', 'capacity', 'form_factor', 'interface',
        'read_speed', 'write_speed', 'tbw', 'dram_cache', 'latency',
        'ram_slots', 'pcie', 'm2_slots',
    ]),
    ('Дисплей', [
        'screen_size', 'display', 'resolution', 'panel',
        'refresh_rate', 'response_time', 'hdr',
    ]),
    ('Батарея и питание', [
        'battery', 'battery_earbuds', 'battery_case', 'charging',
        'wattage', 'certification', 'modular', 'efficiency',
    ]),
    ('Камера и аудио', [
        'camera', 'driver', 'codec', 'anc',
    ]),
    ('Электрические', [
        'resistance', 'capacitance', 'inductance',
        'voltage', 'current', 'power', 'frequency', 'gain',
        'supply_voltage', 'saturation_voltage', 'rds_on',
        'vceo', 'ic', 'hfe', 'ft', 'vf', 'if', 'vr',
        'coil_voltage', 'contact_current',
    ]),
    ('Точность и температура', [
        'tolerance', 'temp_coef', 'operating_temp', 'max_temp', 'min_temp',
    ]),
    ('Охлаждение', [
        'fan_count', 'fan_size', 'tdp_rated', 'rgb',
    ]),
    ('Коммуникации', [
        'connectivity', 'network', 'inputs', 'wireless', 'controller',
        'compatibility',
    ]),
    ('Модули и датчики', [
        'mcu', 'clock', 'flash', 'gpio', 'logic_level', 'sensor_type',
        'measurement_range', 'accuracy', 'sample_rate', 'memory', 'counts',
        'true_rms', 'mode', 'signal', 'touch', 'delay',
    ]),
    ('Инструмент и расходники', [
        'temperature_range', 'tip_type', 'airflow', 'magnification', 'light',
        'board_size', 'points', 'power_rails', 'contact_count',
        'melting_point', 'diameter', 'volume', 'purity', 'shrink_ratio',
        'gauge', 'color', 'section', 'width', 'hole_count', 'flux_core',
        'size', 'connector', 'safety',
    ]),
    ('Конструкция', [
        'type', 'dielectric', 'material', 'configuration',
        'turns', 'pin_count', 'pitch', 'chipset', 'chipset_support',
        'chassis',
    ]),
    ('Общее', [
        'os', 'weight', 'stylus', 'mounting',
    ]),
]


INTERNAL_PARAM_KEYS = frozenset({
    'applications',
    'datasheet_extracted',
    'catalog_quality',
    'catalog_version',
    '_catalog_version',
    'image_source',
    'image_source_url',
    'image_source_policy',
    'image_verified_from',
    'image_original_url',
    'image_license_note',
})

_GROUPED_SKIP_KEYS = INTERNAL_PARAM_KEYS  # рендерятся отдельными секциями или используются сервисами


def group_parameters(params):
    """Группирует плоский dict параметров в список (group, [(label, value), ...]).
    Ключи из _GROUPED_SKIP_KEYS (например, 'applications' — длинный текстовый
    блок) исключаются: они показываются собственными секциями в шаблоне."""
    if not params:
        return []

    remaining = {k: v for k, v in params.items() if k not in _GROUPED_SKIP_KEYS}
    result = []

    for group_name, keys in PARAM_GROUPS:
        group_items = []
        for k in keys:
            if k in remaining:
                label = PARAM_LABELS.get(k, k.replace('_', ' ').capitalize())
                group_items.append((label, remaining.pop(k)))
        if group_items:
            result.append((group_name, group_items))

    # Остальные ключи — в «Прочие»
    if remaining:
        extras = [
            (PARAM_LABELS.get(k, k.replace('_', ' ').capitalize()), v)
            for k, v in remaining.items()
        ]
        result.append(('Прочие', extras))

    return result


# ════════════════════════════════════════════════════════════════════
# 3. Чипы карточки (CARD_PARAM_*) + chip_filter_name, chip_group
# ════════════════════════════════════════════════════════════════════

CARD_PARAM_ORDER = [
    # === РЭБ: пассивные ===
    'resistance', 'capacitance', 'inductance',
    'voltage', 'max_voltage', 'current', 'max_current', 'power', 'tolerance',
    'type', 'package', 'mounting', 'dielectric', 'temp_coef', 'max_temp', 'temp_max',
    # === РЭБ: активные (транзисторы/диоды/IC) ===
    'supply_voltage', 'vceo', 'vds', 'ic', 'id', 'hfe', 'ft', 'rds_on',
    'vf', 'if', 'vrrm', 'vz', 'trr', 'wavelength',
    'output_current', 'dropout', 'family', 'channels', 'flash', 'gbw', 'slew_rate', 'interface',
    'coil_voltage', 'contact_rating', 'configuration', 'pins', 'pitch', 'dcr', 'srf',
    # === Модули / датчики / учебные платы ===
    'mcu', 'logic_level', 'clock', 'gpio', 'wireless',
    'sensor_type', 'measurement_range', 'accuracy', 'controller',
    'display', 'resolution',
    # === Инструменты / расходники ===
    'sample_rate', 'memory', 'counts', 'true_rms', 'safety',
    'temperature_range', 'tip_type', 'airflow', 'compatibility',
    'magnification', 'light', 'board_size', 'points', 'power_rails',
    'contact_count', 'melting_point', 'diameter', 'volume', 'purity',
    'shrink_ratio', 'gauge', 'color', 'section', 'width', 'hole_count',
    'flux_core', 'size', 'connector', 'orientation', 'gender', 'contact_material',
    'rotation', 'mode', 'signal', 'touch', 'delay', 'application',
    # === CPU ===
    'cores', 'threads', 'boost_clock', 'base_clock', 'cache_l3', 'socket',
    'tdp', 'process',
    # === GPU ===
    'gpu_chip', 'cuda_cores', 'stream_processors', 'vram', 'memory_bus',
    'outputs', 'power_conn',
    # === RAM ===
    'frequency', 'latency',
    # === SSD ===
    'capacity', 'interface', 'form_factor',
    'read_speed', 'write_speed', 'tbw', 'dram_cache',
    # === PSU ===
    'wattage', 'certification', 'efficiency', 'modular',
    # === Cooling ===
    'tdp_rated', 'fan_count', 'fan_size',
    # === Motherboards ===
    'chipset', 'ram_slots', 'pcie', 'm2_slots', 'network',
    # === Monitors ===
    'screen_size', 'resolution', 'panel', 'refresh_rate', 'response_time',
    'hdr', 'inputs',
    # === Smartphones / tablets / laptops ===
    'chip', 'cpu', 'gpu', 'ram', 'storage', 'camera', 'battery',
    'battery_earbuds', 'battery_case', 'charging', 'os', 'weight',
    'chassis', 'stylus', 'connectivity',
    # === Audio (наушники) ===
    'anc', 'driver', 'codec',
    # === Misc ===
    'rgb', 'igpu', 'chipset_support', 'length', 'bandwidth',
]

CARD_PARAM_LABELS = {
    'resistance': 'R',
    'capacitance': 'C',
    'inductance': 'L',
    'voltage': 'V',
    'max_voltage': 'Umax',
    'current': 'I',
    'max_current': 'Imax',
    'output_current': 'Iout',
    'power': 'P',
    # Не 'тут было ±' — value у tolerance уже содержит ±20%, label дублировал
    # и выводил «±±20%». Текстовый префикс читается яснее + готов к i18n.
    'tolerance': 'Доп.',
    'type': 'Тип',
    'package': 'Упак.',
    'mounting': 'Монтаж',
    'supply_voltage': 'Vcc',
    'vceo': 'Vceo',
    'vds': 'Vds',
    'ic': 'Ic',
    'id': 'Id',
    'rds_on': 'Rds',
    'hfe': 'hFE',
    'ft': 'fT',
    'dropout': 'Drop',
    'vf': 'Vf',
    'if': 'If',
    'vrrm': 'Vr',
    'vz': 'Vz',
    'trr': 'trr',
    'wavelength': 'λ',
    'slew_rate': 'SR',
    'coil_voltage': 'Кат.',
    'contact_rating': 'Контакт',
    'configuration': 'Схема',
    'pins': 'Pin',
    'pitch': 'Шаг',
    'mcu': 'MCU',
    'logic_level': 'Vlogic',
    'clock': 'Clk',
    'gpio': 'GPIO',
    'wireless': 'Radio',
    'sensor_type': 'Сенсор',
    'measurement_range': 'Диап.',
    'accuracy': 'Точн.',
    'controller': 'Ctrl',
    'sample_rate': 'SR',
    'memory': 'Пам.',
    'counts': 'Counts',
    'true_rms': 'RMS',
    'safety': 'CAT',
    'temperature_range': 'Темп.',
    'tip_type': 'Жало',
    'airflow': 'Воздух',
    'compatibility': 'Совм.',
    'magnification': 'Увел.',
    'light': 'Свет',
    'board_size': 'Плата',
    'rotation': 'Повор.',
    'points': 'Точек',
    'power_rails': 'Шины',
    'contact_count': 'Кол-во',
    'orientation': 'Ориент.',
    'gender': 'Контакт',
    'contact_material': 'Мат.',
    'melting_point': 'Плавл.',
    'diameter': 'Ø',
    'volume': 'Объём',
    'purity': 'Чист.',
    'shrink_ratio': 'Усадка',
    'gauge': 'AWG',
    'color': 'Цвет',
    'section': 'Сеч.',
    'width': 'Шир.',
    'hole_count': 'Отв.',
    'flux_core': 'Флюс',
    'size': 'Размер',
    'connector': 'Разъём',
    'mode': 'Режим',
    'signal': 'Сигнал',
    'touch': 'Touch',
    'delay': 'Зад.',
    'application': 'Назн.',
    'capacity': 'Объём',
    'interface': 'Инт.',
    'form_factor': 'Ф/ф',
    'wattage': 'Вт',
    'screen_size': 'Экран',
    'chip': 'SoC',
    'cpu': 'CPU',
    'gpu': 'GPU',
    'ram': 'RAM',
    'storage': 'SSD',
    'tdp': 'TDP',
    # SSD-параметры (NVMe-категория)
    'read_speed':  'Rd',
    'write_speed': 'Wr',
    'tbw':         'TBW',
    'dram_cache':  'DRAM',
    # Конденсаторный диэлектрик
    'dielectric':  'Диэл.',
    # === CPU ===
    'cores': 'Ядер', 'threads': 'Потоков',
    'base_clock': 'Базов.', 'boost_clock': 'Турбо',
    'cache_l3': 'L3', 'socket': 'Сокет', 'process': 'Техпроц.',
    'igpu': 'iGPU',
    # === GPU ===
    'gpu_chip': 'Чип', 'cuda_cores': 'CUDA',
    'stream_processors': 'Stream', 'vram': 'VRAM',
    'memory_bus': 'Шина', 'outputs': 'Видеовых.', 'power_conn': 'Питание',
    # === RAM ===
    'frequency': 'Част.', 'latency': 'CL',
    # === PSU ===
    'certification': 'Сертиф.', 'efficiency': 'КПД', 'modular': 'Модуль',
    # === Cooling ===
    'tdp_rated': 'TDP', 'fan_count': 'Вент.', 'fan_size': '⌀ вент.',
    # === Motherboards ===
    'chipset': 'Чипсет', 'ram_slots': 'DIMM', 'pcie': 'PCIe',
    'm2_slots': 'M.2', 'network': 'LAN', 'chipset_support': 'Чипсеты',
    # === Monitors ===
    'resolution': 'Разреш.', 'panel': 'Матр.',
    'refresh_rate': 'Гц', 'response_time': 'Откл.', 'hdr': 'HDR',
    'inputs': 'Входы',
    # === Phones/tablets/laptops ===
    'camera': 'Камера', 'battery': 'Батарея',
    'battery_earbuds': 'Бат. (наушн.)', 'battery_case': 'Бат. (кейс)',
    'charging': 'Заряд.', 'os': 'ОС', 'weight': 'Масса',
    'chassis': 'Корпус', 'stylus': 'Стилус', 'connectivity': 'Связь',
    # === Audio ===
    'anc': 'ANC', 'driver': 'Излуч.', 'codec': 'Кодек',
    # === Misc ===
    'rgb': 'RGB', 'length': 'Длина', 'bandwidth': 'Пропуск. сп.',
    'temp_coef': 'TCR',
    'max_temp': 'Tmax',
    'temp_max': 'Tmax',
    'dcr': 'DCR',
    'srf': 'SRF',
    'family': 'Серия',
    'channels': 'Кан.',
    'flash': 'Flash',
    'gbw': 'GBW',
}

# Маппинг ключа параметра → имя GET-параметра фильтра. Используется в шаблонах
# карточки, чтобы превратить чип в ссылку на /category/?<filter>=<value>.
# Должно соответствовать ENGINEERING_FILTERS в shop/views.py.
CARD_PARAM_FILTER_MAP = {
    # Номинал
    'value': 'nominal', 'resistance': 'nominal', 'capacitance': 'nominal',
    'inductance': 'nominal', 'capacity': 'nominal',
    # Мощность
    'power': 'power', 'wattage': 'power', 'tdp': 'power', 'tdp_rated': 'power',
    # Напряжение
    'voltage': 'voltage', 'max_voltage': 'voltage', 'supply_voltage': 'voltage', 'vceo': 'voltage',
    'vr': 'voltage', 'vrrm': 'voltage', 'vf': 'voltage', 'vz': 'voltage', 'coil_voltage': 'voltage',
    # Ток / выводы / тип
    'current': 'current', 'max_current': 'current', 'output_current': 'current',
    'ic': 'current', 'id': 'current', 'if': 'current',
    'type': 'type',
    'pins': 'pins', 'pin_count': 'pins', 'contact_count': 'pins',
    'pitch': 'pitch',
    # Допуск
    'tolerance': 'tolerance',
    # Потребительская электроника и PC-компоненты
    'frequency': 'frequency', 'base_clock': 'frequency', 'boost_clock': 'frequency',
    'refresh_rate': 'frequency', 'bandwidth': 'frequency',
    'ram': 'capacity', 'storage': 'capacity', 'vram': 'capacity',
    'battery': 'capacity', 'battery_earbuds': 'capacity', 'battery_case': 'capacity',
    'cache_l3': 'capacity',
    'screen_size': 'display', 'resolution': 'display', 'panel': 'display',
    'display': 'display', 'hdr': 'display',
    'socket': 'platform', 'chipset': 'platform', 'chipset_support': 'platform',
    'chip': 'platform', 'cpu': 'platform', 'gpu': 'platform', 'gpu_chip': 'platform',
    'process': 'platform', 'mcu': 'platform', 'controller': 'platform',
    'connectivity': 'connectivity', 'network': 'connectivity', 'outputs': 'connectivity',
    'inputs': 'connectivity', 'power_conn': 'connectivity', 'm2_slots': 'connectivity',
    'pcie': 'connectivity', 'ram_slots': 'connectivity', 'charging': 'connectivity',
    'os': 'connectivity', 'codec': 'connectivity', 'wireless': 'connectivity',
    'connector': 'connectivity',
    'compatibility': 'compatibility',
    # Product.package_type
    'package': 'package',
    # Расширенные (дублируют ENGINEERING_FILTERS в views.py) — каждый
    # параметр теперь даёт кликабельный чип в карточке.
    'form_factor': 'form_factor',
    'interface': 'interface',
    'dielectric': 'dielectric',
    'mounting': 'mounting',
    'material': 'material', 'contact_material': 'material', 'flux_core': 'material',
    'application': 'application',
    'length': 'size', 'width': 'size', 'diameter': 'size', 'size': 'size',
    'board_size': 'size', 'hole_count': 'size', 'points': 'size', 'power_rails': 'size',
    'gauge': 'wire', 'section': 'wire', 'color': 'wire',
    'configuration': 'configuration', 'orientation': 'configuration', 'gender': 'configuration',
    'temperature_range': 'temperature_range', 'operating_temp': 'temperature_range',
    'max_temp': 'temperature_range', 'temp_max': 'temperature_range',
    'min_temp': 'temperature_range', 'melting_point': 'temperature_range',
    'mode': 'mode', 'signal': 'mode',
    'safety': 'safety',
}


def chip_filter_name(key):
    """Возвращает имя GET-параметра для чипа, либо пустую строку если параметр
    не поддерживает фильтрацию (тогда шаблон отрендерит чип без ссылки)."""
    if key in CARD_PARAM_FILTER_MAP:
        return CARD_PARAM_FILTER_MAP[key]
    if (
        key
        and key not in CARD_PARAM_EXCLUDE
        and not (isinstance(key, str) and key.startswith('_'))
    ):
        # Любой видимый параметр должен быть действием. Если для поля еще нет
        # отдельного backend-фильтра, используем общий инженерный поиск.
        return 'q'
    return ''


def chip_value_valid(param_filter_options, key, value):
    """True если значение `value` есть в списке доступных для фильтра `key`.

    Шаблон вызывает: `{% if chip_value_valid param_filter_options item.key item.value %}`.
    Если param_filter_options отсутствует (например, страница без sidebar),
    возвращает True — чтобы чип всё-таки был кликабельным как fallback.
    Цель — отсечь чипы, ведущие на пустую страницу (filter применится,
    но 0 товаров найдут, юзер расстроится).
    """
    if value in (None, ''):
        return False
    # UX-решение каталога V3: все видимые chips кликабельны. Для строгих
    # facet-фильтров значение обычно есть в param_filter_options, а для редких
    # инженерных полей chip_filter_name() дает fallback в `q`.
    if not param_filter_options:
        return True
    filter_name = CARD_PARAM_FILTER_MAP.get(key)
    if not filter_name:
        return key not in CARD_PARAM_EXCLUDE
    if filter_name in {'q', 'package'}:
        return True
    available = param_filter_options.get(filter_name) or []
    if not available:
        return True
    if str(value) in available:
        return True
    # Фильтр может быть шире, чем список facet-значений на текущей странице
    # (например, значение скрыто предыдущим фильтром). Оставляем chip
    # кликабельным, чтобы пользователь мог перейти к поиску/сужению.
    return True


# Группы параметров для color-coding лейблов в карточке. Группа = одна
# семантическая категория измерения → один акцентный цвет.
# ВАЖНО: имя _COLOR_GROUPS (раньше было PARAM_GROUPS — конфликтовало
# с верхним PARAM_GROUPS-list'ом, который использует group_parameters().
_COLOR_GROUPS = {
    # Электрические — cyan
    'electrical': {'resistance', 'capacitance', 'inductance', 'voltage', 'max_voltage',
                   'current', 'max_current', 'output_current', 'power',
                   'supply_voltage', 'vceo', 'vds',
                   'ic', 'id', 'rds_on', 'vf', 'if', 'vrrm', 'vz',
                   'coil_voltage', 'contact_rating', 'dcr', 'srf',
                   'wattage', 'tdp', 'tdp_rated',
                   'battery', 'battery_earbuds', 'battery_case', 'charging',
                   'efficiency', 'certification', 'logic_level', 'melting_point'},
    # Корпус/механика — оранжевый
    'package': {'mounting', 'package', 'pins', 'pitch', 'form_factor',
                'chassis', 'material', 'configuration', 'turns', 'pin_count',
                'weight', 'modular', 'fan_size', 'fan_count', 'length',
                'rgb', 'process', 'tip_type', 'board_size', 'points', 'power_rails',
                'contact_count', 'diameter', 'volume', 'purity', 'shrink_ratio',
                'gauge', 'color', 'section', 'width', 'hole_count', 'flux_core',
                'size', 'connector', 'rotation'},
    # Производительность — фиолетовый
    'performance': {'chip', 'cpu', 'gpu', 'gpu_chip', 'ram', 'storage',
                    'read_speed', 'write_speed', 'tbw', 'dram_cache',
                    'screen_size',
                    'cores', 'threads', 'base_clock', 'boost_clock',
                    'cache_l3', 'cuda_cores', 'stream_processors',
                    'vram', 'memory_bus', 'frequency', 'gain',
                    'family', 'channels', 'flash', 'gbw', 'slew_rate', 'mcu', 'clock', 'gpio',
                    'sample_rate', 'memory', 'counts', 'true_rms', 'magnification',
                    'refresh_rate', 'response_time', 'bandwidth'},
    # Интерфейс / форматы / стандарты — зелёный
    'interface': {'interface', 'capacity', 'dielectric', 'type',
                  'socket', 'chipset', 'chipset_support',
                  'm2_slots', 'pcie', 'ram_slots', 'outputs', 'power_conn',
                  'panel', 'resolution', 'hdr', 'display', 'wireless', 'controller',
                  'sensor_type', 'measurement_range', 'mode', 'signal', 'touch', 'application',
                  'connectivity', 'network', 'inputs',
                  'os', 'stylus', 'compatibility', 'light', 'airflow'},
    # Допуск / температурные пределы — жёлтый
    'tolerance': {'tolerance', 'temp_coef', 'operating_temp',
                  'max_temp', 'temp_max', 'min_temp', 'temperature_range', 'accuracy',
                  'safety', 'delay'},
    # Аудио — розовый
    'audio': {'anc', 'driver', 'codec', 'camera'},
}
_KEY_TO_GROUP = {key: group for group, keys in _COLOR_GROUPS.items() for key in keys}


def chip_group(key):
    """Возвращает имя CSS-группы для чипа (для color-coding label-а).
    'electrical' / 'package' / 'performance' / 'interface' / 'tolerance' / 'other'.
    Шаблон добавляет class="param-chip--<group>"."""
    return _KEY_TO_GROUP.get(key, 'other')


# ════════════════════════════════════════════════════════════════════
# 4. STOCK_IMAGE_PATHS + is_stock_image, parameter_preview
# ════════════════════════════════════════════════════════════════════

# Стоковые/категорийные картинки — одно фото на 2+ товара. Раньше юзер
# видел «4 одинаковых кухонных снимка дросселей»: визуально это сбивает,
# реальный товар не отличить. Для таких картинок шаблон рисует
# процедурный SVG-плейсхолдер с категорийной иконкой вместо файла.
STOCK_IMAGE_PATHS = frozenset({
    'products/accessories.jpg',
    'products/cooling.jpg',
    'products/laptops.jpg',
    'products/motherboards.jpg',
    'products/psu.jpg',
    'products/smartphones.jpg',
    'products/tablets.jpg',
    'products/reb/capacitor.jpg',
    'products/reb/capacitor_tht.jpg',
    'products/reb/connector.jpg',
    'products/reb/connector_bnc.jpg',
    'products/reb/ic.jpg',
    'products/reb/ic_tht.jpg',
    'products/reb/inductor.jpg',
    'products/reb/ic_soic.jpg',
    'products/reb/diode.jpg',
    'products/reb/diode_tht.jpg',
    'products/reb/resistor.jpg',
    'products/reb/resistor_tht.jpg',
    'products/reb/relay.jpg',
    'products/reb/relay_signal.jpg',
    'products/reb/transistor.jpg',
    'products/reb/transistor_tht.jpg',
    'products/reb/transistor_to220.jpg',
    'products/reb/trimpot.jpg',
    'products/monitors.jpg',
    'products/ram.jpg',
    'products/ssd.jpg',
    'products/gpu.jpg',
    'products/cpu.jpg',
})


def is_stock_image(image_field):
    """True если у товара назначен расшаренный «категорийный» снимок,
    которым подменено настоящее фото изделия. Шаблон в таком случае
    показывает SVG-плейсхолдер с категорийной иконкой."""
    if not image_field:
        return True
    try:
        image_name = (image_field.name or '').replace('\\', '/')
        if image_name in STOCK_IMAGE_PATHS:
            return True
        lowered = image_name.lower()
        return (
            lowered.startswith('products/commons/')
            or lowered.startswith('products/curated/')
            or 'wikimedia.org' in lowered
            or 'wikipedia.org' in lowered
        )
    except (AttributeError, ValueError):
        return False


CARD_PARAM_EXCLUDE = {
    # Технические/служебные — никогда не нужны в карточке-превью
    'spice_model', 'datasheet_url', 'notes',
    'warranty', 'manufacturer_country',
    # Legacy-ключи: в реальных данных используются 'modular'/'rgb'/'length'
    # без суффикса 'lighting'/'-ity' — этих имён вообще нет в БД.
    'modularity', 'rgb_lighting', 'cable_length',
    # Длинный текстовый блок — рендерится отдельной секцией на
    # product_detail.html, не помещается в формат «label/value» чипа.
    'applications',
    'datasheet_extracted',
    # Внутренние маркеры (используются командами populate_catalog_v2,
    # apply_curated_product_photos и т.п. для идемпотентного re-import'а).
    # В карточке-превью это шум — «catalog version: v2» бесполезен юзеру.
    'catalog_version', '_catalog_version', 'catalog_quality',
    # Метаинформация о происхождении PNG-картинки (curated/generated/verified)
    # — используется audit'ом media-policy, не предназначена для отображения.
    'image_source', 'image_source_url', 'image_source_policy',
    'image_verified_from', 'image_original_url', 'image_license_note',
}

WIDE_CARD_VALUE_KEYS = frozenset({
    'type',
    'chip',
    'cpu',
    'gpu',
    'resolution',
    'connectivity',
    'outputs',
    'inputs',
    'power_conn',
    'chipset_support',
    'contact_rating',
    'configuration',
    'interface',
    'wireless',
    'measurement_range',
    'compatibility',
    'sensor_type',
    'temperature_range',
    'material',
    'contact_material',
    'flux_core',
    'connector',
    'safety',
    'signal',
    'mode',
    'application',
})


def parameter_preview(params, limit=5):
    """Короткий список ключевых параметров для компактной карточки товара."""
    if not params:
        return []
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 5

    selected = []
    used = set()
    # Внутренние ключи (с префиксом '_' и '__') — никогда не показываются.
    # Конвенция: используются commands и services для idempotency-маркеров,
    # training metadata, audit полей.
    def _is_internal(key):
        return isinstance(key, str) and key.startswith('_')

    def _preview_item(key, value):
        text = str(value)
        return {
            'key': key,
            'label': CARD_PARAM_LABELS.get(key, PARAM_LABELS.get(key, key.replace('_', ' ').capitalize())),
            'value': value,
            'wide': key in WIDE_CARD_VALUE_KEYS and len(text) > 15,
        }

    for key in CARD_PARAM_ORDER:
        if key in used or key not in params or key in CARD_PARAM_EXCLUDE or _is_internal(key):
            continue
        value = params.get(key)
        if value in (None, ''):
            continue
        selected.append(_preview_item(key, value))
        used.add(key)
        if len(selected) >= limit:
            return selected

    for key, value in params.items():
        if key in used or key in CARD_PARAM_EXCLUDE or _is_internal(key) or value in (None, ''):
            continue
        selected.append(_preview_item(key, value))
        if len(selected) >= limit:
            break
    return selected


DATASHEET_FIELD_LABELS = {
    'pinout_keywords': 'Выводы',
    'absolute_maximum_ratings': 'Предельные режимы',
    'recommended_operating_conditions': 'Рабочие условия',
    'package': 'Корпус',
    'thermal_data': 'Тепловые данные',
    'typical_application_hints': 'Применение',
}


def datasheet_summary(params):
    """Compact view model for Product.parameters.datasheet_extracted."""
    record = (params or {}).get('datasheet_extracted') if isinstance(params, dict) else None
    if not isinstance(record, dict):
        return None
    fields = record.get('fields') or {}
    found = []
    snippets = []
    for key, label in DATASHEET_FIELD_LABELS.items():
        values = fields.get(key) or []
        if values:
            found.append({'key': key, 'label': label, 'count': len(values)})
            if len(snippets) < 3:
                snippets.append({'label': label, 'text': str(values[0])})
    if not found:
        return None
    return {
        'confidence': record.get('confidence'),
        'source_url': record.get('source_url'),
        'extractor': record.get('extractor') or 'metadata',
        'checked_at': record.get('checked_at'),
        'fields': found,
        'snippets': snippets,
    }


# ════════════════════════════════════════════════════════════════════
# 5. Бренды + delivery_hint (brand-color бейджи)
# ════════════════════════════════════════════════════════════════════

# Slug → (display name, brand color, letter). Цвета — primary brand color.
MANUFACTURER_BRANDS = {
    'apple':     ('Apple',         '#a8a8a8', 'A'),
    'samsung':   ('Samsung',       '#1428a0', 'S'),
    'nvidia':    ('NVIDIA',        '#76b900', 'N'),
    'amd':       ('AMD',           '#ed1c24', 'A'),
    'intel':     ('Intel',         '#0071c5', 'I'),
    'ti':        ('Texas Instr.',  '#cc0000', 'TI'),
    'st':        ('STMicro',       '#03234b', 'ST'),
    'vishay':    ('Vishay',        '#c8102e', 'V'),
    'infineon':  ('Infineon',      '#009933', 'IF'),
    'onsemi':    ('ON Semi',       '#003366', 'ON'),
    'nxp':       ('NXP',           '#ff8200', 'NXP'),
    'panasonic': ('Panasonic',     '#0d4283', 'P'),
    'murata':    ('Murata',        '#003c84', 'M'),
    'kemet':     ('Kemet',         '#ce0000', 'K'),
    'nichicon':  ('Nichicon',      '#0d4283', 'N'),
    'yageo':     ('Yageo',         '#d1232a', 'Y'),
    'bourns':    ('Bourns',        '#033478', 'B'),
    'tdk':       ('TDK',           '#006eb6', 'TDK'),
    'wurth':     ('Würth',         '#d22d28', 'W'),
}


# Name-based fallback для брендов, которых нет в Product.MANUFACTURER_CHOICES.
# Порядок важен: более специфичные needles идут первыми.
NAME_TO_BRAND = [
    # GPU / процессоры
    ('rtx ',           ('NVIDIA',     '#76b900', 'N')),
    ('nvidia',         ('NVIDIA',     '#76b900', 'N')),
    ('radeon',         ('AMD',        '#ed1c24', 'A')),
    ('ryzen',          ('AMD',        '#ed1c24', 'A')),
    ('core i',         ('Intel',      '#0071c5', 'I')),
    # Apple-экосистема
    ('iphone',         ('Apple',      '#a8a8a8', 'A')),
    ('ipad',           ('Apple',      '#a8a8a8', 'A')),
    ('macbook',        ('Apple',      '#a8a8a8', 'A')),
    ('airpods',        ('Apple',      '#a8a8a8', 'A')),
    # Samsung-смартфоны/планшеты
    ('galaxy',         ('Samsung',    '#1428a0', 'S')),
    ('samsung',        ('Samsung',    '#1428a0', 'S')),
    # Другие смартфон-бренды
    ('oneplus',        ('OnePlus',    '#eb0028', 'OP')),
    # RAM
    ('hyperx fury',    ('HyperX',     '#a31a23', 'HX')),
    ('fury beast',     ('Kingston',   '#a31a23', 'K')),
    ('kingston',       ('Kingston',   '#a31a23', 'K')),
    ('dominator',      ('Corsair',    '#fcd000', 'C')),
    ('trident z',      ('G.Skill',    '#c10039', 'GS')),
    ('g.skill',        ('G.Skill',    '#c10039', 'GS')),
    # SSD
    ('990 pro',        ('Samsung',    '#1428a0', 'S')),
    ('sn850',          ('WD',         '#0073cf', 'WD')),
    ('wd black',       ('WD',         '#000000', 'WD')),
    ('crucial',        ('Crucial',    '#0073e6', 'CR')),
    ('nv2',            ('Kingston',   '#a31a23', 'K')),
    # PSU
    ('hx850',          ('Corsair',    '#fcd000', 'C')),
    ('supernova',      ('EVGA',       '#404040', 'E')),
    ('evga',           ('EVGA',       '#404040', 'E')),
    ('focus plus',     ('Seasonic',   '#e94e1b', 'SE')),
    ('seasonic',       ('Seasonic',   '#e94e1b', 'SE')),
    ('toughpower',     ('Thermaltake','#c00000', 'TT')),
    ('thermaltake',    ('Thermaltake','#c00000', 'TT')),
    # Cooling
    ('noctua',         ('Noctua',     '#dba36a', 'NO')),
    ('h150i',          ('Corsair',    '#fcd000', 'C')),
    ('dark rock',      ('be quiet!',  '#212121', 'BQ')),
    ('be quiet',       ('be quiet!',  '#212121', 'BQ')),
    ('freezer 50',     ('Arctic',     '#0070ba', 'AR')),
    ('arctic',         ('Arctic',     '#0070ba', 'AR')),
    # Motherboards / Monitors
    ('rog ',           ('ASUS ROG',   '#cc0000', 'RG')),
    ('proart',         ('ASUS',       '#000080', 'AS')),
    ('asus',           ('ASUS',       '#000080', 'AS')),
    ('aorus',          ('Gigabyte',   '#ff6600', 'AO')),
    ('gigabyte',       ('Gigabyte',   '#ff6600', 'G')),
    ('meg ',           ('MSI',        '#cc0000', 'M')),
    ('msi ',           ('MSI',        '#cc0000', 'M')),
    ('pro b850',       ('MSI',        '#cc0000', 'M')),
    ('lg ',            ('LG',         '#a50034', 'LG')),
    ('ultrawide',      ('LG',         '#a50034', 'LG')),
    # Аксессуары — generic
    ('hdmi ',          ('HDMI',       '#5a5a5a', 'H')),
    ('displayport',    ('VESA DP',    '#1f4e79', 'DP')),
    ('anker',          ('Anker',      '#00aaff', 'AN')),
    ('corsair',        ('Corsair',    '#fcd000', 'C')),
    # РЭБ-производители
    ('omron',          ('Omron',      '#0099d4', 'OM')),
    ('finder',         ('Finder',     '#003478', 'FI')),
    ('panasonic',      ('Panasonic',  '#0d4283', 'P')),
    ('microchip',      ('Microchip',  '#ee3124', 'MC')),
    ('atmega',         ('Microchip',  '#ee3124', 'MC')),
    ('mcp',            ('Microchip',  '#ee3124', 'MC')),
    ('jst ',           ('JST',        '#003478', 'J')),
    ('phoenix',        ('Phoenix',    '#009639', 'PX')),
    ('kingbright',     ('Kingbright', '#00a651', 'KB')),
    ('würth',          ('Würth',      '#d22d28', 'W')),
    ('wurth',          ('Würth',      '#d22d28', 'W')),
    ('vishay',         ('Vishay',     '#c8102e', 'V')),
    ('on semi',        ('ON Semi',    '#003366', 'ON')),
    ('texas instr',    ('TI',         '#cc0000', 'TI')),
    ('kemet',          ('KEMET',      '#ce0000', 'K')),
    ('murata',         ('Murata',     '#003c84', 'M')),
    ('nichicon',       ('Nichicon',   '#0d4283', 'N')),
    ('tdk ',           ('TDK',        '#006eb6', 'TDK')),
    ('bourns',         ('Bourns',     '#033478', 'B')),
    ('yageo',          ('Yageo',      '#d1232a', 'Y')),
    ('infineon',       ('Infineon',   '#009933', 'IF')),
    ('nxp ',           ('NXP',        '#ff8200', 'NXP')),
    ('st ',            ('STMicro',    '#03234b', 'ST')),
]


def brand_badge(product):
    """Возвращает dict с brand-info или None.
    1) Сначала смотрит product.manufacturer (slug из MANUFACTURER_CHOICES).
    2) Если 'other' или not in MANUFACTURER_BRANDS — fallback на детект по
       подстроке в product.name (для NVIDIA/Kingston/Corsair/ASUS — их нет
       в MANUFACTURER_CHOICES, а делать миграцию ради бейджа дорого).
    3) Если товар добавлен через Enterprise add-product UI и юзер выбрал
       «моя организация» — parameters._manufacturer_org_name содержит имя
       org'а; используем его (бейдж с первой буквой имени организации).
    """
    slug = getattr(product, 'manufacturer', None)
    if slug and slug != 'other':
        info = MANUFACTURER_BRANDS.get(slug)
        if info:
            return {'name': info[0], 'color': info[1], 'letter': info[2]}

    # Enterprise-org как «бренд»: имя берём из parameters._manufacturer_org_name
    params = getattr(product, 'parameters', None) or {}
    org_name = params.get('_manufacturer_org_name')
    if org_name and isinstance(org_name, str):
        return {
            'name': org_name,
            # Стабильный цвет от имени организации — каждый бренд свой оттенок,
            # но всегда один и тот же при одинаковом имени.
            'color': _stable_org_color(org_name),
            'letter': org_name[:1].upper(),
        }

    # Fallback: парсим название
    name = (getattr(product, 'name', '') or '').lower()
    for needle, info in NAME_TO_BRAND:
        if needle in name:
            return {'name': info[0], 'color': info[1], 'letter': info[2]}
    return None


def _stable_org_color(name: str) -> str:
    """Хэш-функция → HSL-цвет: одно и то же имя всегда даёт один и тот же оттенок.

    Используется для бейджа Enterprise-org'а в каталоге. HSL с фикс. saturation/
    lightness даёт читаемый цвет на тёмном фоне.
    """
    h = abs(hash(name)) % 360
    return f'hsl({h}, 65%, 45%)'


def delivery_hint(product):
    """Возвращает dict {label, css_class, icon} по product.stock.

    Для каталога нужна короткая «сигнальная» строка: «Доставка завтра»
    даёт ощущение «куплю прямо сейчас» лучше, чем «125 шт. на складе».
    Пороги stock'а — практический MVP-маркет. Без реальной системы складов
    это «mock» — но он функционально полезен.
    """
    stock = getattr(product, 'stock', 0) or 0
    if stock >= 50:
        return {'label': 'Доставка завтра',     'css_class': 'delivery--fast', 'icon': '🚚'}
    if stock >= 10:
        return {'label': 'Доставка 1–2 дня',    'css_class': 'delivery--ok',   'icon': '📦'}
    if stock > 0:
        return {'label': 'Мало · 1–2 дня',      'css_class': 'delivery--low',  'icon': '⚠️'}
    return     {'label': 'Под заказ 7–10 дней', 'css_class': 'delivery--out',  'icon': '⏳'}


# ════════════════════════════════════════════════════════════════════
# 6. Рейтинг и отзывы (seeded, без БД)
# ════════════════════════════════════════════════════════════════════

# Демо-функционал: рейтинг и список отзывов генерируются детерминированно
# по product.id. Без таблицы Review — в дипломном проекте достаточно
# для демонстрации UX. Чтобы не показывать «1.2 ★» для всех товаров,
# распределение скошено в сторону 4.0-5.0 (как у реальных маркетплейсов).

_REVIEW_NAMES = [
    'Александр К.', 'Мария Л.', 'Дмитрий П.', 'Анна С.', 'Игорь Б.',
    'Екатерина Н.', 'Сергей М.', 'Ольга Р.', 'Павел Т.', 'Наталья В.',
    'Андрей Ф.', 'Юлия Ж.', 'Максим Д.', 'Светлана Г.', 'Артём Х.',
]

_REVIEW_TEXTS_POS = [
    'Отличный товар! Качество на высоте, доставка быстрая.',
    'Использую уже несколько месяцев — претензий нет.',
    'Цена-качество — на уровне. Рекомендую.',
    'Полностью соответствует описанию. Беру повторно для нового проекта.',
    'Работает как заявлено. Магазин — на 5+.',
    'Покупкой доволен. Упаковка надёжная, всё пришло без повреждений.',
    'Использую в инженерных задачах — характеристики совпадают с datasheet.',
    'Купил по совету коллеги — оказалось дельная вещь.',
]
_REVIEW_TEXTS_MID = [
    'В целом нормально, но за такую цену ожидал большего.',
    'Работает, но упаковка была слегка помята.',
    'По параметрам — норм, но инструкция оставляет желать лучшего.',
]
_REVIEW_DATES = [
    '2 дня назад', '1 неделю назад', '3 недели назад', 'месяц назад',
    '2 месяца назад', 'полгода назад',
]


def product_rating(product):
    """Возвращает dict с рейтингом 3.5-5.0 для product (детерминированно).
    Визуально показываем целыми ★ (4.6 → 5★), точное значение — отдельным
    числом рядом (4.6/5). Half-star символы (⯨) рендерятся не везде —
    надёжнее показать «★★★★★ 4.6», чем «★★★★⯨»."""
    pid = getattr(product, 'id', None) or 0
    rng = _seeded(pid, 'rating')
    roll = rng.random()
    if roll < 0.70:
        value = round(rng.uniform(4.5, 5.0), 1)
    elif roll < 0.95:
        value = round(rng.uniform(4.0, 4.5), 1)
    else:
        value = round(rng.uniform(3.5, 4.0), 1)
    full = int(round(value))                          # 4.6 → 5, 4.3 → 4
    empty = 5 - full
    count = rng.randint(7, 184)
    return {
        'value': value, 'count': count,
        'stars_full': full, 'stars_empty': empty,
        'full_range':  list(range(full)),
        'empty_range': list(range(empty)),
    }


def product_reviews(product, count=3):
    """Возвращает список из <count> seeded-отзывов для product. Без БД."""
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = 3
    pid = getattr(product, 'id', None) or 0
    rng = _seeded(pid, 'reviews')
    rating = product_rating(product)
    avg = rating['value']
    reviews = []
    for _ in range(count):
        # 80% отзывов >= 4★, 15% = 3★, 5% = 2★
        roll = rng.random()
        if roll < 0.80:
            stars = 5 if avg >= 4.5 and rng.random() < 0.6 else 4
            text = rng.choice(_REVIEW_TEXTS_POS)
        elif roll < 0.95:
            stars = 3
            text = rng.choice(_REVIEW_TEXTS_MID)
        else:
            stars = 2
            text = rng.choice(_REVIEW_TEXTS_MID)
        reviews.append({
            'name':  rng.choice(_REVIEW_NAMES),
            'date':  rng.choice(_REVIEW_DATES),
            'stars': stars,
            'stars_filled': list(range(stars)),
            'stars_empty':  list(range(5 - stars)),
            'text':  text,
        })
    return reviews
