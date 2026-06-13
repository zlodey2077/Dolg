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
HOST = '127.0.0.1'
PORT = 8031
BASE_URL = f'http://{HOST}:{PORT}'
DEMO_USER = 'diploma_demo'
DEMO_PASSWORD = 'diploma-demo-2026'


def is_port_open() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((HOST, PORT)) == 0


def wait_for_server(timeout: int = 120) -> None:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            with urlopen(BASE_URL + '/', timeout=2) as response:
                if response.status < 500:
                    return
        except Exception as exc:
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f'Server did not start: {last_error!r}')


def start_server() -> subprocess.Popen | None:
    if is_port_open():
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


def ensure_demo_user() -> tuple[str, str]:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Dolg_PR.settings')
    os.environ['DEBUG'] = 'True'
    sys.path.insert(0, str(ROOT))
    import django

    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.test import Client

    user_model = get_user_model()
    user, _created = user_model.objects.get_or_create(
        username=DEMO_USER, defaults={'email': 'demo@dolg.local'}
    )
    user.set_password(DEMO_PASSWORD)
    user.is_staff = True
    user.save()
    client = Client()
    if not client.login(username=DEMO_USER, password=DEMO_PASSWORD):
        raise RuntimeError('Could not create authenticated demo session')
    return settings.SESSION_COOKIE_NAME, client.cookies[settings.SESSION_COOKIE_NAME].value


def launch_browser(playwright):
    try:
        return playwright.chromium.launch(channel='msedge', headless=True)
    except Exception:
        return playwright.chromium.launch(headless=True)


# Чистая, читаемая демо-цепь: питание → токоограничивающий резистор → светодиод,
# плюс RC-делитель. Для иллюстрации УГО-режима и smart wiring в главе 2.
DEMO_SCHEME_JS = """
() => {
    localStorage.setItem('dolg.tour.simulation.seen', '1');
    applySchemeData({
        version: 2,
        components: [
            { id: 0, type: 'battery', x: 160, y: 320, rotation: 90, voltage: 9, label: 'V1 9V' },
            { id: 1, type: 'resistor', x: 360, y: 220, rotation: 0, resistance: 1000, label: 'R1 1k', catalog_parameters: { tdp_w: 0.25 } },
            { id: 2, type: 'led', x: 560, y: 220, rotation: 90, label: 'D1' },
            { id: 3, type: 'resistor', x: 360, y: 420, rotation: 0, resistance: 10000, label: 'R2 10k', catalog_parameters: { tdp_w: 0.25 } },
            { id: 4, type: 'capacitor', x: 560, y: 420, rotation: 90, capacitance: 10, label: 'C1 10uF' },
            { id: 5, type: 'ground', x: 160, y: 520, label: 'GND' },
        ],
        connections: [
            { from: { compId: 0, portId: '+' }, to: { compId: 1, portId: 'a' }, waypoints: [{ x: 160, y: 220 }] },
            { from: { compId: 1, portId: 'b' }, to: { compId: 2, portId: 'a' }, waypoints: [] },
            { from: { compId: 0, portId: '+' }, to: { compId: 3, portId: 'a' }, waypoints: [{ x: 160, y: 420 }] },
            { from: { compId: 3, portId: 'b' }, to: { compId: 4, portId: 'a' }, waypoints: [] },
            { from: { compId: 2, portId: 'b' }, to: { compId: 5, portId: 'a' }, waypoints: [{ x: 560, y: 520 }] },
            { from: { compId: 4, portId: 'b' }, to: { compId: 5, portId: 'a' }, waypoints: [{ x: 560, y: 520 }] },
            { from: { compId: 0, portId: '-' }, to: { compId: 5, portId: 'a' }, waypoints: [] },
        ],
    });
    zoom = 1.0;
    panX = 20;
    panY = 10;
    drawCanvas();
}
"""


