# Knowledge Base

Drop reference material here that should inform how `self-improving-claude` reasons about hooks.

Intended sources for the first pass:

- **Anthropic *Claude Code* course** — what hooks exist, how `settings.json` works, idiomatic skill/plugin patterns, examples of well-designed guardrails.
- **Claude Code official docs** — the canonical reference for hook events, slash commands, plugin structure.
- **Real examples from the wild** — community plugins, useful hook patterns, anti-patterns to avoid.

## Current contents

| File | What's in it |
|---|---|
| `hooks-and-sdk.md` | Everything about hooks (PreToolUse, PostToolUse, and the other 7 hook types), how to write them, exit-code semantics, the `$PWD` absolute-path pattern, worked examples, and an overview of the Claude Agent SDK with package install + minimal example. Ends with implications for `self-improving-claude`. |
| `slash-commands-and-claude-md.md` | How custom slash commands work (`.claude/commands/<name>.md`, `$ARGUMENTS`), and how `CLAUDE.md` provides persistent project memory, including `@file` mentions. Ends with implications for our design. |

## What to add next (when relevant)

- Official Claude Code docs links (canonical reference URLs)
- Real-world example plugins from the community
- Anti-patterns / pitfalls observed in the wild
- Patterns specific to our domain (e.g. testing hook-generation, sandboxing freeform scripts)

This material will eventually be distilled into the reference doc that ships *inside* the plugin and grounds the LLM when it drafts hooks.
