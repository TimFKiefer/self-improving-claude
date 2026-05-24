"""Unit tests for evals/clients.py — the backend client factory."""
import pytest

from evals.clients import make_client
from evals.client_ollama import OllamaClient
from evals.client_claude_cli import ClaudeCliClient


def test_make_client_ollama_keeps_colon_in_model():
    client, model = make_client("ollama:gemma4:e4b")
    assert isinstance(client, OllamaClient)
    assert model == "gemma4:e4b"          # partition splits on the FIRST colon only


def test_make_client_claude_cli():
    client, model = make_client("claude-cli:claude-sonnet-4-5")
    assert isinstance(client, ClaudeCliClient)
    assert model == "claude-sonnet-4-5"


def test_make_client_rejects_specless_or_unknown_backend():
    with pytest.raises(ValueError):
        make_client("haiku")                # no backend prefix
    with pytest.raises(ValueError):
        make_client("openai:gpt-4")         # unknown backend
