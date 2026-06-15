"""Toolkit локального AI-ассистента: вызывает инженерные движки и возвращает
готовые строки + источник для вшивания в ответ rule_ai.

Принцип «compute-don't-guess»: число берётся из реального движка (MNA, Monte
Carlo, P=U²/R), а не выдумывается языковой моделью. Полностью self-hosted —
никаких внешних API. Каждый блок помечает источник (expert-first).
"""

from __future__ import annotations

from typing import Any


def compute_dc(scheme_data: dict | None) -> dict[str, Any]:
    """DC-решение схемы через NumPy MNA. {ok, voltages, currents, source} либо {ok:False}."""
    try:
        from .monte_carlo import scheme_to_circuit, solve_dc

        circuit = scheme_to_circuit(scheme_data or {})
        if circuit['n_nodes'] <= 1 or not circuit['elements']:
            return {'ok': False, 'reason': 'no_circuit'}
        result = solve_dc(circuit)
        return {
            'ok': True,
            'voltages': result['voltages'],
            'currents': result['currents'],
            'circuit': circuit,
            'source': 'MNA (NumPy solve_dc)',
        }
    except Exception as exc:
        return {'ok': False, 'reason': str(exc)}


def dc_voltage_lines(scheme_data: dict | None, *, limit: int = 6) -> list[str]:
    """Строки с реальными напряжениями узлов + токами источников (DC)."""
    dc = compute_dc(scheme_data)
    if not dc['ok']:
        return []
    lines = [f'узел {net}: {v:.3f} В' for net, v in sorted(dc['voltages'].items()) if net != 0]
    lines = lines[:limit]
    for vid, current in (dc['currents'] or {}).items():
        lines.append(f'ток через {vid}: {current * 1000:.2f} мА')
    if lines:
        lines.append(f'источник: {dc["source"]}')
    return lines


def power_lines(scheme_data: dict | None, *, limit: int = 6) -> list[str]:
    """Рассеиваемая мощность на резисторах из DC-решения: P = ΔU²/R."""
    dc = compute_dc(scheme_data)
    if not dc['ok']:
        return []
    voltages = dc['voltages']
    rows: list[tuple[str, float]] = []
    for elem in dc['circuit']['elements']:
        if elem['type'] != 'R' or elem['value'] <= 0:
            continue
        n1, n2 = elem['nodes']
        delta = abs(voltages.get(n1, 0.0) - voltages.get(n2, 0.0))
        power = delta * delta / elem['value']
        rows.append((str(elem['id']), power))
    if not rows:
        return []
    rows.sort(key=lambda item: -item[1])
    lines = []
    for rid, power in rows[:limit]:
        lines.append(f'{rid}: {power * 1000:.1f} мВт' if power < 1 else f'{rid}: {power:.2f} Вт')
    lines.append('источник: P = ΔU²/R по DC-решению (MNA)')
    return lines


def derating_lines(scheme_data: dict | None, *, limit: int = 6) -> list[str]:
    """Запас по мощности резисторов: рассеиваемая P (из MNA) против номинальной
    мощности TDP из каталога + вердикт derating. Честно: на реальных `tdp_w`
    каталога и расчётной P, без угаданных тепловых сопротивлений.
    """
    dc = compute_dc(scheme_data)
    if not dc['ok']:
        return []
    rated_by_id: dict[str, float] = {}
    for comp in _components(scheme_data):
        params = comp.get('catalog_parameters') or comp.get('parameters') or {}
        try:
            rated_by_id[str(comp.get('id'))] = float(
                params.get('tdp_w') or params.get('power_w') or params.get('power') or 0
            )
        except TypeError, ValueError:
            rated_by_id[str(comp.get('id'))] = 0.0
    voltages = dc['voltages']
    rows: list[tuple[str, float, float]] = []
    for elem in dc['circuit']['elements']:
        if elem['type'] != 'R' or elem['value'] <= 0:
            continue
        n1, n2 = elem['nodes']
        delta = abs(voltages.get(n1, 0.0) - voltages.get(n2, 0.0))
        power = delta * delta / elem['value']
        rated = rated_by_id.get(str(elem['id'])) or 0.25  # дефолт 1/4 Вт
        rows.append((str(elem['id']), power, rated))
    if not rows:
        return []
    rows.sort(key=lambda r: -(r[1] / r[2] if r[2] else 0.0))
    lines: list[str] = []
    worst = 0.0
    for rid, power, rated in rows[:limit]:
        load = (power / rated * 100.0) if rated else 0.0
        worst = max(worst, load)
        # Доменные пороги derating-factor (§AK): ≤50% промышл., ≤80% IPC-9592B.
        if load >= 100:
            verdict = 'перегрузка'
        elif load >= 80:
            verdict = 'предел >80%'
        elif load >= 50:
            verdict = 'внимание >50%'
        else:
            verdict = 'норма'
        pstr = f'{power * 1000:.0f} мВт' if power < 1 else f'{power:.2f} Вт'
        lines.append(f'{rid}: {pstr} / {rated:.2f} Вт ном → {load:.0f}% ({verdict})')
    if worst >= 100:
        lines.append('⚠ перегрузка по мощности — увеличить номинал/корпус резистора')
    elif worst >= 80:
        lines.append('выше 80% (предел high-density по IPC-9592B) — поднять номинал/корпус')
    elif worst >= 50:
        lines.append('рекомендация: держать нагрузку <50% номинала (промышл. derating-запас)')
    lines.append('источник: P=ΔU²/R (MNA) против tdp_w; derating ≤50% (промышл.)/≤80% (IPC-9592B)')
    return lines


