"""Tests for evals/run.py — prompt assembly and proposal parsing.

The Anthropic-call integration is tested with @pytest.mark.integration
which requires ANTHROPIC_API_KEY in the environment. Skipped by default;
run with: python3 -m pytest evals/tests/test_run.py -m integration

Run unit tests: python3 -m pytest evals/tests/test_run.py -v -m "not integration"
"""
import json
import os
from types import SimpleNamespace

import pytest

from evals.fixtures_lib import load_fixture
from evals.grade_model import GRADER_MODEL
from evals.run import (
    _aggregate,
    assemble_prompt,
    parse_proposals,
    run_one_entry,
)


def test_assemble_prompt_includes_fixture_signals():
    fx = load_fixture("001-pnpm-test-watcher")
    prompt = assemble_prompt(
        mode="proactive",
        user_directive="",
        fixture=fx,
    )
    # The fixture's planted-problem evidence must show up in the prompt
    assert "pnpm test" in prompt
    assert "test:ci" in prompt
    assert "<rubric>" in prompt
    assert "<examples>" in prompt
    # Mode is set
    assert "<mode>proactive</mode>" in prompt
    # Empty user directive renders cleanly
    assert "<user_directive></user_directive>" in prompt


def test_assemble_prompt_pulls_references_from_skill():
    """The prompt must include the SAME references the skill ships — read live from disk."""
    fx = load_fixture("001-pnpm-test-watcher")
    prompt = assemble_prompt(mode="proactive", user_directive="", fixture=fx)
    # A signature line from the rubric
    assert "Mandatory criteria" in prompt
    # A signature line from hook-patterns
    assert "Hook events at a glance" in prompt
    # A signature line from examples
    assert "Worked Examples" in prompt


def test_parse_proposals_extracts_valid_json():
    raw = json.dumps({
        "proposals": [
            {"form": "command-hook", "event": "PreToolUse", "matcher": "Bash",
             "rationale": "x", "script": "import sys", "script_lang": "python",
             "sentinel_name": "self-improving-claude/x"},
        ]
    })
    proposals = parse_proposals(raw)
    assert len(proposals) == 1
    assert proposals[0]["form"] == "command-hook"


def test_parse_proposals_strips_fences():
    raw = "```json\n" + json.dumps({"proposals": [{"form": "permissions.deny", "rule": "Read(**/.env)"}]}) + "\n```"
    proposals = parse_proposals(raw)
    assert proposals[0]["rule"] == "Read(**/.env)"


def test_parse_proposals_returns_empty_on_garbage():
    proposals = parse_proposals("not json")
    assert proposals == []


def test_run_one_entry_uses_mocked_client(monkeypatch, tmp_path):
    """End-to-end with a fake Anthropic client — verifies the pipeline."""
    canned_response = json.dumps({
        "proposals": [{
            "form": "command-hook",
            "event": "PreToolUse",
            "matcher": "Bash",
            "rationale": "Blocks pnpm test (watcher); steers Claude to pnpm test:ci.",
            "script_lang": "python",
            "script": "import sys\ndef main(): return 0\nif __name__=='__main__': sys.exit(main())\n",
            "sentinel_name": "self-improving-claude/block-pnpm-test-watcher",
        }]
    })

    class FakeClient:
        def __init__(self):
            self.messages = SimpleNamespace(create=self._create)

        def _create(self, **kwargs):
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=canned_response)])

    entries = [{
        "id": "001-pnpm-test-watcher",
        "trigger": "improve-init",
        "user_args": "",
        "fixture": "fixtures/001-pnpm-test-watcher",
        "planted_problem": "Claude keeps invoking pnpm test",
        "expected_hook_traits": {
            "form": "command-hook",
            "event": "PreToolUse",
            "matcher": "Bash",
            "rationale_must_mention": ["pnpm test:ci", "watcher"],
        }
    }]

    result = run_one_entry(entries[0], client=FakeClient(), proposer_model="claude-haiku-4-5-20251001")
    assert result["id"] == "001-pnpm-test-watcher"
    assert "proposals" in result
    assert "code_grades" in result
    assert "model_grades" in result
    # With the canned proposal that mirrors expected_traits, code_grade should be high
    assert result["code_grades"][0]["mean"] >= 8.0


# --- v0.3.4: proposer/grader routing + aggregation ---

