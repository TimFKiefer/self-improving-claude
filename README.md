<div align="center">

# self-improving-claude

**Turns the bugs you just saw into the hooks that prevent the next ones.**

A [Claude Code](https://claude.com/claude-code) plugin that converts observed footguns into per-project guardrails — proposed by Claude itself, installed only with your explicit approval.

[![Version](https://img.shields.io/badge/version-0.6.1-blue)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-plugin-d97757)](https://docs.claude.com/en/docs/claude-code/plugins)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB)](evals/)

[Quick start](#quick-start) · [How it works](#how-it-works) · [The self-improvement loop](#the-self-improvement-loop) · [Privacy](#telemetry--privacy) · [Development](#development) · [Roadmap](#roadmap)

</div>

---

## Why

Claude Code is powerful by default, but every project has its own footguns. A test command that's `pnpm test:ci`, not `pnpm test`. A generated directory that should never be hand-edited. A push that should always require human confirmation. A constant rename that needs a callers-grep first.

You notice these the moment Claude trips over them — and then you watch it trip over them again next week.

`self-improving-claude` closes that loop. Right after Claude does something you don't want repeated, you run `/improve`: the plugin reads the conversation, drafts the *lightest* guardrail that would have prevented it (a `permissions.deny` rule, a `permissions.ask` prompt, a Pre/PostToolUse hook, or a `CLAUDE.md` note), validates it against an explicit rubric — including a recursion trace so generated hooks can never loop — and walks you through approval one proposal at a time. You see the actual code before anything installs.

## Quick start

Inside any Claude Code session:

```text
/plugin marketplace add TimFKiefer/self-improving-claude
/plugin install self-improving-claude@self-improving-claude
```

Restart Claude Code so the plugin loads (`exit`, then `claude`), then run your first scan:

```text
/improve-init
```

<details>
<summary>Other install methods</summary>

**From the shell:**

```bash
claude plugin marketplace add TimFKiefer/self-improving-claude
claude plugin install self-improving-claude@self-improving-claude
```

**From a local clone** (point `marketplace add` at the repo path):

```text
/plugin marketplace add /path/to/self-improving-claude
/plugin install self-improving-claude@self-improving-claude
```

**Hacking on the plugin itself** — load it directly per session:

```bash
git clone https://github.com/TimFKiefer/self-improving-claude.git
claude --plugin-dir ./self-improving-claude/plugin
```

</details>

## Commands

| Command | When to use |
|---|---|
| `/improve` | Right after seeing Claude do something you don't want again. Uses the live conversation as primary context. |
| `/improve "directive"` | Point it at a specific problem (`/improve "block edits to src/migrations"`) or give feedback on an installed hook (`/improve "the foo-hook blocked something legit"`). |
| `/improve-init` | First time, or periodic full sweep. Reads your project's code, recent session transcripts, and the bundled telemetry log. |
| `/improve-uninstall` | Cleanly remove the plugin's footprint from THIS project (settings.json entries, generated scripts, optionally telemetry). The plugin itself stays installed. |

## What a proposal looks like

Say telemetry shows `pnpm test` hanging repeatedly because it opens an interactive watcher. `/improve` proposes:

> **Form:** Command hook on `PreToolUse` (matcher: `Bash`)
> **Rationale:** Blocks the recurring `pnpm test` watcher trap by inspecting the Bash command before it runs and pointing Claude at `pnpm test:ci`; a `permissions.deny` rule would also block the correct `pnpm test:ci` because it shares the prefix.

```python
def main():
    ev = json.load(sys.stdin)
    cmd = (ev.get("tool_input") or {}).get("command", "")
    if cmd.strip().startswith("pnpm test") and "test:ci" not in cmd:
        print("Use `pnpm test:ci` instead — `pnpm test` opens an interactive watcher.", file=sys.stderr)
        return 2
    return 0
```

You approve, edit, or reject. On approval the script lands in `.claude/hooks/` and the entry merges into `.claude/settings.json` — never overwriting your existing config.

## How it works

When you run `/improve` or `/improve-init`, the plugin's orchestrator skill:

1. **Reads what already exists** in your project: `CLAUDE.md`, `.claude/settings.json`, the bundled telemetry log, recent session transcripts, and your saved preferences.
2. **Identifies up to 5 candidate guardrails** from real evidence — a chat message describing a bug, repeated tool-call failures, project conventions — never hypotheticals.
3. **Picks the lightest viable form** per candidate:
   - `permissions.deny` rule (cheapest — no script, no model call)
   - `permissions.ask` rule (built-in Claude Code asks you each time)
   - prompt-based hook (LLM evaluates each tool call)
   - command hook on `PreToolUse` (deterministic block)
   - command hook on `PostToolUse` (surface context after an action)
   - `CLAUDE.md` note (last resort, taste-level only)
4. **Drafts against a 14-criterion rubric** and self-critiques. Every command hook is traced against constructed stdin envelopes before you see it: does it fire on its trigger, pass clean input, and — the loop-safety check — does the corrective action it demands *terminate* instead of re-firing the hook forever?
5. **Walks you through approval** one at a time: the bug it prevents, the actual code, the merge into your settings, in plain English.
6. **Writes approved files** to `.claude/hooks/` and merges entries into `.claude/settings.json` defensively.
7. **Tells you to restart** Claude Code so the new hooks load.

### Loop safety

Hooks that demand actions can recurse: a `PostToolUse` hook on `Write|Edit` whose stderr demands more edits re-fires on those edits; a hook that spawns a sub-Claude can fork-bomb; a `Stop` hook that forces continuation can never let the session end. The rubric's criterion 14 makes termination a shipping requirement — convergent checks (fail only on NEW violations vs. a recorded baseline), corrective-path exemptions, sentinel env guards for SDK-spawning hooks, and `stop_hook_active` handling for Stop hooks. See [`docs/knowledge/hooks-and-sdk.md`](docs/knowledge/hooks-and-sdk.md) §10 for the full taxonomy.

## The self-improvement loop

The plugin doesn't just write guardrails — it improves *itself* against evals, with git as the ratchet:

- **`evals/run.py`** scores the orchestrator skill against fixture scenarios (real footgun transcripts with reference answers), on local models (Ollama) or the Claude API.
- **`evals/auto_loop.py`** runs autonomously: it proposes a bounded edit to the skill's canonical sources, re-scores, and keeps the edit only if it clears a strict no-regression gate on both visible and held-out fixtures — then commits. Rejected edits are reverted.
- **Dual-axis since v0.6:** the loop optimizes the skill's *output quality* (procedure, rubric) and its *activation* (does the skill fire spontaneously when it should, stay quiet when it shouldn't) — each gated on its own deterministic metric.

Baselines and run history are committed under [`evals/results/`](evals/results/). The methodology lives in [`docs/knowledge/eval-methodology.md`](docs/knowledge/eval-methodology.md).

## Telemetry & privacy

The plugin installs one passive telemetry hook that logs summarized tool usage to `.claude/self-improving-claude/telemetry.jsonl` in each project where Claude Code is active. **All telemetry stays on your local machine. Nothing is sent anywhere.**

Redaction is strict (tested in [`plugin/scripts/tests/test_telemetry.py`](plugin/scripts/tests/test_telemetry.py)):

- File `Read`/`Write`/`Edit` log only the path, never content.
- `Bash` logs the first 80 chars of the command and (only on non-zero exit) the first 200 chars of stderr.
- `Grep`/`Glob` redact patterns matching known secret prefixes (`API_KEY`, `SECRET`, `TOKEN`, …).
- `WebFetch` logs only the URL host — never query strings.
- `Task`/`TodoWrite` log type/counts only — never prompt or todo content.

The hook also captures session boundaries (`SessionStart`), compaction events (`PreCompact`), and permission/idle notifications (`Notification`) for richer `/improve-init` signal. The log rotates at session end.

## Project structure

```text
plugin/                       # the shippable Claude Code plugin
├── .claude-plugin/plugin.json
├── hooks/hooks.json          # bundled telemetry hook registration
├── scripts/telemetry.py      # the telemetry hook (+ tests)
└── skills/
    ├── _shared/              # ★ CANONICAL sources: procedure, preambles, references
    ├── improve/              # generated — do not edit
    ├── improve-init/         # generated — do not edit
    └── improve-uninstall/
evals/                        # eval harness + autonomous improvement loop (dev-only)
docs/
├── knowledge/                # distilled Claude Code reference material (grounds the design)
├── ROADMAP.md                # canonical release history + exit criteria
└── VISION.md                 # the north star
scripts/sync_skills.py        # builds generated skills from _shared/
.claude-plugin/marketplace.json
```

## Inspecting & troubleshooting

- `/hooks` — list all currently-loaded hooks (yours + plugins')
- `claude plugin list` — show installed plugins
- `claude --debug` — verbose logging, including hook execution
- `claude plugin uninstall self-improving-claude` — remove the plugin itself (does NOT touch your project's `.claude/` directory — use `/improve-uninstall` for that)

If a generated hook misfires:

```text
/improve "the <name> hook just blocked something legit"
```

This is feedback-mode — it logs your complaint to `.claude/self-improving-claude/feedback.jsonl` and narrows the affected hook automatically.

## Development

```bash
# one-time: pre-commit hook that blocks drift between _shared/ and generated skills
bash scripts/install-hooks.sh

# after editing plugin/skills/_shared/** (NEVER edit generated SKILL.md / references directly)
python3 scripts/sync_skills.py        # rebuild
python3 scripts/sync_skills.py --check

# telemetry hook tests
python3 -m pytest plugin/scripts/tests/

# evals (dev-only; local Ollama by default, cloud via EVAL_BACKEND=anthropic)
pip install -r requirements-dev.txt
python3 -m evals.run
```

The two orchestrator skills are **generated** from `plugin/skills/_shared/` (one shared procedure + per-skill preambles + one references set). The skill body is treated as trainable parameters: substantive changes to it should go through the eval gate (`evals/auto_loop.py` or a manual before/after run), not vibes. See [`docs/knowledge/prompt-engineering.md`](docs/knowledge/prompt-engineering.md) §8.

## Roadmap

[`docs/ROADMAP.md`](docs/ROADMAP.md) is the canonical, linear roadmap (v0.1 → v1.0) with exit criteria and lessons per release. The short version:

- **v0.1–v0.3.x** — the product: proactive/reactive scans, per-proposal approval, telemetry hook, marketplace install, measurement-hardened eval harness.
- **v0.4.0** — Foundation for Autonomy: sandbox eval drives the *real* skill; single-sourced skills (`_shared/` is canonical).
- **v0.5.x** — The Self-Improvement Loop: `auto_loop.py` + git-ratchet + held-out confirmation gate; calibrated eval suite.
- **v0.6.x** (current) — Activation Frontier: the loop optimizes the skill's *trigger*, not just its body; loop-safety hardening (recursion guards for generated hooks).
- **v0.7+ → v1.0** — Night-Shift packaging, multi-skill generalization (`improve-skill <any SKILL.md> --eval <suite>`).

## Contributing

Issues and PRs welcome. The ground rules:

1. **Edit `plugin/skills/_shared/`, never the generated skill trees** — then run `python3 scripts/sync_skills.py` (the pre-commit hook enforces this).
2. **Skill-body changes need eval evidence** — a before/after `evals/run.py` score, or go through `auto_loop.py`.
3. **No personal context in shipped prompts** — generic examples only (`git push`, `npm publish`), no usernames or machine paths.
4. **Keep proposals observable** — guardrail patterns added to the rubric/examples must target behavior that actually occurs, not hypotheticals.

## License

[MIT](LICENSE) © Tim Kiefer
