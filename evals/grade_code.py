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
    exp = e.get("form")
    if isinstance(exp, list):
        return 10 if p.get("form") in exp else 0
    return 10 if p.get("form") == exp else 0


def _check_event_matches(p: dict, e: dict) -> int | None:
    if "event" not in e:
        return None  # not applicable (e.g. permissions.deny)
    exp = e["event"]
    if isinstance(exp, list):
        return 10 if p.get("event") in exp else 0
    return 10 if p.get("event") == exp else 0


def _check_matcher_matches(p: dict, e: dict) -> int | None:
    if "matcher" in e:
        return 10 if p.get("matcher") == e.get("matcher") else 0
    if "matcher_must_include" in e:
        m = p.get("matcher", "") or ""
        required = e["matcher_must_include"]
        return 10 if all(piece in m for piece in required) else 0
    return None


def _check_script_parses(p: dict, e: dict) -> int | None:
    form = p.get("form")
    if form != "command-hook":
        return None  # not applicable
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


def _check_sentinel_format(p: dict, e: dict) -> int | None:
    if p.get("form") in ("permissions.deny", "permissions.ask", "claude-md-note"):
        return None  # these forms don't carry sentinels
    name = p.get("sentinel_name") or ""
    return 10 if SENTINEL_RE.match(name) else 0


def _check_rationale_keywords(p: dict, e: dict) -> int:
    required = e.get("rationale_must_mention") or []
    if not required:
        return 10
    rationale = (p.get("rationale") or "").lower()
    return 10 if all(kw.lower() in rationale for kw in required) else 0


def _check_rule_pattern(p: dict, e: dict) -> int | None:
    """For permissions.ask / permissions.deny proposals, verify the rule string."""
    if "rule_pattern" in e:
        return 10 if p.get("rule") == e["rule_pattern"] else 0
    if "rule_pattern_must_contain" in e:
        rule = p.get("rule", "") or ""
        return 10 if e["rule_pattern_must_contain"] in rule else 0
    return None


# Rubric criterion 12 (v0.3.1+): command-hooks that emit stderr feedback must use
# imperative voice. Banned phrasing licenses inaction; required phrasing compels it.
_STDERR_BANNED_RE = re.compile(
    r"\b(audit|consider|verify|review)\b|\bor\b\s+\S+\s+\bis\s+unrelated\b",
    re.IGNORECASE,
)
# Action-forcing phrasing: the explicit v0.3.1 tokens, OR a clause that LEADS with
# an imperative action verb (so "Fix the reported issues before continuing." counts).
# Stays a binary pattern match per the founding doc — no fuzzy/NLP scoring.
_STDERR_REQUIRED_RE = re.compile(
    r"\b(REQUIRED FOLLOW-UP|DO NOT STOP|FIX EACH|BLOCKING|DO NOT ASK)\b"
    r"|(?:^|[.\n]\s*)(Fix|Run|Update|Replace|Remove|Add|Rerun|Regenerate|Revert|Migrate|Delete|Rename)\b",
    re.IGNORECASE,
)
# Stderr-writing calls across the three languages we generate.
_JS_STDERR_CALL_RE = re.compile(r"console\.error\s*\((.*?)\)", re.DOTALL)
_SH_STDERR_CALL_RE = re.compile(r"(?:echo|printf)\b(.*?)>&\s*2", re.DOTALL)
# String literals: double / single / backtick. f-, r-, b- prefixes sit OUTSIDE
# the quote, so capturing the quoted span works regardless of prefix.
_STRING_LITERAL_RE = re.compile(r'"([^"]*)"|\'([^\']*)\'|`([^`]*)`')


def _extract_stderr_strings(script: str) -> list[str]:
    """Pull literal text from every stderr-writing call (Python / JS / bash).

    Handles f-strings, r-strings, multiple calls, and JS template literals.
    Interpolation braces ({name}, ${n}) stay inside the captured text —
    harmless for phrase matching. Returns [] when the script writes no stderr.

    Python prints are isolated per-call (split before each `print(`) so a
    preceding stdout print cannot bleed its text into a later stderr scan.
    """
    regions: list[str] = []
    for call in re.split(r"(?=\bprint\s*\()", script):
        if re.search(r"file\s*=\s*sys\.stderr", call):
            m = re.match(r"print\s*\((.*?)file\s*=\s*sys\.stderr", call, re.DOTALL)
            if m:
                regions.append(m.group(1))
    for rx in (_JS_STDERR_CALL_RE, _SH_STDERR_CALL_RE):
        regions.extend(rx.findall(script))

    out: list[str] = []
    for region in regions:
        for dq, sq, bq in _STRING_LITERAL_RE.findall(region):
            lit = dq or sq or bq
            if lit:
                out.append(lit)
    return out


_BLOCKING_EVENTS = {"PreToolUse", "Stop", "SubagentStop", "UserPromptSubmit"}


def _check_imperative_stderr(p: dict, e: dict) -> int | None:
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

    Returns 10 (pass), 0 (fail), or None (not applicable).
    """
    if p.get("form") != "command-hook":
        return None  # not applicable
    script = p.get("script") or ""
    stderr_strings = _extract_stderr_strings(script)
    if not stderr_strings:
        return None  # hook doesn't write to stderr — n/a
    combined = " ".join(stderr_strings)
    if _STDERR_BANNED_RE.search(combined):
        return 0
    if p.get("event") in _BLOCKING_EVENTS:
        return 10  # blocking event — stderr is explanation, banned-only check
    # Non-blocking event (PostToolUse, etc.) — require an action-forcing phrase
    if not _STDERR_REQUIRED_RE.search(combined):
        return 0
    return 10


def _rules_present(p: dict, e: dict):
    """For coverage fixtures: which required substrings the proposal's rule covers.

    Returns None when the fixture has no `required_rules` (run.py then skips
    coverage for it). Not a 0/10 check — it feeds the cross-proposal coverage
    rollup in run.py.
    """
    req = e.get("required_rules")
    if not req:
        return None
    rule = p.get("rule") or ""
    return [r for r in req if r in rule]


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
    """Return {checks: {name: 0|10|None}, mean, degenerate, rules_present}.

    A check returning None does not apply and is excluded from the mean
    (applicable-checks denominator). `rules_present` feeds run.py's
    cross-proposal coverage rollup for `required_rules` fixtures.
    """
    checks = {name: fn(proposal, expected) for name, fn in _CHECKS.items()}
    applicable = [v for v in checks.values() if v is not None]
    mean = (sum(applicable) / len(applicable)) if applicable else 0.0
    return {
        "checks": checks,
        "mean": mean,
        "degenerate": len(applicable) == 0,
        "rules_present": _rules_present(proposal, expected),
    }
