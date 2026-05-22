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
