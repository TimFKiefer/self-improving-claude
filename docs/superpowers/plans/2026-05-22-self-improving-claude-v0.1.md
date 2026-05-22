# self-improving-claude v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a working v0.1 of the `self-improving-claude` Claude Code plugin — a user can install it, run `/improve-init`, see sensible hook proposals, approve some, restart Claude Code, and find the approved hooks firing.

**Architecture:** A Claude Code plugin with three skills (one user-invoked entry skill, one model-invoked orchestrator skill, with five distilled reference docs), a bundled `PostToolUse: "*"` telemetry hook script with strict redaction, and a defensive `settings.json` merge that the orchestrator performs in the user's live session.

**Tech Stack:** Python 3 (stdlib only for the shipped telemetry script; pytest for dev tests), Markdown + YAML frontmatter for skills, JSON for plugin/hook configuration.

**Spec:** `docs/superpowers/specs/2026-05-22-self-improving-claude-design.md` is authoritative — refer to it whenever a step references the rubric, the merge algorithm, the telemetry summarization rules, or the orchestrator procedure.

**Working directory for every command:** `~/Desktop/Projects/self-improving-claude`

---

## Task 1: Plugin scaffold (manifest + LICENSE)

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `LICENSE`

**Purpose:** Establishes a valid Claude Code plugin skeleton. With just these two files plus the existing `README.md`, the plugin is technically loadable (it will register zero skills/hooks, but the manifest is valid).

- [ ] **Step 1: Create the plugin manifest**

Create `.claude-plugin/plugin.json` with this exact content:

```json
{
  "name": "self-improving-claude",
  "version": "0.1.0",
  "description": "Turns the bugs you just saw into the hooks that prevent the next ones — a Claude Code plugin that uses /improve and /improve-init to convert observed footguns into per-project hooks, with explicit per-hook user approval.",
  "author": {
    "name": "Tim Kiefer",
    "email": "tim.f.kief@gmail.com"
  },
  "license": "MIT",
  "keywords": ["claude-code", "hooks", "self-improving", "guardrails", "code-quality"]
}
```

- [ ] **Step 2: Verify the manifest parses as valid JSON**

Run from repo root:
```bash
python3 -c "import json; json.load(open('.claude-plugin/plugin.json')); print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Create the LICENSE file (MIT)**

Create `LICENSE` with this exact content (replace YEAR if anything other than 2026 is current):

```
MIT License

Copyright (c) 2026 Tim Kiefer

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 4: Commit**

```bash
git add .claude-plugin/plugin.json LICENSE
git commit -m "Add plugin manifest and LICENSE — minimum loadable plugin"
```

---

## Task 2: Bundled telemetry-hook registration

**Files:**
- Create: `hooks/hooks.json`

**Purpose:** Registers the bundled telemetry hook so that whenever a user enables the plugin, the `PostToolUse: "*"` hook is auto-applied. Uses `${CLAUDE_PLUGIN_ROOT}` so the path is portable across machines.

- [ ] **Step 1: Create the hooks registration**

Create `hooks/hooks.json` with this exact content:

```json
{
  "description": "self-improving-claude — passive telemetry hook that logs summarized tool usage for /improve-init",
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "name": "self-improving-claude/telemetry",
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/telemetry.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Verify the file parses as valid JSON**

```bash
python3 -c "import json; json.load(open('hooks/hooks.json')); print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add hooks/hooks.json
git commit -m "Register bundled telemetry hook (PostToolUse: \"*\")"
```

---

## Task 3: Telemetry script with redaction (TDD)

**Files:**
- Create: `scripts/telemetry.py`
- Create: `scripts/tests/__init__.py`
- Create: `scripts/tests/test_telemetry.py`

**Purpose:** Implements the bundled hook script. Stdlib-only Python. Reads JSON from stdin, applies per-tool summarization rules from spec §3.4, appends a JSONL row to `${CLAUDE_PROJECT_DIR}/.claude/self-improving-claude/telemetry.jsonl`. Strict: never logs file contents, never logs raw bash output > 200 chars, never logs URL query strings, never logs raw env values. Silent-fail on any unexpected error (don't break Claude Code's tool execution).

We use pure stdlib (`json`, `os`, `sys`, `pathlib`, `datetime`, `re`) so the shipped script has zero install footprint on the user's machine.

- [ ] **Step 1: Write the failing tests**

Create `scripts/tests/__init__.py` as an empty file:

```bash
mkdir -p scripts/tests
touch scripts/tests/__init__.py
```

Create `scripts/tests/test_telemetry.py`:

```python
"""Tests for scripts/telemetry.py.

These tests run the telemetry script as a subprocess, feeding it JSON via
stdin and pointing CLAUDE_PROJECT_DIR at a tempdir. They assert on the
resulting JSONL row to verify per-tool redaction rules from spec §3.4.

Run: python3 -m pytest scripts/tests/test_telemetry.py -v
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "telemetry.py"


def run_telemetry(payload: dict, project_dir: Path) -> dict | None:
    """Run telemetry.py with the given hook payload. Return the JSONL row written, or None."""
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    # Telemetry must NEVER exit non-zero — that would feed errors back to Claude.
    assert result.returncode == 0, f"stderr: {result.stderr}"
    log_path = project_dir / ".claude" / "self-improving-claude" / "telemetry.jsonl"
    if not log_path.exists():
        return None
    lines = log_path.read_text().strip().splitlines()
    return json.loads(lines[-1]) if lines else None


def test_bash_logs_summary_with_exit_code(tmp_path):
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "pnpm test"},
        "tool_response": {"exit_code": 1, "stderr": "ENOENT: missing module foo"},
    }
    row = run_telemetry(payload, tmp_path)
    assert row["tool"] == "Bash"
    assert row["args_summary"] == "pnpm test"
    assert row["outcome"]["exit_code"] == 1
    assert "ENOENT" in row["outcome"]["stderr_head"]
    assert "ts" in row


def test_bash_truncates_long_command_to_80_chars(tmp_path):
    long_cmd = "echo " + "x" * 200
    payload = {"tool_name": "Bash", "tool_input": {"command": long_cmd}, "tool_response": {"exit_code": 0}}
    row = run_telemetry(payload, tmp_path)
    assert len(row["args_summary"]) <= 80


def test_bash_truncates_stderr_to_200_chars(tmp_path):
    long_err = "x" * 1000
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "false"},
        "tool_response": {"exit_code": 1, "stderr": long_err},
    }
    row = run_telemetry(payload, tmp_path)
    assert len(row["outcome"]["stderr_head"]) <= 200


def test_bash_omits_stderr_on_success(tmp_path):
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "true"},
        "tool_response": {"exit_code": 0, "stderr": "warning: foo"},
    }
    row = run_telemetry(payload, tmp_path)
    # On success we only record exit_code, not stderr noise.
    assert row["outcome"]["exit_code"] == 0
    assert "stderr_head" not in row["outcome"]


def test_read_logs_path_only_not_content(tmp_path):
    payload = {
        "tool_name": "Read",
        "tool_input": {"file_path": "/secret/.env"},
        "tool_response": {"contents": "API_KEY=sk-leaked"},
    }
    row = run_telemetry(payload, tmp_path)
    assert row["args_summary"] == "/secret/.env"
    assert "API_KEY" not in json.dumps(row)
    assert "sk-leaked" not in json.dumps(row)


def test_write_logs_path_only(tmp_path):
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": "/code/foo.py", "content": "PASSWORD=hunter2"},
    }
    row = run_telemetry(payload, tmp_path)
    assert row["args_summary"] == "/code/foo.py"
    assert "hunter2" not in json.dumps(row)


def test_edit_logs_path_only(tmp_path):
    payload = {
        "tool_name": "Edit",
        "tool_input": {"file_path": "/code/foo.py", "old_string": "x", "new_string": "y"},
    }
    row = run_telemetry(payload, tmp_path)
    assert row["args_summary"] == "/code/foo.py"


def test_grep_logs_pattern(tmp_path):
    payload = {"tool_name": "Grep", "tool_input": {"pattern": "TODO", "path": "/code"}}
    row = run_telemetry(payload, tmp_path)
    assert row["args_summary"] == "TODO"


def test_grep_redacts_secret_pattern(tmp_path):
    payload = {"tool_name": "Grep", "tool_input": {"pattern": "API_KEY=sk-foo", "path": "/code"}}
    row = run_telemetry(payload, tmp_path)
    assert row["args_summary"] == "<redacted-secret-pattern>"


def test_glob_logs_pattern(tmp_path):
    payload = {"tool_name": "Glob", "tool_input": {"pattern": "**/*.py", "path": "/code"}}
    row = run_telemetry(payload, tmp_path)
    assert row["args_summary"] == "**/*.py"


def test_webfetch_logs_host_only_strips_query(tmp_path):
    payload = {"tool_name": "WebFetch", "tool_input": {"url": "https://api.example.com/users?token=abc123&q=foo"}}
    row = run_telemetry(payload, tmp_path)
    assert row["args_summary"] == "api.example.com"
    assert "abc123" not in json.dumps(row)


def test_task_logs_subagent_type_only(tmp_path):
    payload = {
        "tool_name": "Task",
        "tool_input": {"subagent_type": "Explore", "prompt": "secret prompt content"},
    }
    row = run_telemetry(payload, tmp_path)
    assert row["args_summary"] == "Explore"
    assert "secret prompt" not in json.dumps(row)


def test_todowrite_logs_count_only(tmp_path):
    payload = {
        "tool_name": "TodoWrite",
        "tool_input": {"todos": [{"content": "secret"}, {"content": "stuff"}, {"content": "here"}]},
    }
    row = run_telemetry(payload, tmp_path)
    assert row["args_summary"] == "3 todos"
    assert "secret" not in json.dumps(row)


def test_unknown_tool_logs_name_and_ts_only(tmp_path):
    payload = {"tool_name": "SomeMcpTool", "tool_input": {"anything": "goes here"}}
    row = run_telemetry(payload, tmp_path)
    assert row["tool"] == "SomeMcpTool"
    assert "args_summary" not in row or row["args_summary"] == ""


def test_malformed_json_does_not_crash(tmp_path):
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input="not valid json",
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0  # silent-fail: never break Claude Code


def test_creates_parent_directory_if_missing(tmp_path):
    # tmp_path has no .claude/ subdir initially
    payload = {"tool_name": "Bash", "tool_input": {"command": "ls"}, "tool_response": {"exit_code": 0}}
    row = run_telemetry(payload, tmp_path)
    assert row is not None
    log_path = tmp_path / ".claude" / "self-improving-claude" / "telemetry.jsonl"
    assert log_path.exists()


def test_appends_not_overwrites(tmp_path):
    payload1 = {"tool_name": "Bash", "tool_input": {"command": "first"}, "tool_response": {"exit_code": 0}}
    payload2 = {"tool_name": "Bash", "tool_input": {"command": "second"}, "tool_response": {"exit_code": 0}}
    run_telemetry(payload1, tmp_path)
    run_telemetry(payload2, tmp_path)
    log_path = tmp_path / ".claude" / "self-improving-claude" / "telemetry.jsonl"
    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["args_summary"] == "first"
    assert json.loads(lines[1])["args_summary"] == "second"


def test_missing_project_dir_silent_fail(tmp_path):
    """If CLAUDE_PROJECT_DIR is unset, telemetry should silently no-op."""
    env = os.environ.copy()
    env.pop("CLAUDE_PROJECT_DIR", None)
    payload = {"tool_name": "Bash", "tool_input": {"command": "ls"}, "tool_response": {"exit_code": 0}}
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
```

- [ ] **Step 2: Verify the tests fail (telemetry.py doesn't exist yet)**

```bash
python3 -m pytest scripts/tests/test_telemetry.py -v
```
Expected: all tests fail with `FileNotFoundError` or similar (the script doesn't exist yet).

- [ ] **Step 3: Implement scripts/telemetry.py**

Create `scripts/telemetry.py`:

```python
#!/usr/bin/env python3
"""self-improving-claude — passive telemetry hook (PostToolUse: "*").