def test_proposer_and_grader_models_route_separately():
    seen = []

    class _Recorder:
        def __init__(self):
            self.messages = SimpleNamespace(create=self._create)

        def _create(self, *, model, max_tokens, messages, system=None, **kw):
            seen.append(model)
            text = ('{"proposals":[{"form":"permissions.deny","rule":"Read(**/.env*)",'
                    '"rationale":".env"}]}' if system is None
                    else '{"score":7,"strengths":[],"weaknesses":[],"reasoning":"x"}')
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])

    entry = {"id": "002-block-env-reads", "trigger": "improve-init", "user_args": "",
             "planted_problem": "p",
             "expected_hook_traits": {"form": "permissions.deny",
                                      "rule_pattern": "Read(**/.env*)",
                                      "rationale_must_mention": [".env"]}}
    run_one_entry(entry, client=_Recorder(), proposer_model="opus")
    assert "opus" in seen              # proposal used the proposer model
    assert GRADER_MODEL in seen        # grading used the pinned grader model


def _mk_entry(id, code_means, model_scores, expected=None, rules_present=None):
    return {
        "id": id,
        "proposals": [{} for _ in code_means],
        "expected_hook_traits": expected or {},
        "code_grades": [{"mean": m, "rules_present": (rules_present[i] if rules_present else None)}
                        for i, m in enumerate(code_means)],
        "model_grades": [{"valid": s is not None, "score": s} for s in model_scores],
    }


def test_aggregate_excludes_invalid_model_grades():
    agg = _aggregate([_mk_entry("a", [10.0], [None])])
    e = agg["entries"][0]
    assert e["model_max"] is None and e["n_model_valid"] == 0
    assert agg["average_model"] is None


def test_aggregate_reports_mean_and_clean_rate():
    agg = _aggregate([_mk_entry("a", [10.0, 4.0, 8.0], [9, 3, 7])])
    e = agg["entries"][0]
    assert e["code_max"] == 10.0
    assert round(e["code_mean"], 2) == 7.33
    assert round(e["clean_rate"], 2) == 0.67   # 2 of 3 >= 7.0


def test_aggregate_computes_coverage_union():
    expected = {"required_rules": ["src/generated/prisma", "prisma/dev.db"]}
    entry = _mk_entry("c", [10.0, 8.6], [5, 5], expected=expected,
                      rules_present=[["src/generated/prisma"], ["prisma/dev.db"]])
    agg = _aggregate([entry])
    assert agg["entries"][0]["coverage"] == 1.0


@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set")
def test_integration_real_api_call():
    """Smoke: a real Haiku call returns parseable proposals.

    Skipped unless ANTHROPIC_API_KEY is set. Costs ~$0.01 per run.
    Run with: python3 -m pytest evals/tests/test_run.py::test_integration_real_api_call -v -s
    """
    from anthropic import Anthropic
    client = Anthropic()
    fx = load_fixture("001-pnpm-test-watcher")
    prompt = assemble_prompt(mode="proactive", user_directive="", fixture=fx)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text
    proposals = parse_proposals(text)
    assert len(proposals) >= 1, f"Got no proposals. Raw: {text[:500]}"


import evals.run as run_mod
from evals.run import _installed_ok, _aggregate_sandbox, _compute_skill_size


def test_dataset_has_three_holdout_entries():
    """The held-out validation set is fixed at 3; visible is everything else.

    (The visible set grew past v0.4.1's 9 when the eval-suite-headroom work added
    fixtures 013-018; the held-out invariant — exactly 3, one of each type — holds.)
    """
    from evals.fixtures_lib import load_dataset
    ds = load_dataset()
    visible = [e for e in ds if not e.get("holdout")]
    holdout = [e for e in ds if e.get("holdout")]
    assert len(holdout) == 3, f"expected 3 holdout, got {len(holdout)}: {[e['id'] for e in holdout]}"
    assert len(visible) == len(ds) - 3, f"expected {len(ds) - 3} visible, got {len(visible)}"
    # Each subset must keep at least one of each type for representativeness
    hold_ids = {e["id"] for e in holdout}
    assert any("secret-in-source" in i for i in hold_ids), "holdout needs a firing fixture"
    assert any("one-off-bug" in i for i in hold_ids), "holdout needs a restraint fixture"
    assert any("block-env-reads" in i for i in hold_ids), "holdout needs a shape-only fixture"


def test_installed_ok_accepts_multi_rule_list():
    proposal = {"form": "permissions.deny",
                "rule": ["Edit(src/generated/**)", "Write(src/generated/**)"]}
    written = {"settings_parses": True,
               "permission_rules": ["Edit(src/generated/**)", "Write(src/generated/**)", "MultiEdit(x)"]}
    assert _installed_ok(proposal, written) is True


