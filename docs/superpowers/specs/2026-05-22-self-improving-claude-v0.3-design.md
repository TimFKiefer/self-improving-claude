# self-improving-claude v0.3 — Design Spec

**Status:** Approved design (revised 2026-05-23 after knowledge-base re-review). Implementation plan to follow via `writing-plans`.

**Predecessor specs:**
- `docs/superpowers/specs/2026-05-22-self-improving-claude-design.md` (v0.1 + v0.2 design — still authoritative for unchanged sections)
- This spec extends that with the v0.3 changes.

**Design principle for v0.3:** Use Claude Code's built-in features (hooks, permissions, skills, commands) before writing custom scripts. Where the platform already does something, don't reinvent it.

**Feedback memories driving this design:**
- `memory/feedback_distribution_ux.md` — three UX gaps from dogfooding
- `memory/feedback_orchestrator_form_bias.md` — form-selection bias
- `memory/feedback_ollama_first.md` — eval backend preference

---

## 1. Problem and goal

After v0.2 dogfooding, three classes of friction blocked a public release:

1. **Distribution.** The repo's flat layout meant `claude plugin install` didn't work. Users had to use `claude --plugin-dir <path>` per session — fine for the author, hostile for first-time visitors.
2. **UX.** The model-invoked orchestrator skill showed up in the `/` menu where the user could mis-select it, leaving the orchestrator in an undefined state.
3. **Quality.** The orchestrator's Step 4 (form selection) slid to `CLAUDE.md note` whenever a hook seemed expensive, missing PostToolUse command-hooks AND `permissions.ask` entirely. Dogfooded against a real bug (`FILE_READ_TOOL_NAME 'Read' → 'View'`), it produced a soft suggestion when an enforceable guardrail was warranted.

v0.3 is the **public release**. It fixes all three classes by leaning into Claude Code's built-in capabilities — settings.json `permissions.{deny,ask,allow}`, the full set of 9 hook events for richer telemetry, slash commands as the user-facing surface for everything, and the `${CLAUDE_PLUGIN_ROOT}` portability pattern.

**Non-goals (v0.3):**
- GitHub Actions CI (later)
- Demo screencast / blog post (separate launch workstream, not code)
- Auto-rewind investigation (still stretch)
- **Auto-collect / Stop-hook pattern detection** — speculative feature, deferred to v0.4 until dogfood evidence shows it's wanted (YAGNI)
- Cross-platform Windows support — until someone asks
- Plugin renaming — would break sentinels

---

## 2. User-visible surface

v0.3 ships **three** user-invoked slash commands (was two in v0.2):

| Command | Behavior |
|---|---|
| `/improve` | Reactive guardrail proposal (uses current chat). Unchanged from v0.2 except orchestrator improvements. |
| `/improve-init` | Proactive scan (project + telemetry + feedback). Unchanged surface; reads more telemetry signal now (see §3.5). |
| **`/improve-uninstall`** | NEW. Removes the plugin's footprint from THIS project (sentinel entries in settings.json, generated hook scripts, optionally telemetry). Plugin itself stays installed; use `claude plugin uninstall` for that. |

The `/` menu shows **only** these three. The orchestrator becomes a non-skill content file (`shared/procedure.md`) so it doesn't pollute the menu.

Three artifacts inside the user's project's `.claude/self-improving-claude/`:
- `telemetry.jsonl` — current session's tool log (richer in v0.3 — captures more event types)
- `telemetry.<YYYYMMDD-HHMMSS>.jsonl` — archived previous sessions (new — rotated at session end via inline bash)
- `feedback.jsonl` — user-flagged hook misfires (new — formalized from v0.2 chat-only routing)

(No `candidates.jsonl` — auto-collect deferred to v0.4.)

---

## 3. Architecture

### 3.1 Repo + plugin layout (the restructure)