def capture() -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    session_cookie_name, session_cookie_value = ensure_demo_user()
    server = start_server()
    try:
        wait_for_server()
        # django.setup() (Channels/Daphne) переключает asyncio на SelectorEventLoop,
        # который на Windows не умеет subprocess — Playwright не может поднять драйвер.
        # Возвращаем Proactor-политику перед запуском браузера.
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        with sync_playwright() as playwright:
            browser = launch_browser(playwright)
            context = browser.new_context(viewport={'width': 1680, 'height': 1080}, device_scale_factor=1)
            context.add_cookies(
                [
                    {
                        'name': session_cookie_name,
                        'value': session_cookie_value,
                        'domain': HOST,
                        'path': '/',
                        'httpOnly': True,
                        'sameSite': 'Lax',
                    }
                ]
            )
            context.add_init_script(
                "try { localStorage.setItem('dolg.tour.simulation.seen', '1'); } catch (e) {}"
            )
            page = context.new_page()
            page.set_default_timeout(90_000)
            page.set_default_navigation_timeout(90_000)

            # 1. Schematic editor canvas with demo circuit (УГО, smart wiring).
            page.goto(BASE_URL + '/simulation/', wait_until='domcontentloaded')
            page.wait_for_selector('#schematicCanvas')
            # Закрываем баннер cookie-согласия, чтобы он не лез в кадр (в т.ч. на /cad/).
            for label in ('Принять всё', 'Принять все', 'Принять', 'Сохранить выбор'):
                try:
                    page.locator(f"button:has-text('{label}')").first.click(timeout=2500)
                    break
                except Exception:
                    pass
            # Гасим онбординг-модалку выбора demo-схемы, иначе она перекроет канвас.
            for label in ('Пустой канвас', 'Больше не показывать'):
                try:
                    page.locator(f"button:has-text('{label}')").first.click(timeout=3000)
                except Exception:
                    pass
            page.evaluate(
                "() => { document.querySelectorAll('.modal, .demo-picker, [class*=picker], [class*=onboard]').forEach(e => e.style.display='none'); }"
            )
            page.evaluate(DEMO_SCHEME_JS)
            page.wait_for_timeout(900)
            editor = OUT / 'ch2_editor_canvas.png'
            page.locator('#schematicCanvas').screenshot(path=str(editor))
            created.append(editor)

            # 2. CAD GOST A3 schematic sheet (unique — нет в приложениях).
            page.goto(BASE_URL + '/cad/', wait_until='domcontentloaded', timeout=90_000)
            page.wait_for_selector('#canvas', timeout=30_000)
            page.evaluate(
                """
                () => {
                    const objs = gostFrame(420, 297);
                    const add = (obj) => { objs.push(obj); return obj; };
                    const line = (x1, y1, x2, y2, lw = 2) => add(tplLine(x1, y1, x2, y2, '#0f2942', lw));
                    const rect = (x, y, w, h, lw = 2, fill = 'none') => add(tplRect(x, y, w, h, '#0f2942', lw, fill));
                    const text = (x, y, value, size = 13) => add(tplText(x, y, value, '#0f2942', size));
                    const dim = (x1, y1, x2, y2) => add({
                        id: 0, type: 'dimension', x1, y1, x2, y2,
                        x: Math.min(x1, x2), y: Math.min(y1, y2),
                        width: Math.abs(x2 - x1), height: Math.abs(y2 - y1),
                        color: '#0f2942', lineWidth: 1.4, fill: 'none', fontSize: 11,
                    });
                    const leader = (x1, y1, x2, y2, value) => add({
                        id: 0, type: 'leader', x1, y1, x2, y2,
                        x: Math.min(x1, x2), y: Math.min(y1, y2),
                        width: Math.abs(x2 - x1), height: Math.abs(y2 - y1),
                        color: '#0f2942', lineWidth: 1.4, fill: 'none', text: value, fontSize: 12,
                    });
                    text(195, 82, 'Принципиальная схема испытательного узла DOLG', 18);
                    text(240, 104, 'питание, RLC-фильтр, нагрузка и контрольные точки', 12);
                    line(140, 160, 705, 160, 2.2);
                    line(140, 305, 705, 305, 2.2);
                    line(140, 160, 140, 305, 2.2);
                    line(125, 205, 155, 205, 2.5);
                    line(132, 226, 148, 226, 2.5);
                    text(92, 218, 'V1 12 В', 12);
                    line(140, 305, 140, 330, 1.6);
                    line(125, 330, 155, 330, 1.8);
                    line(130, 338, 150, 338, 1.6);
                    line(135, 346, 145, 346, 1.4);
                    text(116, 365, 'GND', 11);
                    line(255, 160, 255, 210, 1.8);
                    rect(242, 210, 26, 48, 2);
                    line(255, 258, 255, 305, 1.8);
                    text(232, 198, 'R1', 12);
                    text(225, 278, '10 кОм', 11);
                    line(360, 160, 360, 202, 1.8);
                    for (let i = 0; i < 4; i += 1) {
                        add(tplArc(360, 214 + i * 18, 9, '#0f2942', 1.8, -Math.PI / 2, Math.PI / 2));
                    }
                    line(360, 286, 360, 305, 1.8);
                    text(338, 198, 'L1', 12);
                    text(326, 286, '10 мГн', 11);
                    line(475, 160, 475, 217, 1.8);
                    line(455, 217, 495, 217, 2.3);
                    line(455, 238, 495, 238, 2.3);
                    line(475, 238, 475, 305, 1.8);
                    text(452, 204, 'C1', 12);
                    text(442, 262, '47 мкФ', 11);
                    line(585, 160, 585, 210, 1.8);
                    rect(572, 210, 26, 48, 2);
                    line(585, 258, 585, 305, 1.8);
                    text(562, 198, 'R2', 12);
                    text(560, 278, '220 Ом', 11);
                    rect(675, 196, 42, 74, 2);
                    for (let y = 210; y <= 252; y += 14) line(675, y, 717, y, 1);
                    line(705, 160, 705, 196, 1.8);
                    line(705, 270, 705, 305, 1.8);
                    text(650, 187, 'XS1', 12);
                    text(641, 292, 'клеммник', 11);
                    dim(140, 350, 705, 350);
                    leader(255, 234, 185, 250, 'ветвь датчика тока');
                    leader(475, 228, 535, 178, 'фильтр C1');
                    leader(705, 232, 755, 214, 'выход на стенд');
                    text(590, 525, 'DOLG CAD / ГОСТ 2.104', 11);
                    text(720, 565, 'А3', 10);
                    text(777, 565, '1:2', 10);
                    // CAD-канвас теперь светлый (как редактор схем) — оставляем
                    // тёмные линии #0f2942, они хорошо читаются на светлом фоне.
                    objs.forEach((obj, index) => { obj.id = index + 1; });
                    State.layers = [{ id: 1, name: 'Слой 1', visible: true, objs }];
                    State.objects = objs;
                    State.selectedObj = null;
                    State.history = [];
                    State.historyIndex = -1;
                    saveHistory();
                    renderLayers();
                    fitView();
                    document.getElementById('objCountSpan').textContent = `Объектов: ${State.objects.length}`;
                }
                """
            )
            page.wait_for_timeout(700)
            cad = OUT / 'ch2_cad_gost.png'
            page.locator('#canvas').screenshot(path=str(cad))
            created.append(cad)

            context.close()
            browser.close()
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=8)
            except subprocess.TimeoutExpired:
                server.kill()
    return created


def main() -> None:
    for path in capture():
        print(path)


if __name__ == '__main__':
    main()
