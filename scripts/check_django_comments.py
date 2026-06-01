"""Static check: find multi-line `{# ... #}` Django comments that leak as plain text.

Django parses `{# ... #}` only as a single-line comment. Anything with a newline
between the braces gets passed through to the browser as visible HTML — text
appears on the page, and any literal HTML inside the comment is interpreted.
This script grep-style scans all .html files in the repo and reports each
violation as ``path:line  <snippet>``.

Usage:
    python scripts/check_django_comments.py

Exit code 0 if clean, 1 if any leaks found. Wire into pre-commit or CI to
guarantee zero leaks (this has bitten the project 4 times already — see
memory/feedback_django_comments.md).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PATTERN = re.compile(r"\{#(?:(?!#\}).)*?\n(?:(?!#\}).)*?#\}", re.DOTALL)
SKIP = ('.venv', 'site-packages', 'htmlcov', 'node_modules', 'release/', 'backups/')


def main() -> int:
    problems: list[str] = []
    for tpl in Path('.').rglob('*.html'):
        path = str(tpl).replace('\\', '/')
        if any(skip in path for skip in SKIP):
            continue
        try:
            text = tpl.read_text(encoding='utf-8')
        except Exception:
            continue
        for match in PATTERN.finditer(text):
            line_no = text[:match.start()].count('\n') + 1
            snippet = match.group(0)[:80].replace('\n', ' / ')
            problems.append(f'{tpl}:{line_no}  {snippet}')

    if not problems:
        print('OK: no multi-line {# #} leaks found.')
        return 0

    print(f'FAIL: {len(problems)} multi-line Django comment leaks (use {{% comment %}}…{{% endcomment %}} instead):')
    for p in problems[:50]:
        print(' ', p)
    if len(problems) > 50:
        print(f'  ... and {len(problems) - 50} more')
    return 1


if __name__ == '__main__':
    sys.exit(main())
