# self-improving-claude

> A Claude Code plugin that turns the bugs you just saw into the hooks that prevent the next ones.

**Status:** v0.2.0 — `/improve-init` (proactive scan) AND `/improve` (reactive) both work end-to-end. Eval harness with 5 fixtures + code & model graders + first committed baseline (gemma4 via Ollama).

---

## What it does

You're working in Claude Code. Claude does something you don't want again — runs the wrong test command, edits a file it shouldn't, forgets a migration step. You type `/improve-init`. The plugin reviews your project, your past session transcripts, and a bundled telemetry log, then proposes a set of guardrails (hooks, `permissions.deny` rules, or `CLAUDE.md` notes) with **per-proposal explicit approval**. Approved guardrails are written into your project's `.claude/` directory. Restart Claude Code and they take effect.

It's a Claude Code add-on that makes Claude Code measurably better at *your* project, the moment you notice it isn't.

## Install

### One-session use (recommended for v0.1)

Clone the repo, then start Claude Code with the plugin loaded for the current session:

```bash
git clone <this-repo> ~/code/self-improving-claude
claude --plugin-dir ~/code/self-improving-claude
```

That's it. The `/improve-init` command is available immediately and the bundled telemetry hook runs for every tool call in this session. No registration, no symlinks, no marketplace setup.

Optional: validate the plugin manifest first:

```bash
claude plugin validate ~/code/self-improving-claude
# → ✔ Validation passed
```

### Per-session forever (cheapest persistent setup)

Wrap the flag in a shell alias so every `claude` invocation loads the plugin:

```bash
echo 'alias claude="command claude --plugin-dir ~/code/self-improving-claude"' >> ~/.zshrc
source ~/.zshrc
```

(Use `~/.bashrc` for bash.)

### Permanent install via marketplace

Coming in a later release — requires the plugin to live in a `plugins/<name>/` subdirectory of a marketplace root, which is a structural change deferred until publishing to GitHub.

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

### `/improve`

Run *right after* seeing Claude do something you don't want again. Unlike `/improve-init`, this command uses the **current conversation** as its primary signal — the bug you just saw is already in scrollback, and the orchestrator looks there first.

```
/improve
/improve "add a guardrail against unbounded recursion"
/improve "the foo-hook just blocked something legit"
```

Accepts free-text args for directives or feedback; otherwise scans recent chat for the most-recent observable problem.

### Eval harness

`evals/` is a dev-only measurement substrate for the orchestrator's proposal quality. Five fixtures (`evals/fixtures/001-005/`) plant known problems; the runner asks the model to propose guardrails and grades them with a deterministic code-grader (form/event/matcher/syntax/sentinel/keywords) plus a model-grader (LLM judges substance).

Defaults to local Ollama (no API key needed):

```bash
pip install -r requirements-dev.txt
python3 -m evals.run                    # uses gemma4:e4b by default (~5 min)
python3 -m evals.run --entry 004-...    # just one entry
```

Switch backends:

```bash
EVAL_BACKEND=anthropic ANTHROPIC_API_KEY=sk-... python3 -m evals.run
EVAL_BACKEND=ollama OLLAMA_MODEL=qwen3.5:9b python3 -m evals.run
```

Baseline: `evals/results/2026-05-22-baseline.json` — code 9.3/10, model 6.2/10 (gemma4:e4b). Future SKILL.md changes should be paired with delta scores so we know whether they regress or improve quality.

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

- **v0.1** — `/improve-init` proactive scan, per-proposal approval, bundled telemetry hook.
- **v0.2** (current) — `/improve` reactive mode; `evals/` harness with code + model graders + committed scored baselines.
- **v0.3+** — formal feedback channel (`/improve "the foo-hook blocked something legit"` becomes a structured log), expanded eval coverage, marketplace publish, larger reference baseline (Haiku/Sonnet).

## Design docs

- `docs/superpowers/specs/2026-05-22-self-improving-claude-design.md` — full design spec.
- `docs/knowledge/` — distilled Claude Code course material grounding the design.
- `docs/superpowers/plans/2026-05-22-self-improving-claude-v0.1.md` — v0.1 implementation plan.
- `docs/superpowers/plans/2026-05-22-self-improving-claude-v0.2.md` — v0.2 implementation plan.

## License

MIT. See `LICENSE`.
