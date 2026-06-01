# Eval Suite with Headroom — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the auto-loop something to optimize — a calibrated eval suite where the current orchestrator scores mid-range on fixtures whose gap a bounded instruction edit can provably close, so a run can move a number.

**Architecture:** A calibration layer (`evals/calibrate.py`) scores every fixture with the current orchestrator (N=5 median) and classifies it `saturated` / `headroom` / `brick` using the loop's *own* gating functions (`is_saturated`, `strictly_better`). Six new fixtures are authored against orchestrator weaknesses **proven real by the v0.5.0 reverted keeps** (i3/i13/i26/i29/i41 — kept-then-noise-reverted, so the gaps persist and the fixing edit is known). Each new fixture ships a **withheld** `reference_fix` used once in an A/B to prove closability, then reverted. The loop's `pick_target` is restricted to `headroom` fixtures; saturated ones stay as regression guards.

**Tech Stack:** Python 3.10+ stdlib (`statistics`, `json`, `argparse`), `pytest`. Reuses `evals/ratchet.py` (`strictly_better`), `evals/auto_loop.py` (`is_saturated`, `apply_edit`, `run_sync_skills`, `git_reset_sync_paths`, `_run_eval_and_extract_result`), `evals/run.py`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-01-eval-suite-headroom-design.md`

---

## Knowledge-base grounding (carry into every task)

- **`eval-methodology.md` § Variance budget** — single-shot scores carry ±3 pts/fixture. → Calibration **must multi-sample** (N=5, median). One-shot tiering would mis-classify (`010` proves it: 7.14 nominal, re-measures 10.0).
- **`prompt-engineering.md` §8.6 (verifier wall)** — gate only on deterministic metrics; the LLM judge is advisory. → Tiering classifies on the **deterministic gating composite** (`average_code`, `install_rate`, `fire_rate`, `average_restraint` via `is_saturated`), **never** the model judge.
- **`prompt-engineering.md` §8.1 (bounded edits, 4–8)** — → every `reference_fix` is a bounded edit (≤ 8 `new_content` lines, `add`/`delete`/`replace`, slow-state allowlist) — the *same* envelope the loop's proposer works in. A reference fix outside that envelope would prove a fix the loop can't reach.
- **`prompt-engineering.md` §2 (negative imperatives) / §3 (decision boundaries) / §5 ("explain why")** — → reference fixes are themselves prompt edits; author them to that standard (name the default to suppress + the alternative; pair when-to-use with when-NOT; example additions carry a "why" line).
- **`agentic-patterns.md` §2c (parallelization)** — calibration cells are independent; ~120 sequential opus+max evals is many hours. → Build sequential (project convention) but `log` progress per fixture; flag parallelization as a future optimization.
- **`hooks-and-sdk.md` §4 (Pre blocks / Post can't), §5 (tool_input shape differs per tool)** & **`settings-and-permissions.md` §3 (permissions-vs-hooks decision table)** — the semantic source for the new fixtures' `expected_hook_traits` and reference fixes.

---

## Refinements to the spec (from the knowledge grounding — flag to user)

Two deliberate refinements the deep read forced. Both make calibration use the **exact gates the loop uses**, and both are noted here rather than silently changing the approved spec:

1. **Tier on the gating composite, not a code-only band.** Spec §4.1 described tiers via a "median code 3–<8" band. Refined: `saturated = is_saturated(median_summary)` (all four gating metrics at ceiling — reuses the loop's own function); `ab_verdict` reuses `strictly_better` + `is_saturated`. Rationale: §8.6 — the loop optimizes the gating composite, so headroom must be defined on that composite, and reusing the loop's functions guarantees "calibration-headroom" ⇔ "loop-improvable."

2. **The taxonomy is re-anchored to gating checks (the spec's §4.2 axes are replaced).** The spec listed *multi-rule completeness* and *composed multi-hook*. Their difficulty lives in `required_rules` **coverage**, which `grade_code` computes **separately from** the gating `average_code` mean — so the loop cannot move it. A coverage-only fixture is **brick-by-construction**. Refined taxonomy: six fixtures each anchored to a metric the loop actually gates (form/event/matcher/rationale → `average_code`; passthrough → `fire_rate`; over-block → `average_restraint`), and each **grounded in a specific v0.5.0 reverted keep** that proves the gap is real *and* instruction-fixable (the keep helped before it was noise-reverted). See Task 5.

---

## File structure

| File | Create / Modify | Responsibility |
|---|---|---|
| `evals/calibrate.py` | **Create** | Pure: `median_summary`, `classify_tier`, `ab_verdict`. Orchestration: `calibrate_fixture` (N-sample), `run_reference_fix_ab` (apply→sync→sample→**revert**), `calibrate_all` (writes tiers to dataset.json + report). CLI `python3 -m evals.calibrate`. |
| `evals/tests/test_calibrate.py` | **Create** | Unit tests for the three pure functions. |
| `evals/auto_loop.py` | Modify | `pick_target` gains `eligible_ids`; `main` computes it from dataset tiers + guards "no headroom fixtures". |
| `evals/tests/test_auto_loop.py` | Modify (append) | `pick_target` eligible-ids filtering tests. |
| `evals/dataset.json` | Modify | Add `tier`/`rotation` per entry (written by calibrate); add 6 new entries (013–018) with `reference_fix`. |
| `evals/fixtures/01{3,4,5,6,7,8}-*/` | **Create** | `description.md`, `expected_traits.json`, `project/`, `chat.md`/`telemetry.jsonl`, `reference_fix.json` per new fixture. |
| `evals/results/README.md`, `CHANGELOG.md`, `docs/ROADMAP.md` | Modify | Record calibration + payoff results, version bump. |

**Phasing:** A (engine, Tasks 1–2) → B (loop integration, Task 3) → C (audit existing, Task 4) → D (author fixtures, Task 5) → E (calibrate new, Task 6) → F (gated payoff + finalize, Task 7). Tasks 4, 6, 7 are operational (spend money / run the orchestrator); gate Task 7 on explicit go-ahead.

---

## Task 1: Calibration pure functions

**Files:** Create `evals/calibrate.py`; Create `evals/tests/test_calibrate.py`.

- [ ] **Step 1: Write the failing tests** — create `evals/tests/test_calibrate.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest evals/tests/test_calibrate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals.calibrate'`

