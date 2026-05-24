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
    # Each applicable check passes; non-applicable checks are None (excluded).
    for check, score in result["checks"].items():
        assert score in (None, 10), f"Check {check!r} failed unexpectedly"


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


# --- imperative_stderr check (rubric criterion 12) ---

_IMPERATIVE_SCRIPT = """\
import json, sys
def main():
    ev = json.load(sys.stdin)
    print("REQUIRED FOLLOW-UP: N stale references remain.", file=sys.stderr)
    print("Fix each, then summarize. Do not stop.", file=sys.stderr)
    return 2
if __name__ == "__main__":
    sys.exit(main())
"""

_PASSIVE_SCRIPT = """\
import json, sys
def main():
    ev = json.load(sys.stdin)
    print("Found references. Verify these are consistent with your change.", file=sys.stderr)
    print("Audit any hardcoded usages or consider whether they are unrelated.", file=sys.stderr)
    return 2
if __name__ == "__main__":
    sys.exit(main())
"""

_NO_STDERR_SCRIPT = """\
import json, sys
def main():
    return 0
if __name__ == "__main__":
    sys.exit(main())
"""

EXPECTED_HOOK = {
    "form": "command-hook",
    "event": "PostToolUse",
    "matcher_must_include": ["Edit"],
    "rationale_must_mention": ["export"],
}


def test_imperative_stderr_passes_on_action_forcing_voice():
    proposal = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Edit|MultiEdit",
        "script": _IMPERATIVE_SCRIPT,
        "script_lang": "python",
        "rationale": "Surfaces callers after an export edit.",
        "sentinel_name": "self-improving-claude/grep-callers",
    }
    result = grade_code(proposal, EXPECTED_HOOK)
    assert result["checks"]["imperative_stderr"] == 10


def test_imperative_stderr_fails_on_passive_voice():
    proposal = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Edit|MultiEdit",
        "script": _PASSIVE_SCRIPT,
        "script_lang": "python",
        "rationale": "Surfaces callers after an export edit.",
        "sentinel_name": "self-improving-claude/grep-callers",
    }
    result = grade_code(proposal, EXPECTED_HOOK)
    assert result["checks"]["imperative_stderr"] == 0


def test_imperative_stderr_na_when_no_stderr_emitted():
    """Hooks that don't write to stderr (pure block-or-allow, no message) get full marks."""
    proposal = {
        "form": "command-hook",
        "event": "PreToolUse",
        "matcher": "Bash",
        "script": _NO_STDERR_SCRIPT,
        "script_lang": "python",
        "rationale": "Block without explanation.",
        "sentinel_name": "self-improving-claude/silent-block",
    }
    result = grade_code(proposal, {"form": "command-hook", "event": "PreToolUse", "matcher": "Bash"})
    assert result["checks"]["imperative_stderr"] is None


def test_imperative_stderr_na_for_permissions_forms():
    """permissions.deny / permissions.ask have no script, hence no stderr — n/a."""
    proposal = {"form": "permissions.ask", "rule": "Bash(git push:*)", "rationale": "Ask before push"}
    result = grade_code(proposal, {"form": "permissions.ask", "rule_pattern_must_contain": "git push"})
    assert result["checks"]["imperative_stderr"] is None


def test_imperative_stderr_fails_on_partial_passive():
    """Even one banned phrase amid required ones fails — banned takes precedence."""
    proposal = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Edit",
        "script": """\
import sys
print("REQUIRED FOLLOW-UP: Fix each.", file=sys.stderr)
print("Or verify the reference is unrelated.", file=sys.stderr)
""",
        "script_lang": "python",
        "rationale": "x",
        "sentinel_name": "self-improving-claude/x",
    }
    result = grade_code(proposal, EXPECTED_HOOK)
    # Has REQUIRED FOLLOW-UP but ALSO has "verify ... is unrelated" (escape hatch)
    assert result["checks"]["imperative_stderr"] == 0


def test_imperative_stderr_requires_at_least_one_action_phrase():
    """Stderr that's neutral (neither banned nor required) gets 0 — no force."""
    proposal = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Edit",
        "script": """\
import sys
print("Done.", file=sys.stderr)
print("Result: N references found.", file=sys.stderr)
""",
        "script_lang": "python",
        "rationale": "x",
        "sentinel_name": "self-improving-claude/x",
    }
    result = grade_code(proposal, EXPECTED_HOOK)
    assert result["checks"]["imperative_stderr"] == 0


# --- imperative_stderr: multi-language / f-string coverage (v0.3.3) ---

def test_imperative_stderr_catches_banned_word_in_fstring():
    """A passive word hidden in an f-string must be caught (was a false pass pre-v0.3.3)."""
    proposal = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Edit",
        "script": 'import sys\nprint(f"Audit the {n} callers of {name}.", file=sys.stderr)\n',
        "script_lang": "python",
        "rationale": "x",
        "sentinel_name": "self-improving-claude/x",
    }
    result = grade_code(proposal, EXPECTED_HOOK)
    assert result["checks"]["imperative_stderr"] == 0


def test_imperative_stderr_requires_action_phrase_in_fstring_only_message():
    """Non-blocking stderr that is ONLY a neutral f-string (no action phrase) fails."""
    proposal = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Edit",
        "script": 'import sys\nprint(f"Found {n} references.", file=sys.stderr)\n',
        "script_lang": "python",
        "rationale": "x",
        "sentinel_name": "self-improving-claude/x",
    }
    result = grade_code(proposal, EXPECTED_HOOK)
    assert result["checks"]["imperative_stderr"] == 0


