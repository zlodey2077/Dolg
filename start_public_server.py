"""Public DOLG launcher.

Default provider: ngrok via deploy/ngrok.exe.
Cloudflare remains available as an explicit fallback, but it is not the default
because Quick Tunnel repeatedly returned error 1033 in this environment.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


ROOT = Path(__file__).resolve().parent
DJANGO_PORT = 8000
CLOUDFLARE_URL_RE = re.compile(r'https://[a-z0-9-]+\.trycloudflare\.com')
NGROK_URL_RE = re.compile(r'https://[a-z0-9-]+\.ngrok(?:-free)?\.(?:dev|app|io)')
NGROK_CONFIG_RE = re.compile(r'^\s*authtoken\s*:\s*(?P<token>.+?)\s*$')
ROOT_AUTHTOKEN_RE = re.compile(r'^authtoken\s*:\s*(?P<token>.+?)\s*$')


def out(message: str) -> None:
    print(message, flush=True)


def find_python() -> str:
    venv_python = ROOT / '.venv' / 'Scripts' / 'python.exe'
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def find_cloudflared() -> Path | None:
    candidates = [
        os.getenv('CLOUDFLARED_BIN', ''),
        str(ROOT / 'deploy' / 'cloudflared.exe'),
        str(ROOT / 'cloudflared.exe'),
        shutil.which('cloudflared') or '',
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return None


def find_ngrok() -> Path | None:
    candidates = [
        os.getenv('NGROK_BIN', ''),
        str(ROOT / 'deploy' / 'ngrok.exe'),
        str(ROOT / 'ngrok.exe'),
        shutil.which('ngrok') or '',
        str(
            Path(os.getenv('LOCALAPPDATA', ''))
            / 'Microsoft'
            / 'WinGet'
            / 'Packages'
            / 'Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe'
            / 'ngrok.exe'
        ),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return None


def ngrok_config_path() -> Path:
    local_appdata = os.getenv('LOCALAPPDATA')
    if local_appdata:
        return Path(local_appdata) / 'ngrok' / 'ngrok.yml'
    return Path.home() / 'AppData' / 'Local' / 'ngrok' / 'ngrok.yml'


def _is_ngrok_v3(lines: list[str]) -> bool:
    for line in lines:
        stripped = line.lstrip('\ufeff').strip().replace('"', '').replace("'", '')
        if stripped.startswith('version:'):
            return stripped.split(':', 1)[1].strip() == '3'
    return False


def mask_secret(value: str) -> str:
    value = value.strip().strip('"').strip("'")
    if not value:
        return ''
    if len(value) <= 10:
        return '***'
    return value[:4] + '...' + value[-4:]


def repair_ngrok_config(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f'ngrok config not found: {path}'

    raw = path.read_text(encoding='utf-8', errors='replace')
    lines = raw.splitlines()
    if not _is_ngrok_v3(lines):
        return False, 'ngrok config exists; not v3, no repair needed'

    root_token = ''
    root_token_indexes: list[int] = []
    has_indented_token = False
    has_agent_section = False
    agent_line_index = -1

    for index, line in enumerate(lines):
        if re.match(r'^agent\s*:\s*$', line):
            has_agent_section = True
            agent_line_index = index
        root_match = ROOT_AUTHTOKEN_RE.match(line)
        if root_match:
            root_token = root_match.group('token').strip()
            root_token_indexes.append(index)
            continue
        if NGROK_CONFIG_RE.match(line) and line[:1].isspace():
            has_indented_token = True

    if not root_token_indexes:
        return False, 'ngrok config already uses v3-compatible token placement'

    fixed_lines = [line for index, line in enumerate(lines) if index not in root_token_indexes]
    if not has_indented_token and root_token:
        if has_agent_section and agent_line_index >= 0:
            fixed_lines.insert(agent_line_index + 1, f'  authtoken: {root_token}')
        else:
            fixed_lines[1:1] = ['agent:', f'  authtoken: {root_token}']

    backup = path.with_suffix(path.suffix + f'.bak-{time.strftime("%Y%m%d-%H%M%S")}')
    backup.write_text(raw, encoding='utf-8')
    path.write_text('\n'.join(fixed_lines).rstrip() + '\n', encoding='utf-8')
    return True, f'ngrok config repaired; backup: {backup.name}; token: {mask_secret(root_token)}'


def check_binary(binary: Path, args: list[str], attempts: int = 2) -> tuple[bool, str]:
    last_detail = ''
    for attempt in range(1, attempts + 1):
        try:
            result = subprocess.run(
                [str(binary), *args],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=25,
            )
        except subprocess.TimeoutExpired:
            last_detail = f'{binary.name} check timed out'
        except Exception as exc:
            last_detail = f'{binary.name} check failed: {exc}'
        else:
            output = (result.stdout or result.stderr or '').strip()
            if result.returncode == 0:
                suffix = '' if attempt == 1 else f' (after retry {attempt})'
                return True, (output or f'{binary.name} ok') + suffix
            last_detail = output or f'{binary.name} exited with {result.returncode}'
        if attempt < attempts:
            time.sleep(1.0)
    return False, last_detail


def build_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault('DEBUG', 'True')
    env.setdefault('PYTHONUTF8', '1')
    env.setdefault('PYTHONIOENCODING', 'utf-8')
    env.setdefault('PYTHONUNBUFFERED', '1')
    env.setdefault('DOLG_SKIP_ASGI', '1')
    env.setdefault('DOLG_SKIP_OPTIONAL_APP_PROBES', '1')
    env.setdefault('DOLG_SKIP_SOCIALACCOUNT_PROVIDERS', '1')
    env.setdefault('OLLAMA_BASE_URL', 'http://127.0.0.1:11434')
    env.setdefault('OLLAMA_MODEL', 'qwen3:0.6b')
    return env


def wait_tcp(host: str, port: int, timeout: int = 90) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def probe_url(url: str, timeout: int = 8) -> bool:
    try:
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'DOLG-public-launcher/1.0',
                'ngrok-skip-browser-warning': '1',
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status < 600
    except urllib.error.HTTPError as exc:
        return exc.code not in {530}
    except Exception:
        return False


def reader_thread(stream, store: dict[str, object], url_re: re.Pattern[str], prefix: str = '') -> None:
    for raw in iter(stream.readline, b''):
        line = raw.decode('utf-8', errors='replace').rstrip()
        log = store.setdefault('log', [])
        if isinstance(log, list):
            log.append(line)
            if len(log) > 500:
                del log[:-500]
        if line:
            out((prefix + ' ' if prefix else '') + line)
        if not store.get('url'):
            match = url_re.search(line)
            if match:
                store['url'] = match.group(0)


def start_with_reader(
    cmd: list[str],
    env: dict[str, str],
    url_re: re.Pattern[str] | None = None,
    prefix: str = '',
):
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
        creationflags=flags,
    )
    store: dict[str, object] = {'url': None, 'log': []}
    pattern = url_re or re.compile(r'$^')
    thread = threading.Thread(target=reader_thread, args=(proc.stdout, store, pattern, prefix), daemon=True)
    thread.start()
    return proc, store


def stop_proc(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    except Exception:
        pass


def banner(public_url: str, provider: str) -> None:
    line = '=' * 66
    out('')
    out(line)
    out('              >>> DOLG PUBLIC DEMO READY <<<')
    out(line)
    out('')
    out(f'   Public URL ({provider}):')
    out('')
    out(f'       {public_url}')
    out('')
    out(f'   Local URL: http://127.0.0.1:{DJANGO_PORT}/')
    out(line)
    out('')


def run_cloudflare(args, env: dict[str, str], python: str, cloudflared: Path) -> int:
    out('Starting local Django launcher...')
    local_cmd = [python, 'start_server.py', '--local', '--no-browser', '--hot' if args.hot else '--no-hot']
    local_proc, local_log = start_with_reader(local_cmd, env, prefix='[local]')

    if not wait_tcp('127.0.0.1', DJANGO_PORT, timeout=120):
        out('[ERROR] Django did not become ready on 127.0.0.1:8000.')
        for line in list(local_log.get('log', []))[-35:]:
            out('  ' + str(line))
        stop_proc(local_proc)
        return 1

    out('Starting Cloudflare Quick Tunnel...')
    tunnel_cmd = [str(cloudflared), 'tunnel', '--url', f'http://127.0.0.1:{DJANGO_PORT}']
    tunnel_proc, tunnel_log = start_with_reader(tunnel_cmd, env, CLOUDFLARE_URL_RE, prefix='[cloudflare]')

    deadline = time.time() + 75
    while time.time() < deadline and not tunnel_log.get('url'):
        if tunnel_proc.poll() is not None:
            out('[ERROR] cloudflared exited before URL allocation. Log tail:')
            for line in list(tunnel_log.get('log', []))[-35:]:
                out('  ' + str(line))
            stop_proc(local_proc)
            return 1
        time.sleep(0.3)

    public_url = str(tunnel_log.get('url') or '')
    if not public_url:
        out('[ERROR] cloudflared did not provide a public URL in 75 seconds. Log tail:')
        for line in list(tunnel_log.get('log', []))[-35:]:
            out('  ' + str(line))
        stop_proc(tunnel_proc)
        stop_proc(local_proc)
        return 1

    propagated = False
    deadline = time.time() + 60
    while time.time() < deadline:
        if probe_url(public_url):
            propagated = True
            break
        time.sleep(3)

    if not propagated:
        out('[WARN] Tunnel URL allocated but not reachable yet; it may need 30-60 seconds.')

    banner(public_url, 'cloudflare')
    if not args.no_browser and propagated:
        webbrowser.open(public_url)

    try:
        while True:
            time.sleep(2)
            if local_proc.poll() is not None:
                out('[ERROR] Django local launcher stopped.')
                return local_proc.returncode or 1
            if tunnel_proc.poll() is not None:
                out('[ERROR] Cloudflare tunnel stopped.')
                return tunnel_proc.returncode or 1
    except KeyboardInterrupt:
        out('Stopping public launcher...')
        return 0
    finally:
        stop_proc(tunnel_proc)
        stop_proc(local_proc)


def run_ngrok(args, env: dict[str, str], python: str, ngrok: Path) -> int:
    out('Starting ngrok public tunnel...')
    out('  note: free ngrok domains can show a one-time browser warning to visitors.')
    config_path = ngrok_config_path()
    if not args.no_repair_ngrok:
        repaired, message = repair_ngrok_config(config_path)
        out(('  repair: ' if repaired else '  ngrok:  ') + message)
    ok, detail = check_binary(ngrok, ['config', 'check', '--config', str(config_path)])
    out(('  check:  ' if ok else '[ERROR] ') + detail)
    if not ok:
        return 1
    child = [python, 'start_server.py', '--hot' if args.hot else '--no-hot']
    if args.no_browser:
        child.append('--no-browser')
    return subprocess.call(child, cwd=str(ROOT), env=env)


def run() -> int:
    parser = argparse.ArgumentParser(description='Start public DOLG server.')
    parser.add_argument(
        '--provider',
        choices=['cloudflare', 'local', 'ngrok'],
        default=os.getenv('DOLG_PUBLIC_TUNNEL_PROVIDER', 'ngrok'),
        help='public tunnel provider; default: ngrok',
    )
    parser.add_argument('--check-only', action='store_true', help='validate launch prerequisites and exit')
    parser.add_argument('--no-browser', action='store_true', help='do not open browser after tunnel is ready')
    parser.add_argument('--hot', action='store_true', help='try jurigged hot patching in Django')
    parser.add_argument('--no-repair-ngrok', action='store_true', help='skip automatic ngrok.yml v3 repair')
    args = parser.parse_args()

    env = build_env()
    python = find_python()
    cloudflared = find_cloudflared()
    ngrok = find_ngrok()

    out('DOLG public Python launcher')
    out(f'  provider:    {args.provider}')
    out(f'  python:      {python}')
    out(f'  ngrok:       {ngrok or "not found"}')
    out(f'  cloudflared: {cloudflared or "not used"}')

    if not (ROOT / 'manage.py').exists():
        out('[ERROR] manage.py not found; run this from the project root.')
        return 1
    if not (ROOT / 'start_server.py').exists():
        out('[ERROR] start_server.py not found; local lifecycle engine is missing.')
        return 1

    if args.provider == 'cloudflare':
        if not cloudflared:
            out('[ERROR] cloudflared.exe not found. Expected deploy/cloudflared.exe or CLOUDFLARED_BIN.')
            return 1
        ok, detail = check_binary(cloudflared, ['--version'])
        out(('  check:      ' if ok else '[ERROR] ') + detail)
        if not ok:
            return 1
        if args.check_only:
            out('OK: Cloudflare public launcher prerequisites are ready.')
            return 0
        return run_cloudflare(args, env, python, cloudflared)

    if args.provider == 'local':
        if args.check_only:
            out('OK: local fallback is ready.')
            return 0
        child = [python, 'start_server.py', '--local', '--no-hot']
        if args.no_browser:
            child.append('--no-browser')
        return subprocess.call(child, cwd=str(ROOT), env=env)

    if not ngrok:
        out('[ERROR] ngrok.exe not found.')
        return 1
    if args.check_only:
        config_path = ngrok_config_path()
        if not args.no_repair_ngrok:
            repair_ngrok_config(config_path)
        ok, detail = check_binary(ngrok, ['config', 'check', '--config', str(config_path)])
        out(('  check:      ' if ok else '[ERROR] ') + detail)
        if ok:
            out('OK: ngrok public launcher prerequisites are ready.')
            return 0
        return 1
    return run_ngrok(args, env, python, ngrok)


if __name__ == '__main__':
    raise SystemExit(run())
