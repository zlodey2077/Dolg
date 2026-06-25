"""Catalog of server-side engines that can be routed from DOLG.

The first useful step toward "one engine per task" is a stable catalog:
the UI can explain the matrix, tests can protect the IDs, and future Docker
adapters can target the same records instead of hard-coding names in HTML.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

ENGINE_CATEGORIES = [
    {'key': 'core', 'label': 'Ядро DOLG'},
    {'key': 'spice', 'label': 'SPICE/схемы'},
    {'key': 'modeling', 'label': 'Физические модели'},
    {'key': 'eda', 'label': 'EDA/FPGA'},
    {'key': 'embedded', 'label': 'Встраиваемые'},
    {'key': 'lab', 'label': 'Измерения'},
    {'key': 'radio', 'label': 'Радио/SDR'},
    {'key': 'cv', 'label': 'Computer vision'},
    {'key': 'ops', 'label': 'DevOps'},
]

ENGINE_ROUTER_PROFILE = {
    'primary_engine': 'dolg-engine-router',
    'primary_external_engine': 'xyce',
    'interactive_engine': 'dolg-ngspice-wasm',
    'python_bridge': 'pyspice',
    'strategy': (
        'DOLG Engine Router принимает server-side jobs, локально делегирует в NumPy MNA, '
        'а для тяжёлых SPICE-задач готовит Xyce/PySpice/GnuCap workers.'
    ),
    'contract': {
        'submit': 'POST /engines/{engine_id}/jobs',
        'status': 'GET /engines/jobs/{job_id}',
        'result': 'GET /engines/jobs/{job_id}/result',
        'payload': ['netlist', 'analysis', 'options', 'artifacts'],
    },
    'docker_services': [
        'engine-gateway',
        'xyce-worker',
        'pyspice-worker',
        'gnucap-worker',
        'openmodelica-worker',
        'sigrok-agent',
        'artifact-store',
    ],
    'kubernetes': [
        'engine-gateway Deployment + Service',
        'worker Deployments with resource limits',
        'Job/CronJob for long simulations',
        'Redis/Celery queue or Kubernetes Jobs for async runs',
        'PersistentVolume/S3-compatible storage for raw traces and reports',
    ],
    'fallback_order': [
        'dolg-engine-router',
        'xyce',
        'pyspice',
        'gnucap',
        'dolg-ngspice-wasm',
        'dolg-numpy-mna',
    ],
    'local_ai_links': {
        'command_planner': 'text -> safe EngineJob JSON payload',
        'engine_selector': 'scheme + PyTorch/rule hints -> ranked engine list',
        'result_explainer': 'EngineJob result -> local_ai notes + neural_hint',
        'execution_policy': 'never execute arbitrary shell; queue validated engine jobs only',
    },
}

SERVER_ENGINE_CATALOG = [
    {
        'id': 'dolg-engine-router',
        'name': 'DOLG Engine Router',
        'category': 'core',
        'status': 'connected',
        'status_label': 'серверный MVP',
        'task': 'Единая server-side точка входа для EngineJob и будущих Docker/Kubernetes workers.',
        'fit': 'Маршрутизация DC/AC/transient/tolerance задач, единый result contract, retries, stale и audit.',
        'integration': 'Django worker сегодня делегирует в NumPy MNA; позже выбирает Xyce/PySpice/GnuCap/GNN.',
        'license': 'internal',
        'source_url': '',
        'endpoint': '/api/sim/jobs/',
        'outputs': ['DOLG engine result v1', 'job audit', 'worker heartbeat'],
        'tags': ['electronics', 'spice', 'mna', 'server-engine', 'router', 'docker', 'kubernetes'],
        'priority': 12,
    },
    {
        'id': 'dolg-ngspice-wasm',
        'name': 'ngspice.wasm',
        'category': 'core',
        'status': 'connected',
        'status_label': 'подключено',
        'task': 'Быстрая SPICE-симуляция прямо в редакторе.',
        'fit': 'DC, AC и transient-прогоны учебных и дипломных схем без очереди на сервер.',
        'integration': 'WASM worker в браузере, результаты сохраняются через SimulationRun.',
        'license': 'open-source',
        'source_url': 'https://ngspice.sourceforge.io/',
        'endpoint': 'client://simulation/ngspice-worker',
        'outputs': ['графики', 'узловые напряжения', 'netlist'],
        'tags': ['electronics', 'spice', 'dc', 'ac', 'transient'],
        'priority': 10,
    },
    {
        'id': 'dolg-numpy-mna',
        'name': 'NumPy MNA',
        'category': 'core',
        'status': 'connected',
        'status_label': 'подключено',
        'task': 'Серверный fallback-решатель и Monte Carlo для простых цепей.',
        'fit': 'Резистивные и RC-схемы, worst-case, допуски компонентов и быстрые проверки API.',
        'integration': 'Django service Dolg_APP.services.monte_carlo без внешнего процесса.',
        'license': 'internal',
        'source_url': '',
        'endpoint': '/api/sim/monte_carlo/',
        'outputs': ['статистика узлов', 'worst-case', 'paranoia-отчёт'],
        'tags': ['electronics', 'mna', 'monte-carlo', 'dc', 'tolerance'],
        'priority': 9,
    },
    {
        'id': 'dolg-scikit-rf',
        'name': 'scikit-rf',
        'category': 'core',
        'status': 'connected',
        'status_label': 'подключено',
        'task': 'RF-анализ фильтров и S-параметров.',
        'fit': 'RC/LC-фильтры, S11/S21, частота среза и проверка полосы пропускания.',
        'integration': 'Django endpoint с численным расчётом и JSON-графиками.',
        'license': 'open-source',
        'source_url': 'https://scikit-rf.org/',
        'endpoint': '/api/sim/rf_analysis/',
        'outputs': ['S21/S11', '−3 дБ', 'частотные точки'],
        'tags': ['electronics', 'rf', 'radio', 'filter', 's-parameters'],
        'priority': 8,
    },
    {
        'id': 'xyce',
        'name': 'Xyce',
        'category': 'spice',
        'status': 'primary-candidate',
        'status_label': 'основной кандидат',
        'task': 'Основной серверный SPICE-движок для тяжёлых и пакетных задач.',
        'fit': 'Большие netlist, transient/AC/DC, параметрические прогоны и будущие очереди Kubernetes.',
        'integration': 'Docker worker: DOLG netlist -> xyce CLI -> raw/CSV parser -> единый SimulationRun JSON.',
        'license': 'open-source',
        'source_url': 'https://xyce.sandia.gov/',
        'endpoint': '/engines/xyce/run',
        'outputs': ['raw/CSV curves', 'solver log', 'convergence report'],
        'tags': ['electronics', 'spice', 'dc', 'ac', 'transient', 'docker', 'kubernetes'],
        'priority': 11,
    },
    {
        'id': 'pyspice',
        'name': 'PySpice',
        'category': 'spice',
        'status': 'adapter-ready',
        'status_label': 'адаптер',
        'task': 'Python-обвязка вокруг SPICE-движка для интеграции с Django.',
        'fit': 'Быстрые server-side прототипы, генерация netlist, анализ результатов в Python и fallback к ngspice.',
        'integration': 'Python worker: схема -> PySpice circuit -> ngspice shared/lib -> JSON-графики.',
        'license': 'open-source',
        'source_url': 'https://pyspice.fabrice-salvaire.fr/',
        'endpoint': '/engines/pyspice/run',
        'outputs': ['Python result objects', 'JSON traces', 'ngspice log'],
        'tags': ['electronics', 'spice', 'python', 'ngspice', 'prototype'],
        'priority': 9,
    },
    {
        'id': 'atuin',
        'name': 'Atuin',
        'category': 'ops',
        'status': 'adapter-ready',
        'status_label': 'адаптер',
        'task': 'Воспроизводимая история CLI-команд для стенда и защиты.',
        'fit': 'Фиксация команд deploy, Docker, миграций, smoke-тестов и повторяемых демо-сценариев.',
        'integration': 'Sidecar-сервис: CLI пишет историю, REST-адаптер отдаёт выбранные runbook-команды.',
        'license': 'open-source',
        'source_url': 'https://github.com/atuinsh/atuin',
        'endpoint': '/engines/atuin/history/search',
        'outputs': ['команды', 'теги runbook', 'история стенда'],
        'tags': ['ops', 'cli', 'history', 'runbook', 'demo'],
        'priority': 4,
    },
    {
        'id': 'dockly',
        'name': 'Dockly',
        'category': 'ops',
        'status': 'adapter-ready',
        'status_label': 'адаптер',
        'task': 'Терминальная панель контроля Docker-контейнеров.',
        'fit': 'Мониторинг контейнеров движков, логов, рестартов и ресурсов во время прогона.',
        'integration': 'Отдельный TUI для администратора плюс лёгкий Docker Engine REST proxy для DOLG.',
        'license': 'open-source',
        'source_url': 'https://github.com/lirantal/dockly',
        'endpoint': '/engines/docker/status',
        'outputs': ['логи', 'статусы контейнеров', 'ресурсы'],
        'tags': ['ops', 'docker', 'containers', 'logs'],
        'priority': 5,
    },
    {
        'id': 'supervision',
        'name': 'Supervision',
        'category': 'cv',
        'status': 'prototype',
        'status_label': 'прототип',
        'task': 'Постобработка computer-vision результатов.',
        'fit': 'Аннотации плат, детекция компонентов на фото, визуализация масок и треков.',
        'integration': 'Python worker: image upload -> model result -> Supervision annotators -> PNG/JSON.',
        'license': 'open-source',
        'source_url': 'https://github.com/roboflow/supervision',
        'endpoint': '/engines/cv/supervision/annotate',
        'outputs': ['аннотированное изображение', 'detections JSON', 'метрики'],
        'tags': ['cv', 'vision', 'annotation', 'yolo', 'opencv', 'pcb-photo'],
        'priority': 6,
    },
    {
        'id': 'gnucap',
        'name': 'GnuCap',
        'category': 'spice',
        'status': 'adapter-ready',
        'status_label': 'адаптер',
        'task': 'Свободная SPICE-совместимая симуляция смешанных схем.',
        'fit': 'Аналоговая обвязка плюс цифровая логика или микроконтроллерные модели.',
        'integration': 'Docker REST: netlist in, batch run, stdout/raw curves out; хорошо подходит для Raspberry Pi demo.',
        'license': 'GPL-compatible',
        'source_url': 'https://gnucap.org/',
        'endpoint': '/engines/gnucap/run',
        'outputs': ['raw curves', 'stdout', 'mixed-signal report'],
        'tags': ['electronics', 'spice', 'mixed-signal', 'verilog', 'microcontroller'],
        'priority': 9,
    },
    {
        'id': 'tina-ti',
        'name': 'TINA-TI',
        'category': 'spice',
        'status': 'license-gated',
        'status_label': 'лицензия',
        'task': 'Симуляция TI-микросхем и импульсных источников.',
        'fit': 'DC/DC, операционные усилители и reference-дизайны на популярных чипах Texas Instruments.',
        'integration': 'Headless VM/container wrapper с очередью задач; требует отдельного лицензионного контура.',
        'license': 'registration-required',
        'source_url': 'https://www.ti.com/tool/TINA-TI',
        'endpoint': '/engines/tina-ti/run',
        'outputs': ['осциллограммы', 'BOM по TI-чипам', 'ошибки модели'],
        'tags': ['electronics', 'spice', 'power', 'opamp', 'ti', 'smps'],
        'priority': 7,
    },
    {
        'id': 'maplesim',
        'name': 'MapleSim',
        'category': 'modeling',
        'status': 'license-gated',
        'status_label': 'лицензия',
        'task': 'Символьные уравнения и аналитические модели.',
        'fit': 'Синтез фильтров, вывод формул, мультидисциплинарные модели с понятными уравнениями.',
        'integration': 'Container/VM worker: модель -> symbolic export -> Markdown/LaTeX блок для отчёта.',
        'license': 'commercial/student',
        'source_url': 'https://www.maplesoft.com/products/maplesim/',
        'endpoint': '/engines/maplesim/derive',
        'outputs': ['уравнения', 'LaTeX', 'параметрическая модель'],
        'tags': ['modeling', 'symbolic', 'filters', 'equations', 'multiphysics'],
        'priority': 6,
    },
    {
        'id': 'symphony-openroad',
        'name': 'Symphony EDA + OpenROAD',
        'category': 'eda',
        'status': 'research',
        'status_label': 'исследование',
        'task': 'Собственный серверный EDA-конвейер вокруг открытых инструментов.',
        'fit': 'Уникальный дипломный сценарий: REST API для синтеза, размещения, трассировки и отчётов.',
        'integration': 'Docker compose: gateway -> job queue -> OpenROAD worker -> artifacts storage.',
        'license': 'open-source-mixed',
        'source_url': 'https://openroad-flow-scripts.readthedocs.io/',
        'endpoint': '/engines/openroad/flow',
        'outputs': ['DEF/GDS artifacts', 'timing report', 'flow log'],
        'tags': ['eda', 'openroad', 'layout', 'routing', 'custom-engine'],
        'priority': 7,
    },
    {
        'id': 'fritzing',
        'name': 'Fritzing',
        'category': 'eda',
        'status': 'adapter-ready',
        'status_label': 'адаптер',
        'task': 'Наглядные макетки, breadboard и PCB-документация.',
        'fit': 'Учебные схемы, отчётные иллюстрации, связь “схема -> макетка -> плата”.',
        'integration': 'File adapter: Fritzing project export/import, preview renderer, attachments in ProjectReview.',
        'license': 'open-source/commercial-download',
        'source_url': 'https://fritzing.org/',
        'endpoint': '/engines/fritzing/render',
        'outputs': ['breadboard preview', 'PCB preview', 'проектный файл'],
        'tags': ['eda', 'breadboard', 'pcb', 'documentation', 'prototype'],
        'priority': 5,
    },
    {
        'id': 'openmodelica',
        'name': 'OpenModelica',
        'category': 'modeling',
        'status': 'adapter-ready',
        'status_label': 'адаптер',
        'task': 'Симуляция физических систем за пределами чистой электроники.',
        'fit': 'Сервоприводы, насосы, теплообмен, механика и связка Modelica-моделей с электроникой.',
        'integration': 'Docker REST: .mo model -> omc batch -> CSV/plots -> Engineering Review.',
        'license': 'open-source',
        'source_url': 'https://openmodelica.org/',
        'endpoint': '/engines/openmodelica/run',
        'outputs': ['CSV траектории', 'plots', 'model diagnostics'],
        'tags': ['modeling', 'multiphysics', 'thermal', 'mechanics', 'servo', 'pump'],
        'priority': 8,
    },
    {
        'id': 'sigrok',
        'name': 'Sigrok',
        'category': 'lab',
        'status': 'adapter-ready',
        'status_label': 'адаптер',
        'task': 'Захват и декодирование данных с измерительных приборов.',
        'fit': 'Автоматизация тестов с логическими анализаторами, мультиметрами и осциллографами.',
        'integration': 'USB/serial worker рядом с железом; REST отдаёт captured traces и protocol decode.',
        'license': 'open-source',
        'source_url': 'https://sigrok.org/',
        'endpoint': '/engines/sigrok/capture',
        'outputs': ['logic trace', 'protocol decode', 'измерения'],
        'tags': ['lab', 'measurement', 'oscilloscope', 'logic-analyzer', 'hardware-test'],
        'priority': 8,
    },
    {
        'id': 'openfpga',
        'name': 'OpenFPGA',
        'category': 'eda',
        'status': 'research',
        'status_label': 'исследование',
        'task': 'Фреймворк для FPGA-архитектур, синтеза и трассировки.',
        'fit': 'Эксперименты с аппаратным ускорителем, размещением и трассировкой цифровой части.',
        'integration': 'Queue worker: HDL/arch -> OpenFPGA flow -> reports/artifacts.',
        'license': 'open-source',
        'source_url': 'https://github.com/lnis-uofu/OpenFPGA',
        'endpoint': '/engines/openfpga/flow',
        'outputs': ['bitstream artifacts', 'routing report', 'timing'],
        'tags': ['eda', 'fpga', 'hdl', 'routing', 'accelerator'],
        'priority': 6,
    },
    {
        'id': 'riscv-cores',
        'name': 'RISC-V cores',
        'category': 'embedded',
        'status': 'research',
        'status_label': 'исследование',
        'task': 'Открытые ядра VexRiscv, Rocket Chip, Ibex для цифровой части.',
        'fit': 'Встраиваемый контроллер, co-simulation прошивки и аппаратного блока управления схемой.',
        'integration': 'HDL adapter: core config -> synthesis/sim -> firmware hooks in DOLG protocol.',
        'license': 'open-source-mixed',
        'source_url': 'https://github.com/SpinalHDL/VexRiscv',
        'endpoint': '/engines/riscv/sim',
        'outputs': ['Verilog/VHDL', 'simulation log', 'firmware ABI note'],
        'tags': ['embedded', 'risc-v', 'microcontroller', 'hdl', 'firmware'],
        'priority': 6,
    },
    {
        'id': 'openwrt',
        'name': 'OpenWrt',
        'category': 'ops',
        'status': 'prototype',
        'status_label': 'прототип',
        'task': 'Прошивки и веб-интерфейс для сетевого железа.',
        'fit': 'Удалённое управление стендом, Wi-Fi-шлюз, firewall и web UI для лаборатории.',
        'integration': 'Image builder job + config templates; результаты прикладываются к проекту.',
        'license': 'open-source',
        'source_url': 'https://openwrt.org/',
        'endpoint': '/engines/openwrt/build',
        'outputs': ['firmware image', 'package manifest', 'network config'],
        'tags': ['ops', 'embedded', 'network', 'wifi', 'firmware'],
        'priority': 4,
    },
    {
        'id': 'gnuradio',
        'name': 'GNU Radio',
        'category': 'radio',
        'status': 'adapter-ready',
        'status_label': 'адаптер',
        'task': 'Построение SDR-конвейеров и обработка радиосигналов.',
        'fit': 'Приём, фильтрация, демодуляция, анализ спектра и связь с RF-разделом DOLG.',
        'integration': 'Headless flowgraph runner: .grc/.py -> samples/spectrum -> JSON/PNG.',
        'license': 'open-source',
        'source_url': 'https://www.gnuradio.org/',
        'endpoint': '/engines/gnuradio/run',
        'outputs': ['spectrum PNG', 'samples', 'flowgraph log'],
        'tags': ['radio', 'rf', 'sdr', 'spectrum', 'signal-processing'],
        'priority': 8,
    },
    {
        'id': 'zephyr',
        'name': 'Zephyr RTOS',
        'category': 'embedded',
        'status': 'adapter-ready',
        'status_label': 'адаптер',
        'task': 'RTOS-основание для прошивок встраиваемых устройств.',
        'fit': 'Сенсоры, периферия, real-time задачи, сборка firmware под конкретную плату.',
        'integration': 'West build worker: board + overlay + app -> artifacts and flash instructions.',
        'license': 'open-source',
        'source_url': 'https://zephyrproject.org/',
        'endpoint': '/engines/zephyr/build',
        'outputs': ['firmware binary', 'build log', 'device tree report'],
        'tags': ['embedded', 'rtos', 'firmware', 'sensor', 'microcontroller'],
        'priority': 7,
    },
    {
        'id': 'openscale',
        'name': 'OpenScale',
        'category': 'lab',
        'status': 'prototype',
        'status_label': 'прототип',
        'task': 'Калибровка тензодатчиков и весовых измерений.',
        'fit': 'Проекты с HX711, весовыми датчиками, лабораторными калибровками и отчётами.',
        'integration': 'Microservice: raw samples -> calibration -> stable weight data for protocol.',
        'license': 'open-source',
        'source_url': 'https://github.com/sowbug/openscale',
        'endpoint': '/engines/openscale/calibrate',
        'outputs': ['calibration curve', 'weight samples', 'stability report'],
        'tags': ['lab', 'sensor', 'load-cell', 'weight', 'calibration'],
        'priority': 5,
    },
]


def list_server_engines(category: str | None = None) -> list[dict[str, Any]]:
    """Return catalog records, optionally filtered by category."""
    engines = deepcopy(SERVER_ENGINE_CATALOG)
    if category:
        engines = [engine for engine in engines if engine.get('category') == category]
    return engines


def get_server_engine(engine_id: str | None) -> dict[str, Any] | None:
    """Return one catalog record by id."""
    if not engine_id:
        return None
    needle = str(engine_id).strip().lower()
    for engine in SERVER_ENGINE_CATALOG:
        if engine.get('id') == needle:
            return deepcopy(engine)
    return None


def server_engine_ids() -> set[str]:
    """Stable id set for request validation and tests."""
    return {str(engine['id']) for engine in SERVER_ENGINE_CATALOG}


def summarize_engines(engines: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Small aggregate used by the UI header and API clients."""
    engines = engines if engines is not None else SERVER_ENGINE_CATALOG
    by_status: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for engine in engines:
        status = str(engine.get('status') or 'unknown')
        category = str(engine.get('category') or 'other')
        by_status[status] = by_status.get(status, 0) + 1
        by_category[category] = by_category.get(category, 0) + 1
    return {
        'total': len(engines),
        'by_status': by_status,
        'by_category': by_category,
        'docker_rest_ready': sum(
            1
            for engine in engines
            if engine.get('status') in {'adapter-ready', 'connected', 'primary-candidate'}
        ),
        'primary_candidate': next(
            (engine['id'] for engine in engines if engine.get('status') == 'primary-candidate'),
            ENGINE_ROUTER_PROFILE['primary_engine'],
        ),
    }


