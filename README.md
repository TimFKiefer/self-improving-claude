# self-improving-claude

> A Claude Code plugin that turns the bugs you just saw into the hooks that prevent the next ones.

**Status:** v0.1.0 — `/improve-init` (proactive scan) works end-to-end. `/improve` (reactive) is v0.2.

---

## What it does

You're working in Claude Code. Claude does something you don't want again — runs the wrong test command, edits a file it shouldn't, forgets a migration step. You type `/improve-init`. The plugin reviews your project, your past session transcripts, and a bundled telemetry log, then proposes a set of guardrails (hooks, `permissions.deny` rules, or `CLAUDE.md` notes) with **per-proposal explicit approval**. Approved guardrails are written into your project's `.claude/` directory. Restart Claude Code and they take effect.

It's a Claude Code add-on that makes Claude Code measurably better at *your* project, the moment you notice it isn't.

## Install (local, from this repo)

1. Clone or download this repo to a stable location, e.g. `~/code/self-improving-claude`.
2. Symlink (or copy) it into Claude Code's plugins directory:

   ```bash
   ln -s ~/code/self-improving-claude ~/.claude/plugins/cache/self-improving-claude
   ```

   The exact path may differ slightly on your machine — the rule is that the plugin needs to live somewhere Claude Code scans for plugins. Check `~/.claude/plugins/` to find the cache root used on your install.

3. Restart Claude Code (`exit`, then `claude`). On the next session start, the bundled telemetry hook is registered and the `/improve-init` command is available.

## Usage

### `/improve-init`

Run inside any project you'd like to harden. The plugin will:

1. Read your project's `CLAUDE.md`, manifest files, and a sampled set of source files.
2. Read recent past-session transcripts and the bundled telemetry log (if present).
3. Identify up to 5 candidate guardrails.
4. For each candidate, propose the lightest viable form (`permissions.deny` rule, prompt-based hook, command hook, or `CLAUDE.md` note).
5. Walk you through them one at a time — you approve, reject, or edit each.
6. Write approved files to your project's `.claude/hooks/` and merge entries into `.claude/settings.json`.
7. Tell you to restart Claude Code so the new hooks load.

Optional scoped invocation:

```
/improve-init "focus on the queries directory"
```

### Telemetry hook

The plugin installs one always-on hook — `PostToolUse: "*"` — that logs summarized tool usage to `.claude/self-improving-claude/telemetry.jsonl` inside each project where Claude Code is active. Logged fields per call:

```jsonl
{"ts": "2026-05-22T14:33:01Z", "tool": "Bash", "args_summary": "pnpm test", "outcome": {"exit_code": 1, "stderr_head": "ENOENT..."}}
```

**Redaction is strict** (tested in `scripts/tests/test_telemetry.py`):

- File `Read`/`Write`/`Edit` log only the path, never content.
- `Bash` logs the first 80 chars of the command and (only on non-zero exit) the first 200 chars of stderr.
- `Grep`/`Glob` redact patterns that match known secret prefixes (`API_KEY`, `SECRET`, `TOKEN`, etc.).
- `WebFetch` logs only the URL host — never query strings.
- `Task`/`TodoWrite` log type/counts only — never the prompt or todo content.

The script silently no-ops on any unexpected error — it must never break Claude Code's tool execution.

If you want to disable telemetry entirely, remove the `PostToolUse` entry whose `name` is `self-improving-claude/telemetry` from your `.claude/settings.json` (or just don't enable the plugin).

## What's installed where

| Location | What |
|---|---|
| Plugin directory (read-only) | `.claude-plugin/plugin.json`, skills, bundled telemetry script. Plugin updates touch only this. |
| Your project's `.claude/hooks/` | Generated hook scripts (you own these). |
| Your project's `.claude/settings.json` | Plugin-added entries carry `"name": "self-improving-claude/<slug>"` so you can find/edit/remove them. |
| Your project's `.claude/self-improving-claude/telemetry.jsonl` | The redacted telemetry log. |

## Roadmap

- **v0.1** (current) — `/improve-init` proactive scan, per-proposal approval, bundled telemetry hook.
- **v0.2** — `/improve` reactive mode (uses current chat as primary input); `evals/` harness with code + model graders; generated hooks default to `"type": "prompt"` where the event supports it.
- **v0.3+** — feedback channel (`/improve "the foo-hook blocked something legit"`), formal conflict UX, more eval entries.

## Design docs

- `docs/superpowers/specs/2026-05-22-self-improving-claude-design.md` — full design spec.
- `docs/knowledge/` — distilled Claude Code course material grounding the design.
- `docs/superpowers/plans/2026-05-22-self-improving-claude-v0.1.md` — the implementation plan for this version.

## License

MIT. See `LICENSE`.
