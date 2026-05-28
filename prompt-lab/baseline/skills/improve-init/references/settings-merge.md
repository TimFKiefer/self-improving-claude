# settings.json Merge Algorithm (runtime contract)

This is the procedure to follow when writing approved hooks/permissions into `.claude/settings.json`. Deviating from it risks clobbering user-authored config — which is the worst thing this skill can do.

## The hard rules

- **Never overwrite the whole file.** Always read → merge → write.
- **Never overwrite an existing array.** Append to it.
- **If the file won't parse, stop.** Tell the user, do not write anything.
- **Mark everything you add.** Each entry you create carries `"name": "self-improving-claude/<descriptive-slug>"`. JSON doesn't have comments; this is how user (and future-you) finds plugin-added entries to edit or remove.

## Algorithm

1. **Read.** `Read .claude/settings.json` (or `.claude/settings.local.json` if the user picked personal scope). If the file does not exist, treat its content as `{}`.

2. **Parse.** Validate as JSON. If parsing fails, surface the error to the user with the file path and the parser message, and abort. Do not attempt a "best-effort" write.

3. **Plan the merge** — at key level:
   - `hooks.<EventName>` (e.g. `hooks.PreToolUse`) — **append** new entries to the array. Each entry is a `{matcher, hooks: [{name, type, command|prompt, timeout?}]}` object. Do not replace existing entries with the same matcher unless conflict-resolution has been done in Step 4.
   - `permissions.deny` (or `.allow` / `.ask`) — **append** the rule string if it is not already present (string-equality dedupe).
   - Every other top-level key (`env`, `model`, `statusLine`, etc.) — **leave untouched**.

4. **Conflict detection** (run before persisting any entry):
   - For each new hook entry under `hooks.<Event>`, check whether the existing array already contains an entry whose `matcher` overlaps. Overlap = exact match, or one is a substring of the other in an alternation, or one is `*`.
   - On overlap, surface the conflict via `AskUserQuestion` with these options (in order):
     - **Keep both** (recommended for most cases): append the new entry alongside the existing one. Two hooks for the same matcher run in parallel — this is fine if both are independent.
     - **Replace existing**: remove the existing entry and write the new one. Mark this option as destructive in its description. Replacing destroys user-authored config; warrant explicit consent.
     - **Skip**: drop the new entry, do not write it.
   - Apply the user's choice; only then proceed to Step 5.

5. **Write.** Serialize the merged object with `json.dumps(..., indent=2, sort_keys=False)` (or the equivalent — preserve key order). Stable 2-space indent so user-side `git diff` is readable. Write atomically: write to `settings.json.tmp`, then rename over the original.

6. **Verify.** Re-read the file and parse it. If parsing fails (shouldn't, but be safe), restore the pre-write content from a snapshot taken in Step 1 and surface the error.

## What plugin-added entries look like

A hook entry we add:

```json
{
  "matcher": "Bash",
  "hooks": [
    {
      "name": "self-improving-claude/block-pnpm-test-watcher",
      "type": "command",
      "command": "python3 ${CLAUDE_PROJECT_DIR}/.claude/hooks/block-pnpm-test-watcher.py",
      "timeout": 5
    }
  ]
}
```

A `permissions.deny` rule we add carries no marker (the rule string itself is descriptive enough; we dedupe on it). If the user wants to remove plugin-added deny rules, they can grep their file for entries we mentioned in the close-out message.

## Where to write

- **Default:** `.claude/settings.json` (committed, team-shared). Most rules are valuable for the team.
- **Personal scope:** `.claude/settings.local.json` (not committed). Offer this via `AskUserQuestion` when the rule is obviously developer-specific (depends on local paths, single dev's preferences, machine-specific tools).
- **Never** write to `~/.claude/settings.json` (global) without an explicit user-confirmed reason — that's a different scope entirely.

## Slug rules for the `name` field

`self-improving-claude/<descriptive-kebab-slug>` where the slug:

- describes what the hook does, not what it blocks (positive framing)
- uses lowercase letters, digits, hyphens
- ≤ 50 chars
- is unique within the file (if a collision arises, suffix `-2`, `-3`, etc.)

Good: `block-pnpm-test-watcher`, `format-on-write-python`, `gate-git-force-push`.
Bad: `hook-1`, `MyHook`, `block-things`.

---

## Feedback log schema

The orchestrator writes user-reported hook misfires to `${CLAUDE_PROJECT_DIR}/.claude/self-improving-claude/feedback.jsonl`. One JSON object per line:

```jsonl
{"ts":"2026-05-23T15:30:01Z","target":"self-improving-claude/block-pnpm-test-watcher","mode":"too-broad","complaint":"blocked legitimate `pnpm test --filter foo` command","resolution":"narrowed matcher from Bash to Bash(pnpm test) with --filter exception"}
```

Required fields:
- `ts` — ISO-8601 UTC timestamp of the feedback event
- `target` — sentinel `name` (`self-improving-claude/<slug>`) of the hook complained about
- `mode` ∈ `{too-broad, false-positive, please-narrow, missed-case}`
- `complaint` — user's verbatim feedback text (trim very long inputs to ~500 chars)
- `resolution` — one-sentence description of what the orchestrator changed in response

`/improve-init` reads feedback.jsonl on subsequent runs and applies extra scrutiny when proposing similar hooks: if a recent feedback row mentions a hook whose pattern resembles a new proposal, flag the new proposal for explicit user confirmation rather than auto-accepting on the rubric alone.
