"""Генератор инженерного/лабораторного протокола (Markdown).

Один сборщик отчёта из готовых структурированных кусков. Двойное назначение:
  • симулятор/review → **инженерный протокол** проекта (приложения диплома Г/Д);
  • инженерная лаборатория/обучение → **протокол лабораторной работы** студента.

Формирует только секции, для которых есть данные (пустые пропускает). DC-расчёт
может посчитать сам из `scheme_data` (через MNA `solve_dc`); лаб-расчёты и findings
принимает готовыми (без реверс-зависимости на `knowledge`), поэтому headless-тестируем.

Expert-first: проверки выводятся с rule_id/severity/recommendation; числа — из движков.
"""

from __future__ import annotations

import time

_VALUE_FIELDS = ('resistance', 'capacitance', 'inductance', 'voltage', 'current', 'value', 'part_number')
_SEVERITY_ORDER = {'error': 0, 'warning': 1, 'info': 2}
_SEVERITY_LABEL = {'error': 'ошибка', 'warning': 'предупреждение', 'info': 'инфо'}


def _component_value(component: dict) -> str:
    for key in _VALUE_FIELDS:
        val = component.get(key)
        if val not in (None, ''):
            return str(val)
    return '—'


def _fmt(value, digits: int = 4) -> str:
    try:
        v = float(value)
    except TypeError, ValueError:
        return str(value)
    if v != v:  # NaN
        return '—'
    if v == 0:
        return '0'
    if abs(v) >= 1000 or abs(v) < 0.001:
        return f'{v:.{digits}g}'
    return f'{v:.{digits}g}'


def _scheme_section(scheme_data: dict) -> tuple[str, list[str]] | None:
    components = (scheme_data or {}).get('components') or []
    if not components:
        return None
    connections = (scheme_data or {}).get('connections') or []
    counts: dict[str, int] = {}
    rows = ['| Обозначение | Тип | Номинал |', '|---|---|---|']
    for c in components:
        if not isinstance(c, dict):
            continue
        ctype = str(c.get('type') or '—')
        counts[ctype] = counts.get(ctype, 0) + 1
        label = c.get('label') or c.get('id') or '—'
        rows.append(f'| {label} | {ctype} | {_component_value(c)} |')
    summary = ', '.join(f'{t}×{n}' for t, n in sorted(counts.items()))
    lines = [f'Компонентов: {len(components)}, соединений: {len(connections)}. Состав: {summary}.', '']
    lines.extend(rows)
    return ('Состав схемы', lines)


def _dc_section(scheme_data: dict) -> tuple[str, list[str]] | None:
    try:
        from .monte_carlo import scheme_to_circuit, solve_dc

        circuit = scheme_to_circuit(scheme_data)
        if not circuit.get('elements'):
            return None
        result = solve_dc(circuit)
    except Exception:
        return None
    voltages = result.get('voltages') or {}
    currents = result.get('currents') or {}
    if not voltages and not currents:
        return None
    lines = []
    if voltages:
        lines.append('Узловые потенциалы (В):')
        for node, v in sorted(voltages.items(), key=lambda kv: str(kv[0])):
            lines.append(f'- узел {node}: {_fmt(v)} В')
    if currents:
        lines.append('')
        lines.append('Токи через источники/диоды (А):')
        for cid, i in currents.items():
            lines.append(f'- {cid}: {_fmt(i)} А')
    return ('Расчёт рабочей точки (DC, MNA)', lines)


def _measurements_section(measurements: list) -> tuple[str, list[str]] | None:
    rows = []
    for m in measurements or []:
        if not isinstance(m, dict):
            continue
        label = m.get('label') or m.get('name') or 'измерение'
        unit = m.get('unit') or ''
        rows.append(f'- {label}: {_fmt(m.get("value"))} {unit}'.rstrip())
    if not rows:
        return None
    return ('Измерения', rows)


def _lab_section(lab_calcs: list) -> tuple[str, list[str]] | None:
    lines = []
    for calc in lab_calcs or []:
        if not isinstance(calc, dict) or not calc.get('ok', True):
            continue
        title = calc.get('title') or calc.get('kind') or 'расчёт'
        status = calc.get('status_label') or calc.get('status') or ''
        head = f'**{title}**' + (f' — _{status}_' if status else '')
        lines.append(head)
        for out in (calc.get('outputs') or {}).values():
            if not isinstance(out, dict):
                continue
            disp = out.get('display') if out.get('display') is not None else _fmt(out.get('value'))
            lines.append(f'- {out.get("label", "")}: {disp} {out.get("unit", "")}'.rstrip())
        if calc.get('feedback'):
            lines.append(f'  > {calc["feedback"]}')
        lines.append('')
    if not lines:
        return None
    return ('Инженерные расчёты', lines)


def _findings_section(findings: list) -> tuple[str, list[str]] | None:
    items = [f for f in (findings or []) if isinstance(f, dict)]
    if not items:
        return None
    items.sort(key=lambda f: _SEVERITY_ORDER.get(f.get('severity'), 9))
    lines = []
    for f in items:
        sev = _SEVERITY_LABEL.get(f.get('severity'), f.get('severity') or 'инфо')
        rid = f.get('rule_id') or ''
        msg = f.get('message') or ''
        lines.append(f'- **[{sev}]** {msg}' + (f' `({rid})`' if rid else ''))
        if f.get('recommendation'):
            lines.append(f'  → {f["recommendation"]}')
    return ('Проверки (DRC / review)', lines)


def build_protocol(
    title: str = 'Протокол проектирования',
    scheme_data: dict | None = None,
    *,
    include_dc: bool = True,
    measurements: list | None = None,
    lab_calcs: list | None = None,
    findings: list | None = None,
    notes: str | None = None,
    author: str | None = None,
) -> dict:
    """Собирает протокол. Возвращает {'markdown', 'sections', 'meta'}.

    Все блоки опциональны — секция попадает в отчёт только если по ней есть данные.
    `lab_calcs` — результаты `engineering_lab.calculate_lab` (передаются готовыми).
    `findings` — список {rule_id, severity, message, recommendation} (review/pcb_drc).
    """
    sections: list[tuple[str, list[str]]] = []
    if scheme_data:
        sec = _scheme_section(scheme_data)
        if sec:
            sections.append(sec)
        if include_dc:
            sec = _dc_section(scheme_data)
            if sec:
                sections.append(sec)
    for builder, arg in (
        (_measurements_section, measurements),
        (_lab_section, lab_calcs),
        (_findings_section, findings),
    ):
        sec = builder(arg)
        if sec:
            sections.append(sec)
    if notes:
        sections.append(('Выводы', [str(notes)]))

    stamp = time.strftime('%Y-%m-%d %H:%M')
    head = [f'# {title}', '', f'_Сформировано: {stamp}_']
    if author:
        head.append(f'_Автор: {author}_')
    head.append('')
    body: list[str] = []
    for name, lines in sections:
        body.append(f'## {name}')
        body.extend(lines)
        body.append('')

    markdown = '\n'.join(head + body).rstrip() + '\n'
    return {
        'markdown': markdown,
        'sections': [name for name, _ in sections],
        'meta': {
            'generated_at': stamp,
            'section_count': len(sections),
            'has_findings': bool(findings),
        },
    }
