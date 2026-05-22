---
name: improve-init
description: Run /improve-init to do a first-time or periodic proactive scan of this project for guardrail opportunities. Reads project code, recent session transcripts, and the bundled telemetry log to propose hooks / permissions.deny rules / CLAUDE.md notes — with per-proposal user approval.
argument-hint: [optional scope hint in quotes, e.g. "focus on the queries directory"]
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, Skill, AskUserQuestion]
---

# /improve-init — Proactive Guardrail Scan

Hand off to the `self-improving-claude` orchestrator with `mode=proactive`. You — the calling skill — are responsible for gathering the inputs below, then invoking the orchestrator (via the `Skill` tool with `skill: "self-improving-claude"`) so it can run its 10-step workflow.

## Step 1 — Gather inputs

Collect each of these before invoking the orchestrator. Skip silently any that aren't available; don't fail the run.

**`<user_directive>`** — the literal contents of `$ARGUMENTS`, or empty string.

**`<project_snapshot>`** — a sampled, *trimmed* view of the project:
- `CLAUDE.md` if it exists (read whole, paste excerpt or summary if very long)
- `package.json` / `pyproject.toml` / `Cargo.toml` / similar manifest if present
- `README.md` (first 80 lines)
- A handful of representative source files (let your judgment pick — prefer files named in `CLAUDE.md` or telemetry, otherwise pick representative ones via `Glob` + `Read`)

Cap total size around 5–8 KB. Excerpt, don't paste whole files when they're large.

**`<telemetry_excerpt>`** — the most recent ~200 rows from `.claude/self-improving-claude/telemetry.jsonl` if it exists. If the file is missing or empty, pass empty and note that the user hasn't accumulated telemetry yet — the orchestrator should mention this in close-out.

**`<transcript_excerpt>`** — past-session transcripts for this project, found at `~/.claude/projects/<project-path-with-slashes-as-dashes>/*.jsonl`. Each `.jsonl` file is one prior Claude Code session; rows include tool calls and outcomes. Use `Glob` to list available sessions, then sample ~30 behaviorally interesting rows total across the 2–3 most recent sessions (prefer non-zero exits, repeated edits to the same file, repeated tool patterns). If the directory is missing or empty, pass empty — the orchestrator handles the absent-signal case in close-out.

**`<existing_hooks>`** — the `hooks` block from `.claude/settings.json` (parse and serialize the relevant slice; empty `{}` if file missing).

**`<existing_permissions>`** — the `permissions` block from `.claude/settings.json` (empty `{}` if file missing).

If `.claude/settings.json` won't parse, stop here and tell the user — do not invoke the orchestrator with broken state.

## Step 2 — Hand off to the orchestrator

Invoke the `self-improving-claude` skill, passing the inputs you gathered. The orchestrator owns everything from there: it does its inspection (Step 1–2), proposes (Step 3–5), self-critiques (Step 6), validates (Step 7), walks the user through approvals (Step 8), writes approved files (Step 9), and closes out (Step 10).

You — the entry skill — do not run those steps yourself. You just gather inputs and call.

## Mode is fixed for this command

`<mode>proactive</mode>` always. The orchestrator uses this to know it should weight `<project_snapshot>` + `<telemetry_excerpt>` over `<recent_chat>` (which will be empty for this command).
