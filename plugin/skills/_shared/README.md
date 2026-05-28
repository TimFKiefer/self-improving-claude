# `_shared/` — canonical source for the orchestrator skill

This directory is the **slow state** of the `self-improving-claude` skill.

## Contents

- `orchestrator-procedure.md` — the 10-step body shared by both `/improve` and `/improve-init`.
- `preambles/<skill>.md` — per-skill head (Inputs section, mode tag).
- `references/*.md` — rubric, hook patterns, tools reference, settings-merge discipline, examples.

## How it's built

`scripts/sync_skills.py` builds each `plugin/skills/<skill>/SKILL.md` as `preamble + procedure` and copies `references/` into the per-skill tree. The build is byte-preserving — regenerating a correctly-seeded tree is a no-op.

The pre-commit hook installed by `scripts/install-hooks.sh` runs `python3 scripts/sync_skills.py --check` and fails the commit on drift. Do **not** edit `plugin/skills/<skill>/SKILL.md` or `plugin/skills/<skill>/references/*` directly — they are generated. Edit the canonical source here, then commit (the hook regenerates as needed) or re-run `python3 scripts/sync_skills.py`.

## Slow state vs. fast state

| | Slow state | Fast state |
|---|---|---|
| **Where** | `plugin/skills/_shared/` (this directory) | `${HOME}/.claude/self-improving-claude/`, `${CLAUDE_PROJECT_DIR}/.claude/self-improving-claude/` |
| **Examples** | procedure step text, rubric criteria, reference docs | `preferences.md`, `feedback.jsonl`, `telemetry.jsonl` |
| **Changes through** | deliberate, eval-gated iteration (the prompt-lab loop or v0.5 auto-loop) | every invocation / every session |
| **Audience** | every user of the plugin | one project, one machine |
| **Personal context** | never (use generic examples — `git push`, `npm publish`, not user names or paths) | this is where personal context belongs |

The invariant: **fast-state writers structurally cannot reach slow-state paths.** `preferences.md` lives under `.claude/` (per project or per user); the slow-state generator (`sync_skills.py`) reads from this directory only; the pre-commit `--check` blocks out-of-band edits from drifting into the generated trees. A fast-state convenience that "writes a preference into the skill body" would break the invariant — don't add one.

Reading: `docs/knowledge/prompt-engineering.md` §8.4 (slow vs. fast state) covers the rationale.
