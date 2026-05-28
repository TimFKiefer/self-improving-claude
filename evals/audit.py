"""Audit log for the auto-loop.

Each `python3 -m evals.auto_loop` run gets its own audit dir at
`prompt-lab/auto-runs/<timestamp>-<proposer_short>/` containing:
  - config.json: caps, models, seed, run start time
  - iterations.jsonl: one row per iteration with the schema below
  - summary.md: written on clean exit; baseline vs final headline + keep list
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

REQUIRED_FIELDS = ("i", "ts", "fixture", "edit", "hypothesis", "confidence",
                   "scores_before", "scores_after",
                   "scores_holdout_before", "scores_holdout_after",
                   "decision", "commit_sha")
REJECTION_PREFIX = "rejected"


def _validate(record: dict) -> None:
    missing = [f for f in REQUIRED_FIELDS if f not in record]
    if missing:
        raise ValueError(f"audit iteration record missing fields: {missing}")


class AuditLog:
    def __init__(self, root: Path, config: dict, proposer_short: str = "proposer"):
        ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        self.dir = root / f"{ts}-{proposer_short}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.iterations_path = self.dir / "iterations.jsonl"
        self.config_path = self.dir / "config.json"
        self.summary_path = self.dir / "summary.md"
        self.config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        # Touch the iterations file so callers can rely on it existing
        self.iterations_path.touch()

    def write_iteration(self, record: dict) -> None:
        _validate(record)
        with self.iterations_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    def last_n_rejected_edits(self, n: int) -> list[dict]:
        """Last n iteration records whose decision starts with 'rejected'.
        Used by the proposer to avoid retrying bad edits."""
        if not self.iterations_path.exists():
            return []
        rejected = []
        with self.iterations_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if str(rec.get("decision", "")).startswith(REJECTION_PREFIX):
                    rejected.append(rec)
        return rejected[-n:]

    def write_summary(self, *, kept: int, total: int, baseline: dict, final: dict) -> None:
        ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines = [
            f"# Auto-loop run summary",
            f"",
            f"- **Completed:** {ts}",
            f"- **Iterations:** {total}",
            f"- **Kept:** {kept}",
            f"- **Rejected:** {total - kept}",
            f"",
            f"## Baseline → Final",
            f"",
            "| metric | baseline | final | Δ |",
            "|---|---|---|---|",
        ]
        for m in ("average_code", "install_rate", "fire_rate", "average_restraint"):
            b = baseline.get(m)
            f = final.get(m)
            d = (f - b) if (isinstance(b, (int, float)) and isinstance(f, (int, float))) else None
            lines.append(f"| {m} | {b} | {f} | {d if d is None else round(d, 4)} |")
        self.summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
