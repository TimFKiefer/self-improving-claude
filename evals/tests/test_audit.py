"""Tests for evals/audit.py — JSONL audit log writer."""
import json
from pathlib import Path

import pytest

from evals.audit import AuditLog


def _record(i=1, decision="kept"):
    return {
        "i": i, "ts": "2026-05-28T20:14:00Z", "fixture": "010-x",
        "edit": {"file": "_shared/orchestrator-procedure.md", "operation": "add",
                 "anchor": "Step 7", "new_content": "hello"},
        "hypothesis": "improve recursion fixture",
        "confidence": 7,
        "scores_before": {"average_code": 7.0},
        "scores_after": {"average_code": 7.5},
        "scores_holdout_before": None,
        "scores_holdout_after": None,
        "decision": decision,
        "commit_sha": "abc1234" if decision == "kept" else None,
    }


def test_init_creates_dir_and_config(tmp_path):
    log = AuditLog(tmp_path, {"max_iter": 5}, proposer_short="sonnet")
    assert log.dir.exists() and log.dir.is_dir()
    assert log.config_path.exists()
    assert log.iterations_path.exists()
    cfg = json.loads(log.config_path.read_text(encoding="utf-8"))
    assert cfg["max_iter"] == 5


def test_write_iteration_appends_jsonl(tmp_path):
    log = AuditLog(tmp_path, {"x": 1})
    log.write_iteration(_record(i=1))
    log.write_iteration(_record(i=2, decision="rejected: no_visible_gain"))
    rows = [json.loads(l) for l in log.iterations_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 2
    assert rows[0]["i"] == 1 and rows[0]["decision"] == "kept"
    assert rows[1]["i"] == 2 and rows[1]["decision"].startswith("rejected")


def test_write_iteration_rejects_missing_field(tmp_path):
    log = AuditLog(tmp_path, {})
    bad = _record()
    del bad["hypothesis"]
    with pytest.raises(ValueError, match="hypothesis"):
        log.write_iteration(bad)


def test_last_n_rejected_edits_returns_only_rejections(tmp_path):
    log = AuditLog(tmp_path, {})
    log.write_iteration(_record(i=1, decision="kept"))
    log.write_iteration(_record(i=2, decision="rejected: no_visible_gain"))
    log.write_iteration(_record(i=3, decision="rejected: invalid_edit"))
    log.write_iteration(_record(i=4, decision="kept"))
    out = log.last_n_rejected_edits(5)
    assert [r["i"] for r in out] == [2, 3]


def test_last_n_rejected_edits_caps_at_n(tmp_path):
    log = AuditLog(tmp_path, {})
    for i in range(1, 6):
        log.write_iteration(_record(i=i, decision="rejected: invalid_edit"))
    out = log.last_n_rejected_edits(3)
    assert [r["i"] for r in out] == [3, 4, 5]


def test_last_n_rejected_edits_empty_when_no_iterations(tmp_path):
    log = AuditLog(tmp_path, {})
    assert log.last_n_rejected_edits(5) == []


def test_write_summary_produces_parseable_markdown(tmp_path):
    log = AuditLog(tmp_path, {})
    baseline = {"average_code": 7.0, "install_rate": 0.8, "fire_rate": 0.5, "average_restraint": 0.0}
    final = {"average_code": 8.0, "install_rate": 0.9, "fire_rate": 0.5, "average_restraint": 5.0}
    log.write_summary(kept=3, total=5, baseline=baseline, final=final)
    text = log.summary_path.read_text(encoding="utf-8")
    assert "Auto-loop run summary" in text
    assert "kept 3" in text
    assert "Aggregate" in text


# v0.5.0 RC: richer summary
def test_write_summary_includes_usd_and_hours(tmp_path):
    log = AuditLog(tmp_path, {})
    log.write_summary(kept=2, total=10, baseline={}, final={},
                      usd_spent=12.34, hours_spent=1.5)
    text = log.summary_path.read_text(encoding="utf-8")
    assert "$12.34" in text
    assert "1.50h" in text


def test_write_summary_decision_breakdown_from_iterations(tmp_path):
    log = AuditLog(tmp_path, {})
    log.write_iteration(_record(i=1, decision="kept"))
    log.write_iteration(_record(i=2, decision="rejected: no_visible_gain"))
    log.write_iteration(_record(i=3, decision="rejected: holdout_regression"))
    log.write_iteration(_record(i=4, decision="rejected: holdout_regression"))
    log.write_summary(kept=1, total=4, baseline={}, final={})
    text = log.summary_path.read_text(encoding="utf-8")
    assert "Decision breakdown" in text
    assert "rejected: holdout_regression" in text
    assert "| 2 |" in text  # holdout_regression count


def test_write_summary_kept_commits_listed(tmp_path):
    log = AuditLog(tmp_path, {})
    rec = _record(i=7, decision="kept")
    rec["commit_sha"] = "deadbee"
    rec["hypothesis"] = "Tested hypothesis A"
    log.write_iteration(rec)
    log.write_iteration(_record(i=8, decision="rejected: no_visible_gain"))
    log.write_summary(kept=1, total=2, baseline={}, final={})
    text = log.summary_path.read_text(encoding="utf-8")
    assert "Kept commits" in text
    assert "deadbee" in text
    assert "Tested hypothesis A" in text


def test_write_summary_per_fixture_delta_table(tmp_path):
    log = AuditLog(tmp_path, {})
    baseline = {"entries": [
        {"id": "001-x", "code_max": 5.0, "install_rate": 0.5},
        {"id": "002-y", "code_max": 8.0, "install_rate": 1.0},
    ]}
    final = {"entries": [
        {"id": "001-x", "code_max": 9.0, "install_rate": 1.0},
        {"id": "002-y", "code_max": 8.0, "install_rate": 1.0},
    ]}
    log.write_summary(kept=1, total=5, baseline=baseline, final=final)
    text = log.summary_path.read_text(encoding="utf-8")
    assert "Per-fixture" in text
    assert "001-x" in text and "002-y" in text


def test_write_summary_backward_compat_minimal_args(tmp_path):
    """The old 4-arg call signature still produces a valid markdown file."""
    log = AuditLog(tmp_path, {})
    log.write_summary(kept=0, total=5, baseline={}, final={})
    text = log.summary_path.read_text(encoding="utf-8")
    assert "kept 0" in text
