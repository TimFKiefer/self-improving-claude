# self-improving-claude v0.3 — Design Spec

**Status:** Approved design (2026-05-22). Implementation plan to follow via `writing-plans`.

**Predecessor specs:**
- `docs/superpowers/specs/2026-05-22-self-improving-claude-design.md` (v0.1 + v0.2 design — still authoritative for unchanged sections)
- This spec extends that with the v0.3 changes.

**Feedback memories driving this design:**
- `memory/feedback_distribution_ux.md` — three UX gaps from dogfooding
- `memory/feedback_orchestrator_form_bias.md` — form-selection bias
- `memory/feedback_ollama_first.md` — eval backend preference

---

## 1. Problem and goal

After v0.2 dogfooding, three classes of friction blocked a public release:

1. **Distribution.** The repo's flat layout meant `claude plugin install` didn't work. Users had to use `claude --plugin-dir <path>` per session — fine for the author, hostile for first-time visitors.
2. **UX.** The model-invoked orchestrator skill showed up in the `/` menu where the user could mis-select it, leaving the orchestrator in an undefined state.
3. **Quality.** The orchestrator's Step 4 (form selection) slid to `CLAUDE.md note` whenever a hook seemed expensive, missing PostToolUse command-hooks entirely. Dogfooded against a real bug (`FILE_READ_TOOL_NAME 'Read' → 'View'`), it produced a soft suggestion when an enforceable guardrail was warranted.

v0.3 is the **public release**. It fixes all three classes, plus adds session-lifecycle hooks (SessionEnd telemetry rotation, opt-in Stop-hook auto-collect) that make the plugin sustainably usable in long-running projects.

**Non-goals (v0.3):** GitHub Actions CI, demo/screencast materials, auto-rewind, cross-platform Windows support, "full auto" auto-improve (only opt-in silent-collect lands).

---

## 2. User-visible surface

Same two slash commands as v0.2 — no API changes. Internal changes:

| Surface | v0.2 behavior | v0.3 behavior |
|---|---|---|
| `/improve` | Reactive | Same. Reads candidates.jsonl (if present) alongside chat. |
| `/improve-init` | Proactive | Same. Reads candidates.jsonl + feedback.jsonl. |
| Bundled telemetry hook | `PostToolUse: "*"` to `telemetry.jsonl` | Same + SessionEnd archiver + opt-in Stop collector. |
| `/` menu | Shows `improve`, `improve-init`, **`self-improving-claude`** | Shows only `improve` and `improve-init`. |

