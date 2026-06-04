"""Server-side Monte Carlo DC analysis — Block D2 (master plan 3 weeks).

NumPy-based MNA solver + parameter sweep с гауссовским джиттером по толерансу
компонентов. Заменяет 1000 браузерных WASM-итераций одним server-side вызовом
(NumPy LAPACK через `numpy.linalg.solve` — на 2 порядка быстрее).

Архитектура (зеркало JS `simulation-engine.js::buildMNA_DC`):
    1. scheme_data → circuit (R/V/D/GND; C → open, L → short на DC)
    2. MNA-матрица: conductance-stamps + V-source extension
    3. numpy.linalg.solve(A, b)
    4. Извлекаем node voltages

Monte Carlo:
    1. Для каждой итерации: каждому R/V параметру даём gaussian noise `N(value, tol*value)`
    2. Прогоняем DC → собираем voltages по узлам
    3. Финал: mean / std / percentiles (5/50/95) per node

Pitch для защиты:
    «Production-практика: 1000 прогонов с разбросом ±5% параметров —
    оцениваем yield платы перед запуском в производство. Раньше это
    делал PySpice + ngspice, теперь у нас всё на NumPy, 1000 точек
    за секунду без внешних бинарников».

Phase 2 (post-defense):
    - AC sweep (impedance matrix)
    - Transient (трапеции, как в JS-движке)
    - Histogram + Pareto plot в UI
    - Worst-case + sensitivity analysis
"""

from __future__ import annotations

import logging
import time

import numpy as np

logger = logging.getLogger(__name__)

# Толеранс по умолчанию (1σ) — стандарт E96 (1%), E24 (5%), E12 (10%).
DEFAULT_TOLERANCE = 0.05
MAX_ITERATIONS = 5000  # safety cap (~1 сек @ 50 nodes)
MIN_ITERATIONS = 10
GMIN = 1e-12  # против сингулярности «плавающих» узлов
DIODE_DROP = 0.7
LED_DROP = 2.0


# ─── Преобразование scheme_data → circuit (зеркало scheme-netlist.js) ─────
def scheme_to_circuit(scheme_data: dict) -> dict:
    """Из scheme_data собирает MNA-circuit.

    Returns: {
        'n_nodes': int (включая ground),
        'elements': [{'id', 'type', 'nodes': [n1, n2], 'value', 'label'}, ...]
    }
    where node index 0 = ground.

    Стратегия (минимальная — для Monte Carlo DC):
        - Каждый компонент с двумя соединёнными портами получает свой net.
        - Соединения объединяют net'ы через union-find.
        - Ground-компоненты (type='ground') слипаются в net 0.
    """
    components = scheme_data.get('components') or []
    connections = scheme_data.get('connections') or []
    if not components:
        return {'n_nodes': 1, 'elements': []}

    # Union-find для net'ов. Ключ = (comp_id, port_id).
    parent: dict[tuple, tuple] = {}

    def find(k: tuple) -> tuple:
        if k not in parent:
            parent[k] = k
            return k
        if parent[k] == k:
            return k
        parent[k] = find(parent[k])
        return parent[k]

    def union(a: tuple, b: tuple) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Все порты регистрируем
    port_ids = set()
    for c in components:
        cid = c.get('id')
        ports = c.get('ports') or [{'id': '1'}, {'id': '2'}]
        for p in ports:
            key = (cid, p.get('id') or p.get('name') or '1')
            port_ids.add(key)
            find(key)

    # Объединяем по connections
    for conn in connections:
        f = conn.get('from') or {}
        t = conn.get('to') or {}
        fk = (
            f.get('compId') or f.get('componentId') or f.get('id'),
            f.get('portId') or f.get('pinId') or f.get('port') or '1',
        )
        tk = (
            t.get('compId') or t.get('componentId') or t.get('id'),
            t.get('portId') or t.get('pinId') or t.get('port') or '1',
        )
        if fk in port_ids and tk in port_ids:
            union(fk, tk)

    # GND-компоненты — все их порты в один общий ground-net
    ground_key: tuple | None = None
    for c in components:
        if (c.get('type') or '').lower() == 'ground':
            cid = c.get('id')
            for p in c.get('ports') or [{'id': '1'}]:
                k = (cid, p.get('id') or '1')
                if ground_key is None:
                    ground_key = k
                else:
                    union(k, ground_key)

    # Нумеруем net'ы: ground → 0, остальные 1..N
    net_to_idx: dict[tuple, int] = {}
    if ground_key is not None:
        net_to_idx[find(ground_key)] = 0
    next_idx = 1
    for key in port_ids:
        root = find(key)
        if root not in net_to_idx:
            net_to_idx[root] = next_idx
            next_idx += 1

    n_nodes = next_idx  # включая ground

    def node_of(comp_id, port_id) -> int:
        return net_to_idx[find((comp_id, port_id))]

    elements: list[dict] = []
    for c in components:
        ctype = (c.get('type') or '').lower()
        cid = c.get('id')
        ports = c.get('ports') or [{'id': '1'}, {'id': '2'}]
        if len(ports) < 2 and ctype != 'ground':
            continue
        n1 = node_of(cid, ports[0].get('id') or '1') if ports else 0
        n2 = node_of(cid, ports[1].get('id') or '2') if len(ports) > 1 else 0

        if ctype == 'resistor':
            value = float(c.get('resistance') or c.get('value') or 1000)
            elements.append(
                {
                    'id': cid,
                    'type': 'R',
                    'nodes': [n1, n2],
                    'value': max(value, 1e-3),
                    'label': f'R{cid}',
                    'tolerable': True,
                }
            )
        elif ctype == 'capacitor':
            elements.append(
                {
                    'id': cid,
                    'type': 'C',
                    'nodes': [n1, n2],
                    'value': float(c.get('capacitance') or 1e-6),
                    'label': f'C{cid}',
                    'tolerable': False,
                }
            )
        elif ctype == 'inductor':
            elements.append(
                {
                    'id': cid,
                    'type': 'L',
                    'nodes': [n1, n2],
                    'value': float(c.get('inductance') or 1e-3),
                    'label': f'L{cid}',
                    'tolerable': False,
                }
            )
        elif ctype == 'battery':
            value = float(c.get('voltage') or 9.0)
            elements.append(
                {
                    'id': cid,
                    'type': 'V',
                    'nodes': [n1, n2],
                    'value': value,
                    'label': f'V{cid}',
                    'tolerable': True,
                }
            )
        elif ctype == 'diode':
            elements.append(
                {
                    'id': cid,
                    'type': 'D',
                    'nodes': [n1, n2],
                    'value': DIODE_DROP,
                    'label': f'D{cid}',
                    'tolerable': False,
                }
            )
        elif ctype == 'led':
            elements.append(
                {
                    'id': cid,
                    'type': 'D',
                    'nodes': [n1, n2],
                    'value': LED_DROP,
                    'label': f'LED{cid}',
                    'tolerable': False,
                }
            )

    return {'n_nodes': n_nodes, 'elements': elements}


