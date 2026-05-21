# Knowledge Base

Drop reference material here that should inform how `self-improving-claude` reasons about hooks.

Intended sources for the first pass:

- **Anthropic *Claude Code* course** — what hooks exist, how `settings.json` works, idiomatic skill/plugin patterns, examples of well-designed guardrails.
- **Claude Code official docs** — the canonical reference for hook events, slash commands, plugin structure.
- **Real examples from the wild** — community plugins, useful hook patterns, anti-patterns to avoid.

## Current contents

| File | What's in it | Confidence |
|---|---|---|
| `hooks-and-sdk.md` | All 9 hook types, configuration, `$PWD` absolute-path pattern, worked `.env`-blocking example, TypeScript-check and sub-Claude review patterns, Agent SDK install + minimal example. Closes with design implications. | **High** — direct from course material |
| `slash-commands-and-claude-md.md` | Custom slash commands (`.claude/commands/<name>.md`, `$ARGUMENTS`), `CLAUDE.md` persistent memory including `@`-mentions, plus the `#` quick-memory shortcut, `/clear`, Claude Code's built-in MCP client (`claude mcp add`), and the recommended Feed → Plan → Implement workflow. Closes with design implications. | **High** — direct from course material |
| `tools-reference.md` | The `tool_input` shape per built-in tool (Read, Write, Edit, Bash, Glob, Grep, WebFetch, WebSearch, Task, TodoWrite, etc.), the standard stdin envelope, common matcher patterns. The lookup table every generated hook needs. | **High** for shapes shown directly in course examples; **medium** for the others |
| `settings-and-permissions.md` | The rest of `settings.json` beyond hooks: the `permissions` system (allow/deny/ask rules), `env`, defensive write strategy for our plugin, when to prefer `permissions.deny` over a hook. | **Medium** — broadly-documented Claude Code basics, but specific edge cases worth verifying against official docs |
| `plugins-and-skills.md` | Working hypothesis for plugin and skill anatomy, the proposed file layout for `self-improving-claude`, and an explicit list of gaps where course material would help. | **Low-medium** — biggest knowledge gap, marked accordingly |
| `prompt-engineering.md` | The five techniques (clear/direct, specific, XML tags, examples, temperature) and how each applies to writing the SKILL.md. The SKILL is itself a prompt — these are how we make it produce well-crafted hooks. | **High** — direct from course material |
| `eval-methodology.md` | How to measure SKILL quality: the five-step eval workflow, dataset shape with planted-bug fixtures, code-based + model-based graders, when to use which, what evals *can't* tell us. The discipline that makes prompt iteration measurable. | **High** — direct from course material |
| `agentic-patterns.md` | Workflows vs agents, the four patterns (chaining, routing, parallelization, evaluator-optimizer), and "environment inspection" as a non-negotiable. Our SKILL is a workflow with a few agentic islands; this doc maps each pattern onto our flow. | **High** — direct from course material |

## Confidence convention

When a section is based on direct course excerpts, it's marked **(course material)**. When it's compiled from general Claude Code knowledge, it's flagged so we know to verify before depending on it. Sections that need course material to be authoritative are marked with **🔍 Gap to fill**.

## What to add next

Highest leverage:

- **Plugin section of the Anthropic *Claude Code* course** (manifest format, install/uninstall, hook registration semantics, marketplace flow). Fills the biggest gap — see `plugins-and-skills.md` for specific questions.
- **Skill section of the course** (frontmatter schema, activation rules, references convention).

Lower priority:

- Real-world plugin examples (community / first-party).
- Anti-patterns / pitfalls observed in the wild.
- Official Claude Code docs URLs as a canonical link list.

This material will eventually be distilled into the `references/` directory inside the plugin so the SKILL.md can `@`-mention it at runtime.
