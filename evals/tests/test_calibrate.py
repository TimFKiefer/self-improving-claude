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


def test_run_reference_fix_ab_reverts_on_eval_error(monkeypatch):
    import evals.calibrate as cal
    calls = {"applied": False, "synced": False, "reverted": False}
    monkeypatch.setattr(cal, "apply_edit", lambda edit: (calls.__setitem__("applied", True) or (True, "ok")))
    monkeypatch.setattr(cal, "run_sync_skills", lambda: (calls.__setitem__("synced", True) or (True, "ok")))
    monkeypatch.setattr(cal, "git_reset_sync_paths", lambda: calls.__setitem__("reverted", True))
    def boom(*a, **k):
        raise RuntimeError("eval failed")
    monkeypatch.setattr(cal, "calibrate_fixture", boom)
    fixed, msg = cal.run_reference_fix_ab(
        "013-x", {"file": "f", "operation": "add"}, {"average_code": 4.0},
        n=1, skill_model="opus", judge_model="opus", effort="max")
    assert fixed is None
    assert calls["reverted"] is True   # MUST revert even though the eval raised


def test_ab_verdict_true_at_exact_ceiling_eight():
    from evals.calibrate import ab_verdict
    assert ab_verdict({"average_code": 4.0, "install_rate": 1.0},
                      {"average_code": 8.0, "install_rate": 1.0}) is True


def test_classify_tier_code_exactly_three_is_headroom():
    from evals.calibrate import classify_tier
    assert classify_tier({"average_code": 3.0, "install_rate": 1.0}) == "headroom"


def test_classify_tier_code_just_below_three_is_brick():
    from evals.calibrate import classify_tier
    assert classify_tier({"average_code": 2.99, "install_rate": 1.0}) == "brick"


def test_median_summary_even_count_averages_two_middle():
    from evals.calibrate import median_summary
    out = median_summary([{"install_rate": 0.0}, {"install_rate": 1.0}])
    assert out["install_rate"] == 0.5


def test_median_summary_empty_list_all_none():
    from evals.calibrate import median_summary
    out = median_summary([])
    assert out["average_code"] is None and out["install_rate"] is None