def server_engine_payload(category: str | None = None) -> dict[str, Any]:
    """Canonical JSON payload for the simulation page and public catalog API."""
    engines = list_server_engines(category=category)
    return {
        'ok': True,
        'categories': deepcopy(ENGINE_CATEGORIES),
        'engines': engines,
        'summary': summarize_engines(engines),
        'router_profile': deepcopy(ENGINE_ROUTER_PROFILE),
        'local_ai': {
            'backend': 'ollama+pytorch+rule_ai',
            'commands': ['recommend_engine', 'plan_engine_job', 'queue_engine_job', 'explain_engine_result'],
            'safe_contract': ['engine_id', 'analysis_type', 'options', 'scheme_data', 'source'],
        },
    }


def recommend_server_engines(scheme_data: dict[str, Any] | None, *, limit: int = 5) -> list[dict[str, Any]]:
    """Rank engines for a scheme-like payload using lightweight component tags."""
    components = (scheme_data or {}).get('components') if isinstance(scheme_data, dict) else []
    tags = _tags_from_components(components if isinstance(components, list) else [])
    if not tags:
        tags = {'electronics', 'spice'}

    ranked = []
    for engine in SERVER_ENGINE_CATALOG:
        engine_tags = set(engine.get('tags') or [])
        overlap = tags & engine_tags
        score = len(overlap) * 10 + int(engine.get('priority') or 0)
        if engine.get('status') == 'connected':
            score += 6
        elif engine.get('status') == 'primary-candidate':
            score += 8
        elif engine.get('status') == 'adapter-ready':
            score += 3
        if overlap or engine.get('category') == 'core':
            ranked.append((score, engine))

    ranked.sort(key=lambda item: item[0], reverse=True)
    output = []
    for score, engine in ranked[:limit]:
        item = deepcopy(engine)
        item['ai_score'] = score
        item['ai_connections'] = {
            'can_be_selected_by_local_ai': True,
            'command_target': f'engine:{item["id"]}',
            'job_payload_field': 'engine_id',
        }
        output.append(item)
    return output


