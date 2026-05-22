"""Unit tests for evals/client_ollama.py.

Mocks urllib.request.urlopen so tests don't need a running Ollama daemon.
"""
import io
import json
from unittest.mock import patch

import pytest

from evals.client_ollama import OllamaClient


def _fake_urlopen_factory(response_content: str):
    """Build a fake urlopen that returns a JSON response body."""
    body = json.dumps({"message": {"content": response_content}, "done": True}).encode("utf-8")

    class _FakeResp:
        def __init__(self):
            self._body = io.BytesIO(body)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return self._body.read()

    def _fake(req, timeout=None):
        return _FakeResp()

    return _fake


def test_create_returns_anthropic_shape():
    client = OllamaClient(model="gemma4:e4b")
    with patch("evals.client_ollama.urllib.request.urlopen",
               new=_fake_urlopen_factory("hello world")):
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",  # caller's request — should be ignored
            max_tokens=256,
            messages=[{"role": "user", "content": "say hi"}],
        )
    assert len(resp.content) == 1
    assert resp.content[0].type == "text"
    assert resp.content[0].text == "hello world"


def test_create_includes_system_prompt():
    """If system is passed, it becomes the first message with role=system."""
    captured: dict = {}

    def _capture(req, timeout=None):
        captured["body"] = json.loads(req.data)

        class _R:
            def __enter__(self): return self
            def __exit__(self, *exc): return False
            def read(self): return b'{"message":{"content":"ok"},"done":true}'
        return _R()

    client = OllamaClient(model="gemma4:e4b")
    with patch("evals.client_ollama.urllib.request.urlopen", new=_capture):
        client.messages.create(
            model="x", max_tokens=100,
            system="You are a grader.",
            messages=[{"role": "user", "content": "review this"}],
        )

    msgs = captured["body"]["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == "You are a grader."
    assert msgs[1]["role"] == "user"


def test_create_uses_configured_model_not_caller_model():
    """We ignore the model kwarg from callers (Anthropic names) and use our local model."""
    captured: dict = {}

    def _capture(req, timeout=None):
        captured["body"] = json.loads(req.data)

        class _R:
            def __enter__(self): return self
            def __exit__(self, *exc): return False
            def read(self): return b'{"message":{"content":"ok"},"done":true}'
        return _R()

    client = OllamaClient(model="gemma4:e4b")
    with patch("evals.client_ollama.urllib.request.urlopen", new=_capture):
        client.messages.create(
            model="claude-haiku-4-5-20251001",  # caller asks for Haiku
            max_tokens=100,
            messages=[{"role": "user", "content": "x"}],
        )
    assert captured["body"]["model"] == "gemma4:e4b"


def test_create_passes_max_tokens_as_num_predict():
    captured: dict = {}

    def _capture(req, timeout=None):
        captured["body"] = json.loads(req.data)

        class _R:
            def __enter__(self): return self
            def __exit__(self, *exc): return False
            def read(self): return b'{"message":{"content":"ok"},"done":true}'
        return _R()

    client = OllamaClient(model="gemma4:e4b")
    with patch("evals.client_ollama.urllib.request.urlopen", new=_capture):
        client.messages.create(model="x", max_tokens=2048,
                               messages=[{"role": "user", "content": "x"}])
    assert captured["body"]["options"]["num_predict"] == 2048


def test_create_raises_runtime_error_when_daemon_unreachable():
    import urllib.error

    def _refuse(req, timeout=None):
        raise urllib.error.URLError("Connection refused")

    client = OllamaClient(model="gemma4:e4b")
    with patch("evals.client_ollama.urllib.request.urlopen", new=_refuse):
        with pytest.raises(RuntimeError) as ei:
            client.messages.create(model="x", max_tokens=100,
                                   messages=[{"role": "user", "content": "x"}])
    assert "daemon running" in str(ei.value).lower() or "ollama" in str(ei.value).lower()
