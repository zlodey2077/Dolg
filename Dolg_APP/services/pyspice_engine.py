"""PySpice (ngspice) адаптер — индустриальный SPICE как физический движок DOLG.

Берёт ту же сетевую модель, что NumPy MNA (`monte_carlo.scheme_to_circuit`: net 0 =
ground, elements R/C/L/V/D с net-индексами), строит из неё ngspice-нетлист (имена узлов
= net-индексы, узел '0' = земля по конвенции ngspice) и решает DC operating point.

Зачем: PySpice/ngspice — industrial SPICE (нелинейщина/transient/AC/реальные device-модели),
«золотой эталон» сильнее самодельной MNA. Узловые индексы совпадают с MNA/GNN, поэтому
напряжения отсюда прямо сопоставимы (и годятся как метки учителя `neural_teacher`).

Ленивая загрузка: PySpice импортируется ВНУТРИ функций — Django startup не тянет ngspice.
Любая ошибка движка (нет ngspice / вырожденная схема) → None, caller падает на MNA.
"""

from __future__ import annotations

import importlib.util


def available() -> bool:
    """PySpice установлен и импортируется (ngspice DLL грузится лениво при первом solve)."""
    return importlib.util.find_spec('PySpice') is not None


def _build_circuit(scheme_data: dict, *, ac_mode: bool = False):
    """scheme → построенный ngspice-нетлист. Узлы = net-индексы (узел '0' = земля).

    Returns dict {circuit, n_nodes, has_source, cap_nodes} | {'trivial': True} | None.
    cap_nodes — не-ground узлы с конденсатором (для .ic при transient). None — нет
    PySpice / ошибка построения.

    ac_mode: V-источники строятся через raw_spice как `DC <v> AC <v>` (атрибут
    PySpice-источника AC-спеку в нетлист не эмитит), чтобы у `.ac` было возбуждение.
    """
    if not available():
        return None
    try:
        from PySpice.Spice.Netlist import Circuit

        from Dolg_APP.services import monte_carlo

        circuit_data = monte_carlo.scheme_to_circuit(scheme_data)
    except Exception:
        return None

    n_nodes = int(circuit_data.get('n_nodes') or 0)
    elements = circuit_data.get('elements') or []
    if n_nodes <= 1 or not elements:
        return {'trivial': True}

    try:
        circuit = Circuit('dolg')
        counts: dict[str, int] = {}
        has_source = False
        cap_nodes: set[int] = set()
        for elem in elements:
            etype = elem.get('type')
            nodes = elem.get('nodes') or []
            if len(nodes) < 2:
                continue
            a, b = int(nodes[0]), int(nodes[1])
            na, nb = str(a), str(b)
            value = float(elem.get('value') or 0.0)
            counts[etype] = counts.get(etype, 0) + 1
            name = str(counts[etype])
            if etype == 'R':
                circuit.R(name, na, nb, value if value > 0 else 1e-3)
            elif etype == 'V':
                if ac_mode:
                    circuit.raw_spice += f'\nV{name} {na} {nb} DC {value} AC {value or 1}'
                else:
                    circuit.V(name, na, nb, value)
                has_source = True
            elif etype == 'C':
                circuit.C(name, na, nb, value if value > 0 else 1e-12)
                cap_nodes.update(n for n in (a, b) if n != 0)
            elif etype == 'L':
                circuit.L(name, na, nb, value if value > 0 else 1e-9)
            elif etype == 'D':
                # Базовая диодная модель (для DC; точные параметры — на доработку).
                circuit.model('DMOD', 'D', IS=1e-14, N=1.0)
                circuit.Diode(name, na, nb, model='DMOD')
    except Exception:
        return None
    return {'circuit': circuit, 'n_nodes': n_nodes, 'has_source': has_source, 'cap_nodes': cap_nodes}


def solve_dc(scheme_data: dict) -> dict[int, float] | None:
    """DC-напряжения узлов через ngspice. {net_index: voltage}, net 0 = ground = 0.

    None, если PySpice недоступен или схема не решается (вырожденная/без земли).
    Узловая нумерация = `monte_carlo.scheme_to_circuit` (совместимо с MNA и GNN).
    """
    built = _build_circuit(scheme_data)
    if built is None:
        return None
    if built.get('trivial'):
        return {0: 0.0}
    if not built['has_source']:
        return None
    try:
        analysis = built['circuit'].simulator().operating_point()
    except Exception:
        return None

    voltages: dict[int, float] = {0: 0.0}
    for net in range(1, built['n_nodes']):
        try:
            voltages[net] = float(analysis[str(net)][0])
        except Exception:
            voltages[net] = 0.0
    return voltages


