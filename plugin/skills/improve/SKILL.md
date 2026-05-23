---
name: improve
description: Run /improve right after seeing Claude do something you don't want again — uses the current conversation as primary context to propose hooks / permissions.deny rules / CLAUDE.md notes that would have prevented it. Per-proposal user approval.
argument-hint: [optional directive or feedback in quotes, e.g. "block edits to src/migrations" or "the foo-hook blocked something legit"]
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, Skill, AskUserQuestion]
---

# /improve — Reactive Guardrail Proposal

Hand off to the `self-improving-claude` orchestrator with `mode=reactive`. You — the calling skill — gather the inputs below, then invoke the orchestrator (via the `Skill` tool with `skill: "self-improving-claude"`) so it can run its 10-step workflow.

The reactive workflow's primary signal is the **current conversation** — whatever the user saw Claude do that triggered the `/improve` invocation is already in your context window. You don't need to "fetch" the chat; you just need to tell the orchestrator to focus on the recent messages above.

## Step 1 — Gather inputs

**`<user_directive>`** — the literal contents of `$ARGUMENTS`, or empty string. Routing depends on shape:
- empty → default reactive mode (look at recent chat for the most recent observable problem)
- directive ("block edits to migrations/*") → propose specifically against the named target
- feedback ("the foo-hook just blocked something legit") → refine the named existing entry, do not propose new ones

The orchestrator handles classification in its Step 1; you don't pre-classify here.

**`<recent_chat>`** — the most recent ~30 messages of this conversation. You don't read this from a file; it's already in your context. Tell the orchestrator: "review the last ~30 messages above this point for evidence of the problem the user wants prevented." The orchestrator uses this as its primary candidate signal.

**`<project_snapshot>`** — supplemental in reactive mode. Read only if recent chat is thin or the problem clearly hinges on project-specific convention. Same content as `/improve-init` gathers (CLAUDE.md, manifest, README, sampled source). Cap ~5 KB.

**`<telemetry_excerpt>`** — supplemental. The most recent ~50 rows from `.claude/self-improving-claude/telemetry.jsonl` if present; useful when the problem is "Claude has done X repeatedly," less useful for one-off bugs.

**`<transcript_excerpt>`** — empty for reactive mode. The current chat is already the freshest signal; old transcripts add noise.

**`<existing_hooks>`** — the `hooks` block from `.claude/settings.json` (empty `{}` if file missing).

**`<existing_permissions>`** — the `permissions` block from `.claude/settings.json` (empty `{}` if file missing).

If `.claude/settings.json` won't parse, stop here and tell the user — do not invoke the orchestrator with broken state.

## Step 2 — Hand off to the orchestrator

Invoke the `self-improving-claude` skill, passing the inputs you gathered. The orchestrator owns everything from there: routing, inspection, drafting, self-critique, validation, approvals, writes, close-out.

You — the entry skill — do not run those steps yourself. You just gather inputs and call.

## Mode is fixed for this command

`<mode>reactive</mode>` always. The orchestrator uses this to know it should weight `<recent_chat>` over `<project_snapshot>` + `<telemetry_excerpt>`.
