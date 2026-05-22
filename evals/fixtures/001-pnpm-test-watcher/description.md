# Planted problem — pnpm test watcher trap

Claude has been invoking `pnpm test` directly in this project. The project's
package.json defines `pnpm test` as the interactive Vitest watcher (which
never exits), while `pnpm test:ci` is the non-interactive CI runner Claude
should actually be using.

Telemetry shows 3 recent `pnpm test` invocations that exited with non-zero
codes (Claude killed them after timeout). CLAUDE.md does not currently flag
this.

An ideal proposal blocks `pnpm test` via a PreToolUse Bash hook and steers
Claude to `pnpm test:ci`. A `permissions.deny` rule does NOT fit because
the rule string `Bash(pnpm test)` would also block `pnpm test:ci` (same
prefix).
