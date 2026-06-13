"""Браузер-смоук RF-анализа: prefill → payload → fetch (реальный endpoint) → canvas.

Загружает /simulation/, вызывает runRfAnalysis()+runRfCompute() и снимает график
#rf-graph. Проверяет весь фронт-путь на живом api_rf_analysis (CSRF, pro-gate staff,
парсинг ответа, drawRfGraph).
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
HOST, PORT = '127.0.0.1', 8033
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


SCHEME_JS = """
() => {
    applySchemeData({ version: 2, components: [
        { id: 0, type: 'battery', x: 160, y: 320, rotation: 90, voltage: 9, ac: 1, label: 'V1' },
        { id: 1, type: 'resistor', x: 360, y: 220, resistance: 1000, label: 'R1 1k' },
        { id: 2, type: 'capacitor', x: 560, y: 220, capacitance: 0.1, label: 'C1 0.1u' },
        { id: 3, type: 'ground', x: 160, y: 520, label: 'GND' },
    ], connections: [] });
    drawCanvas();
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
            ctx = browser.new_context(viewport={'width': 900, 'height': 600})
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
            page.evaluate(SCHEME_JS)
            # Гарантируем контейнер pro-output, затем гоняем мои функции напрямую.
            page.evaluate("""() => {
                if (!document.getElementById('pro-analysis-output')) {
                    const d = document.createElement('div'); d.id = 'pro-analysis-output';
                    document.body.appendChild(d);
                }
                runRfAnalysis();
            }""")
            page.wait_for_selector('#rf-graph')
            page.evaluate('() => runRfCompute()')
            # Ждём, пока в rf-result появится результат расчёта (не «Считаю...»).
            page.wait_for_function(
                "() => { const e = document.getElementById('rf-result'); return e && /срез|дБ|ошиб|failed|не выполн/i.test(e.textContent) && !/Считаю/.test(e.textContent); }",
                timeout=30_000,
            )
            page.wait_for_timeout(400)
            OUT.mkdir(parents=True, exist_ok=True)
            shot = OUT / 'smoke_rf.png'
            page.locator('#pro-analysis-output').screenshot(path=str(shot))
            result_text = page.eval_on_selector('#rf-result', 'e => e.textContent')
            print('RESULT:', result_text)
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
