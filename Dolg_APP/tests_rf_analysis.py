"""Tests for scikit-rf 2-port S-parameter filter analysis (verify-finding wiring)."""

from __future__ import annotations

import pytest

from Dolg_APP.services.rf_analysis import analyze_filter


def test_rc_lowpass_shape():
    r = analyze_filter('rc_lowpass', r_ohm=1000, c_farad=100e-9)
    s21 = r['s21_db']
    assert len(s21) == r['points']
    assert len(r['frequencies_hz']) == r['points']
    assert s21[0] > s21[-1]  # low-pass: пропускает низ, режет верх
    assert r['cutoff_3db_hz'] and r['cutoff_3db_hz'] > 0
    assert r['analytic_corner_hz'] and r['analytic_corner_hz'] > 0
    assert 'scikit-rf' in r['algorithm']


def test_rc_highpass_shape():
    r = analyze_filter('rc_highpass', r_ohm=1000, c_farad=100e-9)
    s21 = r['s21_db']
    assert s21[0] < s21[-1]  # high-pass: режет низ, пропускает верх
    assert r['cutoff_3db_hz'] and r['cutoff_3db_hz'] > 0


def test_lc_lowpass_is_steeper_than_rc():
    """LC (2-й порядок) спадает круче, чем RC (1-й порядок)."""
    lc = analyze_filter('lc_lowpass', l_henry=1e-3, c_farad=100e-9)
    rc = analyze_filter('rc_lowpass', r_ohm=1000, c_farad=100e-9)
    assert lc['s21_db'][0] > lc['s21_db'][-1]
    # На верхней границе диапазона LC ослабляет сильнее RC
    assert lc['s21_db'][-1] < rc['s21_db'][-1]


def test_larger_capacitor_lowers_cutoff():
    """Физика: больше C → ниже частота среза."""
    small = analyze_filter('rc_lowpass', r_ohm=1000, c_farad=10e-9, f_start=10, f_stop=2e6)
    large = analyze_filter('rc_lowpass', r_ohm=1000, c_farad=100e-9, f_start=10, f_stop=2e6)
    assert large['cutoff_3db_hz'] < small['cutoff_3db_hz']


def test_deterministic():
    a = analyze_filter('rc_lowpass', r_ohm=470, c_farad=47e-9)
    b = analyze_filter('rc_lowpass', r_ohm=470, c_farad=47e-9)
    assert a['s21_db'] == b['s21_db']
    assert a['cutoff_3db_hz'] == b['cutoff_3db_hz']


def test_points_clamped():
    r = analyze_filter('rc_lowpass', r_ohm=1000, c_farad=100e-9, points=999999)
    assert r['points'] <= 2001
    r2 = analyze_filter('rc_lowpass', r_ohm=1000, c_farad=100e-9, points=1)
    assert r2['points'] >= 21


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        analyze_filter('butterworth_7th', r_ohm=1, c_farad=1)


def test_missing_params_raise():
    with pytest.raises(ValueError):
        analyze_filter('rc_lowpass', r_ohm=1000)  # нет c_farad
    with pytest.raises(ValueError):
        analyze_filter('lc_lowpass', c_farad=1e-9)  # нет l_henry


def test_returns_s11_return_loss():
    r = analyze_filter('rc_lowpass', r_ohm=1000, c_farad=100e-9)
    assert 's11_db' in r and len(r['s11_db']) == r['points']
    # S11 — это отражение, |S11| ≤ 0 дБ для пассивной цепи
    assert max(r['s11_db']) <= 0.01
