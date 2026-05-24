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
        "hook_event_name": "PostToolUse",
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
    payload = {"hook_event_name": "PostToolUse",
        "tool_name": "Bash", "tool_input": {"command": long_cmd}, "tool_response": {"exit_code": 0}}
    row = run_telemetry(payload, tmp_path)
    assert len(row["args_summary"]) <= 80


def test_bash_truncates_stderr_to_200_chars(tmp_path):
    long_err = "x" * 1000
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "false"},
        "tool_response": {"exit_code": 1, "stderr": long_err},
    }
    row = run_telemetry(payload, tmp_path)
    assert len(row["outcome"]["stderr_head"]) <= 200


def test_bash_omits_stderr_on_success(tmp_path):
    payload = {
        "hook_event_name": "PostToolUse",
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
        "hook_event_name": "PostToolUse",
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
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "/code/foo.py", "content": "PASSWORD=hunter2"},
    }
    row = run_telemetry(payload, tmp_path)
    assert row["args_summary"] == "/code/foo.py"
    assert "hunter2" not in json.dumps(row)


def test_edit_logs_path_only(tmp_path):
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": "/code/foo.py", "old_string": "x", "new_string": "y"},
    }
    row = run_telemetry(payload, tmp_path)
    assert row["args_summary"] == "/code/foo.py"


def test_grep_logs_pattern(tmp_path):
    payload = {"hook_event_name": "PostToolUse",
        "tool_name": "Grep", "tool_input": {"pattern": "TODO", "path": "/code"}}
    row = run_telemetry(payload, tmp_path)
    assert row["args_summary"] == "TODO"


def test_grep_redacts_secret_pattern(tmp_path):
    payload = {"hook_event_name": "PostToolUse",
        "tool_name": "Grep", "tool_input": {"pattern": "API_KEY=sk-foo", "path": "/code"}}
    row = run_telemetry(payload, tmp_path)
    assert row["args_summary"] == "<redacted-secret-pattern>"


def test_glob_logs_pattern(tmp_path):
    payload = {"hook_event_name": "PostToolUse",
        "tool_name": "Glob", "tool_input": {"pattern": "**/*.py", "path": "/code"}}
    row = run_telemetry(payload, tmp_path)
    assert row["args_summary"] == "**/*.py"


def test_webfetch_logs_host_only_strips_query(tmp_path):
    payload = {"hook_event_name": "PostToolUse",
        "tool_name": "WebFetch", "tool_input": {"url": "https://api.example.com/users?token=abc123&q=foo"}}
    row = run_telemetry(payload, tmp_path)
    assert row["args_summary"] == "api.example.com"
    assert "abc123" not in json.dumps(row)


def test_task_logs_subagent_type_only(tmp_path):
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Task",
        "tool_input": {"subagent_type": "Explore", "prompt": "secret prompt content"},
    }
    row = run_telemetry(payload, tmp_path)
    assert row["args_summary"] == "Explore"
    assert "secret prompt" not in json.dumps(row)


def test_todowrite_logs_count_only(tmp_path):
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "TodoWrite",
        "tool_input": {"todos": [{"content": "secret"}, {"content": "stuff"}, {"content": "here"}]},
    }
    row = run_telemetry(payload, tmp_path)
    assert row["args_summary"] == "3 todos"
    assert "secret" not in json.dumps(row)


def test_unknown_tool_logs_name_and_ts_only(tmp_path):
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "SomeMcpTool",
        "tool_input": {"anything": "goes here"},
    }
    row = run_telemetry(payload, tmp_path)
    assert row["tool"] == "SomeMcpTool"
    assert row["event"] == "tool"
    assert "args_summary" not in row


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
    payload = {"hook_event_name": "PostToolUse",
        "tool_name": "Bash", "tool_input": {"command": "ls"}, "tool_response": {"exit_code": 0}}
    row = run_telemetry(payload, tmp_path)
    assert row is not None
    log_path = tmp_path / ".claude" / "self-improving-claude" / "telemetry.jsonl"
    assert log_path.exists()


def test_appends_not_overwrites(tmp_path):
    payload1 = {"hook_event_name": "PostToolUse",
        "tool_name": "Bash", "tool_input": {"command": "first"}, "tool_response": {"exit_code": 0}}
    payload2 = {"hook_event_name": "PostToolUse",
        "tool_name": "Bash", "tool_input": {"command": "second"}, "tool_response": {"exit_code": 0}}
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
    payload = {"hook_event_name": "PostToolUse",
        "tool_name": "Bash", "tool_input": {"command": "ls"}, "tool_response": {"exit_code": 0}}
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0


