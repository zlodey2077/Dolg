"""AI Tool-use whitelist: actions, которые self-hosted/Pro AI может предлагать
для авто-выполнения через клик пользователя (frontend executor).

Каждый tool описан декларативно:
- ``name``: уникальный ID (snake_case, namespace через точку: `tool.simulation.run_dc`)
- ``label``: короткая UI-надпись для кнопки
- ``description``: tooltip-описание, что произойдёт
- ``icon``: emoji
- ``params_schema``: список допустимых параметров (валидируется frontend'ом)
- ``requires_confirm``: True для destructive (delete, clear) — UI запрашивает Да/Нет
- ``destructive``: True если меняет/удаляет state (для visual warning)
- ``modules``: на каких страницах действует (``simulation``, ``cad``, ``projects``)

Frontend проверяет whitelist (имя tool'а ДОЛЖНО быть в этом dict) перед
выполнением — это защита от prompt-injection в backend AI.
"""

from __future__ import annotations

# Каноничный набор tool'ов. Расширяется по мере появления новых JS-функций.
AI_TOOLS: dict[str, dict] = {
    # ---- Симуляция ----
    'simulation.run_dc': {
        'label': 'Запустить DC',
        'description': 'Найти рабочую точку схемы (DC operating point). Покажет напряжения узлов и токи ветвей.',
        'icon': '▶️',
        'params_schema': [],
        'requires_confirm': False,
        'destructive': False,
        'modules': ['simulation'],
    },
    'simulation.run_tran': {
        'label': 'Запустить TRAN',
        'description': 'Переходный процесс — симуляция во временной области. Покажет графики V(t)/I(t).',
        'icon': '📈',
        'params_schema': ['duration_ms'],
        'requires_confirm': False,
        'destructive': False,
        'modules': ['simulation'],
    },
    'simulation.run_ac': {
        'label': 'Запустить AC',
        'description': 'АЧХ/ФЧХ — частотный анализ с декадной разверткой. Покажет Bode plot.',
        'icon': '📊',
        'params_schema': ['f_start', 'f_stop'],
        'requires_confirm': False,
        'destructive': False,
        'modules': ['simulation'],
    },
    'simulation.stop': {
        'label': 'Остановить',
        'description': 'Прервать текущую симуляцию.',
        'icon': '⏹️',
        'params_schema': [],
        'requires_confirm': False,
        'destructive': False,
        'modules': ['simulation'],
    },
    # ---- Редактирование схемы ----
    'scheme.add_component': {
        'label': 'Добавить компонент',
        'description': 'Добавить новый элемент в схему. Тип передаётся через params.type.',
        'icon': '➕',
        'params_schema': [
            'type'
        ],  # 'resistor' | 'capacitor' | 'ground' | 'battery' | 'led' | 'diode' | 'transistor' | 'switch' | 'inductor'
        'requires_confirm': False,
        'destructive': False,
        'modules': ['simulation', 'cad'],
    },
    'scheme.delete_selected': {
        'label': 'Удалить выбранное',
        'description': 'Удалить выделенные компоненты или провод.',
        'icon': '🗑',
        'params_schema': [],
        'requires_confirm': True,
        'destructive': True,
        'modules': ['simulation', 'cad'],
    },
    'scheme.clear_all': {
        'label': 'Очистить схему',
        'description': 'Очистить всю схему. ВНИМАНИЕ: вся работа будет потеряна (можно вернуть Ctrl+Z).',
        'icon': '🧹',
        'params_schema': [],
        'requires_confirm': True,
        'destructive': True,
        'modules': ['simulation', 'cad'],
    },
    'scheme.undo': {
        'label': 'Отменить',
        'description': 'Откатить последнее действие (Ctrl+Z).',
        'icon': '↶',
        'params_schema': [],
        'requires_confirm': False,
        'destructive': False,
        'modules': ['simulation', 'cad'],
    },
    'scheme.rotate_selected': {
        'label': 'Повернуть',
        'description': 'Повернуть выделенный компонент на 90° (R).',
        'icon': '🔄',
        'params_schema': [],
        'requires_confirm': False,
        'destructive': False,
        'modules': ['simulation', 'cad'],
    },
    # ---- View / overlays ----
    'view.show_3d': {
        'label': 'Открыть 3D',
        'description': 'Открыть 3D-просмотр платы (Three.js).',
        'icon': '🎬',
        'params_schema': [],
        'requires_confirm': False,
        'destructive': False,
        'modules': ['simulation', 'cad'],
    },
    'view.show_lab': {
        'label': 'Лаборатория',
        'description': 'Открыть виртуальную лабораторию: осциллограф, мультиметр, генератор сигналов.',
        'icon': '🔬',
        'params_schema': [],
        'requires_confirm': False,
        'destructive': False,
        'modules': ['simulation'],
    },
    'view.toggle_thermal_3d': {
        'label': 'Тепловая карта',
        'description': 'Включить тепловую карту в 3D-просмотре. Требует симуляции DC или TRAN.',
        'icon': '🌡',
        'params_schema': [],
        'requires_confirm': False,
        'destructive': False,
        'modules': ['simulation'],
    },
    'view.fit': {
        'label': 'Вписать',
        'description': 'Подогнать масштаб канвы под содержимое схемы.',
        'icon': '⤢',
        'params_schema': [],
        'requires_confirm': False,
        'destructive': False,
        'modules': ['simulation', 'cad'],
    },
    # ---- Экспорт ----
    'export.png': {
        'label': 'PNG',
        'description': 'Сохранить снимок схемы как PNG.',
        'icon': '📷',
        'params_schema': [],
        'requires_confirm': False,
        'destructive': False,
        'modules': ['simulation', 'cad'],
    },
    'export.bom': {
        'label': 'BOM CSV',
        'description': 'Экспорт списка компонентов (BOM) в CSV.',
        'icon': '📋',
        'params_schema': [],
        'requires_confirm': False,
        'destructive': False,
        'modules': ['simulation'],
    },
    'export.netlist': {
        'label': 'SPICE-netlist',
        'description': 'Экспорт SPICE-netlist (.cir) для LTspice/ngspice.',
        'icon': '📄',
        'params_schema': [],
        'requires_confirm': False,
        'destructive': False,
        'modules': ['simulation'],
    },
    'export.glb': {
        'label': 'GLB модель',
        'description': 'Скачать 3D-модель в формате glTF 2.0. Открывается в Blender/Windows 3D Viewer.',
        'icon': '🧊',
        'params_schema': [],
        'requires_confirm': False,
        'destructive': False,
        'modules': ['simulation', 'cad'],
    },
    # ---- Pipeline / analysis ----
    'pipeline.run_review': {
        'label': 'Engineering Review',
        'description': 'Полный анализ проекта: DRC, BOM, derating, fault library, expert rules.',
        'icon': '🧠',
        'params_schema': [],
        'requires_confirm': False,
        'destructive': False,
        'modules': ['simulation', 'projects'],
    },
    'pipeline.run_drc': {
        'label': 'DRC проверка',
        'description': 'Design Rule Check — найти ошибки и предупреждения в схеме.',
        'icon': '✓',
        'params_schema': [],
        'requires_confirm': False,
        'destructive': False,
        'modules': ['simulation', 'cad'],
    },
}


