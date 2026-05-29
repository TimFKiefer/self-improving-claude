"""Auto-loop driver — `python3 -m evals.auto_loop`.

The v0.5.0-α cut: edit-proposer + ratchet + apply-edit + audit log against a
single target fixture, no held-out gate, no bottom-3 rotation. β adds the
held-out confirmation gate and rotates over the bottom-3.

Spec: docs/superpowers/specs/2026-05-28-v0.5.0-auto-loop-design.md
Plan: docs/superpowers/plans/2026-05-28-v0.5.0-alpha-auto-loop.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SLOW_STATE_ALLOWLIST = frozenset({
    "plugin/skills/_shared/orchestrator-procedure.md",
    "plugin/skills/_shared/references/prompt-rubric.md",
    "plugin/skills/_shared/references/examples.md",
})

# Paths affected by sync_skills.py — both _shared/ source and generated trees.
SYNC_AFFECTED_PATHS = ("plugin/skills/_shared", "plugin/skills/improve",
                       "plugin/skills/improve-init")

MAX_NEW_CONTENT_LINES = 8  # SkillOpt §8.1 edit-budget

# ---------------------------------------------------------------------------
# Cost estimation — coarse USD lookahead for the --max-usd cap (v0.5.0)
# ---------------------------------------------------------------------------
# Anthropic API pricing (USD per 1M tokens), input / output, as of 2026-05.
# claude --print subscription auth doesn't reliably expose actual USD; we
# estimate from char counts (chars/4 ≈ tokens). Re-calibrate when pricing
# drifts. Upper-bound estimates are intentional — better to abort early than
# overspend. Per SkillOpt §8.6, these are GATING (used to enforce --max-usd).
MODEL_PRICING = {
    "haiku":              {"in":  1.00, "out":  5.00},
    "claude-sonnet-4-5":  {"in":  3.00, "out": 15.00},
    "opus":               {"in": 15.00, "out": 75.00},
}
DEFAULT_PRICING = {"in": 3.00, "out": 15.00}

# Rough token budgets observed in v0.4-v0.5 sandbox runs.
SKILL_RUN_INPUT_TOKENS = 50_000   # SKILL.md + procedure + references + fixture context
SKILL_RUN_OUTPUT_TOKENS = 5_000   # JSON proposals echo
JUDGE_INPUT_TOKENS = 2_000        # per-proposal grader call
JUDGE_OUTPUT_TOKENS = 1_000
PROPOSER_INPUT_TOKENS = 10_000    # procedure + rubric + fixture failure + history
PROPOSER_OUTPUT_TOKENS = 500      # the edit JSON


def _price(model: str) -> dict:
    return MODEL_PRICING.get(model, DEFAULT_PRICING)


def _estimate_eval_cost_usd(skill_model: str, judge_model: str, n_fixtures: int = 1) -> float:
    """Coarse USD estimate for `n_fixtures` sandbox-eval invocations.
    Upper-bound; over-counts when fixtures hit fewer proposals than expected."""
    s = _price(skill_model)
    j = _price(judge_model)
    skill_per_fixture = (SKILL_RUN_INPUT_TOKENS * s["in"]
                         + SKILL_RUN_OUTPUT_TOKENS * s["out"]) / 1_000_000
    judge_per_fixture = (JUDGE_INPUT_TOKENS * j["in"]
                         + JUDGE_OUTPUT_TOKENS * j["out"]) / 1_000_000
    return n_fixtures * (skill_per_fixture + judge_per_fixture)


def _estimate_proposer_cost_usd(proposer_model: str) -> float:
    """Coarse USD estimate for one edit-proposer call."""
    p = _price(proposer_model)
    return (PROPOSER_INPUT_TOKENS * p["in"]
            + PROPOSER_OUTPUT_TOKENS * p["out"]) / 1_000_000


def _estimate_iteration_cost_usd(*, skill_model: str, judge_model: str,
                                  proposer_model: str, holdout_gate_on: bool) -> float:
    """Upper-bound USD estimate for one iteration: proposer + single-fixture
    visible eval + (if held-out gate on AND visible would pass) 3-fixture
    held-out eval. We assume held-out runs to be conservative."""
    cost = _estimate_proposer_cost_usd(proposer_model)
    cost += _estimate_eval_cost_usd(skill_model, judge_model, n_fixtures=1)
    if holdout_gate_on:
        cost += _estimate_eval_cost_usd(skill_model, judge_model, n_fixtures=3)
    return cost


def _estimate_initial_baselines_cost_usd(*, skill_model: str, judge_model: str,
                                          rotation_mode: bool, holdout_gate_on: bool) -> float:
    """Upper-bound USD estimate for the initial baselines `main()` runs before
    the loop starts: visible-9 (rotation mode only) + held-out-3 (gate on only)."""
    cost = 0.0
    if rotation_mode:
        cost += _estimate_eval_cost_usd(skill_model, judge_model, n_fixtures=9)
    if holdout_gate_on:
        cost += _estimate_eval_cost_usd(skill_model, judge_model, n_fixtures=3)
    return cost


def apply_edit(edit: dict, repo_root: Path = REPO_ROOT) -> tuple[bool, str]:
    """Apply a bounded edit to a slow-state file. Returns (ok, reason).

    Rejects if:
    - edit['file'] is outside SLOW_STATE_ALLOWLIST
    - edit['operation'] not in {add, delete, replace}
    - edit['anchor'] does not appear exactly once in the target file
    - edit['anchor_position'] not in {before, after} when operation='add'
    - edit['new_content'] exceeds MAX_NEW_CONTENT_LINES lines
    """
    rel = edit.get("file", "")
    if rel not in SLOW_STATE_ALLOWLIST:
        return False, f"file not in allowlist: {rel}"

    op = edit.get("operation")
    if op not in ("add", "delete", "replace"):
        return False, f"invalid operation: {op}"

    anchor = edit.get("anchor", "")
    if not anchor:
        return False, "empty anchor"

    new_content = edit.get("new_content", "")
    if new_content.count("\n") + 1 > MAX_NEW_CONTENT_LINES and new_content:
        return False, f"new_content exceeds {MAX_NEW_CONTENT_LINES} lines"

    if op == "add":
        pos = edit.get("anchor_position")
        if pos not in ("before", "after"):
            return False, f"invalid anchor_position for add: {pos}"

    target = repo_root / rel
    if not target.exists():
        return False, f"target file does not exist: {rel}"
    text = target.read_text(encoding="utf-8")
    count = text.count(anchor)
    if count != 1:
        return False, f"anchor appears {count} times, expected exactly 1"

    if op == "replace":
        new_text = text.replace(anchor, new_content, 1)
    elif op == "delete":
        new_text = text.replace(anchor, "", 1)
    elif op == "add" and edit.get("anchor_position") == "before":
        new_text = text.replace(anchor, new_content + anchor, 1)
    else:  # add + after
        new_text = text.replace(anchor, anchor + new_content, 1)

    # Atomic write: temp file in same dir, then rename
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    tmp.replace(target)
    return True, "applied"


# ---------------------------------------------------------------------------
# Driver helpers
# ---------------------------------------------------------------------------

def pick_target(visible_baseline: dict, target_fixture: str | None,
                recent_picks: list[str] | None = None,
                rotate_bottom_n: int = 3) -> str:
    """If target_fixture is set, always return it (α fixed-target mode).
    Otherwise (β rotation): pick the lowest-composite-score visible fixture
    among the bottom-N, skipping any picked in the last 2 iterations.
    """
    if target_fixture:
        return target_fixture
    entries = visible_baseline.get("entries", [])
    if not entries:
        raise ValueError("no visible entries to pick a target from")

    def composite(e):
        return (e.get("code_max", 0.0) or 0.0) + (e.get("install_rate", 0.0) or 0.0) * 10
    bottom = sorted(entries, key=composite)[:rotate_bottom_n]
    avoid = set((recent_picks or [])[-2:])
    fresh = [e for e in bottom if e["id"] not in avoid]
    if not fresh:  # all bottom-N picked recently — fall back to oldest of them
        fresh = bottom
    return fresh[0]["id"]


def is_saturated(summary: dict) -> bool:
    """True iff all applicable gating metrics are at their ceiling.

    None means "not applicable for this fixture" (e.g. fire_rate is None for a
    permissions-only fixture); only None-or-max counts as saturated.
    """
    code = summary.get("average_code")
    install = summary.get("install_rate")
    fire = summary.get("fire_rate")
    restraint = summary.get("average_restraint")
    EPS = 1e-6
    return ((code is None or code >= 10.0 - EPS)
            and (install is None or install >= 1.0 - EPS)
            and (fire is None or fire >= 1.0 - EPS)
            and (restraint is None or restraint >= 10.0 - EPS))


def git_reset_sync_paths(repo_root: Path = REPO_ROOT) -> None:
    """Reset only the skill paths to HEAD — preserves any other dirty files."""
    paths = [str(repo_root / p) for p in SYNC_AFFECTED_PATHS]
    subprocess.run(["git", "checkout", "HEAD", "--"] + paths,
                   cwd=repo_root, check=True, capture_output=True)


def git_commit_iteration(message: str, repo_root: Path = REPO_ROOT) -> str:
    """Stage skill paths + commit. Returns commit sha."""
    paths = [str(repo_root / p) for p in SYNC_AFFECTED_PATHS]
    subprocess.run(["git", "add"] + paths, cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo_root, check=True, capture_output=True)
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                         cwd=repo_root, check=True, capture_output=True, text=True)
    return sha.stdout.strip()


def run_sync_skills(repo_root: Path = REPO_ROOT) -> tuple[bool, str]:
    """Run scripts/sync_skills.py to regenerate the per-skill trees.
    Returns (ok, message). On failure, the caller should reset."""
    try:
        r = subprocess.run(
            ["python3", "scripts/sync_skills.py"],
            cwd=repo_root, capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return False, f"sync_skills.py rc={r.returncode}: {r.stderr.strip()[:300]}"
        return True, "synced"
    except subprocess.TimeoutExpired:
        return False, "sync_skills.py timed out"


def run_single_fixture_eval(target_id: str, skill_model: str, judge_model: str) -> dict:
    """Run a single fixture sandbox eval. Returns the per-fixture aggregation:
    {average_code, install_rate, fire_rate, average_restraint, ...}"""
    # Import lazily to avoid circular references at module load
    from evals.fixtures_lib import load_dataset
    from evals.run import run_one_entry_sandbox, _aggregate_sandbox
    from evals.client_claude_cli import ClaudeCliClient
    entries = load_dataset()
    target = next((e for e in entries if e["id"] == target_id), None)
    if target is None:
        raise ValueError(f"target fixture not found in dataset: {target_id}")
    grader_client = ClaudeCliClient()
    result = run_one_entry_sandbox(target, model=skill_model, grader_client=grader_client,
                                   judge_model=judge_model)
    return _aggregate_sandbox([result])


def _run_eval_over(filter_predicate, skill_model: str, judge_model: str,
                   effort: str | None = None) -> tuple[dict, list[dict]]:
    """Run sandbox eval over every dataset entry matching the predicate.
    Returns (aggregated_summary, raw_per_entry_results)."""
    from evals.fixtures_lib import load_dataset
    from evals.run import run_one_entry_sandbox, _aggregate_sandbox
    from evals.client_claude_cli import ClaudeCliClient
    entries = [e for e in load_dataset() if filter_predicate(e)]
    grader_client = ClaudeCliClient(effort=effort)
    results = []
    for entry in entries:
        results.append(run_one_entry_sandbox(
            entry, model=skill_model, grader_client=grader_client,
            judge_model=judge_model, effort=effort,
        ))
    return _aggregate_sandbox(results), results


def run_visible_eval(skill_model: str, judge_model: str,
                     effort: str | None = None) -> tuple[dict, list[dict]]:
    """Run the eval over visible-only entries (NOT holdout). β baseline + after-edit gate."""
    return _run_eval_over(lambda e: not e.get("holdout"), skill_model, judge_model, effort)


def run_holdout_eval(skill_model: str, judge_model: str,
                     effort: str | None = None) -> tuple[dict, list[dict]]:
    """Run the eval over holdout-only entries. β confirmation gate."""
    return _run_eval_over(lambda e: bool(e.get("holdout")), skill_model, judge_model, effort)


def _fixture_failure_from_baseline(target_id: str, baseline: dict, dataset_entry: dict,
                                    last_eval_result: dict) -> dict:
    """Package what the edit-proposer needs to see about a failing fixture."""
    proposals = last_eval_result.get("proposals", []) if last_eval_result else []
    actual = proposals[0] if proposals else {}
    return {
        "id": target_id,
        "planted_problem": dataset_entry.get("planted_problem", ""),
        "expected_traits": dataset_entry.get("expected_hook_traits", {}),
        "actual_proposal": actual,
        "scores": {
            "code": baseline.get("average_code"),
            "install": baseline.get("install_rate"),
            "fire": baseline.get("fire_rate"),
            "restraint": baseline.get("average_restraint"),
        },
    }


def _run_eval_and_extract_result(target_id: str, skill_model: str, judge_model: str,
                                  effort: str | None = None) -> tuple[dict, dict]:
    """Run the single-fixture eval and also return the per-fixture raw result."""
    from evals.fixtures_lib import load_dataset
    from evals.run import run_one_entry_sandbox, _aggregate_sandbox
    from evals.client_claude_cli import ClaudeCliClient
    entries = load_dataset()
    target = next((e for e in entries if e["id"] == target_id), None)
    if target is None:
        raise ValueError(f"target fixture not found in dataset: {target_id}")
    grader_client = ClaudeCliClient(effort=effort)
    result = run_one_entry_sandbox(target, model=skill_model, grader_client=grader_client,
                                   judge_model=judge_model, effort=effort)
    summary = _aggregate_sandbox([result])
    return summary, result


def run_iteration(*, i: int, target_id: str, baseline: dict, last_result: dict,
                  holdout_baseline: dict | None,
                  procedure: str, rubric: str, audit, client, proposer_model: str,
                  skill_model: str, judge_model: str, effort: str | None = None,
                  dry_run: bool = False,
                  holdout_gate_enabled: bool = True,
                  ) -> tuple[dict, dict | None, dict | None]:
    """Run one auto-loop iteration. Returns (new_baseline, new_result, new_holdout).

    β additions on top of α:
    - Saturation pre-check: skip the iteration if baseline is at ceiling.
    - Held-out gate (when holdout_gate_enabled): after visible strictly_better,
      run the held-out eval; on regresses(), revert instead of commit.
    """
    from evals.fixtures_lib import load_dataset
    from evals.edit_proposer import propose_edit
    from evals.ratchet import strictly_better, regresses

    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entries = load_dataset()
    dataset_entry = next(e for e in entries if e["id"] == target_id)
    history = audit.last_n_rejected_edits(5)

    record = {
        "i": i, "ts": ts, "fixture": target_id,
        "edit": {}, "hypothesis": "", "confidence": 0,
        "scores_before": dict(baseline),
        "scores_after": None,
        "scores_holdout_before": dict(holdout_baseline) if holdout_baseline else None,
        "scores_holdout_after": None,
        "decision": "rejected: invalid_edit",
        "commit_sha": None,
    }

    # β: saturation pre-check — skip if the target is already maxed
    if is_saturated(baseline):
        record["decision"] = "skipped: saturated_baseline"
        audit.write_iteration(record)
        return baseline, last_result, holdout_baseline

    fixture_failure = _fixture_failure_from_baseline(target_id, baseline,
                                                     dataset_entry, last_result)

    # 1. Propose the edit
    try:
        proposal = propose_edit(
            fixture_failure=fixture_failure, procedure=procedure, rubric=rubric,
            history=history, client=client, model=proposer_model,
        )
    except (ValueError, Exception) as e:
        record["edit"] = {"error": str(e)[:200]}
        record["decision"] = f"rejected: invalid_edit ({type(e).__name__})"
        audit.write_iteration(record)
        return baseline, last_result, holdout_baseline

    if proposal is None:
        record["decision"] = "rejected: low_confidence"
        audit.write_iteration(record)
        return baseline, last_result, holdout_baseline

    record["edit"] = proposal.to_edit_dict()
    record["hypothesis"] = proposal.hypothesis
    record["confidence"] = proposal.confidence

    if dry_run:
        record["decision"] = "dry_run (proposed only)"
        audit.write_iteration(record)
        return baseline, last_result, holdout_baseline

    # 2. Apply the edit
    ok, reason = apply_edit(proposal.to_edit_dict())
    if not ok:
        record["decision"] = f"rejected: invalid_edit ({reason})"
        audit.write_iteration(record)
        return baseline, last_result, holdout_baseline

    # 3. Regenerate via sync_skills.py
    sync_ok, sync_msg = run_sync_skills()
    if not sync_ok:
        git_reset_sync_paths()
        record["decision"] = f"rejected: sync_failed ({sync_msg})"
        audit.write_iteration(record)
        return baseline, last_result, holdout_baseline

    # 4. Run the visible eval on the same target fixture
    try:
        new_baseline, new_result = _run_eval_and_extract_result(target_id, skill_model,
                                                                judge_model, effort)
    except Exception as e:
        git_reset_sync_paths()
        record["decision"] = f"rejected: eval_failed ({type(e).__name__}: {str(e)[:100]})"
        audit.write_iteration(record)
        return baseline, last_result, holdout_baseline

    record["scores_after"] = dict(new_baseline)

    # 5. Visible ratchet
    if not strictly_better(new_baseline, baseline):
        git_reset_sync_paths()
        record["decision"] = "rejected: no_visible_gain"
        audit.write_iteration(record)
        return baseline, last_result, holdout_baseline

    # 6. β: held-out confirmation gate
    if holdout_gate_enabled and holdout_baseline is not None:
        try:
            new_holdout, _ = run_holdout_eval(skill_model, judge_model, effort)
        except Exception as e:
            git_reset_sync_paths()
            record["decision"] = f"rejected: holdout_eval_failed ({type(e).__name__})"
            audit.write_iteration(record)
            return baseline, last_result, holdout_baseline

        record["scores_holdout_after"] = dict(new_holdout)
        if regresses(new_holdout, holdout_baseline):
            git_reset_sync_paths()
            record["decision"] = "rejected: holdout_regression"
            audit.write_iteration(record)
            return baseline, last_result, holdout_baseline
        # Held-out passed; commit
        sha = git_commit_iteration(f"auto-loop[i={i}]: {proposal.hypothesis[:80]}")
        record["decision"] = "kept"
        record["commit_sha"] = sha
        audit.write_iteration(record)
        return new_baseline, new_result, new_holdout

    # 7. Held-out gate disabled — α-compatibility path
    sha = git_commit_iteration(f"auto-loop[i={i}]: {proposal.hypothesis[:80]}")
    record["decision"] = "kept"
    record["commit_sha"] = sha
    audit.write_iteration(record)
    return new_baseline, new_result, holdout_baseline


# ---------------------------------------------------------------------------
# CLI / main
# ---------------------------------------------------------------------------

def _read_slow_state() -> tuple[str, str]:
    procedure = (REPO_ROOT / "plugin/skills/_shared/orchestrator-procedure.md").read_text(encoding="utf-8")
    rubric = (REPO_ROOT / "plugin/skills/_shared/references/prompt-rubric.md").read_text(encoding="utf-8")
    return procedure, rubric


def _check_clean_tree() -> None:
    r = subprocess.run(["git", "status", "--porcelain"],
                       cwd=REPO_ROOT, check=True, capture_output=True, text=True)
    dirty = [line for line in r.stdout.splitlines()
             if any(line.endswith(p) or f" {p}" in line for p in SYNC_AFFECTED_PATHS)]
    if dirty:
        raise SystemExit(f"Refusing to start: dirty slow-state files:\n{chr(10).join(dirty)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evals.auto_loop",
                                     description="v0.5.0 auto-loop driver (β: held-out gate + rotation)")
    parser.add_argument("--max-iterations", type=int, default=20,
                        help="max iterations (default 20 for β; 5 for α-compat)")
    parser.add_argument("--target-fixture", default=None,
                        help="lock to one fixture (α mode). Default None → rotate over bottom-N visible.")
    parser.add_argument("--rotate-bottom-n", type=int, default=3,
                        help="rotation pool size for --target-fixture=None (default 3)")
    parser.add_argument("--proposer", default="claude-sonnet-4-5",
                        help="model used to propose edits to the skill body")
    parser.add_argument("--skill-runner", default="claude-sonnet-4-5",
                        help="model used to invoke /improve in the sandbox eval")
    parser.add_argument("--judge", default="opus",
                        help="model used for the LLM-judge advisory score")
    parser.add_argument("--dry-run", action="store_true",
                        help="propose edits but do not apply or commit")
    parser.add_argument("--no-holdout-gate", action="store_true",
                        help="(α-compat) disable the held-out confirmation gate")
    parser.add_argument("--max-usd", type=float, default=None,
                        help="abort cleanly before next iteration would exceed this USD cap "
                             "(coarse estimate from token counts × per-model pricing)")
    parser.add_argument("--max-hours", type=float, default=None,
                        help="abort cleanly before next iteration if total wall-clock "
                             "elapsed (since launch) exceeds this many hours")
    parser.add_argument("--effort", default=None,
                        help="thinking effort for skill-runner + judge (low|medium|high|xhigh|max). "
                             "Falls back to SANDBOX_EFFORT env var if unset.")
    args = parser.parse_args(argv)
    import os
    effort = args.effort or os.environ.get("SANDBOX_EFFORT") or None

    _check_clean_tree()

    # Lazy imports to keep import cost low for unit tests
    from evals.client_claude_cli import ClaudeCliClient
    from evals.audit import AuditLog

    rotation_mode = args.target_fixture is None
    holdout_gate_on = not args.no_holdout_gate
    iter_cost_est = _estimate_iteration_cost_usd(
        skill_model=args.skill_runner, judge_model=args.judge,
        proposer_model=args.proposer, holdout_gate_on=holdout_gate_on,
    )
    initial_cost_est = _estimate_initial_baselines_cost_usd(
        skill_model=args.skill_runner, judge_model=args.judge,
        rotation_mode=rotation_mode, holdout_gate_on=holdout_gate_on,
    )

    # Pre-flight: if max_usd is set and we can't even afford the initial baselines, refuse
    if args.max_usd is not None and initial_cost_est > args.max_usd:
        print(f"[cap] --max-usd {args.max_usd:.2f} cannot cover initial baselines "
              f"(estimate ${initial_cost_est:.2f}). Raise --max-usd or use --target-fixture.",
              file=sys.stderr)
        return 2

    audit_root = REPO_ROOT / "prompt-lab" / "auto-runs"
    audit = AuditLog(audit_root, config={
        "max_iterations": args.max_iterations,
        "target_fixture": args.target_fixture,
        "rotate_bottom_n": args.rotate_bottom_n,
        "proposer": args.proposer,
        "skill_runner": args.skill_runner,
        "judge": args.judge,
        "effort": effort,
        "dry_run": args.dry_run,
        "holdout_gate_enabled": holdout_gate_on,
        "max_usd": args.max_usd,
        "max_hours": args.max_hours,
        "iter_cost_est_usd": round(iter_cost_est, 4),
        "initial_cost_est_usd": round(initial_cost_est, 4),
        "start_ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }, proposer_short=args.proposer.split("-")[1] if "-" in args.proposer else args.proposer)

    mode = "rotation" if rotation_mode else f"fixed:{args.target_fixture}"
    gate = "on" if holdout_gate_on else "OFF"
    caps = []
    if args.max_usd is not None:
        caps.append(f"--max-usd=${args.max_usd:.2f}")
    if args.max_hours is not None:
        caps.append(f"--max-hours={args.max_hours}")
    cap_str = (" caps=" + ",".join(caps)) if caps else ""
    effort_str = f" effort={effort}" if effort else ""
    print(f"Auto-loop v0.5.0 — mode={mode} holdout-gate={gate} proposer={args.proposer} "
          f"skill-runner={args.skill_runner} judge={args.judge}{effort_str} "
          f"max-iter={args.max_iterations}{cap_str}", file=sys.stderr)
    print(f"Cost estimate: initial ${initial_cost_est:.2f} + ~${iter_cost_est:.2f}/iter",
          file=sys.stderr)
    print(f"Audit dir: {audit.dir}", file=sys.stderr)

    proposer_client = ClaudeCliClient()
    procedure, rubric = _read_slow_state()

    # SIGINT handler — write summary and exit cleanly
    state = {"baseline": None, "last_result": None, "holdout_baseline": None,
             "iteration": 0, "recent_picks": [], "kept": 0,
             "visible_baseline": None, "original_visible": None,
             "original_holdout": None,
             "usd_spent": 0.0,
             "start_monotonic": time.monotonic()}

    def _on_sigint(signum, frame):
        print("\n[SIGINT] writing audit summary and exiting cleanly", file=sys.stderr)
        if state["baseline"] is not None or state["visible_baseline"] is not None:
            hours = (time.monotonic() - state["start_monotonic"]) / 3600
            audit.write_summary(
                kept=state["kept"], total=state["iteration"],
                baseline=state["original_visible"] or state["baseline"] or {},
                final=state["visible_baseline"] or state["baseline"] or {},
                usd_spent=state["usd_spent"], hours_spent=hours,
            )
        sys.exit(130)
    signal.signal(signal.SIGINT, _on_sigint)

    # Initial baselines (cost accounted up-front per estimate; actual call burns subscription quota)
    if rotation_mode:
        print("[baseline] running visible-9 eval (for rotation picking)...", file=sys.stderr)
        visible_baseline, _ = run_visible_eval(args.skill_runner, args.judge, effort)
        state["visible_baseline"] = visible_baseline
        state["original_visible"] = dict(visible_baseline)
        state["usd_spent"] += _estimate_eval_cost_usd(args.skill_runner, args.judge, n_fixtures=9)
        print(f"[baseline] visible: code={visible_baseline.get('average_code'):.2f} "
              f"install={visible_baseline.get('install_rate')} "
              f"restraint={visible_baseline.get('average_restraint')}", file=sys.stderr)
    else:
        print(f"[baseline] α-mode (fixed fixture {args.target_fixture})", file=sys.stderr)

    if holdout_gate_on:
        print("[baseline] running held-out-3 eval (for gate)...", file=sys.stderr)
        holdout_baseline, _ = run_holdout_eval(args.skill_runner, args.judge, effort)
        state["holdout_baseline"] = holdout_baseline
        state["original_holdout"] = dict(holdout_baseline)
        state["usd_spent"] += _estimate_eval_cost_usd(args.skill_runner, args.judge, n_fixtures=3)
        print(f"[baseline] holdout: code={holdout_baseline.get('average_code')} "
              f"install={holdout_baseline.get('install_rate')} "
              f"restraint={holdout_baseline.get('average_restraint')}", file=sys.stderr)

    for i in range(1, args.max_iterations + 1):
        state["iteration"] = i

        # v0.5.0 caps: abort cleanly before next iter would exceed budget
        if args.max_usd is not None:
            if state["usd_spent"] + iter_cost_est > args.max_usd:
                print(f"\n[cap] would exceed --max-usd ${args.max_usd:.2f} "
                      f"(spent ${state['usd_spent']:.2f}, next iter ~${iter_cost_est:.2f}); "
                      f"aborting after {i-1} iterations.", file=sys.stderr)
                break
        if args.max_hours is not None:
            elapsed_hours = (time.monotonic() - state["start_monotonic"]) / 3600
            if elapsed_hours >= args.max_hours:
                print(f"\n[cap] elapsed {elapsed_hours:.2f}h ≥ --max-hours {args.max_hours}; "
                      f"aborting after {i-1} iterations.", file=sys.stderr)
                break

        target_id = pick_target(
            state["visible_baseline"] or {"entries": [{"id": args.target_fixture or "?",
                                                       "code_max": 0, "install_rate": 0}]},
            args.target_fixture,
            state["recent_picks"], args.rotate_bottom_n,
        )
        print(f"\n[iter {i}/{args.max_iterations}] target={target_id} proposing edit...",
              file=sys.stderr)

        # Per-iteration target baseline = single-fixture (cheap; aligns with α)
        if state["baseline"] is None or target_id != state.get("baseline_target"):
            print(f"[iter {i}] running single-fixture target baseline...", file=sys.stderr)
            target_baseline, target_result = _run_eval_and_extract_result(
                target_id, args.skill_runner, args.judge, effort,
            )
            state["baseline"] = target_baseline
            state["last_result"] = target_result
            state["baseline_target"] = target_id

        new_baseline, new_result, new_holdout = run_iteration(
            i=i, target_id=target_id,
            baseline=state["baseline"], last_result=state["last_result"],
            holdout_baseline=state["holdout_baseline"],
            procedure=procedure, rubric=rubric, audit=audit,
            client=proposer_client, proposer_model=args.proposer,
            skill_model=args.skill_runner, judge_model=args.judge,
            effort=effort,
            dry_run=args.dry_run,
            holdout_gate_enabled=holdout_gate_on,
        )
        state["usd_spent"] += iter_cost_est  # upper-bound accumulation
        state["recent_picks"].append(target_id)
        if new_baseline is not state["baseline"]:
            state["kept"] += 1
            print(f"[iter {i}] KEPT — target {target_id} code "
                  f"{state['baseline'].get('average_code'):.2f} → "
                  f"{new_baseline.get('average_code'):.2f}", file=sys.stderr)
            procedure, rubric = _read_slow_state()
            state["holdout_baseline"] = new_holdout  # update to post-edit holdout
            # Invalidate target baseline so next pick re-evals
            state["baseline_target"] = None
        else:
            print(f"[iter {i}] rejected", file=sys.stderr)
        state["baseline"] = new_baseline
        state["last_result"] = new_result

    final_summary = state["visible_baseline"] or state["baseline"] or {}
    hours_spent = (time.monotonic() - state["start_monotonic"]) / 3600
    audit.write_summary(
        kept=state["kept"], total=state["iteration"],
        baseline=state["original_visible"] or state["original_holdout"] or {},
        final=final_summary,
        usd_spent=state["usd_spent"],
        hours_spent=hours_spent,
    )
    print(f"\nDone. Kept {state['kept']}/{state['iteration']}. "
          f"USD spent ~${state['usd_spent']:.2f}, wall-clock {hours_spent:.2f}h. "
          f"Audit: {audit.dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
