"""Tests for the pure calibration classifiers."""
from evals.calibrate import median_summary, classify_tier, ab_verdict


def _s(code=None, install=None, fire=None, restraint=None):
    return {"average_code": code, "install_rate": install,
            "fire_rate": fire, "average_restraint": restraint}


def test_median_summary_takes_per_metric_median():
    out = median_summary([_s(code=6.0), _s(code=8.0), _s(code=7.0)])
    assert out["average_code"] == 7.0

def test_median_summary_ignores_none_and_returns_none_if_all_none():
    out = median_summary([_s(code=6.0, fire=None), _s(code=8.0, fire=None)])
    assert out["average_code"] == 7.0
    assert out["fire_rate"] is None

def test_classify_restraint_when_expect_no_proposal():
    assert classify_tier(_s(code=10.0, install=1.0), expect_no_proposal=True) == "restraint"

def test_classify_saturated_when_all_gating_ceiling():
    # code=10, install=1, fire/restraint None → is_saturated true
    assert classify_tier(_s(code=10.0, install=1.0)) == "saturated"

def test_classify_headroom_when_not_saturated_and_no_ab():
    assert classify_tier(_s(code=6.0, install=1.0)) == "headroom"

def test_classify_brick_when_code_floor_and_no_ab():
    assert classify_tier(_s(code=0.0, install=None)) == "brick"

def test_classify_headroom_when_ab_passed():
    assert classify_tier(_s(code=6.0, install=1.0), ab_passed=True) == "headroom"

def test_classify_brick_when_ab_failed():
    assert classify_tier(_s(code=6.0, install=1.0), ab_passed=False) == "brick"

def test_ab_verdict_true_when_strictly_better_and_near_ceiling():
    base = _s(code=4.0, install=1.0)
    fixed = _s(code=9.0, install=1.0)
    assert ab_verdict(base, fixed) is True

def test_ab_verdict_false_when_better_but_not_near_ceiling():
    base = _s(code=4.0, install=1.0)
    fixed = _s(code=6.0, install=1.0)   # +2 but < 8 and not saturated
    assert ab_verdict(base, fixed) is False

def test_ab_verdict_false_on_tie():
    base = _s(code=8.0, install=1.0)
    fixed = _s(code=8.0, install=1.0)
    assert ab_verdict(base, fixed) is False
