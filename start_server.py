"""DOLG one-click launcher: Django + ngrok tunnel.

ВАЖНО: код namespace ASCII-only (без emoji) — Python на Windows иногда
падает с UnicodeEncodeError на cp1251-консоли. Эмодзи только в вывод
через print с explicit encoding-fallback.
"""

import os
import re
import shutil
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
# ngrok.exe в deploy/. Cloudflare Quick Tunnel периодически отдаёт error 1033,
# поэтому публичный режим по умолчанию снова использует ngrok.
# Токен — в %LOCALAPPDATA%\ngrok\ngrok.yml
# (один раз: ngrok config add-authtoken ...).
def find_ngrok():
    candidates = [
        os.getenv('NGROK_BIN', ''),
        str(ROOT / 'deploy' / 'ngrok.exe'),
        str(ROOT / 'ngrok.exe'),
        shutil.which('ngrok') or '',
        str(Path(os.getenv('LOCALAPPDATA', '')) / 'Microsoft' / 'WinGet' / 'Packages' / 'Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe' / 'ngrok.exe'),
    ]
    for item in candidates:
        if item and Path(item).exists():
            return Path(item)
    return None


NGROK = find_ngrok()
# ngrok --log=stdout пишет logfmt; URL приходит как url=https://xxx.ngrok-free.dev
URL_PATTERN = re.compile(r'https://[a-z0-9-]+\.ngrok(?:-free)?\.(?:dev|app|io)')
FAST_MIGRATION_PROBE = r"""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Dolg_PR.settings')
os.environ.setdefault('DOLG_SKIP_ASGI', '1')
import django
django.setup()
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor
executor = MigrationExecutor(connections[DEFAULT_DB_ALIAS])
targets = executor.loader.graph.leaf_nodes()
plan = executor.migration_plan(targets)
if plan:
    print('pending migrations: %d' % len(plan))
    raise SystemExit(1)
raise SystemExit(0)
"""


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


def free_port(port):
    """Снять залипший python-сервер, слушающий port (zombie со старым кодом).

    Бьём ТОЛЬКО процессы с именем python* — чтобы не задеть посторонние
    приложения, которые могли занять этот порт. Возвращает список убитых PID.
    Без psutil тихо ничего не делает (порт-проверка обработает ошибку выше).
    """
    killed = []
    try:
        import psutil
    except Exception:
        return killed
    targets = {}
    for conn in psutil.net_connections(kind='inet'):
        try:
            if not conn.laddr or conn.laddr.port != port:
                continue
            if conn.status != psutil.CONN_LISTEN or not conn.pid:
                continue
            proc = psutil.Process(conn.pid)
            if 'python' not in proc.name().lower():
                continue
            # runserver с auto-reload = reloader-родитель + слушающий ребёнок.
            # Убиваем оба, иначе родитель респавнит ребёнка и порт не освободится.
            targets[proc.pid] = proc
            try:
                parent = proc.parent()
                if parent and 'python' in parent.name().lower():
                    targets[parent.pid] = parent
                    for child in parent.children(recursive=True):
                        targets[child.pid] = child
            except Exception:
                pass
        except Exception:
            continue
    for pid, proc in targets.items():
        try:
            proc.terminate()
            killed.append(pid)
        except Exception:
            continue
    if killed:
        gone, alive = [], []
        try:
            gone, alive = psutil.wait_procs([psutil.Process(pid) for pid in killed], timeout=3)
        except Exception:
            time.sleep(1.0)
        for proc in alive:
            try:
                proc.kill()
            except Exception:
                pass
    return killed


def wait_tcp(host, port, timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.4)
    return False