Reads a hook event from stdin, applies summarization rules from spec §3.4,
appends one JSONL row to ${CLAUDE_PROJECT_DIR}/.claude/self-improving-claude/telemetry.jsonl.

Silent-fail by design: any unexpected error must NOT block Claude Code's
tool execution. Always exits 0.

Stdlib only. Do not introduce dependencies — this ships to user machines.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


SECRET_PATTERN_RE = re.compile(
    r"(API_KEY|SECRET|PASSWORD|TOKEN|BEARER|PRIVATE_KEY|AWS_|SK_)",
    re.IGNORECASE,
)


def summarize(event: dict) -> dict:
    """Convert a raw hook event into a JSONL row honoring spec §3.4 redaction rules."""
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    tool_response = event.get("tool_response") or {}

    row: dict = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool": tool,
    }

    if tool == "Bash":
        cmd = (tool_input.get("command") or "")[:80]
        row["args_summary"] = cmd
        exit_code = tool_response.get("exit_code", 0)
        outcome: dict = {"exit_code": exit_code}
        if exit_code != 0:
            stderr = (tool_response.get("stderr") or "")[:200]
            outcome["stderr_head"] = stderr
        row["outcome"] = outcome

    elif tool in ("Read", "Write", "Edit", "MultiEdit"):
        row["args_summary"] = tool_input.get("file_path", "")

    elif tool in ("Glob", "Grep"):
        pattern = tool_input.get("pattern", "") or ""
        if SECRET_PATTERN_RE.search(pattern):
            row["args_summary"] = "<redacted-secret-pattern>"
        else:
            row["args_summary"] = pattern

    elif tool == "WebFetch":
        url = tool_input.get("url", "") or ""
        try:
            row["args_summary"] = urlparse(url).hostname or ""
        except Exception:
            row["args_summary"] = ""

    elif tool == "Task":
        row["args_summary"] = tool_input.get("subagent_type", "")

    elif tool == "TodoWrite":
        todos = tool_input.get("todos") or []
        row["args_summary"] = f"{len(todos)} todos"

    # Unknown tools (incl. MCP) → name + ts only.

    return row


def main() -> int:
    try:
        raw = sys.stdin.read()
        if not raw:
            return 0
        event = json.loads(raw)
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        if not project_dir:
            return 0
        log_path = Path(project_dir) / ".claude" / "self-improving-claude" / "telemetry.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        row = summarize(event)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    except Exception:
        # Never break Claude Code's tool execution. Swallow everything.
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests and verify they all pass**

```bash
python3 -m pytest scripts/tests/test_telemetry.py -v
```
Expected: all 18 tests pass.

If any test fails, fix `scripts/telemetry.py` against that test's expectation before moving on. Do not skip or weaken the test.

- [ ] **Step 5: Commit**

```bash
git add scripts/telemetry.py scripts/tests/__init__.py scripts/tests/test_telemetry.py
git commit -m "Add telemetry script with per-tool redaction rules and tests"
```

---

## Task 4: Reference docs — hook patterns + tools reference

**Files:**
- Create: `skills/self-improving-claude/references/hook-patterns.md`
- Create: `skills/self-improving-claude/references/tools-reference.md`

