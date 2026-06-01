# Planted problem — Claude confuses the linter with the formatter and names the wrong tool

The project's CLAUDE.md specifies `ruff format` as the formatter. Telemetry shows Claude running `ruff check` (the linter) after edits and calling that "formatting." The user wants a PostToolUse hook that runs `ruff format` on modified Python files — and the rationale must say "ruff format," not "ruff check" or "lint."

`ruff check` finds style violations; `ruff format` rewrites the file. They are different commands with different effects. A hook that runs `ruff check` and calls it a formatter is both functionally wrong and incorrectly described in its rationale.

Expected proposal: form=`command-hook`, event=`PostToolUse`, matcher=`Write|Edit|MultiEdit`, rationale mentions `ruff format`.
