---
name: improve-init
description: Run /improve-init to do a first-time or periodic proactive scan of this project for guardrail opportunities. Reads project code, recent session transcripts, and the bundled telemetry log to propose hooks / permissions.deny rules / CLAUDE.md notes — with per-proposal user approval.
argument-hint: [optional scope hint in quotes, e.g. "focus on the queries directory"]
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, Skill, AskUserQuestion]
---

# /improve-init — Proactive Guardrail Scan

You — invoked via the `/improve-init` slash command — are running the orchestrator workflow in PROACTIVE mode. Project code and accumulated telemetry are your primary signals.

## Inputs

<mode>proactive</mode>
<user_directive>$ARGUMENTS</user_directive>

Gather these inputs before running the procedure:

- **`<user_directive>`** — the literal contents of `$ARGUMENTS`, or empty string.
- **`<project_snapshot>`** — a sampled, *trimmed* view of the project: `CLAUDE.md` if it exists, manifest files (package.json / pyproject.toml / Cargo.toml), `README.md` first 80 lines, a handful of representative source files. Cap ~5-8 KB total.
- **`<telemetry_excerpt>`** — most recent ~200 rows from `.claude/self-improving-claude/telemetry.jsonl` if it exists. Empty if missing.
- **`<transcript_excerpt>`** — past-session transcripts at `~/.claude/projects/<project-path>/*.jsonl`. Sample ~30 behaviorally interesting rows.
- **`<existing_hooks>`** — the `hooks` block from `.claude/settings.json` (empty `{}` if file missing).
- **`<existing_permissions>`** — the `permissions` block from `.claude/settings.json` (empty `{}` if file missing).

If `.claude/settings.json` won't parse, stop and tell the user.

## Procedure to follow

