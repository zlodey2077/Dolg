"""DOLG tray launcher — управление dev-сервером из системного трея, без консоли.

Двойной клик по DOLG.vbs (или pythonw dolg_tray.py) поднимает иконку в трее:
старт/стоп/рестарт сервера, открыть вкладку, открыть админку/симулятор, показать лог.
Сервер стартует автоматически и сразу открывает браузер.

Расширяемость (по просьбе: «с возможностью будущей кастомизации под будущие задачи»):
меню строится из реестра TRAY_ACTIONS — список деклараций. Новая фича проекта =
одна запись (label/handler/visible/enabled), каркас трогать не нужно. Это тот же
приём, что и реестр ai_algorithms у локального AI.

Зависимости: pystray + Pillow (обе в .venv). Если pystray нет — печатает подсказку
и предлагает обычный консольный start_local.bat.
"""

from __future__ import annotations

import os
import socket
import subprocess
import threading
import time
import webbrowser
from pathlib import Path
from typing import Callable, NamedTuple

import start_server as srv  # переиспользуем helpers (find_python/free_port/wait_tcp/build_django_cmd)

ROOT = Path(__file__).resolve().parent
PORT = srv.DJANGO_PORT
LOCAL_URL = f'http://127.0.0.1:{PORT}/'
LOG_PATH = ROOT / '.tmp_django.log'
SINGLE_INSTANCE_PORT = 8765  # bind-lock: второй запуск не поднимет вторую иконку


# ---------------------------------------------------------------------------
# Контроллер сервера: владеет процессом Django, умеет старт/стоп/статус.
# ---------------------------------------------------------------------------
class ServerController:
    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._on_change: Callable[[], None] = lambda: None

    def bind_change(self, callback: Callable[[], None]) -> None:
        """Колбэк для обновления меню трея при смене состояния."""
        self._on_change = callback

    def is_running(self) -> bool:
        if self.proc is not None and self.proc.poll() is None:
            return True
        # Процесс мог быть запущен прошлой сессией — проверяем порт.
        return srv.port_in_use('127.0.0.1', PORT)

    def status_text(self) -> str:
        return f'● Сервер: работает ({PORT})' if self.is_running() else '○ Сервер: остановлен'

    def _env(self) -> dict:
        env = os.environ.copy()
        env['DEBUG'] = 'True'
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUNBUFFERED'] = '1'
        env['PYTHONUTF8'] = '1'  # см. фикс hot-reload (jurigged + cp1251)
        return env

    def start(self, *, open_browser: bool = True) -> None:
        with self._lock:
            if self.is_running():
                if open_browser:
                    webbrowser.open(LOCAL_URL)
                return
            if srv.port_in_use('127.0.0.1', PORT):
                srv.free_port(PORT)
                time.sleep(0.5)
            py = srv.find_python()
            cmd, _hot = srv.build_django_cmd(py, hot=True)
            log = open(LOG_PATH, 'w', encoding='utf-8', buffering=1)
            self.proc = subprocess.Popen(
                cmd, cwd=str(ROOT), env=self._env(), stdout=log, stderr=subprocess.STDOUT
            )
        threading.Thread(target=self._wait_and_open, args=(open_browser,), daemon=True).start()

    def _wait_and_open(self, open_browser: bool) -> None:
        up = srv.wait_tcp('127.0.0.1', PORT, timeout=120)
        self._on_change()
        if up and open_browser:
            webbrowser.open(LOCAL_URL)

    def stop(self) -> None:
        with self._lock:
            proc = self.proc
            self.proc = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except Exception:
                pass
        # Подчистить залипшие python-серверы на порту (jurigged-родитель/ребёнок).
        if srv.port_in_use('127.0.0.1', PORT):
            srv.free_port(PORT)
        self._on_change()

    def restart(self) -> None:
        self.stop()
        time.sleep(0.6)
        self.start(open_browser=False)


def _open(url_or_path):
    """Открыть URL в браузере или файл/папку через ОС."""

    def handler(icon, item):
        try:
            if str(url_or_path).startswith('http'):
                webbrowser.open(url_or_path)
            else:
                os.startfile(str(url_or_path))
        except Exception:
            pass

    return handler


# ---------------------------------------------------------------------------
# Реестр пунктов меню. ДОБАВИТЬ ФИЧУ = добавить TrayAction сюда.
#   text     — строка ИЛИ callable(controller)->str (динамический заголовок)
#   handler  — callable(controller)->callable(icon,item)  (фабрика обработчика)
#   enabled  — callable(controller)->bool (опц., серый пункт когда False)
#   default  — bool: срабатывает по левому клику на иконке
#   separator_before — bool: горизонтальный разделитель перед пунктом
# ---------------------------------------------------------------------------
class TrayAction(NamedTuple):
    key: str
    text: object  # str | Callable[[ServerController], str]
    handler: Callable[[ServerController], Callable]
    enabled: Callable[[ServerController], bool] | None = None
    default: bool = False
    separator_before: bool = False


