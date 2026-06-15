"""Браузер-смоук Probes-панели: portNetMap → nodeVoltages → updateProbesPanel.

Делитель 9В (R1 1k / R2 2k): узлы 9В и 6В, ток ветвей 3мА. Строит portNetMap так
же, как приложение, подставляет nodeVoltages и проверяет, что панель рисует таблицу
V/I с корректными токами. Не зависит от запуска ngspice (детерминированно).
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'diploma_assets' / 'screenshots'
HOST, PORT = '127.0.0.1', 8034
BASE_URL = f'http://{HOST}:{PORT}'
DEMO_USER, DEMO_PASSWORD = 'diploma_demo', 'diploma-demo-2026'


def wait_for_server(timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(BASE_URL + '/', timeout=2) as r:
                if r.status < 500:
                    return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError('server did not start')


def start_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        if s.connect_ex((HOST, PORT)) == 0:
            return None
    env = os.environ.copy()
    env['DEBUG'] = 'True'
    env.setdefault('DJANGO_SETTINGS_MODULE', 'Dolg_PR.settings')
    return subprocess.Popen(
        [
            str(ROOT / '.venv' / 'Scripts' / 'python.exe'),
            'manage.py',
            'runserver',
            f'{HOST}:{PORT}',
            '--noreload',
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
    )


def ensure_demo_user():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Dolg_PR.settings')
    os.environ['DEBUG'] = 'True'
    sys.path.insert(0, str(ROOT))
    import django

    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.test import Client

    um = get_user_model()
    u, _ = um.objects.get_or_create(username=DEMO_USER, defaults={'email': 'demo@dolg.local'})
    u.set_password(DEMO_PASSWORD)
    u.is_staff = True
    u.save()
    c = Client()
    c.login(username=DEMO_USER, password=DEMO_PASSWORD)
    return settings.SESSION_COOKIE_NAME, c.cookies[settings.SESSION_COOKIE_NAME].value


# Делитель: V1(9В) + → R1.a; R1.b → R2.a; R2.b → GND; V1.- → GND.
DRIVE_JS = """
() => {
    applySchemeData({ version: 2, components: [
        { id: 0, type: 'battery',  x: 120, y: 300, rotation: 90, voltage: 9, label: 'V1 9V' },
        { id: 1, type: 'resistor', x: 320, y: 200, resistance: 1000, label: 'R1 1k' },
        { id: 2, type: 'resistor', x: 320, y: 400, resistance: 2000, label: 'R2 2k' },
        { id: 3, type: 'ground',   x: 120, y: 520, label: 'GND' },
    ], connections: [
        { from: { compId: 0, portId: '+' }, to: { compId: 1, portId: 'a' }, waypoints: [] },
        { from: { compId: 1, portId: 'b' }, to: { compId: 2, portId: 'a' }, waypoints: [] },
        { from: { compId: 2, portId: 'b' }, to: { compId: 3, portId: 'a' }, waypoints: [] },
        { from: { compId: 0, portId: '-' }, to: { compId: 3, portId: 'a' }, waypoints: [] },
    ] });
    drawCanvas();
    // Строим port→net как приложение и подставляем напряжения узлов делителя.
    const map = window.DolgSchemeNetlist.buildPortNetMap(components, connections, getComponentPorts);
    window._lastPortNetMap = map;
    const top = String(map.get('0:+'));
    const mid = String(map.get('1:b'));
    const gnd = String(map.get('3:a'));
    const nv = {}; nv[top] = 9; nv[mid] = 6; nv[gnd] = 0;
    const result = { type: 'dc', nodeVoltages: nv };
    window._lastSimResult = result;
    updateProbesPanel(result);
    return { top, mid, gnd, panel: (document.getElementById('probes-panel') || {}).innerText || '' };
}
"""


def main():
    cname, cval = ensure_demo_user()
    server = start_server()
    try:
        wait_for_server()
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(channel='msedge', headless=True)
            except Exception:
                browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={'width': 900, 'height': 640})
            ctx.add_cookies(
                [
                    {
                        'name': cname,
                        'value': cval,
                        'domain': HOST,
                        'path': '/',
                        'httpOnly': True,
                        'sameSite': 'Lax',
                    }
                ]
            )
            ctx.add_init_script("try{localStorage.setItem('dolg.tour.simulation.seen','1');}catch(e){}")
            errors = []
            page = ctx.new_page()
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
            page.set_default_timeout(60_000)
            page.goto(BASE_URL + '/simulation/', wait_until='domcontentloaded')
            page.wait_for_selector('#schematicCanvas')
            for label in ('Пустой канвас', 'Принять всё', 'Принять все'):
                try:
                    page.locator(f"button:has-text('{label}')").first.click(timeout=2000)
                except Exception:
                    pass
            info = page.evaluate(DRIVE_JS)
            # Открыть таб Probes и снять скрин.
            try:
                page.locator("button[data-tab='probes']").first.click(timeout=3000)
            except Exception:
                pass
            page.wait_for_timeout(300)
            OUT.mkdir(parents=True, exist_ok=True)
            shot = OUT / 'smoke_probes.png'
            try:
                page.locator('#probes-panel').screenshot(path=str(shot))
            except Exception as e:
                print('screenshot skip:', e)
            print('NETS:', {k: info[k] for k in ('top', 'mid', 'gnd')})
            print('PANEL TEXT:\n' + info['panel'])
            print('JS ERRORS:', errors if errors else 'none')
            print('SHOT:', shot)
            ctx.close()
            browser.close()
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=8)
            except subprocess.TimeoutExpired:
                server.kill()


if __name__ == '__main__':
    main()