def thermal_lines(scheme_data: dict | None, *, limit: int = 6) -> list[str]:
    """Оценка температуры кристалла диодов/LED: T_j = Ta + P·R_θ, где P = Vd·Id из
    нелинейного MNA (реальные Vd, Id), R_θ — дефолт по типу (оценка, не паспорт).
    Флаг при приближении к T_j_max. Пусто, если диодов/LED в схеме нет (§Y)."""
    dc = compute_dc(scheme_data)
    if not dc['ok']:
        return []
    voltages = dc['voltages']
    currents = dc.get('currents') or {}
    ta = 25.0  # окружающая, °C
    # R_θ (j-a, °C/Вт) и T_j_max по типу — дефолтные оценки без радиатора.
    led = {'rth': 300.0, 'tjmax': 110.0}
    diode = {'rth': 100.0, 'tjmax': 150.0}
    rows = []
    for elem in dc['circuit']['elements']:
        if elem.get('type') != 'D':
            continue
        n1, n2 = elem['nodes']
        vd = abs(voltages.get(n1, 0.0) - voltages.get(n2, 0.0))
        idc = abs(float(currents.get(str(elem['id']), 0.0)))
        power = vd * idc
        is_led = str(elem.get('label') or '').upper().startswith('LED')
        spec = led if is_led else diode
        tj = ta + power * spec['rth']
        rows.append((str(elem['id']), power, tj, spec['tjmax']))
    if not rows:
        return []
    rows.sort(key=lambda r: -r[2])
    lines = []
    worst_ratio = 0.0
    for rid, power, tj, tjmax in rows[:limit]:
        worst_ratio = max(worst_ratio, tj / tjmax if tjmax else 0.0)
        flag = 'перегрев' if tj >= tjmax else ('близко к пределу' if tj >= 0.85 * tjmax else 'норма')
        pstr = f'{power * 1000:.1f} мВт' if power < 1 else f'{power:.2f} Вт'
        lines.append(f'{rid}: P={pstr} → T_j≈{tj:.0f}°C (макс {tjmax:.0f}, {flag})')
    if worst_ratio >= 1.0:
        lines.append('⚠ перегрев кристалла — снизить ток/добавить теплоотвод')
    elif worst_ratio >= 0.85:
        lines.append('близко к T_j_max — уменьшить ток или улучшить охлаждение')
    lines.append('источник: T_j=Ta+P·R_θ (P=Vd·Id из нелинейного MNA); R_θ — дефолт-оценка по типу')
    return lines


