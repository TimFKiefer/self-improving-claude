---
name: improve
description: Run /improve right after seeing Claude do something you don't want again — uses the current conversation as primary context to propose hooks / permissions.deny rules / CLAUDE.md notes that would have prevented it. Per-proposal user approval.
argument-hint: [optional directive or feedback in quotes, e.g. "block edits to src/migrations" or "the foo-hook blocked something legit"]
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, Skill, AskUserQuestion]
---

# /improve — Reactive Guardrail Proposal

You — invoked via the `/improve` slash command — are running the orchestrator workflow in REACTIVE mode. The current conversation is your primary signal — review the recent messages above for the problem the user wants prevented.

## Inputs

<mode>reactive</mode>
<user_directive>$ARGUMENTS</user_directive>

Gather these inputs before running the procedure:

- **`<recent_chat>`** — the most recent ~30 messages of this conversation (already in your context).
- **`<project_snapshot>`** — supplemental in reactive mode. Read CLAUDE.md, manifests, README, sampled source files only if recent chat is thin (≤ 5KB cap).
- **`<telemetry_excerpt>`** — supplemental. Most recent ~50 rows from `.claude/self-improving-claude/telemetry.jsonl` if it exists.
- **`<transcript_excerpt>`** — empty for reactive mode.
- **`<existing_hooks>`** — the `hooks` block from `.claude/settings.json` (empty `{}` if file missing).
- **`<existing_permissions>`** — the `permissions` block from `.claude/settings.json` (empty `{}` if file missing).

If `.claude/settings.json` won't parse, stop and tell the user — do not run the procedure with broken state.

## Procedure to follow

