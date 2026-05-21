# Slash Commands and `CLAUDE.md`

Source: Anthropic *Claude Code* course material. This is the reference for how custom slash commands work and how the `CLAUDE.md` system threads persistent instructions through every conversation. `self-improving-claude` ships **two** custom slash commands (`/improve`, `/improve-init`), so this knowledge is directly load-bearing.

---

## 1. Custom slash commands — folder structure

Claude Code ships built-in commands (`/help`, `/init`, `/memory`, `/hooks`, etc.) but you can add your own. The mechanism is just files in a folder:

```
<project root>/
└── .claude/
    └── commands/
        ├── audit.md
        ├── write_tests.md
        └── ...
```

Rules:

- Commands live in `.claude/commands/`.
- **Filename becomes the command name** — `audit.md` → `/audit`, `write_tests.md` → `/write_tests`.
- The file is a Markdown document. Its contents become the prompt Claude executes when the command is invoked.
- Claude Code picks up new commands automatically — **no restart needed**.

This is the same mechanism whether the commands live in a user's project or are shipped from a plugin (the plugin loader places the command files into the right spot during install).

---

## 2. Example — the audit command

A practical `audit.md` that hardens a Node project's dependencies:

```md
Audit this project for vulnerable dependencies and fix what's safe to fix:

1. Run `npm audit` to identify vulnerable packages.
2. Run `npm audit fix` to apply updates that don't require a major version bump.
3. Run the test suite (`npm test`) to confirm nothing broke.
4. Summarise what changed and flag anything that still has open advisories.
```

When the user types `/audit`, Claude treats this Markdown as the prompt and proceeds. The command is just a saved prompt with a name.

---

## 3. Arguments via `$ARGUMENTS`

Commands can be parameterised with the `$ARGUMENTS` placeholder. The user's text after the command name is substituted in.

`write_tests.md`:

```md
Write comprehensive tests for: $ARGUMENTS

Testing conventions:
* Use Vitest with React Testing Library
* Place test files in a __tests__ directory in the same folder as the source file
* Name test files as [filename].test.ts(x)
* Use @/ prefix for imports

Coverage:
* Test happy paths
* Test edge cases
* Test error states
```

Invocation:

```
/write_tests the use-auth.ts file in the hooks directory
```

`$ARGUMENTS` ends up as `"the use-auth.ts file in the hooks directory"`. Arguments don't have to be file paths — any free-text string works.

### Why this matters for `self-improving-claude`

Both our commands use this:

- `/improve` — `$ARGUMENTS` may be empty (full pass over the current chat context) **or** carry a directive (`/improve "block edits to migrations/*"`) **or** feedback (`/improve "the foo-hook just blocked something legit"`). The skill behind the command reads `$ARGUMENTS` and branches.
- `/improve-init` — same idea, with `$ARGUMENTS` letting the user scope the initial scan (e.g. `/improve-init "focus on the queries directory"`).

---

## 4. Why custom commands matter

| Benefit | What it means |
|---|---|
| **Automation** | Turn repetitive workflows into one keystroke. |
| **Consistency** | Same steps every time — no skipped instructions. |
| **Context** | Embed project-specific conventions in the prompt itself. |
| **Flexibility** | `$ARGUMENTS` makes one command serve many inputs. |

For us: every time the user wants to extend their guardrails, it's a single command. No memorising syntax, no copying snippets.

---

## 5. `CLAUDE.md` — persistent project memory

`CLAUDE.md` is a Markdown file that Claude Code **automatically includes in every request** for the project. It's effectively a system prompt for the project.

Two main purposes:

1. **Onboard Claude to the codebase** — important commands, architecture, coding style.
2. **Give Claude specific or custom instructions** — preferences, conventions, things to avoid.

Generated automatically by the `/init` command (which crawls the repo and writes a starter `CLAUDE.md`), but you can edit it freely afterward — directly in your editor, or by running `/memory` inside Claude Code to open it.

Changes apply to the **next** message — Claude re-reads it at the start of every conversation.

### Three locations Claude recognises

| File | Scope |
|---|---|
| `CLAUDE.md` | Project, **committed** — shared with the team. Created by `/init`. |
| `CLAUDE.local.md` | Project, **not committed** — your personal instructions for this project. |
| `~/.claude/CLAUDE.md` | **Global** — applies to every project on your machine. |

### Example custom instructions

If Claude is adding too many comments, add this to `CLAUDE.md`:

```
Use comments sparingly. Only comment complex code.
```

---

## 6. File mentions with `@`

Anywhere Claude reads text — in your prompts, or inside `CLAUDE.md` — you can reference a file with `@<path>` and that file's **contents are inlined** into the request.

### In prompts

```
How does the auth system work? @auth
```

Claude offers a list of `auth*` files, you pick one, and its contents are attached. Beats explaining file paths.

### In `CLAUDE.md`

This is where it gets powerful. You can pin reference files so they're always loaded:

```
The database schema is defined in the @prisma/schema.prisma file.
Reference it anytime you need to understand the structure of data stored
in the database.
```

