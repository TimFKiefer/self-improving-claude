# Plugins and Skills

Source: observable from the repo's actual `plugin/` tree, `plugin/.claude-plugin/plugin.json`,
`.claude-plugin/marketplace.json`, `plugin/hooks/hooks.json`, `plugin/skills/*/SKILL.md`,
`plugin/skills/_shared/`, `CHANGELOG.md`, and the skill references under
`plugin/skills/improve/references/`.

---

## 1. What a plugin is

A Claude Code plugin is a self-contained directory bundling skills, a manifest, and
optionally hooks. Once installed, the plugin's skills become available as slash commands
(one skill = one slash command) and its bundled hooks fire on configured events.

Plugins are installed from a **marketplace** — a repository whose root contains a
`.claude-plugin/marketplace.json` file. Install sequence:

```bash
claude plugin marketplace add github:<owner>/<repo>   # register the marketplace
claude plugin install self-improving-claude            # install a named plugin from it
```

For local dev or per-session use, pass the plugin directory directly:

```bash
claude --plugin-dir <repo>/plugin
```

---

## 2. Real layout — `self-improving-claude`

```
<repo>/
├── .claude-plugin/
│   └── marketplace.json            ← root marketplace declaration
└── plugin/                         ← plugin root (passed to --plugin-dir)
    ├── .claude-plugin/
    │   └── plugin.json             ← plugin manifest
    ├── hooks/
    │   └── hooks.json              ← bundled hook declarations
    ├── scripts/
    │   └── telemetry.py            ← telemetry hook script (PostToolUse / Notification / etc.)
    └── skills/
        ├── _shared/                ← single-source (generator inputs)
        │   ├── orchestrator-procedure.md
        │   ├── preambles/
        │   │   ├── improve.md
        │   │   └── improve-init.md
        │   └── references/
        │       ├── hook-patterns.md
        │       ├── settings-merge.md
        │       ├── tools-reference.md
        │       ├── prompt-rubric.md
        │       └── examples.md
        ├── improve/
        │   ├── SKILL.md            ← generated; do NOT hand-edit
        │   └── references/         ← generated copies of _shared/references/
        ├── improve-init/
        │   ├── SKILL.md            ← generated; do NOT hand-edit
        │   └── references/         ← generated copies of _shared/references/
        └── improve-uninstall/
            └── SKILL.md            ← standalone; not generated
```

There is **no `commands/` directory**. Each `SKILL.md` IS the slash command — the skill's
`name` frontmatter field determines the `/<name>` command users type.

---

## 3. Manifests

### Plugin manifest — `plugin/.claude-plugin/plugin.json`

Declares the plugin identity. Current fields:

```json
{
  "name": "self-improving-claude",
  "version": "0.3.4",
  "description": "...",
  "author": { "name": "...", "email": "..." },
  "license": "MIT",
  "keywords": ["claude-code", "hooks", "self-improving", "guardrails", "code-quality"]
}
```

### Marketplace manifest — `.claude-plugin/marketplace.json`

Declares the marketplace and the plugins it offers. Real fields from the repo:

```json
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "self-improving-claude",
  "description": "Marketplace for the self-improving-claude plugin ...",
  "owner": { "name": "...", "email": "..." },
  "plugins": [
    {
      "name": "self-improving-claude",
      "description": "...",
      "author": { "name": "...", "email": "..." },
      "category": "productivity",
      "source": "./plugin"
    }
  ]
}
```

Key fields: `plugins[].name` is what you pass to `claude plugin install`; `plugins[].source`
is the relative path to the plugin root within the repo.

---

## 4. Skills

A skill is a Markdown file (`SKILL.md`) with YAML frontmatter. The skill's frontmatter
`name` field determines its slash command (`/improve`, `/improve-init`,
`/improve-uninstall`). Skills are lazily activated — only the `description` is visible
until the skill is invoked via the `Skill` tool or typed as a slash command.

### Frontmatter fields (observed)

```yaml
---
name: improve
description: One-line summary — used by the model to decide when to invoke.
argument-hint: [optional hint shown in the / menu]
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, Skill, AskUserQuestion]
---
```

### `@`-reference resolution

A skill body can `@`-reference files in its **own** `references/` subdirectory:

```markdown
<rubric>
@references/prompt-rubric.md
</rubric>
```

**`@../` (cross-directory) mentions do NOT resolve.** This was confirmed as a hard
limitation in v0.3.0 (CHANGELOG): the probe for `@`-mention resolution outside the skill
directory failed. That failure is why `improve` and `improve-init` each carry their own
`references/` copies rather than sharing a single set — the generator in
`scripts/sync_skills.py` is the fix.

---

## 5. Skill single-sourcing (`plugin/skills/_shared/`)

`improve` and `improve-init` share identical orchestrator procedure text and reference
files. The `_shared/` directory is the **single source of truth**:

- `_shared/orchestrator-procedure.md` — the shared Steps 1–10 body
- `_shared/preambles/<skill>.md` — per-skill preamble (mode/inputs section)
- `_shared/references/*.md` — the 5 reference files

`scripts/sync_skills.py` generates each skill's `SKILL.md` (`preamble + procedure`) and
copies `references/` into place. The generated files are byte-for-byte reproducible —
regenerating an already-correct tree is a no-op.

**Edit `_shared/` sources only. Never hand-edit the generated `SKILL.md` or `references/`
files under `improve/` or `improve-init/`.** Run `bash scripts/install-hooks.sh` once to
install a pre-commit hook (`scripts/sync_skills.py --check`) that blocks commits when the
generated files drift from `_shared/`.

