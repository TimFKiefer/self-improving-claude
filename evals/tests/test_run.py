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
from evals.run import (
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

    result = run_one_entry(entries[0], client=FakeClient())
    assert result["id"] == "001-pnpm-test-watcher"
    assert "proposals" in result
    assert "code_grades" in result
    assert "model_grades" in result
    # With the canned proposal that mirrors expected_traits, code_grade should be high
    assert result["code_grades"][0]["mean"] >= 8.0


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
