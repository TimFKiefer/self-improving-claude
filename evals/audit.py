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

    def _read_iterations(self) -> list[dict]:
        """Read all iteration records from iterations.jsonl. Returns [] on missing file."""
        if not self.iterations_path.exists():
            return []
        out = []
        with self.iterations_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def write_summary(self, *, kept: int, total: int, baseline: dict, final: dict,
                      usd_spent: float | None = None,
                      hours_spent: float | None = None) -> None:
        """Write a markdown run summary. Pulls decision breakdown, kept commits,
        and per-fixture Δ from the iterations.jsonl this AuditLog owns."""
        ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        records = self._read_iterations()

        # Decision breakdown
        decision_counts: dict[str, int] = {}
        kept_commits: list[tuple[int, str, str]] = []  # (i, sha, hypothesis)
        for r in records:
            d = r.get("decision", "?")
            decision_counts[d] = decision_counts.get(d, 0) + 1
            if d == "kept" and r.get("commit_sha"):
                kept_commits.append((r["i"], r["commit_sha"],
                                     (r.get("hypothesis") or "")[:90]))

        # Header
        lines = [
            "# Auto-loop run summary",
            "",
            f"- **Completed:** {ts}",
            f"- **Iterations:** {total} (kept {kept}, rejected {total - kept})",
        ]
        if usd_spent is not None:
            lines.append(f"- **USD spent (estimate):** ${usd_spent:.2f}")
        if hours_spent is not None:
            lines.append(f"- **Wall-clock:** {hours_spent:.2f}h")
        lines.append("")

        # Aggregate Δ
        lines += ["## Aggregate Δ", "",
                  "| metric | baseline | final | Δ |",
                  "|---|---|---|---|"]
        for m in ("average_code", "install_rate", "fire_rate", "average_restraint"):
            b = baseline.get(m)
            f = final.get(m)
            d = (f - b) if (isinstance(b, (int, float)) and isinstance(f, (int, float))) else None
            lines.append(f"| {m} | {b} | {f} | {d if d is None else round(d, 4)} |")
        lines.append("")

        # Per-fixture Δ (visible)
        b_entries = baseline.get("entries") if isinstance(baseline, dict) else None
        f_entries = final.get("entries") if isinstance(final, dict) else None
        if b_entries and f_entries:
            f_by_id = {e["id"]: e for e in f_entries}
            lines += ["## Per-fixture Δ", "",
                      "| fixture | code before | code after | install before | install after |",
                      "|---|---:|---:|---:|---:|"]
            for be in b_entries:
                fe = f_by_id.get(be["id"], {})
                lines.append(f"| {be['id']} | {be.get('code_max')} | {fe.get('code_max')} "
                             f"| {be.get('install_rate')} | {fe.get('install_rate')} |")
            lines.append("")

        # Kept commits
        if kept_commits:
            lines += ["## Kept commits", ""]
            for i, sha, hyp in kept_commits:
                lines.append(f"- `{sha}` — iter {i}: {hyp}")
            lines.append("")

        # Decision breakdown
        if decision_counts:
            lines += ["## Decision breakdown", "",
                      "| decision | count |", "|---|---:|"]
            for d in sorted(decision_counts, key=lambda x: -decision_counts[x]):
                lines.append(f"| {d} | {decision_counts[d]} |")
            lines.append("")

        self.summary_path.write_text("\n".join(lines), encoding="utf-8")
