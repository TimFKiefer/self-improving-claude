"""Calibration layer (eval-suite-headroom).

Classifies each fixture by the CURRENT orchestrator's multi-sampled score into
saturated / headroom / brick, reusing the loop's own gating functions so
"calibration-headroom" means exactly "loop-improvable". New fixtures prove
closability via a reference-fix A/B (the fix is applied, scored, then reverted —
never shipped, so the loop must rediscover it).

CLI: python3 -m evals.calibrate [--n 5] [--skill-runner opus] [--judge opus]
     [--effort max] [--only <id>] [--write]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

from evals.ratchet import strictly_better
from evals.auto_loop import is_saturated

GATING = ("average_code", "install_rate", "fire_rate", "average_restraint")
NEAR_CEILING_CODE = 8.0
BRICK_CODE = 3.0


def median_summary(summaries: list[dict]) -> dict:
    """Per-metric median across N single-fixture summaries. None if all None."""
    out = {}
    for m in GATING:
        vals = [s.get(m) for s in summaries if s.get(m) is not None]
        out[m] = statistics.median(vals) if vals else None
    return out


def ab_verdict(base: dict, fixed: dict) -> bool:
    """The reference fix closes the gap iff it is strictly better on the gating
    metrics AND lands near ceiling. Reuses the loop's own strictly_better/is_saturated."""
    near_ceiling = is_saturated(fixed) or (fixed.get("average_code") or 0.0) >= NEAR_CEILING_CODE
    return strictly_better(fixed, base) and near_ceiling


def classify_tier(median_sum: dict, *, expect_no_proposal: bool = False,
                  ab_passed: bool | None = None) -> str:
    """Tier a fixture from its median summary.

    - expect_no_proposal fixtures are always `restraint`.
    - all gating metrics at ceiling → `saturated`.
    - reference-fix A/B decides headroom/brick when available.
    - otherwise (existing fixtures, no A/B): provisional by code floor.
    """
    if expect_no_proposal:
        return "restraint"
    if is_saturated(median_sum):
        return "saturated"
    if ab_passed is True:
        return "headroom"
    if ab_passed is False:
        return "brick"
    code = median_sum.get("average_code") or 0.0
    return "brick" if code < BRICK_CODE else "headroom"
