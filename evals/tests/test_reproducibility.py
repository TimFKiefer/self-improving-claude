"""Tests for the reproducibility overlap tool (v0.5.1)."""
from __future__ import annotations

import json
from pathlib import Path

from evals.reproducibility import (
    load_keeps,
    by_fixture_overlap,
    judge_overlap,
)


def _write_run(tmp_path: Path, name: str, rows: list[dict]) -> Path:
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    with (d / "iterations.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return d


def test_load_keeps_returns_only_kept_rows(tmp_path):
    d = _write_run(tmp_path, "run", [
        {"i": 1, "decision": "kept", "fixture": "002", "commit_sha": "aaa",
         "hypothesis": "h1", "edit": {"file": "f", "operation": "add"}},
        {"i": 2, "decision": "rejected: no_visible_gain", "fixture": "003",
         "commit_sha": None, "hypothesis": "h2", "edit": {}},
        {"i": 3, "decision": "kept", "fixture": "006", "commit_sha": "bbb",
         "hypothesis": "h3", "edit": {"file": "f", "operation": "add"}},
    ])
    keeps = load_keeps(d)
    assert [k["fixture"] for k in keeps] == ["002", "006"]
    assert [k["commit_sha"] for k in keeps] == ["aaa", "bbb"]


def test_by_fixture_overlap_partial(tmp_path):
    ref = [{"fixture": "002"}, {"fixture": "003"}, {"fixture": "006"}]
    cand = [{"fixture": "002"}, {"fixture": "006"}, {"fixture": "009"}]
    result = by_fixture_overlap(ref, cand)
    assert result["matched"] == {"002", "006"}
    assert result["fraction"] == 2 / 3


def test_by_fixture_overlap_zero(tmp_path):
    ref = [{"fixture": "002"}, {"fixture": "003"}]
    cand = [{"fixture": "009"}]
    result = by_fixture_overlap(ref, cand)
    assert result["matched"] == set()
    assert result["fraction"] == 0.0


def test_by_fixture_overlap_empty_reference_is_zero():
    assert by_fixture_overlap([], [{"fixture": "002"}])["fraction"] == 0.0


def test_judge_overlap_counts_reproduced(tmp_path):
    ref = [{"fixture": "002", "hypothesis": "fix dot notation", "edit": {}},
           {"fixture": "003", "hypothesis": "anti-patterns", "edit": {}}]
    cand = [{"fixture": "002", "hypothesis": "use permissions.ask dot", "edit": {}}]

    # Fake complete_fn: reproduces the first ref, not the second.
    calls = []

    def fake_complete(prompt: str) -> str:
        calls.append(prompt)
        reproduced = "dot notation" in prompt
        return json.dumps({"reproduced": reproduced, "reasoning": "test"})

    result = judge_overlap(ref, cand, fake_complete)
    assert result["fraction"] == 1 / 2
    assert len(calls) == 2  # one judge call per reference keep


def test_judge_overlap_unparseable_falls_back_to_not_reproduced():
    ref = [{"fixture": "002", "hypothesis": "h", "edit": {}}]
    cand = [{"fixture": "002", "hypothesis": "h2", "edit": {}}]

    def bad_complete(prompt: str) -> str:
        return "this is not json at all"

    result = judge_overlap(ref, cand, bad_complete)
    assert result["fraction"] == 0.0
    assert result["matches"][0]["reproduced"] is False


def test_load_keeps_skips_malformed_lines(tmp_path):
    d = tmp_path / "run"
    d.mkdir()
    (d / "iterations.jsonl").write_text(
        '{"decision": "kept", "fixture": "002", "commit_sha": "a", "hypothesis": "h", "edit": {}}\n'
        'this is not json\n'
        '{"decision": "kept", "fixture": "006", "commit_sha": "b", "hypothesis": "h", "edit": {}}\n',
        encoding="utf-8")
    keeps = load_keeps(d)
    assert [k["fixture"] for k in keeps] == ["002", "006"]


def test_format_report_renders_floor_and_judge():
    from evals.reproducibility import format_report
    ref = [{"fixture": "002", "hypothesis": "fix dot", "commit_sha": "aaa"}]
    cand = [{"fixture": "002", "hypothesis": "dot fix", "commit_sha": "bbb"}]
    by_fixture = {"fraction": 1.0, "matched": {"002"},
                  "reference_fixtures": {"002"}, "candidate_fixtures": {"002"}}
    judge = {"fraction": 1.0, "matches": [
        {"reference_fixture": "002", "reproduced": True, "reasoning": "same defect"}]}
    out = format_report(ref, cand, by_fixture, judge)
    assert "by-fixture overlap (floor):** 100%" in out
    assert "judge overlap (headline):** 100%" in out
    assert "✓ 002" in out

def test_format_report_omits_judge_when_none():
    from evals.reproducibility import format_report
    ref = [{"fixture": "002", "hypothesis": "h", "commit_sha": "a"}]
    cand = []
    by_fixture = {"fraction": 0.0, "matched": set(),
                  "reference_fixtures": {"002"}, "candidate_fixtures": set()}
    out = format_report(ref, cand, by_fixture, None)
    assert "judge overlap" not in out
    assert "Judge verdicts" not in out