def test_empty_stdin_does_not_write(tmp_path):
    """Empty stdin (e.g. a hook event with no body) must not crash and must not write."""
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input="",
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    log_path = tmp_path / ".claude" / "self-improving-claude" / "telemetry.jsonl"
    assert not log_path.exists()


def test_multiedit_logs_path_only(tmp_path):
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "MultiEdit",
        "tool_input": {"file_path": "/code/foo.py", "edits": [{"old_string": "x", "new_string": "y"}]},
    }
    row = run_telemetry(payload, tmp_path)
    assert row["args_summary"] == "/code/foo.py"


def test_grep_redacts_token_pattern(tmp_path):
    payload = {"hook_event_name": "PostToolUse",
        "tool_name": "Grep", "tool_input": {"pattern": "TOKEN=abc123", "path": "/code"}}
    row = run_telemetry(payload, tmp_path)
    assert row["args_summary"] == "<redacted-secret-pattern>"


def test_grep_does_not_redact_substring_match(tmp_path):
    """Word-boundary anchoring means `access_token` (no \\b before `token`) is not redacted."""
    payload = {"hook_event_name": "PostToolUse",
        "tool_name": "Grep", "tool_input": {"pattern": "access_token", "path": "/code"}}
    row = run_telemetry(payload, tmp_path)
    assert row["args_summary"] == "access_token"  # not redacted


def test_notification_event_logged(tmp_path):
    payload = {
        "hook_event_name": "Notification",
        "session_id": "abc",
        "cwd": str(tmp_path),
    }
    row = run_telemetry(payload, tmp_path)
    assert row["event"] == "notification"
    assert "ts" in row


def test_precompact_event_logged(tmp_path):
    payload = {
        "hook_event_name": "PreCompact",
        "session_id": "abc",
        "cwd": str(tmp_path),
    }
    row = run_telemetry(payload, tmp_path)
    assert row["event"] == "compact"
    assert "ts" in row


def test_sessionstart_event_logged(tmp_path):
    payload = {
        "hook_event_name": "SessionStart",
        "session_id": "abc",
        "cwd": str(tmp_path),
    }
    row = run_telemetry(payload, tmp_path)
    assert row["event"] == "session_start"
    assert "ts" in row


def test_existing_posttooluse_event_still_tagged(tmp_path):
    """Existing PostToolUse payloads should now carry event='tool' field too."""
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
        "tool_response": {"exit_code": 0},
    }
    row = run_telemetry(payload, tmp_path)
    assert row["event"] == "tool"
    assert row["tool"] == "Bash"
    assert row["args_summary"] == "ls"


def test_unknown_event_silently_ignored(tmp_path):
    """Unknown hook events should not crash, just write a minimal marker row."""
    payload = {
        "hook_event_name": "SomeFutureEvent",
        "session_id": "abc",
    }
    row = run_telemetry(payload, tmp_path)
    assert row["event"] == "other"
    assert "ts" in row


# --- discriminating fields: kind / reason / source (v0.3.3, spec 3.5) ---

def test_notification_kind_permission(tmp_path):
    payload = {"hook_event_name": "Notification",
               "message": "Claude needs your permission to use Bash"}
    row = run_telemetry(payload, tmp_path)
    assert row["event"] == "notification"
    assert row["kind"] == "waiting_for_permission"


def test_notification_kind_idle(tmp_path):
    payload = {"hook_event_name": "Notification",
               "message": "Claude is waiting for your input"}
    row = run_telemetry(payload, tmp_path)
    assert row["kind"] == "idle"


def test_notification_kind_other_when_no_message(tmp_path):
    payload = {"hook_event_name": "Notification"}
    row = run_telemetry(payload, tmp_path)
    assert row["kind"] == "other"


def test_precompact_reason_from_trigger(tmp_path):
    payload = {"hook_event_name": "PreCompact", "trigger": "auto"}
    row = run_telemetry(payload, tmp_path)
    assert row["event"] == "compact"
    assert row["reason"] == "auto"


def test_precompact_reason_empty_when_absent(tmp_path):
    payload = {"hook_event_name": "PreCompact"}
    row = run_telemetry(payload, tmp_path)
    assert row["reason"] == ""


def test_sessionstart_source_captured(tmp_path):
    payload = {"hook_event_name": "SessionStart", "source": "resume"}
    row = run_telemetry(payload, tmp_path)
    assert row["event"] == "session_start"
    assert row["source"] == "resume"
