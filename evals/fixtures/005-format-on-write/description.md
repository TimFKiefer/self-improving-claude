# Planted problem — Python files aren't being formatted after Claude edits

The project uses `ruff format` as the formatter (per CLAUDE.md). Telemetry
shows recent Edits to `src/*.py` files with no formatting follow-up;
subsequent `pnpm lint`-equivalent (`ruff check`) runs flagged formatting
issues.

Ideal proposal: a `PostToolUse` command-hook on `Write|Edit|MultiEdit` that
runs `ruff format` on the affected file. Cannot be a prompt-hook because
PostToolUse doesn't support prompt-type. Cannot be permissions.deny — this
is a follow-up action, not a block.
