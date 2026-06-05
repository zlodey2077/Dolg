"""Claude Code PostToolUse hook: авто-линт после правки Python-файла.

Подключается в ~/.claude/settings.json -> hooks.PostToolUse (matcher Edit|Write).
Получает на stdin JSON с tool_input.file_path. Если файл .py — гоняет
`ruff --fix` (безопасные авто-фиксы) и печатает остаток проблем, чтобы агент
сразу увидел и починил, не дожидаясь ручной проверки человеком.

Это часть "паранойдальной автоматизации": каждая правка кода автоматически
проходит линтер, мои ошибки ловятся мгновенно. Non-blocking (exit 0) — не
ломает поток, только сообщает.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUFF = ROOT / '.venv' / 'Scripts' / 'ruff.exe'


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    tool_input = payload.get('tool_input') or {}
    fp = tool_input.get('file_path') or ''
    if not fp.endswith('.py'):
        return 0
    path = Path(fp)
    if not path.exists():
        return 0
    ruff = str(RUFF) if RUFF.exists() else 'ruff'
    # 1) безопасные авто-фиксы
    try:
        subprocess.run([ruff, 'check', '--fix', '--quiet', str(path)], cwd=str(ROOT), timeout=60)
    except Exception:
        pass
    # 2) остаток проблем — в stdout, агент увидит
    try:
        res = subprocess.run(
            [ruff, 'check', str(path)], cwd=str(ROOT),
            capture_output=True, text=True, timeout=60,
        )
    except Exception:
        return 0
    out = (res.stdout or '').strip()
    if res.returncode != 0 and out:
        print(f'[hook ruff] остались проблемы в {path.name}:\n{out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
