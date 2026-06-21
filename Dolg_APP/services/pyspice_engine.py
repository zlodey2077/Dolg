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


def solve_dc(scheme_data: dict) -> dict[int, float] | None:
    """DC-напряжения узлов через ngspice. {net_index: voltage}, net 0 = ground = 0.

    None, если PySpice недоступен или схема не решается (вырожденная/без земли).
    Узловая нумерация = `monte_carlo.scheme_to_circuit` (совместимо с MNA и GNN).
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
        return {0: 0.0}

    try:
        circuit = Circuit('dolg')
        counts: dict[str, int] = {}
        has_source = False
        for elem in elements:
            etype = elem.get('type')
            nodes = elem.get('nodes') or []
            if len(nodes) < 2:
                continue
            na, nb = str(int(nodes[0])), str(int(nodes[1]))
            value = float(elem.get('value') or 0.0)
            counts[etype] = counts.get(etype, 0) + 1
            name = str(counts[etype])
            if etype == 'R':
                circuit.R(name, na, nb, value if value > 0 else 1e-3)
            elif etype == 'V':
                circuit.V(name, na, nb, value)
                has_source = True
            elif etype == 'C':
                circuit.C(name, na, nb, value if value > 0 else 1e-12)
            elif etype == 'L':
                circuit.L(name, na, nb, value if value > 0 else 1e-9)
            elif etype == 'D':
                # Базовая диодная модель (для DC; точные параметры — на доработку).
                circuit.model('DMOD', 'D', IS=1e-14, N=1.0)
                circuit.Diode(name, na, nb, model='DMOD')
        if not has_source:
            return None  # без источника DC-операционная точка тривиальна/вырождена

        analysis = circuit.simulator().operating_point()
    except Exception:
        return None

    voltages: dict[int, float] = {0: 0.0}
    for net in range(1, n_nodes):
        try:
            voltages[net] = float(analysis[str(net)][0])
        except Exception:
            voltages[net] = 0.0
    return voltages
