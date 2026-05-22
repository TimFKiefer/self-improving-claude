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
from pathlib import Path

from evals.fixtures_lib import EVALS_DIR, Fixture, load_dataset, load_fixture
from evals.grade_code import grade_code
from evals.grade_model import grade_model

REPO_ROOT = EVALS_DIR.parent
SKILL_REFS = REPO_ROOT / "skills" / "self-improving-claude" / "references"
PROMPT_TEMPLATE_PATH = EVALS_DIR / "prompt_template.md"

ORCHESTRATOR_MODEL = "claude-haiku-4-5-20251001"

_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)


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
    """Extract proposals from the model's response. Return empty list on parse failure."""
    text = text.strip()
    m = _FENCE_RE.match(text)
    if m:
        text = m.group(1)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(obj, dict) and "proposals" in obj:
        return obj["proposals"] or []
    if isinstance(obj, list):
        return obj
    return []


def run_one_entry(entry: dict, *, client) -> dict:
    """Run one dataset entry end-to-end: assemble → call → parse → grade."""
    fx = load_fixture(entry["id"])
    mode = "reactive" if entry["trigger"] == "improve" else "proactive"
    prompt = assemble_prompt(
        mode=mode,
        user_directive=entry.get("user_args", ""),
        fixture=fx,
    )
    resp = client.messages.create(
        model=ORCHESTRATOR_MODEL,
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
        "proposals": proposals,
        "code_grades": code_grades,
        "model_grades": model_grades,
        "raw_response_head": raw[:500],
    }


def _aggregate(per_entry_results: list[dict]) -> dict:
    """Compute dataset-level averages and a flat scorecard."""
    if not per_entry_results:
        return {"average_code": 0, "average_model": 0, "entries": []}

    # If an entry has multiple proposals, take the BEST (max) — credits a strong proposal
    # even when others are weak, which matches the orchestrator's "pick the best candidates" intent.
    per_entry = []
    for r in per_entry_results:
        best_code = max((c["mean"] for c in r["code_grades"]), default=0.0)
        best_model = max((m["score"] for m in r["model_grades"]), default=0)
        per_entry.append({"id": r["id"], "code": best_code, "model": best_model})

    avg_code = sum(p["code"] for p in per_entry) / len(per_entry)
    avg_model = sum(p["model"] for p in per_entry) / len(per_entry)
    return {"average_code": avg_code, "average_model": avg_model, "entries": per_entry}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--entry", help="run only one entry by id")
    args = parser.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 2

    from anthropic import Anthropic  # local import so tests don't need the package
    client = Anthropic()

    entries = load_dataset()
    if args.entry:
        entries = [e for e in entries if e["id"] == args.entry]
        if not entries:
            print(f"No entry with id={args.entry}", file=sys.stderr)
            return 2

    per_entry_results = []
    for entry in entries:
        print(f"Running {entry['id']}...", file=sys.stderr)
        per_entry_results.append(run_one_entry(entry, client=client))

    agg = _aggregate(per_entry_results)
    output = {
        "date": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": ORCHESTRATOR_MODEL,
        "results": per_entry_results,
        "summary": agg,
    }

    results_dir = EVALS_DIR / "results"
    results_dir.mkdir(exist_ok=True)
    out_path = results_dir / f"{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d')}.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nResults written to {out_path}")
    print(f"Average code score:  {agg['average_code']:.1f}/10")
    print(f"Average model score: {agg['average_model']:.1f}/10")
    return 0


if __name__ == "__main__":
    sys.exit(main())
