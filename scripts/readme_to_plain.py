"""One-shot script: convert README.md from markdown to clean plain text.

Removes badges, links (keeps text + URL in parens for external), inline code
(turned into "quoted"), bold/italic markers, table separators, list bullets
become «• ». Run once after `python README split` step that puts history
into docs/CHANGELOG.md.
"""

from __future__ import annotations

import re
from pathlib import Path


def main() -> None:
    src = Path('README.md')
    text = src.read_text(encoding='utf-8')

    # 1. Badges at top: ![tests](https://img.shields.io/...)
    text = re.sub(r'^!\[.*?\]\(.*?\)\s*\n', '', text, flags=re.MULTILINE)

    # 2. Inline images
    text = re.sub(r'!\[[^\]\n]*\]\([^)\n]+\)', '', text)

    # 3. Links [text](url): keep text + (url) for external, just text for anchors/local
    def link_repl(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        if url.startswith('#') or url.endswith('.md') or url.startswith('docs/') or url.startswith('media/'):
            return label
        return f'{label} ({url})'
    text = re.sub(r'\[([^\]\n]+)\]\(([^)\n]+)\)', link_repl, text)

    # 4. Code fences ```lang\ncode\n``` → indent by 4 spaces, drop language label
    def code_block_repl(m: re.Match) -> str:
        body = m.group(2)
        return '\n'.join('    ' + line for line in body.split('\n'))
    text = re.sub(r'```(\w*)\n(.*?)```', code_block_repl, text, flags=re.DOTALL)

    # 5. Inline code `x` → "x"
    text = re.sub(r'`([^`\n]+)`', r'"\1"', text)

    # 6. Bold **x** / __x__ → x
    text = re.sub(r'\*\*([^*\n]+)\*\*', r'\1', text)
    text = re.sub(r'__([^_\n]+)__', r'\1', text)
    # Italic *x* / _x_ — careful with bullet asterisks and SI underscores
    text = re.sub(r'(?<!\w)\*([^*\n]+)\*(?!\w)', r'\1', text)
    text = re.sub(r'(?<!\w)_([^_\n]+)_(?!\w)', r'\1', text)

    # 7. Headers `#`/`##` → plain text. H1 uppercased. Others as-is.
    def header_repl(m: re.Match) -> str:
        level = len(m.group(1))
        body = m.group(2).strip()
        if level == 1:
            return body.upper()
        return body
    text = re.sub(r'^(#{1,6})\s+(.+?)\s*$', header_repl, text, flags=re.MULTILINE)

    # 8. Tables: skip separator rows '|---|---|', convert data rows
    out = []
    for line in text.split('\n'):
        stripped = line.strip()
        # Separator row
        if stripped and all(c in '-:| ' for c in stripped) and '|' in stripped:
            continue
        # Data row
        if stripped.startswith('|') and stripped.count('|') >= 2:
            cells = [c.strip() for c in stripped.strip('|').split('|')]
            out.append('  ' + ' · '.join(cells))
        else:
            out.append(line)
    text = '\n'.join(out)

    # 9. Lists '- ' / '* ' / '+ ' → '• '
    text = re.sub(r'^([ \t]*)[-*+]\s+', r'\1• ', text, flags=re.MULTILINE)

    # 10. Horizontal rule lines
    text = re.sub(r'^[-=_]{3,}\s*$', '', text, flags=re.MULTILINE)

    # 11. Multiple blank lines → single
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 12. Trailing whitespace
    text = re.sub(r'[ \t]+\n', '\n', text)

    src.write_text(text.strip() + '\n', encoding='utf-8')
    print(f'README.md → plain text: {len(text)} chars, {text.count(chr(10))} lines')


if __name__ == '__main__':
    main()
