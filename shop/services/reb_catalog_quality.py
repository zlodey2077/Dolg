from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

NORMALIZATION_VERSION = 'reb_catalog_quality_v1'

RATING_KEYS = {
    'max_voltage_v',
    'max_voltage',
    'voltage',
    'supply_voltage',
    'max_current_a',
    'max_current',
    'current',
    'output_current',
    'max_power_w',
    'rated_power_w',
    'tdp_w',
    'power',
    'max_power',
    'max_junction_c',
    'max_temperature_c',
    'max_temp',
    'temperature',
}

SMD_HINTS = (
    'SMD',
    'SMT',
    'SOIC',
    'SOT',
    'SOD',
    'SMA',
    'SMB',
    'QFN',
    'TSSOP',
    'MSOP',
    '0603',
    '0805',
    '1206',
    '1210',
    '2512',
    'CD43',
    'USB-C',
    'MICRO-B',
    'SOT-223',
)

THT_HINTS = (
    'THT',
    'DIP',
    'PDIP',
    'TO-92',
    'TO-18',
    'TO-220',
    'DO-35',
    'DO-41',
    'DO-201',
    'AXIAL',
    'RADIAL',
    'HEADER',
    'DUPONT',
    'JST-XH',
    'DB9',
    'SCREW',
    'TERMINAL',
    'RELAY',
    'TOR',
)

FAMILY_DATASHEETS = {
    (
        'resistors',
        'yageo',
    ): 'https://www.yageo.com/upload/media/product/productsearch/datasheet/rchip/PYu-RC_Group_51_RoHS_L_12.pdf',
    ('resistors', 'vishay_smd'): 'https://www.vishay.com/doc?20035',
    ('resistors', 'vishay_tht'): 'https://www.vishay.com/doc?28729',
    ('capacitors', 'murata'): 'https://www.murata.com/en-us/products/capacitor/ceramiccapacitor',
    (
        'capacitors',
        'kemet',
    ): 'https://www.kemet.com/content/dam/kemet/lightning/migration-pdfs/AutoECML/TS0004.pdf',
    ('capacitors', 'nichicon'): 'https://www.nichicon.co.jp/english/products/pdfs/e-uvr.pdf',
    ('connectors', 'jst_xh'): 'https://www.jst-mfg.com/product/pdf/eng/eXH.pdf',
    (
        'connectors',
        'phoenix_terminal',
    ): 'https://www.phoenixcontact.com/en-pc/products/pcb-terminal-block-mkds-1-2-35-1725656',
    ('connectors', 'usb_c'): 'https://www.we-online.com/catalog/datasheet/632723300011.pdf',
    ('connectors', 'we_usb'): 'https://www.we-online.com/en/components/products/WR-COM_USB_3_1_TYPE_C',
    ('connectors', 'we_pinheader'): 'https://www.we-online.com/en/components/products/WR-PHD',
    ('connectors', 'db9'): 'https://www.amphenol-cs.com/d-sub-connectors.html',
    ('connectors', 'rj45'): 'https://www.we-online.com/en/components/products/WR-MJ',
    (
        'connectors',
        'dc_jack',
    ): 'https://www.cuidevices.com/catalog/interconnect/connectors/dc-power-connectors/pj-102ah',
    ('relays', 'songle'): 'https://www.songlerelay.com/Public/Uploads/20161104/581c21a2c5c85.pdf',
    ('relays', 'omron_g5le'): 'https://components.omron.com/us-en/datasheet_pdf/K047-E1.pdf',
    ('relays', 'solid_state'): 'https://www.fotek.com.tw/en-gb/product/693',
}

