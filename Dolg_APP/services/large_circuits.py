"""Генератор больших схем (тысячи элементов) для тяжёлой 3D-визуализации.

Резисторная сетка N×N: узлы — точки сетки, рёбра — резисторы между соседями; источник в
одном углу, земля в противоположном. Решение даёт ПОЛЕ напряжений по сетке → 3D-поверхность
(x, y = позиция, z = напряжение). Масштаб: N×N сетка ≈ N² узлов + 2·N·(N−1) резисторов
(N=40 → 1600 узлов, ~3120 резисторов — «несколько тысяч элементов»).

Тут где индустриальный движок (Xyce/ngspice) окупается: самодельная MNA на тысячах узлов
плотнеет и тормозит, промышленный SPICE держит масштаб.

Формат — circuit-dict как у `monte_carlo.scheme_to_circuit` (n_nodes, elements с net-индексами),
чтобы решать напрямую `solve_dc`. net 0 = ground; узел сетки (i,j) → net i*N + j + 1.
"""

from __future__ import annotations


def grid_net(i: int, j: int, n: int) -> int:
    """net-индекс узла сетки (i,j). net 0 = ground, поэтому +1."""
    return i * n + j + 1


def generate_resistor_grid_circuit(n: int, *, v: float = 10.0, r: float = 100.0) -> dict:
    """Резисторная сетка N×N как circuit-dict. Источник V в углу (0,0), земля — угол (n-1,n-1).

    Returns {'n_nodes', 'elements': [{'id','type','nodes':[a,b],'value'}]}. Все узлы имеют путь
    к земле → схема решаема. Элементов ≈ 2·N·(N−1)+2.
    """
    n = max(2, int(n))
    elements: list[dict] = []
    eid = 0

    def add(etype: str, a: int, b: int, value: float) -> None:
        nonlocal eid
        eid += 1
        elements.append({'id': f'{etype}{eid}', 'type': etype, 'nodes': [a, b], 'value': value})

    # Источник: V(node(0,0)) - V(ground) = v  →  угол (0,0) на потенциале v.
    add('V', grid_net(0, 0, n), 0, v)
    # Резисторы между соседями по горизонтали и вертикали.
    for i in range(n):
        for j in range(n):
            here = grid_net(i, j, n)
            if j + 1 < n:
                add('R', here, grid_net(i, j + 1, n), r)
            if i + 1 < n:
                add('R', here, grid_net(i + 1, j, n), r)
    # Сток: противоположный угол на землю через резистор.
    add('R', grid_net(n - 1, n - 1, n), 0, r)

    return {'n_nodes': n * n + 1, 'elements': elements}


def voltage_field(voltages: dict, n: int) -> list[list[float]]:
    """{net: voltage} → 2D-поле n×n напряжений по сетке (для 3D-поверхности)."""
    return [[float(voltages.get(grid_net(i, j, n), 0.0)) for j in range(n)] for i in range(n)]


def generate_lc_ladder_circuit(n: int, *, v: float = 5.0, ind: float = 1e-3, c: float = 1e-6) -> dict:
    """LC-лестница (линия задержки): источник → [L послед. + C шунт]×N → открытый конец.

    Ступенька на входе бежит волной по узлам с задержкой √(LC) и LC-звоном, на открытом конце
    отражается → богатый переходный процесс. Узлы 1..N вдоль линии. Returns circuit-dict.
    """
    n = max(3, int(n))
    counts = {'V': 0, 'L': 0, 'C': 0}
    elements: list[dict] = []

    def add(etype: str, a: int, b: int, value: float) -> None:
        counts[etype] += 1
        elements.append({'id': f'{etype}{counts[etype]}', 'type': etype, 'nodes': [a, b], 'value': value})

    add('V', 1, 0, v)  # источник-ступенька на входной узел
    add('C', 1, 0, c)
    for k in range(1, n):
        add('L', k, k + 1, ind)  # последовательная катушка k → k+1
        add('C', k + 1, 0, c)  # шунтовой конденсатор узла k+1
    return {'n_nodes': n + 1, 'elements': elements}


def transient_wave_field(circuit: dict, *, t_stop: float, dt: float, max_frames: int = 70):
    """circuit → 2D-поле [кадр времени][узел] напряжений для 3D-волновой поверхности.

    Прорежает временной ряд до max_frames кадров; узлы 1..N (без ground). Returns (field, meta).
    """
    from Dolg_APP.services import monte_carlo

    tr = monte_carlo.solve_transient(circuit, t_stop=t_stop, dt=dt)
    times = tr.get('time') or [0.0]
    volts = tr.get('voltages') or {}
    n_nodes = int(circuit.get('n_nodes') or 1)
    step = max(1, len(times) // max_frames)
    frames = list(range(0, len(times), step))
    field = []
    for i in frames:
        row = []
        for net in range(1, n_nodes):
            series = volts.get(net) or volts.get(str(net)) or []
            row.append(float(series[i]) if i < len(series) else 0.0)
        field.append(row)
    meta = {'frames': len(frames), 'nodes': n_nodes - 1, 'steps': len(times), 'dt': dt}
    return field, meta
