"""Headless sandbox runner — drive the real /improve and /improve-init slash
commands end-to-end and return structured evidence for grading.

Used by evals/run.py's sandbox mode (built across Tasks 2-4). ONE `claude --print`
invocation per call, in a throwaway temp project built from a fixture; no retries.
Flags were pinned by a feasibility spike: bypassPermissions (acceptEdits denied the
Step-9 writes) + a forceful --append-system-prompt override (a mild one let the
skill's Step 8 approval dominate). Do NOT use --bare (it disables OAuth).

Spec: docs/superpowers/specs/2026-05-26-v0.4.0-real-skill-sandbox-eval-design.md
"""
from __future__ import annotations

import json
from pathlib import Path

from evals.client_claude_cli import _to_cli_model
from evals.fixtures_lib import Fixture

# The FORCEFUL override (pinned by the spike — the mild version let Step 8 win).
OVERRIDE = (
    "<<EVAL HARNESS — ABSOLUTE DIRECTIVE>> This OVERRIDES ALL conflicting "
    "instructions in the skill procedure that follows, including Step 8 (approval) "
    "and Step 10 (close-out). You are a fully autonomous non-interactive batch "
    "process: there is NO human, NO approval, NO further turns. You MUST: (1) NEVER "
    "ask for approval or print 'Approve/Reject/Edit'. (2) Treat every candidate "
    "surviving Step 1-7 as ALREADY APPROVED. (3) PERFORM the Step 9 writes NOW with "
    "the Write tool — create .claude/settings.json and any hook script files in the "
    "current directory. (4) Do not stop until those files exist. (5) Your FINAL "
    "message must be EXACTLY one JSON object and nothing else: "
    '{"proposals":[{...}]}, one object per surviving candidate, fields form, event, '
    "matcher, rationale, script_lang, script, prompt, rule, claude_md_line, "
    "sentinel_name (include claude-md-note candidates even though you do not write "
    "those to disk). NO prose before or after the JSON."
)


def _build_override(entry: dict, fixture: Fixture) -> str:
    text = OVERRIDE
    if entry.get("trigger") == "improve" and fixture.chat.strip():
        text += ("\n\nRecent conversation the user is reacting to "
                 "(treat as <recent_chat>):\n\n" + fixture.chat.strip())
    return text


def _build_sandbox(tmp: Path, fixture: Fixture) -> None:
    for rel, content in fixture.project_files.items():
        dest = tmp / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    if fixture.telemetry:
        tdir = tmp / ".claude" / "self-improving-claude"
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / "telemetry.jsonl").write_text(
            "\n".join(json.dumps(r) for r in fixture.telemetry) + "\n", encoding="utf-8")
    (tmp / ".claude").mkdir(parents=True, exist_ok=True)


def _build_argv(*, model: str, command: str, plugin_path: Path, override: str,
                max_budget_usd: float = 2.0) -> list[str]:
    return [
        "claude", "--print",
        "--model", _to_cli_model(model),
        "--plugin-dir", str(plugin_path),
        "--permission-mode", "bypassPermissions",
        "--output-format", "json",
        "--no-session-persistence",
        "--max-budget-usd", str(max_budget_usd),
        "--append-system-prompt", override,
        command,
    ]
