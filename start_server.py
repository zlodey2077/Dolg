"""DOLG one-click launcher: Django + Cloudflare Quick Tunnel.

ВАЖНО: код namespace ASCII-only (без emoji) — Python на Windows иногда
падает с UnicodeEncodeError на cp1251-консоли. Эмодзи только в вывод
через print с explicit encoding-fallback.
"""
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

# Принудительно UTF-8 для stdout (Python 3.7+ ReconfigWriter)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


def p(msg):
    """Print с явным flush — иначе Start-Process на Windows буферизует."""
    print(msg, flush=True)


ROOT = Path(__file__).resolve().parent
DJANGO_PORT = 8000
# cloudflared.exe переехал в deploy/ вместе с Docker-инфраструктурой —
# корень проекта стал чище. Для backward-compat пробуем и старый путь.
CLOUDFLARED = ROOT / 'deploy' / 'cloudflared.exe'
if not CLOUDFLARED.exists():
    legacy = ROOT / 'cloudflared.exe'
    if legacy.exists():
        CLOUDFLARED = legacy
URL_PATTERN = re.compile(r'https://[a-z0-9-]+\.trycloudflare\.com')


def find_python():
    venv_py = ROOT / '.venv' / 'Scripts' / 'python.exe'
    if venv_py.exists():
        return str(venv_py)
    return sys.executable


def port_in_use(host, port):
    """True если port уже занят (TCP connect succeeds)."""
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def wait_tcp(host, port, timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.4)
    return False


