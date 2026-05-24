"""Claude CLI client that mimics the anthropic.Anthropic interface.

Wraps `claude --print --model <X>` (OAuth subscription) so the eval harness
can run against Haiku/Sonnet/Opus with NO ANTHROPIC_API_KEY — auth is the
user's Claude Code subscription. Same `.messages.create(**kwargs)` shape as
the Anthropic SDK and OllamaClient, so grade_model / run_one_entry stay
backend-agnostic.

Default model: `haiku`. Override via CLAUDE_CLI_MODEL env var.
"""
from __future__ import annotations

import json
import os
import subprocess
from types import SimpleNamespace

DEFAULT_MODEL = os.environ.get("CLAUDE_CLI_MODEL", "haiku")
DEFAULT_TIMEOUT = float(os.environ.get("CLAUDE_CLI_TIMEOUT", "600"))


class ClaudeCliClient:
    """Drop-in for `anthropic.Anthropic` using the `claude --print` CLI."""

    def __init__(self, model: str = DEFAULT_MODEL, timeout: float = DEFAULT_TIMEOUT):
        self.cli_model = model
        self.timeout = timeout
        # mirror anthropic.Anthropic's surface: client.messages.create(**kwargs)
        self.messages = SimpleNamespace(create=self._create)

    def _build_prompt(self, system: str | None, messages: list) -> str:
        parts: list[str] = []
        if system:
            parts.append(system)
            parts.append("")
        for msg in messages:
            content = msg["content"]
            if not isinstance(content, str):
                content = json.dumps(content)
            parts.append(content)
        return "\n\n".join(parts)

    def _create(self, *, model: str, max_tokens: int, messages: list,
                system: str | None = None, **_ignored):
        """Issue one completion via `claude --print`. The Anthropic `model`
        kwarg (a cloud model name) is ignored; the CLI model is fixed at
        construction. `max_tokens` has no CLI equivalent and is ignored."""
        prompt = self._build_prompt(system, messages)
        try:
            result = subprocess.run(
                [
                    "claude", "--print",
                    "--model", self.cli_model,
                    "--disable-slash-commands",
                    "--no-session-persistence",
                    "--exclude-dynamic-system-prompt-sections",
                    prompt,
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except FileNotFoundError as e:
            raise RuntimeError(
                "`claude` CLI not found on PATH — is Claude Code installed?"
            ) from e
        if result.returncode != 0:
            raise RuntimeError(
                f"`claude --print` failed (rc={result.returncode}): "
                f"{result.stderr[:500]}"
            )
        # Anthropic SDK shape: response.content is a list of blocks with .type/.text.
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=result.stdout)]
        )