EXACT_DATASHEETS = {
    '1N4001': 'https://www.onsemi.com/download/data-sheet/pdf/1n4001-d.pdf',
    '1N4007': 'https://www.onsemi.com/download/data-sheet/pdf/1n4001-d.pdf',
    '1N4148': 'https://www.onsemi.com/download/data-sheet/pdf/1n914-d.pdf',
    '1N5817': 'https://www.onsemi.com/download/data-sheet/pdf/1n5817-d.pdf',
    '1N5819': 'https://www.onsemi.com/download/data-sheet/pdf/1n5817-d.pdf',
    '1N5822': 'https://www.diodes.com/datasheet/download/1N5822.pdf',
    'BAT54': 'https://www.infineon.com/part/BAT54',
    'SS14': 'https://www.onsemi.com/download/data-sheet/pdf/ss19-d.pdf',
    'BZX55C-3V3': 'https://www.vishay.com/en/product/85604/',
    'BZX55C-5V1': 'https://www.vishay.com/en/product/85604/',
    'BZX55C-12V': 'https://www.vishay.com/en/product/85604/',
    'BC547B': 'https://www.onsemi.com/pdf/datasheet/bc546-d.pdf',
    'BC557B': 'https://www.onsemi.com/pdf/datasheet/bc556b-d.pdf',
    '2N2222A': 'https://www.st.com/resource/en/datasheet/2n2222a.pdf',
    '2N2907A': 'https://www.onsemi.com/pdf/datasheet/p2n2907a-d.pdf',
    '2N3904': 'https://www.onsemi.com/pdf/datasheet/2n3903-d.pdf',
    '2N3906': 'https://www.onsemi.com/pdf/datasheet/2n3906-d.pdf',
    'BC817-25': 'https://www.onsemi.com/pdf/datasheet/bc817-16lt1-d.pdf',
    'BC857B': 'https://www.onsemi.com/pdf/datasheet/bc856alt1-d.pdf',
    'IRF540N': 'https://www.infineon.com/dgdl/irf540npbf.pdf',
    'IRF9540N': 'https://www.infineon.com/dgdl/irf9540npbf.pdf',
    'IRLZ44N': 'https://www.infineon.com/dgdl/Infineon-IRLZ44N-DataSheet-v01_01-EN.pdf',
    'AO3400': 'https://www.aosmd.com/res/data_sheets/AO3400.pdf',
    'AO3401': 'https://www.aosmd.com/res/data_sheets/AO3401.pdf',
    'BSS138': 'https://www.onsemi.com/pdf/datasheet/bss138-d.pdf',
    'TIP120': 'https://www.onsemi.com/pdf/datasheet/tip120-d.pdf',
    'NE555': 'https://www.ti.com/lit/ds/symlink/ne555.pdf',
    'LM358': 'https://www.ti.com/lit/ds/symlink/lm358.pdf',
    'LM324': 'https://www.ti.com/lit/ds/symlink/lm324.pdf',
    'LM741': 'https://www.ti.com/lit/ds/symlink/lm741.pdf',
    'TL072': 'https://www.ti.com/lit/ds/symlink/tl072.pdf',
    'LM386': 'https://www.ti.com/lit/ds/symlink/lm386.pdf',
    'LM7805': 'https://www.st.com/resource/en/datasheet/l78.pdf',
    'LM7812': 'https://www.st.com/resource/en/datasheet/l78.pdf',
    'LM7905': 'https://www.st.com/resource/en/datasheet/l79.pdf',
    'LM7912': 'https://www.st.com/resource/en/datasheet/l79.pdf',
    'LM317T': 'https://www.st.com/resource/en/datasheet/lm217.pdf',
    'AMS1117-3.3': 'https://www.advanced-monolithic.com/pdf/ds1117.pdf',
    'AMS1117-5.0': 'https://www.advanced-monolithic.com/pdf/ds1117.pdf',
    'LM2596': 'https://www.ti.com/lit/ds/symlink/lm2596.pdf',
    'XL6009': 'https://datasheet4u.com/datasheet-pdf/XLSEMI/XL6009/pdf.php?id=775384',
    'ATMEGA328P-PU': 'https://ww1.microchip.com/downloads/en/DeviceDoc/ATmega48A-PA-88A-PA-168A-PA-328-P-DS-DS40002061B.pdf',
    'ATTINY85': 'https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/ProductDocuments/DataSheets/Atmel-2586-AVR-8-bit-Microcontroller-ATtiny25-ATtiny45-ATtiny85_Datasheet.pdf',
    '74HC04': 'https://www.nxp.com/docs/en/data-sheet/74HC_HCT04.pdf',
    '74HC08': 'https://www.nxp.com/docs/en/data-sheet/74HC_HCT08.pdf',
    '74HC32': 'https://www.nxp.com/docs/en/data-sheet/74HC_HCT32.pdf',
    '74HC74': 'https://www.nxp.com/docs/en/data-sheet/74HC_HCT74.pdf',
    '74HC595': 'https://www.nxp.com/docs/en/data-sheet/74HC_HCT595.pdf',
    '74HC165': 'https://www.nxp.com/docs/en/data-sheet/74HC_HCT165.pdf',
    'MCP23017': 'https://ww1.microchip.com/downloads/en/devicedoc/20001952c.pdf',
    'DS1307': 'https://www.analog.com/media/en/technical-documentation/data-sheets/ds1307.pdf',
    'DS18B20': 'https://www.analog.com/media/en/technical-documentation/data-sheets/ds18b20.pdf',
    'AT24C32': 'https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/AT24C32D-64D-I2C-Compatible-2-Wire-Serial-EEPROM-32Kbit-64Kbit-20006031A.pdf',
    'CD43': 'https://www.bourns.com/docs/Product-Datasheets/SRU.pdf',
    'AXIAL': 'https://www.bourns.com/docs/Product-Datasheets/78F.pdf',
    'TOR': 'https://www.we-online.com/en/components/products/WE-TI',
    'LED-3MM-RED': 'https://www.kingbrightusa.com/images/catalog/SPEC/WP710A10ID.pdf',
    'LED-3MM-GREEN': 'https://www.kingbrightusa.com/images/catalog/SPEC/WP710A10GD.pdf',
    'LED-3MM-BLUE': 'https://www.kingbrightusa.com/images/catalog/SPEC/WP710A10QBC-D.pdf',
    'LED-5MM-RED': 'https://www.kingbrightusa.com/images/catalog/SPEC/L-53HD.pdf',
    'LED-5MM-GREEN': 'https://www.kingbrightusa.com/images/catalog/SPEC/L-53GD.pdf',
    'LED-5MM-BLUE': 'https://www.kingbrightusa.com/images/catalog/SPEC/L-53QBC.pdf',
    'LED-5MM-WHITE': 'https://www.kingbrightusa.com/images/catalog/SPEC/WP7113ZGC.pdf',
    'LED-RGB-COMMON-A': 'https://www.kingbrightusa.com/images/catalog/SPEC/WP154A4SUREQBFZGC.pdf',
    'HL-1U-5V': 'https://www.alldatasheet.com/datasheet-pdf/pdf/1132639/SONGLERELAY/SRD-05VDC-SL-C.html',
    'JQX-105F-12V': 'https://www.futurlec.com/Datasheet/Relays/JQX-105F.pdf',
}