def test_installed_ok_accepts_multi_rule_joined_string():
    proposal = {"form": "permissions.deny", "rule": "Edit(a)\nWrite(b)"}
    written = {"settings_parses": True, "permission_rules": ["Edit(a)", "Write(b)"]}
    assert _installed_ok(proposal, written) is True


def test_installed_ok_multi_rule_missing_one_is_false():
    proposal = {"form": "permissions.deny", "rule": ["Edit(a)", "Write(b)"]}
    written = {"settings_parses": True, "permission_rules": ["Edit(a)"]}  # Write(b) missing
    assert _installed_ok(proposal, written) is False


def test_installed_ok_single_rule_string_still_works():
    proposal = {"form": "permissions.ask", "rule": "Bash(git push:*)"}
    written = {"settings_parses": True, "permission_rules": ["Bash(git push:*)"]}
    assert _installed_ok(proposal, written) is True


def test_installed_ok_empty_rule_is_false():
    proposal = {"form": "permissions.deny", "rule": ""}
    written = {"settings_parses": True, "permission_rules": []}
    assert _installed_ok(proposal, written) is False


def test_aggregate_sandbox_handles_empty_results():
    """Empty input (e.g. --holdout-only with no holdout matches) returns all-None summary."""
    agg = _aggregate_sandbox([])
    assert agg["average_code"] is None
    assert agg["install_rate"] is None
    assert agg["fire_rate"] is None
    assert agg["average_restraint"] is None
    assert agg["entries"] == [] and agg["restraint_entries"] == []


def test_compute_skill_size_reads_live_slow_state():
    """skill_size measures the actual on-disk slow-state files (advisory metric)."""
    size = _compute_skill_size()
    # Three breakdown fields populated with positive char counts
    assert size["breakdown"]["procedure"] > 1000, "orchestrator-procedure.md should be substantial"
    assert size["breakdown"]["preamble_max"] > 100, "at least one preamble should exist"
    assert size["breakdown"]["references"] > 1000, "references should be substantial"
    # chars_per_invocation = procedure + preamble_max + references
    expected_chars = (size["breakdown"]["procedure"] + size["breakdown"]["preamble_max"]
                      + size["breakdown"]["references"])
    assert size["chars_per_invocation"] == expected_chars
    # Token approximation is chars // 4
    assert size["approx_tokens_per_invocation"] == expected_chars // 4


def test_installed_ok_permission_rule_present():
    w = {"settings_parses": True, "permission_rules": ["Read(**/.env*)"], "hook_files": [], "settings": {}}
    assert _installed_ok({"form": "permissions.deny", "rule": "Read(**/.env*)"}, w) is True
    assert _installed_ok({"form": "permissions.deny", "rule": "Read(**/secret*)"}, w) is False


def test_installed_ok_claude_md_note_is_na():
    w = {"settings_parses": True, "permission_rules": [], "hook_files": [], "settings": {}}
    assert _installed_ok({"form": "claude-md-note", "claude_md_line": "# x"}, w) is None


def test_installed_ok_command_hook_needs_file():
    w = {"settings_parses": True, "permission_rules": [], "hook_files": ["h.py"],
         "settings": {"hooks": {"PostToolUse": [{"x": 1}]}}}
    assert _installed_ok({"form": "command-hook", "sentinel_name": "self-improving-claude/h"}, w) is True
    w2 = {**w, "hook_files": []}
    assert _installed_ok({"form": "command-hook", "sentinel_name": "self-improving-claude/h"}, w2) is False


def test_aggregate_sandbox_separates_restraint_and_install_rate():
    results = [
        {"id": "a", "code_grades": [{"mean": 8.0}], "model_grades": [{"valid": True, "score": 7}],
         "proposals": [{}], "installed": [True]},
        {"id": "b", "code_grades": [{"mean": 6.0}], "model_grades": [{"valid": True, "score": 5}],
         "proposals": [{}], "installed": [False]},
        {"id": "r", "expect_no_proposal": True, "restraint": 10},
    ]
    agg = _aggregate_sandbox(results)
    assert agg["average_code"] == 7.0
    assert agg["install_rate"] == 0.5
    assert agg["average_restraint"] == 10.0
    assert len(agg["entries"]) == 2 and len(agg["restraint_entries"]) == 1


class _FakeGrader:
    def __init__(self):
        self.messages = type("M", (), {"create": lambda *a, **k: None})()


def _sb_result(echo, written=None):
    return {"echo": echo, "echo_valid": True,
            "written": written or {"settings_parses": True, "permission_rules": [], "hook_files": [], "settings": {}},
            "raw_result": "", "returncode": 0, "error": None}