- [ ] **Step 3: Implement the pure functions** — create `evals/calibrate.py` with this top section:

```python
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
```

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m pytest evals/tests/test_calibrate.py -v`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add evals/calibrate.py evals/tests/test_calibrate.py
git commit -m "feat(headroom): calibration pure functions (tier on gating composite, A/B)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Calibration orchestration + CLI

**Files:** Modify `evals/calibrate.py` (append orchestration + `main`). Test: append one revert-safety test to `evals/tests/test_calibrate.py`.

> **Testing note:** the per-fixture eval calls hit the real orchestrator (claude-cli) and aren't unit-mocked — consistent with the project's existing decision (see `test_auto_loop.py` bottom note). The pure classifiers are covered in Task 1. The one unit test here verifies `run_reference_fix_ab` **always reverts** even when the eval raises, because a leaked reference fix would silently ship the answer key into the orchestrator.

- [ ] **Step 1: Write the failing revert-safety test** — append to `evals/tests/test_calibrate.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest evals/tests/test_calibrate.py::test_run_reference_fix_ab_reverts_on_eval_error -v`
Expected: FAIL — `AttributeError: module 'evals.calibrate' has no attribute 'run_reference_fix_ab'`

- [ ] **Step 3: Implement the orchestration** — append to `evals/calibrate.py`:

```python
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
    try:
        fixed = calibrate_fixture(fixture_id, n=n, skill_model=skill_model,
                                  judge_model=judge_model, effort=effort)
    finally:
        git_reset_sync_paths()   # never ship the fix — revert no matter what
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
        results.append({"id": fid, "tier": tier, "ab_passed": ab_passed,
                        "median": base})
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest evals/tests/test_calibrate.py -v` → PASS (12 tests).
Run: `python3 -m pytest evals/tests/ -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add evals/calibrate.py evals/tests/test_calibrate.py
git commit -m "feat(headroom): calibration orchestration + CLI (reference-fix A/B with guaranteed revert)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Restrict the loop's `pick_target` to headroom fixtures