def _noop(_ctrl):
    return lambda icon, item: None


TRAY_ACTIONS: list[TrayAction] = [
    TrayAction('status', lambda c: c.status_text(), _noop, enabled=lambda c: False),
    TrayAction(
        'open',
        '▶ Открыть в браузере',
        lambda c: lambda icon, item: webbrowser.open(LOCAL_URL),
        enabled=lambda c: c.is_running(),
        default=True,
        separator_before=True,
    ),
    TrayAction(
        'admin', '⚙ Открыть админку', lambda c: _open(LOCAL_URL + 'admin/'), enabled=lambda c: c.is_running()
    ),
    TrayAction(
        'simulator',
        '🔌 Открыть симулятор',
        lambda c: _open(LOCAL_URL + 'simulation/'),
        enabled=lambda c: c.is_running(),
    ),
    TrayAction(
        'start',
        '⬤ Запустить сервер',
        lambda c: lambda icon, item: c.start(),
        enabled=lambda c: not c.is_running(),
        separator_before=True,
    ),
    TrayAction(
        'restart',
        '⟳ Перезапустить',
        lambda c: lambda icon, item: c.restart(),
        enabled=lambda c: c.is_running(),
    ),
    TrayAction(
        'stop', '■ Остановить', lambda c: lambda icon, item: c.stop(), enabled=lambda c: c.is_running()
    ),
    TrayAction('log', '📄 Показать лог', lambda c: _open(LOG_PATH), separator_before=True),
    # --- БУДУЩИЕ ФИЧИ: раскомментировать/добавить по мере роста проекта ---
    # TrayAction('public', '🌐 Публичный туннель (Cloudflare)', lambda c: (lambda i,m: c.start_public())),
    # TrayAction('tests',  '✓ Прогнать тесты',                  lambda c: (lambda i,m: run_pytest())),
    # TrayAction('gnn',    '🧠 Обучить GNN',                     lambda c: (lambda i,m: train_gnn())),
]


def build_menu(controller: ServerController):
    import pystray

    items = []
    for act in TRAY_ACTIONS:
        if act.separator_before:
            items.append(pystray.Menu.SEPARATOR)
        text = (lambda item, a=act: a.text(controller)) if callable(act.text) else act.text
        enabled = (lambda item, a=act: a.enabled(controller)) if act.enabled else True
        items.append(pystray.MenuItem(text, act.handler(controller), enabled=enabled, default=act.default))
    items.append(pystray.Menu.SEPARATOR)
    items.append(pystray.MenuItem('✖ Выход', lambda icon, item: _exit(icon, controller)))
    return pystray.Menu(*items)


def _exit(icon, controller: ServerController):
    try:
        controller.stop()
    finally:
        icon.stop()


def make_icon_image():
    """Иконка трея: монограмма D на сине-циановом круге (Pillow)."""
    from PIL import Image, ImageDraw

    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    dc = ImageDraw.Draw(img)
    dc.ellipse((2, 2, size - 2, size - 2), fill=(0, 160, 192, 255))
    dc.ellipse((8, 8, size - 8, size - 8), outline=(255, 255, 255, 230), width=3)
    dc.text((size // 2, size // 2 - 2), 'D', fill=(255, 255, 255, 255), anchor='mm')
    return img


def acquire_single_instance() -> socket.socket | None:
    """Bind-lock: если порт занят — уже запущен другой экземпляр трея."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('127.0.0.1', SINGLE_INSTANCE_PORT))
        s.listen(1)
        return s
    except OSError:
        s.close()
        return None


def main() -> int:
    try:
        import pystray
    except Exception:
        print('[DOLG tray] pystray не установлен. Поставь:')
        print('   .venv\\Scripts\\python.exe -m pip install pystray')
        print('   …или запусти обычный консольный start_local.bat')
        return 1

    lock = acquire_single_instance()
    if lock is None:
        # Уже запущено — просто открыть вкладку и выйти.
        webbrowser.open(LOCAL_URL)
        return 0

    import pystray

    controller = ServerController()
    icon = pystray.Icon('DOLG', icon=make_icon_image(), title='DOLG — dev сервер')
    controller.bind_change(lambda: icon.update_menu())
    icon.menu = build_menu(controller)

    # Автозапуск сервера + авто-открытие вкладки.
    controller.start(open_browser=True)
    icon.run()
    try:
        lock.close()
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
