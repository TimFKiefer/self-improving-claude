"""Capability benchmark — rank proposer models by hook-authoring quality.

Multi-sample (N per model x fixture), judged on quality-vs-planted-problem by a fixed
judge (default Sonnet), aggregated to a leaderboard. Separate instrument from the
conformance tripwire in run.py. See docs/superpowers/specs/2026-05-25-capability-benchmark-design.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import statistics
import sys

from evals.clients import make_client
from evals.fixtures_lib import EVALS_DIR, load_dataset, load_fixture
from evals.grade_model import grade_model, grade_model_batch
from evals.run import assemble_prompt, parse_proposals

DEFAULT_MODELS = "claude-cli:haiku,claude-cli:claude-sonnet-4-5,claude-cli:opus,ollama:gemma4:e4b"
DEFAULT_JUDGE = "claude-cli:claude-sonnet-4-5"
DEFAULT_SAMPLES = 4


def mean_stderr(values: list[float]) -> tuple[float, float, float]:
    """Return (mean, std, stderr). std is the sample std (0 for n<2); stderr=std/sqrt(n)."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0, 0.0
    mean = sum(values) / n
    std = statistics.stdev(values) if n > 1 else 0.0
    return mean, std, (std / math.sqrt(n))


def aggregate_cell(per_sample_quality: list[float], *, n_valid: int, n: int) -> dict:
    """One (model x fixture) cell. per_sample_quality has one number per sample
    (0 for samples that produced no proposal). n_valid = samples with >=1 proposal."""
    mean, std, stderr = mean_stderr(per_sample_quality)
    return {
        "mean": round(mean, 3),
        "std": round(std, 3),
        "stderr": round(stderr, 3),
        "valid_rate": round(n_valid / n, 3) if n else 0.0,
        "n": n,
        "per_sample_quality": per_sample_quality,
    }


def build_leaderboard(cells: list[dict]) -> list[dict]:
    """Group cells by model, average cell means across fixtures, sort desc."""
    by_model: dict[str, list[dict]] = {}
    for c in cells:
        by_model.setdefault(c["model"], []).append(c)
    rows = []
    for model, cs in by_model.items():
        mean, _std, stderr = mean_stderr([c["mean"] for c in cs])
        rows.append({
            "model": model,
            "mean_quality": round(mean, 3),
            "stderr": round(stderr, 3),
            "fixtures_scored": len(cs),
            "avg_valid_rate": round(sum(c["valid_rate"] for c in cs) / len(cs), 3),
        })
    rows.sort(key=lambda r: r["mean_quality"], reverse=True)
    return rows


def within_noise(a: dict, b: dict) -> bool:
    """True if two leaderboard rows' means differ by less than 2x combined stderr."""
    band = 2 * math.sqrt(a["stderr"] ** 2 + b["stderr"] ** 2)
    return abs(a["mean_quality"] - b["mean_quality"]) < band


def run_cell(*, entry: dict, proposer_client, proposer_model: str,
             judge_client, judge_model: str, samples: int, independent: bool = False) -> dict:
    """Run N proposer samples for one (model x fixture), judge them, aggregate.

    Per-sample quality = max valid judge score over that sample's proposals (0 if the
    sample produced none). Judging is one batched call per cell unless `independent`.
    """
    fx = load_fixture(entry["id"])
    mode = "reactive" if entry["trigger"] == "improve" else "proactive"
    prompt = assemble_prompt(mode=mode, user_directive=entry.get("user_args", ""), fixture=fx)
    planted = entry["planted_problem"]

    sample_props: list[list[dict]] = []
    for _ in range(samples):
        resp = proposer_client.messages.create(
            model=proposer_model, max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        sample_props.append(parse_proposals(resp.content[0].text))

    flat = [(si, p) for si, props in enumerate(sample_props) for p in props]
    if not flat:
        scores: list = []
    elif independent:
        scores = [grade_model(proposal=p, planted_problem=planted, client=judge_client,
                              judge_model=judge_model).get("score") for _, p in flat]
    else:
        graded = grade_model_batch(items=[p for _, p in flat], planted_problem=planted,
                                   client=judge_client, judge_model=judge_model)
        scores = [g.get("score") for g in graded]

    per_sample: list[float] = []
    n_valid = 0
    for si, props in enumerate(sample_props):
        if props:
            n_valid += 1
        sc = [scores[k] for k, (s, _) in enumerate(flat) if s == si and scores[k] is not None]
        per_sample.append(float(max(sc)) if sc else 0.0)

    return aggregate_cell(per_sample, n_valid=n_valid, n=samples)


def run_benchmark(*, model_specs: list[str], judge_spec: str, samples: int,
                  fixture_id: str | None = None, independent: bool = False) -> dict:
    entries = load_dataset()
    if fixture_id:
        entries = [e for e in entries if e["id"] == fixture_id]
    judge_client, judge_model = make_client(judge_spec)
    cells = []
    for spec in model_specs:
        proposer_client, proposer_model = make_client(spec)
        for entry in entries:
            print(f"  {spec} x {entry['id']} ...", file=sys.stderr)
            cell = run_cell(entry=entry, proposer_client=proposer_client,
                            proposer_model=proposer_model, judge_client=judge_client,
                            judge_model=judge_model, samples=samples, independent=independent)
            cell["model"] = spec
            cell["fixture"] = entry["id"]
            cells.append(cell)
    return {
        "date": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "judge": judge_spec,
        "samples_per_cell": samples,
        "independent": independent,
        "cells": cells,
        "leaderboard": build_leaderboard(cells),
    }


def _format_leaderboard(leaderboard: list[dict]) -> str:
    lines = ["", "Leaderboard (mean quality, judge-graded; indicative ± stderr):"]
    for i, r in enumerate(leaderboard):
        flag = ""
        if i > 0 and within_noise(leaderboard[i - 1], r):
            flag = "  (within noise of above)"
        lines.append(f"  {r['mean_quality']:5.2f} ± {r['stderr']:.2f}  "
                     f"{r['model']:32s} valid={r['avg_valid_rate']:.0%}{flag}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Capability benchmark for hook proposers.")
    ap.add_argument("--fixture", help="run only one fixture id")
    ap.add_argument("--independent", action="store_true",
                    help="judge each proposal in its own call (gold-standard; ~7x more judge calls)")
    args = ap.parse_args(argv)

    model_specs = [s.strip() for s in os.environ.get("BENCH_MODELS", DEFAULT_MODELS).split(",") if s.strip()]
    judge_spec = os.environ.get("BENCH_JUDGE", DEFAULT_JUDGE)
    samples = int(os.environ.get("BENCH_SAMPLES", DEFAULT_SAMPLES))

    print(f"Benchmark: models={model_specs} judge={judge_spec} N={samples} "
          f"independent={args.independent}", file=sys.stderr)
    result = run_benchmark(model_specs=model_specs, judge_spec=judge_spec, samples=samples,
                           fixture_id=args.fixture, independent=args.independent)

    out_dir = EVALS_DIR / "results" / "benchmark"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d')}-bench.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nResults written to {out_path}")
    print(_format_leaderboard(result["leaderboard"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