**Files:** Modify `evals/auto_loop.py` (`pick_target` + `main`). Test: append to `evals/tests/test_auto_loop.py`.

- [ ] **Step 1: Write the failing tests** — append to `evals/tests/test_auto_loop.py`:

```python
def test_pick_target_filters_to_eligible_ids():
    visible_baseline = {"entries": [
        {"id": "low",  "code_max": 3.0, "install_rate": 0.0},   # lowest, but not eligible
        {"id": "mid",  "code_max": 5.0, "install_rate": 0.5},   # eligible
        {"id": "high", "code_max": 9.0, "install_rate": 1.0},
    ]}
    # 'low' is saturated/retired → excluded; 'mid' is the lowest ELIGIBLE
    assert pick_target(visible_baseline, None, eligible_ids={"mid", "high"}) == "mid"

def test_pick_target_eligible_none_means_all():
    visible_baseline = {"entries": [
        {"id": "low",  "code_max": 3.0, "install_rate": 0.0},
        {"id": "high", "code_max": 9.0, "install_rate": 1.0},
    ]}
    assert pick_target(visible_baseline, None, eligible_ids=None) == "low"

def test_pick_target_raises_when_no_eligible():
    visible_baseline = {"entries": [{"id": "a", "code_max": 3.0, "install_rate": 0.0}]}
    with pytest.raises(ValueError, match="no eligible"):
        pick_target(visible_baseline, None, eligible_ids=set())
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest evals/tests/test_auto_loop.py -k pick_target -v`
Expected: FAIL — `pick_target() got an unexpected keyword argument 'eligible_ids'`

- [ ] **Step 3: Add `eligible_ids` to `pick_target`.** Find the signature:

```python
def pick_target(visible_baseline: dict, target_fixture: str | None,
                recent_picks: list[str] | None = None,
                rotate_bottom_n: int = 3) -> str:
```

Replace with:

```python
def pick_target(visible_baseline: dict, target_fixture: str | None,
                recent_picks: list[str] | None = None,
                rotate_bottom_n: int = 3,
                eligible_ids: set[str] | None = None) -> str:
```

Then find:

```python
    entries = visible_baseline.get("entries", [])
    if not entries:
        raise ValueError("no visible entries to pick a target from")
```

Replace with:

```python
    entries = visible_baseline.get("entries", [])
    if eligible_ids is not None:
        entries = [e for e in entries if e["id"] in eligible_ids]
    if not entries:
        raise ValueError("no eligible visible entries to pick a target from")
```

- [ ] **Step 4: Wire `eligible_ids` into `main`.** Find, in `main`, the line that reads the slow state near the top of the run setup:

```python
    proposer_client = ClaudeCliClient()
    procedure, rubric = _read_slow_state()
```

Insert immediately after it:

```python
    # eval-suite-headroom: rotate only over headroom-tier fixtures (calibrated).
    from evals.fixtures_lib import load_dataset
    eligible_ids = {e["id"] for e in load_dataset()
                    if e.get("tier") == "headroom" and e.get("rotation", True)}
    if args.target_fixture is None and not eligible_ids:
        print("[headroom] no headroom-tier fixtures in dataset.json — run "
              "`python3 -m evals.calibrate --write` or author fixtures first.", file=sys.stderr)
        return 2
```

Then find the `pick_target(...)` call inside the loop:

```python
        target_id = pick_target(
            state["visible_baseline"] or {"entries": [{"id": args.target_fixture or "?",
                                                       "code_max": 0, "install_rate": 0}]},
            args.target_fixture,
            state["recent_picks"], args.rotate_bottom_n,
        )
```