Three new artifacts inside the user's project's `.claude/self-improving-claude/`:
- `telemetry.jsonl` — current session's tool log (same as v0.2)
- `telemetry.<YYYY-MM-DD-HHMMSS>.jsonl` — archived previous sessions (new)
- `candidates.jsonl` — pattern-detected guardrail candidates from opt-in Stop hook (new)
- `feedback.jsonl` — user-flagged hook misfires (new)

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
│   │   └── shared/                                  ← NOT a skill (no SKILL.md)
│   │       ├── procedure.md                         ← 10-step orchestrator body
│   │       └── references/
│   │           ├── hook-patterns.md
│   │           ├── tools-reference.md
│   │           ├── settings-merge.md
│   │           ├── prompt-rubric.md
│   │           └── examples.md
│   ├── hooks/
│   │   └── hooks.json                               ← telemetry + session_end + stop
│   └── scripts/
│       ├── telemetry.py
│       ├── session_end.py                           ← NEW (rotates telemetry)
│       ├── stop.py                                  ← NEW (opt-in candidate collector)
│       └── uninstall.py                             ← NEW (sentinel-aware cleanup)
├── docs/                                            ← unchanged location
│   ├── superpowers/{specs,plans}/
│   └── knowledge/
├── evals/                                           ← unchanged location
│   ├── ...
│   └── run.py                                       ← path constant updated to plugin/skills/shared/references/
├── README.md                                        ← rewritten for public
├── CHANGELOG.md                                     ← NEW
├── LICENSE
├── pyproject.toml
├── requirements-dev.txt
└── .gitignore
```

**Breaking change:** `--plugin-dir` path moves from `<repo>` to `<repo>/plugin`. Documented in CHANGELOG.

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

Preferred: `plugin/skills/shared/procedure.md` (single file, no SKILL.md ⇒ not a discoverable skill). Both entry skills `@`-mention `@../shared/procedure.md` plus the references under `@../shared/references/`.

**Probe-task in implementation:** confirm `@`-mentions resolve outside the skill directory (i.e. relative paths with `../`). If they DO NOT resolve, fall back to **inline duplication** — copy the procedure body into both `skills/improve/SKILL.md` and `skills/improve-init/SKILL.md`, accept the maintenance burden of keeping them in sync, and document the fallback in CHANGELOG.

The old `skills/self-improving-claude/` directory is removed regardless of which fallback is used.

### 3.4 Form-selection fix

`plugin/skills/shared/references/prompt-rubric.md` criterion #2 rewritten:

> **Lightest *viable* form.** The chosen form must actually enforce the rule. CLAUDE.md notes are NOT viable for rules of shape "before X do Y" or "after X show Y" — these need a hook (Pre/PostToolUse). A CLAUDE.md note that relies on the model remembering is not viable for any recurring failure mode. Use a hook unless the rule is purely a stylistic preference with no enforcement need.

`plugin/skills/shared/procedure.md` Step 4 expanded with explicit ordering:

> Consider the candidate forms in this order:
> 1. **`permissions.deny`** — if a glob covers it uniformly across tools.
> 2. **Prompt-based hook** (`"type": "prompt"`) — if pre-condition reasoning is needed AND the event supports prompt hooks (PreToolUse, Stop, SubagentStop, UserPromptSubmit).
> 3. **Command-hook on PreToolUse** — if the check is fast and deterministic and must BLOCK.
> 4. **Command-hook on PostToolUse** — if the check needs to SURFACE context (e.g. grep results, formatter output, type errors) back to Claude after an action. Often the right answer for "after editing X, show Y." Cheap, deterministic, no model call.
> 5. **`CLAUDE.md` note** — ONLY for taste-level preferences with zero enforcement need.

**A new worked example** lands in `examples.md` as Example 4: the `grep-export-callers` PostToolUse command-hook — concrete Python ≤60 LOC demonstrating the "surface callers after an export edit" pattern that was missed in dogfooding.

### 3.5 Feedback channel (formalized)

New file at `.claude/self-improving-claude/feedback.jsonl` (separate from telemetry):

```jsonl
{"ts":"2026-05-22T15:30:01Z","target":"self-improving-claude/block-pnpm-test-watcher","mode":"too-broad","complaint":"blocked legitimate `pnpm test --filter foo` command","resolution":"narrowed matcher"}
```

Schema fields:
- `ts` (ISO-8601 UTC)
- `target` — sentinel `name` of the hook the user complained about
- `mode` ∈ `{too-broad, false-positive, please-narrow, missed-case}`
- `complaint` — user's free-text complaint
- `resolution` — orchestrator's text describing what it did

Procedure Step 1 routing updated: when `<user_directive>` matches feedback shape ("the X hook blocked something legit", "X is too broad", etc.), the orchestrator:
1. Identifies the target hook by name (asks via `AskUserQuestion` if ambiguous).
2. Appends a row to feedback.jsonl.
3. Modifies the named hook entry to narrow its matcher / add an exception / loosen the block condition (whatever fits the complaint shape).
4. Does NOT propose new hooks in feedback mode.

`/improve-init` reads recent feedback.jsonl entries and applies extra scrutiny when proposing similar hooks again.

### 3.6 Session-lifecycle hooks

**Bundled `hooks/hooks.json`** updated:

```json
{
  "description": "self-improving-claude — passive telemetry + session lifecycle",
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [{
          "name": "self-improving-claude/telemetry",
          "type": "command",
          "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/telemetry.py",
          "timeout": 5
        }]
      }
    ],
    "Stop": [
      {
        "matcher": "*",
        "hooks": [{
          "name": "self-improving-claude/auto-collect",
          "type": "command",
          "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/stop.py",
          "timeout": 10
        }]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "*",
        "hooks": [{
          "name": "self-improving-claude/rotate-telemetry",
          "type": "command",
          "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/session_end.py",
          "timeout": 10
        }]
      }
    ]
  }
}
```

**`scripts/session_end.py` behavior:**
1. Read `${CLAUDE_PROJECT_DIR}/.claude/self-improving-claude/telemetry.jsonl`.
2. Rename to `telemetry.<YYYY-MM-DD-HHMMSS>.jsonl` (timestamp at session-end moment).
3. Touch a fresh empty `telemetry.jsonl` for the next session.
4. Silent-fail (same discipline as `telemetry.py` — never break Claude Code's shutdown).

**`scripts/stop.py` behavior:**
1. Read the plugin-installed gate from the session environment: `${SELF_IMPROVING_CLAUDE_AUTO_COLLECT}` (env var). If not `"true"`, exit 0 immediately.
2. Read current session's `telemetry.jsonl`. Scan for interesting patterns:
   - 3+ Bash invocations with same args_summary returning non-zero
   - Edits to the same `file_path` 3+ times within session
   - Repeated `<redacted-secret-pattern>` in Grep
   - `Read` to a path that matches an existing `permissions.deny` entry (= the user's deny is being circumvented somehow)
3. Append matched candidates to `${CLAUDE_PROJECT_DIR}/.claude/self-improving-claude/candidates.jsonl`:
   ```jsonl
   {"ts":"2026-05-22T15:30:01Z","pattern":"repeated-bash-failure","evidence":[{...}],"suggested_form":"command-hook"}
   ```
4. Pure pattern detection — no model call. Never blocks.

**Opt-in mechanism:** the plugin does NOT auto-enable Stop collection. The README documents how to opt in:

```json
// in user's .claude/settings.json
{
  "env": {
    "SELF_IMPROVING_CLAUDE_AUTO_COLLECT": "true"
  }
}
```

Default behavior (no env var set): `stop.py` exits immediately, no patterns collected. Off is the default.

### 3.7 Uninstall script

`plugin/scripts/uninstall.py` — invokable by user when they want to remove the plugin's footprint from a project:

```bash
python3 ~/.claude/plugins/marketplaces/self-improving-claude/plugin/scripts/uninstall.py \
  --project /path/to/your/project
