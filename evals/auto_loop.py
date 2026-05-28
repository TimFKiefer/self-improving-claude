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

def pick_target(visible_baseline: dict, target_fixture: str | None) -> str:
    """For α: if target_fixture is set, always return it. Otherwise pick the
    lowest-composite-score fixture in the visible baseline."""
    if target_fixture:
        return target_fixture
    entries = visible_baseline.get("entries", [])
    if not entries:
        raise ValueError("no visible entries to pick a target from")

    def composite(e):
        return (e.get("code_max", 0.0) or 0.0) + (e.get("install_rate", 0.0) or 0.0) * 10
    return sorted(entries, key=composite)[0]["id"]


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


def _run_eval_and_extract_result(target_id: str, skill_model: str, judge_model: str
                                  ) -> tuple[dict, dict]:
    """Run the single-fixture eval and also return the per-fixture raw result."""
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
    summary = _aggregate_sandbox([result])
    return summary, result


def run_iteration(*, i: int, target_id: str, baseline: dict, last_result: dict,
                  procedure: str, rubric: str, audit, client, proposer_model: str,
                  skill_model: str, judge_model: str, dry_run: bool = False
                  ) -> tuple[dict, dict | None]:
    """Run one auto-loop iteration. Returns (new_baseline, new_result) on keep,
    or (baseline, last_result) on reject. Always writes an audit record."""
    from evals.fixtures_lib import load_dataset
    from evals.edit_proposer import propose_edit

    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entries = load_dataset()
    dataset_entry = next(e for e in entries if e["id"] == target_id)
    fixture_failure = _fixture_failure_from_baseline(target_id, baseline,
                                                     dataset_entry, last_result)
    history = audit.last_n_rejected_edits(5)

    record = {
        "i": i, "ts": ts, "fixture": target_id,
        "edit": {}, "hypothesis": "", "confidence": 0,
        "scores_before": dict(baseline),
        "scores_after": None,
        "decision": "rejected: invalid_edit",
        "commit_sha": None,
    }

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
        return baseline, last_result

    if proposal is None:
        record["decision"] = "rejected: low_confidence"
        audit.write_iteration(record)
        return baseline, last_result

    record["edit"] = proposal.to_edit_dict()
    record["hypothesis"] = proposal.hypothesis
    record["confidence"] = proposal.confidence

    if dry_run:
        record["decision"] = "dry_run (proposed only)"
        audit.write_iteration(record)
        return baseline, last_result

    # 2. Apply the edit
    ok, reason = apply_edit(proposal.to_edit_dict())
    if not ok:
        record["decision"] = f"rejected: invalid_edit ({reason})"
        audit.write_iteration(record)
        return baseline, last_result

    # 3. Regenerate via sync_skills.py
    sync_ok, sync_msg = run_sync_skills()
    if not sync_ok:
        git_reset_sync_paths()
        record["decision"] = f"rejected: sync_failed ({sync_msg})"
        audit.write_iteration(record)
        return baseline, last_result

    # 4. Run the eval on the same target fixture
    try:
        new_baseline, new_result = _run_eval_and_extract_result(target_id, skill_model, judge_model)
    except Exception as e:
        git_reset_sync_paths()
        record["decision"] = f"rejected: eval_failed ({type(e).__name__}: {str(e)[:100]})"
        audit.write_iteration(record)
        return baseline, last_result

    record["scores_after"] = dict(new_baseline)

    # 5. Ratchet — strictly_better on visible-only (α scope; β adds held-out gate)
    from evals.ratchet import strictly_better
    if strictly_better(new_baseline, baseline):
        sha = git_commit_iteration(
            f"auto-loop[i={i}]: {proposal.hypothesis[:80]}",
        )
        record["decision"] = "kept"
        record["commit_sha"] = sha
        audit.write_iteration(record)
        return new_baseline, new_result
    else:
        git_reset_sync_paths()
        record["decision"] = "rejected: no_visible_gain"
        audit.write_iteration(record)
        return baseline, last_result


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
                                     description="v0.5.0-α auto-loop driver")
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--target-fixture", default="010-block-staging-fetch")
    parser.add_argument("--proposer", default="claude-sonnet-4-5",
                        help="model used to propose edits to the skill body")
    parser.add_argument("--skill-runner", default="claude-sonnet-4-5",
                        help="model used to invoke /improve in the sandbox eval")
    parser.add_argument("--judge", default="opus",
                        help="model used for the LLM-judge advisory score")
    parser.add_argument("--dry-run", action="store_true",
                        help="propose edits but do not apply or commit")
    args = parser.parse_args(argv)

    _check_clean_tree()

    # Lazy imports to keep import cost low for unit tests
    from evals.client_claude_cli import ClaudeCliClient
    from evals.audit import AuditLog

    audit_root = REPO_ROOT / "prompt-lab" / "auto-runs"
    audit = AuditLog(audit_root, config={
        "max_iterations": args.max_iterations,
        "target_fixture": args.target_fixture,
        "proposer": args.proposer,
        "skill_runner": args.skill_runner,
        "judge": args.judge,
        "dry_run": args.dry_run,
        "start_ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }, proposer_short=args.proposer.split("-")[1] if "-" in args.proposer else args.proposer)

    print(f"Auto-loop α — target={args.target_fixture} proposer={args.proposer} "
          f"skill-runner={args.skill_runner} judge={args.judge} max-iter={args.max_iterations}",
          file=sys.stderr)
    print(f"Audit dir: {audit.dir}", file=sys.stderr)

    proposer_client = ClaudeCliClient()
    procedure, rubric = _read_slow_state()

    # SIGINT handler — write summary and exit cleanly
    state = {"baseline": None, "last_result": None, "iteration": 0}

    def _on_sigint(signum, frame):
        print("\n[SIGINT] writing audit summary and exiting cleanly", file=sys.stderr)
        if state["baseline"] is not None:
            audit.write_summary(kept=0, total=state["iteration"],
                                baseline=state["baseline"], final=state["baseline"])
        sys.exit(130)
    signal.signal(signal.SIGINT, _on_sigint)

    # Initial baseline
    print(f"[baseline] running single-fixture eval on {args.target_fixture}...", file=sys.stderr)
    initial_baseline, initial_result = _run_eval_and_extract_result(
        args.target_fixture, args.skill_runner, args.judge,
    )
    state["baseline"] = initial_baseline
    state["last_result"] = initial_result
    original_baseline = dict(initial_baseline)
    print(f"[baseline] {initial_baseline}", file=sys.stderr)

    kept = 0
    for i in range(1, args.max_iterations + 1):
        state["iteration"] = i
        print(f"\n[iter {i}/{args.max_iterations}] proposing edit...", file=sys.stderr)
        new_baseline, new_result = run_iteration(
            i=i, target_id=args.target_fixture,
            baseline=state["baseline"], last_result=state["last_result"],
            procedure=procedure, rubric=rubric, audit=audit,
            client=proposer_client, proposer_model=args.proposer,
            skill_model=args.skill_runner, judge_model=args.judge,
            dry_run=args.dry_run,
        )
        if new_baseline is not state["baseline"]:
            kept += 1
            print(f"[iter {i}] KEPT — new baseline: {new_baseline}", file=sys.stderr)
            # Re-read slow state since the kept edit changed it
            procedure, rubric = _read_slow_state()
        else:
            print(f"[iter {i}] rejected", file=sys.stderr)
        state["baseline"] = new_baseline
        state["last_result"] = new_result

    audit.write_summary(kept=kept, total=args.max_iterations,
                        baseline=original_baseline, final=state["baseline"])
    print(f"\nDone. Kept {kept}/{args.max_iterations}. Audit: {audit.dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