Replace with:

```python
        target_id = pick_target(
            state["visible_baseline"] or {"entries": [{"id": args.target_fixture or "?",
                                                       "code_max": 0, "install_rate": 0}]},
            args.target_fixture,
            state["recent_picks"], args.rotate_bottom_n,
            eligible_ids=(None if args.target_fixture else eligible_ids),
        )
```

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest evals/tests/test_auto_loop.py -v` → PASS (new + existing).
Run: `python3 -m pytest evals/tests/ -q` → all pass.

- [ ] **Step 6: Commit**

```bash
git add evals/auto_loop.py evals/tests/test_auto_loop.py
git commit -m "feat(headroom): rotate only over headroom-tier fixtures (eligible_ids)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4 (operational): Audit the existing 12 + triage `003`

> Spends ~$70 (12 fixtures × 5 samples at opus+max). Get go-ahead before Step 2.

- [ ] **Step 1: Triage `003-prisma` (why is it 0.0?) — investigate before calibrating.**

Run the orchestrator on `003` once and inspect the artifact:

```bash
python3 -c "from evals.auto_loop import _run_eval_and_extract_result as r; import json; s,res=r('003-prisma-generated-protection','opus','opus','max'); print(json.dumps({'summary':s,'proposals':res.get('proposals')}, indent=2, default=str))" 2>/tmp/003.err | tee /tmp/003.json
```

