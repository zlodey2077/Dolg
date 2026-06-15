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

import itertools
import logging
import math
import time

import numpy as np

logger = logging.getLogger(__name__)

# Толеранс по умолчанию (1σ) — стандарт E96 (1%), E24 (5%), E12 (10%).
DEFAULT_TOLERANCE = 0.05
MAX_ITERATIONS = 10000  # safety cap (~2 сек @ 50 nodes) — режим «шизо-теста»
MIN_ITERATIONS = 10
GMIN = 1e-12  # против сингулярности «плавающих» узлов
DIODE_DROP = 0.7
LED_DROP = 2.0
# Нелинейная модель диода (Shockley + Newton-Raphson). Is выводится из паспортного
# Vf при опорном токе I_REF, чтобы падение ≈ Vf около рабочей точки, но менялось с
# током и корректно отсекало обратное смещение (фикс-Vf этого не умел).
VT_THERMAL = 0.02585  # kT/q при ~300K
N_DIODE = 2.0  # коэффициент неидеальности (норм для LED/Si-диода в учебной модели)
I_REF_DIODE = 1e-3  # опорный ток для калибровки Is по Vf
DIODE_MAX_ITER = 100  # Newton iterations cap
DIODE_VSTEP_CLAMP = 0.1  # макс. шаг Vd за итерацию (демпфирование экспоненты)
DIODE_CONV_TOL = 1e-7  # сходимость по |ΔVd|
# Worst-case: на сколько σ уходим к краю допуска (совпадает с clamp Monte Carlo,
# поэтому угловой конверт гарантированно охватывает все MC-выборки).
SIGMA_MULTIPLIER = 3.0
# Полный перебор углов = 2^k solve-вызовов. Выше порога — случайная выборка углов.
WORST_CASE_MAX_COMPONENTS = 13  # 2^13 = 8192 прогонов


def _num(value, default: float) -> float:
    """Парс номинала в float, устойчивый к инженерным строкам ('1k'→1000,
    '1u'→1e-6, '100n'→1e-7). Реальные схемы хранят номиналы строками, а голый
    float('1k') падал и ронял весь MNA (DC/power/транзиент/толеранс)."""
    if value is None or value == '':
        return float(default)
    try:
        return float(value)
    except TypeError, ValueError:
        pass
    try:
        from .engineering_units import parse_engineering_number

        parsed = parse_engineering_number(value, default=None)
        if parsed is not None:
            return float(parsed)
    except Exception:
        pass
    return float(default)


