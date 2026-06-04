"""CircuitPython Code Generator — Block B1 (master plan 3 weeks).

Парсер scheme_data → готовый `code.py` для CircuitPlayground / Raspberry Pi Pico /
ESP32-S2 (Adafruit). Поддерживает LED, Button, PWM (analogout), ADC (analogin),
I2C-сенсоры (BME280, DHT22), UART.

Использование (Python):
    from Dolg_APP.services.circuit_python_export import generate_circuit_python
    code = generate_circuit_python(scheme_data, target_board='raspberry_pi_pico')
    # code = "import board, digitalio, time\\n..."

Frontend (Файл-меню в hamburger):
    Меню → Файл → Экспорт → 📦 CircuitPython
    → скачивается code.py готовый к копированию на CIRCUITPY drive.

Pitch для защиты:
    «Полный цикл: нарисовал схему → симулировал → один клик → готовый код для
     микроконтроллера. Реальный мост между schematic и embedded.»

Поддерживаемые компоненты (Phase 1 MVP):
    - LED + Battery + Resistor → digitalio.DigitalInOut(... OUTPUT)
    - LED + Battery + Resistor + блинк → time.sleep loop
    - Button + Pullup + LED → DigitalInOut INPUT + toggle output
    - Potentiometer (резистор-делитель к analog pin) → analogio.AnalogIn
    - Многоканальный LED → board.LEDx pins

Phase 2 (after MVP):
    - I2C sensors (BME280, BMP280, DHT22)
    - SPI displays (SH1106, ST7735)
    - UART communication
    - PWM-driven servos
    - Stepper motors
"""

from __future__ import annotations