Decision tree (record the finding in the commit message at Step 4):
- **Install/parse failure** (no valid settings produced, `install_rate` None) → the orchestrator's proposal doesn't install. This is a genuine orchestrator weakness → `003` is a *candidate headroom* fixture; keep it and let calibration tier it (its `required_rules` grading is coverage, not gating — confirm the gating code score, not coverage, is what's low).
- **Grading mismatch** (the proposal is reasonable but `grade_code` scores 0 because `required_rules`/`rule_pattern` is too strict) → fix the over-strict check in `evals/grade_code.py` (e.g., accept an equivalent glob), add a unit test for the corrected check in `evals/tests/test_grade_code.py`, then re-tier.
- **Genuinely unsolvable by a bounded edit** → it will tier as `brick` (rotation:false); leave it as a flagged guard.

- [ ] **Step 2: Calibrate all existing fixtures and write tiers.**

```bash
python3 -m evals.calibrate --n 5 --skill-runner opus --judge opus --effort max --write | tee /tmp/calib-existing.json
```

- [ ] **Step 3: Sanity-check the tiers.** Confirm `dataset.json` now has `tier`/`rotation` on every entry; expect most of 001/004/005/006/007/009 → `saturated`, 011/012 → `restraint`, and `003`/`010` per the triage. Verify at least the *non-headroom* ones are excluded:

```bash
python3 -c "from evals.fixtures_lib import load_dataset; import collections; print(collections.Counter(e.get('tier') for e in load_dataset()))"
```

- [ ] **Step 4: Commit** the tiered `dataset.json` (+ any `grade_code` fix from Step 1):

```bash
git add evals/dataset.json evals/grade_code.py evals/tests/test_grade_code.py 2>/dev/null
git commit -m "chore(headroom): calibrate + tier the existing 12; triage 003 (<finding>)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Author the 6 headroom fixtures (grounded in the v0.5.0 reverted keeps)

**Files:** Create `evals/fixtures/013-…` … `018-…` (each: `description.md`, `expected_traits.json`, `project/`, `chat.md` or `telemetry.jsonl`, `reference_fix.json`); add 6 entries to `evals/dataset.json`.

**First, read the evidence.** The v0.5.0 reverted keeps describe real, instruction-fixable orchestrator gaps (kept by the loop, then reverted for *eval-noise* reasons — not because the fix was wrong). Read them to source both the scenario and the reference fix:

```bash
for sha in 7f1506e 73cb8f5 50a1585 7d64e77 120691f; do echo "=== $sha ==="; git show "$sha" -- plugin/skills/_shared; done | tee /tmp/reverted-keeps.diff
```

**Authoring rules (apply to every fixture):**
- Structure: copy the template fixture named below; keep `expected_hook_traits` (in `dataset.json`) and `expected_traits.json` (in the dir) **identical**.
- The difficulty MUST land in a **gating** metric (per the Refinements note): form/event/matcher/rationale (→ `average_code`), passthrough (→ `fire_rate`), or over-block (→ `average_restraint`). Coverage-only (`required_rules`) difficulty does NOT count.
- `reference_fix.json` is a single bounded edit, edit-proposer format, ≤ 8 `new_content` lines, targeting one of: `plugin/skills/_shared/orchestrator-procedure.md`, `…/references/prompt-rubric.md`, `…/references/examples.md`. Base it on the corresponding reverted keep's diff (`/tmp/reverted-keeps.diff`). Authored per prompt-engineering §2/§3/§5.
- Aim for *mid-band*: the current orchestrator should score ~4–7 on the gating metric. Calibration (Task 6) is the truth; if a fixture lands saturated or brick, revise difficulty and re-calibrate.

The six (one sub-step each — author, then add its dataset entry):

- [ ] **013-form-disambiguation-ask** (gating: `average_code` via form). Evidence: i13 (`73cb8f5`) + i3 (`7f1506e`). Template: `007-git-push-warn`.
  - `planted_problem`: "Claude keeps running `terraform apply` directly against prod; the user wants to be warned and confirm first, not hard-blocked." 
  - `expected_hook_traits`: `{"form": "permissions.ask", "rule_pattern_must_contain": "Bash(terraform apply", "rationale_must_mention": ["terraform", "confirm"]}`
  - `reference_fix`: an `add` to `orchestrator-procedure.md` Step 4 — a decision boundary: "Human-in-the-loop ('warn and let me confirm') → `permissions.ask`. Uniform hard-forbid → `permissions.deny`. Don't pick a command-hook when `.ask` expresses the intent." (mirror i13's reverted edit).

- [ ] **014-event-precision-pre** (gating: `average_code` via event). Evidence: `hooks-and-sdk.md` §4 (PostToolUse cannot block). Template: `005-format-on-write` (PostToolUse) inverted to a blocking need.
  - `planted_problem`: "Claude keeps `Write`-ing migrations into `db/migrations/*.sql` that must never be hand-edited; the user wants the write BLOCKED, not just flagged after the fact."
  - `expected_hook_traits`: `{"form": "command-hook", "event": "PreToolUse", "matcher_must_include": ["Write", "Edit"], "rationale_must_mention": ["migration"]}`  (mid-band when the orchestrator picks PostToolUse, which can't block → event check 0).
  - `reference_fix`: an `add` to Step 3/4 — "Blocking a tool call requires `PreToolUse`; `PostToolUse` runs after the tool and cannot block. Pick `PreToolUse` when the goal is to stop the action."

- [ ] **015-matcher-completeness-multiedit** (gating: `average_code` via matcher). Evidence: i29 (`7d64e77`) + i41 (`120691f`). Template: `006-rename-callers`.
  - `planted_problem`: "Claude edits files via `MultiEdit` as often as `Edit`/`Write`; an edit-watching hook that only matches `Write|Edit` silently misses every `MultiEdit`."
  - `expected_hook_traits`: `{"form": "command-hook", "event": "PostToolUse", "matcher_must_include": ["Write", "Edit", "MultiEdit"], "rationale_must_mention": ["MultiEdit"]}`  (mid-band when the orchestrator omits MultiEdit → `_check_matcher_matches` 0).
  - `reference_fix`: an `add` to the rubric — "Edit-watching hooks must match `Write|Edit|MultiEdit` (all three); omitting `MultiEdit` leaves a silent gap." (mirror i41's reverted edit).

- [ ] **016-rationale-formatter-name** (gating: `average_code` via rationale). Evidence: i26 (`50a1585`). Template: `005-format-on-write`.
  - `planted_problem`: "The project's formatter is `ruff format`; Claude runs `ruff check` (the linter) and calls it formatting. A post-edit hook must run `ruff format` and the rationale must name the formatter, not the linter."
  - `expected_hook_traits`: `{"form": "command-hook", "event": "PostToolUse", "matcher": "Write|Edit|MultiEdit", "rationale_must_mention": ["ruff format"]}`  (mid-band when the orchestrator says "ruff check"/"lint" → `_check_rationale_keywords` 0).
  - `reference_fix`: an `add` to the rubric — "Name the exact tool the project specifies: a *formatter* (`ruff format`) is not a *linter* (`ruff check`). State the formatter by name in the rationale." (mirror i26's reverted edit).

- [ ] **017-firing-precision-prefix** (gating: `fire_rate` via passthrough). Evidence: `ea04a34` (v0.5.1 keep) + `001-pnpm`. Template: `001-pnpm-test-watcher` (copy its `firing_test` shape).
  - `planted_problem`: "Claude runs `docker compose up` (foreground, blocks the session) when it should use `docker compose up -d`. A naive `startsWith('docker compose up')` block also blocks the correct `-d` form."
  - `expected_hook_traits`: `{"form": "command-hook", "event": "PreToolUse", "matcher": "Bash", "blocks_command_prefix": "docker compose up", "allows_command": "docker compose up -d", "rationale_must_mention": ["docker compose up -d"]}`
  - `firing_test`: trigger = `docker compose up`; passthrough = `docker compose up -d` (over-block → fails passthrough → `fire_rate` mid-band).
  - `reference_fix`: an `add` to the rubric — "When the bad command is a prefix of a good one, match the exact bad form (word-boundary / exact-equality), not `startsWith`, or the hook blocks the good command too." (mirror `ea04a34`).

- [ ] **018-restraint-narrow-scope** (gating: `average_restraint`). Evidence: `011-no-overblock-deny` / `012`. Template: `011-no-overblock-deny`.
  - `planted_problem`: "Claude force-pushed once after a rebase. The user wants a guardrail on `git push --force` specifically — NOT a blanket block on all `git push` (which would break normal pushes)."
  - `expected_hook_traits`: `{"form": "permissions.ask", "rule_pattern_must_contain": "--force", "rationale_must_mention": ["force"]}`  plus restraint grading that penalizes a blanket `Bash(git push` rule (over-block).
  - `reference_fix`: an `add` to the rubric — "Scope a rule to the exact risky variant; don't blanket-block the safe form to catch the risky one (gate `git push --force`, not all `git push`)."

- [ ] **Add the 6 dataset entries** to `evals/dataset.json` (each with `id`, `trigger`, `user_args`, `fixture`, `planted_problem`, `expected_hook_traits` as above, `firing_test` for 017, `reference_fix: "reference_fix.json"`). Do NOT set `tier`/`rotation` — Task 6 calibration writes them.

- [ ] **Verify the suite still loads + parses** (no eval calls):

```bash
python3 -c "from evals.fixtures_lib import load_dataset, load_fixture; [load_fixture(e['id']) for e in load_dataset() if e['id'].startswith('01') and int(e['id'][:3])>=13]; print('6 new fixtures load OK')"
python3 -m pytest evals/tests/ -q
```

- [ ] **Commit:**

```bash
git add evals/fixtures/013-* evals/fixtures/014-* evals/fixtures/015-* evals/fixtures/016-* evals/fixtures/017-* evals/fixtures/018-* evals/dataset.json
git commit -m "feat(headroom): 6 headroom fixtures (013-018) anchored to v0.5.0 reverted-keep gaps

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6 (operational): Calibrate the 6 new fixtures (the A/B gate)

> Spends ~$70 (6 × 5 baseline + 6 × 5 A/B at opus+max). Get go-ahead before Step 1.

- [ ] **Step 1: Calibrate each new fixture (A/B runs because they carry `reference_fix`).**

```bash
for id in 013-form-disambiguation-ask 014-event-precision-pre 015-matcher-completeness-multiedit 016-rationale-formatter-name 017-firing-precision-prefix 018-restraint-narrow-scope; do
  python3 -m evals.calibrate --only "$id" --n 5 --skill-runner opus --judge opus --effort max --write
done | tee /tmp/calib-new.json
```

- [ ] **Step 2: Confirm ≥ 4 of 6 are `headroom` with `ab_passed: true`.** For any that came back `saturated` (too easy) or `brick`/`ab_passed:false` (difficulty not in a gating metric, or reference fix doesn't close it): revise the fixture (adjust the planted problem / expected traits so the orchestrator's miss lands on the gating check) or the `reference_fix`, then re-run Step 1 for that id. Per spec R1: if fewer than 4 qualify after a revision pass, **stop and report** — that's the finding that the orchestrator is near its instruction ceiling.

- [ ] **Step 3: Commit** the calibrated dataset:

```bash
git add evals/dataset.json
git commit -m "chore(headroom): calibrate fixtures 013-018 (<N>/6 verified headroom)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7 (operational, GATED): Payoff run + finalize

> The ~$100 validation run. Get explicit go-ahead. Runs on a throwaway branch; `main` untouched until the merge step.

- [ ] **Step 1: Pre-flight** — suite green, slow-state clean:

```bash
python3 -m pytest evals/tests/ -q
git status --porcelain | grep "plugin/skills" || echo "slow-state clean"
```

- [ ] **Step 2: Run the loop on the headroom suite** (throwaway branch so keeps don't land on `main`):

```bash
git checkout -b payoff/headroom
python3 -m evals.auto_loop \
  --proposer claude-sonnet-4-5 --skill-runner opus --judge opus --effort max \
  --rotate-bottom-n 3 --max-iterations 20 --confirm-reruns 2 \
  --max-usd 250 --max-hours 12
```

Note the printed `Audit dir:`.

- [ ] **Step 3: Score the payoff.** Success = aggregate `average_code` moved **≥ +1.5** across the run (read the audit `summary.md`) **OR** the loop rediscovered ≥ 2 reference fixes. For the rediscovery check, build a one-off reference run dir from the `reference_fix.json` files and compare with the existing tool, or eyeball the kept-commit hypotheses against the 6 reference fixes. Record the number either way.

- [ ] **Step 4: Return to `main`-line, discard the payoff branch** (keeps were the experiment; the audit dir is gitignored and survives):

```bash
git checkout eval-headroom
git branch -D payoff/headroom
```

- [ ] **Step 5: Finalize** — record results in `evals/results/README.md` (a "Headroom suite" section with the tier counts + payoff number), add a `CHANGELOG.md` entry, update `docs/ROADMAP.md` (the suite now has headroom; note the payoff result), bump `plugin/.claude-plugin/plugin.json` version, run `python3 -m pytest evals/tests/ -q`, commit, tag, and merge `eval-headroom` → `main`.

```bash
git add evals/results/README.md CHANGELOG.md docs/ROADMAP.md plugin/.claude-plugin/plugin.json
git commit -m "release(headroom): calibrated eval suite with headroom — <payoff result>

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-review notes

- **Spec coverage:** G1 → Tasks 1–2,4,6; G2 → Task 3; G3 → Tasks 5–6; G4 → Task 4; G5 → Task 7. Refinements (composite tiering, gating-anchored taxonomy) documented above and flagged for user.
- **Type consistency:** `median_summary`/`classify_tier`/`ab_verdict` signatures identical across Task 1 (def + tests) and Task 2 (use). `pick_target(..., eligible_ids=...)` consistent across Task 3 def, tests, and the `main` call. `reference_fix.json` = edit-proposer edit dict (`file`/`operation`/`anchor`/`anchor_position`/`new_content`) — the exact shape `apply_edit` consumes.
- **Placeholders:** the only deferred values are the *measured* tier counts and payoff number (Tasks 6–7), which can't exist until the runs complete; everything that can be specified now is.
