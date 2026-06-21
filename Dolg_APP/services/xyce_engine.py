"""Xyce (Sandia industrial SPICE) адаптер — shell-out движок.

Берёт ту же сетевую модель, что NumPy MNA (`monte_carlo.scheme_to_circuit`: net 0 =
ground, R/C/L/V/D с net-индексами), генерит SPICE-нетлист (узлы = net-индексы, узел '0' =
земля), запускает `Xyce.exe` и парсит `.prn`-вывод. Узловые индексы совпадают с MNA/GNN,
поэтому напряжения отсюда прямо сопоставимы.

Xyce — настоящий индустриальный SPICE (Sandia), «золотой эталон» сильнее самодельной MNA.
Запускается внешним процессом (в отличие от in-process ngspice через PySpice).

Поиск бинаря: env `XYCE_EXE` → `Xyce` в PATH → стандартные места (Program Files, ~/Xyce_portable).
None, если Xyce не найден / схема не решается — caller падает на следующий движок.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

_RUN_TIMEOUT_S = 60


def xyce_path() -> str | None:
    """Путь к Xyce.exe: env XYCE_EXE → PATH → стандартные места. None если не найден."""
    env = os.environ.get('XYCE_EXE')
    if env and Path(env).exists():
        return env
    found = shutil.which('Xyce') or shutil.which('Xyce.exe')
    if found:
        return found
    candidates = [
        Path(os.path.expanduser('~')) / 'Xyce_portable' / 'bin' / 'Xyce.exe',
        Path('C:/Program Files/Xyce 7.10.0 NORAD/bin/Xyce.exe'),
        Path('/usr/local/bin/Xyce'),
        Path('/usr/bin/Xyce'),
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return None


def available() -> bool:
    return xyce_path() is not None


def _netlist_lines(scheme_data) -> tuple[list[str], int, str] | None:
    """scheme → (строки элементов нетлиста, n_nodes, имя первого V-источника) | None.

    Узлы = net-индексы (str), '0' = земля. Имя V-источника нужно для `.DC`-свипа.
    """
    from Dolg_APP.services import monte_carlo

    try:
        circuit = monte_carlo.scheme_to_circuit(scheme_data)
    except Exception:
        return None
    n_nodes = int(circuit.get('n_nodes') or 0)
    elements = circuit.get('elements') or []
    if n_nodes <= 1 or not elements:
        return None

    lines: list[str] = []
    counts: dict[str, int] = {}
    first_vsource = ''
    has_diode = False
    for elem in elements:
        etype = elem.get('type')
        nodes = elem.get('nodes') or []
        if len(nodes) < 2:
            continue
        na, nb = str(int(nodes[0])), str(int(nodes[1]))
        value = float(elem.get('value') or 0.0)
        counts[etype] = counts.get(etype, 0) + 1
        name = f'{etype}{counts[etype]}'
        if etype == 'R':
            lines.append(f'{name} {na} {nb} {value if value > 0 else 1e-3:g}')
        elif etype == 'V':
            lines.append(f'{name} {na} {nb} {value:g}')
            if not first_vsource:
                first_vsource = name
        elif etype == 'C':
            lines.append(f'{name} {na} {nb} {value if value > 0 else 1e-12:g}')
        elif etype == 'L':
            lines.append(f'{name} {na} {nb} {value if value > 0 else 1e-9:g}')
        elif etype == 'D':
            lines.append(f'{name} {na} {nb} DMOD')
            has_diode = True
    if not first_vsource:
        return None
    if has_diode:
        lines.append('.MODEL DMOD D')
    return lines, n_nodes, first_vsource


def _parse_prn(text: str, n_nodes: int) -> dict[int, float] | None:
    """Парсит .prn Xyce: хедер `Index V(1) V(2) ...` + строка значений → {net: voltage}."""
    rows = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith('End of')]
    if len(rows) < 2:
        return None
    header = rows[0].split()
    # колонка net k = индекс токена 'V(k)'
    col_of_net: dict[int, int] = {}
    for idx, token in enumerate(header):
        m = re.fullmatch(r'V\((\d+)\)', token)
        if m:
            col_of_net[int(m.group(1))] = idx
    data = rows[1].split()
    voltages: dict[int, float] = {0: 0.0}
    for net in range(1, n_nodes):
        col = col_of_net.get(net)
        try:
            voltages[net] = float(data[col]) if col is not None and col < len(data) else 0.0
        except ValueError, TypeError:
            voltages[net] = 0.0
    return voltages


def solve_dc(scheme_data) -> dict[int, float] | None:
    """DC-напряжения узлов через Xyce. {net_index: voltage}, net 0 = ground = 0. None если
    Xyce не найден / схема не решается."""
    exe = xyce_path()
    if not exe:
        return None
    built = _netlist_lines(scheme_data)
    if built is None:
        return None
    elem_lines, n_nodes, vsource = built

    # `.DC <vsrc> <v> <v> 1` даёт чистый .prn с рабочей точкой; печатаем все не-ground узлы.
    vval = next((ln.split()[-1] for ln in elem_lines if ln.startswith(vsource + ' ')), '0')
    prints = ' '.join(f'V({net})' for net in range(1, n_nodes))
    netlist = (
        'DOLG Xyce DC\n'
        + '\n'.join(elem_lines)
        + f'\n.DC {vsource} {vval} {vval} 1\n.PRINT DC {prints}\n.END\n'
    )

    try:
        tmpdir = tempfile.mkdtemp(prefix='dolg_xyce_')
        cir = Path(tmpdir) / 'circuit.cir'
        cir.write_text(netlist, encoding='ascii')
        subprocess.run(
            [exe, str(cir)],
            cwd=tmpdir,
            capture_output=True,
            timeout=_RUN_TIMEOUT_S,
            check=False,
        )
        prn = Path(tmpdir) / 'circuit.cir.prn'
        if not prn.exists():
            return None
        return _parse_prn(prn.read_text(encoding='utf-8', errors='ignore'), n_nodes)
    except OSError, subprocess.SubprocessError:
        return None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
