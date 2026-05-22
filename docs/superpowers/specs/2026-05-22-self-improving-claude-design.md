# self-improving-claude — Design Spec

**Status:** Approved design (2026-05-22). Implementation plan to follow via `writing-plans`.

**Knowledge base:** `docs/knowledge/` (agentic patterns, evals, hooks/SDK, plugins/skills, prompt engineering, settings/permissions, slash commands, tools reference).

---

## 1. Problem and goal

Claude Code is powerful by default, but every project has idiosyncratic footguns the model keeps tripping over — the wrong test command, an off-limits directory, a destructive shell pattern, a missing migration step. Today, users encode these rules manually after the damage is done.

**Goal:** ship a Claude Code plugin that converts observed footguns into installed hooks the moment they're noticed, with explicit per-hook user approval. Move project-specific knowledge from the prompt (fragile) to the harness (deterministic, mandatory).

**Non-goals (v0.x):** automatic chat rewind, background daemons, hook template library, MCP integration, CI integration.

---

## 2. User-visible surface

| Surface | What it does |
|---|---|
| `/improve` | Reactive. Uses the current chat as primary input (the bug is in scrollback). Proposes targeted hooks for what just happened. |
| `/improve-init` | Proactive. Reads project code + past session transcripts + the bundled telemetry log. Proposes a baseline guardrail set. |
| (Bundled) telemetry hook | `PostToolUse: "*"`. Logs `{tool, ts, summarized_args, outcome}` JSONL to `.claude/self-improving-claude/telemetry.jsonl`. Args summarized, no raw secrets. |

Both commands accept free-text `$ARGUMENTS`. The skill routes on the shape of input: empty (default mode), directive ("add a rule that prevents X"), or feedback ("the foo-hook just blocked something legit").

Every run ends with an explicit close-out message:

> *"N hook(s) installed at `.claude/hooks/` and registered in `.claude/settings.json`. Hooks load at session start, so to activate them: type `exit` then `claude` to restart. In the fresh session, press ESC twice and pick the message where you ran /improve to remove this conversation's detour."*

---

## 3. Architecture

`self-improving-claude` is a Claude Code plugin. It runs entirely inside the user's existing Claude Code session — no separate API key, no SDK call from outside. The orchestration skill is a **workflow** (sequence is fixed: route → inspect → propose → approve → write → close out) containing a few **agentic islands** (the hook-drafting step is genuinely creative; an evaluator-optimizer mini-loop polishes its output).

### 3.1 Plugin layout

```
self-improving-claude/
├── .claude-plugin/
│   └── plugin.json
├── skills/
│   ├── improve/SKILL.md                          (user-invoked — /improve)
│   ├── improve-init/SKILL.md                     (user-invoked — /improve-init)
│   └── self-improving-claude/
│       ├── SKILL.md                              (model-invoked — shared orchestrator)
│       └── references/
│           ├── hook-patterns.md
│           ├── tools-reference.md
│           ├── settings-merge.md
│           ├── prompt-rubric.md
│           └── examples.md
├── hooks/
│   └── hooks.json                                (registers the bundled telemetry hook)
├── scripts/
│   └── telemetry.py                              (the telemetry hook script)
├── evals/
│   ├── dataset.json
│   ├── fixtures/<id>/                            (per-test fixtures)
│   ├── grade.py
│   └── run.py
├── README.md
└── LICENSE
```

### 3.2 Plugin manifest (`.claude-plugin/plugin.json`)

```json
{
  "name": "self-improving-claude",
  "version": "0.1.0",
  "description": "Turns the bugs you just saw into the hooks that prevent the next ones — a Claude Code plugin that uses /improve and /improve-init to convert observed footguns into per-project hooks, with explicit per-hook user approval.",
  "author": {
    "name": "Tim Kiefer",
    "email": "tim.f.kief@gmail.com"
  },
  "license": "MIT",
  "keywords": ["claude-code", "hooks", "self-improving", "guardrails", "code-quality"]
}
```

`hooks` field is omitted — defaults to `./hooks/hooks.json`. Skills are auto-discovered under `skills/`. No `commands/` directory; slash commands ride the modern skill format.

### 3.3 The three skills

**`skills/improve/SKILL.md`** — user-invoked. Frontmatter:

```yaml
---
name: improve
description: Reactive. Run after you see Claude do something you don't want again. Uses the current chat context to propose hooks that would have prevented it.
argument-hint: [optional directive or feedback in quotes]
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
---
```

Body: a workflow that primes the orchestrator skill with `mode=reactive` and the chat-context source.

**`skills/improve-init/SKILL.md`** — user-invoked. Frontmatter mirrors above with a different `description` and `argument-hint`. Body primes the orchestrator with `mode=proactive` and the code+telemetry input source.