def wait_django_ready(proc, host, port, timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False, 'process exited with code %s' % proc.returncode
        try:
            with socket.create_connection((host, port), timeout=1):
                return True, ''
        except OSError:
            time.sleep(0.4)
    if proc.poll() is not None:
        return False, 'process exited with code %s' % proc.returncode
    return False, 'timeout after %ss' % timeout


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
    p("   Lokal'no: http://127.0.0.1:%d/" % DJANGO_PORT)
    p(line)
    p('')
    p('   Ctrl+C ili zakroyte okno dlya ostanovki.')
    p('')


def jurigged_available():
    try:
        import jurigged  # noqa: F401

        return True
    except Exception:
        return False


def build_django_cmd(py, hot):
    """Komanda zapuska Django. hot=True -> cherez jurigged (zhivoy hot-reload
    bez restarta: pravki tel funktsiy primenyayutsya za <1 sek). Strukturnye
    pravki (URL/model/settings) vse ravno trebuyut restarta."""
    base = ['manage.py', 'runserver', '127.0.0.1:%d' % DJANGO_PORT, '--skip-checks', '--noreload']
    if hot and jurigged_available():
        watch = []
        for app in ('Dolg_APP', 'shop', 'accounts', 'orders', 'knowledge', 'Dolg_PR'):
            d = ROOT / app
            if d.exists():
                watch += ['--watch', str(d)]
        # Django reloader is disabled here: jurigged owns hot patching.
        return [py, '-m', 'jurigged'] + watch + base, True
    return [py] + base, False


# Эти процессы НЕ трогаем при чистке: MCP-серверы Claude и т.п. инфраструктура,
# которая запускается из .venv этого же проекта, но к dev-серверу не относится.
_KILL_EXCLUDE = (
    'mcp_server',
    'fastmcp',
    'headroom',
    'context7',
    'sequential-thinking',
    'modelcontextprotocol',
)


def kill_orphans():
    """Убийца зомби-процессов: полный чистый рестарт dev-окружения.

    Снимает ВСЕ процессы прошлых сессий, относящиеся к dev-серверу: любые
    `manage.py …` (runserver, а также зависшие management-команды вроде обучения
    GNN), jurigged, daphne и leftover cloudflared. Частая причина «ни один вход
    не работает» — именно такие зомби, держащие ресурсы/порт.

    НЕ трогает: текущий launcher и его родителя, а также MCP-серверы Claude
    (_KILL_EXCLUDE). Без psutil — no-op."""
    killed = []
    try:
        import psutil
    except Exception:
        return killed
    me = os.getpid()
    try:
        parent = psutil.Process(me).ppid()
    except Exception:
        parent = None
    for pr in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            pid = pr.info['pid']
            if pid in (me, parent):
                continue
            name = (pr.info['name'] or '').lower()
            cl = ' '.join(pr.info['cmdline'] or [])
            cl_low = cl.lower()
            # leftover ngrok-туннель (не python) — тоже снимаем.
            is_cloudflared = 'ngrok' in name or 'cloudflared' in name
            is_devproc = 'python' in name and ('manage.py' in cl or 'jurigged' in cl or 'daphne' in cl_low)
            if not (is_cloudflared or is_devproc):
                continue
            if any(tok in cl_low for tok in _KILL_EXCLUDE):
                continue  # не убиваем MCP-инфраструктуру
            pr.kill()
            killed.append(pid)
        except Exception:
            continue
    return killed


def port_holder(port):
    """Имя+PID процесса, занявшего порт (для отчёта)."""
    try:
        import psutil

        for c in psutil.net_connections(kind='inet'):
            if c.laddr and c.laddr.port == port and c.pid:
                try:
                    return '%s (PID %d)' % (psutil.Process(c.pid).name(), c.pid)
                except Exception:
                    return 'PID %d' % c.pid
    except Exception:
        pass
    return 'unknown'


def migration_state(py, env):
    """Return ('ok'|'pending'|'timeout'|'error', detail) for migration preflight."""
    try:
        timeout = int(env.get('DOLG_MIGRATION_CHECK_TIMEOUT', '10'))
    except ValueError:
        timeout = 10
    try:
        r = subprocess.run(
            [py, '-c', FAST_MIGRATION_PROBE],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if r.returncode == 0:
            return 'ok', ''
        return 'pending', (r.stderr or r.stdout or '').strip()
    except subprocess.TimeoutExpired:
        return 'timeout', 'fast migration probe timed out after %ss' % timeout
    except Exception as exc:
        return 'error', 'fast migration probe failed: %s' % exc


def _start_django(py, env, hot, log_path):
    """Запустить Django; вернуть (proc, 'hot'|'plain')."""
    django_cmd, hot_active = build_django_cmd(py, hot)
    mode = 'hot' if hot_active else 'plain'
    with open(log_path, 'a', encoding='utf-8', buffering=1) as log:
        log.write('\n--- %s Django start (%s) ---\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), mode))
        log.write('cmd: %s\n' % subprocess.list2cmdline(django_cmd))
    proc = subprocess.Popen(
        django_cmd,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
    )
    echo = env.get('DOLG_SHOW_DJANGO_LOG', '1').lower() not in {'0', 'false', 'no'}
    threading.Thread(
        target=_forward_django_output,
        args=(proc.stdout, log_path, echo),
        daemon=True,
    ).start()
    return proc, mode


def _forward_django_output(stream, log_path, echo):
    if stream is None:
        return
    with open(log_path, 'a', encoding='utf-8', buffering=1) as log:
        for raw in iter(stream.readline, b''):
            line = raw.decode('utf-8', errors='replace').rstrip()
            log.write(line + '\n')
            if echo and line:
                p('[django] ' + line)


def _kill_proc(proc):
    try:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                proc.kill()
    except Exception:
        pass


def _write_report(report):
    try:
        (ROOT / '.tmp_launch_report.txt').write_text('\n'.join(report), encoding='utf-8')
    except Exception:
        pass


def _msgbox(text):
    """MessageBox для тихого режима (pythonw из .vbs/трея), чтобы сбой не был молчаливым."""
    if os.name != 'nt':
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, text[:1800], 'DOLG launcher', 0x10)
    except Exception:
        pass


def _abort(report):
    """Фатальный выход: сохранить отчёт, показать его (MessageBox + консоль)."""
    _write_report(report)
    _msgbox('DOLG не запустился:\n\n' + '\n'.join(report[-12:]) + '\n\nПодробнее: .tmp_launch_report.txt')
    try:
        input('\nEnter dlya vyhoda...')
    except Exception:
        pass
    return 1


def main():
    local_only = ('--local' in sys.argv) or ('--no-tunnel' in sys.argv)
    hot = ('--hot' in sys.argv) and ('--no-hot' not in sys.argv)
    no_browser = '--no-browser' in sys.argv
    exit_after_ready = '--exit-after-ready' in sys.argv

    report = []

    def rep(level, msg):
        line = '[%s] %s' % (level, msg)
        report.append(line)
        p(line)

    rep('INFO', 'DOLG launcher: preflight (самопроверка и автолечение)...')

    # --- Проверки окружения ---
    py = find_python()
    rep('OK' if os.path.exists(py) else 'WARN', 'Python: %s' % py)
    try:
        import django as _dj

        rep('OK', 'Django %s' % _dj.get_version())
    except Exception as exc:
        rep(
            'ERR',
            'Django не импортируется (%s). Установи зависимости: '
            '.venv\\Scripts\\python.exe -m pip install -r requirements.txt' % exc,
        )
        return _abort(report)
    if not (ROOT / 'manage.py').exists():
        rep('ERR', 'manage.py не найден — это не папка проекта DOLG?')
        return _abort(report)
    if not local_only and not NGROK:
        rep('ERR', 'ngrok.exe не найден: поставьте Ngrok.Ngrok через winget или задайте NGROK_BIN')
        return _abort(report)

    env = os.environ.copy()
    env['DEBUG'] = 'True'
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUNBUFFERED'] = '1'
    env['PYTHONUTF8'] = '1'  # UTF-8 mode: чинит hot-reload (jurigged + cp1251 на рус. Windows)
    env['TERM'] = 'dumb'
    env['NO_COLOR'] = '1'
    env['PY_COLORS'] = '0'
    env['CLICOLOR'] = '0'
    env['CLICOLOR_FORCE'] = '0'
    env['DOLG_SKIP_ASGI'] = '1'
    env['DOLG_SKIP_OPTIONAL_APP_PROBES'] = '1'
    if '--quiet-django-log' in sys.argv:
        env['DOLG_SHOW_DJANGO_LOG'] = '0'
    else:
        env.setdefault('DOLG_SHOW_DJANGO_LOG', '1')
    env.setdefault('OLLAMA_BASE_URL', 'http://127.0.0.1:11434')
    env.setdefault('OLLAMA_MODEL', 'qwen3:0.6b')
    strict_migrations = env.get('DOLG_LAUNCHER_STRICT_MIGRATIONS') == '1'

    if not local_only and env.get('NGROK_AUTHTOKEN'):
        subprocess.run(
            [str(NGROK), 'config', 'add-authtoken', env['NGROK_AUTHTOKEN']],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )

    # ngrok — отдельная группа процессов (CTRL_BREAK_EVENT для чистой остановки).
    creation_flags_cf = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0

    # --- Самолечение ---
    orphans = kill_orphans()
    rep(
        'FIX' if orphans else 'OK',
        'Орфан-серверы: %s' % (('сняты PID ' + ', '.join(map(str, orphans))) if orphans else 'не найдены'),
    )

    if port_in_use('127.0.0.1', DJANGO_PORT):
        killed = free_port(DJANGO_PORT)
        time.sleep(1.0)
        if port_in_use('127.0.0.1', DJANGO_PORT):
            rep(
                'ERR',
                'Порт %d занят посторонним: %s. Закрой его и повтори.'
                % (DJANGO_PORT, port_holder(DJANGO_PORT)),
            )
            return _abort(report)
        rep('FIX', 'Порт %d освобождён (сняты: %s)' % (DJANGO_PORT, ', '.join(map(str, killed)) or '—'))
    else:
        rep('OK', 'Порт %d свободен' % DJANGO_PORT)

    migrate_state, migrate_detail = migration_state(py, env)
    if migrate_state in {'timeout', 'error'}:
        detail = migrate_detail + '; continuing local startup'
        rep('ERR' if strict_migrations else 'WARN', detail)
        if strict_migrations:
            return _abort(report)
    if migrate_state == 'pending':
        rep('WARN', 'Есть непринятые миграции — применяю...')
        try:
            mr = subprocess.run(
                [py, 'manage.py', 'migrate', '--noinput', '--skip-checks'],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
            )
            migrate_output = mr.stderr or mr.stdout or ''
        except subprocess.TimeoutExpired:
            rep('ERR' if strict_migrations else 'WARN', 'manage.py migrate --noinput timed out after 180s')
            if strict_migrations:
                return _abort(report)
            migrate_output = ''
            mr = None
        rep(
            'FIX' if mr is not None and mr.returncode == 0 else ('ERR' if strict_migrations else 'WARN'),
            'migrate: '
            + (
                'применены'
                if mr is not None and mr.returncode == 0
                else (migrate_output[-300:] or 'skipped/failed; continuing local startup')
            ),
        )
        if mr is not None and mr.returncode != 0 and strict_migrations:
            return _abort(report)
    elif migrate_state == 'ok':
        rep('OK', 'Миграции применены')

    # --- Старт Django с авто-fallback hot(jurigged) -> plain ---
    django_log_path = ROOT / '.tmp_django.log'
    try:
        django_log_path.write_text('', encoding='utf-8')
    except Exception:
        pass
    django, mode = _start_django(py, env, hot, django_log_path)
    rep('INFO', 'Старт Django (%s), жду готовности (до 90с)...' % mode)
    ok, ready_detail = wait_django_ready(django, '127.0.0.1', DJANGO_PORT, timeout=90)
    if not ok:
        ok = False
        if mode == 'hot':
            rep('WARN', 'hot/jurigged не поднялся (%s) — fallback на обычный режим...' % ready_detail)
            _kill_proc(django)
            leftover = kill_orphans()
            freed = free_port(DJANGO_PORT)
            if leftover or freed:
                rep('FIX', 'hot cleanup: сняты PID %s' % ', '.join(map(str, leftover + freed)))
            time.sleep(1.0)
            django, mode = _start_django(py, env, False, django_log_path)
            ok, ready_detail = wait_django_ready(django, '127.0.0.1', DJANGO_PORT, timeout=90)
        if not ok:
            tail = ''
            try:
                with open(django_log_path, encoding='utf-8') as f:
                    tail = f.read()[-1200:]
            except Exception:
                pass
            rep('ERR', 'Django не поднялся (%s). Хвост лога:\n%s' % (ready_detail, tail))
            _kill_proc(django)
            return _abort(report)

    rep('OK', 'Сервер отвечает (%s) на 127.0.0.1:%d' % (mode, DJANGO_PORT))
    _write_report(report)

    if exit_after_ready:
        rep('OK', 'Проверочный запуск завершён: сервер поднялся, теперь останавливаю процесс.')
        _kill_proc(django)
        return 0

    cf = None
    if local_only:
        local_url = 'http://127.0.0.1:%d/' % DJANGO_PORT
        line = '=' * 60
        p('')
        p(line)
        p('              >>> DOLG ГОТОВ К РАБОТЕ (локально) <<<')
        p(line)
        p('')
        p('   Открыть:')
        p('')
        p('       ' + local_url)
        p('')
        p('   Стабильный режим без autoreload. Ctrl+C — остановить сервер.')
        p('')
        if not no_browser:
            try:
                webbrowser.open(local_url)
            except Exception:
                pass
    else:
        p('')
        p('[2/3] Zapuskayu ngrok tunnel...')

        cf = subprocess.Popen(
            [str(NGROK), 'http', str(DJANGO_PORT), '--log=stdout'],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            creationflags=creation_flags_cf,
        )

        store = {'url': None, 'log': []}
        t = threading.Thread(target=reader_thread, args=(cf.stdout, store), daemon=True)
        t.start()

        p('      Zhdu publichnyy URL...')
        deadline = time.time() + 40
        while time.time() < deadline and not store['url']:
            if cf.poll() is not None:
                p('[ERROR] ngrok upal. Log:')
                for ln in store['log'][-25:]:
                    p('  ' + ln)
                django.terminate()
                input('\nEnter dlya vyhoda...')
                return 1
            time.sleep(0.3)

        if not store['url']:
            p('[ERROR] ngrok ne dal URL za 40 sek. Log:')
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
            p('       inogda ngrok propagiruet do 1 minuty.')

        banner(public_url)

        # Открываем в браузере только если propagated — иначе юзер сразу
        # увидит ошибку 1033 и расстроится.
        if propagated and not no_browser:
            try:
                webbrowser.open(public_url)
            except Exception:
                pass
        elif not propagated:
            p('   Brauzer NE otkryl avtomaticheski (tunnel eshe greetsya).')
            p('   Skoporiy URL vyshe i otkroy vruchnuyu cherez 30-60 sek.')
            p('')

    try:
        while True:
            time.sleep(2)
            if django.poll() is not None:
                p('\n[!] Django process died.')
                break
            if cf is not None and cf.poll() is not None:
                p('\n[!] Tunnel process died.')
                break
    except KeyboardInterrupt:
        p('\n[*] Stopping...')
    finally:
        # CTRL_BREAK_EVENT работает только на процессах, запущенных с
        # CREATE_NEW_PROCESS_GROUP (т.е. tunnel process). Django был запущен
        # без флага — посылка CTRL_BREAK туда упадёт с ValueError, поэтому
        # для него сразу .terminate().
        graceful = ([(cf, 'ngrok', True)] if cf is not None else []) + [(django, 'django', False)]
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
        p('[*] Stopped.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
