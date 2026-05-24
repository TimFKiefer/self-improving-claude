"""Build an eval backend client from a 'backend:model' spec.

Specs: 'ollama:gemma4:e4b', 'claude-cli:haiku', 'claude-cli:claude-sonnet-4-5',
'anthropic:claude-haiku-4-5-20251001'. Returns (client, model) where `model` is the
bare model string callers pass to client.messages.create(model=...).
"""
from __future__ import annotations


def make_client(spec: str):
    """Return (client, model) for a 'backend:model' spec. Raises ValueError on a
    malformed spec or unknown backend."""
    backend, sep, model = spec.partition(":")
    if not sep or not model:
        raise ValueError(f"client spec must be 'backend:model', got {spec!r}")
    if backend == "ollama":
        from evals.client_ollama import OllamaClient
        return OllamaClient(model=model), model
    if backend == "claude-cli":
        from evals.client_claude_cli import ClaudeCliClient
        return ClaudeCliClient(model=model), model
    if backend == "anthropic":
        from anthropic import Anthropic
        return Anthropic(), model
    raise ValueError(
        f"unknown backend {backend!r} in {spec!r} (expected ollama|claude-cli|anthropic)"
    )