**Purpose:** Two of the five distilled reference docs that the orchestrator skill `@`-mentions. These are runtime grounding for the LLM when drafting hooks. They are **distilled** versions of the knowledge files — trimmed to "what the model needs at run time," not the full design rationale. Source material lives in `docs/knowledge/hooks-and-sdk.md` and `docs/knowledge/tools-reference.md`.

- [ ] **Step 1: Create the hook-patterns reference**

Create `skills/self-improving-claude/references/hook-patterns.md`:

```markdown
# Hook Patterns (runtime reference)

The patterns you need at draft time. For the full rationale, see the project's `docs/knowledge/hooks-and-sdk.md`.

## Hook events at a glance

| Event | Fires when | Can block? | Supports `type: prompt`? |
|---|---|---|---|
| PreToolUse | Before a tool runs | Yes (exit 2 / `permissionDecision: deny`) | Yes |
| PostToolUse | After a tool ran | No, but stderr is fed back to Claude | No |
| UserPromptSubmit | User submits a prompt | Yes (block before model sees it) | Yes |
| Stop | Main agent considers stopping | Yes (force continue) | Yes |
| SubagentStop | Subagent considers stopping | Yes | Yes |
| SessionStart | New session begins | No | No |
| SessionEnd | Session ends | No | No |
| PreCompact | Before context compaction | No | No |
| Notification | A notification is sent | No | No |

## Where to write hook entries

`.claude/settings.json` (committed, team-shared) — default.
`.claude/settings.local.json` (not committed, personal) — when the rule is one developer's preference.
Never `~/.claude/settings.json` without an explicit user-confirmed reason — that's a different scope.

## The two hook types

**Prompt-based** (`"type": "prompt"`) — the LLM evaluates each invocation. Best for reasoning-heavy checks. Available only on PreToolUse, Stop, SubagentStop, UserPromptSubmit. Costs a model call per fire.

```json
{
  "type": "prompt",
  "prompt": "Evaluate if this Bash command is safe. Deny if it would push to main, force-push anywhere, or rm -rf outside the project. Otherwise allow.",
  "timeout": 30
}
```

**Command** (`"type": "command"`) — a shell command (typically Python or bash) runs. Best for fast deterministic checks. Available on every event. No model call.

```json
{
  "type": "command",
  "command": "python3 ${CLAUDE_PROJECT_DIR}/.claude/hooks/block-rm-outside-cwd.py",
  "timeout": 10
}
```

## When to prefer which (priority order)

1. `permissions.deny` rule — for uniform path/glob-based blocks across all tools (cheapest, fastest).
2. Prompt hook — when the check needs context and the event supports it.
3. Command hook — when the check is fast and deterministic, or the event doesn't support prompt hooks (most `PostToolUse` formatters/linters fall here).
4. `CLAUDE.md` note — when the rule is taste-level, not safety-level (offer as a `#`-line for the user to paste; don't write `CLAUDE.md` directly).

## Settings-file structure (where to merge)

```json
{
  "permissions": { "deny": ["Read(**/.env)"] },
  "hooks": {
    "PreToolUse":  [ { "matcher": "Bash", "hooks": [ /* ... */ ] } ],
    "PostToolUse": [ { "matcher": "Write|Edit", "hooks": [ /* ... */ ] } ]
  }
}
```

Hook entries within an event array each carry a `matcher` (tool name, `|`-separated alternation, or `*`) and a `hooks: []` list of executors.

## Hook event stdin (PreToolUse / PostToolUse common shape)

```json
{
  "session_id": "uuid",
  "cwd": "/abs/path",
  "permission_mode": "ask|allow",
  "hook_event_name": "PreToolUse" | "PostToolUse",
  "tool_name": "Bash",
  "tool_input": { /* tool-specific, see tools-reference.md */ },
  "tool_response": { /* PostToolUse only */ }
}
```

## Exit codes (command hooks)

- `0` — let the tool proceed; stdout shown in transcript.
- `2` — block (PreToolUse) or feed-stderr-back-to-Claude (PostToolUse). Whatever you wrote to stderr becomes Claude's explanation.
- Anything else — non-blocking error.

## Portable paths

- `${CLAUDE_PLUGIN_ROOT}` — the plugin's install directory. Use this for scripts shipped *by* the plugin (e.g. our telemetry hook).
- `${CLAUDE_PROJECT_DIR}` — the user's project root. Use this for scripts you write *into* a project (e.g. generated `.claude/hooks/*.py`).

## Generated hook conventions (what we write)

Every command-hook script we generate begins with the stdin-reading boilerplate from `tools-reference.md`. Generated scripts target one event, ≤ 60 LOC, carry the `"name": "self-improving-claude/<slug>"` sentinel in their settings.json entry.

## Restart caveat

Hooks load at session start. A hook we install during `/improve-init` only fires after the user restarts Claude Code. Always tell the user this in the close-out message.
```

- [ ] **Step 2: Create the tools-reference**

Create `skills/self-improving-claude/references/tools-reference.md`:

```markdown
# Tools Reference (runtime lookup)

What `tool_input` and `tool_response` look like per built-in tool. Generated hooks need this to branch correctly. For the full discussion of why, see `docs/knowledge/tools-reference.md`.

## Standard stdin envelope

```json
{
  "session_id": "uuid",
  "transcript_path": "/abs/path",
  "cwd": "/abs/path",
  "permission_mode": "ask|allow",
  "hook_event_name": "PreToolUse|PostToolUse|...",
  "tool_name": "<see table>",
  "tool_input":    { /* varies */ },
  "tool_response": { /* PostToolUse only, varies */ }
}
```

## Python boilerplate (use as the head of every generated command hook)

```python
import json, sys

def main():
    try:
        ev = json.load(sys.stdin)
    except Exception:
        return 0  # never break Claude Code on bad input

    tool  = ev.get("tool_name", "")
    inp   = ev.get("tool_input")    or {}
    resp  = ev.get("tool_response") or {}

    # branch on `tool`; inspect `inp` / `resp`
    # block: print to stderr and return 2
    # allow: return 0

    return 0

if __name__ == "__main__":
    sys.exit(main())
```

## Per-tool `tool_input` (with matcher)

| Tool | Matcher | `tool_input` keys |
|---|---|---|
| `Read` | `Read` | `file_path` (abs) |
| `Write` | `Write` | `file_path` (abs), `content` |
| `Edit` | `Edit` | `file_path`, `old_string`, `new_string`, `replace_all` |
| `MultiEdit` | `MultiEdit` | `file_path`, `edits` (array of `{old_string, new_string}`) |
| `Glob` | `Glob` | `pattern`, `path` (search root, a directory) |
| `Grep` | `Grep` | `pattern` (regex), `path`, `glob`, `output_mode` |
| `Bash` | `Bash` | `command`, `description`, `timeout`, `run_in_background` |
| `WebFetch` | `WebFetch` | `url`, `prompt` |
| `WebSearch` | `WebSearch` | `query` |
| `Task` | `Task` | `subagent_type`, `description`, `prompt` |
| `TodoWrite` | `TodoWrite` | `todos` (array of `{content, status, id}`) |
| `NotebookEdit` | `NotebookEdit` | notebook-specific cell edits (rare) |

## Per-tool `tool_response` (PostToolUse only, highlights)

| Tool | `tool_response` shape |
|---|---|
| `Bash` | `{ stdout, stderr, exit_code, interrupted }` — `exit_code` is the gold for telemetry |
| `Read` | file content (often with metadata) |
| `Write` / `Edit` | confirmation of write |
| `Glob` / `Grep` | matches / counts |
| `TodoWrite` | `{ oldTodos, newTodos }` |
| `Task` | subagent's final response |

