"""Reproducibility overlap tool (v0.5.1).

Compares the keep-set of two auto-loop runs. Reports two numbers:
- by-fixture overlap (deterministic floor): fraction of reference-kept fixtures
  the candidate also produced a keep for.
- judge overlap (advisory headline): per reference keep, ask a judge whether the
  candidate reproduced a substantively equivalent improvement.

The human reads both + the side-by-side table and makes the final >50% call,
mirroring the project's "deterministic gate + advisory judge" discipline.

CLI: python3 -m evals.reproducibility <reference_run_dir> <candidate_run_dir> [--judge opus]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable


def load_keeps(run_dir: Path) -> list[dict]:
    """Return the kept iteration rows of a run, in order."""
    path = Path(run_dir) / "iterations.jsonl"
    keeps = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("decision") == "kept":
                keeps.append(rec)
    return keeps


def by_fixture_overlap(reference: list[dict], candidate: list[dict]) -> dict:
    """Deterministic floor: fraction of reference-kept fixtures the candidate
    also kept. Returns {fraction, matched, reference_fixtures, candidate_fixtures}."""
    ref_fixtures = {k["fixture"] for k in reference}
    cand_fixtures = {k["fixture"] for k in candidate}
    matched = ref_fixtures & cand_fixtures
    fraction = (len(matched) / len(ref_fixtures)) if ref_fixtures else 0.0
    return {
        "fraction": fraction,
        "matched": matched,
        "reference_fixtures": ref_fixtures,
        "candidate_fixtures": cand_fixtures,
    }


_JUDGE_TEMPLATE = """You are checking whether two auto-loop runs discovered the SAME improvement.

REFERENCE improvement (from run A):
- fixture: {ref_fixture}
- hypothesis: {ref_hypothesis}
- edit: {ref_edit}

CANDIDATE improvements (from run B):
{cand_block}

Did run B produce a SUBSTANTIVELY EQUIVALENT improvement to the reference —
addressing the same defect, even if worded or anchored differently?

Reply with ONLY compact JSON: {{"reproduced": true|false, "reasoning": "one clause"}}"""


def judge_overlap(reference: list[dict], candidate: list[dict],
                  complete_fn: Callable[[str], str]) -> dict:
    """Advisory headline: one judge call per reference keep. complete_fn takes a
    prompt and returns model text. Returns {fraction, matches:[{...}]}."""
    cand_block = "\n".join(
        f"- fixture={c.get('fixture')} hypothesis={c.get('hypothesis')} edit={json.dumps(c.get('edit'))}"
        for c in candidate
    ) or "(none)"
    matches = []
    reproduced_count = 0
    for ref in reference:
        prompt = _JUDGE_TEMPLATE.format(
            ref_fixture=ref.get("fixture"),
            ref_hypothesis=ref.get("hypothesis"),
            ref_edit=json.dumps(ref.get("edit")),
            cand_block=cand_block,
        )
        text = complete_fn(prompt)
        try:
            start, end = text.index("{"), text.rindex("}") + 1
            verdict = json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            verdict = {"reproduced": False, "reasoning": f"unparseable: {text[:80]}"}
        reproduced = bool(verdict.get("reproduced"))
        reproduced_count += int(reproduced)
        matches.append({"reference_fixture": ref.get("fixture"),
                        "reproduced": reproduced,
                        "reasoning": verdict.get("reasoning", "")})
    fraction = (reproduced_count / len(reference)) if reference else 0.0
    return {"fraction": fraction, "matches": matches}


def format_report(reference: list[dict], candidate: list[dict],
                  by_fixture: dict, judge: dict | None) -> str:
    lines = ["# Reproducibility report", ""]
    lines.append(f"- reference keeps: {len(reference)}  |  candidate keeps: {len(candidate)}")
    lines.append(f"- **by-fixture overlap (floor):** {by_fixture['fraction']:.0%} "
                 f"(matched {sorted(by_fixture['matched'])})")
    if judge is not None:
        lines.append(f"- **judge overlap (headline):** {judge['fraction']:.0%}")
    lines.append("")
    lines.append("## Reference keeps")
    for k in reference:
        lines.append(f"- {k.get('fixture')}: {k.get('hypothesis','')[:80]} ({k.get('commit_sha')})")
    lines.append("")
    lines.append("## Candidate keeps")
    for k in candidate:
        lines.append(f"- {k.get('fixture')}: {k.get('hypothesis','')[:80]} ({k.get('commit_sha')})")
    if judge is not None:
        lines.append("")
        lines.append("## Judge verdicts (per reference keep)")
        for m in judge["matches"]:
            mark = "✓" if m["reproduced"] else "✗"
            lines.append(f"- {mark} {m['reference_fixture']}: {m['reasoning']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="evals.reproducibility")
    p.add_argument("reference_run_dir", help="the run to reproduce (e.g. the RC audit dir)")
    p.add_argument("candidate_run_dir", help="the new run to compare")
    p.add_argument("--judge", default="opus", help="judge model for the advisory overlap (default opus)")
    p.add_argument("--no-judge", action="store_true", help="skip the judge call (floor only)")
    args = p.parse_args(argv)

    reference = load_keeps(Path(args.reference_run_dir))
    candidate = load_keeps(Path(args.candidate_run_dir))
    by_fixture = by_fixture_overlap(reference, candidate)

    judge = None
    if not args.no_judge:
        from evals.client_claude_cli import ClaudeCliClient
        client = ClaudeCliClient(model=args.judge)
        judge = judge_overlap(reference, candidate,
                              lambda prompt: client.complete(prompt))

    print(format_report(reference, candidate, by_fixture, judge))
    return 0


if __name__ == "__main__":
    sys.exit(main())