```

Behavior (with prompts):
1. **Read** `<project>/.claude/settings.json`. If parse fails, refuse to act.
2. **Enumerate** all entries with `name: "self-improving-claude/..."`. Show summary to user.
3. **Confirm**: "Remove these N entries? [y/N]"
4. **Strip** matched entries from `hooks.<Event>` arrays. Leave non-plugin entries alone.
5. **Delete** referenced scripts from `<project>/.claude/hooks/` (those that were generated under our sentinel naming convention).
6. **Optionally** clear `<project>/.claude/self-improving-claude/` (telemetry + candidates + feedback). Prompts before destructive action.
7. **Write** updated settings.json with same atomic-write discipline as the orchestrator.
8. Reports what was removed and what remained.

Does NOT remove the plugin itself — that's `claude plugin uninstall`.

### 3.8 Anthropic-marketplace PR preparation

A new file: `docs/anthropic-marketplace-pr.md` containing:
- The diff that would land if we PR to `anthropics/claude-plugins-official` (add an entry to their `marketplace.json` pointing at this repo's git-subdir)
- Draft PR title + body explaining the plugin
- A pre-submit checklist (description length, category, schema validation against anthropic's schema)

Does NOT submit the PR — that's a user action after public launch.

### 3.9 README rewrite

`README.md` at the repo root targets a **first-time visitor** audience:
- **Hero pitch** (3 sentences): what it does, who it's for, why care
- **30-second demo** (asciinema/gif link placeholder; just text for v0.3)
- **Install** (3 lines: marketplace add + install + done)
- **First-time use** (run `/improve-init` walkthrough)
- **Trust & privacy** (arbitrary hook code, per-proposal approval, telemetry stays local)
- **Roadmap & status** (v0.3 current, future plans)
- **Contributing** (link to design docs, eval requirements)

---

## 4. Data flow

### 4.1 Normal session (no opt-in)

```
SessionStart → PostToolUse fires per call → telemetry.jsonl grows
   → user runs /improve → reads chat + telemetry → proposes → installs hooks
   → user keeps working → telemetry grows → ...
   → SessionEnd → session_end.py archives telemetry → empty fresh log