ZENER_VOLTAGES = {
    'BZX55C-3V3': '3.3 В',
    'BZX55C-5V1': '5.1 В',
    'BZX55C-12V': '12 В',
}


@dataclass
class NormalizationResult:
    product_id: int | None
    slug: str
    changes: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.changes)


def normalize_reb_product(product, *, force: bool = False) -> NormalizationResult:
    """Infer safe catalog metadata for REB products without touching UI code."""
    category = getattr(product.category, 'slug', '')
    result = NormalizationResult(getattr(product, 'id', None), product.slug)
    if category not in {
        'resistors',
        'capacitors',
        'transistors',
        'ics',
        'diodes',
        'inductors',
        'connectors',
        'relays',
    }:
        return result

    params = dict(product.parameters or {})
    pn = _norm_pn(product.part_number or product.slug)

    new_part_number = product.part_number or infer_part_number(product)
    if new_part_number and new_part_number != product.part_number:
        result.changes['part_number'] = {'old': product.part_number, 'new': new_part_number}
        product.part_number = new_part_number
        pn = _norm_pn(new_part_number)

    package_type = infer_package_type(product, pn)
    if package_type and (force or _package_needs_update(product.package_type, package_type)):
        result.changes['package_type'] = {'old': product.package_type, 'new': package_type}
        product.package_type = package_type

    mounting = params.get('mounting') or infer_mounting(product, pn)
    if mounting and (force or not params.get('mounting')):
        _set_param(params, result, 'mounting', mounting)

    _infer_category_parameters(product, pn, params, result, force=force)
    _add_rating_aliases(params, result)

    datasheet_url = infer_datasheet_url(product, pn)
    if datasheet_url and (force or not product.datasheet_url):
        result.changes['datasheet_url'] = {'old': product.datasheet_url, 'new': datasheet_url}
        product.datasheet_url = datasheet_url
        if not datasheet_url.lower().endswith('.pdf'):
            result.warnings.append('datasheet_url is a product/family reference page, not a direct PDF')

    if result.changed:
        quality = dict(params.get('catalog_quality') or {})
        quality.update(
            {
                'normalizer': NORMALIZATION_VERSION,
                'confidence': _confidence_for(product, params),
                'notes': 'Inferred missing REB catalog fields from part number, package, category and official family documentation.',
            }
        )
        params['catalog_quality'] = quality
        product.parameters = params
    return result


def infer_part_number(product) -> str:
    slug = str(product.slug or '').strip('-')
    if not slug:
        return ''
    return slug.upper().replace('-', '-').replace('254', '2.54').replace('55X21', '5.5X2.1')


def infer_mounting(product, pn: str = '') -> str:
    haystack = ' '.join(
        [
            pn,
            str(product.slug or ''),
            str(product.package_type or ''),
            str(product.name or ''),
            str(product.description or ''),
        ]
    ).upper()
    if any(hint in haystack for hint in THT_HINTS):
        return 'THT'
    if any(hint in haystack for hint in SMD_HINTS):
        return 'SMD'
    if getattr(product.category, 'slug', '') in {'connectors', 'relays'}:
        return 'THT'
    return ''