def solve_transient(scheme_data: dict, *, t_stop: float, dt: float) -> dict | None:
    """Переходный отклик через ngspice. Формат как `monte_carlo.solve_transient`:
    `{'time':[...], 'voltages':{net:[...]}, 'steps', 'dt', 'engine'}`.

    Конденсаторы стартуют с 0 В (power-on заряд, как в MNA): `.ic v(node)=0` + UIC,
    иначе ngspice стартовал бы из DC-рабочей точки (кондёр уже заряжен). None — нет
    PySpice / нет источника / схема не считается.
    """
    if t_stop <= 0 or dt <= 0:
        return None
    built = _build_circuit(scheme_data)
    if built is None or built.get('trivial') or not built['has_source']:
        return None

    circuit = built['circuit']
    cap_nodes = built['cap_nodes']
    try:
        if cap_nodes:
            circuit.raw_spice += '.ic ' + ' '.join(f'v({n})=0' for n in sorted(cap_nodes))
        analysis = circuit.simulator().transient(
            step_time=dt, end_time=t_stop, use_initial_condition=bool(cap_nodes)
        )
        time = [float(x) for x in analysis.time]
    except Exception:
        return None

    voltages: dict[int, list[float]] = {0: [0.0] * len(time)}
    for net in range(1, built['n_nodes']):
        try:
            voltages[net] = [float(x) for x in analysis[str(net)]]
        except Exception:
            voltages[net] = [0.0] * len(time)
    return {'time': time, 'voltages': voltages, 'steps': len(time), 'dt': dt, 'engine': 'pyspice-ngspice'}


def solve_ac(scheme_data: dict, freqs) -> dict | None:
    """Частотный отклик (мод/фаза по узлам) через ngspice. Формат как
    `monte_carlo.solve_ac`: `{'freqs':[...], 'nodes':{net:{'mag':[...],'phase_deg':[...]}}}`.

    AC-возбуждение источников = их `value` (1В-источник даёт передаточную функцию, как в
    monte_carlo). На каждую запрошенную частоту — точечный `.ac` (произвольный список freqs,
    ngspice-сетка тут не нужна). None — нет PySpice / нет источника / схема не считается.
    """
    import math as _math

    import numpy as _np

    freq_list = [f for f in (float(x) for x in freqs) if f > 0]
    if not freq_list:
        return None
    built = _build_circuit(scheme_data, ac_mode=True)
    if built is None or built.get('trivial') or not built['has_source']:
        return None

    n_nodes = built['n_nodes']
    nodes_out: dict[int, dict] = {net: {'mag': [], 'phase_deg': []} for net in range(n_nodes)}
    used_freqs: list[float] = []
    try:
        simulator = built['circuit'].simulator()
        for freq in freq_list:
            analysis = simulator.ac(
                start_frequency=freq, stop_frequency=freq, number_of_points=1, variation='lin'
            )
            used_freqs.append(freq)
            for net in range(n_nodes):
                if net == 0:
                    nodes_out[net]['mag'].append(0.0)
                    nodes_out[net]['phase_deg'].append(0.0)
                    continue
                try:
                    # numpy-массив сохраняет комплексное значение; прямое [0]-индексирование
                    # PySpice-обёртки кастит к float и теряет мнимую часть (|H| → Re(H)).
                    value = complex(_np.asarray(analysis[str(net)])[0])
                    nodes_out[net]['mag'].append(float(abs(value)))
                    nodes_out[net]['phase_deg'].append(
                        float(_math.degrees(_math.atan2(value.imag, value.real)))
                    )
                except Exception:
                    nodes_out[net]['mag'].append(0.0)
                    nodes_out[net]['phase_deg'].append(0.0)
    except Exception:
        return None
    return {'freqs': used_freqs, 'nodes': nodes_out, 'engine': 'pyspice-ngspice'}