# ─── DC MNA solver (numpy) ───────────────────────────────────────────────
def solve_dc(circuit: dict, *, caps_open: bool = True, inds_short: bool = True) -> dict:
    """Решает DC через MNA. Возвращает {voltages: {node_idx: V}, currents: {v_id: I}}.

    Зеркало JS `simulation-engine.js::buildMNA_DC` + `solveLinear`, но через
    numpy.linalg.solve (LAPACK).
    """
    node_count = circuit['n_nodes'] - 1  # минус ground
    if node_count <= 0:
        return {'voltages': {0: 0.0}, 'currents': {}}

    elements = circuit['elements']
    v_sources = [e for e in elements if e['type'] == 'V']
    diodes = [e for e in elements if e['type'] == 'D']
    extra = len(v_sources) + len(diodes)
    size = node_count + extra

    A = np.zeros((size, size), dtype=np.float64)
    b = np.zeros(size, dtype=np.float64)

    def stamp_g(n1: int, n2: int, g: float) -> None:
        if n1 > 0:
            A[n1 - 1, n1 - 1] += g
        if n2 > 0:
            A[n2 - 1, n2 - 1] += g
        if n1 > 0 and n2 > 0:
            A[n1 - 1, n2 - 1] -= g
            A[n2 - 1, n1 - 1] -= g

    for e in elements:
        if e['type'] == 'R' and e['value'] > 0:
            stamp_g(e['nodes'][0], e['nodes'][1], 1.0 / e['value'])
        elif e['type'] == 'L' and inds_short:
            stamp_g(e['nodes'][0], e['nodes'][1], 1e9)

    if caps_open:
        # G_min — против сингулярности на плавающих узлах
        for i in range(node_count):
            A[i, i] += GMIN

    for k, e in enumerate(v_sources):
        row = node_count + k
        np_, nn = e['nodes']
        if np_ > 0:
            A[np_ - 1, row] += 1
            A[row, np_ - 1] += 1
        if nn > 0:
            A[nn - 1, row] -= 1
            A[row, nn - 1] -= 1
        b[row] = e['value']

    for k, e in enumerate(diodes):
        row = node_count + len(v_sources) + k
        np_, nn = e['nodes']
        if np_ > 0:
            A[np_ - 1, row] += 1
            A[row, np_ - 1] += 1
        if nn > 0:
            A[nn - 1, row] -= 1
            A[row, nn - 1] -= 1
        b[row] = e['value']

    try:
        x = np.linalg.solve(A, b)
    except np.linalg.LinAlgError as exc:
        raise ValueError(f'Singular MNA matrix: {exc}') from exc

    voltages = {0: 0.0}
    for i in range(node_count):
        voltages[i + 1] = float(x[i])
    currents: dict[str, float] = {}
    for k, e in enumerate(v_sources):
        currents[str(e['id'])] = float(-x[node_count + k])
    return {'voltages': voltages, 'currents': currents}