def _component_tolerance(component: dict) -> float | None:
    """Относительный допуск компонента (0.05 = ±5%) из scheme. None — если не
    задан (тогда берётся глобальный). Поле `tolerance_percent` — это проценты
    (1 → 0.01, важно для E96 1%-резисторов); поле `tolerance` — уже доля."""
    if component.get('tolerance_percent') is not None:
        try:
            value = float(component['tolerance_percent']) / 100.0
        except TypeError, ValueError:
            return None
        return max(0.0, min(0.5, value))
    if component.get('tolerance') is not None:
        try:
            value = float(component['tolerance'])
        except TypeError, ValueError:
            return None
        if value > 1.0:  # прислали проценты в поле доли — мягко конвертируем
            value /= 100.0
        return max(0.0, min(0.5, value))
    return None


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
            value = _num(c.get('resistance') or c.get('value'), 1000)
            elements.append(
                {
                    'id': cid,
                    'type': 'R',
                    'nodes': [n1, n2],
                    'value': max(value, 1e-3),
                    'label': f'R{cid}',
                    'tolerable': True,
                    'tolerance': _component_tolerance(c),
                }
            )
        elif ctype == 'capacitor':
            elements.append(
                {
                    'id': cid,
                    'type': 'C',
                    'nodes': [n1, n2],
                    'value': _num(c.get('capacitance'), 1e-6),
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
                    'value': _num(c.get('inductance'), 1e-3),
                    'label': f'L{cid}',
                    'tolerable': False,
                }
            )
        elif ctype == 'battery':
            value = _num(c.get('voltage'), 9.0)
            elements.append(
                {
                    'id': cid,
                    'type': 'V',
                    'nodes': [n1, n2],
                    'value': value,
                    'label': f'V{cid}',
                    'tolerable': True,
                    'tolerance': _component_tolerance(c),
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
    size = node_count + len(v_sources)

    def _diode_is(vf: float) -> float:
        """Is из паспортного Vf при опорном токе I_REF (Shockley)."""
        denom = math.exp(min(vf, 5.0) / (N_DIODE * VT_THERMAL)) - 1.0
        return I_REF_DIODE / denom if denom > 0 else 1e-12

    diode_is = [_diode_is(float(e.get('value') or DIODE_DROP)) for e in diodes]
    vd = [float(e.get('value') or DIODE_DROP) for e in diodes]  # init guess = Vf

    def _build_and_solve(vd_cur):
        """Один линейный шаг MNA: R/L/Gmin + V-источники + companion-модели диодов
        в текущей рабочей точке vd_cur. Возвращает (x, diode_currents)."""
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

        # Companion-модель диода: I_d ≈ Gd·V + Ieq (линеаризация Shockley в vd_cur).
        diode_currents = []
        for k, e in enumerate(diodes):
            n1, n2 = e['nodes']
            v = vd_cur[k]
            ex = math.exp(min(v, 5.0) / (N_DIODE * VT_THERMAL))
            i_d = diode_is[k] * (ex - 1.0)
            gd = max(diode_is[k] / (N_DIODE * VT_THERMAL) * ex, GMIN)
            ieq = i_d - gd * v
            stamp_g(n1, n2, gd)
            if n1 > 0:
                b[n1 - 1] -= ieq
            if n2 > 0:
                b[n2 - 1] += ieq
            diode_currents.append(i_d)

        try:
            return np.linalg.solve(A, b), diode_currents
        except np.linalg.LinAlgError as exc:
            raise ValueError(f'Singular MNA matrix: {exc}') from exc

    if not diodes:
        x, diode_currents = _build_and_solve(vd)
    else:
        # Newton-Raphson: итерируем рабочие точки диодов до сходимости с
        # демпфированием шага (экспонента иначе расходится).
        x, diode_currents = _build_and_solve(vd)
        for _ in range(DIODE_MAX_ITER):
            x, diode_currents = _build_and_solve(vd)
            max_dv = 0.0
            for k, e in enumerate(diodes):
                n1, n2 = e['nodes']
                v_n1 = float(x[n1 - 1]) if n1 > 0 else 0.0
                v_n2 = float(x[n2 - 1]) if n2 > 0 else 0.0
                new_vd = v_n1 - v_n2
                step = new_vd - vd[k]
                if step > DIODE_VSTEP_CLAMP:
                    new_vd = vd[k] + DIODE_VSTEP_CLAMP
                elif step < -DIODE_VSTEP_CLAMP:
                    new_vd = vd[k] - DIODE_VSTEP_CLAMP
                new_vd = max(-50.0, min(new_vd, float(e.get('value') or DIODE_DROP) + 0.5))
                max_dv = max(max_dv, abs(new_vd - vd[k]))
                vd[k] = new_vd
            if max_dv < DIODE_CONV_TOL:
                break
        # Финальный пересчёт токов в сошедшейся точке.
        x, diode_currents = _build_and_solve(vd)

    voltages = {0: 0.0}
    for i in range(node_count):
        voltages[i + 1] = float(x[i])
    currents: dict[str, float] = {}
    for k, e in enumerate(v_sources):
        currents[str(e['id'])] = float(-x[node_count + k])
    for k, e in enumerate(diodes):
        currents[str(e['id'])] = float(diode_currents[k])
    return {'voltages': voltages, 'currents': currents}


# ─── Transient (TRAN) MNA solver — Backward Euler ────────────────────────
# Companion-модели реактивных элементов по неявной схеме Backward Euler (A-устойчива):
#   Конденсатор: i_C = C·dv/dt ≈ (C/h)·(v − v_prev) → Geq=C/h, ток-источник Geq·v_prev.
#   Катушка:     v_L = L·di/dt ≈ (L/h)·(i − i_prev) → Geq=h/L, ток-источник i_prev.
# Линейная версия (R/V/C/L). Диоды в транзиенте — отдельная итерация (нелинейный
# Newton на каждом шаге); здесь сознательно линейная, чтобы покрыть RC/RL/RLC точно.
TRAN_MAX_STEPS = 20000  # safety cap по числу временных точек


def solve_transient(
    circuit: dict,
    *,
    t_stop: float,
    dt: float,
    v_initial: dict | None = None,
) -> dict:
    """Переходный анализ через MNA + Backward Euler.

    Returns {
        'time':     [t0, t1, ...],            # секунды
        'voltages': {node_idx: [v0, v1, ...]},# временной ряд по узлам
        'steps':    int,
        'dt':       float,
    }
    Линейные R/V/C/L. Начальные условия: узлы 0В (или v_initial), ток катушек 0.
    """
    node_count = circuit['n_nodes'] - 1
    if node_count <= 0 or dt <= 0 or t_stop <= 0:
        return {'time': [0.0], 'voltages': {0: [0.0]}, 'steps': 1, 'dt': dt}

    elements = circuit['elements']
    v_sources = [e for e in elements if e['type'] == 'V']
    caps = [e for e in elements if e['type'] == 'C']
    inds = [e for e in elements if e['type'] == 'L']
    size = node_count + len(v_sources)

    n_steps = min(int(math.ceil(t_stop / dt)) + 1, TRAN_MAX_STEPS)

    # Состояние: напряжение на каждом конденсаторе и ток через каждую катушку.
    v_cap = [0.0] * len(caps)
    i_ind = [0.0] * len(inds)
    # Начальные узловые напряжения (для v_cap из v_initial).
    node_v = {i: 0.0 for i in range(node_count + 1)}
    if v_initial:
        for k, val in v_initial.items():
            try:
                node_v[int(k)] = float(val)
            except TypeError, ValueError:
                continue
    for k, e in enumerate(caps):
        n1, n2 = e['nodes']
        v_cap[k] = node_v.get(n1, 0.0) - node_v.get(n2, 0.0)

    def stamp_g(A, n1, n2, g):
        if n1 > 0:
            A[n1 - 1, n1 - 1] += g
        if n2 > 0:
            A[n2 - 1, n2 - 1] += g
        if n1 > 0 and n2 > 0:
            A[n1 - 1, n2 - 1] -= g
            A[n2 - 1, n1 - 1] -= g

    times: list[float] = []
    series: dict[int, list[float]] = {i: [] for i in range(node_count + 1)}

    def _record(t: float, node_now: dict) -> None:
        times.append(t)
        for i in range(node_count + 1):
            series[i].append(node_now[i])

    # Начальная рабочая точка (t=0): конденсаторы держат v_cap (источник напряжения),
    # катушки держат i_ind (источник тока). Это истинные узловые потенциалы при t=0,
    # отдельно от первого BE-шага (иначе первая точка была бы уже «после» шага).
    op_size = size + len(caps)
    A0 = np.zeros((op_size, op_size), dtype=np.float64)
    b0 = np.zeros(op_size, dtype=np.float64)
    for e in elements:
        if e['type'] == 'R' and e['value'] > 0:
            stamp_g(A0, e['nodes'][0], e['nodes'][1], 1.0 / e['value'])
    for i in range(node_count):
        A0[i, i] += GMIN
    for kk, e in enumerate(v_sources):
        row = node_count + kk
        np_, nn = e['nodes']
        if np_ > 0:
            A0[np_ - 1, row] += 1
            A0[row, np_ - 1] += 1
        if nn > 0:
            A0[nn - 1, row] -= 1
            A0[row, nn - 1] -= 1
        b0[row] = e['value']
    for k, e in enumerate(caps):  # конденсатор как V-источник = v_cap[k]
        row = size + k
        n1, n2 = e['nodes']
        if n1 > 0:
            A0[n1 - 1, row] += 1
            A0[row, n1 - 1] += 1
        if n2 > 0:
            A0[n2 - 1, row] -= 1
            A0[row, n2 - 1] -= 1
        b0[row] = v_cap[k]
    for k, e in enumerate(inds):  # катушка как I-источник = i_ind[k] (n1→n2)
        n1, n2 = e['nodes']
        if n1 > 0:
            b0[n1 - 1] -= i_ind[k]
        if n2 > 0:
            b0[n2 - 1] += i_ind[k]
    try:
        x0 = np.linalg.solve(A0, b0)
        node0 = {0: 0.0}
        for i in range(node_count):
            node0[i + 1] = float(x0[i])
        _record(0.0, node0)
    except np.linalg.LinAlgError:
        pass  # вырожденная начальная точка — пропускаем, первый BE-шаг стартует от IC

    # Шаги BE: точки при t = dt, 2·dt, … (t=0 уже записан выше).
    for step in range(1, n_steps):
        t = step * dt
        A = np.zeros((size, size), dtype=np.float64)
        b = np.zeros(size, dtype=np.float64)

        for e in elements:
            if e['type'] == 'R' and e['value'] > 0:
                stamp_g(A, e['nodes'][0], e['nodes'][1], 1.0 / e['value'])
        for i in range(node_count):
            A[i, i] += GMIN

        # Конденсаторы: Geq=C/h, ток-источник Ieq=Geq·v_prev (по направлению n1→n2).
        for k, e in enumerate(caps):
            n1, n2 = e['nodes']
            geq = float(e['value']) / dt
            ieq = geq * v_cap[k]
            stamp_g(A, n1, n2, geq)
            if n1 > 0:
                b[n1 - 1] += ieq
            if n2 > 0:
                b[n2 - 1] -= ieq

        # Катушки: Geq=h/L, ток-источник Ieq=i_prev.
        for k, e in enumerate(inds):
            n1, n2 = e['nodes']
            geq = dt / max(float(e['value']), 1e-12)
            ieq = i_ind[k]
            stamp_g(A, n1, n2, geq)
            if n1 > 0:
                b[n1 - 1] -= ieq
            if n2 > 0:
                b[n2 - 1] += ieq

        for kk, e in enumerate(v_sources):
            row = node_count + kk
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
            raise ValueError(f'Singular MNA matrix (transient t={t:g}): {exc}') from exc

        node_now = {0: 0.0}
        for i in range(node_count):
            node_now[i + 1] = float(x[i])

        _record(t, node_now)

        # Обновляем состояние реактивных элементов для следующего шага.
        for k, e in enumerate(caps):
            n1, n2 = e['nodes']
            v_cap[k] = node_now.get(n1, 0.0) - node_now.get(n2, 0.0)
        for k, e in enumerate(inds):
            n1, n2 = e['nodes']
            geq = dt / max(float(e['value']), 1e-12)
            v_l = node_now.get(n1, 0.0) - node_now.get(n2, 0.0)
            i_ind[k] = i_ind[k] + geq * v_l

    return {'time': times, 'voltages': series, 'steps': len(times), 'dt': dt}


# ─── Tolerance resolution (per-element) ──────────────────────────────────
def _resolve_tolerances(
    elements: list[dict],
    global_tolerance: float,
    component_tolerances: dict | None,
) -> np.ndarray:
    """Возвращает per-element массив относительных допусков (1σ). Приоритет:
    явный override по id компонента → собственный допуск элемента → глобальный.
    Нетолерантные элементы (C/L/D) всегда 0. `component_tolerances` — доли
    (0.05 = ±5%); percent→доля конвертирует вызывающий слой (view)."""
    overrides = {}
    for key, val in (component_tolerances or {}).items():
        try:
            v = float(val)
        except TypeError, ValueError:
            continue
        overrides[str(key)] = max(0.0, min(0.5, v))

    out = np.zeros(len(elements), dtype=np.float64)
    for i, e in enumerate(elements):
        if not e.get('tolerable'):
            continue
        if str(e.get('id')) in overrides:
            out[i] = overrides[str(e['id'])]
        elif e.get('tolerance') is not None:
            out[i] = float(e['tolerance'])
        else:
            out[i] = max(0.0, min(0.5, float(global_tolerance)))
    return out


# ─── Monte Carlo entry-point ─────────────────────────────────────────────
def run_monte_carlo(
    scheme_data: dict,
    *,
    iterations: int = 1000,
    tolerance: float = DEFAULT_TOLERANCE,
    seed: int | None = None,
    component_tolerances: dict | None = None,
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

    # Per-element допуски (1σ): override по id → собственный → глобальный.
    base_values = np.array([e['value'] for e in base_circuit['elements']], dtype=np.float64)
    tol_array = _resolve_tolerances(base_circuit['elements'], tolerance, component_tolerances)
    # Номинал (без джиттера) — опора для worst-case и paranoia.
    try:
        nominal_voltages = solve_dc(base_circuit)['voltages']
    except ValueError:
        nominal_voltages = {}

    node_samples: dict[int, list[float]] = {}
    current_samples: dict[str, list[float]] = {}
    errors: list[str] = []
    success = 0
    failed = 0
    start_ns = time.perf_counter_ns()

    for _ in range(iterations):
        # Gaussian jitter с per-element σ — clamp на 3σ (scale=0 → элемент не дрожит)
        jitter = rng.normal(loc=1.0, scale=tol_array, size=base_values.shape)
        jitter = np.clip(jitter, 1.0 - 3 * tol_array, 1.0 + 3 * tol_array)
        new_values = base_values * jitter
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
        'nominal': {str(node): float(v) for node, v in sorted(nominal_voltages.items())},
        'nodes': {str(node): _stats(samples) for node, samples in sorted(node_samples.items())},
        'currents': {vid: _stats(samples) for vid, samples in current_samples.items()},
        'errors': errors,
        'algorithm': 'NumPy MNA + Gaussian Monte Carlo (DC)',
    }


# ─── Worst-case / corner analysis ────────────────────────────────────────
def run_worst_case(
    scheme_data: dict,
    *,
    tolerance: float = DEFAULT_TOLERANCE,
    component_tolerances: dict | None = None,
    seed: int | None = None,
    max_components: int = WORST_CASE_MAX_COMPONENTS,
) -> dict:
    """Угловой (worst-case) анализ: каждый толерантный параметр ставится в край
    допуска (±3σ, как clamp Monte Carlo). При ≤ max_components параметрах
    перебираются ВСЕ 2^k углов (точная огибающая), иначе — случайная выборка
    углов (приближённая). Возвращает per-node min/max/span вокруг номинала."""
    circuit = scheme_to_circuit(scheme_data)
    elements = circuit['elements']
    if not elements:
        return {
            'evaluated': 0,
            'failed': 0,
            'exhaustive': True,
            'components': 0,
            'sigma_multiplier': SIGMA_MULTIPLIER,
            'nodes': {},
            'nominal': {},
            'errors': ['scheme has no simulatable components'],
        }

    base_values = np.array([e['value'] for e in elements], dtype=np.float64)
    tol_array = _resolve_tolerances(elements, tolerance, component_tolerances)
    tol_idx = [i for i, t in enumerate(tol_array) if t > 0]
    k = len(tol_idx)
    rng = np.random.default_rng(seed)

    exhaustive = k <= max_components
    if k == 0:
        sign_combos: list[tuple] = [()]
    elif exhaustive:
        sign_combos = list(itertools.product((-1, 1), repeat=k))
    else:
        cap = 2**max_components
        sign_combos = [tuple(int(s) for s in rng.choice((-1, 1), size=k)) for _ in range(cap)]

    node_min: dict[int, float] = {}
    node_max: dict[int, float] = {}
    evaluated = 0
    failed = 0
    for signs in sign_combos:
        vals = base_values.copy()
        for pos, j in enumerate(tol_idx):
            vals[j] = base_values[j] * (1.0 + signs[pos] * SIGMA_MULTIPLIER * tol_array[j])
        vals = np.maximum(vals, 1e-6)
        local = {
            'n_nodes': circuit['n_nodes'],
            'elements': [{**e, 'value': float(vals[i])} for i, e in enumerate(elements)],
        }
        try:
            res = solve_dc(local)
        except ValueError:
            failed += 1
            continue
        evaluated += 1
        for node, v in res['voltages'].items():
            if node not in node_min or v < node_min[node]:
                node_min[node] = v
            if node not in node_max or v > node_max[node]:
                node_max[node] = v

    try:
        nominal = solve_dc(circuit)['voltages']
    except ValueError:
        nominal = {}

    nodes = {}
    for node in sorted(node_min):
        lo, hi = node_min[node], node_max[node]
        nom = float(nominal.get(node, (lo + hi) / 2.0))
        nodes[str(node)] = {
            'min': round(lo, 6),
            'max': round(hi, 6),
            'nominal': round(nom, 6),
            'span': round(hi - lo, 6),
        }
    return {
        'evaluated': evaluated,
        'failed': failed,
        'exhaustive': exhaustive,
        'components': k,
        'sigma_multiplier': SIGMA_MULTIPLIER,
        'nodes': nodes,
        'nominal': {str(n): round(float(v), 6) for n, v in sorted(nominal.items())},
        'algorithm': 'NumPy MNA worst-case corner sweep (DC)',
    }


def _paranoia_report(worst_case: dict) -> dict:
    """«Паранойя-отчёт»: по огибающей worst-case выявляет узлы с опасным
    разбросом или сменой знака. Severity: high (>30% или смена знака) /
    medium (>10%). Для питча по надёжности (РЭБ/критичные условия)."""
    flags = []
    for node, wc in (worst_case.get('nodes') or {}).items():
        if node == '0':  # ground
            continue
        nom = wc.get('nominal', 0.0)
        span = wc.get('span', 0.0)
        ref = max(abs(nom), 1e-9)
        span_pct = span / ref * 100.0
        sign_flip = wc.get('min', 0.0) < -1e-9 and wc.get('max', 0.0) > 1e-9
        if sign_flip:
            flags.append(
                {
                    'node': node,
                    'severity': 'high',
                    'span_pct': round(span_pct, 1),
                    'min': wc.get('min'),
                    'max': wc.get('max'),
                    'nominal': nom,
                    'message': (
                        f'узел {node}: напряжение меняет знак в пределах допусков '
                        f'({wc.get("min"):.3f}…{wc.get("max"):.3f} В) — риск инверсии полярности'
                    ),
                }
            )
        elif span_pct >= 30.0:
            flags.append(
                {
                    'node': node,
                    'severity': 'high',
                    'span_pct': round(span_pct, 1),
                    'min': wc.get('min'),
                    'max': wc.get('max'),
                    'nominal': nom,
                    'message': (
                        f'узел {node}: разброс {span_pct:.0f}% от номинала ({nom:.3f} В) — '
                        f'вне инженерного запаса'
                    ),
                }
            )
        elif span_pct >= 10.0:
            flags.append(
                {
                    'node': node,
                    'severity': 'medium',
                    'span_pct': round(span_pct, 1),
                    'min': wc.get('min'),
                    'max': wc.get('max'),
                    'nominal': nom,
                    'message': f'узел {node}: разброс {span_pct:.0f}% от номинала ({nom:.3f} В)',
                }
            )

    if worst_case.get('failed'):
        flags.append(
            {
                'node': None,
                'severity': 'high',
                'message': (
                    f'{worst_case["failed"]} угловых комбинаций дали вырожденную матрицу — '
                    f'схема неустойчива в части диапазона допусков'
                ),
            }
        )

    flags.sort(key=lambda f: (0 if f['severity'] == 'high' else 1, -f.get('span_pct', 0)))
    high = sum(1 for f in flags if f['severity'] == 'high')
    medium = sum(1 for f in flags if f['severity'] == 'medium')
    verdict = 'critical' if high else 'warning' if medium else 'ok'
    summary = {
        'ok': 'Схема устойчива к разбросу параметров в заданных допусках.',
        'warning': f'Умеренный разброс: {medium} узл(ов) выходят за 10% от номинала.',
        'critical': f'Высокий риск: {high} критичн(ых) узл(ов) (>30% или смена знака).',
    }[verdict]
    return {'verdict': verdict, 'high': high, 'medium': medium, 'flags': flags, 'summary': summary}


def run_tolerance_analysis(
    scheme_data: dict,
    *,
    iterations: int = 1000,
    tolerance: float = DEFAULT_TOLERANCE,
    seed: int | None = None,
    component_tolerances: dict | None = None,
    worst_case: bool = True,
) -> dict:
    """Полный «шизо-тест»: Monte Carlo + worst-case corner + paranoia-отчёт.
    Один вызов для UI — собирает разброс (статистика) и гарантированную
    огибающую (углы) в единый отчёт надёжности."""
    mc = run_monte_carlo(
        scheme_data,
        iterations=iterations,
        tolerance=tolerance,
        seed=seed,
        component_tolerances=component_tolerances,
    )
    report = {'monte_carlo': mc}
    if worst_case:
        wc = run_worst_case(
            scheme_data,
            tolerance=tolerance,
            component_tolerances=component_tolerances,
            seed=seed,
        )
        report['worst_case'] = wc
        report['paranoia'] = _paranoia_report(wc)
    return report