def infer_package_type(product, pn: str = '') -> str:
    current = str(product.package_type or '').strip()
    category = getattr(product.category, 'slug', '')
    token = pn.upper()
    text = ' '.join([token, str(product.slug or ''), str(product.description or '')]).upper()

    if category == 'diodes':
        if token.startswith('1N400'):
            return 'THT DO-41'
        if token in {'1N5817', '1N5819'}:
            return 'THT DO-41'
        if token == '1N5822':
            return 'THT DO-201'
        if token.startswith('1N4148') or token.startswith('BZX55'):
            return 'THT DO-35'
        if token.startswith('BAT54'):
            return 'SMD SOT-23'
        if token.startswith('SS14'):
            return 'SMD SMA'
        if token.startswith('LED-3MM'):
            return 'THT LED 3 mm'
        if token.startswith('LED-5MM') or token.startswith('LED-RGB'):
            return 'THT LED 5 mm'
    if category == 'transistors':
        if token in {'BC817-25', 'BC857B', 'AO3400', 'AO3401', 'BSS138'}:
            return 'SMD SOT-23'
        if token in {'IRF540N', 'IRF9540N', 'IRLZ44N', 'TIP120'}:
            return 'THT TO-220'
        return current if current and current != 'TO-92' else 'THT TO-92'
    if category == 'ics':
        if token in {'LM7805', 'LM7812', 'LM7905', 'LM7912', 'LM317T'}:
            return 'THT TO-220'
        if token.startswith('AMS1117'):
            return 'SMD SOT-223'
        if token.startswith('74HC'):
            return 'DIP-14 / SOIC-14'
        if 'DIP-28' in text:
            return 'THT DIP-28'
        if 'DIP-14' in text:
            return 'THT DIP-14'
        return 'THT DIP-8'
    if category == 'inductors':
        if token.startswith('CD43'):
            return 'SMD CD43'
        if token.startswith('AXIAL'):
            return 'THT axial'
        if token.startswith('TOR'):
            return 'THT toroidal'
    if category == 'connectors':
        if 'USB-C' in token or 'MICRO-B' in token:
            return 'SMD USB'
        if 'USB-A' in token or 'HEADER' in token or 'DUPONT' in token or 'JST-XH' in token:
            return 'THT 2.54 mm' if 'JST-XH' not in token else 'THT 2.5 mm'
        if 'SCREW' in token:
            return 'THT terminal block'
        if 'DB9' in token:
            return 'THT D-Sub'
        if 'RJ45' in token:
            return 'THT RJ45'
        if 'DC-JACK' in token:
            return 'THT DC jack'
    return current


def infer_datasheet_url(product, pn: str = '') -> str:
    category = getattr(product.category, 'slug', '')
    mfr = str(product.manufacturer or '').lower()
    token = pn.upper()

    if token in EXACT_DATASHEETS:
        return EXACT_DATASHEETS[token]
    for prefix in ('LED-3MM', 'LED-5MM', 'LED-RGB', 'CD43', 'AXIAL', 'TOR'):
        if token.startswith(prefix):
            return EXACT_DATASHEETS.get(prefix) or EXACT_DATASHEETS.get(token, '')
    if token.startswith('BZX55'):
        return EXACT_DATASHEETS['BZX55C-5V1']
    if category == 'resistors':
        if mfr == 'yageo' or token.startswith('RC0603'):
            return FAMILY_DATASHEETS[(category, 'yageo')]
        if mfr == 'vishay' and ('SMD' in str(product.package_type).upper() or token.startswith('CRCW')):
            return FAMILY_DATASHEETS[(category, 'vishay_smd')]
        if mfr == 'vishay':
            return FAMILY_DATASHEETS[(category, 'vishay_tht')]
    if category == 'capacitors':
        if mfr in {'murata', 'kemet', 'nichicon'}:
            return FAMILY_DATASHEETS[(category, mfr)]
    if category == 'connectors':
        if token.startswith('JST-XH'):
            return FAMILY_DATASHEETS[(category, 'jst_xh')]
        if token.startswith('SCREW'):
            return FAMILY_DATASHEETS[(category, 'phoenix_terminal')]
        if token.startswith('USB-C'):
            return FAMILY_DATASHEETS[(category, 'usb_c')]
        if token.startswith('USB'):
            return FAMILY_DATASHEETS[(category, 'we_usb')]
        if token.startswith('HEADER') or token.startswith('DUPONT'):
            return FAMILY_DATASHEETS[(category, 'we_pinheader')]
        if token.startswith('DB9'):
            return FAMILY_DATASHEETS[(category, 'db9')]
        if token.startswith('RJ45'):
            return FAMILY_DATASHEETS[(category, 'rj45')]
        if token.startswith('DC-JACK'):
            return FAMILY_DATASHEETS[(category, 'dc_jack')]
    if category == 'relays':
        if token.startswith('SRD'):
            return FAMILY_DATASHEETS[(category, 'songle')]
        if token.startswith('G5LE'):
            return FAMILY_DATASHEETS[(category, 'omron_g5le')]
        if token.startswith('SSR'):
            return FAMILY_DATASHEETS[(category, 'solid_state')]
    return ''


def _infer_category_parameters(
    product, pn: str, params: dict[str, Any], result: NormalizationResult, *, force: bool = False
) -> None:
    category = getattr(product.category, 'slug', '')
    token = pn.upper()

    if category == 'diodes':
        _infer_diode_params(token, params, result)
    elif category == 'resistors':
        _infer_resistor_params(product, token, params, result)
    elif category == 'transistors':
        _infer_transistor_params(token, params, result)
    elif category == 'ics':
        _infer_ic_params(token, params, result)
    elif category == 'inductors':
        _infer_inductor_params(token, params, result)
    elif category == 'connectors':
        _infer_connector_params(token, params, result)
    elif category == 'relays':
        _infer_relay_params(token, params, result)
    elif category == 'capacitors':
        if params.get('temp_max') and not params.get('max_temp'):
            _set_param(params, result, 'max_temp', params['temp_max'])


