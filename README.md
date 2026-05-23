# self-improving-claude

> A Claude Code plugin that turns the bugs you just saw into the hooks that prevent the next ones — per-project guardrails proposed by Claude itself, installed only with your explicit approval.

**Status:** v0.3.0 — public release.

## What it does

Claude Code is powerful by default, but every project has its own footguns. A test command that's `pnpm test:ci` not `pnpm test`. A generated directory that should never be hand-edited. A push command that should always require human confirmation. A constant rename that needs a callers-grep first.

`self-improving-claude` watches your Claude Code sessions, then — when you ask — proposes a tailored set of guardrails for THIS project: `permissions.deny` rules, `permissions.ask` prompts, hooks, or `CLAUDE.md` notes. You approve each one individually. The plugin generates the code; you decide what installs.

Three commands:

| Command | When to use |
|---|---|
| `/improve` | Right after seeing Claude do something you don't want again. Uses the live conversation as primary context. |
| `/improve-init` | First time, or periodic full sweep. Reads your project's code, recent session transcripts, and the bundled telemetry log. |
| `/improve-uninstall` | Cleanly remove the plugin's footprint from THIS project (settings.json entries, generated scripts, optionally telemetry). The plugin itself stays installed. |

## Install

```bash
# Add this repo as a marketplace
claude plugin marketplace add github:tim/self-improving-claude

# Install the plugin
claude plugin install self-improving-claude

# Restart Claude Code so the plugin loads
exit && claude
```

Inside any session: type `/improve-init` to run a first scan.

### Local dev / per-session use

If you're hacking on the plugin itself, clone the repo and use `--plugin-dir`:

```bash
git clone <this-repo> ~/code/self-improving-claude
claude --plugin-dir ~/code/self-improving-claude/plugin
```

Or alias it:

```bash
echo 'alias claude="command claude --plugin-dir ~/code/self-improving-claude/plugin"' >> ~/.zshrc
```

## How it works

When you run `/improve` or `/improve-init`, the plugin's orchestrator skill:

1. **Reads what already exists** in your project: `CLAUDE.md`, `.claude/settings.json`, the bundled telemetry log, recent session transcripts.
2. **Identifies up to 5 candidate guardrails** based on what it sees (a chat message describing a bug, repeated tool-call failures, project conventions encoded in CLAUDE.md, etc.).
3. **For each candidate, picks the lightest viable form:**
   - `permissions.deny` rule (cheapest)
   - `permissions.ask` rule (built-in Claude Code asks you each time)
   - prompt-based hook (LLM evaluates each tool call)
   - command hook on PreToolUse (deterministic block)
   - command hook on PostToolUse (surface context after action)
   - `CLAUDE.md` note (last resort, taste-level only)
4. **Self-critiques** the draft against an explicit rubric. Drops candidates that don't measure up.
5. **Walks you through approval** one at a time. You see the actual code, the rationale, where it merges into your `.claude/settings.json`. Approve, edit, or skip per candidate.
6. **Writes approved files** to `.claude/hooks/` and merges entries into `.claude/settings.json` (defensively — never overwrites your existing config).
7. **Tells you to restart Claude Code** so the new hooks load.

## Telemetry & privacy

The plugin installs one passive telemetry hook that logs summarized tool usage to `.claude/self-improving-claude/telemetry.jsonl` in each project where Claude Code is active.

**Redaction is strict** (tested in `plugin/scripts/tests/test_telemetry.py`):

- File `Read`/`Write`/`Edit` log only the path, never content.
- `Bash` logs the first 80 chars of the command and (only on non-zero exit) the first 200 chars of stderr.
- `Grep`/`Glob` redact patterns that match known secret prefixes (`API_KEY`, `SECRET`, `TOKEN`, etc.).
- `WebFetch` logs only the URL host — never query strings.
- `Task`/`TodoWrite` log type/counts only — never the prompt or todo content.

In v0.3 the telemetry hook also captures session boundaries (`SessionStart`), compaction events (`PreCompact`), and permission/idle notifications (`Notification`) — these give `/improve-init` richer signal to mine.

The log rotates at session end (renamed to `telemetry.<YYYYMMDD-HHMMSS>.jsonl`, fresh empty file for the next session).

**All telemetry stays on your local machine.** Nothing is sent anywhere.

## Inspecting & troubleshooting

Use Claude Code's built-in commands:

- `/hooks` — list all currently-loaded hooks (yours + plugins')
- `/memory` — open and edit your project's `CLAUDE.md`
- `claude plugin list` — show installed plugins
- `claude --debug` — verbose logging, including hook execution
- `claude plugin uninstall self-improving-claude` — remove the plugin itself (does NOT touch your project's `.claude/` directory — for that, use `/improve-uninstall`)

If a generated hook ever misfires:

```
/improve "the <name> hook just blocked something legit"
```

This is feedback-mode — it logs your complaint to `.claude/self-improving-claude/feedback.jsonl` and narrows the affected hook automatically.

## Design docs & evals

- `docs/superpowers/specs/` — full design specs for v0.1, v0.2, v0.3
- `docs/superpowers/plans/` — implementation plans
- `docs/knowledge/` — distilled Claude Code course material that grounds the design
- `docs/anthropic-marketplace-pr.md` — materials for publishing to the official marketplace
- `evals/` — dev-only eval harness. Run `pip install -r requirements-dev.txt && python3 -m evals.run` to reproduce the baseline (uses local Ollama by default; cloud Anthropic via `EVAL_BACKEND=anthropic`).

Baselines committed to `evals/results/`.

## Roadmap

- **v0.1** — `/improve-init` proactive scan, per-proposal approval, bundled telemetry hook.
- **v0.2** — `/improve` reactive mode, eval harness with 5 fixtures + code & model graders.
- **v0.3** (current) — public release: marketplace install, hidden orchestrator, `permissions.ask` as form option, multi-event telemetry, `/improve-uninstall`, formalized feedback channel, 7-fixture eval baseline.
- **v0.4+** — opt-in Stop-hook auto-collect (proactive pattern detection), conflict-resolution UX expansion, 10–20 eval entries, Anthropic-marketplace PR.

## License

MIT. See `LICENSE`.