```
self-improving-claude/                              ← marketplace + repo + git root
├── .claude-plugin/
│   └── marketplace.json                            ← lists self-improving-claude at "./plugin"
├── plugin/                                          ← THE PLUGIN
│   ├── .claude-plugin/
│   │   └── plugin.json
│   ├── skills/
│   │   ├── improve/SKILL.md
│   │   ├── improve-init/SKILL.md
│   │   ├── improve-uninstall/SKILL.md               ← NEW user-invoked skill
│   │   └── shared/                                  ← NOT a skill (no SKILL.md)
│   │       ├── procedure.md                         ← 10-step orchestrator body
│   │       └── references/
│   │           ├── hook-patterns.md
│   │           ├── tools-reference.md
│   │           ├── settings-merge.md
│   │           ├── prompt-rubric.md
│   │           └── examples.md
│   ├── hooks/
│   │   └── hooks.json                               ← multi-event telemetry + inline-bash rotation
│   └── scripts/
│       └── telemetry.py                             ← only Python script we ship (extended for multi-event)
├── docs/                                            ← unchanged location
├── evals/                                           ← unchanged location (with fixture 006 added)
├── README.md                                        ← rewritten for public + troubleshooting section
├── CHANGELOG.md                                     ← NEW
├── LICENSE
├── pyproject.toml
├── requirements-dev.txt
└── .gitignore
```

**Breaking change:** `--plugin-dir` path moves from `<repo>` to `<repo>/plugin`. Documented in CHANGELOG.

**No more session_end.py, stop.py, uninstall.py.** All replaced by built-in mechanisms (inline bash, slash command, deferred-to-v0.4).

### 3.2 Marketplace manifest

`.claude-plugin/marketplace.json`:

```json
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "self-improving-claude",
  "description": "Marketplace for the self-improving-claude plugin — turns the bugs you just saw into the hooks that prevent the next ones.",
  "owner": {
    "name": "Tim Kiefer",
    "email": "tim.f.kief@gmail.com"
  },
  "plugins": [
    {
      "name": "self-improving-claude",
      "description": "Proactive and reactive guardrail proposals for your Claude Code projects, with per-proposal approval.",
      "author": {
        "name": "Tim Kiefer",
        "email": "tim.f.kief@gmail.com"
      },
      "category": "productivity",
      "source": "./plugin"
    }
  ]
}
```

### 3.3 Inline-vs-shared orchestrator decision

Preferred: `plugin/skills/shared/procedure.md` (single file, no SKILL.md ⇒ not a discoverable skill). Both entry skills `@`-mention `@../shared/procedure.md` plus references under `@../shared/references/`.

**Probe-task in implementation:** confirm `@`-mentions resolve outside the skill directory (paths with `../`). If they DO NOT resolve, fall back to **inline duplication** — copy the procedure body into both `skills/improve/SKILL.md` and `skills/improve-init/SKILL.md`, document the fallback in CHANGELOG.

The old `skills/self-improving-claude/` directory is removed regardless of which fallback is used.

### 3.4 Form-selection fix — now five forms

`plugin/skills/shared/references/prompt-rubric.md` criterion #2 rewritten:

> **Lightest *viable* form.** The chosen form must actually enforce the rule. CLAUDE.md notes are NOT viable for rules of shape "before X do Y" or "after X show Y" — these need a hook (Pre/PostToolUse) or a `permissions` rule. A CLAUDE.md note that relies on the model remembering is not viable for any recurring failure mode. Use one of the lighter forms (`permissions.deny`, `permissions.ask`, prompt-hook, command-hook) unless the rule is purely a stylistic preference with no enforcement need.

`plugin/skills/shared/procedure.md` Step 4 expanded — **five forms, considered in this order:**