When generating PostToolUse hooks, look up the response shape here; in unfamiliar cases use defensive lookups (`resp.get("exit_code", 0)`).

## Most-likely matchers we'll generate

| Matcher | Why |
|---|---|
| `Bash` | Block dangerous shell commands; gate destructive ops |
| `Read` | Block reads of secrets / sensitive paths (often beaten by `permissions.deny`) |
| `Write\|Edit\|MultiEdit` | Post-write formatter, type-check, convention enforcement |
| `Edit\|MultiEdit` | Stricter post-edit checks (e.g. import-validity) |
| `*` | Telemetry, blanket logging — we already ship this one; rarely need to generate another |

## Matcher syntax

- Exact: `"Bash"`
- Alternation: `"Read|Write|Edit"`
- Wildcard: `"*"`
- Regex: `"mcp__.*"` — matches all MCP tools (case-sensitive)

## Bash inspection — common hostile patterns

When drafting a Bash-targeting hook, check for these in `tool_input.command`:

- `rm -rf` outside `${CLAUDE_PROJECT_DIR}`
- `git push --force` or `git push -f` (especially to `main`/`master`)
- Pipes to `sh` / `bash` from `curl` / `wget`
- `eval` of unvetted input
- Project-specific anti-patterns surfaced in `<recent_chat>` or `<telemetry_excerpt>`
```

- [ ] **Step 3: Verify the files are well-formed Markdown (no broken code fences)**

```bash
# Both files should print non-empty content and have balanced ``` fences:
for f in skills/self-improving-claude/references/hook-patterns.md \
         skills/self-improving-claude/references/tools-reference.md; do
  echo "--- $f"
  fences=$(grep -c '^```' "$f")
  echo "fence count: $fences (must be even)"
  test $((fences % 2)) -eq 0 || echo "UNBALANCED FENCES IN $f"
done
```
Expected: each file reports an even fence count.

- [ ] **Step 4: Commit**

```bash
git add skills/self-improving-claude/references/hook-patterns.md \
        skills/self-improving-claude/references/tools-reference.md
git commit -m "Add distilled hook-patterns and tools-reference for the orchestrator"
```

---

## Task 5: Reference doc — settings merge algorithm

**Files:**
- Create: `skills/self-improving-claude/references/settings-merge.md`

**Purpose:** The settings.json merge algorithm in spec §6 written as an instructional reference the orchestrator follows at runtime. Distinct from the other reference docs — this is the algorithm the model must execute step-by-step, not background knowledge.

- [ ] **Step 1: Create the settings-merge reference**

Create `skills/self-improving-claude/references/settings-merge.md`:

```markdown
# settings.json Merge Algorithm (runtime contract)

This is the procedure to follow when writing approved hooks/permissions into `.claude/settings.json`. Deviating from it risks clobbering user-authored config — which is the worst thing this skill can do.

## The hard rules

- **Never overwrite the whole file.** Always read → merge → write.
- **Never overwrite an existing array.** Append to it.
- **If the file won't parse, stop.** Tell the user, do not write anything.
- **Mark everything you add.** Each entry you create carries `"name": "self-improving-claude/<descriptive-slug>"`. JSON doesn't have comments; this is how user (and future-you) finds plugin-added entries to edit or remove.

## Algorithm

1. **Read.** `Read .claude/settings.json` (or `.claude/settings.local.json` if the user picked personal scope). If the file does not exist, treat its content as `{}`.

2. **Parse.** Validate as JSON. If parsing fails, surface the error to the user with the file path and the parser message, and abort. Do not attempt a "best-effort" write.

3. **Plan the merge** — at key level:
   - `hooks.<EventName>` (e.g. `hooks.PreToolUse`) — **append** new entries to the array. Each entry is a `{matcher, hooks: [{name, type, command|prompt, timeout?}]}` object. Do not replace existing entries with the same matcher unless conflict-resolution has been done in Step 4.
   - `permissions.deny` (or `.allow` / `.ask`) — **append** the rule string if it is not already present (string-equality dedupe).
   - Every other top-level key (`env`, `model`, `statusLine`, etc.) — **leave untouched**.

4. **Conflict detection** (run before persisting any entry):
   - For each new hook entry under `hooks.<Event>`, check whether the existing array already contains an entry whose `matcher` overlaps. Overlap = exact match, or one is a substring of the other in an alternation, or one is `*`.
   - On overlap, surface the conflict via `AskUserQuestion` with these options (in order):
     - **Keep both** (recommended for most cases): append the new entry alongside the existing one. Two hooks for the same matcher run in parallel — this is fine if both are independent.
     - **Replace existing**: remove the existing entry and write the new one. Mark this option as destructive in its description. Replacing destroys user-authored config; warrant explicit consent.
     - **Skip**: drop the new entry, do not write it.
   - Apply the user's choice; only then proceed to Step 5.

5. **Write.** Serialize the merged object with `json.dumps(..., indent=2, sort_keys=False)` (or the equivalent — preserve key order). Stable 2-space indent so user-side `git diff` is readable. Write atomically: write to `settings.json.tmp`, then rename over the original.