---

## 6. Plugin hook registration

Plugin hooks are **NOT auto-registered on plugin install**. There are two distinct
mechanisms:

### 6a. Bundled telemetry hooks — `plugin/hooks/hooks.json`

The plugin ships a `hooks.json` declaring multi-event telemetry hooks (PostToolUse,
Notification, PreCompact, SessionStart, SessionEnd). These use `${CLAUDE_PLUGIN_ROOT}` for
portable paths to `scripts/telemetry.py`. The mechanism by which Claude Code reads
`hooks.json` at plugin load time is not fully documented in the repo sources — treat the
presence of this file as the declaration mechanism and `${CLAUDE_PLUGIN_ROOT}` as the
portability pattern.

Example entry from `plugin/hooks/hooks.json`:

```json
{
  "name": "self-improving-claude/telemetry",
  "type": "command",
  "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/telemetry.py",
  "timeout": 5
}
```

### 6b. Project guardrail hooks — installed by `/improve-init`

The project-level guardrail hooks (the plugin's core output) are written into the project's
`.claude/settings.json` by the `/improve-init` or `/improve` skills at run time, one hook
at a time, with explicit per-hook user approval. These use `${CLAUDE_PROJECT_DIR}` for
portable paths to generated scripts in `.claude/hooks/`.

The skill itself performs the installation rather than the plugin declaring it statically —
pairing cleanly with `/improve-init` as the first-time setup gesture (per-project opt-in
rather than auto-registration on plugin install).

---

## 7. Hook runtime facts

### `type: "prompt"` hook contract

A prompt-based hook (`"type": "prompt"`) asks the LLM to evaluate each invocation. It
returns a JSON decision rather than running a shell script. The decision key is
`permissionDecision` (`"deny"` | `"allow"` | `"ask"`) plus an optional reason. Supported
only on events that can block: PreToolUse, Stop, SubagentStop, UserPromptSubmit (not
PostToolUse). Costs a model call per fire.

```json
{
  "type": "prompt",
  "prompt": "Evaluate if this Bash command is safe. Deny if it would push to main ...",
  "timeout": 30
}
```

### Advanced JSON hook stdout (command hooks)

Beyond exit codes, a command hook can print a JSON object to stdout to control the
decision — the structured alternative to exit-2 + stderr for blocking. The key from the
source is `permissionDecision` (seen in the hook-patterns table as the PreToolUse block
mechanism alongside exit 2). The exact JSON schema for stdout decisions is referenced in
`hook-patterns.md` but not spelled out there beyond the `permissionDecision: deny`
example.

### Stop hook — force-continue and `stop_hook_active`

A Stop hook can refuse turn-end (force the agent to continue). The Stop event stdin
includes `"stop_hook_active": false` (or `true` when a Stop hook is already running) —
hooks must guard against recursive invocation by checking this field and exiting cleanly
when `stop_hook_active` is `true`.

Stop stdin shape (from `hooks-and-sdk.md`):

```json
{
  "session_id": "af9f50b6-...",
  "transcript_path": "...",
  "hook_event_name": "Stop",
  "stop_hook_active": false
}
```

### Portable path env vars

| Variable | Expands to |
|---|---|
| `${CLAUDE_PLUGIN_ROOT}` | The plugin's install directory — use for scripts shipped *by* the plugin (e.g. `telemetry.py`) |
| `${CLAUDE_PROJECT_DIR}` | The user's project root — use for scripts written *into* a project (e.g. generated `.claude/hooks/*.py`) |

Source: `hook-patterns.md` "Portable paths" section and `settings-merge.md` examples.

### Exit codes (command hooks)

| Code | Meaning |
|---|---|
| `0` | Allow / proceed |
| `2` | Block (PreToolUse) or feed stderr back to Claude as information (PostToolUse) |
| Other | Non-blocking error |

### PostToolUse limitation

PostToolUse exit-2 feeds the model *information*, not a hard imperative — the model can
summarize and stop instead of acting on the feedback. For genuine "after X, ensure Y"
enforcement, prefer `permissions.deny`/`permissions.ask` when a glob fits, or use the
composed PostToolUse + Stop pattern (v0.4 roadmap item): paired hooks sharing a state
file, where the Stop hook re-verifies and blocks turn-end if findings persist.

---

## 8. `@../` non-resolution — why the single-source generator exists

CHANGELOG v0.3.0: "The probe for `@`-mention resolution outside the skill directory
FAILED, so the implementation took the inline duplication fallback — the 10-step
orchestrator procedure is now inlined in both `plugin/skills/improve/SKILL.md` and
`plugin/skills/improve-init/SKILL.md`, and references are duplicated in each skill's
`references/` directory."

The v0.4.0 branch introduced `scripts/sync_skills.py` to end that duplication: edits go
to `_shared/`, the generator propagates them, and the pre-commit hook (`--check`) prevents
drift from sneaking in.

---

## 9. What to keep in `hooks-and-sdk.md` vs here

- **`hooks-and-sdk.md`** — hook mechanics (exit codes, stdin shapes, event semantics, the
  Agent SDK, code quality / formatting patterns). Course-sourced, implementation-level.
- **`plugins-and-skills.md`** (this file) — plugin/skill structure, manifest schemas,
  registration mechanics, single-source workflow, the `@../` limitation. Repo-observable,
  architecture-level.