def test_imperative_stderr_passes_imperative_fstring():
    """An action-forcing f-string passes (it was previously scored n/a by accident)."""
    proposal = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Edit",
        "script": 'import sys\nprint(f"BLOCKING: {n} stale refs. Fix each. Do not stop.", file=sys.stderr)\n',
        "script_lang": "python",
        "rationale": "x",
        "sentinel_name": "self-improving-claude/x",
    }
    result = grade_code(proposal, EXPECTED_HOOK)
    assert result["checks"]["imperative_stderr"] == 10


def test_imperative_stderr_catches_passive_bash_echo():
    """Bash hooks that echo passive text to stderr must be caught."""
    proposal = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Edit",
        "script": 'echo "consider reviewing these references" >&2\nexit 2\n',
        "script_lang": "bash",
        "rationale": "x",
        "sentinel_name": "self-improving-claude/x",
    }
    result = grade_code(proposal, EXPECTED_HOOK)
    assert result["checks"]["imperative_stderr"] == 0


def test_imperative_stderr_catches_passive_console_error():
    """JS hooks using console.error with passive text must be caught."""
    proposal = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Edit",
        "script": 'console.error("Audit these usages");\nprocess.exit(2);\n',
        "script_lang": "javascript",
        "rationale": "x",
        "sentinel_name": "self-improving-claude/x",
    }
    result = grade_code(proposal, EXPECTED_HOOK)
    assert result["checks"]["imperative_stderr"] == 0


def test_imperative_stderr_passes_imperative_js_template_literal():
    """A JS template literal with an action phrase passes."""
    proposal = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Edit",
        "script": 'console.error(`BLOCKING: ${n} refs. Fix each. Do not stop.`);\n',
        "script_lang": "javascript",
        "rationale": "x",
        "sentinel_name": "self-improving-claude/x",
    }
    result = grade_code(proposal, EXPECTED_HOOK)
    assert result["checks"]["imperative_stderr"] == 10


def test_imperative_stderr_adjacent_stdout_print_not_scanned():
    """A stdout print's text must not bleed into the stderr scan."""
    proposal = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Edit",
        "script": (
            'import sys\n'
            'print("audit summary")\n'                      # stdout — must be ignored
            'print(f"BLOCKING: {n}. Fix each. Do not stop.", file=sys.stderr)\n'
        ),
        "script_lang": "python",
        "rationale": "x",
        "sentinel_name": "self-improving-claude/x",
    }
    result = grade_code(proposal, EXPECTED_HOOK)
    # "audit" lives only on the stdout line — must NOT trigger the banned check.
    assert result["checks"]["imperative_stderr"] == 10


# --- v0.3.4: applicable-checks denominator (N/A -> None) ---

def test_na_checks_are_none_and_excluded():
    proposal = {"form": "permissions.deny", "rule": "Read(**/.env*)",
                "rationale": "block .env reads"}
    expected = {"form": "permissions.deny", "rule_pattern": "Read(**/.env*)",
                "rationale_must_mention": [".env"]}
    r = grade_code(proposal, expected)
    assert r["checks"]["event_matches"] is None
    assert r["checks"]["matcher_matches"] is None
    assert r["checks"]["script_parses"] is None
    assert r["checks"]["sentinel_format"] is None
    assert r["checks"]["imperative_stderr"] is None
    assert r["mean"] == 10.0


def test_wrong_form_scored_below_right_form():
    expected = {"form": "command-hook", "event": "PostToolUse",
                "matcher": "Edit", "rationale_must_mention": ["x"]}
    right = {"form": "command-hook", "event": "PostToolUse", "matcher": "Edit",
             "script": "import sys", "script_lang": "python",
             "rationale": "x reason", "sentinel_name": "self-improving-claude/a"}
    wrong = {**right, "form": "permissions.deny"}
    assert grade_code(wrong, expected)["mean"] < grade_code(right, expected)["mean"]


# --- v0.3.4: broadened imperative_stderr (intent, not literal tokens) ---

def _post_hook(script):
    return {"form": "command-hook", "event": "PostToolUse", "matcher": "Edit",
            "script": script, "script_lang": "python",
            "rationale": "x", "sentinel_name": "self-improving-claude/x"}


def test_imperative_stderr_accepts_fix_directive():
    p = _post_hook('import sys\nprint("ruff check failed. Fix the reported issues before continuing.", file=sys.stderr)\n')
    assert grade_code(p, {"form": "command-hook"})["checks"]["imperative_stderr"] == 10


def test_imperative_stderr_still_fails_neutral_found_message():
    p = _post_hook('import sys\nprint("Found 3 references.", file=sys.stderr)\n')
    assert grade_code(p, {"form": "command-hook"})["checks"]["imperative_stderr"] == 0


# --- v0.3.4: form/event set-membership + rules_present ---

def test_form_set_membership():
    expected = {"form": ["prompt-hook", "command-hook"]}
    assert grade_code({"form": "command-hook"}, expected)["checks"]["form_matches"] == 10
    assert grade_code({"form": "prompt-hook"}, expected)["checks"]["form_matches"] == 10
    assert grade_code({"form": "permissions.deny"}, expected)["checks"]["form_matches"] == 0


def test_event_set_membership():
    expected = {"form": "command-hook", "event": ["PreToolUse", "PostToolUse"]}
    p = {"form": "command-hook", "event": "PostToolUse", "script": "import sys",
         "script_lang": "python", "rationale": "y",
         "sentinel_name": "self-improving-claude/x"}
    assert grade_code(p, expected)["checks"]["event_matches"] == 10


def test_required_rules_presence():
    expected = {"form": "permissions.deny",
                "required_rules": ["src/generated/prisma", "prisma/dev.db"]}
    p = {"form": "permissions.deny", "rule": "Edit(src/generated/prisma/**)",
         "rationale": "block generated"}
    assert grade_code(p, expected)["rules_present"] == ["src/generated/prisma"]
