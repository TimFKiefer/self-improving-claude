"""Pure score-comparison for the auto-loop ratchet.

The auto-loop accepts an edit only if visible-set scores `strictly_better`
the previous baseline (and, in β+, the held-out scores do not `regresses`).
Per SkillOpt §8.3: reject ties. Per §8.6 (verifier wall): gate only on
deterministic metrics — the LLM-judge `average_model` is advisory and is
not in the gating set.
"""
from __future__ import annotations

EPSILON = {
    "average_code": 0.05,
    "install_rate": 0.0,
    "fire_rate": 0.05,
    "average_restraint": 0.0,
}
GATING_METRICS = tuple(EPSILON.keys())


def _delta(new_v, old_v) -> float | None:
    """new - old, with None treated as 'no comparable value'.

    None→None: no change (returns 0.0)
    None→number: improvement (treat None as 0.0 baseline-floor)
    number→None: regression (treat None as 0.0 new-floor; the metric vanished)
    """
    if new_v is None and old_v is None:
        return 0.0
    if old_v is None:
        return float(new_v)  # gained signal where there was none
    if new_v is None:
        return -float(old_v)  # lost signal
    return float(new_v) - float(old_v)


def strictly_better(new: dict, old: dict) -> bool:
    """True iff at least one gating metric improved by > EPSILON and
    no gating metric regressed by > EPSILON. Ties (within-epsilon) are
    not improvements — per SkillOpt §8.3, reject ties.
    """
    saw_improvement = False
    for m in GATING_METRICS:
        d = _delta(new.get(m), old.get(m))
        if d > EPSILON[m]:
            saw_improvement = True
        elif d < -EPSILON[m]:
            return False  # regression on some gating metric → reject
    return saw_improvement


def regresses(new: dict, old: dict) -> bool:
    """True if any gating metric drops by > EPSILON. Used for the held-out
    confirmation gate: an edit that wins on visible-9 must not regress on
    held-out-3.
    """
    for m in GATING_METRICS:
        d = _delta(new.get(m), old.get(m))
        if d < -EPSILON[m]:
            return True
    return False