def test_run_one_entry_sandbox_restraint_pass(monkeypatch):
    monkeypatch.setattr(run_mod, "run_in_sandbox",
        lambda **k: _sb_result([], {"settings_parses": True, "permission_rules": [], "hook_files": [], "settings": {}}))
    monkeypatch.setattr(run_mod, "load_fixture", lambda _id: object())
    entry = {"id": "011-x", "trigger": "improve-init", "expect_no_proposal": True}
    out = run_mod.run_one_entry_sandbox(entry, model="haiku", grader_client=_FakeGrader())
    assert out["expect_no_proposal"] is True and out["restraint"] == 10


def test_run_one_entry_sandbox_restraint_fail_when_proposes(monkeypatch):
    monkeypatch.setattr(run_mod, "run_in_sandbox",
        lambda **k: _sb_result([{"form": "permissions.deny", "rule": "Read(**/.env*)"}],
                               {"settings_parses": True, "permission_rules": ["Read(**/.env*)"], "hook_files": [], "settings": {}}))
    monkeypatch.setattr(run_mod, "load_fixture", lambda _id: object())
    entry = {"id": "011-x", "trigger": "improve-init", "expect_no_proposal": True}
    out = run_mod.run_one_entry_sandbox(entry, model="haiku", grader_client=_FakeGrader())
    assert out["restraint"] == 0


def test_run_one_entry_sandbox_positive_grades(monkeypatch):
    monkeypatch.setattr(run_mod, "run_in_sandbox",
        lambda **k: _sb_result([{"form": "permissions.deny", "rule": "Read(**/.env*)", "rationale": "block .env"}],
                               {"settings_parses": True, "permission_rules": ["Read(**/.env*)"], "hook_files": [], "settings": {}}))
    monkeypatch.setattr(run_mod, "load_fixture", lambda _id: object())
    monkeypatch.setattr(run_mod, "grade_model",
        lambda **k: {"valid": True, "score": 8, "error": None})
    entry = {"id": "002-x", "trigger": "improve-init",
             "expected_hook_traits": {"form": "permissions.deny", "rule_pattern": "Read(**/.env*)",
                                      "rationale_must_mention": [".env"]},
             "planted_problem": "block .env"}
    out = run_mod.run_one_entry_sandbox(entry, model="haiku", grader_client=_FakeGrader())
    assert out["code_grades"][0]["mean"] == 10.0
    assert out["model_grades"][0]["score"] == 8
    assert out["installed"][0] is True


def test_main_sandbox_mode_writes_per_model_results(monkeypatch, tmp_path):
    monkeypatch.setenv("SANDBOX_MODEL", "haiku")
    monkeypatch.setattr(run_mod, "load_dataset",
        lambda: [{"id": "r", "trigger": "improve-init", "expect_no_proposal": True}])
    monkeypatch.setattr(run_mod, "run_one_entry_sandbox",
        lambda entry, **k: {"id": "r", "expect_no_proposal": True, "restraint": 10})
    monkeypatch.setattr(run_mod, "EVALS_DIR", tmp_path)
    rc = run_mod.main(["--sandbox"])
    assert rc == 0
    out = list((tmp_path / "results").glob("*-v0.4.1-sandbox-haiku.json"))
    assert len(out) == 1
    data = json.loads(out[0].read_text())
    assert data["mode"] == "sandbox" and data["summary"]["average_restraint"] == 10.0


def test_installed_ok_command_hook_requires_slug_match():
    w = {"settings_parses": True, "permission_rules": [], "hook_files": ["other.py"],
         "settings": {"hooks": {"PostToolUse": [{}]}}}
    p = {"form": "command-hook", "sentinel_name": "self-improving-claude/block-env"}
    assert _installed_ok(p, w) is False                      # written file is a different slug
    w2 = {**w, "hook_files": ["block-env.py"]}
    assert _installed_ok(p, w2) is True


def test_installed_ok_prompt_hook_needs_type_prompt():
    w_yes = {"settings_parses": True, "permission_rules": [], "hook_files": [],
             "settings": {"hooks": {"PreToolUse": [{"type": "prompt"}]}}}
    w_no = {"settings_parses": True, "permission_rules": [], "hook_files": [],
            "settings": {"hooks": {"PreToolUse": [{"type": "command"}]}}}
    p = {"form": "prompt-hook", "sentinel_name": "self-improving-claude/x"}
    assert _installed_ok(p, w_yes) is True
    assert _installed_ok(p, w_no) is False