def _tags_from_components(components: list[dict[str, Any]]) -> set[str]:
    tags: set[str] = set()
    for component in components:
        if not isinstance(component, dict):
            continue
        raw = ' '.join(
            str(component.get(key) or '')
            for key in ('type', 'label', 'name', 'category', 'part_number', 'description')
        ).lower()

        if any(
            token in raw for token in ('resistor', 'capacitor', 'inductor', 'diode', 'battery', 'transistor')
        ):
            tags.update({'electronics', 'spice'})
        if any(
            token in raw for token in ('ic', 'opamp', 'lm358', 'tl07', '7805', 'ti', 'buck', 'boost', 'smps')
        ):
            tags.update({'electronics', 'spice', 'power', 'opamp'})
        if any(
            token in raw for token in ('mcu', 'microcontroller', 'arduino', 'esp32', 'pico', 'risc', 'ibex')
        ):
            tags.update({'embedded', 'microcontroller', 'firmware', 'mixed-signal'})
        if any(token in raw for token in ('rf', 'antenna', 'sdr', 'filter', 'radio')):
            tags.update({'rf', 'radio', 'filter', 'signal-processing'})
        if any(token in raw for token in ('sensor', 'hx711', 'load', 'weight', 'strain')):
            tags.update({'sensor', 'lab', 'load-cell', 'calibration'})
        if any(token in raw for token in ('servo', 'motor', 'pump', 'thermal', 'heater', 'mechanic')):
            tags.update({'modeling', 'multiphysics', 'thermal', 'mechanics'})
        if any(token in raw for token in ('fpga', 'hdl', 'verilog', 'vhdl')):
            tags.update({'eda', 'fpga', 'hdl'})
    return tags
