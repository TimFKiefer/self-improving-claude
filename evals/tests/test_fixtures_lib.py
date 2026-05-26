"""Tests for evals/fixtures_lib.py — fixture loading.

Each fixture is a self-contained directory under evals/fixtures/<id>/.
The loader exposes a typed view of one entry from the dataset.

Run: python3 -m pytest evals/tests/test_fixtures_lib.py -v
"""
import json
from pathlib import Path

import pytest

from evals.fixtures_lib import (
    EVALS_DIR,
    Fixture,
    load_dataset,
    load_fixture,
)


def test_evals_dir_resolves_to_repo_evals():
    # Sanity: the package can locate its own fixtures directory.
    assert EVALS_DIR.name == "evals"
    assert (EVALS_DIR / "dataset.json").exists()


def test_load_dataset_returns_list_of_entries():
    entries = load_dataset()
    assert isinstance(entries, list)
    assert len(entries) >= 1
    first = entries[0]
    # Required fields per spec §7
    assert "id" in first
    assert "trigger" in first
    assert first["trigger"] in ("improve", "improve-init")
    assert "user_args" in first  # may be ""
    assert "fixture" in first
    assert "planted_problem" in first
    assert "expected_hook_traits" in first


def test_load_fixture_001_returns_complete_fixture():
    fx = load_fixture("001-pnpm-test-watcher")
    assert isinstance(fx, Fixture)
    assert fx.id == "001-pnpm-test-watcher"
    assert fx.description.strip() != ""
    assert isinstance(fx.expected_traits, dict)
    assert "event" in fx.expected_traits
    # Project snapshot is a dict {filename → content}
    assert isinstance(fx.project_files, dict)
    assert "CLAUDE.md" in fx.project_files
    assert "package.json" in fx.project_files
    # Chat is a string (markdown body) — may be empty for proactive fixtures.
    assert isinstance(fx.chat, str)
    # Telemetry is a list of dicts (parsed from JSONL).
    assert isinstance(fx.telemetry, list)


def test_load_fixture_raises_clear_error_on_missing():
    with pytest.raises(FileNotFoundError) as ei:
        load_fixture("999-does-not-exist")
    assert "999-does-not-exist" in str(ei.value)


def test_load_fixture_handles_missing_optional_files(tmp_path, monkeypatch):
    """If chat.md or telemetry.jsonl is missing, loader returns empty defaults."""
    # Construct a minimal fixture in tmp_path
    fid = "test-minimal"
    fdir = tmp_path / "fixtures" / fid
    (fdir / "project").mkdir(parents=True)
    (fdir / "description.md").write_text("minimal")
    (fdir / "expected_traits.json").write_text('{"event": "PreToolUse"}')
    (fdir / "project" / "CLAUDE.md").write_text("ok")
    # No chat.md, no telemetry.jsonl, no package.json

    monkeypatch.setattr("evals.fixtures_lib.EVALS_DIR", tmp_path)
    fx = load_fixture(fid)
    assert fx.chat == ""
    assert fx.telemetry == []
    assert "CLAUDE.md" in fx.project_files
    assert "package.json" not in fx.project_files


def test_telemetry_jsonl_parses_each_line(tmp_path, monkeypatch):
    fid = "test-telemetry"
    fdir = tmp_path / "fixtures" / fid
    (fdir / "project").mkdir(parents=True)
    (fdir / "description.md").write_text("t")
    (fdir / "expected_traits.json").write_text('{}')
    telemetry = [
        {"ts": "2026-05-22T10:00:00Z", "tool": "Bash", "args_summary": "pnpm test"},
        {"ts": "2026-05-22T10:01:00Z", "tool": "Read", "args_summary": "/p"},
    ]
    (fdir / "telemetry.jsonl").write_text("\n".join(json.dumps(r) for r in telemetry) + "\n")

    monkeypatch.setattr("evals.fixtures_lib.EVALS_DIR", tmp_path)
    fx = load_fixture(fid)
    assert fx.telemetry == telemetry


def test_restraint_fixtures_load_and_flag():
    ids = {e["id"]: e for e in load_dataset()}
    for fid in ("011-no-overblock-deny", "012-one-off-bug-no-guardrail"):
        assert ids[fid]["expect_no_proposal"] is True
        assert "expected_hook_traits" not in ids[fid]      # restraint fixtures omit it
        fx = load_fixture(fid)                              # dir loads without error
        assert fx.id == fid
