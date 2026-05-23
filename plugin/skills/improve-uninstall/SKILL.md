---
name: improve-uninstall
description: Run /improve-uninstall to cleanly remove self-improving-claude's footprint from THIS project — sentinel hooks in settings.json, generated scripts in .claude/hooks/, optionally the local telemetry log. The plugin itself stays installed; use `claude plugin uninstall self-improving-claude` for that.
argument-hint: [optional --dry-run to preview without changing files]
allowed-tools: [Read, Edit, Bash, AskUserQuestion]
---

# /improve-uninstall — Project Footprint Cleanup

You — invoked via `/improve-uninstall` — remove the plugin's footprint from THIS project. You do NOT uninstall the plugin itself; that's `claude plugin uninstall self-improving-claude`. You touch only files inside this project.

**Important:** if `$ARGUMENTS` is `--dry-run`, do NOT modify any files. Walk through Steps 1–4 read-only and present what WOULD be removed.

## Step 1 — Inspect

Read `.claude/settings.json` (in the current project's `.claude/` directory — use `${CLAUDE_PROJECT_DIR}/.claude/settings.json` or just `.claude/settings.json` relative to cwd).

If the file does not exist: nothing to clean up. Tell the user and exit.

If the file exists but fails to parse as JSON: do NOT proceed. Show the user the parse error and the file path, ask them to fix it manually first.

## Step 2 — Enumerate

From the parsed settings.json, collect:

**Plugin-installed hook entries.** Walk each `hooks.<EventName>` array. For each entry, look at its `hooks: [...]` sub-array. Collect entries whose `name` starts with `self-improving-claude/`.

**Plugin-installed permission rules.** Walk `permissions.deny`, `permissions.ask`, `permissions.allow`. These don't carry sentinels (it's just strings), so use a best-effort heuristic: collect rules that are documented in our examples (e.g. `Read(**/.env)`, `Edit(src/generated/prisma/**)`, `Bash(git push:*)`)) — but mark them as "best-effort match" in the summary, so the user can confirm or override.

**Generated hook scripts.** Walk `.claude/hooks/` directory. Collect files whose names correspond to sentinel slugs we found in the hook entries above (e.g. if there's a hook entry with `name: "self-improving-claude/block-pnpm-test-watcher"`, look for `.claude/hooks/block-pnpm-test-watcher.{py,sh,js}`).

**Telemetry artifacts.** Note `.claude/self-improving-claude/` directory existence (telemetry log, archives, feedback.jsonl).

## Step 3 — Confirm with the user

Use `AskUserQuestion` to summarize what was found and ask the user how to proceed. Frame the summary concretely:

> Found:
> - N plugin-installed hook entries in settings.json
> - M generated hook scripts in .claude/hooks/
> - K possibly-plugin-installed permission rules (best-effort match — please review)
> - Telemetry directory `.claude/self-improving-claude/` (X files, Y bytes)

Options:
- **Confirm all** — remove the hook entries, delete the scripts, also clear the telemetry directory
- **Confirm hooks only** — remove hook entries + delete scripts, KEEP the telemetry directory
- **Dry-run preview** — show the exact changes that would be made to settings.json (don't modify the file)
- **Abort** — do nothing

If the user passed `--dry-run` as $ARGUMENTS in the original invocation, treat the choice as "Dry-run preview" automatically — show what would change without writing.

## Step 4 — Remove

For **non-dry-run paths only:**

- **Hook entries:** for each plugin-installed entry, remove it from its array in settings.json. Preserve all other entries. Use the same defensive merge discipline as `@references/settings-merge.md` — read, parse, modify in-memory, write atomically (write to `.tmp`, then rename). Reparse after to confirm the write produced valid JSON; if not, restore the pre-write content.
- **Permission rules:** ONLY remove rules the user explicitly confirmed in Step 3 (don't auto-remove "best-effort match" entries without user sign-off).
- **Generated scripts:** delete `.claude/hooks/<slug>.py` (or `.sh`, `.js`) for each matched script. Use `Bash` with `rm -- <path>`.
- **Telemetry directory:** if the user chose "Confirm all", `rm -rf .claude/self-improving-claude/` (use `Bash`).

After all removals, re-read settings.json one more time. If it doesn't parse, restore from the pre-write content and tell the user something went wrong.

## Step 5 — Report

End with a short summary:
- N hook entries removed (or "would be removed" in dry-run)
- M scripts deleted (or "would be deleted")
- K permission rules removed (or 0 if user declined)
- Telemetry directory: kept / cleared / would be cleared

Then remind the user:

> The plugin itself is still installed. To remove the plugin entirely, run:
> `claude plugin uninstall self-improving-claude`
>
> If you want to reinstall later: `claude plugin install self-improving-claude` from the same marketplace.
