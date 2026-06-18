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

from ..pcb_layout import analyze_pcb_drc, compute_pcb_layout

_VALUE_FIELDS = ('resistance', 'capacitance', 'inductance', 'voltage', 'current', 'value', 'part_number')
_SEVERITY_ORDER = {'error': 0, 'warning': 1, 'info': 2}
_SEVERITY_LABEL = {'error': 'ошибка', 'warning': 'предупреждение', 'info': 'инфо'}
_EMPTY_CELL = '—'
_SPARKLINE = '▁▂▃▄▅▆▇█'


def _component_value(component: dict) -> str:
    for key in _VALUE_FIELDS:
        val = component.get(key)
        if val not in (None, ''):
            return str(val)
    return '—'


def _fmt(value, digits: int = 4) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if v != v:  # NaN
        return '—'
    if v == 0:
        return '0'
    if abs(v) >= 1000 or abs(v) < 0.001:
        return f'{v:.{digits}g}'
    return f'{v:.{digits}g}'


def _float_or_none(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:  # NaN
        return None
    return result


def _md_cell(value) -> str:
    text = str(value or _EMPTY_CELL).strip() or _EMPTY_CELL
    return text.replace('|', '/')


def _first_component_value(component: dict, *keys: str) -> str:
    for key in keys:
        value = component.get(key)
        if value not in (None, '', False):
            return str(value)
    return ''


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


def _bom_section(scheme_data: dict) -> tuple[str, list[str]] | None:
    components = (scheme_data or {}).get('components') or []
    if not components:
        return None

    linked = footprints = datasheets = spice_models = 0
    rows = [
        '| Обозначение | BOM/каталог | Footprint/CAD | Datasheet | SPICE |',
        '|---|---|---|---|---|',
    ]
    for component in components:
        if not isinstance(component, dict):
            continue
        label = component.get('label') or component.get('id') or _EMPTY_CELL
        catalog = _first_component_value(
            component, 'catalog_ref', 'catalog_slug', 'part_number', 'sku', 'product_id'
        )
        footprint = _first_component_value(component, 'footprint', 'cad_model', 'package')
        datasheet = _first_component_value(component, 'datasheet_url', 'datasheet', 'product_datasheet_url')
        spice = _first_component_value(component, 'spice_model', 'model')
        linked += int(bool(catalog))
        footprints += int(bool(footprint))
        datasheets += int(bool(datasheet))
        spice_models += int(bool(spice))
        rows.append(
            '| '
            + ' | '.join(
                [
                    _md_cell(label),
                    _md_cell(catalog),
                    _md_cell(footprint),
                    _md_cell(datasheet),
                    _md_cell(spice),
                ]
            )
            + ' |'
        )

    total = len([component for component in components if isinstance(component, dict)])
    if not total:
        return None
    lines = [
        (
            f'Компонентов: {total}; связаны с BOM/каталогом: {linked}; '
            f'footprint/CAD: {footprints}; datasheet: {datasheets}; SPICE-модель: {spice_models}.'
        ),
        '',
    ]
    lines.extend(rows)
    return ('BOM и источники компонентов', lines)


def _pcb_drc_section(scheme_data: dict) -> tuple[str, list[str]] | None:
    components = (scheme_data or {}).get('components') or []
    if not components:
        return None
    try:
        layout = compute_pcb_layout(scheme_data)
        drc = analyze_pcb_drc(layout, scheme_data)
    except Exception:
        return None

    summary = drc.get('summary') or {}
    rules = drc.get('rules') or {}
    status = drc.get('status') or 'unknown'
    status_label = {
        'pass': 'OK',
        'warn': 'есть предупреждения',
        'fail': 'есть ошибки',
    }.get(status, status)
    lines = [
        (
            f'Статус: **{status_label}**; errors={summary.get("errors", 0)}, '
            f'warnings={summary.get("warnings", 0)}, info={summary.get("info", 0)}.'
        ),
        (
            f'Правила: clearance={_fmt(rules.get("clearance_mm"))} мм; '
            f'min trace={_fmt(rules.get("min_trace_width_mm"))} мм; '
            f'copper={_fmt(rules.get("copper_oz"))} oz; '
            f'temp rise={_fmt(rules.get("temp_rise_c"))} °C.'
        ),
    ]
    issues = [issue for issue in (drc.get('issues') or []) if isinstance(issue, dict)]
    if issues:
        lines.extend(['', '| Severity | Code | Finding |', '|---|---|---|'])
        for issue in issues[:10]:
            severity = _SEVERITY_LABEL.get(issue.get('severity'), issue.get('severity') or 'info')
            title = issue.get('title') or issue.get('code') or 'DRC'
            detail = issue.get('detail') or ''
            finding = f'{title}: {detail}' if detail else title
            lines.append(
                f'| {_md_cell(severity)} | {_md_cell(issue.get("code"))} | {_md_cell(finding)} |'
            )
        if len(issues) > 10:
            lines.append(f'Показано 10 из {len(issues)} DRC-сообщений.')
    else:
        lines.append('Критичных нарушений базового PCB DRC не найдено.')
    return ('PCB DRC', lines)


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


def _run_field(run, key: str, default=None):
    if isinstance(run, dict):
        return run.get(key, default)
    return getattr(run, key, default)


def _run_result(run) -> dict:
    for key in ('result_data', 'result', 'output'):
        value = _run_field(run, key)
        if isinstance(value, dict):
            return value
    return {}


def _simulation_runs_section(simulation_runs: list) -> tuple[str, list[str]] | None:
    rows = []
    for run in simulation_runs or []:
        analysis = _run_field(run, 'analysis_type') or _run_field(run, 'type') or 'unknown'
        engine = _run_field(run, 'engine') or 'local'
        status = _run_field(run, 'status') or 'success'
        elapsed = _run_field(run, 'elapsed_ms')
        created = _run_field(run, 'created_at') or _run_field(run, 'created')
        if hasattr(created, 'strftime'):
            created = created.strftime('%Y-%m-%d %H:%M')
        elapsed_text = f'{_fmt(elapsed, digits=3)} мс' if elapsed not in (None, '') else '—'
        rows.append(f'| {analysis} | {engine} | {status} | {elapsed_text} | {created or "—"} |')
    if not rows:
        return None
    return (
        'Запуски симуляции',
        ['| Анализ | Движок | Статус | Время | Дата |', '|---|---|---|---|---|'] + rows,
    )


def _thin_values(values: list[float], limit: int = 36) -> list[float]:
    if len(values) <= limit:
        return values
    if limit <= 1:
        return values[:1]
    last = len(values) - 1
    return [values[round(index * last / (limit - 1))] for index in range(limit)]


def _sparkline(values: list[float]) -> str:
    values = _thin_values([value for value in values if value is not None])
    if not values:
        return ''
    lo = min(values)
    hi = max(values)
    if hi == lo:
        return _SPARKLINE[0] * len(values)
    scale = len(_SPARKLINE) - 1
    return ''.join(_SPARKLINE[round((value - lo) / (hi - lo) * scale)] for value in values)


def _waveform_rows(result: dict) -> list[str]:
    rows = []
    waveforms = result.get('waveforms')
    if not isinstance(waveforms, list):
        waveforms = []
    for wave in waveforms[:5]:
        if not isinstance(wave, dict):
            continue
        points = wave.get('points') or []
        y_values = []
        x_values = []
        for point in points:
            if isinstance(point, dict):
                y = _float_or_none(point.get('y'))
                x = _float_or_none(point.get('x'))
            elif isinstance(point, (list, tuple)) and len(point) >= 2:
                x = _float_or_none(point[0])
                y = _float_or_none(point[1])
            else:
                x = None
                y = _float_or_none(point)
            if y is not None:
                y_values.append(y)
            if x is not None:
                x_values.append(x)
        name = wave.get('name') or wave.get('node') or 'trace'
        unit = wave.get('unit') or ''
        if y_values:
            preview = _sparkline(y_values)
            x_range = f', x={_fmt(min(x_values))}..{_fmt(max(x_values))}' if x_values else ''
            rows.append(
                f'- {name}: {len(y_values)} точек{x_range}, '
                f'y={_fmt(min(y_values))}..{_fmt(max(y_values))} {unit}; `{preview}`'.rstrip()
            )
        else:
            rows.append(f'- {name}: точки не сохранены')

    nodes = result.get('nodes')
    if isinstance(nodes, list) and len(rows) < 5:
        for node in nodes[: 5 - len(rows)]:
            if not isinstance(node, dict):
                continue
            samples = [_float_or_none(value) for value in node.get('samples') or []]
            samples = [value for value in samples if value is not None]
            if not samples:
                continue
            name = node.get('id') or node.get('name') or 'node'
            unit = node.get('unit') or ''
            rows.append(
                f'- {name}: {len(samples)} samples, '
                f'{_fmt(min(samples))}..{_fmt(max(samples))} {unit}; `{_sparkline(samples)}`'.rstrip()
            )
    return rows


def _metric_lines(metrics: dict) -> list[str]:
    rows = []
    for key, value in list((metrics or {}).items())[:10]:
        if isinstance(value, (dict, list)):
            continue
        rows.append(f'{key}={_fmt(value)}')
    return rows


def _artifact_lines(artifacts: list) -> list[str]:
    rows = []
    for artifact in artifacts[:5] if isinstance(artifacts, list) else []:
        if isinstance(artifact, dict):
            name = artifact.get('name') or artifact.get('filename') or artifact.get('type') or 'artifact'
            location = artifact.get('url') or artifact.get('path') or artifact.get('href') or ''
            rows.append(f'- {name}' + (f': {location}' if location else ''))
        else:
            rows.append(f'- {artifact}')
    return rows


def _simulation_outputs_section(simulation_runs: list) -> tuple[str, list[str]] | None:
    lines = []
    for run in simulation_runs or []:
        result = _run_result(run)
        summary = _run_field(run, 'result_summary') or {}
        if not isinstance(summary, dict):
            summary = {}
        metrics = result.get('metrics') if isinstance(result.get('metrics'), dict) else summary.get('metrics')
        wave_rows = _waveform_rows(result) if result else []
        artifact_rows = _artifact_lines(result.get('artifacts') or _run_field(run, 'artifacts') or [])
        metric_rows = _metric_lines(metrics if isinstance(metrics, dict) else {})
        if not (wave_rows or metric_rows or artifact_rows):
            continue
        analysis = _run_field(run, 'analysis_type') or _run_field(run, 'type') or 'unknown'
        engine = _run_field(run, 'engine') or result.get('engine') or 'local'
        lines.append(f'**{analysis} / {engine}**')
        if metric_rows:
            lines.append('- metrics: ' + ', '.join(metric_rows))
        lines.extend(wave_rows)
        if artifact_rows:
            lines.append('- artifacts:')
            lines.extend([f'  {row}' for row in artifact_rows])
        lines.append('')
    if not lines:
        return None
    return ('Осциллограммы и артефакты симуляции', lines)


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


def _source_refs(finding: dict) -> list:
    refs = []
    for key in ('source_references', 'sources', 'references'):
        value = finding.get(key)
        if isinstance(value, dict):
            refs.append(value)
        elif isinstance(value, list):
            refs.extend(value)
    return refs


def _sources_section(findings: list) -> tuple[str, list[str]] | None:
    rows = []
    seen = set()
    for finding in findings or []:
        if not isinstance(finding, dict):
            continue
        rule_id = finding.get('rule_id') or finding.get('code') or ''
        for source in _source_refs(finding):
            if isinstance(source, dict):
                title = source.get('title') or source.get('name') or source.get('id') or 'source'
                url = source.get('url') or source.get('href') or ''
                line = f'- {rule_id}: {title}' if rule_id else f'- {title}'
                if url:
                    line += f' — {url}'
            else:
                line = f'- {rule_id}: {source}' if rule_id else f'- {source}'
            if line in seen:
                continue
            seen.add(line)
            rows.append(line)
    if not rows:
        return None
    return ('Источники проверки', rows[:30])


def build_protocol(
    title: str = 'Протокол проектирования',
    scheme_data: dict | None = None,
    *,
    include_dc: bool = True,
    simulation_runs: list | None = None,
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
        sec = _bom_section(scheme_data)
        if sec:
            sections.append(sec)
        sec = _pcb_drc_section(scheme_data)
        if sec:
            sections.append(sec)
        if include_dc:
            sec = _dc_section(scheme_data)
            if sec:
                sections.append(sec)
    sec = _simulation_runs_section(simulation_runs or [])
    if sec:
        sections.append(sec)
    sec = _simulation_outputs_section(simulation_runs or [])
    if sec:
        sections.append(sec)
    for builder, arg in (
        (_measurements_section, measurements),
        (_lab_section, lab_calcs),
        (_findings_section, findings),
        (_sources_section, findings),
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