def test_run_one_entry_tolerates_missing_expected_hook_traits(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(run_mod, "load_fixture", lambda _id: object())
    monkeypatch.setattr(run_mod, "assemble_prompt", lambda **k: "prompt")
    client = SimpleNamespace(messages=SimpleNamespace(
        create=lambda **k: SimpleNamespace(content=[SimpleNamespace(type="text", text="not json")])))
    entry = {"id": "z", "trigger": "improve-init", "planted_problem": "p"}  # no expected_hook_traits
    out = run_mod.run_one_entry(entry, client=client, proposer_model="m")
    assert out["expected_hook_traits"] is None and out["proposals"] == []


def test_run_one_entry_sandbox_forwards_judge_model(monkeypatch):
    captured = {}
    monkeypatch.setattr(run_mod, "run_in_sandbox",
        lambda **k: _sb_result([{"form": "permissions.deny", "rule": "r", "rationale": "x"}]))
    monkeypatch.setattr(run_mod, "load_fixture", lambda _id: object())
    monkeypatch.setattr(run_mod, "grade_model",
        lambda **k: captured.update(k) or {"valid": True, "score": 7})
    entry = {"id": "002-x", "trigger": "improve-init",
             "expected_hook_traits": {"form": "permissions.deny"}, "planted_problem": "p"}
    run_mod.run_one_entry_sandbox(entry, model="haiku", grader_client=None, judge_model="opus")
    assert captured["judge_model"] == "opus"


def test_run_one_entry_sandbox_forwards_effort(monkeypatch):
    captured = {}
    monkeypatch.setattr(run_mod, "run_in_sandbox",
        lambda **k: captured.update(k) or _sb_result([]))
    monkeypatch.setattr(run_mod, "load_fixture", lambda _id: object())
    entry = {"id": "011-x", "trigger": "improve-init", "expect_no_proposal": True}
    run_mod.run_one_entry_sandbox(entry, model="haiku", grader_client=None, effort="max")
    assert captured["effort"] == "max"


def test_run_one_entry_sandbox_sets_fired_for_command_hook(monkeypatch):
    monkeypatch.setattr(run_mod, "run_in_sandbox",
        lambda **k: _sb_result([{"form": "command-hook", "script_lang": "python",
                                 "script": "import json,sys; d=json.loads(sys.stdin.read());"
                                           " sys.exit(2 if 'pnpm test'==d['tool_input']['command'] else 0)"}]))
    monkeypatch.setattr(run_mod, "load_fixture", lambda _id: object())
    monkeypatch.setattr(run_mod, "grade_model", lambda **k: {"valid": True, "score": 7})
    entry = {"id": "001-x", "trigger": "improve-init",
             "expected_hook_traits": {"form": "command-hook"}, "planted_problem": "p",
             "firing_test": {"trigger": {"tool_input": {"command": "pnpm test"}},
                             "passthrough": {"tool_input": {"command": "pnpm test:ci"}}}}
    out = run_mod.run_one_entry_sandbox(entry, model="haiku", grader_client=None)
    assert out["fired"] == [True]


def test_run_one_entry_sandbox_fired_none_without_firing_test(monkeypatch):
    monkeypatch.setattr(run_mod, "run_in_sandbox",
        lambda **k: _sb_result([{"form": "permissions.deny", "rule": "Read(**/.env*)", "rationale": "x"}]))
    monkeypatch.setattr(run_mod, "load_fixture", lambda _id: object())
    monkeypatch.setattr(run_mod, "grade_model", lambda **k: {"valid": True, "score": 7})
    entry = {"id": "002-x", "trigger": "improve-init",
             "expected_hook_traits": {"form": "permissions.deny"}, "planted_problem": "p"}
    out = run_mod.run_one_entry_sandbox(entry, model="haiku", grader_client=None)
    assert out["fired"] == [None]


def test_aggregate_sandbox_reports_fire_rate():
    results = [
        {"id": "a", "code_grades": [{"mean": 8.0}], "model_grades": [{"valid": True, "score": 7}],
         "proposals": [{}], "installed": [True], "fired": [True]},
        {"id": "b", "code_grades": [{"mean": 6.0}], "model_grades": [{"valid": True, "score": 5}],
         "proposals": [{}], "installed": [True], "fired": [False]},
        {"id": "c", "code_grades": [{"mean": 9.0}], "model_grades": [{"valid": True, "score": 8}],
         "proposals": [{}], "installed": [True], "fired": [None]},
    ]
    agg = run_mod._aggregate_sandbox(results)
    assert agg["fire_rate"] == 0.5