def _infer_diode_params(pn: str, params: dict[str, Any], result: NormalizationResult) -> None:
    table = {
        '1N4001': {
            'type': 'rectifier diode',
            'max_voltage': '50 В',
            'current': '1 А',
            'max_current': '30 А имп.',
            'vf': '1.1 В @ 1 А',
        },
        '1N4007': {
            'type': 'rectifier diode',
            'max_voltage': '1000 В',
            'current': '1 А',
            'max_current': '30 А имп.',
            'vf': '1.1 В @ 1 А',
        },
        '1N4148': {
            'type': 'small-signal diode',
            'max_voltage': '100 В',
            'current': '200 мА',
            'max_current': '450 мА имп.',
            'trr': '4 нс',
        },
        '1N5817': {
            'type': 'Schottky diode',
            'max_voltage': '20 В',
            'current': '1 А',
            'max_current': '25 А имп.',
            'vf': '0.45 В тип.',
        },
        '1N5819': {
            'type': 'Schottky diode',
            'max_voltage': '40 В',
            'current': '1 А',
            'max_current': '25 А имп.',
            'vf': '0.6 В тип.',
        },
        '1N5822': {
            'type': 'Schottky diode',
            'max_voltage': '40 В',
            'current': '3 А',
            'max_current': '80 А имп.',
            'vf': '0.55 В тип.',
        },
        'BAT54': {
            'type': 'Schottky diode',
            'max_voltage': '30 В',
            'current': '200 мА',
            'max_current': '600 мА имп.',
            'vf': '0.8 В макс.',
        },
        'SS14': {
            'type': 'Schottky diode',
            'max_voltage': '40 В',
            'current': '1 А',
            'max_current': '30 А имп.',
            'vf': '0.5 В тип.',
        },
    }
    values = table.get(pn)
    if pn.startswith('BZX55'):
        zener_current = {
            'BZX55C-3V3': '150 мА расч.',
            'BZX55C-5V1': '98 мА расч.',
            'BZX55C-12V': '42 мА расч.',
        }
        values = {
            'type': 'Zener diode',
            'voltage': ZENER_VOLTAGES.get(pn, '5.1 В'),
            'power': '0.5 Вт',
            'max_current': zener_current.get(pn, 'по P/Vz'),
        }
    if pn.startswith('LED-'):
        vf = (
            '3.2 В'
            if 'BLUE' in pn
            else ('3.0 В' if 'WHITE' in pn else ('2.1 В' if 'GREEN' in pn else '2.0 В'))
        )
        values = {'type': 'LED', 'vf': vf, 'current': '20 мА', 'max_current': '30 мА'}
    _merge_params(params, result, values or {})


def _infer_resistor_params(product, pn: str, params: dict[str, Any], result: NormalizationResult) -> None:
    package = str(getattr(product, 'package_type', '') or '').upper()
    token = ' '.join([pn, package, str(getattr(product, 'slug', '') or '')]).upper()

    if '0603' in token:
        defaults = {
            'type': 'thick-film resistor',
            'material': 'thick film',
            'max_voltage': '75 В',
            'temp_coef': '100 ppm/°C',
        }
    elif '0805' in token:
        defaults = {
            'type': 'thick-film resistor',
            'material': 'thick film',
            'max_voltage': '150 В',
            'temp_coef': '100 ppm/°C',
        }
    elif '1206' in token:
        defaults = {
            'type': 'thick-film resistor',
            'material': 'thick film',
            'max_voltage': '200 В',
            'temp_coef': '100 ppm/°C',
        }
    elif pn.startswith('MF') or 'METAL' in token:
        defaults = {
            'type': 'metal-film resistor',
            'material': 'metal film',
            'max_voltage': '250 В',
            'temp_coef': '50 ppm/°C',
        }
    else:
        defaults = {'type': 'thick-film resistor', 'material': 'thick film', 'temp_coef': '100 ppm/°C'}

    if 'power' not in params and 'rated_power_w' not in params:
        if '0603' in token:
            defaults['power'] = '0.1 Вт'
        elif '0805' in token:
            defaults['power'] = '0.125 Вт'
        elif '1206' in token:
            defaults['power'] = '0.25 Вт'
        else:
            defaults['power'] = '0.25 Вт'

    _merge_params(params, result, defaults)


