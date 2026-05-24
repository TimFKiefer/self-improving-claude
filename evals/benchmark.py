"""Capability benchmark — rank proposer models by hook-authoring quality.

Multi-sample (N per model x fixture), judged on quality-vs-planted-problem by a fixed
judge (default Sonnet), aggregated to a leaderboard. Separate instrument from the
conformance tripwire in run.py. See docs/superpowers/specs/2026-05-25-capability-benchmark-design.md.
"""
from __future__ import annotations

import math
import statistics


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
