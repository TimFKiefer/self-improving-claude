"""Tests for evals/grade_code.py — deterministic proposal grader.

Each check returns a score 0 or 10. The overall code-grade is the mean.
The proposal dict shape is documented in evals/grade_code.py.

Run: python3 -m pytest evals/tests/test_grade_code.py -v
"""
import pytest

from evals.grade_code import grade_code


PERFECT_BASH_BLOCK_HOOK = {
    "form": "command-hook",
    "event": "PreToolUse",
    "matcher": "Bash",
    "rationale": "Blocks `pnpm test` (interactive watcher); steers Claude to `pnpm test:ci`.",
    "script_lang": "python",
    "script": """import json, sys
def main():
    try:
        ev = json.load(sys.stdin)
    except Exception:
        return 0
    if ev.get("tool_name") != "Bash":
        return 0
    cmd = (ev.get("tool_input") or {}).get("command", "")
    if cmd.strip().startswith("pnpm test") and "test:ci" not in cmd:
        print("Use pnpm test:ci", file=sys.stderr)
        return 2
    return 0
if __name__ == "__main__":
    sys.exit(main())
""",
    "sentinel_name": "self-improving-claude/block-pnpm-test-watcher",
}

EXPECTED_001 = {
    "form": "command-hook",
    "event": "PreToolUse",
    "matcher": "Bash",
    "blocks_command_prefix": "pnpm test",
    "allows_command": "pnpm test:ci",
    "rationale_must_mention": ["pnpm test:ci", "watcher"],
}


def test_perfect_proposal_gets_full_marks():
    result = grade_code(PERFECT_BASH_BLOCK_HOOK, EXPECTED_001)
    assert result["mean"] == 10.0
    # Each individual check should also pass
    for check, score in result["checks"].items():
        assert score == 10, f"Check {check!r} failed unexpectedly"


def test_grade_rejects_wrong_form():
    bad = dict(PERFECT_BASH_BLOCK_HOOK, form="permissions.deny")
    result = grade_code(bad, EXPECTED_001)
    assert result["checks"]["form_matches"] == 0
    assert result["mean"] < 10.0


def test_grade_rejects_wrong_event():
    bad = dict(PERFECT_BASH_BLOCK_HOOK, event="PostToolUse")
    result = grade_code(bad, EXPECTED_001)
    assert result["checks"]["event_matches"] == 0


def test_grade_rejects_wrong_matcher():
    bad = dict(PERFECT_BASH_BLOCK_HOOK, matcher="Write")
    result = grade_code(bad, EXPECTED_001)
    assert result["checks"]["matcher_matches"] == 0


def test_grade_rejects_script_with_syntax_error():
    bad = dict(PERFECT_BASH_BLOCK_HOOK, script="def x(:\n    pass")
    result = grade_code(bad, EXPECTED_001)
    assert result["checks"]["script_parses"] == 0


def test_grade_rejects_missing_sentinel():
    bad = dict(PERFECT_BASH_BLOCK_HOOK, sentinel_name="my-hook")
    result = grade_code(bad, EXPECTED_001)
    assert result["checks"]["sentinel_format"] == 0


def test_grade_rejects_rationale_missing_required_keywords():
    bad = dict(PERFECT_BASH_BLOCK_HOOK, rationale="A nice idea.")
    result = grade_code(bad, EXPECTED_001)
    assert result["checks"]["rationale_keywords"] == 0


def test_grade_handles_permissions_deny_proposal():
    """For form='permissions.deny', there's no script — only the rule string."""
    proposal = {
        "form": "permissions.deny",
        "rule": "Read(**/.env)",
        "rationale": "Blocks .env reads uniformly across tools.",
        "sentinel_name": None,  # permissions.deny rules don't carry sentinels
    }
    expected = {
        "form": "permissions.deny",
        "rule_pattern": "Read(**/.env)",
        "rationale_must_mention": [".env"],
    }
    result = grade_code(proposal, expected)
    assert result["mean"] >= 7.0  # at least 70% of checks pass for a clean match


def test_grade_returns_per_check_dict():
    """Caller needs the breakdown to render scorecards."""
    result = grade_code(PERFECT_BASH_BLOCK_HOOK, EXPECTED_001)
    assert "checks" in result
    assert "mean" in result
    assert isinstance(result["checks"], dict)
    # Specific keys we promise
    for key in ("form_matches", "event_matches", "matcher_matches",
                "script_parses", "sentinel_format", "rationale_keywords"):
        assert key in result["checks"]


def test_grade_script_lang_javascript_parses():
    """If the model picks JS, we still check syntax (with node --check)."""
    proposal = dict(
        PERFECT_BASH_BLOCK_HOOK,
        script_lang="javascript",
        script="""process.stdin.on("data", d => { try { JSON.parse(d); } catch(e) {} });""",
    )
    result = grade_code(proposal, EXPECTED_001)
    # As long as the JS parses, the script_parses check should pass.
    assert result["checks"]["script_parses"] == 10


def test_grade_matcher_must_include_passes_on_subset_match():
    proposal = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Edit|MultiEdit",
        "script": "import sys\nsys.exit(0)\n",
        "script_lang": "python",
        "rationale": "After editing an export, show callers.",
        "sentinel_name": "self-improving-claude/grep-callers",
    }
    expected = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher_must_include": ["Edit", "MultiEdit"],
        "rationale_must_mention": ["export", "caller"],
    }
    result = grade_code(proposal, expected)
    assert result["checks"]["matcher_matches"] == 10


def test_grade_matcher_must_include_fails_when_missing():
    proposal = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Write",
        "script": "import sys\nsys.exit(0)\n",
        "script_lang": "python",
        "rationale": "After editing an export, show callers.",
        "sentinel_name": "self-improving-claude/grep-callers",
    }
    expected = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher_must_include": ["Edit", "MultiEdit"],
        "rationale_must_mention": ["export", "caller"],
    }
    result = grade_code(proposal, expected)
    assert result["checks"]["matcher_matches"] == 0


def test_grade_permissions_ask_proposal():
    proposal = {
        "form": "permissions.ask",
        "rule": "Bash(git push:*)",
        "rationale": "Causes Claude Code to confirm before every git push.",
    }
    expected = {
        "form": "permissions.ask",
        "rule_pattern_must_contain": "Bash(git push",
        "rationale_must_mention": ["git push", "confirm"],
    }
    result = grade_code(proposal, expected)
    assert result["mean"] >= 8.0
    assert result["checks"]["form_matches"] == 10
    assert result["checks"]["rule_pattern"] == 10
    assert result["checks"]["rationale_keywords"] == 10


def test_grade_rule_pattern_must_contain_substring():
    proposal = {"form": "permissions.deny", "rule": "Read(**/.env.production)", "rationale": "Block reads of .env files"}
    expected = {"form": "permissions.deny", "rule_pattern_must_contain": ".env", "rationale_must_mention": [".env"]}
    result = grade_code(proposal, expected)
    assert result["checks"]["rule_pattern"] == 10