# Map of board → pin assignments. Default = Raspberry Pi Pico.
BOARD_PINS = {
    'raspberry_pi_pico': {
        'digital': [f'GP{i}' for i in range(28)],
        'pwm': [f'GP{i}' for i in range(16, 28)],  # PWM on GP16-GP27
        'adc': ['GP26', 'GP27', 'GP28'],
        'i2c_sda': 'GP4',
        'i2c_scl': 'GP5',
        'spi_mosi': 'GP19',
        'spi_miso': 'GP16',
        'spi_clk': 'GP18',
        'uart_tx': 'GP0',
        'uart_rx': 'GP1',
        'led_builtin': 'LED',  # board.LED
    },
    'circuitplayground': {
        'digital': [f'D{i}' for i in range(12)],
        'pwm': [f'D{i}' for i in (3, 5, 6, 9, 10, 11, 13)],
        'adc': ['A0', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6'],
        'i2c_sda': 'SDA',
        'i2c_scl': 'SCL',
        'spi_mosi': 'MOSI',
        'spi_miso': 'MISO',
        'spi_clk': 'SCK',
        'uart_tx': 'TX',
        'uart_rx': 'RX',
        'led_builtin': 'D13',
    },
    'esp32s2': {
        'digital': [f'IO{i}' for i in range(2, 22)],
        'pwm': [f'IO{i}' for i in range(2, 22)],
        'adc': [f'IO{i}' for i in (4, 5, 6, 7, 8, 9, 10)],
        'i2c_sda': 'IO8',
        'i2c_scl': 'IO9',
        'spi_mosi': 'IO11',
        'spi_miso': 'IO13',
        'spi_clk': 'IO12',
        'uart_tx': 'IO43',
        'uart_rx': 'IO44',
        'led_builtin': 'LED',
    },
}


def generate_circuit_python(scheme_data: dict, target_board: str = 'raspberry_pi_pico') -> str:
    """Главный entry-point: scheme_data → готовый код code.py.

    Стратегия (Phase 1):
        1. Сканируем компоненты, классифицируем по ролям (LED/Button/Sensor/...)
        2. Раскидываем по pin'ам платы (autoassign)
        3. Генерируем header (imports) + setup + main loop
        4. Возвращаем готовый текст code.py
    """
    pin_layout = BOARD_PINS.get(target_board, BOARD_PINS['raspberry_pi_pico'])
    board_label = {
        'raspberry_pi_pico': 'Raspberry Pi Pico (RP2040)',
        'circuitplayground': 'Adafruit CircuitPlayground Express',
        'esp32s2': 'ESP32-S2 (Adafruit Feather)',
    }.get(target_board, target_board)

    components = scheme_data.get('components') or []
    classified = _classify_components(components)
    pin_assignments = _assign_pins(classified, pin_layout)

    parts = []
    parts.append(_render_header(board_label, classified))
    parts.append(_render_imports(classified))
    parts.append(_render_setup(classified, pin_assignments, pin_layout))
    parts.append(_render_main_loop(classified, pin_assignments))

    return '\n\n'.join(parts) + '\n'


def _classify_components(components: list[dict]) -> dict[str, list[dict]]:
    """Раскидывает компоненты по ролям."""
    result = {
        'leds': [],
        'buttons': [],
        'analog_inputs': [],
        'pwm_outputs': [],
        'i2c_sensors': [],
        'unknown': [],
    }
    for c in components:
        ctype = (c.get('type') or '').lower()
        label = (c.get('label') or '').lower()
        model = (c.get('model') or '').lower()
        if ctype == 'led':
            result['leds'].append(c)
        elif ctype == 'switch' or ctype == 'button' or 'button' in label:
            result['buttons'].append(c)
        elif ctype == 'potentiometer' or 'pot' in label:
            result['analog_inputs'].append(c)
        elif ctype in ('bme280', 'dht22', 'bmp280'):
            result['i2c_sensors'].append({**c, 'driver': ctype})
        elif ctype == 'sensor' and model in ('bme280', 'bmp280', 'dht22'):
            result['i2c_sensors'].append({**c, 'driver': model})
        elif ctype == 'pwm' or 'servo' in label:
            result['pwm_outputs'].append(c)
        else:
            result['unknown'].append(c)
    return result


def _var_for(component: dict, fallback: str) -> str:
    """Единая стратегия имени переменной (label → id → fallback)."""
    return _safe_var(
        component.get('label') or component.get('id') or fallback,
        fallback,
    )


def _assign_pins(classified: dict, pin_layout: dict) -> dict:
    """Назначает уникальные pin'ы каждому компоненту по их ролям."""
    assignments = {}
    digital_pool = list(pin_layout['digital'])
    adc_pool = list(pin_layout['adc'])
    pwm_pool = list(pin_layout['pwm'])

    for led in classified['leds']:
        if not digital_pool:
            break
        assignments[led.get('id')] = digital_pool.pop(0)
    for btn in classified['buttons']:
        if not digital_pool:
            break
        assignments[btn.get('id')] = digital_pool.pop(0)
    for ai in classified['analog_inputs']:
        if not adc_pool:
            break
        assignments[ai.get('id')] = adc_pool.pop(0)
    for pwm in classified['pwm_outputs']:
        if not pwm_pool:
            break
        assignments[pwm.get('id')] = pwm_pool.pop(0)

    return assignments


def _render_header(board_label: str, classified: dict) -> str:
    counts = {k: len(v) for k, v in classified.items() if v}
    summary = ', '.join(f'{n} {role}' for role, n in counts.items())
    return f'''\
"""CircuitPython code generated by DOLG from schematic.

Target board: {board_label}
Components: {summary or 'none'}

Скопируй этот файл как code.py на CIRCUITPY-drive твоей платы.
Подробности: https://learn.adafruit.com/welcome-to-circuitpython
"""'''


def _render_imports(classified: dict) -> str:
    lines = ['import board', 'import time']
    if classified['leds'] or classified['buttons']:
        lines.append('import digitalio')
    if classified['analog_inputs']:
        lines.append('import analogio')
    if classified['pwm_outputs']:
        lines.append('import pwmio')
    if classified['i2c_sensors']:
        lines.append('import busio')
        for s in classified['i2c_sensors']:
            driver = s.get('driver')
            if driver == 'bme280':
                lines.append('import adafruit_bme280.basic as adafruit_bme280')
            elif driver == 'bmp280':
                lines.append('import adafruit_bmp280')
            elif driver == 'dht22':
                lines.append('import adafruit_dht')
    return '\n'.join(lines)


def _render_setup(classified: dict, assignments: dict, pin_layout: dict) -> str:
    lines = ['# ── Setup ───────────────────────────────────────────────']

    for led in classified['leds']:
        pin = assignments.get(led.get('id'), pin_layout['led_builtin'])
        var = _var_for(led, 'led')
        lines.append(f'{var} = digitalio.DigitalInOut(board.{pin})')
        lines.append(f'{var}.direction = digitalio.Direction.OUTPUT')
    for btn in classified['buttons']:
        pin = assignments.get(btn.get('id'), pin_layout['digital'][0])
        var = _var_for(btn, 'button')
        lines.append(f'{var} = digitalio.DigitalInOut(board.{pin})')
        lines.append(f'{var}.direction = digitalio.Direction.INPUT')
        lines.append(f'{var}.pull = digitalio.Pull.UP')  # активный low — стандарт для button
    for ai in classified['analog_inputs']:
        pin = assignments.get(ai.get('id'), pin_layout['adc'][0])
        var = _var_for(ai, 'pot')
        lines.append(f'{var} = analogio.AnalogIn(board.{pin})')
    for pwm in classified['pwm_outputs']:
        pin = assignments.get(pwm.get('id'), pin_layout['pwm'][0])
        var = _var_for(pwm, 'pwm')
        lines.append(f'{var} = pwmio.PWMOut(board.{pin}, frequency=1000, duty_cycle=0)')
    if classified['i2c_sensors']:
        lines.append(f'i2c = busio.I2C(board.{pin_layout["i2c_scl"]}, board.{pin_layout["i2c_sda"]})')
        for s in classified['i2c_sensors']:
            var = _var_for(s, 'sensor')
            driver = s.get('driver')
            if driver == 'bme280':
                lines.append(f'{var} = adafruit_bme280.Adafruit_BME280_I2C(i2c)')
            elif driver == 'bmp280':
                lines.append(f'{var} = adafruit_bmp280.Adafruit_BMP280_I2C(i2c)')

    return '\n'.join(lines)


def _render_main_loop(classified: dict, assignments: dict) -> str:
    lines = [
        '# ── Main loop ──────────────────────────────────────────',
        'while True:',
    ]

    # LED blink (если только LED'ы без кнопок) — простой пример
    if classified['leds'] and not classified['buttons'] and not classified['analog_inputs']:
        for led in classified['leds']:
            var = _var_for(led, 'led')
            lines.append(f'    {var}.value = True')
        lines.append('    time.sleep(0.5)')
        for led in classified['leds']:
            var = _var_for(led, 'led')
            lines.append(f'    {var}.value = False')
        lines.append('    time.sleep(0.5)')
        return '\n'.join(lines)

    # Button-controlled LED toggle (если есть и LED, и Button)
    if classified['leds'] and classified['buttons']:
        btn_var = _var_for(classified['buttons'][0], 'button')
        led_var = _var_for(classified['leds'][0], 'led')
        lines.append(f'    if not {btn_var}.value:  # button pressed (active low с pull-up)')
        lines.append(f'        {led_var}.value = not {led_var}.value')
        lines.append('        time.sleep(0.3)  # дебаунс')
        lines.append('    else:')
        lines.append('        time.sleep(0.05)')
        return '\n'.join(lines)

    # ADC reading (если есть аналоговые входы)
    if classified['analog_inputs']:
        ai_var = _var_for(classified['analog_inputs'][0], 'pot')
        lines.append(f'    value = {ai_var}.value')
        lines.append('    pct = value * 100 / 65535')
        lines.append('    print(f"ADC: {value} ({pct:.1f}%)")')
        if classified['pwm_outputs']:
            pwm_var = _var_for(classified['pwm_outputs'][0], 'pwm')
            lines.append(f'    {pwm_var}.duty_cycle = value  # 16-bit value passes through')
        lines.append('    time.sleep(0.05)')
        return '\n'.join(lines)

    # I2C sensor read
    if classified['i2c_sensors']:
        for s in classified['i2c_sensors']:
            var = _var_for(s, 'sensor')
            driver = s.get('driver')
            if driver == 'bme280':
                lines.append(
                    f'    print(f"Temp: {{{var}.temperature:.1f}}°C, Hum: {{{var}.relative_humidity:.0f}}%, Pres: {{{var}.pressure:.0f}}hPa")'
                )
            elif driver == 'bmp280':
                lines.append(
                    f'    print(f"Temp: {{{var}.temperature:.1f}}°C, Pres: {{{var}.pressure:.0f}}hPa")'
                )
        lines.append('    time.sleep(2)')
        return '\n'.join(lines)

    # Fallback — пустой loop
    lines.append('    pass  # TODO: add your logic')
    lines.append('    time.sleep(0.1)')
    return '\n'.join(lines)


def _safe_var(name: str, fallback: str) -> str:
    """Python-safe variable name."""
    import re

    s = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    if not s or not s[0].isalpha():
        s = fallback + '_' + s
    return s.lower()
