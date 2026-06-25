"""Public DOLG launcher.

This is a small Python entrypoint for demo/public mode. It keeps the public
launch separate from the dev/local launcher, repairs the common ngrok v3 config
mistake, then delegates the actual Django+ngrok lifecycle to start_server.py.

Usage:
    .venv\\Scripts\\python.exe start_public_server.py
    .venv\\Scripts\\python.exe start_public_server.py --check-only
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


ROOT = Path(__file__).resolve().parent
NGROK_CONFIG_RE = re.compile(r'^\s*authtoken\s*:\s*(?P<token>.+?)\s*$')
ROOT_AUTHTOKEN_RE = re.compile(r'^authtoken\s*:\s*(?P<token>.+?)\s*$')


def out(message: str) -> None:
    print(message, flush=True)


def mask_secret(value: str) -> str:
    value = value.strip().strip('"').strip("'")
    if not value:
        return ''
    if len(value) <= 10:
        return '***'
    return value[:4] + '...' + value[-4:]


def find_python() -> str:
    venv_python = ROOT / '.venv' / 'Scripts' / 'python.exe'
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


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


def repair_ngrok_config(path: Path) -> tuple[bool, str]:
    """Move root-level authtoken into agent.authtoken for ngrok config v3.

    ngrok v3 rejects this shape:
        version: "3"
        agent:
          authtoken: xxx
        authtoken: xxx

    The function preserves the rest of the file and writes a timestamped backup
    only when it actually changes the config.
    """
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
            insert_at = agent_line_index + 1
            fixed_lines.insert(insert_at, f'  authtoken: {root_token}')
        else:
            insert_at = 1 if fixed_lines else 0
            fixed_lines[insert_at:insert_at] = ['agent:', f'  authtoken: {root_token}']

    backup = path.with_suffix(path.suffix + f'.bak-{time.strftime("%Y%m%d-%H%M%S")}')
    path.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(raw, encoding='utf-8')
    path.write_text('\n'.join(fixed_lines).rstrip() + '\n', encoding='utf-8')
    return True, f'ngrok config repaired; backup: {backup.name}; token: {mask_secret(root_token)}'


def check_ngrok_config(ngrok: Path, config_path: Path, env: dict[str, str]) -> tuple[bool, str]:
    cmd = [str(ngrok), 'config', 'check']
    if config_path.exists():
        cmd.extend(['--config', str(config_path)])
    try:
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=25,
        )
    except subprocess.TimeoutExpired:
        return False, 'ngrok config check timed out'
    except Exception as exc:
        return False, f'ngrok config check failed: {exc}'

    output = (result.stdout or result.stderr or '').strip()
    if result.returncode != 0:
        return False, output or f'ngrok config check exited with {result.returncode}'
    return True, output or 'ngrok config is valid'


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


def run() -> int:
    parser = argparse.ArgumentParser(description='Start public DOLG server through ngrok.')
    parser.add_argument('--check-only', action='store_true', help='validate launch prerequisites and exit')
    parser.add_argument('--no-browser', action='store_true', help='do not open browser after tunnel is ready')
    parser.add_argument('--hot', action='store_true', help='try jurigged hot patching in Django')
    parser.add_argument('--no-repair-ngrok', action='store_true', help='skip automatic ngrok.yml v3 repair')
    args = parser.parse_args()

    env = build_env()
    python = find_python()
    ngrok = find_ngrok()
    config_path = ngrok_config_path()

    out('DOLG public Python launcher')
    out(f'  python: {python}')
    out(f'  ngrok:  {ngrok or "not found"}')
    out(f'  config: {config_path}')

    if not (ROOT / 'manage.py').exists():
        out('[ERROR] manage.py not found; run this from the project root.')
        return 1
    if not (ROOT / 'start_server.py').exists():
        out('[ERROR] start_server.py not found; public lifecycle engine is missing.')
        return 1
    if not ngrok:
        out('[ERROR] ngrok.exe not found in deploy/, project root, PATH, or WinGet package folder.')
        out('        Install: winget install --id Ngrok.Ngrok --exact')
        return 1

    if not args.no_repair_ngrok:
        repaired, message = repair_ngrok_config(config_path)
        out(('  repair: ' if repaired else '  ngrok:  ') + message)

    ok, detail = check_ngrok_config(ngrok, config_path, env)
    out(('  check:  ' if ok else '[ERROR] ') + detail)
    if not ok:
        return 1

    if args.check_only:
        out('OK: public launcher prerequisites are ready.')
        return 0

    child = [python, 'start_server.py']
    child.append('--hot' if args.hot else '--no-hot')
    if args.no_browser:
        child.append('--no-browser')

    out('')
    out('Starting public Django server through ngrok...')
    out('Local URL will be:  http://127.0.0.1:8000/')
    out('Public URL appears after ngrok tunnel allocation.')
    out('')
    return subprocess.call(child, cwd=str(ROOT), env=env)


if __name__ == '__main__':
    raise SystemExit(run())