```

### 4.2 Opt-in auto-collect session

```
SessionStart → SELF_IMPROVING_CLAUDE_AUTO_COLLECT=true (from settings.env)
   → normal session work → PostToolUse fires → telemetry.jsonl grows
   → Stop event fires → stop.py reads telemetry, finds patterns
      → appends to candidates.jsonl (no model call)
   → SessionEnd → session_end.py archives telemetry
   ── next session ──
   → user runs /improve → reads chat + telemetry + candidates.jsonl
   → orchestrator surfaces collected candidates alongside chat-based ones
   → per-proposal approval (UNCHANGED — opt-in only affects what's surfaced)
```

### 4.3 Feedback flow

```
User runs /improve "the foo-hook blocked something legit"
   → orchestrator Step 1 classifies as feedback-mode
   → identifies target hook by name (or asks user)
   → appends row to feedback.jsonl
   → modifies the hook's matcher to narrow / add exception
   → writes updated settings.json
   → does NOT propose new hooks in this run
```

---

## 5. Out of scope for v0.3

- GitHub Actions CI (test/eval on PR) — later, when contributors exist
- Demo screencast / blog post — separate launch workstream, not code
- Auto-rewind investigation — still stretch goal
- Full-auto auto-improve mode (model call at session-end without consent) — opt-in silent-collect only
- Eval fixtures 008+ (saturation past 7) — sufficient coverage for v0.3 baseline
- Cross-platform Windows testing — until someone asks
- Plugin renaming (e.g. shorter prefix) — would break sentinels

---

## 6. Critical risks and mitigations

| Risk | Mitigation |
|---|---|
| `@`-mention to `../shared/procedure.md` doesn't resolve | Probe-task in implementation; fallback to inline duplication if needed. |
| Restructure breaks existing user installs (their `--plugin-dir` path changes) | CHANGELOG entry; README documents new path; existing settings.json entries are unaffected (sentinel format unchanged). |
| Auto-collect Stop hook adds latency on every Claude response | Off by default; even when opted in, no model call — pure pattern detection in Python. Hook timeout 10s. |
| Telemetry archive files accumulate forever | Acknowledged trade-off — archives are small JSONL. User can `rm` them; `uninstall.py` clears the directory if asked. v0.4 may add age-based pruning. |
| Uninstall script accidentally removes user-authored entries | Strict sentinel-name match only; entries without `self-improving-claude/` prefix are left untouched; user confirmation before destructive action. |
| Anthropic-marketplace PR rejected | Preparation only; user decides whether to submit; no v0.3 dependency on acceptance. |
| Form-selection fix overcorrects (now uses hooks for taste-level rules) | Eval fixture 006 + the rubric's new "zero enforcement need" carve-out keep CLAUDE.md note as a valid option for taste rules. Baseline rerun verifies. |
| candidates.jsonl grows unbounded | session_end.py truncates candidates.jsonl to most-recent 200 entries after archiving. |

---

## 7. Acceptance criteria for v0.3.0

1. **Install:** `claude plugin marketplace add /path/to/repo` succeeds; `claude plugin install self-improving-claude` succeeds; restart shows `improve` and `improve-init` in `/` listing AND NOT `self-improving-claude` (orchestrator hidden).
2. **Form-selection regression:** eval fixture 006 (rename-callers) scores `command-hook` or `prompt-hook`, NOT `claude-md-note`.
3. **Baseline:** both gemma4 and Haiku baselines rerun and committed at `evals/results/2026-05-22-v0.3-gemma.json` and `evals/results/2026-05-22-v0.3-haiku.json`. Both deltas vs v0.2 documented in CHANGELOG.
4. **Session lifecycle:** after a session, an archived `telemetry.<YYYY-MM-DD-HHMMSS>.jsonl` exists; fresh empty `telemetry.jsonl` is created; if `SELF_IMPROVING_CLAUDE_AUTO_COLLECT=true` was set, `candidates.jsonl` contains pattern-matched entries.
5. **Feedback:** invoking `/improve "the foo-hook just blocked something legit"` on a project with that hook installed appends a row to `feedback.jsonl` and modifies (does not duplicate) the hook entry.
6. **Uninstall:** `python3 .../uninstall.py --project <path>` removes all sentinel entries, deletes generated scripts, confirms before destructive action.
7. **README:** publishable — clear hero pitch, install in <2 minutes, trust + privacy + security sections, link to design docs. A first-time visitor can install and try the plugin without messaging the maintainer.
8. **Anthropic-marketplace PR materials:** `docs/anthropic-marketplace-pr.md` exists with a draft PR body and validated schema-compliance.

---

## 8. Open implementation questions

- Whether `@`-mentions resolve `../shared/...` paths from inside a skill directory — probe in Task 1. If no, fall back to inline duplication.
- Exact placement of the SELF_IMPROVING_CLAUDE_AUTO_COLLECT env var in user settings — top-level `env: {...}` or under a plugin-specific block. Pick whichever Claude Code's settings loader supports.
- Whether `claude plugin install` always-pulls from marketplace or can install from a local directory — affects whether `marketplace add /local/path` then `install` works, or if we need a different local-install instruction.

These are resolved during implementation, not blockers for the spec.
