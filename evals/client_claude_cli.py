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
DEFAULT_EFFORT = os.environ.get("CLAUDE_CLI_EFFORT") or None  # low|medium|high|xhigh|max

# Map Anthropic model IDs (what grade_model / run pass) to `claude --print` aliases.
# Unknown values pass through unchanged (a CLI alias like "opus" is already valid).
# NOTE: do NOT map "claude-sonnet-4-5" -> "sonnet". The bare `sonnet` alias resolves
# to a 1M-context variant that needs usage credits; the explicit `claude-sonnet-4-5`
# id (200k) must pass through verbatim to work on a plain subscription.
_CLI_MODEL_MAP = {
    "claude-haiku-4-5-20251001": "haiku",
    "claude-opus-4-7": "opus",
}


def _to_cli_model(model: str) -> str:
    return _CLI_MODEL_MAP.get(model, model)


class ClaudeCliClient:
    """Drop-in for `anthropic.Anthropic` using the `claude --print` CLI."""

    def __init__(self, model: str = DEFAULT_MODEL, timeout: float = DEFAULT_TIMEOUT,
                 effort: str | None = DEFAULT_EFFORT):
        self.cli_model = model
        self.timeout = timeout
        self.effort = effort  # low|medium|high|xhigh|max; appended to claude --print
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

    def _create(self, *, model: str | None = None, max_tokens: int, messages: list,
                system: str | None = None, **_ignored):
        """Issue one completion via `claude --print`. The per-call `model` (an
        Anthropic id or CLI alias) is honored and mapped to a CLI alias, falling
        back to the construction model — this lets the grader be pinned (Haiku)
        while the proposer varies. `max_tokens` has no CLI equivalent (ignored)."""
        cli_model = _to_cli_model(model) if model else self.cli_model
        prompt = self._build_prompt(system, messages)
        argv = [
            "claude", "--print",
            "--model", cli_model,
            "--disable-slash-commands",
            "--no-session-persistence",
            "--exclude-dynamic-system-prompt-sections",
        ]
        if self.effort:
            argv += ["--effort", self.effort]
        argv.append(prompt)
        try:
            result = subprocess.run(
                argv,
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