> 1. **`permissions.deny`** — if a glob covers it uniformly across tools and the action should be unconditionally blocked. Cheapest. No model call, no script, no user interaction.
>
> 2. **`permissions.ask`** — if a glob covers the action AND the user is sometimes OK with it but wants to be the one to decide. Examples: `Bash(git push:*)`, `Bash(rm -rf:*)`, `Bash(npm publish:*)`. Built-in Claude Code prompts the user; we don't write a script or hook. Lighter than a prompt-hook because no LLM evaluation is needed — the user decides directly. This form is often missed; use it whenever "warn and let me confirm" is the right semantic.
>
> 3. **Prompt-based hook** (`"type": "prompt"`) — if pre-condition *reasoning* is needed (recognizing intent across novel input shapes that globs can't express) AND the event supports prompt hooks (PreToolUse, Stop, SubagentStop, UserPromptSubmit).
>
> 4. **Command-hook on PreToolUse** — if the check is fast and deterministic and must BLOCK the tool call.
>
> 5. **Command-hook on PostToolUse** — if the check needs to SURFACE context (grep results, formatter output, type errors) back to Claude AFTER an action. Often the right answer for "after editing X, show Y." Cheap, deterministic, no model call. Was missed in v0.2's form selection — explicitly elevated in v0.3.
>
> Last resort: **`CLAUDE.md` note** — only for taste-level preferences with zero enforcement need (e.g. "prefer pnpm over npm"). Never for ordering rules or context-surfacing rules.

**New worked example #4 lands in `examples.md`:** the `grep-export-callers` PostToolUse command-hook (the case from the 2026-05-22 dogfooding). Demonstrates form #5.

**New worked example #5 lands in `examples.md`:** a `permissions.ask` rule for `Bash(git push:*)`, replacing the v0.2 prompt-hook example (which is rewritten to demonstrate when a prompt-hook IS appropriate — e.g. detecting novel input shapes a glob can't catch).

### 3.5 Multi-event telemetry

The bundled telemetry hook listens on **four events** instead of just `PostToolUse`:

```json
{
  "hooks": {
    "PostToolUse": [{"matcher": "*", "hooks": [{"name":"self-improving-claude/telemetry","type":"command","command":"python3 ${CLAUDE_PLUGIN_ROOT}/scripts/telemetry.py","timeout":5}]}],
    "Notification": [{"matcher": "*", "hooks": [{"name":"self-improving-claude/telemetry-notification","type":"command","command":"python3 ${CLAUDE_PLUGIN_ROOT}/scripts/telemetry.py","timeout":5}]}],
    "PreCompact": [{"matcher": "*", "hooks": [{"name":"self-improving-claude/telemetry-precompact","type":"command","command":"python3 ${CLAUDE_PLUGIN_ROOT}/scripts/telemetry.py","timeout":5}]}],
    "SessionStart": [{"matcher": "*", "hooks": [{"name":"self-improving-claude/telemetry-sessionstart","type":"command","command":"python3 ${CLAUDE_PLUGIN_ROOT}/scripts/telemetry.py","timeout":5}]}],
    "SessionEnd": [{"matcher": "*", "hooks": [{"name":"self-improving-claude/rotate-telemetry","type":"command","command":"f=\"${CLAUDE_PROJECT_DIR}/.claude/self-improving-claude/telemetry.jsonl\"; [ -f \"$f\" ] && mv \"$f\" \"${f%.jsonl}.$(date +%Y%m%d-%H%M%S).jsonl\" && touch \"$f\" || true","timeout":5}]}]
  }
}
```

`scripts/telemetry.py` extended to branch on `hook_event_name`:

| Event | New row shape |
|---|---|
| `PostToolUse` | `{ts, event:"tool", tool, args_summary, outcome}` (existing) |
| `Notification` | `{ts, event:"notification", kind}` — kind = `"waiting_for_permission"` or `"idle"` (signals friction) |
| `PreCompact` | `{ts, event:"compact", reason}` — signals long session |
| `SessionStart` | `{ts, event:"session_start"}` — boundary marker |

`SessionEnd` is **inline bash** (no Python) — renames `telemetry.jsonl` to `telemetry.<YYYYMMDD-HHMMSS>.jsonl`, touches a fresh empty file for the next session. No script file shipped for this.

**Why:** the extra events give `/improve-init` richer signal to mine. `Notification` waiting-for-permission events surface "permission rules that are nagging the user every session." `PreCompact` signals "this session is long enough that compaction happened — maybe ergonomics rules would help." `SessionStart` lets `/improve-init` segment per-session when needed.

### 3.6 Feedback channel (formalized)

New file at `.claude/self-improving-claude/feedback.jsonl` (separate from telemetry):

```jsonl
{"ts":"2026-05-22T15:30:01Z","target":"self-improving-claude/block-pnpm-test-watcher","mode":"too-broad","complaint":"blocked legitimate `pnpm test --filter foo` command","resolution":"narrowed matcher"}
```

Schema:
- `ts` (ISO-8601 UTC)
- `target` — sentinel `name` of the hook the user complained about
- `mode` ∈ `{too-broad, false-positive, please-narrow, missed-case}`
- `complaint` — user's free-text complaint
- `resolution` — orchestrator's text describing what it did

Procedure Step 1 routing: when `<user_directive>` matches feedback shape, the orchestrator:
1. Identifies the target hook by name (asks via `AskUserQuestion` if ambiguous).
2. Appends a row to feedback.jsonl.
3. Modifies the named hook entry to narrow its matcher / add an exception / loosen the block condition.
4. Does NOT propose new hooks in feedback mode.

`/improve-init` reads recent feedback.jsonl entries — when proposing similar hooks again, applies extra scrutiny ("the user previously said hook X was too broad — make sure I don't repeat the same overreach shape").

### 3.7 `/improve-uninstall` slash command

`plugin/skills/improve-uninstall/SKILL.md` — frontmatter:

```yaml
---
name: improve-uninstall
description: Run /improve-uninstall to cleanly remove self-improving-claude's footprint from THIS project — sentinel hooks in settings.json, generated scripts in .claude/hooks/, optionally the local telemetry log. The plugin itself stays installed; use `claude plugin uninstall self-improving-claude` for that.
argument-hint: [optional --dry-run to preview, or --keep-telemetry to preserve the log archive]
allowed-tools: [Read, Edit, Bash, AskUserQuestion]
---
```

Body — 5-step skill workflow:

1. **Inspect.** Read `.claude/settings.json`. Parse. If parse fails, abort with the error path and ask user to fix manually.
2. **Enumerate.** Find all entries under `hooks.*` arrays with `name: "self-improving-claude/..."`. Find any `permissions.deny` / `permissions.ask` rules that match known plugin-emitted patterns (we don't tag permission rules with sentinels, so this is best-effort — show user the list for confirmation).
3. **Confirm.** Show the user a summary via `AskUserQuestion`: how many hook entries, how many generated scripts to delete, whether to also clear `.claude/self-improving-claude/`. Options: `confirm-all`, `confirm-hooks-only`, `dry-run`, `abort`.
4. **Remove.** Strip matched hook entries from arrays via the same defensive merge as `/improve` (per `@../shared/references/settings-merge.md`). Delete generated scripts from `.claude/hooks/<slug>.*`. Optionally `rm -rf .claude/self-improving-claude/` if user opted in.
5. **Report.** Summarize what was removed, what was kept, remind the user about `claude plugin uninstall self-improving-claude` for the plugin-level uninstall.

**Why a slash command not a Python script:** consistent UX with `/improve` and `/improve-init`; reuses the existing skill mechanism; no terminal command for the user to remember; `AskUserQuestion` gives native confirmation prompts.

### 3.8 README rewrite (with troubleshooting section)

`README.md` at the repo root targets a **first-time visitor** audience:
- **Hero pitch** (3 sentences): what it does, who it's for, why care
- **30-second demo** (asciinema/gif link placeholder; just text for v0.3)
- **Install** (3 lines: marketplace add + install + done)
- **First-time use** (run `/improve-init` walkthrough)
- **The three commands** (`/improve`, `/improve-init`, `/improve-uninstall`)
- **Trust & privacy** (arbitrary hook code, per-proposal approval, telemetry stays local)
- **Inspecting & troubleshooting** — points at Claude Code's BUILT-IN affordances:
  - `/hooks` — list all currently-loaded hooks
  - `/memory` — open/edit your CLAUDE.md
  - `claude plugin list` — list installed plugins
  - `claude --debug` — verbose logging for hook execution
  - `claude plugin uninstall self-improving-claude` — remove the plugin
- **Roadmap & status** (v0.3 current)
- **Contributing** (link to design docs, eval requirements)

### 3.9 Anthropic-marketplace PR materials

`docs/anthropic-marketplace-pr.md` containing:
- The diff that would land if we PR to `anthropics/claude-plugins-official` (add an entry to their `marketplace.json` pointing at this repo's git-subdir)
- Draft PR title + body explaining the plugin
- Pre-submit checklist (description length, category, schema validation)

Does NOT submit the PR — that's a user action after public launch.

---

## 4. Data flow

### 4.1 Normal session

```
SessionStart event → telemetry.py logs session_start marker
   → user works → PostToolUse events log each tool call
   → Notification events log permission/idle friction
   → PreCompact (if it fires) logs compaction
   → SessionEnd event → inline bash renames telemetry.jsonl → archive,
                         touches fresh empty file
```

### 4.2 /improve (reactive)

```
User invokes /improve "..."
   → orchestrator reads chat + recent telemetry + feedback.jsonl + existing hooks
   → routes on $ARGUMENTS shape (default | directive | feedback)
   → if FEEDBACK mode: append to feedback.jsonl, modify target hook, no new proposals
   → else: identify candidates, choose lightest viable form (5-option ladder),
           draft, self-critique, validate, walk user through approval, write files
   → close out with restart + ESC-ESC-rewind instructions
```

### 4.3 /improve-init (proactive)

```
User invokes /improve-init
   → orchestrator reads project snapshot + telemetry archives + transcripts
                  + feedback.jsonl (applies scrutiny for re-proposed shapes)
   → identifies candidates (capped at 5)
   → same form-selection ladder, same approval loop
```

### 4.4 /improve-uninstall

```
User invokes /improve-uninstall [--dry-run]
   → skill inspects settings.json for self-improving-claude/* sentinels
   → confirms with AskUserQuestion (confirm-all | hooks-only | dry-run | abort)
   → atomic settings.json edit, scripts deletion, optional telemetry clear
   → reports + reminds about `claude plugin uninstall` for the plugin itself
```

---

## 5. Out of scope for v0.3

- **Auto-collect via Stop hook** (deferred to v0.4 if dogfood shows real demand)
- GitHub Actions CI
- Demo screencast / blog post (separate launch workstream)
- Auto-rewind investigation
- Cross-platform Windows testing
- Plugin renaming
- Eval fixtures 008+ (sufficient coverage at 7 entries for v0.3)
- Integration tests for canonical generated hooks (manual smoke test in acceptance covers this for v0.3)

---

## 6. Critical risks and mitigations

| Risk | Mitigation |
|---|---|
| `@`-mention to `../shared/procedure.md` doesn't resolve | Probe in implementation Task 1; fall back to inline duplication if needed. |
| Restructure breaks existing user installs (their `--plugin-dir` path changes) | CHANGELOG entry; README documents new path; existing settings.json entries unaffected (sentinel format unchanged). |
| Multi-event telemetry generates too much data on long sessions | `telemetry.py` discards unknown events gracefully; SessionEnd rotation keeps each file bounded to one session. |
| `/improve-uninstall` accidentally removes user-authored entries | Strict sentinel-name match only; entries without `self-improving-claude/` prefix left untouched; `AskUserQuestion` confirmation before destructive action; `--dry-run` preview supported. |
| `permissions.ask` rules cause friction if the user originally wanted hard-block | Orchestrator's procedure Step 4 explicitly notes when to prefer `ask` vs `deny`; the per-proposal approval gives the user final say. |
| Anthropic-marketplace PR rejected | Preparation only; no v0.3 dependency on acceptance. |
| Form-selection fix overcorrects (now uses hooks for taste-level rules) | Eval fixture 006 + the rubric's "zero enforcement need" carve-out keep CLAUDE.md as a valid option for taste rules. Baseline rerun verifies. |

---

## 7. Acceptance criteria for v0.3.0

1. **Install:** `claude plugin marketplace add /path/to/repo` succeeds; `claude plugin install self-improving-claude` succeeds; restart shows `improve`, `improve-init`, and `improve-uninstall` in `/` listing AND NOT `self-improving-claude` (orchestrator hidden).
2. **Form-selection regression:** eval fixture 006 (rename-callers) scores `command-hook` or `prompt-hook`, NOT `claude-md-note`. NEW: eval fixture 007 (git-push-warn) prefers `permissions.ask` over `prompt-hook` when both would work.
3. **Baseline:** both gemma4 and Haiku baselines rerun and committed at `evals/results/2026-05-23-v0.3-gemma.json` and `evals/results/2026-05-23-v0.3-haiku.json`. Both deltas vs v0.2 baseline documented in CHANGELOG.
4. **Multi-event telemetry:** `telemetry.jsonl` from a real session contains rows with `event` in `{tool, notification, session_start, compact}`. Archive file appears after session end.
5. **Feedback:** invoking `/improve "the foo-hook just blocked something legit"` on a project with that hook installed appends a row to `feedback.jsonl` AND modifies (does not duplicate) the hook entry.
6. **Uninstall:** running `/improve-uninstall --dry-run` lists what would be removed without changing files. Running `/improve-uninstall` removes sentinel entries, deletes generated scripts, confirms before destructive action.
7. **README:** publishable — clear hero pitch, install in <2 minutes, trust + privacy + security sections, troubleshooting section pointing at built-in commands (`/hooks`, `--debug`, etc.), link to design docs.
8. **Anthropic-marketplace PR materials:** `docs/anthropic-marketplace-pr.md` exists with a draft PR body and validated schema-compliance.

---

## 8. Open implementation questions

- Whether `@`-mentions resolve `../shared/...` paths from inside a skill directory — probe in Task 1. If no, fall back to inline duplication.
- Whether `claude plugin install` works against a local marketplace path (`marketplace add /local/path` then `install`), or if a different local-install workflow is needed for development. Verified during Task 1.
- Whether all four bundled telemetry events fire reliably on a real session — verified during the multi-event telemetry task.

These are resolved during implementation, not blockers for the spec.

---

## 9. Implementation track summary

**Track A — Distribution (3 tasks):**
- A1. Marketplace restructure (plugin/ subdir + marketplace.json + path updates in evals/run.py)
- A2. Orchestrator hidden (probe `@../shared/procedure.md`, fallback inline)
- A3. README rewrite + CHANGELOG + Anthropic-marketplace PR materials

**Track B — Quality (4 tasks):**
- B1. Form-selection fix (rubric §2 + procedure Step 4, now 5 forms including `permissions.ask`)
- B2. Two new worked examples (`grep-export-callers` PostToolUse, `permissions.ask` for git push)
- B3. Eval fixtures 006 (rename-callers) and 007 (git-push-warn)
- B4. Feedback channel formalized (Step 1 routing writes feedback.jsonl + modifies target hook)

**Track C — Robustness (2 tasks):**
- C1. Multi-event telemetry (`telemetry.py` branches on `hook_event_name`, hooks.json adds 3 more events)
- C2. `/improve-uninstall` slash command (new skill with the 5-step workflow)

**Track D — Eval maturity (1 task):**
- D1. Cloud baseline rerun against Haiku for production-quality reference

**Total: 10 tasks** (down from the original 14 — auto-collect dropped, three Python scripts collapsed into inline bash / slash command / extended telemetry.py).
