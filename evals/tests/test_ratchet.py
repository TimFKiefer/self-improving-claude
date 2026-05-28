"""Tests for evals/ratchet.py — pure score comparison.

Covers: strictly_better (visible-set ratchet), regresses (held-out gate),
None handling, epsilon boundaries. Per SkillOpt §8.3 (reject ties) and §8.6
(deterministic gating only).
"""
from evals.ratchet import strictly_better, regresses


def _summary(code=8.0, install=0.8, fire=0.5, restraint=0.0):
    return {
        "average_code": code,
        "install_rate": install,
        "fire_rate": fire,
        "average_restraint": restraint,
    }


def test_strictly_better_one_metric_up_no_regression():
    old = _summary(code=8.0)
    new = _summary(code=8.5)  # +0.5 > epsilon 0.05
    assert strictly_better(new, old) is True


def test_strictly_better_rejects_tie_on_all_metrics():
    old = _summary()
    new = _summary()  # identical
    assert strictly_better(new, old) is False  # SkillOpt §8.3


def test_strictly_better_rejects_within_epsilon_tie():
    old = _summary(code=8.0)
    new = _summary(code=8.03)  # +0.03 < epsilon 0.05
    assert strictly_better(new, old) is False


def test_strictly_better_rejects_one_up_one_down():
    old = _summary(code=8.0, install=0.8)
    new = _summary(code=8.5, install=0.5)  # code +0.5 but install regressed
    assert strictly_better(new, old) is False


def test_strictly_better_accepts_one_up_others_within_epsilon():
    old = _summary(code=8.0, fire=0.5)
    new = _summary(code=8.5, fire=0.47)  # fire -0.03 within epsilon 0.05
    assert strictly_better(new, old) is True


def test_strictly_better_install_zero_epsilon_strict():
    """install_rate has epsilon=0 — any drop is a regression, any gain is improvement."""
    old = _summary(install=0.8)
    new = _summary(install=0.79)  # tiny drop, but epsilon=0
    assert strictly_better(new, old) is False


def test_strictly_better_restraint_zero_epsilon_strict():
    old = _summary(restraint=5.0)
    new = _summary(restraint=4.99)
    assert strictly_better(new, old) is False


def test_strictly_better_none_to_none_is_no_change():
    old = {"average_code": None, "install_rate": 0.8, "fire_rate": 0.5, "average_restraint": 0.0}
    new = {"average_code": None, "install_rate": 0.8, "fire_rate": 0.5, "average_restraint": 0.0}
    assert strictly_better(new, old) is False


def test_strictly_better_none_to_number_is_improvement():
    old = {"average_code": None, "install_rate": 0.8, "fire_rate": 0.5, "average_restraint": 0.0}
    new = _summary(code=7.0)
    assert strictly_better(new, old) is True


def test_strictly_better_number_to_none_is_regression():
    old = _summary(code=8.0)
    new = {"average_code": None, "install_rate": 0.8, "fire_rate": 0.5, "average_restraint": 0.0}
    assert strictly_better(new, old) is False


def test_regresses_catches_install_drop():
    old = _summary(install=1.0)
    new = _summary(install=0.95)
    assert regresses(new, old) is True


def test_regresses_ignores_within_epsilon_code_fluctuation():
    old = _summary(code=8.0)
    new = _summary(code=7.98)  # -0.02 within epsilon 0.05
    assert regresses(new, old) is False


def test_regresses_false_when_all_flat_or_better():
    old = _summary(code=8.0, install=0.8)
    new = _summary(code=8.5, install=0.85)
    assert regresses(new, old) is False


def test_regresses_catches_restraint_drop():
    old = _summary(restraint=10.0)
    new = _summary(restraint=5.0)
    assert regresses(new, old) is True
