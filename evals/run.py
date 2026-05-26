"""Eval runner — drives the orchestrator's prompt content against Anthropic, grades proposals.

Usage:
    python3 -m evals.run                    # run all entries, write evals/results/<date>.json
    python3 -m evals.run --entry 001-...    # run one entry

Requires ANTHROPIC_API_KEY in the environment.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

from evals.fixtures_lib import EVALS_DIR, Fixture, load_dataset, load_fixture
from evals.grade_code import grade_code
from evals.grade_model import grade_model
from evals.sandbox_runner import run_in_sandbox

REPO_ROOT = EVALS_DIR.parent
SKILL_REFS = REPO_ROOT / "plugin" / "skills" / "improve" / "references"
PROMPT_TEMPLATE_PATH = EVALS_DIR / "prompt_template.md"

ORCHESTRATOR_MODEL = "claude-haiku-4-5-20251001"
CLEAN_THRESHOLD = 7.0  # a proposal at/above this code mean counts as "clean"

_FENCE_OPEN_RE = re.compile(r"^```(?:json|JSON)?\s*\n?")
_FENCE_CLOSE_RE = re.compile(r"\n?```\s*$")


def _read_ref(name: str) -> str:
    return (SKILL_REFS / name).read_text(encoding="utf-8")


def _format_project_snapshot(files: dict[str, str], cap_bytes: int = 6000) -> str:
    """Render a {filename → content} dict as one inline snapshot, capped in size."""
    parts: list[str] = []
    used = 0
    for name, content in files.items():
        head = f"=== {name} ===\n"
        chunk = head + content + "\n"
        if used + len(chunk) > cap_bytes:
            parts.append(head + "(truncated)\n")
            break
        parts.append(chunk)
        used += len(chunk)
    return "".join(parts).strip() or "(no project files in fixture)"


def _format_telemetry(rows: list[dict]) -> str:
    if not rows:
        return "(no telemetry rows)"
    return "\n".join(json.dumps(r) for r in rows)


def assemble_prompt(*, mode: str, user_directive: str, fixture: Fixture) -> str:
    """Build the full eval prompt from skill references + fixture inputs.

    Uses string replacement (not .format()) because the substituted reference
    files contain raw `{` from JSON examples that would crash the formatter.
    """
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    substitutions = {
        "<<<RUBRIC>>>":              _read_ref("prompt-rubric.md"),
        "<<<HOOK_PATTERNS>>>":       _read_ref("hook-patterns.md"),
        "<<<TOOLS_REFERENCE>>>":     _read_ref("tools-reference.md"),
        "<<<SETTINGS_MERGE>>>":      _read_ref("settings-merge.md"),
        "<<<EXAMPLES>>>":            _read_ref("examples.md"),
        "<<<MODE>>>":                mode,
        "<<<USER_DIRECTIVE>>>":      user_directive,
        "<<<RECENT_CHAT>>>":         fixture.chat.strip() or "(none — proactive run)",
        "<<<PROJECT_SNAPSHOT>>>":    _format_project_snapshot(fixture.project_files),
        "<<<TELEMETRY_EXCERPT>>>":   _format_telemetry(fixture.telemetry),
        "<<<EXISTING_HOOKS>>>":      "{}",
        "<<<EXISTING_PERMISSIONS>>>": "{}",
    }
    out = template
    for marker, value in substitutions.items():
        out = out.replace(marker, value)
    return out


def parse_proposals(text: str) -> list[dict]:
    """Extract proposals from the model's response. Return empty list on parse failure.

    Strips ```json``` fences (open and close independently — small local models
    sometimes forget to close their fence at the token limit).
    """
    text = text.strip()
    text = _FENCE_OPEN_RE.sub("", text)
    text = _FENCE_CLOSE_RE.sub("", text)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(obj, dict) and "proposals" in obj:
        return obj["proposals"] or []
    if isinstance(obj, list):
        return obj
    return []


def run_one_entry(entry: dict, *, client, proposer_model: str) -> dict:
    """Run one dataset entry end-to-end: assemble → call → parse → grade.

    The proposal uses `proposer_model` (varies per run); grading uses
    grade_model.GRADER_MODEL (pinned to Haiku) for cross-run comparability.
    """
    fx = load_fixture(entry["id"])
    mode = "reactive" if entry["trigger"] == "improve" else "proactive"
    prompt = assemble_prompt(
        mode=mode,
        user_directive=entry.get("user_args", ""),
        fixture=fx,
    )
    resp = client.messages.create(
        model=proposer_model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text
    proposals = parse_proposals(raw)

    code_grades = [grade_code(p, entry["expected_hook_traits"]) for p in proposals]
    model_grades = [
        grade_model(proposal=p, planted_problem=entry["planted_problem"], client=client)
        for p in proposals
    ]

    return {
        "id": entry["id"],
        "trigger": entry["trigger"],
        "user_args": entry.get("user_args", ""),
        "expected_hook_traits": entry["expected_hook_traits"],
        "proposals": proposals,
        "code_grades": code_grades,
        "model_grades": model_grades,
        "raw_response_head": raw[:500],
    }


def _aggregate(per_entry_results: list[dict]) -> dict:
    """Dataset-level rollup.

    Headline = max code grade (best-candidate intent). Also reports code_mean
    and clean_rate so noisy proposal sets are visible, and per-fixture coverage
    for `required_rules` fixtures. Invalid model grades (score is None) are
    excluded — never counted as 0.
    """
    if not per_entry_results:
        return {"average_code": 0.0, "average_model": None,
                "average_clean_rate": 0.0, "entries": []}

    entries = []
    for r in per_entry_results:
        codes = [c["mean"] for c in r["code_grades"]]
        valid_models = [m["score"] for m in r["model_grades"]
                        if m.get("valid") and m.get("score") is not None]
        entry = {
            "id": r["id"],
            "code_max": max(codes, default=0.0),
            "code_mean": (sum(codes) / len(codes)) if codes else 0.0,
            "model_max": max(valid_models, default=None),
            "model_mean": (sum(valid_models) / len(valid_models)) if valid_models else None,
            "clean_rate": (sum(1 for c in codes if c >= CLEAN_THRESHOLD) / len(codes)) if codes else 0.0,
            "n_proposals": len(r.get("proposals", [])),
            "n_model_valid": len(valid_models),
        }
        required = (r.get("expected_hook_traits") or {}).get("required_rules")
        if required:
            covered = set()
            for cg in r["code_grades"]:
                for rp in (cg.get("rules_present") or []):
                    covered.add(rp)
            entry["coverage"] = len(covered) / len(required)
        entries.append(entry)

    model_maxes = [e["model_max"] for e in entries if e["model_max"] is not None]
    return {
        "average_code": sum(e["code_max"] for e in entries) / len(entries),
        "average_model": (sum(model_maxes) / len(model_maxes)) if model_maxes else None,
        "average_clean_rate": sum(e["clean_rate"] for e in entries) / len(entries),
        "entries": entries,
    }


SANDBOX_PLUGIN_PATH = REPO_ROOT / "plugin"


def _installed_ok(proposal: dict, written: dict) -> bool | None:
    """Did this echoed proposal actually land on disk? None = N/A (claude-md-note,
    which Step 9 never writes). Coarse integrity signal, never folded into grades."""
    form = proposal.get("form")
    if form == "claude-md-note":
        return None
    if not written.get("settings_parses"):
        return False
    if form in ("permissions.deny", "permissions.ask"):
        return (proposal.get("rule") or "") in (written.get("permission_rules") or [])
    if form == "command-hook":
        return bool(written.get("hook_files")) and bool(written.get("settings", {}).get("hooks"))
    if form == "prompt-hook":
        return bool(written.get("settings", {}).get("hooks"))
    return False


def _aggregate_sandbox(results: list[dict]) -> dict:
    """Rollup for sandbox mode: code/model/clean over positive fixtures, a separate
    install_rate integrity axis, and average_restraint over expect_no_proposal fixtures."""
    pos = [r for r in results if not r.get("expect_no_proposal")]
    restraint = [r for r in results if r.get("expect_no_proposal")]
    entries = []
    install_flags: list[bool] = []
    for r in pos:
        codes = [c["mean"] for c in r["code_grades"]]
        valid_models = [m["score"] for m in r["model_grades"]
                        if m.get("valid") and m.get("score") is not None]
        oks = [o for o in r.get("installed", []) if o is not None]
        install_flags.extend(oks)
        entries.append({
            "id": r["id"],
            "code_max": max(codes, default=0.0),
            "code_mean": (sum(codes) / len(codes)) if codes else 0.0,
            "model_max": max(valid_models, default=None),
            "clean_rate": (sum(1 for c in codes if c >= CLEAN_THRESHOLD) / len(codes)) if codes else 0.0,
            "n_proposals": len(r.get("proposals", [])),
            "install_rate": (sum(1 for o in oks if o) / len(oks)) if oks else None,
        })
    restraint_entries = [{"id": r["id"], "restraint": r["restraint"]} for r in restraint]
    model_maxes = [e["model_max"] for e in entries if e["model_max"] is not None]
    return {
        "average_code": (sum(e["code_max"] for e in entries) / len(entries)) if entries else None,
        "average_model": (sum(model_maxes) / len(model_maxes)) if model_maxes else None,
        "average_clean_rate": (sum(e["clean_rate"] for e in entries) / len(entries)) if entries else None,
        "install_rate": (sum(1 for o in install_flags if o) / len(install_flags)) if install_flags else None,
        "average_restraint": (sum(e["restraint"] for e in restraint_entries) / len(restraint_entries)) if restraint_entries else None,
        "entries": entries,
        "restraint_entries": restraint_entries,
    }


def run_one_entry_sandbox(entry: dict, *, model: str, grader_client) -> dict:
    """Run one dataset entry through the REAL slash command in a sandbox, then grade.

    Restraint fixtures (expect_no_proposal) are scored binary on emptiness; positive
    fixtures are graded by the unchanged grade_code/grade_model on the echoed
    proposals, plus a per-proposal install_ok integrity flag.
    """
    fx = load_fixture(entry["id"])
    sb = run_in_sandbox(entry=entry, fixture=fx, model=model, plugin_path=SANDBOX_PLUGIN_PATH)
    if entry.get("expect_no_proposal"):
        wrote_nothing = (not sb["written"]["hook_files"]
                         and not sb["written"]["permission_rules"])
        return {
            "id": entry["id"], "expect_no_proposal": True,
            "restraint": 10 if (not sb["echo"] and wrote_nothing) else 0,
            "echo": sb["echo"], "written": sb["written"], "error": sb["error"],
        }
    proposals = sb["echo"]
    return {
        "id": entry["id"], "trigger": entry["trigger"], "proposals": proposals,
        "code_grades": [grade_code(p, entry["expected_hook_traits"]) for p in proposals],
        "model_grades": [grade_model(proposal=p, planted_problem=entry["planted_problem"],
                                     client=grader_client) for p in proposals],
        "installed": [_installed_ok(p, sb["written"]) for p in proposals],
        "written": sb["written"], "echo_valid": sb["echo_valid"], "error": sb["error"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--entry", help="run only one entry by id")
    args = parser.parse_args(argv)

    backend = os.environ.get("EVAL_BACKEND", "ollama").lower()
    if backend == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY not set (EVAL_BACKEND=anthropic)", file=sys.stderr)
            return 2
        from anthropic import Anthropic  # local import — only needed for this backend
        client = Anthropic()
        model_label = ORCHESTRATOR_MODEL
        proposer_model = ORCHESTRATOR_MODEL
    elif backend == "ollama":
        from evals.client_ollama import OllamaClient, DEFAULT_MODEL
        client = OllamaClient()
        model_label = f"ollama:{DEFAULT_MODEL}"
        proposer_model = DEFAULT_MODEL  # ignored by OllamaClient, kept for labels
    elif backend == "claude-cli":
        from evals.client_claude_cli import ClaudeCliClient, DEFAULT_MODEL as CLI_MODEL
        client = ClaudeCliClient()
        model_label = f"claude-cli:{CLI_MODEL}"
        proposer_model = CLI_MODEL
    else:
        print(f"Unknown EVAL_BACKEND={backend!r} (expected: ollama|anthropic|claude-cli)", file=sys.stderr)
        return 2

    entries = load_dataset()
    if args.entry:
        entries = [e for e in entries if e["id"] == args.entry]
        if not entries:
            print(f"No entry with id={args.entry}", file=sys.stderr)
            return 2

    print(f"Backend: {model_label}", file=sys.stderr)

    per_entry_results = []
    for entry in entries:
        print(f"Running {entry['id']}...", file=sys.stderr)
        per_entry_results.append(run_one_entry(entry, client=client, proposer_model=proposer_model))

    agg = _aggregate(per_entry_results)
    output = {
        "date": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": model_label,
        "results": per_entry_results,
        "summary": agg,
    }

    results_dir = EVALS_DIR / "results"
    results_dir.mkdir(exist_ok=True)
    out_path = results_dir / f"{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d')}.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nResults written to {out_path}")
    print(f"Average code score:  {agg['average_code']:.1f}/10")
    am = agg["average_model"]
    print(f"Average model score: {am:.1f}/10" if am is not None
          else "Average model score: n/a (no valid grades)")
    print(f"Average clean rate:  {agg['average_clean_rate']:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
