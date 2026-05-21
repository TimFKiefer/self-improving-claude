# Plugins and Skills

Source: general Claude Code knowledge plus what's observable from this very machine's plugin layout (see `~/.claude/plugins/`). **The course material we have so far does not cover plugin structure or skill format in depth — this is the biggest documentation gap and the section most worth augmenting with official course excerpts.**

> **Why this matters:** the entire deliverable is a Claude Code **plugin** that contains a **skill** plus two **slash commands** plus a **hook**. We need to know the file layout that makes that work.

---

## 1. What a plugin is (working definition)

A Claude Code plugin is a self-contained directory that bundles one or more of:

- **Skills** — markdown files that get auto-discovered and made available via the `Skill` tool.
- **Slash commands** — markdown files that become user-typeable `/<name>` commands.
- **Hooks** — scripts (registered through the plugin's settings) that fire on PreToolUse / PostToolUse / etc.
- **Other assets** — reference docs, helper scripts, manifests.

Plugins live under `~/.claude/plugins/` once installed. Users install them either via a marketplace command or by dropping the directory in place.

> **🔍 Gap to fill from the course / official docs:**
> - Exact filename and schema of the plugin manifest (likely `plugin.json` or similar)
> - How the bundled `settings.json` (with hooks) is composed with user-level settings
> - Whether plugin hooks are auto-registered or require the user to add them to their settings
> - The marketplace install command and how plugin versions are pinned
> - Whether plugin slash commands live in a `commands/` subdirectory or are declared in the manifest

---

## 2. What a skill is (working definition)

A skill is a Markdown file (conventionally `SKILL.md`) with YAML frontmatter, designed to be:

- **Auto-discovered** — Claude Code scans known skill directories at session start and shows available skills.
- **Lazily activated** — Claude reads the full body of a skill only when it's invoked (via the `Skill` tool); before that, only the frontmatter `description` is visible.
- **Composable** — skills can reference other files (`@`-mentions) and the body becomes the working instruction set when invoked.

### Frontmatter shape (observed)

```yaml
---
name: short-kebab-slug
description: One-line summary describing when this skill applies. Used by the model to decide whether to invoke.
---

Body in Markdown. Becomes the active instructions once invoked.
```

### Where skills live

| Path | Scope |
|---|---|
| `~/.claude/skills/<name>/SKILL.md` | User-level, machine-wide |
| `<plugin>/skills/<name>/SKILL.md` | Bundled with a plugin |
| `.claude/skills/<name>/SKILL.md` | Project-level (less common) |

A skill directory can also contain helper files (`references/`, `examples/`, child markdown files) that the body references with `@<relative-path>`.

> **🔍 Gap to fill from the course / official docs:**
> - Exact schema for the `metadata:` block in frontmatter (some skills use it, e.g. `metadata: { type: feedback }`)
> - Whether skills must be in a directory or whether a single `SKILL.md` at the right path works
> - How a plugin declares its skills to the loader — manifest or convention-based?
> - The activation rules: which skills are loaded by default, which require explicit `Skill` invocation
> - Whether skill descriptions can include trigger keywords or are purely free-text

---

## 3. Slash commands inside a plugin

Already covered in `slash-commands-and-claude-md.md` for the project case (`.claude/commands/<name>.md`). The plugin-internal case is similar: a `commands/` directory inside the plugin contains the same `<name>.md` files.

> **🔍 Gap:** confirm with course material whether plugin-shipped slash commands are auto-registered (just by being in `commands/`) or whether the plugin manifest enumerates them. Most likely auto, but worth confirming.

---

## 4. Hooks inside a plugin

Two patterns are plausible (need course confirmation):

**Pattern A — declarative.** The plugin manifest lists hooks; on install, the relevant entries are merged into the user's `settings.json` (with path resolution to the plugin's directory).

**Pattern B — instructional.** The plugin's `commands/improve-init.md` is responsible for installing the bundled telemetry hook into the user's `settings.json` on first run. This puts more code in the skill but means the plugin is opt-in per-project.

For `self-improving-claude` Pattern B is attractive because it pairs cleanly with `/improve-init` as the "first-time setup" gesture — the user already expects work to happen then.

> **🔍 Gap:** confirm which pattern Claude Code plugins actually use, or whether both are supported.

---

## 5. Proposed plugin layout for `self-improving-claude`

Based on the above, here's a tentative directory layout. **Treat as a working hypothesis** — finalize once we have the plugin-anatomy course content or official docs.

```
self-improving-claude/
├── plugin.json                          ← manifest (name, version, entry points)
├── commands/
│   ├── improve.md                       ← /improve (reactive)
│   └── improve-init.md                  ← /improve-init (proactive)
├── skills/
│   └── self-improving-claude/
│       ├── SKILL.md                     ← the orchestration skill
│       └── references/
│           ├── hooks-and-sdk.md         ← distilled from docs/knowledge/
│           ├── tools-reference.md
│           ├── settings-and-permissions.md
│           └── slash-commands-and-claude-md.md
├── hooks/
│   └── telemetry.py                     ← the bundled PostToolUse logger
├── settings.example.json                ← template with $PWD placeholders
├── scripts/
│   └── init-plugin.js                   ← resolves $PWD into a real settings entry
├── README.md
└── LICENSE
```

Why each piece:

- **`commands/`** — slash commands users type. Both are thin: they invoke the skill.
- **`skills/self-improving-claude/SKILL.md`** — the orchestrator. Reads the references for grounding when drafting hooks. Handles approval loop, file writes, rewind instruction.
- **`skills/.../references/`** — the distilled knowledge base that ships *inside* the plugin. Same content as `docs/knowledge/` but trimmed to "what the LLM needs at run time," not the full design rationale. Loaded with `@` mentions from the SKILL body.
- **`hooks/telemetry.py`** — the bundled `PostToolUse: "*"` logger.
- **`settings.example.json` + `scripts/init-plugin.js`** — the `$PWD` pattern, so the telemetry hook can be registered with an absolute path generated at install time.

---

## 6. Open implementation questions

Driven by the gaps above:

1. **Does the plugin auto-install its telemetry hook on first activation, or only on `/improve-init`?** Hinges on plugin-hook installation semantics.
2. **Can the SKILL.md `@`-reference `references/*.md` files in its own directory?** Strongly expected yes, but worth confirming.
3. **Versioning** — when the plugin updates its bundled hook script, does the user's `settings.json` need updating? Or does the plugin use a stable wrapper path?
4. **Uninstallation** — how does a user fully remove the plugin including any hooks it installed into their project's `settings.json`?

---

## 7. What to feed in next (request to user)

The single highest-value addition to `docs/knowledge/` right now would be:

- **The plugin section of the Anthropic *Claude Code* course** — manifest format, install command, hooks/skills registration semantics.
- **The skill section of the course** — frontmatter schema, activation rules, the `references/` convention.
- (Lower priority) Real plugin examples (community or first-party) to confirm conventions.

Once we have those, the working hypotheses in this document become concrete spec inputs, and we can move from design to implementation plan with confidence.