def list_tools(module: str | None = None) -> list[dict]:
    """Return whitelist tools available for given module (or all).

    Used by rule_ai to know which tools it CAN propose, and by frontend
    to validate incoming action names.
    """
    out = []
    for name, spec in AI_TOOLS.items():
        if module and module not in (spec.get('modules') or []):
            continue
        out.append(
            {
                'name': name,
                'label': spec['label'],
                'description': spec['description'],
                'icon': spec['icon'],
                'params_schema': spec.get('params_schema') or [],
                'requires_confirm': spec.get('requires_confirm', False),
                'destructive': spec.get('destructive', False),
                'modules': spec.get('modules') or [],
            }
        )
    return out


def is_tool_allowed(name: str, module: str | None = None) -> bool:
    """Check if tool name is in whitelist and (optionally) available in module."""
    spec = AI_TOOLS.get(name)
    if not spec:
        return False
    if module is not None and module not in (spec.get('modules') or []):
        return False
    return True


def build_tool_action(
    name: str, params: dict | None = None, *, override_label: str | None = None
) -> dict | None:
    """Build a tool-action dict for inclusion in quick_actions response.

    Returns None if tool is not whitelisted — caller can skip silently.
    The action format mirrors prompt-actions but with ``kind='tool'`` so
    frontend knows to dispatch through executor (not re-send prompt).
    """
    spec = AI_TOOLS.get(name)
    if not spec:
        return None
    return {
        'kind': 'tool',
        'tool': name,
        'label': override_label or spec['label'],
        'icon': spec['icon'],
        'description': spec['description'],
        'params': params or {},
        'requires_confirm': spec.get('requires_confirm', False),
        'destructive': spec.get('destructive', False),
    }