**`skills/self-improving-claude/SKILL.md`** — model-invoked. The actual workflow. Both user-invoked skills hand off to this one. It encapsulates:

1. Route on `$ARGUMENTS` (default / directive / feedback).
2. Inspect current state of `.claude/settings.json`, `.claude/hooks/`, the telemetry log, the project's `CLAUDE.md`.
3. Identify candidate problems.
4. For each candidate, decide on the right form: `permissions.deny` rule, prompt-based hook, command hook, or `CLAUDE.md` note.
5. Draft → self-critique (evaluator-optimizer, capped at 2 retries) → render diff → ask user → write file or skip.
6. Defensive merge into `.claude/settings.json`.
7. Print close-out message (restart + rewind).

Body uses the prompt-engineering practices from `docs/knowledge/prompt-engineering.md`: imperative rubric, XML tags around interpolated content, 3–5 worked examples, every step a verb.

### 3.4 The bundled telemetry hook

`hooks/hooks.json`:

```json
{
  "description": "self-improving-claude — passive telemetry for /improve-init",
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/telemetry.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

`scripts/telemetry.py` reads JSON from stdin, summarizes, appends to `${CLAUDE_PROJECT_DIR}/.claude/self-improving-claude/telemetry.jsonl`. Output format:

```jsonl
{"ts": "2026-05-22T14:33:01Z", "tool": "Bash", "args_summary": "pnpm test", "outcome": {"exit_code": 1, "stderr_head": "ENOENT..."}}
```

Summarization rules (encoded in `telemetry.py` and tested):

| Tool | What we log |
|---|---|
| `Bash` | First 80 chars of `command`; `exit_code` and first 200 chars of `stderr` if non-zero |
| `Read` / `Write` / `Edit` / `MultiEdit` | `file_path` only (path, no content) |
| `Glob` / `Grep` | `pattern` only (redacted if matches known secret prefixes like `SECRET_`, `API_KEY`, etc.) |
| `WebFetch` | `url` host only |
| `Task` | `subagent_type` only |
| `TodoWrite` | counts only (n_todos), not content |
| Everything else | tool name + timestamp |

Hard rule: never log file contents, full URLs with query strings, raw env values, or full multi-line bash output.

---

## 4. Data flow

### 4.1 `/improve` (reactive)

```
User invokes /improve (optionally with directive/feedback in quotes)
  │
  ├── Route on $ARGUMENTS
  │     ├── empty → analyze recent chat for most-recent observable footgun
  │     ├── feedback → mark target hook, refine, no new proposals
  │     └── directive → target named problem, single proposal
  │
  ├── Inspect current state
  │     ├── Read .claude/settings.json (parse, capture)
  │     ├── List .claude/hooks/*
  │     ├── Read .claude/self-improving-claude/telemetry.jsonl (recent N rows)
  │     └── Read CLAUDE.md (for context awareness)
  │
  ├── Identify candidate problem(s)
  │     └── Pull from current chat scrollback as primary signal
  │
  ├── For each candidate (capped at 5):
  │     ├── Decide form: permissions.deny | prompt-hook | command-hook | CLAUDE.md note
  │     ├── Draft hook (or rule, or note)
  │     ├── Self-critique against prompt-rubric.md (≤ 2 retries)
  │     ├── Validate syntax (bash -n / python -m py_compile / json parse)
  │     ├── Render diff vs current settings.json + new file contents
  │     └── Prompt user: approve / reject / edit
  │
  ├── For each approved candidate:
  │     ├── Write script file to .claude/hooks/<slug>.{sh|py}
  │     └── Key-level merge into .claude/settings.json with name sentinel
  │
  └── Close out
        └── "N hooks installed. Restart Claude Code: exit && claude. Then ESC-ESC-rewind."
```

### 4.2 `/improve-init` (proactive)

Same orchestrator, different inputs:

- Primary signal: project code samples (CLAUDE.md, package.json, README, sampled source files) + `~/.claude/projects/<project>/` past transcripts + telemetry log.
- Typically proposes more candidates (still capped at 5 per run; user can re-run for more).
- No chat-scrollback dependency.

---

## 5. Generated hook conventions

### 5.1 Form selection

Generated guardrails come in four flavors, in order of preference:

1. **`permissions.deny` rule** — preferred when a single glob covers all relevant tools. E.g. `"Read(**/.env)"`. Cheapest, fastest, uniform.
2. **Prompt-based hook** (`"type": "prompt"`) — preferred when the check is reasoning-heavy and the event supports it (`PreToolUse`, `Stop`, `SubagentStop`, `UserPromptSubmit`). Cheaper to author and to audit than command hooks.
3. **Command hook** (`"type": "command"`) — used when the check is fast and deterministic (e.g. "run prettier on every Write"), or when the event doesn't support prompt-type hooks (e.g. `PostToolUse`).
4. **`CLAUDE.md` note** — soft preference, no enforcement. Offered when the rule is taste-level ("prefer `pnpm` over `npm`") rather than safety-level. Skill suggests the user type a `# ...` line rather than writing to `CLAUDE.md` directly.

