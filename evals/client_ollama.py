"""Ollama client that mimics the anthropic.Anthropic interface.

Same `.messages.create(**kwargs)` shape as the Anthropic SDK, so `grade_model`
and `run_one_entry` work with either backend via dependency injection.

Calls Ollama's native /api/chat endpoint over localhost:11434 — no auth,
no API key, runs entirely against the local model the user has pulled.

Default model: `gemma4:e4b`. Override via OLLAMA_MODEL env var.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from types import SimpleNamespace

DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")
DEFAULT_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "300"))


class OllamaClient:
    """Drop-in for `anthropic.Anthropic` using a local Ollama daemon."""

    def __init__(self, model: str = DEFAULT_MODEL, base_url: str = DEFAULT_BASE_URL,
                 timeout: float = DEFAULT_TIMEOUT):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # mirror anthropic.Anthropic's surface: client.messages.create(**kwargs)
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, *, model: str, max_tokens: int, messages: list,
                system: str | None = None, **_ignored):
        """Issue one chat completion. Always returns the configured local model;
        the `model` kwarg from callers (which uses Anthropic model names) is ignored."""
        ollama_messages: list[dict] = []
        if system:
            ollama_messages.append({"role": "system", "content": system})
        ollama_messages.extend(messages)

        body = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.2,
            },
        }

        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.load(resp)
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Ollama call failed (is the daemon running at {self.base_url}?): {e}"
            ) from e

        text = (data.get("message") or {}).get("content", "")
        # Anthropic SDK shape: response.content is a list of content blocks,
        # each with .type and .text. We always emit one text block.
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])