def _infer_transistor_params(pn: str, params: dict[str, Any], result: NormalizationResult) -> None:
    table = {
        'BC547B': {
            'type': 'NPN',
            'max_voltage': '45 В',
            'current': '100 мА',
            'hfe': '200...450',
            'ft': '300 МГц',
            'pins': '3',
        },
        'BC557B': {
            'type': 'PNP',
            'max_voltage': '45 В',
            'current': '100 мА',
            'hfe': '220...800',
            'ft': '100 МГц',
            'pins': '3',
        },
        '2N2222A': {
            'type': 'NPN',
            'max_voltage': '40 В',
            'current': '800 мА',
            'hfe': '100...300',
            'ft': '250 МГц',
            'pins': '3',
        },
        '2N2907A': {
            'type': 'PNP',
            'max_voltage': '40 В',
            'current': '600 мА',
            'hfe': '100...300',
            'ft': '200 МГц',
            'pins': '3',
        },
        '2N3904': {
            'type': 'NPN',
            'max_voltage': '40 В',
            'current': '200 мА',
            'hfe': '100...300',
            'ft': '300 МГц',
            'pins': '3',
        },
        '2N3906': {
            'type': 'PNP',
            'max_voltage': '40 В',
            'current': '200 мА',
            'hfe': '100...300',
            'ft': '250 МГц',
            'pins': '3',
        },
        'BC817-25': {
            'type': 'NPN',
            'max_voltage': '45 В',
            'current': '500 мА',
            'hfe': '160...400',
            'ft': '100 МГц',
            'pins': '3',
        },
        'BC857B': {
            'type': 'PNP',
            'max_voltage': '45 В',
            'current': '100 мА',
            'hfe': '220...475',
            'ft': '100 МГц',
            'pins': '3',
        },
        'IRF540N': {
            'type': 'N-MOSFET',
            'max_voltage': '100 В',
            'current': '33 А',
            'rds_on': '44 мОм тип.',
            'power': '130 Вт',
            'pins': '3',
        },
        'IRF9540N': {
            'type': 'P-MOSFET',
            'max_voltage': '100 В',
            'current': '23 А',
            'rds_on': '117 мОм тип.',
            'power': '140 Вт',
            'pins': '3',
        },
        'IRLZ44N': {
            'type': 'Logic N-MOSFET',
            'max_voltage': '55 В',
            'current': '47 А',
            'rds_on': '22 мОм тип.',
            'power': '110 Вт',
            'pins': '3',
        },
        'AO3400': {
            'type': 'N-MOSFET',
            'max_voltage': '30 В',
            'current': '5.7 А',
            'rds_on': '52 мОм тип.',
            'power': '1.4 Вт',
            'pins': '3',
        },
        'AO3401': {
            'type': 'P-MOSFET',
            'max_voltage': '30 В',
            'current': '4 А',
            'rds_on': '85 мОм тип.',
            'power': '1.4 Вт',
            'pins': '3',
        },
        'BSS138': {
            'type': 'N-MOSFET',
            'max_voltage': '50 В',
            'current': '200 мА',
            'rds_on': '3.5 Ом макс.',
            'power': '360 мВт',
            'pins': '3',
        },
        'TIP120': {
            'type': 'NPN Darlington',
            'max_voltage': '60 В',
            'current': '5 А',
            'hfe': '1000 тип.',
            'power': '65 Вт',
            'pins': '3',
        },
    }
    _merge_params(params, result, table.get(pn) or {})


def _infer_ic_params(pn: str, params: dict[str, Any], result: NormalizationResult) -> None:
    table = {
        'NE555': {
            'type': 'Timer',
            'supply_voltage': '4.5...16 В',
            'output_current': '200 мА',
            'pins': '8',
            'frequency': 'до 500 кГц',
        },
        'LM358': {
            'type': 'dual op-amp',
            'supply_voltage': '3...30 В',
            'channels': '2',
            'pins': '8',
            'gbw': '1 МГц',
        },
        'LM324': {
            'type': 'quad op-amp',
            'supply_voltage': '3...30 В',
            'channels': '4',
            'pins': '14',
            'gbw': '1 МГц',
        },
        'LM741': {
            'type': 'op-amp',
            'supply_voltage': '±10...±18 В',
            'channels': '1',
            'pins': '8',
            'gbw': '1 МГц',
            'slew_rate': '0.5 В/мкс',
        },
        'TL072': {
            'type': 'dual JFET op-amp',
            'supply_voltage': '±3.5...±18 В',
            'channels': '2',
            'pins': '8',
            'gbw': '3 МГц',
            'slew_rate': '13 В/мкс',
        },
        'LM386': {
            'type': 'audio amplifier',
            'supply_voltage': '4...12 В',
            'power': '0.7 Вт',
            'pins': '8',
            'gain': '20...200',
        },
        'LM7805': {
            'type': 'linear regulator',
            'voltage': '5 В',
            'current': '1 А',
            'pins': '3',
            'dropout': 'около 2 В',
        },
        'LM7812': {
            'type': 'linear regulator',
            'voltage': '12 В',
            'current': '1 А',
            'pins': '3',
            'dropout': 'около 2 В',
        },
        'LM7905': {
            'type': 'negative linear regulator',
            'voltage': '-5 В',
            'current': '1 А',
            'pins': '3',
            'dropout': 'около 2 В',
        },
        'LM7912': {
            'type': 'negative linear regulator',
            'voltage': '-12 В',
            'current': '1 А',
            'pins': '3',
            'dropout': 'около 2 В',
        },
        'LM317T': {
            'type': 'adjustable linear regulator',
            'voltage': '1.2...37 В',
            'current': '1.5 А',
            'pins': '3',
            'dropout': 'около 3 В',
        },
        'AMS1117-3.3': {
            'type': 'LDO regulator',
            'voltage': '3.3 В',
            'current': '1 А',
            'pins': '3',
            'dropout': '1.1 В тип.',
        },
        'AMS1117-5.0': {
            'type': 'LDO regulator',
            'voltage': '5 В',
            'current': '1 А',
            'pins': '3',
            'dropout': '1.1 В тип.',
        },
        'LM2596': {
            'type': 'buck regulator',
            'voltage': '4.5...40 В',
            'current': '3 А',
            'pins': '5',
            'frequency': '150 кГц',
        },
        'XL6009': {
            'type': 'boost regulator',
            'voltage': '5...32 В',
            'current': '4 А',
            'pins': '5',
            'frequency': '400 кГц',
        },
        'ATMEGA328P-PU': {
            'type': 'AVR MCU',
            'supply_voltage': '1.8...5.5 В',
            'flash': '32 КБ',
            'pins': '28',
            'clock': '20 МГц',
        },
        'ATTINY85': {
            'type': 'AVR MCU',
            'supply_voltage': '1.8...5.5 В',
            'flash': '8 КБ',
            'pins': '8',
            'clock': '20 МГц',
        },
        'MCP23017': {
            'type': 'I2C GPIO expander',
            'supply_voltage': '1.8...5.5 В',
            'interface': 'I2C',
            'pins': '28',
            'gpio': '16',
        },
        'DS1307': {'type': 'RTC', 'supply_voltage': '4.5...5.5 В', 'interface': 'I2C', 'pins': '8'},
        'DS18B20': {
            'type': 'temperature sensor',
            'supply_voltage': '3...5.5 В',
            'interface': '1-Wire',
            'pins': '3',
            'temperature_range': '-55...+125 °C',
        },
        'AT24C32': {
            'type': 'I2C EEPROM',
            'supply_voltage': '1.7...5.5 В',
            'interface': 'I2C',
            'pins': '8',
            'memory': '32 кбит',
        },
    }
    if pn.startswith('74HC'):
        table[pn] = {
            'type': '74HC CMOS logic',
            'supply_voltage': '2...6 В',
            'family': 'HC CMOS',
            'pins': '14',
        }
    _merge_params(params, result, table.get(pn) or {})


