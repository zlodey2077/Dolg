"""CAD/netlist parsing helpers.

Lark is used for the simple SPICE/LTspice subset so unsupported syntax can be
reported cleanly while the old importer still receives normalized tokens.
"""

from __future__ import annotations

from functools import lru_cache

SPICE_LINE_GRAMMAR = r"""
    start: REF TOKEN TOKEN TOKEN*
    REF: /[A-Za-z][A-Za-z0-9_.-]*/
    TOKEN: /[^ \t\r\n]+/
    %ignore /[ \t]+/
"""


@lru_cache(maxsize=1)
def _spice_line_parser():
    from lark import Lark

    return Lark(SPICE_LINE_GRAMMAR, parser='lalr')


def parse_spice_component_line(line: str) -> dict:
    text = (line or '').strip()
    if not text:
        return {'ok': False, 'tokens': [], 'error': 'empty line'}
    if text.startswith('.'):
        return {'ok': False, 'tokens': [], 'error': 'directive'}
    try:
        tree = _spice_line_parser().parse(text)
    except Exception as exc:
        return {'ok': False, 'tokens': [], 'error': str(exc)}
    tokens = [
        str(token) for token in tree.scan_values(lambda item: getattr(item, 'type', None) in {'REF', 'TOKEN'})
    ]
    if len(tokens) < 4:
        return {'ok': False, 'tokens': tokens, 'error': 'too few fields'}
    return {'ok': True, 'tokens': tokens, 'error': ''}
