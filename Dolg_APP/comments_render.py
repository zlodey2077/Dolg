"""Безопасный рендер комментариев.

- Free (rich=False): plain-text с escape, авто-переносы строк, авто-линки URL.
- Pro (rich=True): Markdown через markdown2 + bleach-sanitize (whitelist тегов).

Markdown extras (markdown2):
- fenced-code-blocks (```python ... ```) — для code highlight
- code-friendly (не интерпретирует _ внутри слов как emphasis)
- cuddled-lists
- task_list
- tables
- strike

После рендера прогоняем через bleach с whitelist тегов и атрибутов.
Никакого <script>, <iframe>, on-handlers — только текстовые/inline-теги.
"""

import html as _html
import re

import bleach
import markdown2

ALLOWED_TAGS = [
    'p',
    'br',
    'strong',
    'em',
    'del',
    'code',
    'pre',
    'h1',
    'h2',
    'h3',
    'h4',
    'h5',
    'h6',
    'ul',
    'ol',
    'li',
    'blockquote',
    'hr',
    'a',
    'span',
    'img',
    'table',
    'thead',
    'tbody',
    'tr',
    'th',
    'td',
    'input',  # для task-list checkboxes
]

ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title', 'rel', 'target'],
    'img': ['src', 'alt', 'title', 'width', 'height'],
    'code': ['class'],  # для language hint (class="language-python")
    'pre': ['class'],
    'span': ['class'],
    'input': ['type', 'checked', 'disabled'],  # для task-list
}

ALLOWED_PROTOCOLS = ['http', 'https', 'mailto']


_URL_RE = re.compile(
    r'(https?://[^\s<>"\']+)',
    re.IGNORECASE,
)


def _plain_to_html(text: str) -> str:
    """Plain-text → HTML с переносами и автоссылками. Безопасный escape."""
    escaped = _html.escape(text)
    # Авто-ссылки
    escaped = _URL_RE.sub(
        lambda m: f'<a href="{m.group(1)}" rel="nofollow noopener" target="_blank">{m.group(1)}</a>',
        escaped,
    )
    # Переносы строк → <br>
    return escaped.replace('\n', '<br>')


_MD = markdown2.Markdown(
    extras=[
        'fenced-code-blocks',
        'code-friendly',
        'cuddled-lists',
        'task_list',
        'tables',
        'strike',
        'break-on-newline',
    ]
)


def _markdown_to_html(text: str) -> str:
    """Markdown → HTML → bleach-sanitize."""
    rendered = _MD.convert(text)
    cleaned = bleach.clean(
        rendered,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
    # Линкифицируем простые URL не в <a>
    cleaned = bleach.linkify(
        cleaned,
        callbacks=[
            lambda attrs, new=False: dict(attrs, **{'rel': 'nofollow noopener', 'target': '_blank'}),
        ],
    )
    return cleaned


def render(body: str, rich: bool = False) -> str:
    """Главная точка входа.

    Args:
        body: исходный текст комментария (от юзера).
        rich: True для Pro (Markdown), False для Free (plain).
    """
    if not body:
        return ''
    body = body.strip()
    if rich:
        return _markdown_to_html(body)
    return _plain_to_html(body)
