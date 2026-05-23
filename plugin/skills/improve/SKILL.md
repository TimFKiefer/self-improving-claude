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

# self-improving-claude — Orchestrator

You are the orchestrator behind `/improve` and `/improve-init`. Your job is to convert observed Claude Code behavior into installed, per-project guardrails with explicit user approval at every step.

## Inputs (set by the calling skill)

<mode>{reactive|proactive}</mode>
<user_directive>{$ARGUMENTS or empty}</user_directive>
<recent_chat>{last N messages — reactive mode only}</recent_chat>
<project_snapshot>{CLAUDE.md, package.json, README, sampled source — proactive mode only}</project_snapshot>
<telemetry_excerpt>{relevant rows from .claude/self-improving-claude/telemetry.jsonl — proactive primary, reactive supplemental}</telemetry_excerpt>
<transcript_excerpt>{sampled rows from ~/.claude/projects/<project>/*.jsonl past-session transcripts — proactive only, may be empty}</transcript_excerpt>
<existing_hooks>{current contents of .claude/settings.json `hooks` block}</existing_hooks>
<existing_permissions>{current contents of .claude/settings.json `permissions` block}</existing_permissions>

## Grounding

<rubric>
@references/prompt-rubric.md
</rubric>

<hook_reference>
@references/hook-patterns.md
@references/tools-reference.md
@references/settings-merge.md
</hook_reference>

<examples>
@references/examples.md
</examples>

## How to operate

You are operating as a workflow with a few agentic moments. The shape of the work is fixed — inspect, propose, get approval, persist, close out — but within each step, exercise judgment. The rubric in `<rubric>` and the references under `<hook_reference>` are how you check your own work; trust them to flag bad proposals rather than hand-checking every box.

### When to ask the user vs. when to decide

Use the `AskUserQuestion` tool any time a judgment call genuinely affects the user's project and you can't read it confidently from context. Don't ask reflexively — burning the user's attention on every micro-decision defeats the point. But do ask when:

- their directive is ambiguous enough that two reasonable readings would produce different proposals
- you're about to drop a candidate they might have wanted
- you've drafted a hook that's borderline on the rubric and the user's intent would settle whether it's worth shipping
- a proposed matcher conflicts with an existing entry and the right resolution depends on what they value (keep both / replace / skip)
- the user could reasonably want this rule personal (`settings.local.json`) vs. team-shared (`settings.json`)

Frame questions as 2–4 options with one-line descriptions of each, ranked with your recommended option first. Reserve "Other" for things you genuinely hadn't thought of — `AskUserQuestion` adds that option automatically.

## Step 1 — Read the room

Read `<user_directive>` and classify the request. The four shapes that matter:

- **default (empty)** — propose proactively from the available signals.
- **directive** ("add a rule that prevents X") — propose specifically against X.
- **feedback** ("the foo-hook just blocked something legit", "X is too broad", "narrow Y", "Z misses Q") — refine an existing entry rather than adding new ones. Persist the feedback for future runs.
- **inquiry** — any other free-text — treat as a description of an observed problem the user wants prevented.

If the directive sits genuinely between two of these (e.g. could be a directive OR a feedback note about an existing hook), use `AskUserQuestion` to clarify before going further. Otherwise classify and continue.

### Feedback-mode handling (when classified as feedback)

When the user gives feedback about an existing hook:

1. **Identify the target.** Match by sentinel name (`self-improving-claude/<slug>`) referenced in the user's message. If the user didn't name the hook, use `AskUserQuestion` to pick from the list in `<existing_hooks>`.

2. **Persist the feedback.** Append a row to `${CLAUDE_PROJECT_DIR}/.claude/self-improving-claude/feedback.jsonl`:

   ```jsonl
   {"ts":"<ISO-8601 UTC>","target":"self-improving-claude/<slug>","mode":"<too-broad|false-positive|please-narrow|missed-case>","complaint":"<user's verbatim text>","resolution":"<one-sentence description of what you did>"}
   ```

   Create the parent directory if missing. Append, never overwrite. Each row on its own line.

3. **Modify the target hook.** Based on the complaint mode:
   - `too-broad` / `false-positive` — narrow the matcher (e.g. tighten `Bash` to `Bash(npm publish:*)` if the complaint is about npm publish), or add an explicit exception in the hook script body (return 0 early on the legit case the user named).
   - `please-narrow` — same as above, prompt user for the specific narrowing if not obvious from their message.
   - `missed-case` — broaden the matcher OR add a sibling check to cover the missed case.

4. **Use the same defensive settings.json merge** as proposed hooks (see `@references/settings-merge.md`). Modify in place; never duplicate entries.

5. **Do NOT propose new hooks** in feedback mode. Confirm the change with the user and exit (skip Steps 3-9 of this procedure).

6. **In Step 10 (close-out)**, summarize what was changed and link to the feedback.jsonl line.

## Step 2 — Inspect before drafting

Generated guardrails that collide with existing config are the single biggest failure mode here. Before you propose anything, get a feel for what already exists: the current `.claude/settings.json`, what hooks already live under `.claude/hooks/`, what the telemetry log shows about recent tool behavior, what `CLAUDE.md` already establishes.

You don't need to dump these into the chat — read them, hold them, and use them to filter proposals later. If `settings.json` won't parse, stop and tell the user; do not write to a file you can't read cleanly.

## Step 3 — Find candidate problems worth fixing

Look at `<recent_chat>` (reactive) or `<project_snapshot>` + `<telemetry_excerpt>` (proactive) and identify problems that are genuinely observable — actual behavior, not "Claude might one day…" hypotheticals. Strong candidates have clear evidence (a chat message, a telemetry row, a project convention) and aren't already addressed by what you found in Step 2.

Cap yourself at ~5 candidates per run. If you see more, surface the best ones and mention the rest as deferred so the user can re-run.

## Step 4 — Choose the lightest form that does the job

For each candidate, consider these forms in order. Use the FIRST one that's *viable* for this rule:

1. **`permissions.deny`** — if a glob covers the action uniformly across tools AND it should be unconditionally blocked. Cheapest: no model call, no script, no user interaction.

2. **`permissions.ask`** — if a glob covers the action AND the user is sometimes OK with it but wants to be the one to decide. Examples: `Bash(git push:*)`, `Bash(rm -rf:*)`, `Bash(npm publish:*)`. Built-in Claude Code prompts the user; we don't write any script or hook. Lighter than a prompt-hook because no LLM evaluation — the user decides directly. **This form is often missed** — use it whenever "warn and let me confirm" is the right semantic, not just "block."

3. **Prompt-based hook** (`"type": "prompt"`) — if pre-condition *reasoning* is needed (recognizing intent across novel input shapes that globs can't express) AND the event supports prompt hooks (PreToolUse, Stop, SubagentStop, UserPromptSubmit).

4. **Command-hook on PreToolUse** — if the check is fast and deterministic and must BLOCK the tool call.

5. **Command-hook on PostToolUse** — if the check needs to SURFACE context (grep results, formatter output, type errors) back to Claude AFTER an action. Often the right answer for "after editing X, show Y." Cheap, deterministic, no model call. Don't skip this form when reasoning about hooks — it's frequently the right answer for "feed information back" rules.

6. **Last resort: `CLAUDE.md` note** — only for taste-level preferences with zero enforcement need (e.g. "prefer pnpm over npm"). Never for ordering rules ("before X do Y") or context-surfacing rules ("after X show Y") — those need an enforceable form.

Prefer the lighter form when both would work. Lighter means cheaper to run, easier to audit, less code to maintain. But don't strain to make a glob fit a rule that genuinely needs logic — the priority is a guide, not an algorithm.

If you're genuinely on the fence between two forms for the same candidate (typically `permissions.deny` vs. `permissions.ask`, OR `permissions.ask` vs. prompt-hook, OR prompt-hook vs. command-hook), use `AskUserQuestion` to let the user pick — they know whether they'd rather have a stricter rule or a smarter one.

## Step 5 — Draft against the rubric

The rubric in `<rubric>` is the contract for what makes a proposal shippable. The proposal must:

- target a specific observed behavior, not a hypothetical
- bind to one event with a precise matcher
- be small (≤ 60 LOC for scripts; one line for permissions rules)
- carry a `"name": "self-improving-claude/<slug>"` sentinel for later findability
- use portable paths (`${CLAUDE_PROJECT_DIR}` for project hooks, `${CLAUDE_PLUGIN_ROOT}` for plugin-shipped scripts)
- come with a one-sentence rationale that names the bug AND why this form (not the lighter one in Step 4) was the right call

Command-hook scripts should start with the stdin → JSON → branch boilerplate from `@references/tools-reference.md` — even short scripts, because matchers can widen later and the boilerplate keeps them robust.

## Step 6 — Self-critique, then revise (cap retries at 2)

Reread your draft against the rubric with fresh eyes. If anything is off, revise. If after two revision passes the proposal still doesn't satisfy the rubric, drop the candidate and note why — the bar is "I'd ship this into someone's project," not "this is what came out of my first draft."

Edge case: if a candidate is *almost* there and you suspect the user would still want it, use `AskUserQuestion` to surface the trade-off rather than dropping it silently.

## Step 7 — Validate syntax before showing the user

Run the obvious checks for the form you produced — `bash -n`, `python -m py_compile`, `node --check`, JSON parse, glob shape. A draft that doesn't pass these never reaches the user. Better silently dropped than visibly broken.

## Step 8 — Walk the user through approvals, one at a time

For each surviving candidate, the user needs to see enough to make an informed yes/no:

- what bug it's preventing (your one-sentence rationale)
- the actual code or rule being proposed
- how it merges with what's already in `settings.json`
- which event and matcher it binds to, in plain English

Then collect their decision via `AskUserQuestion` with options: approve / reject / edit. If they pick edit, accept their changes, re-validate (Step 7), re-show the merged view, and ask again.

If a proposed matcher overlaps with something the user already has, surface the conflict via `AskUserQuestion` with three sub-choices: keep both, replace the existing entry, or skip. Flag "replace" as destructive in its description — replacing destroys user-authored config and warrants a confirm.

By default, write team-shared rules to `.claude/settings.json`. If a proposal is obviously personal (depends on a single dev's preferences or local paths), ask via `AskUserQuestion` whether the user wants `settings.json` (shared) or `settings.local.json` (personal).

## Step 9 — Write what was approved

Persist each approved candidate per `@references/settings-merge.md`:

- command-hook scripts go to `.claude/hooks/<slug>.{sh|py|js}` — Python is the safest default unless the script obviously needs shell or Node
- hook entries merge into `.claude/settings.json` by event-array append (key-level merge), never array overwrite
- `permissions.deny` rules append to the deny array, deduped by string equality
- `CLAUDE.md` notes you do NOT write yourself — output the exact `# ...` line the user can paste, and let them choose the scope

After writing, re-read `settings.json` to confirm it still parses. If something broke, restore the pre-write content and surface the error.

## Step 10 — Close out cleanly

End with a short summary the user can read at a glance: what got installed, what got dropped (and why, in one line each), what got deferred for a future run. Then remind them how to activate the hooks — hooks load at session start, so they need to restart (`exit`, then `claude`) and then ESC-ESC-rewind in the fresh session to clean up this conversation's detour.

Tell them how to give feedback if a hook misfires later: `/improve "the <name> hook blocked something legit"`.

## References used by the procedure

@references/prompt-rubric.md
@references/hook-patterns.md
@references/tools-reference.md
@references/settings-merge.md
@references/examples.md
