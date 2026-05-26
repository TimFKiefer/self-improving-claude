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
import re
import shutil
import subprocess
import tempfile
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


_FENCE_OPEN_RE = re.compile(r"^```(?:json|JSON)?\s*\n?")
_FENCE_CLOSE_RE = re.compile(r"\n?```\s*$")


def _parse_echo(result_text: str) -> tuple[list[dict], bool]:
    """Extract the proposal list from the skill's final message.

    Returns (proposals, echo_valid). Tolerates ```json fences and a trailing JSON
    object after prose. Empty list + False when nothing parses.
    """
    text = result_text.strip()
    text = _FENCE_OPEN_RE.sub("", text)
    text = _FENCE_CLOSE_RE.sub("", text)
    candidates = [text]
    m = re.search(r"\{.*\}\s*$", text, re.DOTALL)
    if m:
        candidates.insert(0, m.group(0))
    for c in candidates:
        try:
            obj = json.loads(c)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "proposals" in obj:
            return (obj["proposals"] or [], True)
        if isinstance(obj, list):
            return (obj, True)
    return ([], False)


def _read_written(tmp: Path) -> dict:
    """Read back what the skill installed in the sandbox's .claude/."""
    settings_path = tmp / ".claude" / "settings.json"
    settings_parses = False
    settings: dict = {}
    permission_rules: list[str] = []
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            settings_parses = True
        except json.JSONDecodeError:
            settings_parses = False
    if settings_parses:
        perms = settings.get("permissions", {}) or {}
        for key in ("deny", "ask"):
            permission_rules.extend(perms.get(key, []) or [])
    hooks_dir = tmp / ".claude" / "hooks"
    hook_files = sorted(p.name for p in hooks_dir.glob("*")) if hooks_dir.exists() else []
    return {
        "settings_parses": settings_parses,
        "settings": settings if settings_parses else {},
        "hook_files": hook_files,
        "permission_rules": permission_rules,
    }


def run_in_sandbox(*, entry: dict, fixture: Fixture, model: str,
                   plugin_path: Path, timeout: float = 600) -> dict:
    """Drive the real slash command headlessly for one (fixture x model).

    Returns {echo, echo_valid, written, raw_result, returncode, error}. Always
    tears down the temp project, even on failure.
    """
    command = "/improve" if entry["trigger"] == "improve" else "/improve-init"
    user_args = (entry.get("user_args") or "").strip()
    if user_args:
        command = f"{command} {user_args}"
    override = _build_override(entry, fixture)
    tmp = Path(tempfile.mkdtemp(prefix="sic-eval-"))
    try:
        _build_sandbox(tmp, fixture)
        argv = _build_argv(model=model, command=command, plugin_path=plugin_path, override=override)
        try:
            proc = subprocess.run(argv, cwd=str(tmp), capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError as e:
            raise RuntimeError("`claude` CLI not found on PATH — is Claude Code installed?") from e
        error = None
        result_text = ""
        if proc.returncode != 0:
            error = f"claude rc={proc.returncode}: {(proc.stderr or '')[:500]}"
        else:
            try:
                payload = json.loads(proc.stdout)
                result_text = payload.get("result", "") if isinstance(payload, dict) else ""
            except json.JSONDecodeError:
                result_text = proc.stdout
        echo, echo_valid = _parse_echo(result_text)
        written = _read_written(tmp)
        return {
            "echo": echo, "echo_valid": echo_valid, "written": written,
            "raw_result": result_text, "returncode": proc.returncode, "error": error,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