Now every conversation has the schema in context. Claude can answer schema questions immediately without `Glob`-ing for the file first.

### Composing with `AGENTS.md`

If a repo already has an `AGENTS.md` for another tool, you don't need to duplicate it. Put `@AGENTS.md` on the **first line** of `CLAUDE.md` and Claude loads it first. Add Claude-specific additions below.

---

## 7. Other Claude Code surfaces worth knowing

Three small features the API course flagged that we should be aware of when designing the plugin:

### `#` — quick memory add

Typing `# <some instruction>` at any time during a Claude Code session prompts the user to add that line to `CLAUDE.md` (project, local, or user scope). It's the fastest way to capture a rule mid-conversation.

**Why it matters for us:** for soft-preference suggestions the plugin makes (the "this should be a `CLAUDE.md` note, not a hook" case), we could simply *tell the user* the exact `#`-formatted command to type. Cleaner than writing to `CLAUDE.md` ourselves.

### `/clear` — reset context

`/clear` wipes the current conversation history and resets context. The course flags this as the standard way to start fresh inside a long session without restarting the CLI.

**Why it matters for us:** in v1, `/improve` ends by instructing the user to ESC-ESC-rewind. `/clear` is an alternative cleanup option — coarser (loses *all* history, not just the `/improve` detour) but always available. Worth mentioning in the rewind-instruction message as a fallback.

### MCP integration in Claude Code

Claude Code has an **MCP client built in**, so users can connect MCP servers to extend Claude's tool set. Registration is one command:

```
claude mcp add <server-name> <command-to-start-server>
```

Real-world ecosystem includes things like `sentry-mcp` (pull error context), `playwright-mcp` (browser automation), `slack-mcp` (notifications), etc.

**Why it matters for us (and why it's mostly out of scope for v1):**

- **We don't need to be an MCP server.** Our delivery is a Claude Code plugin (commands + skill + hook), not an external service. MCP would be a different shape.
- **Generated hooks could integrate with MCP tools.** A `PostToolUse` hook could, for instance, log significant events to Slack via `slack-mcp`. Flag for later; not v1.
- **Users with MCP servers installed get a richer telemetry signal.** The bundled telemetry hook should log MCP-tool calls just like built-in tools — matcher `*` already covers this; we just need to be tolerant of unknown `tool_name` values in our analyzer.

---

## 8. Recommended Claude-Code-with-projects workflow

The course's most actionable workflow recommendation, applicable both to *how users should use the plugin* and to *how the SKILL itself should orchestrate*:

> **Feed context → Plan → Implement.** Before asking Claude to do something complex, point it at the relevant files first. Then ask for a plan (no code yet). Then ask for implementation.

A test-driven variant adds two extra steps:

> Feed context → Ask Claude to brainstorm test cases → Implement tests → Ask Claude to write code that passes them.

**Why it matters for us:**

- This is exactly the shape `/improve` should follow internally: *inspect environment* (feed context) → *propose hooks* (plan) → *write files* (implement).
- We should also document this as the **recommended way to use `/improve`** in the README: don't run `/improve` cold; first surface the bug by working on something, then `/improve` while the context is hot.

---

## 9. Implications for `self-improving-claude`

What the slash-command + `CLAUDE.md` system gives us, distilled into design implications:

1. **Two command files ship with the plugin:**
   - `commands/improve.md` — handles reactive in-chat mode. Reads `$ARGUMENTS` to detect directive vs feedback vs empty.
   - `commands/improve-init.md` — handles proactive full-pass mode. Reads `$ARGUMENTS` to allow scoping.
2. **The commands invoke the skill** — they're thin entry points. The bulk of the orchestration logic lives in the skill, which both commands reference. Keeps the commands' Markdown short and the logic single-sourced.
3. **`/improve` can also write to `CLAUDE.md`.** Some lessons aren't best expressed as a hook — they're soft preferences ("when editing this codebase, prefer `pnpm` not `npm`"). For those, the plugin can offer to append a line to `CLAUDE.md` instead of creating a hook. Per-suggestion the user picks: hook (hard rule) vs CLAUDE.md note (soft preference).
4. **Self-referencing knowledge inside the plugin.** Inside the plugin's bundled skill, we use `@` references to point at the curated reference docs we ship (the distilled hooks/SDK knowledge, the patterns library). That way the skill doesn't have to inline everything — Claude pulls them in on demand.
5. **`/memory` is the user's escape hatch.** When debugging the plugin or wanting to tune behavior, the user can open `CLAUDE.md` with `/memory` and see exactly what's accumulated there. We should write any plugin-added `CLAUDE.md` lines under a clearly-marked, easy-to-edit section.
6. **Don't fight `AGENTS.md`-style shared files.** If a project already has shared agent instructions, our `CLAUDE.md` additions should import them with `@AGENTS.md` rather than duplicate.
7. **Free-text `$ARGUMENTS` is the conversational surface.** We don't need fancy flag parsing — the skill reads the natural-language `$ARGUMENTS` and figures out intent. That keeps the UX simple.