6. **Verify.** Re-read the file and parse it. If parsing fails (shouldn't, but be safe), restore the pre-write content from a snapshot taken in Step 1 and surface the error.

## What plugin-added entries look like

A hook entry we add:

```json
{
  "matcher": "Bash",
  "hooks": [
    {
      "name": "self-improving-claude/block-pnpm-test-watcher",
      "type": "command",
      "command": "python3 ${CLAUDE_PROJECT_DIR}/.claude/hooks/block-pnpm-test-watcher.py",
      "timeout": 5
    }
  ]
}
```

A `permissions.deny` rule we add carries no marker (the rule string itself is descriptive enough; we dedupe on it). If the user wants to remove plugin-added deny rules, they can grep their file for entries we mentioned in the close-out message.

## Where to write

- **Default:** `.claude/settings.json` (committed, team-shared). Most rules are valuable for the team.
- **Personal scope:** `.claude/settings.local.json` (not committed). Offer this via `AskUserQuestion` when the rule is obviously developer-specific (depends on local paths, single dev's preferences, machine-specific tools).
- **Never** write to `~/.claude/settings.json` (global) without an explicit user-confirmed reason — that's a different scope entirely.

## Slug rules for the `name` field

`self-improving-claude/<descriptive-kebab-slug>` where the slug:

- describes what the hook does, not what it blocks (positive framing)
- uses lowercase letters, digits, hyphens
- ≤ 50 chars
- is unique within the file (if a collision arises, suffix `-2`, `-3`, etc.)

Good: `block-pnpm-test-watcher`, `format-on-write-python`, `gate-git-force-push`.
Bad: `hook-1`, `MyHook`, `block-things`.
```

- [ ] **Step 2: Verify file is well-formed**

```bash
f=skills/self-improving-claude/references/settings-merge.md
fences=$(grep -c '^```' "$f")
echo "fence count: $fences"
test $((fences % 2)) -eq 0 && echo OK || echo "UNBALANCED FENCES"
```
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add skills/self-improving-claude/references/settings-merge.md
git commit -m "Add settings.json merge algorithm reference"
```

---

## Task 6: Reference docs — rubric + examples

**Files:**
- Create: `skills/self-improving-claude/references/prompt-rubric.md`
- Create: `skills/self-improving-claude/references/examples.md`

**Purpose:** The rubric is the contract every proposal must satisfy before being shown to the user. Examples are the three worked exemplars the model imitates. Both are load-bearing for proposal quality.

- [ ] **Step 1: Create the rubric**

Create `skills/self-improving-claude/references/prompt-rubric.md`:

```markdown
# Hook Proposal Rubric

Every proposal you draft must satisfy every item below before you show it to the user. If a draft fails, revise (up to 2 retries); if it still fails, drop the candidate and note one-line why.

## Mandatory criteria

1. **Grounded in observed behavior.** The proposal points to a specific event in `<recent_chat>` / `<telemetry_excerpt>` / `<project_snapshot>` — not a hypothetical. If you can't quote the evidence in one sentence, the candidate isn't strong enough.

2. **Lightest viable form.** You chose the form (permissions.deny → prompt-hook → command-hook → CLAUDE.md note) by ruling out lighter options. The rationale states *why* a lighter form wouldn't work, if you didn't use one.

3. **One event, one matcher.** The hook binds to exactly one event (`PreToolUse`, `PostToolUse`, etc.) with a precise `matcher` (exact tool, an alternation that's tighter than `*`, or — only when truly universal — `*`).

4. **Small.** Command-hook scripts are ≤ 60 lines. `permissions.deny` is a single rule string. Prompt-hook prompts are ≤ 5 sentences. If you can't fit, the candidate is doing too much — split it into two.

5. **Sentinel name.** Every settings.json entry you create carries `"name": "self-improving-claude/<descriptive-kebab-slug>"`. See `settings-merge.md` for slug rules.

6. **Portable paths.** Scripts use `${CLAUDE_PROJECT_DIR}` (project-side) or `${CLAUDE_PLUGIN_ROOT}` (plugin-side). No absolute paths. No `~`. No relative paths that depend on cwd.

7. **One-sentence rationale.** A single sentence that names the bug AND why this form (not a lighter one) was correct. Goes in front of the user as part of the approval prompt.

8. **Boilerplate at the head.** Command-hook scripts (Python preferred, then bash, then JS) start with the stdin → JSON → branch boilerplate from `tools-reference.md`. Even short scripts — matchers can widen later.

9. **Defensive lookups.** Scripts use `.get(...)`-style access for `tool_input` / `tool_response` fields. They tolerate missing keys silently and never crash on unexpected payload shapes.

10. **Validated syntax.** Before you show it: `bash -n` for shell, `python -m py_compile` for Python, `node --check` for JS, `json.loads` for permission rules / settings entries. A draft that doesn't parse never reaches the user.

## Disqualifiers (drop the candidate immediately)

- The rule duplicates an existing entry (verified against `<existing_hooks>` / `<existing_permissions>`).
- The rule contradicts `CLAUDE.md`.
- The rule encodes a personal preference the user hasn't expressed.
- The rule depends on machine-specific state (a developer's home directory, a particular shell, a specific Node version).
- The rule needs network access to evaluate (we avoid hooks that call out to external services in v0.1).

## Anti-patterns (revise, don't drop)

- Vague rationale ("this is a good idea") → tighten to one specific bug.
- Matcher too broad (`"*"` when `"Bash"` would do) → narrow it.
- Logic in the matcher that belongs in the script (regex with bash-specific shape) → simplify.
- `print()` debug noise in the script → remove.
- Hard-coded paths that should be env-vars → fix.
```

- [ ] **Step 2: Create the examples**

Create `skills/self-improving-claude/references/examples.md`:

```markdown
# Worked Examples

Three exemplars of approved proposals. They demonstrate the lightest-viable-form principle, the rationale style, and the boilerplate.

After each one, the **Why it's good** line names the property the model should imitate.

---

## Example 1 — `permissions.deny` (when a glob suffices)

### Observed problem

> The user said "stop reading my `.env` files," and the chat shows three recent `Read` calls against `.env`, `.env.local`, `.env.production`.

### Proposal

**Form:** `permissions.deny` rule
**Event:** N/A (permissions apply uniformly across tools)
**Settings.json delta:**

```json
{
  "permissions": {
    "deny": [
      "Read(**/.env)",
      "Read(**/.env.*)"
    ]
  }
}
```

**Rationale:** *Blocks reads of `.env` and `.env.*` across all tools (Read, Grep, Glob, etc.) with a single rule — cheaper than per-tool hooks and uniformly enforced.*

### Why it's good

The proposal *ruled out the lighter form first* (there is none — `permissions.deny` is already lightest), picked the most surgical pattern (two specific globs, not `**/*.env*` which over-matches), and the rationale explicitly says why this beats a `PreToolUse` hook.

---

## Example 2 — Command hook (when the check is deterministic)

### Observed problem

> Telemetry shows `pnpm test` invocations exit non-zero 5 times this week, and the project's `package.json` defines `test:ci` (non-interactive) as the correct script. The bare `pnpm test` opens an interactive watcher.

### Proposal

**Form:** Command hook (`"type": "command"`)
**Event:** `PreToolUse`
**Matcher:** `Bash`
**Script:** `.claude/hooks/block-pnpm-test-watcher.py`

```python
#!/usr/bin/env python3
"""Block `pnpm test` (interactive watcher); steer Claude to `pnpm test:ci`."""
import json, sys

def main():
    try:
        ev = json.load(sys.stdin)
    except Exception:
        return 0
    if ev.get("tool_name") != "Bash":
        return 0
    cmd = (ev.get("tool_input") or {}).get("command", "")
    if cmd.strip().startswith("pnpm test") and "test:ci" not in cmd:
        print("Use `pnpm test:ci` instead — `pnpm test` opens an interactive watcher and won't return.", file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

**Settings.json delta:**

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "name": "self-improving-claude/block-pnpm-test-watcher",
            "type": "command",
            "command": "python3 ${CLAUDE_PROJECT_DIR}/.claude/hooks/block-pnpm-test-watcher.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

**Rationale:** *Blocks the recurring `pnpm test` watcher trap by inspecting the Bash command before it runs and pointing Claude at `pnpm test:ci`; a `permissions.deny` rule would also block the correct `pnpm test:ci` because it has the same prefix.*

### Why it's good

The proposal *had to use a hook* because `permissions.deny` can't distinguish `pnpm test` from `pnpm test:ci` (same prefix). The script branches on `tool_name`, uses defensive `.get(...)`, exits 2 with a useful stderr message, stays well under 60 LOC, carries the sentinel `name`, uses `${CLAUDE_PROJECT_DIR}`.

---

## Example 3 — Prompt hook (when reasoning is needed)

### Observed problem

> The user noted "Claude keeps trying to git-push from inside the agent — I want a human in the loop." The check needs context (which branch, force or not, into which remote) that's hard to express deterministically.

### Proposal

**Form:** Prompt hook (`"type": "prompt"`)
**Event:** `PreToolUse`
**Matcher:** `Bash`
**Settings.json delta:**

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "name": "self-improving-claude/gate-git-push",
            "type": "prompt",
            "prompt": "Evaluate this Bash command. If it is a `git push` (or `git push --force`, `git push -f`), respond with `deny` and explain that pushes require human confirmation. If it is not a git push, respond with `allow`.",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

**Rationale:** *Gates all `git push` invocations behind LLM evaluation that can read intent (e.g. recognize `git push origin feature-x` vs `git push --force origin main`) without trying to anticipate every shape with regex; a deterministic script could miss novel invocation forms.*

### Why it's good

The proposal *picked prompt-hook over command-hook* because the check genuinely needs reasoning about `git push` invocation shape (origin name, branch, force flag combinations). Stays focused: one event, one matcher, prompt under 5 sentences. Sentinel name present. The rationale names the bug and explicitly says why a regex would be brittle.
```

- [ ] **Step 3: Verify both files**

```bash
for f in skills/self-improving-claude/references/prompt-rubric.md \
         skills/self-improving-claude/references/examples.md; do
  fences=$(grep -c '^```' "$f")
  echo "$f → fences=$fences"
  test $((fences % 2)) -eq 0 || echo "UNBALANCED FENCES IN $f"
done
```
Expected: each file's fence count is even.

- [ ] **Step 4: Commit**

```bash
git add skills/self-improving-claude/references/prompt-rubric.md \
        skills/self-improving-claude/references/examples.md
git commit -m "Add rubric and three worked examples for the orchestrator"
```

---

## Task 7: Orchestrator skill (`self-improving-claude/SKILL.md`)

**Files:**
- Create: `skills/self-improving-claude/SKILL.md`

**Purpose:** The model-invoked orchestrator that both user-invoked entry skills hand off to. Its body is the procedure from spec §8 — the 10-step workflow with embedded judgment moments. It `@`-references the five files created in Tasks 4–6.

This skill is what does the actual work of `/improve-init`. Task 8 (the user-invoked entry skill) is a thin wrapper that primes it with the right mode and invokes it.

- [ ] **Step 1: Create the orchestrator skill**

Create `skills/self-improving-claude/SKILL.md`:

```markdown
---
name: self-improving-claude
description: Use when invoked by the /improve or /improve-init user-invoked skills. Orchestrates the proposal → approval → install workflow that turns observed Claude Code behavior into installed per-project guardrails (hooks, permissions.deny rules, or CLAUDE.md notes).
version: 0.1.0
---

# self-improving-claude — Orchestrator

You are the orchestrator behind `/improve` and `/improve-init`. Your job is to convert observed Claude Code behavior into installed, per-project guardrails with explicit user approval at every step.

## Inputs (set by the calling skill)

<mode>{reactive|proactive}</mode>
<user_directive>{$ARGUMENTS or empty}</user_directive>
<recent_chat>{last N messages — reactive mode only}</recent_chat>
<project_snapshot>{CLAUDE.md, package.json, README, sampled source — proactive mode only}</project_snapshot>
<telemetry_excerpt>{relevant rows from .claude/self-improving-claude/telemetry.jsonl — proactive primary, reactive supplemental}</telemetry_excerpt>
<existing_hooks>{current contents of .claude/settings.json `hooks` block}</existing_hooks>
<existing_permissions>{current contents of .claude/settings.json `permissions` block}</existing_permissions>

## Grounding

<rubric>
@references/prompt-rubric.md
</rubric>

<hook_reference>
@references/hook-patterns.md
@references/tools-reference.md
@references/settings-merge.md
</hook_reference>

<examples>
@references/examples.md
</examples>

## How to operate

You are operating as a workflow with a few agentic moments. The shape of the work is fixed — inspect, propose, get approval, persist, close out — but within each step, exercise judgment. The rubric in `<rubric>` and the references under `<hook_reference>` are how you check your own work; trust them to flag bad proposals rather than hand-checking every box.

### When to ask the user vs. when to decide

Use the `AskUserQuestion` tool any time a judgment call genuinely affects the user's project and you can't read it confidently from context. Don't ask reflexively — burning the user's attention on every micro-decision defeats the point. But do ask when:

- their directive is ambiguous enough that two reasonable readings would produce different proposals
- you're about to drop a candidate they might have wanted
- you've drafted a hook that's borderline on the rubric and the user's intent would settle whether it's worth shipping
- a proposed matcher conflicts with an existing entry and the right resolution depends on what they value (keep both / replace / skip)
- the user could reasonably want this rule personal (`settings.local.json`) vs. team-shared (`settings.json`)

Frame questions as 2–4 options with one-line descriptions of each, ranked with your recommended option first. Reserve "Other" for things you genuinely hadn't thought of — `AskUserQuestion` adds that option automatically.

## Step 1 — Read the room

Read `<user_directive>` and decide what kind of request you're handling. The three shapes that matter are:

- **default (empty)** → propose proactively from the available signals.
- **directive** ("add a rule that prevents X") → propose specifically against X.
- **feedback** ("the foo-hook blocked something legit") → refine an existing entry rather than adding new ones.

If the directive sits genuinely between two of these (e.g. could be a directive OR a feedback note about an existing hook), use `AskUserQuestion` to clarify before going further. Otherwise, classify and continue.

## Step 2 — Inspect before drafting

Generated guardrails that collide with existing config are the single biggest failure mode here. Before you propose anything, get a feel for what already exists: the current `.claude/settings.json`, what hooks already live under `.claude/hooks/`, what the telemetry log shows about recent tool behavior, what `CLAUDE.md` already establishes.

You don't need to dump these into the chat — read them, hold them, and use them to filter proposals later. If `settings.json` won't parse, stop and tell the user; do not write to a file you can't read cleanly.

## Step 3 — Find candidate problems worth fixing

Look at `<recent_chat>` (reactive) or `<project_snapshot>` + `<telemetry_excerpt>` (proactive) and identify problems that are genuinely observable — actual behavior, not "Claude might one day…" hypotheticals. Strong candidates have clear evidence (a chat message, a telemetry row, a project convention) and aren't already addressed by what you found in Step 2.

Cap yourself at ~5 candidates per run. If you see more, surface the best ones and mention the rest as deferred so the user can re-run.

## Step 4 — Choose the lightest form that does the job

For each candidate, decide what shape the guardrail should take. The options, roughly from lightest to heaviest:

- `permissions.deny` rule — when a glob can express the rule uniformly
- prompt-based hook (`"type": "prompt"`) — when the check needs reasoning AND the event supports prompt hooks (PreToolUse, Stop, SubagentStop, UserPromptSubmit)
- command hook (`"type": "command"`) — when the check is fast and deterministic, or when the event doesn't support prompt hooks (PostToolUse, SessionStart, etc.)
- a soft note that the user pastes into `CLAUDE.md` themselves — when the rule is taste-level, not safety-level

Prefer the lighter form when both would work. Lighter means cheaper to run, easier to audit, less code to maintain. But don't strain to make a glob fit a rule that genuinely needs logic — the priority is a guide, not an algorithm.

If you're genuinely on the fence between two forms for the same candidate (typically `permissions.deny` vs. a prompt hook), use `AskUserQuestion` to let the user pick — they know whether they'd rather have a stricter broad rule or a smarter narrow one.

## Step 5 — Draft against the rubric

The rubric in `<rubric>` is the contract for what makes a proposal shippable. The proposal must:

- target a specific observed behavior, not a hypothetical
- bind to one event with a precise matcher
- be small (≤ 60 LOC for scripts; one line for permissions rules)
- carry a `"name": "self-improving-claude/<slug>"` sentinel for later findability
- use portable paths (`${CLAUDE_PROJECT_DIR}` for project hooks, `${CLAUDE_PLUGIN_ROOT}` for plugin-shipped scripts)
- come with a one-sentence rationale that names the bug AND why this form (not the lighter one in Step 4) was the right call

Command-hook scripts should start with the stdin → JSON → branch boilerplate from `@references/tools-reference.md` — even short scripts, because matchers can widen later and the boilerplate keeps them robust.

## Step 6 — Self-critique, then revise (cap retries at 2)

Reread your draft against the rubric with fresh eyes. If anything is off, revise. If after two revision passes the proposal still doesn't satisfy the rubric, drop the candidate and note why — the bar is "I'd ship this into someone's project," not "this is what came out of my first draft."

Edge case: if a candidate is *almost* there and you suspect the user would still want it, use `AskUserQuestion` to surface the trade-off rather than dropping it silently.

## Step 7 — Validate syntax before showing the user

Run the obvious checks for the form you produced — `bash -n`, `python -m py_compile`, `node --check`, JSON parse, glob shape. A draft that doesn't pass these never reaches the user. Better silently dropped than visibly broken.

## Step 8 — Walk the user through approvals, one at a time

For each surviving candidate, the user needs to see enough to make an informed yes/no:

- what bug it's preventing (your one-sentence rationale)
- the actual code or rule being proposed
- how it merges with what's already in `settings.json`
- which event and matcher it binds to, in plain English

Then collect their decision via `AskUserQuestion` with options: approve / reject / edit. If they pick edit, accept their changes, re-validate (Step 7), re-show the merged view, and ask again.

If a proposed matcher overlaps with something the user already has, surface the conflict via `AskUserQuestion` with three sub-choices: keep both, replace the existing entry, or skip. Flag "replace" as destructive in its description — replacing destroys user-authored config and warrants a confirm.

By default, write team-shared rules to `.claude/settings.json`. If a proposal is obviously personal (depends on a single dev's preferences or local paths), ask via `AskUserQuestion` whether the user wants `settings.json` (shared) or `settings.local.json` (personal).

## Step 9 — Write what was approved

Persist each approved candidate per `@references/settings-merge.md`:

- command-hook scripts go to `.claude/hooks/<slug>.{sh|py|js}` — Python is the safest default unless the script obviously needs shell or Node
- hook entries merge into `.claude/settings.json` by event-array append (key-level merge), never array overwrite
- `permissions.deny` rules append to the deny array, deduped by string equality
- `CLAUDE.md` notes you do NOT write yourself — output the exact `# ...` line the user can paste, and let them choose the scope

After writing, re-read `settings.json` to confirm it still parses. If something broke, restore the pre-write content and surface the error.

## Step 10 — Close out cleanly

End with a short summary the user can read at a glance: what got installed, what got dropped (and why, in one line each), what got deferred for a future run. Then remind them how to activate the hooks — hooks load at session start, so they need to restart (`exit`, then `claude`) and then ESC-ESC-rewind in the fresh session to clean up this conversation's detour.

Tell them how to give feedback if a hook misfires later: `/improve "the <name> hook blocked something legit"`.
```

- [ ] **Step 2: Verify the skill file has valid frontmatter and balanced fences**

```bash
f=skills/self-improving-claude/SKILL.md
head -5 "$f"
echo "---"
fences=$(grep -c '^```' "$f")
echo "fence count: $fences (must be even)"
test $((fences % 2)) -eq 0 && echo OK || echo "UNBALANCED FENCES"
```
Expected: frontmatter shows `name: self-improving-claude` and `version: 0.1.0`; fence count is even and `OK`.

- [ ] **Step 3: Verify the @-references resolve to real files**

```bash
for ref in references/prompt-rubric.md references/hook-patterns.md \
           references/tools-reference.md references/settings-merge.md \
           references/examples.md; do
  test -f "skills/self-improving-claude/$ref" && echo "OK: $ref" || echo "MISSING: $ref"
done
```
Expected: five `OK:` lines.

- [ ] **Step 4: Commit**

```bash
git add skills/self-improving-claude/SKILL.md
git commit -m "Add orchestrator skill — 10-step workflow with AskUserQuestion-driven approvals"
```

---

## Task 8: `/improve-init` user-invoked skill

**Files:**
- Create: `skills/improve-init/SKILL.md`

**Purpose:** The thin wrapper that the user types as `/improve-init`. It prepares the inputs the orchestrator expects (mode=proactive, project snapshot, telemetry excerpt, existing hooks/permissions), then invokes the orchestrator skill. Frontmatter sets it up as a user-invoked slash command per the plugin manifest reference.

- [ ] **Step 1: Create the improve-init slash command**

Create `skills/improve-init/SKILL.md`:

```markdown
---
name: improve-init
description: Run /improve-init to do a first-time or periodic proactive scan of this project for guardrail opportunities. Reads project code, recent session transcripts, and the bundled telemetry log to propose hooks / permissions.deny rules / CLAUDE.md notes — with per-proposal user approval.
argument-hint: [optional scope hint in quotes, e.g. "focus on the queries directory"]
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, Skill, AskUserQuestion]
---

# /improve-init — Proactive Guardrail Scan

Hand off to the `self-improving-claude` orchestrator with `mode=proactive`. You — the calling skill — are responsible for gathering the inputs below, then invoking the orchestrator (via the `Skill` tool with `skill: "self-improving-claude"`) so it can run its 10-step workflow.

## Step 1 — Gather inputs

Collect each of these before invoking the orchestrator. Skip silently any that aren't available; don't fail the run.

**`<user_directive>`** — the literal contents of `$ARGUMENTS`, or empty string.

**`<project_snapshot>`** — a sampled, *trimmed* view of the project:
- `CLAUDE.md` if it exists (read whole, paste excerpt or summary if very long)
- `package.json` / `pyproject.toml` / `Cargo.toml` / similar manifest if present
- `README.md` (first 80 lines)
- A handful of representative source files (let your judgment pick — prefer files named in `CLAUDE.md` or telemetry, otherwise pick representative ones via `Glob` + `Read`)

Cap total size around 5–8 KB. Excerpt, don't paste whole files when they're large.

**`<telemetry_excerpt>`** — the most recent ~200 rows from `.claude/self-improving-claude/telemetry.jsonl` if it exists. If the file is missing or empty, pass empty and note that the user hasn't accumulated telemetry yet — the orchestrator should mention this in close-out.

**`<existing_hooks>`** — the `hooks` block from `.claude/settings.json` (parse and serialize the relevant slice; empty `{}` if file missing).

**`<existing_permissions>`** — the `permissions` block from `.claude/settings.json` (empty `{}` if file missing).

If `.claude/settings.json` won't parse, stop here and tell the user — do not invoke the orchestrator with broken state.

## Step 2 — Hand off to the orchestrator

Invoke the `self-improving-claude` skill, passing the inputs you gathered. The orchestrator owns everything from there: it does its inspection (Step 1–2), proposes (Step 3–5), self-critiques (Step 6), validates (Step 7), walks the user through approvals (Step 8), writes approved files (Step 9), and closes out (Step 10).

You — the entry skill — do not run those steps yourself. You just gather inputs and call.

## Mode is fixed for this command

`<mode>proactive</mode>` always. The orchestrator uses this to know it should weight `<project_snapshot>` + `<telemetry_excerpt>` over `<recent_chat>` (which will be empty for this command).
```

- [ ] **Step 2: Verify the skill file is well-formed**

```bash
f=skills/improve-init/SKILL.md
head -6 "$f"
echo "---"
fences=$(grep -c '^```' "$f")
echo "fence count: $fences"
test $((fences % 2)) -eq 0 && echo OK || echo "UNBALANCED FENCES"
```
Expected: frontmatter shows `name: improve-init` and `allowed-tools: [..., Skill, AskUserQuestion]`; even fence count; `OK`.

- [ ] **Step 3: Commit**

```bash
git add skills/improve-init/SKILL.md
git commit -m "Add /improve-init entry skill — gathers inputs, hands off to orchestrator"
```

---

## Task 9: Update README + manual smoke test

**Files:**
- Modify: `README.md`

**Purpose:** Bring the README from "design captured" to "v0.1 install + run instructions." After the README is current, perform the manual smoke test that is the v0.1 acceptance criterion (spec §13): install, run `/improve-init` on 2–3 real projects, verify at least one approved hook fires after restart.

This is the last task. Once it's done, v0.1 is shipped.

- [ ] **Step 1: Update the README**

Replace the entire contents of `README.md` with:

```markdown
# self-improving-claude

> A Claude Code plugin that turns the bugs you just saw into the hooks that prevent the next ones.

**Status:** v0.1.0 — `/improve-init` (proactive scan) works end-to-end. `/improve` (reactive) is v0.2.

---

## What it does

You're working in Claude Code. Claude does something you don't want again — runs the wrong test command, edits a file it shouldn't, forgets a migration step. You type `/improve-init`. The plugin reviews your project, your past session transcripts, and a bundled telemetry log, then proposes a set of guardrails (hooks, `permissions.deny` rules, or `CLAUDE.md` notes) with **per-proposal explicit approval**. Approved guardrails are written into your project's `.claude/` directory. Restart Claude Code and they take effect.

It's a Claude Code add-on that makes Claude Code measurably better at *your* project, the moment you notice it isn't.

## Install (local, from this repo)

1. Clone or download this repo to a stable location, e.g. `~/code/self-improving-claude`.
2. Symlink (or copy) it into Claude Code's plugins directory:

   ```bash
   ln -s ~/code/self-improving-claude ~/.claude/plugins/cache/self-improving-claude
   ```

   The exact path may differ slightly on your machine — the rule is that the plugin needs to live somewhere Claude Code scans for plugins. Check `~/.claude/plugins/` to find the cache root used on your install.

3. Restart Claude Code (`exit`, then `claude`). On the next session start, the bundled telemetry hook is registered and the `/improve-init` command is available.

## Usage

### `/improve-init`

Run inside any project you'd like to harden. The plugin will:

1. Read your project's `CLAUDE.md`, manifest files, and a sampled set of source files.
2. Read recent past-session transcripts and the bundled telemetry log (if present).
3. Identify up to 5 candidate guardrails.
4. For each candidate, propose the lightest viable form (`permissions.deny` rule, prompt-based hook, command hook, or `CLAUDE.md` note).
5. Walk you through them one at a time — you approve, reject, or edit each.
6. Write approved files to your project's `.claude/hooks/` and merge entries into `.claude/settings.json`.
7. Tell you to restart Claude Code so the new hooks load.

Optional scoped invocation:

```
/improve-init "focus on the queries directory"
```

### Telemetry hook

The plugin installs one always-on hook — `PostToolUse: "*"` — that logs summarized tool usage to `.claude/self-improving-claude/telemetry.jsonl` inside each project where Claude Code is active. Logged fields per call:

```jsonl
{"ts": "2026-05-22T14:33:01Z", "tool": "Bash", "args_summary": "pnpm test", "outcome": {"exit_code": 1, "stderr_head": "ENOENT..."}}
```

**Redaction is strict** (tested in `scripts/tests/test_telemetry.py`):

- File `Read`/`Write`/`Edit` log only the path, never content.
- `Bash` logs the first 80 chars of the command and (only on non-zero exit) the first 200 chars of stderr.
- `Grep`/`Glob` redact patterns that match known secret prefixes (`API_KEY`, `SECRET`, `TOKEN`, etc.).
- `WebFetch` logs only the URL host — never query strings.
- `Task`/`TodoWrite` log type/counts only — never the prompt or todo content.

The script silently no-ops on any unexpected error — it must never break Claude Code's tool execution.

If you want to disable telemetry entirely, remove the `PostToolUse` entry whose `name` is `self-improving-claude/telemetry` from your `.claude/settings.json` (or just don't enable the plugin).

## What's installed where

| Location | What |
|---|---|
| Plugin directory (read-only) | `.claude-plugin/plugin.json`, skills, bundled telemetry script. Plugin updates touch only this. |
| Your project's `.claude/hooks/` | Generated hook scripts (you own these). |
| Your project's `.claude/settings.json` | Plugin-added entries carry `"name": "self-improving-claude/<slug>"` so you can find/edit/remove them. |
| Your project's `.claude/self-improving-claude/telemetry.jsonl` | The redacted telemetry log. |

## Roadmap

- **v0.1** (current) — `/improve-init` proactive scan, per-proposal approval, bundled telemetry hook.
- **v0.2** — `/improve` reactive mode (uses current chat as primary input); `evals/` harness with code + model graders; generated hooks default to `"type": "prompt"` where the event supports it.
- **v0.3+** — feedback channel (`/improve "the foo-hook blocked something legit"`), formal conflict UX, more eval entries.

## Design docs

- `docs/superpowers/specs/2026-05-22-self-improving-claude-design.md` — full design spec.
- `docs/knowledge/` — distilled Claude Code course material grounding the design.
- `docs/superpowers/plans/2026-05-22-self-improving-claude-v0.1.md` — the implementation plan for this version.

## License

MIT. See `LICENSE`.
```

- [ ] **Step 2: Commit the README update**

```bash
git add README.md
git commit -m "Update README with v0.1 install + usage instructions"
```

- [ ] **Step 3: Run all tests one last time and confirm clean state**

```bash
python3 -m pytest scripts/tests/ -v
python3 -c "import json; json.load(open('.claude-plugin/plugin.json'))" && echo "plugin.json OK"
python3 -c "import json; json.load(open('hooks/hooks.json'))" && echo "hooks.json OK"
```
Expected: 18 tests pass; both OK messages.

- [ ] **Step 4: Manual smoke test — install the plugin**

Install the plugin into Claude Code's plugin directory. The exact command depends on your Claude Code install; the simplest portable path is a symlink:

```bash
# Adjust path if your cache root differs
mkdir -p ~/.claude/plugins/cache 2>/dev/null
ln -s "$(pwd)" ~/.claude/plugins/cache/self-improving-claude
```

Then restart Claude Code (`exit`, then `claude`). Verify the plugin is loaded by running `/help` inside a session — `improve-init` should appear in the slash-command list.

If `/improve-init` does not appear, check `claude --debug` output for plugin registration errors and fix any plugin.json / SKILL.md / hooks.json problem surfaced there before continuing.

- [ ] **Step 5: Manual smoke test — first project**

Pick a small real project you actively use (Node, Python, or generic shell — try the simplest one first).

1. `cd` into the project. Open Claude Code there.
2. Do 2–3 minutes of *any* normal work — let the telemetry hook accumulate a few rows.
3. Confirm `.claude/self-improving-claude/telemetry.jsonl` exists and looks reasonable (redacted, JSONL, one row per tool call).
4. Run `/improve-init`.
5. Verify the orchestrator:
   - reads `CLAUDE.md` if you have one
   - reads the telemetry log
   - proposes 1–5 candidates
   - walks you through approvals via `AskUserQuestion`-style prompts
6. Approve one or two proposals.
7. Verify the close-out message tells you to restart.
8. Restart Claude Code. Trigger the condition the hook should catch. Confirm it fires.

If any step fails, capture what went wrong and fix it in the relevant skill / reference / script before moving on. Update the spec or plan if the fix changes a design decision.

- [ ] **Step 6: Manual smoke test — second and third projects**

Repeat Step 5 on two more projects of meaningfully different shape (e.g. a Python repo and a generic shell-script repo if your first was Node). The point is to confirm the orchestrator's proposals are sensible across stacks, not Node-biased.

For each project:
- At least one proposed hook is sensible enough to approve.
- After approve + restart, the approved hook fires when its trigger condition is met.

- [ ] **Step 7: Final commit**

If you fixed anything during the smoke test that's already covered by existing files (without changing the public interface), commit those fixes:

```bash
git status
# review changes, then:
git add <files>
git commit -m "Fix issues found during v0.1 smoke test"
```

If no changes were needed, no final commit is required.

- [ ] **Step 8: Tag v0.1.0**

```bash
git tag -a v0.1.0 -m "v0.1.0 — first working release"
git log --oneline -1
```

v0.1.0 is shipped. The plugin can be installed locally and `/improve-init` produces sensible, approvable, installable guardrails on real projects.
