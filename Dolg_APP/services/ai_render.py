"""L3: render-директивы локального AI — гибрид (структурный массив + inline-токены).

Локальный ответ может нести два слоя (юзер: «гибрид, не пережимать»):
- структурный `render`-массив `[{type:'plot'|'value'|'table'|'highlight', ...}]` —
  надёжно, для крупных виджетов (график, таблица);
- inline-токены `[[value:…]]` / `[[highlight:R1]]` прямо в тексте — для контекстных
  вставок «в середине фразы». Фронт рендерит оба слоя.

Графики — matplotlib SVG (надёжно/просто, без интерактива пока). highlight — по
id компонента (узел-сеть оставлен как будущая возможность, см. arg='net:N').
"""

from __future__ import annotations

import re
from typing import Any

# Inline-токены: [[type:arg]] — type ∈ value|highlight|measure|plot|table.
_TOKEN_RE = re.compile(r'\[\[(\w+):([^\]]+)\]\]')
INLINE_TYPES = frozenset({'value', 'highlight', 'measure', 'plot', 'table'})


def parse_inline_tokens(text: str | None) -> list[dict[str, str]]:
    """Извлекает inline-директивы [[type:arg]] из текста (для валидации/фронта).

    Текст НЕ меняем — фронт сам заменит токены на виджеты на месте (гибрид)."""
    if not text:
        return []
    out = []
    for match in _TOKEN_RE.finditer(text):
        dtype = match.group(1).lower()
        if dtype in INLINE_TYPES:
            out.append({'type': dtype, 'arg': match.group(2).strip(), 'raw': match.group(0)})
    return out


def dc_voltage_plot(scheme_data: dict | None) -> str | None:
    """SVG-бар напряжений узлов (matplotlib Agg). None если схема не решается MNA."""
    from .ai_toolkit import compute_dc

    dc = compute_dc(scheme_data)
    if not dc['ok']:
        return None
    nets = sorted(n for n in dc['voltages'] if n != 0)
    if not nets:
        return None
    try:
        import io

        import matplotlib

        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(4.2, 2.4))
        ax.bar([f'узел {n}' for n in nets], [dc['voltages'][n] for n in nets], color='#00a0c0')
        ax.set_ylabel('В')
        ax.set_title('Напряжения узлов (MNA)')
        ax.grid(axis='y', alpha=0.3)
        fig.tight_layout()
        buf = io.StringIO()
        fig.savefig(buf, format='svg')
        plt.close(fig)
        return buf.getvalue()
    except Exception:
        return None


def build_render_items(scheme_data: dict | None, intent: str) -> list[dict[str, Any]]:
    """Структурные render-айтемы под интент (пока: plot напряжений узлов).

    Display-only (авто-рендер). Canvas-мутации (highlight) идут inline-токенами и
    применяются по клику на фронте."""
    items: list[dict[str, Any]] = []
    if intent in {'measurement', 'overview', 'scheme_overview', 'formula', 'thermal'}:
        svg = dc_voltage_plot(scheme_data)
        if svg:
            items.append(
                {
                    'type': 'plot',
                    'format': 'svg',
                    'title': 'Напряжения узлов (MNA)',
                    'svg': svg,
                    'placement': 'chat',
                }
            )
    return items
