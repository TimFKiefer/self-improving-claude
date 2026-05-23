# Anthropic Marketplace PR — Materials

This document contains everything needed to submit a PR to `anthropics/claude-plugins-official` that adds self-improving-claude to the official marketplace.

**Pre-submit checklist:**

- [ ] Repo is publicly accessible on GitHub
- [ ] Plugin manifest at `plugin/.claude-plugin/plugin.json` passes `claude plugin validate`
- [ ] README clearly explains what the plugin does, install steps, trust/privacy
- [ ] At least one tagged release exists (`v0.3.0`)
- [ ] LICENSE is OSI-approved (MIT)
- [ ] All sentinel-related conventions documented (so reviewers can understand the security model)

## Proposed addition to anthropics/claude-plugins-official/.claude-plugin/marketplace.json

Insert this entry into the `plugins` array (alphabetical ordering — find the right slot):

```json
{
  "name": "self-improving-claude",
  "description": "Proactive and reactive guardrail proposals for your Claude Code projects, with per-proposal approval. Analyzes telemetry, project conventions, and current conversation to suggest hooks, permissions.deny/ask rules, or CLAUDE.md notes — and installs only what you approve.",
  "author": {
    "name": "Tim Kiefer",
    "email": "tim.f.kief@gmail.com"
  },
  "category": "productivity",
  "source": {
    "source": "git-subdir",
    "url": "https://github.com/<user>/self-improving-claude.git",
    "path": "plugin",
    "ref": "v0.3.0",
    "sha": "<sha-of-v0.3.0-tag>"
  },
  "homepage": "https://github.com/<user>/self-improving-claude"
}
```

Replace `<user>` with the actual GitHub username/org. Replace `<sha-of-v0.3.0-tag>` with the commit SHA the tag points to (`git rev-parse v0.3.0`).

## Draft PR body

```
## Adds: self-improving-claude

`self-improving-claude` is a Claude Code plugin that watches your sessions and
proposes per-project guardrails (`permissions.deny` / `.ask`, hooks, CLAUDE.md notes)
based on observed behavior. Per-proposal user approval — nothing installs silently.

### What it does

- `/improve` (reactive) — propose guardrails based on the current conversation
- `/improve-init` (proactive) — periodic full scan of project + telemetry
- `/improve-uninstall` — clean project-level footprint

### Trust model

- All generated hooks live as readable files under the user's `.claude/hooks/` with a `self-improving-claude/<slug>` sentinel
- Telemetry is local-only (redacted JSONL); strict rules tested in repo
- Per-proposal approval — user sees the actual code/rule before anything writes

### Evals

7-fixture baseline (gemma4 local; Haiku cloud rerun deferred to user's environment),
code-grader + model-grader, committed scores at `evals/results/`. Form-selection
regression catches the v0.2 bias bug from real-world dogfooding.

### Compliance with marketplace schema

- `plugin.json` validates against the official schema
- Plugin lives in `plugin/` subdir (matches `git-subdir` source pattern)
- MIT licensed; LICENSE file present
- README clearly documents install + usage + privacy
```

## After submission

If the PR is accepted, update the README's install section from `claude plugin marketplace add github:tim/self-improving-claude` to `claude plugin install self-improving-claude` (no separate marketplace add needed for plugins in the official one).