def _infer_inductor_params(pn: str, params: dict[str, Any], result: NormalizationResult) -> None:
    value = _extract_inductance(pn)
    if value:
        _set_param(params, result, 'inductance', value)
    if pn.startswith('CD43'):
        current = (
            '2 А' if '1UH' in pn else ('1.5 А' if '10UH' in pn else ('800 мА' if '100UH' in pn else '400 мА'))
        )
        dcr = (
            '50 мОм'
            if '1UH' in pn
            else ('120 мОм' if '10UH' in pn else ('600 мОм' if '100UH' in pn else '900 мОм'))
        )
        srf = (
            '120 МГц'
            if '1UH' in pn
            else ('35 МГц' if '10UH' in pn else ('8 МГц' if '100UH' in pn else '5 МГц'))
        )
        _merge_params(
            params, result, {'type': 'SMD power inductor', 'current': current, 'dcr': dcr, 'srf': srf}
        )
    elif pn.startswith('AXIAL'):
        _merge_params(
            params,
            result,
            {'type': 'axial inductor', 'current': '100 мА', 'dcr': 'до 3 Ом', 'srf': 'зависит от номинала'},
        )
    elif pn.startswith('TOR'):
        _merge_params(
            params,
            result,
            {'type': 'toroidal inductor', 'current': '3 А', 'dcr': 'низкое', 'srf': 'power choke'},
        )