# ─── Monte Carlo entry-point ─────────────────────────────────────────────
def run_monte_carlo(
    scheme_data: dict,
    *,
    iterations: int = 1000,
    tolerance: float = DEFAULT_TOLERANCE,
    seed: int | None = None,
) -> dict:
    """Прогоняет N итераций DC с гауссовским jitter параметров.

    Args:
        scheme_data: исходная схема.
        iterations: число итераций (clamp 10..5000).
        tolerance: 1σ относительный (0.05 = ±5%).
        seed: для воспроизводимости.

    Returns: {
        'iterations': int, 'elapsed_ms': float, 'tolerance': float,
        'success': int, 'failed': int,
        'nodes': {node_id: {'mean', 'std', 'min', 'max', 'p05', 'p50', 'p95'}},
        'currents': {v_source_id: {... same stats ...}},
        'errors': [str],
    }
    """
    iterations = max(MIN_ITERATIONS, min(MAX_ITERATIONS, int(iterations)))
    tolerance = max(0.0, min(0.5, float(tolerance)))
    rng = np.random.default_rng(seed)

    base_circuit = scheme_to_circuit(scheme_data)
    if not base_circuit['elements']:
        return {
            'iterations': 0,
            'elapsed_ms': 0.0,
            'tolerance': tolerance,
            'success': 0,
            'failed': 0,
            'nodes': {},
            'currents': {},
            'errors': ['scheme has no simulatable components'],
        }

    # Кэшируем индексы компонентов с tolerable=True (jitter применяем только к ним)
    base_values = np.array([e['value'] for e in base_circuit['elements']], dtype=np.float64)
    tolerable_mask = np.array([e.get('tolerable', False) for e in base_circuit['elements']])

    node_samples: dict[int, list[float]] = {}
    current_samples: dict[str, list[float]] = {}
    errors: list[str] = []
    success = 0
    failed = 0
    start_ns = time.perf_counter_ns()

    for _ in range(iterations):
        # Gaussian jitter — clamp на 3σ чтобы не получать отрицательные R
        jitter = rng.normal(loc=1.0, scale=tolerance, size=base_values.shape)
        jitter = np.clip(jitter, 1.0 - 3 * tolerance, 1.0 + 3 * tolerance)
        new_values = np.where(tolerable_mask, base_values * jitter, base_values)
        new_values = np.maximum(new_values, 1e-6)  # никаких отрицательных

        # Локальный circuit
        local_elements = [
            {**e, 'value': float(new_values[i])} for i, e in enumerate(base_circuit['elements'])
        ]
        local_circuit = {'n_nodes': base_circuit['n_nodes'], 'elements': local_elements}

        try:
            result = solve_dc(local_circuit)
        except ValueError as exc:
            failed += 1
            if len(errors) < 3:
                errors.append(str(exc))
            continue

        success += 1
        for node, v in result['voltages'].items():
            node_samples.setdefault(node, []).append(v)
        for vid, i in result['currents'].items():
            current_samples.setdefault(vid, []).append(i)

    elapsed_ms = (time.perf_counter_ns() - start_ns) / 1e6

    def _stats(samples: list[float]) -> dict:
        if not samples:
            return {'mean': 0, 'std': 0, 'min': 0, 'max': 0, 'p05': 0, 'p50': 0, 'p95': 0, 'n': 0}
        arr = np.asarray(samples, dtype=np.float64)
        return {
            'mean': float(arr.mean()),
            'std': float(arr.std(ddof=1)) if len(arr) > 1 else 0.0,
            'min': float(arr.min()),
            'max': float(arr.max()),
            'p05': float(np.percentile(arr, 5)),
            'p50': float(np.percentile(arr, 50)),
            'p95': float(np.percentile(arr, 95)),
            'n': int(len(arr)),
        }

    return {
        'iterations': iterations,
        'elapsed_ms': round(elapsed_ms, 2),
        'iter_per_sec': round(success / (elapsed_ms / 1000), 0) if elapsed_ms > 0 else 0,
        'tolerance': tolerance,
        'success': success,
        'failed': failed,
        'nodes': {str(node): _stats(samples) for node, samples in sorted(node_samples.items())},
        'currents': {vid: _stats(samples) for vid, samples in current_samples.items()},
        'errors': errors,
        'algorithm': 'NumPy MNA + Gaussian Monte Carlo (DC)',
    }
