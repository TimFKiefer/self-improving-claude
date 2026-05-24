"""Unit tests for evals/client_claude_cli.py.

Mocks subprocess.run so tests never invoke the real `claude` CLI.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from evals.client_claude_cli import ClaudeCliClient


def _fake_run_factory(stdout: str, returncode: int = 0, stderr: str = ""):
    def _fake(cmd, **kwargs):
        _fake.captured = {"cmd": cmd, "kwargs": kwargs}
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)
    return _fake


def test_create_returns_anthropic_shape():
    client = ClaudeCliClient(model="haiku")
    with patch("evals.client_claude_cli.subprocess.run",
               new=_fake_run_factory("hello world")):
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",  # mapped to a CLI alias
            max_tokens=256,
            messages=[{"role": "user", "content": "say hi"}],
        )
    assert len(resp.content) == 1
    assert resp.content[0].type == "text"
    assert resp.content[0].text == "hello world"


def test_create_respects_per_call_model():
    """v0.3.4: the per-call model is honored (mapped to a CLI alias), so the
    grader can be pinned to Haiku even when the client is built for Opus."""
    fake = _fake_run_factory("ok")
    client = ClaudeCliClient(model="opus")
    with patch("evals.client_claude_cli.subprocess.run", new=fake):
        client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=10,
                               messages=[{"role": "user", "content": "x"}])
    cmd = fake.captured["cmd"]
    assert cmd[cmd.index("--model") + 1] == "haiku"


def test_create_falls_back_to_construction_model():
    fake = _fake_run_factory("ok")
    client = ClaudeCliClient(model="sonnet")
    with patch("evals.client_claude_cli.subprocess.run", new=fake):
        client.messages.create(model=None, max_tokens=10,
                               messages=[{"role": "user", "content": "x"}])
    cmd = fake.captured["cmd"]
    assert cmd[cmd.index("--model") + 1] == "sonnet"


def test_create_prepends_system_prompt():
    fake = _fake_run_factory("ok")
    client = ClaudeCliClient(model="haiku")
    with patch("evals.client_claude_cli.subprocess.run", new=fake):
        client.messages.create(model="x", max_tokens=10, system="You are a grader.",
                               messages=[{"role": "user", "content": "review this"}])
    prompt = fake.captured["cmd"][-1]   # prompt is the last positional arg
    assert prompt.startswith("You are a grader.")
    assert "review this" in prompt


def test_create_raises_on_nonzero_exit():
    client = ClaudeCliClient(model="haiku")
    with patch("evals.client_claude_cli.subprocess.run",
               new=_fake_run_factory("", returncode=1, stderr="boom")):
        with pytest.raises(RuntimeError) as ei:
            client.messages.create(model="x", max_tokens=10,
                                   messages=[{"role": "user", "content": "x"}])
    assert "failed" in str(ei.value).lower()


def test_create_raises_when_cli_missing():
    def _missing(cmd, **kwargs):
        raise FileNotFoundError("claude")
    client = ClaudeCliClient(model="haiku")
    with patch("evals.client_claude_cli.subprocess.run", new=_missing):
        with pytest.raises(RuntimeError) as ei:
            client.messages.create(model="x", max_tokens=10,
                                   messages=[{"role": "user", "content": "x"}])
    assert "not found" in str(ei.value).lower()
