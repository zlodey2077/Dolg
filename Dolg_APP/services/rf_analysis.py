"""S-параметрический анализ пассивных 2-портовых фильтров через scikit-rf.

Закрывает verify-находку (scikit-rf установлен, но не использовался). Даёт
честные RF-величины с опорным импедансом 50 Ом:
    - S21 (insertion loss) — передача вход→выход в дБ;
    - S11 (return loss) — отражение от входа в дБ;
    - частота среза −3 дБ относительно полосы пропускания.

Это нагруженный анализ (источник/нагрузка 50 Ом), а не наивная формула
1/(2πRC) холостого хода — то, что и считают в RF/РЭБ-практике. Аналитический
ненагруженный угол отдаётся отдельным полем для сравнения (учебная ценность).

Поддержанные топологии:
    rc_lowpass  — последовательный R + шунтирующий C
    rc_highpass — последовательный C + шунтирующий R
    lc_lowpass  — последовательный L + шунтирующий C
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_Z0 = 50.0
MIN_POINTS = 21
MAX_POINTS = 2001
DEFAULT_POINTS = 401

KINDS = {'rc_lowpass', 'rc_highpass', 'lc_lowpass'}


def _analytic_corner(kind: str, r: float | None, c: float | None, ell: float | None) -> float | None:
    """Ненагруженный угол (Гц) — для сравнения и авто-диапазона."""
    two_pi = 2.0 * np.pi
    if kind in ('rc_lowpass', 'rc_highpass') and r and c:
        return 1.0 / (two_pi * r * c)
    if kind == 'lc_lowpass' and ell and c:
        return 1.0 / (two_pi * np.sqrt(ell * c))
    return None


def _auto_range(corner: float | None) -> tuple[float, float]:
    """~2 декады вокруг угла; запасной диапазон если угол неизвестен."""
    if corner and corner > 0:
        return max(corner / 100.0, 1e-1), corner * 100.0
    return 10.0, 1e6


def _minus3db(freqs: np.ndarray, mag_db: np.ndarray, kind: str) -> float | None:
    """Частота, где |S21| падает на 3 дБ от пика полосы пропускания.

    low-pass: пик на низах → первый спад на 3 дБ снизу вверх.
    high-pass: пик на верхах → первый подъём до пика−3 дБ снизу вверх.
    """
    if mag_db.size == 0:
        return None
    peak = float(mag_db.max())
    threshold = peak - 3.0
    if kind == 'rc_highpass':
        above = np.where(mag_db >= threshold)[0]
        return float(freqs[above[0]]) if above.size else None
    # low-pass / band-pass: первый узел, где упали ниже порога
    below = np.where(mag_db <= threshold)[0]
    return float(freqs[below[0]]) if below.size else None


def analyze_filter(
    kind: str,
    *,
    r_ohm: float | None = None,
    c_farad: float | None = None,
    l_henry: float | None = None,
    f_start: float | None = None,
    f_stop: float | None = None,
    points: int = DEFAULT_POINTS,
    z0: float = DEFAULT_Z0,
) -> dict:
    """Считает S-параметры 2-портового фильтра через scikit-rf.

    Returns: {
        'kind', 'z0', 'points',
        'frequencies_hz': [...], 's21_db': [...], 's11_db': [...],
        'passband_db', 'cutoff_3db_hz', 'analytic_corner_hz',
        'algorithm',
    }
    """
    if kind not in KINDS:
        raise ValueError(f'unknown filter kind: {kind!r} (ожидается одно из {sorted(KINDS)})')

    import skrf
    from skrf.media import DefinedGammaZ0

    points = max(MIN_POINTS, min(MAX_POINTS, int(points)))
    corner = _analytic_corner(kind, r_ohm, c_farad, l_henry)
    if f_start is None or f_stop is None:
        f_start, f_stop = _auto_range(corner)
    f_start = max(float(f_start), 1e-3)
    f_stop = max(float(f_stop), f_start * 1.0001)

    freq = skrf.Frequency(f_start, f_stop, points, unit='hz')
    med = DefinedGammaZ0(frequency=freq, z0=z0)

    if kind == 'rc_lowpass':
        if not (r_ohm and c_farad):
            raise ValueError('rc_lowpass требует r_ohm и c_farad')
        net = med.resistor(float(r_ohm)) ** med.shunt_capacitor(float(c_farad))
    elif kind == 'rc_highpass':
        if not (r_ohm and c_farad):
            raise ValueError('rc_highpass требует r_ohm и c_farad')
        net = med.capacitor(float(c_farad)) ** med.shunt(med.resistor(float(r_ohm)) ** med.short())
    elif kind == 'lc_lowpass':
        if not (l_henry and c_farad):
            raise ValueError('lc_lowpass требует l_henry и c_farad')
        net = med.inductor(float(l_henry)) ** med.shunt_capacitor(float(c_farad))

    s21 = net.s[:, 1, 0]
    s11 = net.s[:, 0, 0]
    s21_db = 20.0 * np.log10(np.maximum(np.abs(s21), 1e-12))
    s11_db = 20.0 * np.log10(np.maximum(np.abs(s11), 1e-12))
    freqs = freq.f

    return {
        'kind': kind,
        'z0': z0,
        'points': points,
        'frequencies_hz': [round(float(f), 3) for f in freqs],
        's21_db': [round(float(v), 3) for v in s21_db],
        's11_db': [round(float(v), 3) for v in s11_db],
        'passband_db': round(float(s21_db.max()), 3),
        'cutoff_3db_hz': _minus3db(freqs, s21_db, kind),
        'analytic_corner_hz': round(float(corner), 3) if corner else None,
        'algorithm': 'scikit-rf S-parameters (2-port, 50Ω ref)',
    }