The orchestrator's rubric (in `references/prompt-rubric.md`) explicitly biases proposals down this list — only fall to a heavier form when the lighter one can't do the job.

### 5.2 Command hook conventions

Every generated command hook script begins with the standard stdin→JSON→branch boilerplate from `docs/knowledge/tools-reference.md`. Paths use `${CLAUDE_PROJECT_DIR}` for portability. Exit codes follow the documented semantics: 0 = allow, 2 = block (PreToolUse) / feed-back-to-Claude (PostToolUse).

Generated scripts max ~60 lines. Anything longer = the rubric forces a redraft.

### 5.3 settings.json sentinel

Every plugin-installed hook entry includes a `"name"` field:

```json
{
  "matcher": "Bash",
  "hooks": [
    {
      "name": "self-improving-claude/block-pnpm-test-watcher",
      "type": "command",
      "command": "bash ${CLAUDE_PROJECT_DIR}/.claude/hooks/block-pnpm-test-watcher.sh"
    }
  ]
}
```

The `name` field acts as a recognizable marker for future removal/edit (JSON has no comments). Convention: `self-improving-claude/<descriptive-kebab-slug>`.

---

## 6. settings.json merge strategy

`references/settings-merge.md` is the runtime reference. Algorithm:

1. **Read** `.claude/settings.json`. If missing, treat as `{}`.
2. **Parse** as JSON. If parse fails, surface error to user and abort (no destructive overwrite).
3. **Merge key-level**:
   - `hooks.PreToolUse` / `hooks.PostToolUse` / etc. — append entries; do not replace arrays.
   - `permissions.deny` — append new rule only if not already present (deduplicate by string equality).
   - Every other top-level key — leave untouched.
4. **Conflict detection** — if a new matcher/path overlaps with an existing entry, surface the conflict in the approval flow: user picks `keep both / replace existing / skip`.
5. **Pretty-print** with stable 2-space indent so user-side `git diff` is readable.
6. **Sentinel marker** — every plugin-added entry carries `"name": "self-improving-claude/..."`.

Same merge logic applies to `.claude/settings.local.json` when the user opts for personal scope (default is the committed file).

---

## 7. Eval methodology

Per `docs/knowledge/eval-methodology.md`:

- `evals/dataset.json` — 5 entries in v0.2, grow toward 10–20 as the plugin matures. Each entry: `{id, trigger, user_args, fixture, planted_problem, expected_hook_traits}`.
- `evals/fixtures/<id>/` — project files, planted chat transcript, telemetry sample.
- `evals/grade.py` — code-grader (syntax validity, sentinel presence, JSON validity of generated settings.json, valid event/matcher) + model-grader (Haiku-class call with strengths/weaknesses/reasoning/score JSON output).
- `evals/run.py` — runs each entry through the skill in a sandboxed Claude Code environment, collects proposed hooks, grades them, writes per-entry + average scores.
- Scores committed to git; SKILL.md changes are paired with score deltas in PRs.

Eval is a guardrail, not a green light. Paired with hand-written integration tests on 2–3 canonical generated hooks (load into Claude Code sandbox, trigger matching tool, verify behavior).

---

## 8. The orchestrator skill's prompt structure

`skills/self-improving-claude/SKILL.md` body assembles, at runtime:

```
<role>
You are the orchestrator behind /improve and /improve-init. Your job is to
convert observed Claude Code behavior into installed, per-project guardrails
with explicit user approval at every step.
</role>

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

<mode>{reactive|proactive}</mode>
<user_directive>{$ARGUMENTS or empty}</user_directive>
<recent_chat>{...}</recent_chat>          (reactive only)
<project_snapshot>{...}</project_snapshot> (proactive only)
<telemetry_excerpt>{...}</telemetry_excerpt> (proactive only, plus reactive if relevant)
<existing_hooks>{...}</existing_hooks>
<existing_permissions>{...}</existing_permissions>

<procedure>
1. Route on user_directive and mode.
2. Identify up to 5 candidate problems.
3. For each, choose the lightest viable form (permissions.deny > prompt-hook > command-hook > CLAUDE.md note).
4. Draft. Self-critique against rubric. Revise (cap 2).
5. Validate syntax. Render diff. Ask user.
6. Write approved files. Merge approved entries into settings.json.
7. Print close-out (restart + rewind instructions).
</procedure>
```