def probe_url(url, timeout=8):
    """HTTP-проверка с правильной обработкой ошибок Cloudflare.
    Возвращает True если получили любой HTTP-ответ (даже 4xx/5xx) — это
    значит туннель установлен. False — только если HTTPError 530 (туннель
    ещё не пропагирован) или сетевая ошибка (origin/connection)."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'DOLG-launcher/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            _ = resp.status
            return True
    except urllib.error.HTTPError as e:
        # Если HTTP-сервер ответил (даже 4xx/5xx) — туннель работает.
        # Ошибка 530 — туннель ещё не пропагирован.
        return e.code != 530
    except Exception:
        # Timeout/DNS/refused — туннель ещё не готов
        return False


def reader_thread(stream, store):
    for raw in iter(stream.readline, b''):
        try:
            line = raw.decode('utf-8', errors='replace').rstrip()
        except Exception:
            continue
        store['log'].append(line)
        if len(store['log']) > 500:
            store['log'] = store['log'][-500:]
        if not store.get('url'):
            m = URL_PATTERN.search(line)
            if m:
                store['url'] = m.group(0)


def banner(url):
    line = '=' * 60
    p('')
    p(line)
    p('              >>> DOLG GOTOV K TESTU <<<')
    p(line)
    p('')
    p('   URL dlya telefona / lyubogo ustroystva:')
    p('')
    p('       ' + url)
    p('')
    p('   (HTTPS, bez firewall, lyubaya set)')
    p('')
    p('   Lokal\'no: http://127.0.0.1:%d/' % DJANGO_PORT)
    p(line)
    p('')
    p('   Ctrl+C ili zakroyte okno dlya ostanovki.')
    p('')


def main():
    p('[DOLG launcher] starting...')

    if not CLOUDFLARED.exists():
        p('[ERROR] cloudflared.exe ne nayden: %s' % CLOUDFLARED)
        input('\nEnter dlya vyhoda...')
        return 1

    py = find_python()
    p('[1/3] Zapuskayu Django server (python: %s)' % py)
    p('      [INFO] Auto-reload AKTIVEN: Django sledit za *.py i urls.py,')
    p('             rebenok-process perezapustitsya pri kazhdom save.')
    p('             Cloudflared tunnel pereletivayet avtomaticheski (1-2 sek).')

    if port_in_use('127.0.0.1', DJANGO_PORT):
        p('[ERROR] Port %d is already in use by another process.' % DJANGO_PORT)
        p('        Close the other Django/server first, or use start_local.bat')
        p('        to attach to the running instance.')
        input('\nEnter dlya vyhoda...')
        return 1

    env = os.environ.copy()
    env['DEBUG'] = 'True'
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUNBUFFERED'] = '1'

    django_log_path = ROOT / '.tmp_django.log'
    django_log = open(django_log_path, 'w', encoding='utf-8', buffering=1)
    # ВАЖНО: Django запускаем БЕЗ CREATE_NEW_PROCESS_GROUP — иначе на Windows
    # subprocess висит на «Performing system checks...» из-за конфликта с
    # stdout PIPE-buffer. cloudflared отдельным группой — там нужен
    # CTRL_BREAK_EVENT для чистой остановки.
    creation_flags_cf = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0

    # БЕЗ --noreload: Django сам отслеживает .py/.urls.py и перезапускает
    # дочерний процесс при сохранении. Наш subprocess.Popen ловит PARENT-watcher,
    # который остаётся живым между ребёнок-restart'ами — django.poll() == None,
    # нам ничего делать не надо. Cloudflared tunnel при кратковременной потере
    # порта 8000 авто-переподключается. Раньше стоял --noreload из-за мнимого
    # «conflict с управлением subprocess» — на практике работает чисто.
    django = subprocess.Popen(
        # --skip-checks: пропускаем системные проверки (-2..-5 сек на старте).
        [py, 'manage.py', 'runserver', '127.0.0.1:%d' % DJANGO_PORT, '--skip-checks'],
        cwd=str(ROOT), env=env,
        stdout=django_log, stderr=subprocess.STDOUT,
    )

    if not wait_tcp('127.0.0.1', DJANGO_PORT, timeout=90):
        p('[ERROR] Django ne podnyalsya za 90 sek. Log:')
        try:
            with open(django_log_path, encoding='utf-8') as f:
                p(f.read()[-1500:])
        except Exception:
            pass
        django.terminate()
        input('\nEnter dlya vyhoda...')
        return 1

    p('      OK')

    p('')
    p('[2/3] Zapuskayu Cloudflare Quick Tunnel...')

    cf = subprocess.Popen(
        [str(CLOUDFLARED), 'tunnel', '--no-autoupdate', '--url', 'http://127.0.0.1:%d' % DJANGO_PORT],
        cwd=str(ROOT),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0,
        creationflags=creation_flags_cf,
    )

    store = {'url': None, 'log': []}
    t = threading.Thread(target=reader_thread, args=(cf.stdout, store), daemon=True)
    t.start()

    p('      Zhdu publichnyy URL...')
    deadline = time.time() + 40
    while time.time() < deadline and not store['url']:
        if cf.poll() is not None:
            p('[ERROR] cloudflared upal. Log:')
            for ln in store['log'][-25:]:
                p('  ' + ln)
            django.terminate()
            input('\nEnter dlya vyhoda...')
            return 1
        time.sleep(0.3)

    if not store['url']:
        p('[ERROR] Cloudflare ne dal URL za 40 sek. Log:')
        for ln in store['log'][-30:]:
            p('  ' + ln)
        cf.terminate()
        django.terminate()
        input('\nEnter dlya vyhoda...')
        return 1

    public_url = store['url']
    p('      URL: %s' % public_url)
    p('')
    p('[3/3] Tunnel ustanovlen, propagiruyu (10-30 sek)...')

    # Цикл prefetch до 60 сек. Probe возвращает True при ЛЮБОМ HTTP-ответе
    # (не только 200) — это значит туннель работает. 530 = «ещё не готов».
    propag_deadline = time.time() + 60
    propagated = False
    while time.time() < propag_deadline:
        if probe_url(public_url, timeout=6):
            propagated = True
            break
        time.sleep(3)

    if propagated:
        p('      OK, tunnel otvetil.')
    else:
        p('[WARN] Tunnel ne otvetil za 60 sek. URL VSE RAVNO mozhet rabotat -')
        p('       inogda Cloudflare propagiruet do 2 minut.')

    banner(public_url)

    # Открываем в браузере только если propagated — иначе юзер сразу
    # увидит ошибку 1033 и расстроится.
    if propagated:
        try:
            webbrowser.open(public_url)
        except Exception:
            pass
    else:
        p('   Brauzer NE otkryl avtomaticheski (tunnel eshe greetsya).')
        p('   Skoporiy URL vyshe i otkroy vruchnuyu cherez 30-60 sek.')
        p('')

    try:
        while True:
            time.sleep(2)
            if django.poll() is not None:
                p('\n[!] Django process died.')
                break
            if cf.poll() is not None:
                p('\n[!] Cloudflared process died.')
                break
    except KeyboardInterrupt:
        p('\n[*] Stopping...')
    finally:
        # CTRL_BREAK_EVENT работает только на процессах, запущенных с
        # CREATE_NEW_PROCESS_GROUP (т.е. cloudflared). Django был запущен
        # без флага — посылка CTRL_BREAK туда упадёт с ValueError, поэтому
        # для него сразу .terminate().
        graceful = [(cf, 'cloudflared', True), (django, 'django', False)]
        for proc, name, can_ctrl_break in graceful:
            try:
                if proc.poll() is None:
                    if os.name == 'nt' and can_ctrl_break:
                        try:
                            proc.send_signal(signal.CTRL_BREAK_EVENT)
                            time.sleep(0.5)
                        except Exception:
                            pass
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
            except Exception:
                pass
        try:
            django_log.close()
        except Exception:
            pass
        p('[*] Stopped.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