def regulator_lines(scheme_data: dict | None) -> list[str]:
    """Линейный стабилизатор (78xx/LM317/КРЕН): проверка dropout (Vin−Vout) и
    рассеяния P=(Vin−Vout)·Iнагр. Детект по типу/метке; Vout из параметра либо
    из 78xx-цифр (7805→5В). Пусто, если регулятора/Vin нет (§AL)."""
    import re

    from shop.component_validation import parse_engineering_value

    comps = _components(scheme_data)
    reg = None
    vout = None
    pat78 = re.compile(r'78(\d\d)')
    label_re = re.compile(r'(78\d\d|79\d\d|lm3\d\d|кр142|крен|regulator|стабилиз|ldo)', re.IGNORECASE)
    for c in comps:
        label = str(c.get('label') or '')
        ctype = (c.get('type') or '').lower()
        params = c.get('catalog_parameters') or c.get('parameters') or {}
        if (
            ctype in ('regulator', 'ldo')
            or label_re.search(label)
            or (ctype == 'ic' and label_re.search(label))
        ):
            reg = c
            try:
                vout = float(params.get('vout') or params.get('output_voltage') or c.get('vout') or 0) or None
            except TypeError, ValueError:
                vout = None
            m = pat78.search(label)
            if vout is None and m:
                vout = float(m.group(1))  # 7805 → 05 → 5 В
            break
    if not reg:
        return []
    src = _first_of(scheme_data, 'battery')
    vin = parse_engineering_value('voltage', src.get('voltage') or src.get('value')) if src else None
    label = str(reg.get('label') or reg.get('type') or 'регулятор')
    lines: list[str] = []
    if vin and vout:
        dropout = vin - vout
        lines.append(f'{label}: Vin={vin:g} В, Vout={vout:g} В → dropout = {dropout:.2f} В')
        if dropout < 2.0:
            lines.append(
                f'⚠ dropout {dropout:.2f} В < ~2 В — стандартный 78xx не стабилизирует (нужен LDO или выше Vin)'
            )
        else:
            lines.append('dropout ОК (≥2 В для стандартного линейного)')
        lines.append(
            f'рассеяние P = (Vin−Vout)·Iнагр = {dropout:.2f}·I Вт → радиатор при больших токах (термика §Y)'
        )
        lines.append('источник: формула линейного стабилизатора (dropout + P=(Vin−Vout)·I)')
    elif vout:
        lines.append(f'{label}: Vout = {vout:g} В (добавьте источник Vin для проверки dropout)')
    return lines


def _components(scheme_data: dict | None):
    return (scheme_data or {}).get('components') or []


def _first_of(scheme_data: dict | None, ctype: str):
    return next((c for c in _components(scheme_data) if (c.get('type') or '').lower() == ctype), None)


def formula_compute(scheme_data: dict | None, topology: str | None) -> list[str]:
    """Считает формулу по реальным значениям схемы (Vout / fc / Iled).

    Compute-don't-guess: число берётся из движка/арифметики по номиналам, а не
    из текста. Пустой список, если данных не хватает."""
    import math

    from shop.component_validation import parse_engineering_value

    lines: list[str] = []
    if topology == 'voltage_divider':
        dc = compute_dc(scheme_data)
        if dc['ok']:
            node_v = [f'{v:.3f} В' for net, v in sorted(dc['voltages'].items()) if net != 0]
            if node_v:
                lines.append('Vout = Vin·R2/(R1+R2); напряжения узлов (MNA): ' + ', '.join(node_v))
                lines.append('источник: MNA (NumPy solve_dc)')
    elif topology == 'rc_network':
        r = _first_of(scheme_data, 'resistor')
        c = _first_of(scheme_data, 'capacitor')
        if r and c:
            r_ohm = parse_engineering_value('resistance', r.get('resistance') or r.get('value'))
            c_uf = parse_engineering_value('capacitance', c.get('capacitance') or c.get('value'))
            if r_ohm and c_uf and r_ohm > 0 and c_uf > 0:
                fc = 1.0 / (2 * math.pi * r_ohm * (c_uf * 1e-6))
                lines.append(f'fc = 1/(2π·R·C) ≈ {fc:,.1f} Гц (R={r_ohm:g} Ом, C={c_uf:g} мкФ)')
                lines.append('источник: расчёт по номиналам (точка −3 дБ)')
    elif topology == 'led_indicator':
        b = _first_of(scheme_data, 'battery')
        led = _first_of(scheme_data, 'led')
        r = _first_of(scheme_data, 'resistor')
        if b and led and r:
            vin = parse_engineering_value('voltage', b.get('voltage') or b.get('value'))
            vf = parse_engineering_value('voltage', led.get('vf') or led.get('forward_voltage') or 2)
            r_ohm = parse_engineering_value('resistance', r.get('resistance') or r.get('value'))
            if vin and vf is not None and r_ohm and r_ohm > 0 and vin > vf:
                iled = (vin - vf) / r_ohm
                lines.append(
                    f'Iled = (Vin−Vf)/R ≈ {iled * 1000:.1f} мА (Vin={vin:g}В, Vf={vf:g}В, R={r_ohm:g}Ом)'
                )
                lines.append('источник: закон Ома по номиналам')
    return lines


