"""Custom system checks для `python manage.py check`.

Запускается автоматически на каждый dev/prod-старт сервера, на CI, и через
явный `manage.py check`. Если возвращает Error — старт сервера блокируется,
если Warning — печатается, но не блокирует.

Список проверок:
  - dolg.W001: multi-line `{# ... #}` Django-комментарии в шаблонах. Каждый
    такой текст утечёт на страницу как plain-text. Используем валидатор из
    scripts/check_django_comments.py (тот же regex).
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.core.checks import Warning as DjangoWarning
from django.core.checks import register

# Тот же regex, что в scripts/check_django_comments.py — держим источник
# истины в одном месте. Если нужно — вынесем в shared helper.
_MULTI_LINE_COMMENT_RE = re.compile(r'\{#(?:(?!#\}).)*?\n(?:(?!#\}).)*?#\}', re.DOTALL)
_SKIP_DIRS = ('.venv', 'site-packages', 'htmlcov', 'node_modules', 'release/', 'backups/')


@register()
def check_multi_line_django_comments(app_configs, **kwargs):
    """W001: ищет `{# ... #}` с переносом строки внутри.

    Django парсит такие комментарии как одностроковые: всё до закрывающей `#}`
    в той же строке выкидывается, а перенесённый хвост остаётся в HTML и виден
    юзеру как обычный текст. За проект наступали на это 4 раза (см. memory
    feedback_django_comments.md).
    """
    project_root = Path(getattr(settings, 'BASE_DIR', '.'))
    problems = []
    for tpl in project_root.rglob('*.html'):
        rel = str(tpl.relative_to(project_root)).replace('\\', '/')
        if any(skip in rel for skip in _SKIP_DIRS):
            continue
        try:
            text = tpl.read_text(encoding='utf-8')
        except Exception:
            continue
        for match in _MULTI_LINE_COMMENT_RE.finditer(text):
            line_no = text[: match.start()].count('\n') + 1
            snippet = match.group(0)[:60].replace('\n', ' / ')
            problems.append(f'{rel}:{line_no}  {snippet}')

    if not problems:
        return []

    msg = (
        f'Найдено {len(problems)} многострочных Django-комментариев `{{# ... #}}`. '
        f'Django парсит их построчно — текст утечёт на страницу. '
        f'Используйте `{{% comment %}}…{{% endcomment %}}`.\n'
        + '\n'.join('  ' + p for p in problems[:20])
        + (f'\n  …и ещё {len(problems) - 20}' if len(problems) > 20 else '')
    )
    return [DjangoWarning(msg, id='dolg.W001')]
