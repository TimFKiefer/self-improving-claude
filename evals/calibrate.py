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


# Imported at module scope so monkeypatch can replace them on evals.calibrate.
from evals.auto_loop import (apply_edit, run_sync_skills, git_reset_sync_paths,
                             _run_eval_and_extract_result)

EVALS_DIR = Path(__file__).resolve().parent


def calibrate_fixture(fixture_id: str, *, n: int, skill_model: str,
                      judge_model: str, effort: str | None) -> dict:
    """Median summary over N single-fixture evals of the CURRENT orchestrator."""
    summaries = []
    for _ in range(n):
        summary, _ = _run_eval_and_extract_result(fixture_id, skill_model, judge_model, effort)
        summaries.append(summary)
    return median_summary(summaries)


def run_reference_fix_ab(fixture_id: str, reference_fix: dict, base_median: dict, *,
                         n: int, skill_model: str, judge_model: str,
                         effort: str | None) -> tuple[dict | None, str]:
    """Apply the reference fix, re-score N times, ALWAYS revert. Returns (fixed_median, msg)."""
    ok, reason = apply_edit(reference_fix)
    if not ok:
        return None, f"reference_fix invalid: {reason}"
    sync_ok, msg = run_sync_skills()
    if not sync_ok:
        git_reset_sync_paths()
        return None, f"sync failed: {msg}"
    fixed = None
    err_msg = None
    try:
        fixed = calibrate_fixture(fixture_id, n=n, skill_model=skill_model,
                                  judge_model=judge_model, effort=effort)
    except Exception as exc:
        err_msg = str(exc)
    finally:
        git_reset_sync_paths()   # never ship the fix — revert no matter what
    if err_msg is not None:
        return None, f"eval error: {err_msg}"
    return fixed, "ok"


def _load_reference_fix(entry: dict) -> dict | None:
    rel = entry.get("reference_fix")
    if not rel:
        return None
    path = EVALS_DIR / "fixtures" / entry["id"] / "reference_fix.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def calibrate_all(*, n: int, skill_model: str, judge_model: str,
                  effort: str | None, only: str | None, write: bool) -> list[dict]:
    from evals.fixtures_lib import load_dataset
    entries = load_dataset()
    results = []
    for entry in entries:
        fid = entry["id"]
        if only and fid != only:
            continue
        print(f"[calibrate] {fid}: sampling baseline (N={n})...", file=sys.stderr)
        base = calibrate_fixture(fid, n=n, skill_model=skill_model,
                                 judge_model=judge_model, effort=effort)
        expect_no_proposal = bool(entry.get("expect_no_proposal"))
        ab_passed = None
        ref = _load_reference_fix(entry)
        prelim = classify_tier(base, expect_no_proposal=expect_no_proposal)
        if ref is not None and prelim not in ("saturated", "restraint"):
            print(f"[calibrate] {fid}: running reference-fix A/B...", file=sys.stderr)
            fixed, msg = run_reference_fix_ab(fid, ref, base, n=n, skill_model=skill_model,
                                              judge_model=judge_model, effort=effort)
            ab_passed = ab_verdict(base, fixed) if fixed is not None else False
        tier = classify_tier(base, expect_no_proposal=expect_no_proposal, ab_passed=ab_passed)
        results.append({"id": fid, "tier": tier, "ab_passed": ab_passed, "median": base})
        print(f"[calibrate] {fid}: tier={tier} code={base.get('average_code')} ab={ab_passed}",
              file=sys.stderr)
    if write:
        _write_tiers(entries, results)
    return results


def _write_tiers(entries: list[dict], results: list[dict]) -> None:
    by_id = {r["id"]: r for r in results}
    for e in entries:
        r = by_id.get(e["id"])
        if not r:
            continue
        e["tier"] = r["tier"]
        e["rotation"] = (r["tier"] == "headroom")
    (EVALS_DIR / "dataset.json").write_text(
        json.dumps({"entries": entries}, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="evals.calibrate")
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--skill-runner", default="opus")
    p.add_argument("--judge", default="opus")
    p.add_argument("--effort", default="max")
    p.add_argument("--only", default=None, help="calibrate a single fixture id")
    p.add_argument("--write", action="store_true", help="write tier/rotation back to dataset.json")
    args = p.parse_args(argv)
    results = calibrate_all(n=args.n, skill_model=args.skill_runner, judge_model=args.judge,
                            effort=args.effort, only=args.only, write=args.write)
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