_NEURAL_ADVISOR = None


def neural_hint_lines(scheme_data: dict | None) -> list[str]:
    """Локальная tiny-AI (PyTorch): топология/риск/следующий компонент.

    Expert-first: это ПОДСКАЗКА, финальный контроль — за правилами и человеком.
    Пустой список, если torch/модель недоступны или схема пустая."""
    global _NEURAL_ADVISOR
    if not scheme_data or not scheme_data.get('components'):
        return []
    try:
        from Dolg_APP.ml.neural import NeuralCircuitAdvisor, torch_available

        if not torch_available():
            return []
        if _NEURAL_ADVISOR is None:
            _NEURAL_ADVISOR = NeuralCircuitAdvisor()
        pred = _NEURAL_ADVISOR.predict(scheme_data or {})
    except Exception:
        return []
    if not isinstance(pred, dict) or not pred.get('topology'):
        return []
    lines = [f'топология: {pred["topology"]} ({float(pred.get("topology_confidence") or 0):.2f})']
    if pred.get('risk_label'):
        lines.append(f'риск: {pred["risk_label"]} ({float(pred.get("risk_score") or 0):.2f})')
    nexts = pred.get('next_components') or []
    if nexts and isinstance(nexts[0], dict):
        top = nexts[0]
        lines.append(
            f'следующий компонент: {top.get("component_type")} ({float(top.get("confidence") or 0):.2f})'
        )
    if pred.get('agreement_score') is not None:
        lines.append(
            f'согласие с expert-baseline: {float(pred["agreement_score"]):.2f} ({pred.get("confidence_policy")})'
        )
    lines.append('источник: локальная tiny-AI (PyTorch) — подсказка, не вердикт')
    return lines


def rf_filter_lines(scheme_data: dict | None) -> list[str]:
    """S-параметры RC-фильтра через scikit-rf: частота среза −3 дБ + полоса.

    Только если в схеме есть резистор и конденсатор. Compute-don't-guess."""
    from shop.component_validation import parse_engineering_value

    r = _first_of(scheme_data, 'resistor')
    c = _first_of(scheme_data, 'capacitor')
    if not (r and c):
        return []
    r_ohm = parse_engineering_value('resistance', r.get('resistance') or r.get('value'))
    c_uf = parse_engineering_value('capacitance', c.get('capacitance') or c.get('value'))
    if not (r_ohm and c_uf and r_ohm > 0 and c_uf > 0):
        return []
    try:
        from .rf_analysis import analyze_filter

        result = analyze_filter('rc_lowpass', r_ohm=r_ohm, c_farad=c_uf * 1e-6)
    except Exception:
        return []
    cutoff = result.get('cutoff_3db_hz')
    lines = []
    if cutoff:
        lines.append(f'RC low-pass: срез −3 дБ ≈ {cutoff:,.0f} Гц (нагруженный, 50 Ом)')
    if result.get('analytic_corner_hz'):
        lines.append(f'ненагруженный угол 1/(2πRC) ≈ {result["analytic_corner_hz"]:,.0f} Гц')
    lines.append(f'полоса пропускания (S21): {result.get("passband_db", 0):.1f} дБ')
    lines.append('источник: scikit-rf S-параметры (2-порт)')
    return lines