The rubric (`references/prompt-rubric.md`) lists the qualities every proposal must satisfy: specific (not hypothetical), binds to exactly one event with a precise matcher, ≤ 60 LOC for scripts, one-sentence rationale that names the bug, sentinel `name` field, lightest-viable-form check explicit.

---

## 9. MVP slicing

### v0.1.0 — "it generates and installs hooks"

- Plugin manifest, skills layout, README, LICENSE.
- `skills/self-improving-claude/SKILL.md` complete (orchestrator).
- `skills/improve-init/SKILL.md` working end-to-end.
- `references/*.md` populated (distilled from `docs/knowledge/`).
- `hooks/hooks.json` + `scripts/telemetry.py` shipped and tested.
- Defensive `settings.json` merge tested with 5+ edge-case fixtures.
- Manual install + smoke test on 2–3 real projects.

Exit criteria: a user can install the plugin, run `/improve-init`, see a sensible set of proposals, approve some, restart, and find them firing.

### v0.2.0 — "reactive mode and measurement"

- `skills/improve/SKILL.md` (reactive mode).
- `$ARGUMENTS` routing across both commands.
- `evals/` with 5 entries + code-grader + model-grader; first scored baseline committed.
- Generated hooks default to `"type": "prompt"` where the event supports it.

### v0.3.0+ — polish

- Feedback channel formalized: `/improve "the foo-hook blocked something legit"` logs to `.claude/self-improving-claude/feedback.jsonl`; next run reads it.
- Conflict UX (keep/replace/skip) for matcher overlaps.
- 10–20 eval entries; documented score thresholds.
- (Stretch) auto-rewind investigation.

---

## 10. Critical risks and mitigations

| Risk | Mitigation |
|---|---|
| Generated hook is malicious or buggy (arbitrary LLM-written code) | Per-hook diff + explicit approval; no auto-install. Sentinel marker for easy removal. Syntax validation before approval prompt. |
| Telemetry log leaks secrets | Strict summarization rules in `telemetry.py`; unit-tested redaction; never log content. Hard rule: no full bash stderr, no file contents, no full URLs with query strings. |
| Clobbering user's existing `settings.json` | Key-level merge, never overwrite. Refuse to write on parse failure. Conflict detection prompts user. |
| Skill prompt regression invisible | `evals/` with code+model graders. SKILL.md PRs include score delta. |
| Hooks loaded only at session start (user confusion) | Close-out message explicitly says to restart. Re-stated in README. |
| Prompt-based hooks fire model calls on every tool use (cost / latency) | Bias rubric toward `permissions.deny` and command hooks for hot-path checks. Prompt hooks reserved for genuinely reasoning-heavy gates. |
| Plugin updates break user's previously-installed hooks | Hooks live as files in the user's project, not in the plugin. Plugin updates don't touch them. The plugin only ships the orchestrator + telemetry. |

---

## 11. Open questions deferred to implementation

- Exact ergonomics of the per-hook approval UI in chat (Markdown-rendered diff? code blocks? embedded `AskUserQuestion`-style choices?). Decided during v0.1 hands-on.
- Whether the orchestrator skill is invoked by `Skill` tool from inside the user-invoked skills, or whether the workflow is inlined into each user-invoked skill body. Evaluated during v0.1 implementation; pick whichever yields a cleaner, more testable structure.
- Whether `evals/` runner needs the Claude Agent SDK (separate API call) or can drive a Claude Code subprocess in headless mode. Investigate when wiring `evals/run.py`.

---

## 12. Out of scope (v0.x)

- Automatic chat rewind (user does ESC-ESC manually).
- Background daemons / continuous learning.
- Template library for generated hooks (purely freeform with rubric grounding).
- Built-in hook-disable UI (managed by editing/deleting files; sentinel `name` makes them findable).
- CI integration.
- MCP server form factor.
- Cross-machine telemetry aggregation.

---

## 13. Acceptance — what "done" means for v0.1

1. Plugin installs cleanly from a local path (either via Claude Code's marketplace install flow or by dropping the directory into `~/.claude/plugins/` and registering it — exact command resolved during v0.1 implementation).
2. `/improve-init` runs without errors on three different sample projects (Node, Python, and a generic shell repo).
3. At least one proposed hook on each sample project is sensible enough to approve.
4. After approve + restart, the approved hook fires when its trigger condition is met.
5. The telemetry hook produces JSONL entries on a fresh session, with no entry containing raw bash output, file content, or recognizable secrets.
6. README walks a new user from install → first `/improve-init` → restart → verification in ≤ 5 minutes.
