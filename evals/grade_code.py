"""Deterministic code-based grader for proposed hooks.

Proposal dict shape (produced by the model in eval mode):

  {
    "form": "command-hook" | "prompt-hook" | "permissions.deny" | "claude-md-note",
    "event": "PreToolUse" | "PostToolUse" | ...        (omit for permissions.deny)
    "matcher": "Bash" | "Read|Write" | "*" | ...        (omit for permissions.deny)
    "rationale": str,                                   (one-sentence why)
    "script_lang": "python" | "bash" | "javascript" | None
    "script": str | None,                               (the hook body, if command-hook)
    "prompt": str | None,                               (the prompt body, if prompt-hook)
    "rule": str | None,                                 (the deny string, if permissions.deny)
    "claude_md_line": str | None,                       (the # line, if claude-md-note)
    "sentinel_name": str | None,                        ("self-improving-claude/<slug>")
  }

Each check returns 0 or 10. The overall mean is in result["mean"].
"""
from __future__ import annotations

import ast
import re
import subprocess

SENTINEL_RE = re.compile(r"^self-improving-claude/[a-z][a-z0-9-]*[a-z0-9]$")


def _check_form_matches(p: dict, e: dict) -> int:
    return 10 if p.get("form") == e.get("form") else 0


def _check_event_matches(p: dict, e: dict) -> int:
    if "event" not in e:
        return 10  # not applicable (e.g. permissions.deny)
    return 10 if p.get("event") == e.get("event") else 0


def _check_matcher_matches(p: dict, e: dict) -> int:
    if "matcher" in e:
        return 10 if p.get("matcher") == e.get("matcher") else 0
    if "matcher_must_include" in e:
        m = p.get("matcher", "") or ""
        required = e["matcher_must_include"]
        return 10 if all(piece in m for piece in required) else 0
    return 10


def _check_script_parses(p: dict, e: dict) -> int:
    form = p.get("form")
    if form != "command-hook":
        return 10  # not applicable
    lang = (p.get("script_lang") or "").lower()
    script = p.get("script") or ""
    if not script:
        return 0
    if lang == "python":
        try:
            ast.parse(script)
            return 10
        except SyntaxError:
            return 0
    if lang == "bash":
        try:
            subprocess.run(["bash", "-n"], input=script, text=True, check=True, capture_output=True)
            return 10
        except (subprocess.CalledProcessError, FileNotFoundError):
            return 0
    if lang in ("javascript", "js", "node"):
        try:
            subprocess.run(["node", "--check", "/dev/stdin"], input=script, text=True, check=True, capture_output=True)
            return 10
        except (subprocess.CalledProcessError, FileNotFoundError):
            return 0
    return 0  # unknown language


def _check_sentinel_format(p: dict, e: dict) -> int:
    if p.get("form") in ("permissions.deny", "claude-md-note"):
        return 10  # these forms don't carry sentinels
    name = p.get("sentinel_name") or ""
    return 10 if SENTINEL_RE.match(name) else 0


def _check_rationale_keywords(p: dict, e: dict) -> int:
    required = e.get("rationale_must_mention") or []
    if not required:
        return 10
    rationale = (p.get("rationale") or "").lower()
    return 10 if all(kw.lower() in rationale for kw in required) else 0


def _check_rule_pattern(p: dict, e: dict) -> int:
    """For permissions.ask / permissions.deny proposals, verify the rule string."""
    if "rule_pattern" in e:
        return 10 if p.get("rule") == e["rule_pattern"] else 0
    if "rule_pattern_must_contain" in e:
        rule = p.get("rule", "") or ""
        return 10 if e["rule_pattern_must_contain"] in rule else 0
    return 10


# Rubric criterion 12 (v0.3.1+): command-hooks that emit stderr feedback must use
# imperative voice. Banned phrasing licenses inaction; required phrasing compels it.
_STDERR_BANNED_RE = re.compile(
    r"\b(audit|consider|verify|review)\b|\bor\b\s+\S+\s+\bis\s+unrelated\b",
    re.IGNORECASE,
)
_STDERR_REQUIRED_RE = re.compile(
    r"\b(REQUIRED FOLLOW-UP|DO NOT STOP|FIX EACH|BLOCKING|DO NOT ASK)\b",
    re.IGNORECASE,
)
_STDERR_PRINT_RE = re.compile(
    r'print\s*\(\s*["\']([^"\']+)["\'].*?file\s*=\s*sys\.stderr',
    re.DOTALL,
)


_BLOCKING_EVENTS = {"PreToolUse", "Stop", "SubagentStop", "UserPromptSubmit"}


def _check_imperative_stderr(p: dict, e: dict) -> int:
    """For command-hooks whose scripts write to stderr, verify imperative voice.

    Per rubric criterion 12 (v0.3.1+): banned phrasing ("audit", "consider",
    "verify these are", "review", "or X is unrelated") licenses model inaction.
    Required phrasing ("REQUIRED FOLLOW-UP", "Do not stop", "Fix each",
    "BLOCKING", "Do not ask") compels action.

    Event-aware strictness:
    - Blocking events (PreToolUse / Stop / SubagentStop / UserPromptSubmit) — the
      hook's exit-2 actually halts the model. Stderr is the explanation, not the
      enforcement. Banned phrasing is still flagged, but we don't require the
      strong action-forcing keywords (a simple "Use X instead" is fine).
    - PostToolUse and other non-blocking events — exit-2 only feeds context to a
      free-to-keep-going model. The stderr IS the enforcement mechanism. Require
      both: no banned phrasing AND at least one required action phrase.

    Returns 10 (n/a or pass), 0 (fail).
    """
    if p.get("form") != "command-hook":
        return 10  # not applicable
    script = p.get("script") or ""
    stderr_strings = _STDERR_PRINT_RE.findall(script)
    if not stderr_strings:
        return 10  # hook doesn't write to stderr — n/a
    combined = " ".join(stderr_strings)
    if _STDERR_BANNED_RE.search(combined):
        return 0
    if p.get("event") in _BLOCKING_EVENTS:
        return 10  # blocking event — stderr is explanation, banned-only check
    # Non-blocking event (PostToolUse, etc.) — require an action-forcing phrase
    if not _STDERR_REQUIRED_RE.search(combined):
        return 0
    return 10


_CHECKS = {
    "form_matches": _check_form_matches,
    "event_matches": _check_event_matches,
    "matcher_matches": _check_matcher_matches,
    "script_parses": _check_script_parses,
    "sentinel_format": _check_sentinel_format,
    "rationale_keywords": _check_rationale_keywords,
    "imperative_stderr": _check_imperative_stderr,
    "rule_pattern": _check_rule_pattern,
}


def grade_code(proposal: dict, expected: dict) -> dict:
    """Return {checks: {name: 0|10}, mean: float}."""
    checks = {name: fn(proposal, expected) for name, fn in _CHECKS.items()}
    mean = sum(checks.values()) / len(checks)
    return {"checks": checks, "mean": mean}