def tolerance_lines(scheme_data: dict | None, *, tolerance: float = 0.05) -> list[str]:
    """Огибающая напряжений при разбросе номиналов (worst-case + вердикт)."""
    try:
        from .monte_carlo import run_tolerance_analysis

        report = run_tolerance_analysis(scheme_data or {}, iterations=2000, tolerance=tolerance, seed=42)
    except Exception:
        return []
    worst = (report.get('worst_case') or {}).get('nodes') or {}
    nodes = sorted(
        ((net, data) for net, data in worst.items() if net != '0'),
        key=lambda kv: -(kv[1].get('span') or 0),
    )
    lines = [
        f'узел {net}: {data["min"]:.2f}…{data["max"]:.2f} В (ном. {data["nominal"]:.2f})'
        for net, data in nodes[:4]
    ]
    if not lines:
        return []
    verdict = (report.get('paranoia') or {}).get('summary')
    if verdict:
        lines.append(f'вердикт: {verdict}')
    lines.append(f'источник: NumPy Monte Carlo + worst-case (±{int(tolerance * 100)}%)')
    return lines


def pcb_drc_lines(scheme_data: dict | None, *, limit: int = 6) -> list[str]:
    """DRC разведённой платы (IPC-2221): из scheme_data строим layout и проверяем
    ширину дорожек, зазоры между нетами и отступ от края. Compute-don't-guess —
    findings из движка pcb_drc с rule_id/рекомендацией."""
    try:
        from ..pcb_layout import compute_pcb_layout
        from .pcb_drc import run_pcb_drc

        layout = compute_pcb_layout(scheme_data or {})
        if not layout.get('traces'):
            return []
        report = run_pcb_drc(layout)
    except Exception:
        return []
    summary = report.get('summary') or {}
    findings = report.get('findings') or []
    if not findings:
        return [
            f'PCB DRC: нарушений нет ({summary.get("checked_traces", 0)} трасс проверено)',
            'источник: IPC-2221 (ширина/зазор/край)',
        ]
    sev = {'error': 'ошибка', 'warning': 'предупр.', 'info': 'инфо'}
    lines = [f'[{sev.get(f.get("severity"), "инфо")}] {f.get("message")}' for f in findings[:limit]]
    lines.append(f'итог: {summary.get("errors", 0)} ошибок, {summary.get("warnings", 0)} предупр.')
    lines.append('источник: IPC-2221 (current capacity / conductor spacing)')
    return lines


def transient_lines(scheme_data: dict | None) -> list[str]:
    """Переходный процесс: если в схеме есть C/L, прогоняем solve_transient и
    сообщаем эмпирическую постоянную времени (до 63% установившегося) и время
    установления (95%). Compute-don't-guess — числа из движка, не из формул."""
    try:
        import statistics

        from .monte_carlo import scheme_to_circuit, solve_transient

        circuit = scheme_to_circuit(scheme_data or {})
        elements = circuit.get('elements') or []
        caps = [e for e in elements if e['type'] == 'C']
        inds = [e for e in elements if e['type'] == 'L']
        if not caps and not inds:
            return []
        res = [e['value'] for e in elements if e['type'] == 'R' and e['value'] > 0]
        r_typ = statistics.median(res) if res else 1000.0
        if caps:
            tau_guess = max(e['value'] for e in caps) * r_typ
        else:
            tau_guess = max(e['value'] for e in inds) / max(r_typ, 1e-9)
        tau_guess = min(max(tau_guess, 1e-9), 100.0)
        tr = solve_transient(circuit, t_stop=8 * tau_guess, dt=tau_guess / 50)
    except Exception:
        return []
    times = tr.get('time') or []
    series = tr.get('voltages') or {}
    if len(times) < 3:
        return []
    best_node, best_swing, best = None, -1.0, None
    for node, vals in series.items():
        if node == 0 or not vals:
            continue
        swing = max(vals) - min(vals)
        if swing > best_swing:
            best_node, best_swing, best = node, swing, vals
    if best is None or best_swing < 1e-6:
        return []
    start, final = best[0], best[-1]

    def _time_to(frac: float) -> float:
        target = start + frac * (final - start)
        for t, v in zip(times, best):
            if (final >= start and v >= target) or (final < start and v <= target):
                return t
        return times[-1]

    return [
        f'узел {best_node}: {start:.2f} → {final:.2f} В (переходный процесс)',
        f'постоянная времени τ ≈ {_time_to(0.632) * 1000:.3g} мс (63%)',
        f'установление 95% за ≈ {_time_to(0.95) * 1000:.3g} мс',
        'источник: транзиент Backward Euler (MNA solve_transient)',
    ]