def _infer_connector_params(pn: str, params: dict[str, Any], result: NormalizationResult) -> None:
    if 'USB-C' in pn:
        _merge_params(
            params,
            result,
            {
                'type': 'USB-C receptacle',
                'pins': '16',
                'current': '5 А',
                'voltage': '20 В PD',
                'gender': 'гнездо',
                'orientation': 'горизонтальный',
                'contact_material': 'медь / золочение',
            },
        )
    elif 'USB-MICRO' in pn:
        _merge_params(
            params,
            result,
            {
                'type': 'USB Micro-B receptacle',
                'pins': '5',
                'current': '1.8 А',
                'voltage': '5 В',
                'gender': 'гнездо',
                'orientation': 'горизонтальный',
                'contact_material': 'медь / золочение',
            },
        )
    elif 'USB-A' in pn:
        _merge_params(
            params,
            result,
            {
                'type': 'USB-A receptacle',
                'pins': '4',
                'current': '1.5 А',
                'voltage': '5 В',
                'gender': 'гнездо',
                'orientation': 'горизонтальный',
                'contact_material': 'медь / золочение',
            },
        )
    elif pn.startswith('JST-XH'):
        pins = _first_number(pn) or '2'
        _merge_params(
            params,
            result,
            {
                'type': 'JST XH connector',
                'pins': pins,
                'pitch': '2.5 мм',
                'current': '3 А',
                'gender': 'гнездо/штекер',
                'orientation': 'вертикальный',
                'contact_material': 'луженая медь',
            },
        )
    elif pn.startswith('HEADER') or pn.startswith('DUPONT'):
        _merge_params(
            params,
            result,
            {
                'type': 'pin header',
                'pitch': '2.54 мм',
                'current': '1 А',
                'gender': 'штыревой',
                'orientation': 'прямой',
                'contact_material': 'латунь / золочение',
            },
        )
    elif pn.startswith('SCREW'):
        pins = _first_number(pn) or '2'
        _merge_params(
            params,
            result,
            {
                'type': 'screw terminal block',
                'pins': pins,
                'pitch': '5.08 мм',
                'current': '10 А',
                'voltage': '250 В',
                'orientation': 'вертикальный',
                'contact_material': 'луженая медь',
            },
        )
    elif pn.startswith('DB9'):
        _merge_params(
            params,
            result,
            {
                'type': 'D-Sub connector',
                'pins': '9',
                'current': '5 А',
                'voltage': '250 В',
                'gender': 'гнездо',
                'orientation': 'угловой',
                'contact_material': 'медь / золочение',
            },
        )
    elif pn.startswith('RJ45'):
        _merge_params(
            params,
            result,
            {
                'type': 'RJ45 connector',
                'pins': '8P8C',
                'current': '1.5 А',
                'voltage': '150 В',
                'gender': 'гнездо',
                'orientation': 'угловой',
                'contact_material': 'фосфористая бронза',
            },
        )
    elif pn.startswith('DC-JACK'):
        _merge_params(
            params,
            result,
            {
                'type': 'DC barrel jack',
                'pins': '3',
                'current': '2 А',
                'voltage': '24 В',
                'gender': 'гнездо',
                'orientation': 'горизонтальный',
            },
        )


def _infer_relay_params(pn: str, params: dict[str, Any], result: NormalizationResult) -> None:
    voltage = '12 В DC' if '12V' in pn else '5 В DC'
    if pn.startswith('SSR'):
        _merge_params(
            params,
            result,
            {
                'type': 'solid state relay',
                'coil_voltage': '3...32 В DC',
                'current': '25 А',
                'voltage': '24...380 В AC',
            },
        )
    elif pn.startswith('SRD') or pn.startswith('JQX') or pn.startswith('G5LE'):
        current = '16 А' if pn.startswith('JQX') else '10 А'
        _merge_params(
            params,
            result,
            {
                'type': 'power relay',
                'coil_voltage': voltage,
                'contact_rating': f'{current} / 250 В AC',
                'current': current,
            },
        )
    elif pn.startswith('HL-'):
        _merge_params(
            params,
            result,
            {
                'type': 'signal relay',
                'coil_voltage': voltage,
                'contact_rating': '1 А / 30 В DC',
                'current': '1 А',
            },
        )


def _add_rating_aliases(params: dict[str, Any], result: NormalizationResult) -> None:
    aliases = {
        'vrrm': 'max_voltage',
        'vds': 'max_voltage',
        'vceo': 'max_voltage',
        'vz': 'voltage',
        'if': 'current',
        'ic': 'current',
        'id': 'current',
        'contact_rating': 'current',
        'temp_max': 'max_temp',
        'wattage': 'power',
    }
    for source, target in aliases.items():
        if params.get(source) and not params.get(target):
            _set_param(params, result, target, params[source])


def _merge_params(params: dict[str, Any], result: NormalizationResult, values: dict[str, Any]) -> None:
    for key, value in values.items():
        _set_param(params, result, key, value)


def _set_param(params: dict[str, Any], result: NormalizationResult, key: str, value: Any) -> None:
    if value in (None, ''):
        return
    if params.get(key) in (None, ''):
        params[key] = value
        result.changes[f'parameters.{key}'] = {'old': None, 'new': value}


def _package_needs_update(current: str, inferred: str) -> bool:
    current = str(current or '').strip()
    if not current:
        return True
    weak = {'SMD', 'THT', 'DIP', 'TO-92', 'DO-35', 'A', 'RED', 'GREEN', 'BLUE', 'WHITE', '3V3', '5V1', '12V'}
    return current.upper() in weak and current != inferred


def _confidence_for(product, params: dict[str, Any]) -> float:
    score = 0.55
    if product.part_number:
        score += 0.1
    if product.datasheet_url:
        score += 0.15
    if params.get('mounting'):
        score += 0.05
    if any(key in params for key in RATING_KEYS):
        score += 0.1
    if str(product.datasheet_url).lower().endswith('.pdf'):
        score += 0.05
    return round(min(score, 0.95), 2)


def _norm_pn(value: str) -> str:
    return str(value or '').strip().upper().replace(' ', '').replace('_', '-')


def _extract_inductance(pn: str) -> str:
    match = re.search(r'(\d+(?:\.\d+)?)(UH|MH)', pn, flags=re.IGNORECASE)
    if not match:
        return ''
    value, unit = match.groups()
    return f'{value} {"мкГн" if unit.upper() == "UH" else "мГн"}'


def _first_number(value: str) -> str:
    match = re.search(r'(\d+)', value or '')
    return match.group(1) if match else ''
