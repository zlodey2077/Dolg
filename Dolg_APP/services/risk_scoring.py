"""Fuzzy risk scoring for engineering review.

The deterministic review remains the source of truth. scikit-fuzzy only turns
several weak signals into a softer "risk posture" for reports and assistant
wording.
"""

from __future__ import annotations

from typing import Any


def assess_fuzzy_project_risk(*, thermal_margin_c=None, bom_risk_count=0, floating_count=0, warning_count=0) -> dict[str, Any]:
    import numpy as np
    import skfuzzy as fuzz

    thermal_margin = 100 if thermal_margin_c is None else max(0, min(100, float(thermal_margin_c)))
    bom_risk = max(0, min(10, int(bom_risk_count)))
    floating = max(0, min(10, int(floating_count)))
    warnings = max(0, min(20, int(warning_count)))

    x_margin = np.arange(0, 101, 1)
    x_count = np.arange(0, 21, 1)
    x_risk = np.arange(0, 101, 1)

    low_margin = fuzz.trimf(x_margin, [0, 0, 25])
    ok_margin = fuzz.trimf(x_margin, [15, 55, 100])
    many_issues = fuzz.trimf(x_count, [2, 10, 20])
    low_risk = fuzz.trimf(x_risk, [0, 0, 35])
    medium_risk = fuzz.trimf(x_risk, [20, 50, 80])
    high_risk = fuzz.trimf(x_risk, [60, 100, 100])

    margin_bad = fuzz.interp_membership(x_margin, low_margin, thermal_margin)
    margin_ok = fuzz.interp_membership(x_margin, ok_margin, thermal_margin)
    issue_load = min(20, bom_risk * 2 + floating * 3 + warnings)
    issues_bad = fuzz.interp_membership(x_count, many_issues, issue_load)

    activation_low = max(0.0, min(margin_ok, 1.0 - issues_bad))
    activation_medium = max(min(margin_bad, 0.65), min(issues_bad, 0.65))
    activation_high = max(margin_bad * 0.9, issues_bad)

    aggregated = np.fmax(
        activation_low * low_risk,
        np.fmax(activation_medium * medium_risk, activation_high * high_risk),
    )
    if not np.any(aggregated):
        score = 0.0
    else:
        score = float(fuzz.defuzz(x_risk, aggregated, 'centroid'))

    if score >= 70:
        label = 'critical'
    elif score >= 45:
        label = 'risk'
    elif score >= 25:
        label = 'needs_review'
    else:
        label = 'ready'

    return {
        'ok': True,
        'engine': 'scikit-fuzzy',
        'score': round(score, 2),
        'label': label,
        'inputs': {
            'thermal_margin_c': thermal_margin_c,
            'bom_risk_count': bom_risk_count,
            'floating_count': floating_count,
            'warning_count': warning_count,
            'issue_load': issue_load,
        },
    }
