"""Markdown-протокол инженерной проверки схемы.

Собирает уже посчитанный review (``_review_to_dict`` / ``build_design_review``)
в читаемый .md-документ: метаданные, итоговый score, метрики, измерения,
найденные проблемы, рекомендации и учебные подсказки. Переиспользует данные
review без повторных вычислений, поэтому дёшев и совпадает с HTML/PDF-отчётом.

Зачем .md: его можно вставить в диплом (приложение «Результаты проверок»),
открыть в любом редакторе, отрендерить в PDF/HTML или показать на защите как
автоматически собранный протокол.
"""

from __future__ import annotations

from typing import Any


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value in (None, '', {}):
        return []
    return [value]


def _finding_line(item: Any) -> str:
    """Одна строка finding'а: принимает str или dict (rule findings)."""
    if isinstance(item, str):
        return f"- {item}"
    if not isinstance(item, dict):
        return f"- {item}"
    title = item.get('title') or item.get('message') or item.get('text') or item.get('rule_id') or 'finding'
    severity = item.get('severity_label') or item.get('severity') or item.get('level')
    rule_id = item.get('rule_id')
    detail = item.get('message') if item.get('title') else None
    recommendation = item.get('recommendation') or item.get('fix') or item.get('advice')
    prefix = f"`{rule_id}` " if rule_id else ''
    head = f"- {prefix}**{title}**"
    if severity:
        head += f" _({severity})_"
    if detail and detail != title:
        head += f" — {detail}"
    if recommendation:
        head += f"\n  - Рекомендация: {recommendation}"
    return head


def _section(title: str, items: list, *, empty: str | None = None) -> list[str]:
    items = _as_list(items)
    if not items:
        return [] if empty is None else [f"### {title}", '', f"_{empty}_", '']
    out = [f"### {title}", '']
    out.extend(_finding_line(it) for it in items)
    out.append('')
    return out


def render_review_markdown(review_display: dict, project: Any = None) -> str:
    """review_display = результат _review_to_dict(review). Возвращает .md-строку."""
    rd = review_display or {}
    name = getattr(project, 'name', None) or rd.get('project_name') or f"проект #{rd.get('project_id', '?')}"
    created = rd.get('created') or ''
    score = rd.get('score')
    status = rd.get('status_label') or rd.get('status') or ''

    errors = _as_list(rd.get('errors'))
    warnings = _as_list(rd.get('warnings'))
    faults = _as_list(rd.get('faults'))
    recommendations = _as_list(rd.get('recommendations'))
    expert = _as_list(rd.get('expert_findings'))
    learning = _as_list(rd.get('learning_suggestions'))
    metric_rows = _as_list(rd.get('metric_rows'))
    measurement_rows = _as_list(rd.get('measurement_rows'))

    L: list[str] = []
    L.append('# Протокол инженерной проверки схемы')
    L.append('')
    L.append(f"**Проект:** {name}  ")
    if created:
        L.append(f"**Дата:** {created}  ")
    if score is not None:
        L.append(f"**Итоговая оценка:** {score}/100 — {status}")
    else:
        L.append(f"**Статус:** {status}")
    L.append('')

    # 1. Сводка
    L.append('## 1. Сводка')
    L.append('')
    L.append(f"- Ошибок: {len(errors)}")
    L.append(f"- Предупреждений: {len(warnings)}")
    L.append(f"- Неисправностей: {len(faults)}")
    L.append(f"- Экспертных замечаний: {len(expert)}")
    summary = rd.get('summary')
    if isinstance(summary, str) and summary.strip():
        L.append('')
        L.append(summary.strip())
    L.append('')

    # 2. Параметры и метрики
    if metric_rows:
        L.append('## 2. Параметры и метрики')
        L.append('')
        L.append('| Параметр | Значение |')
        L.append('|---|---|')
        for r in metric_rows:
            if isinstance(r, dict):
                L.append(f"| {r.get('label') or r.get('key', '')} | {r.get('value', '')} |")
        L.append('')

    # 3. Измерения
    if measurement_rows:
        L.append('## 3. Измерения')
        L.append('')
        L.append('| Метрика | Значение | Ожидаемо | Статус |')
        L.append('|---|---|---|---|')
        for r in measurement_rows:
            if isinstance(r, dict):
                val = r.get('value', '')
                unit = r.get('unit', '') or ''
                vu = f"{val} {unit}".strip()
                L.append(f"| {r.get('label') or r.get('metric', '')} | {vu} | {r.get('expected', '') or ''} | {r.get('status', '') or ''} |")
        L.append('')

    # 4. Найденные проблемы
    L.append('## 4. Найденные проблемы')
    L.append('')
    L.extend(_section('Ошибки', errors, empty='ошибок не обнаружено'))
    L.extend(_section('Предупреждения', warnings, empty='предупреждений нет'))
    L.extend(_section('Неисправности', faults, empty='неисправностей не выявлено'))
    if expert:
        L.extend(_section('Экспертная система', expert))

    # 5. Рекомендации
    if recommendations:
        L.append('## 5. Рекомендации')
        L.append('')
        L.extend(_finding_line(it) for it in recommendations)
        L.append('')

    # 6. Обучение по результатам
    if learning:
        L.append('## 6. Обучение по результатам проверки')
        L.append('')
        for it in learning:
            if isinstance(it, dict):
                title = it.get('title') or it.get('name') or it.get('lesson') or 'урок'
                L.append(f"- {title}")
            else:
                L.append(f"- {it}")
        L.append('')

    L.append('---')
    L.append('Протокол сформирован автоматически системой DOLG на основе инженерной проверки схемы.')
    L.append('')
    return '\n'.join(L)
