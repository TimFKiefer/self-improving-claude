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

## 7. Implications for `self-improving-claude`

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
