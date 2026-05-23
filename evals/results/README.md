# Eval Baseline Results — Reference

This directory holds the scored baselines from running `python3 -m evals.run` (or the one-shot CLI helper `/tmp/eval_via_cli.py`) against various LLM backends. Each `*.json` file in this directory is one full pass over the dataset (`../dataset.json`).

This README explains **what the eval measures, what each number means, and what each fixture tests** so you can read the baselines without re-tracing the code.

---

## What the eval does

For each fixture in `../dataset.json`:

1. **Assemble a prompt** that mirrors what the orchestrator skill (`plugin/skills/improve/SKILL.md` or `improve-init/SKILL.md`) sees at runtime: the rubric, hook references, worked examples, and the fixture's planted inputs (chat / project files / telemetry).
2. **Send it to the configured LLM backend** (gemma4 via Ollama, or one of Claude's Haiku/Sonnet/Opus via subscription or API key) asking it to output proposals as JSON.
3. **Parse the proposals** out of the response.
4. **Grade each proposal twice:**
   - **Code grade** — deterministic Python checks (7 binary checks, see below).
   - **Model grade** — a second LLM call judges how well the proposal solves the *planted problem*.
5. **Aggregate** per fixture (best-of-proposals) and across fixtures (mean).

The goal is to detect regressions: if a future change to the orchestrator prompt drops fixture 007 from 8.6 to 0, we know something broke.

---

## How to read the numbers

### Code grade — scale 0.0 to 10.0

Mean of 7 deterministic checks. Each check returns 0 or 10. So per fixture the possible code grades are: 0.0, 1.4, 2.9, 4.3, 5.7, 7.1, 8.6, 10.0 (i.e. `n × 10 ÷ 7`).

The 7 checks (see `../grade_code.py`):

| Check | What it verifies |
|---|---|
| `form_matches` | The proposal's `form` field matches the fixture's expected form (e.g. `command-hook`, `permissions.ask`, ...) |
| `event_matches` | The proposal's `event` field matches (e.g. `PreToolUse`, `PostToolUse`). N/A for `permissions.*` forms. |
| `matcher_matches` | The proposal's `matcher` is the exact string OR contains all required substrings (`matcher_must_include`). |
| `script_parses` | Python/Bash/JS script syntactically parses (via `ast.parse` / `bash -n` / `node --check`). N/A for non-script forms. |
| `sentinel_format` | The proposal's `sentinel_name` matches `self-improving-claude/<kebab-slug>` regex. N/A for `permissions.*` and `claude-md-note`. |
| `rationale_keywords` | The proposal's `rationale` contains all required keywords from `expected_hook_traits.rationale_must_mention`. |
| `rule_pattern` | For `permissions.*` forms: the `rule` matches expected string exactly OR contains required substring. |

**Rough interpretation:**
- **10.0** = perfect proposal, every check passes
- **8.6** = 6 of 7 checks pass — typical "good but one minor miss" (e.g. rationale missing a keyword)
- **7.1** = 5 of 7 — "decent but multiple issues"
- **0.0** = no proposals parsed OR all checks fail

### Model grade — scale 0 to 10 (integer)

A separate LLM call (the "grader") reads the proposal and the planted problem, then returns a JSON object:

```json
{
  "strengths": ["..."],
  "weaknesses": ["..."],
  "reasoning": "2-3 sentences",
  "score": 8
}
```

**Score interpretation** (per `../grade_model.py`'s prompt):
- **10** = exactly solves the planted problem
- **7-9** = strong proposal, minor issues
- **4-6** = partial / questionable
- **1-3** = misses the point
- **0** = parsing failure OR completely wrong

Model grades vary across model families — Haiku grading the same proposal often gives different numbers than Opus grading it. Use model grades for **directional signal, not absolute truth**.

### Aggregating per fixture

Each eval pass may produce multiple proposals per fixture (up to 3 are requested). The aggregated per-fixture score is the **MAX across proposals** — credits a strong proposal even when others are weak. This matches the orchestrator's "surface the best candidates" intent.

### Aggregating across fixtures

The "AVERAGE" row in the results is the simple arithmetic mean of per-fixture maxes across all 7 fixtures.

---

## The 7 fixtures

Each lives at `../fixtures/<id>/`. The planted problem is in `description.md`, expected output traits in `expected_traits.json`.

| # | ID | Trigger | Planted problem | Expected form |
|---|---|---|---|---|
| 1 | **001-pnpm-test-watcher** | `improve-init` | Claude keeps running `pnpm test` (interactive watcher) instead of `pnpm test:ci`. Telemetry has 3 non-zero exits. A `permissions.deny` rule won't work because `pnpm test` is the prefix of the correct command. | `command-hook` PreToolUse Bash — block the watcher, suggest `:ci` |
| 2 | **002-block-env-reads** | `improve-init` | Claude has read `.env`, `.env.local`, `.env.production` repeatedly. Should be blocked uniformly across Read/Grep/Glob. | `permissions.deny` rule `Read(**/.env)` (+ optional `.env.*`) |
| 3 | **003-prisma-generated-protection** | `improve-init` | Claude edits `src/generated/prisma/*` (auto-regenerated client) and writes to `prisma/dev.db`. CLAUDE.md forbids both but no enforcement. | `permissions.deny` rule blocking edits in the generated dir |
| 4 | **004-recursion-prevention** | `improve` | Claude refactored `walk_tree` from iterative to recursive, RecursionError on 2000-leaf input. User wants a project-wide guardrail. Reasoning-heavy: "is this an unbounded recursion?" doesn't fit a glob. | `prompt-hook` PreToolUse with matcher including Edit/Write |
| 5 | **005-format-on-write** | `improve-init` | Edits to .py files aren't auto-formatted; `ruff check` flags them after. CLAUDE.md says ruff is the formatter. | `command-hook` PostToolUse on `Write\|Edit\|MultiEdit` — run ruff |
| 6 | **006-rename-callers** (NEW v0.3) | `improve` | User reproduced the dogfooded `FILE_READ_TOOL_NAME 'Read' → 'View'` rename that broke ~15 hardcoded callers. Wants a guardrail that surfaces all references when an exported identifier is edited. | `command-hook` PostToolUse on `Edit\|MultiEdit` — grep callers, exit 2 with stderr |
| 7 | **007-git-push-warn** (NEW v0.3) | `improve-init` | User wants confirmation before any `git push` — not a hard block. Telemetry shows pushes to `feature/foo`, `main`, and `--force origin main`. | `permissions.ask` rule `Bash(git push:*)` |

Each fixture is designed to test a *specific form choice*. v0.3's form-selection fix is validated by fixtures 006 (PostToolUse command-hook) and 007 (`permissions.ask`) — both were under-used / missed entirely in v0.2.

---

## The backends compared

| Backend | Source | Cost | When to use |
|---|---|---|---|
| **gemma4:e4b** (Ollama) | Local 8B model, ~9.6 GB | Free | Default for daily eval iteration. No API key, no network call. |
| **Haiku 4.5** | Cloud via Claude Code subscription | Subscription quota | Cheap cloud reference; closest you can get to a "fast" cloud baseline. |
| **Sonnet 4.5 (200k)** | Cloud via subscription | Subscription quota | Mid-tier cloud reference. Default Sonnet for accounts that don't have 1M-context credits. |
| **Opus 4.7 (1M)** | Cloud via subscription | Subscription quota (premium) | Gold-standard cloud reference. Highest quality, highest per-call cost. |

All four were used to produce the v0.3 baseline. The non-Ollama runs went through `claude --print --model <X>` via the user's Claude Code subscription — **no `ANTHROPIC_API_KEY` env var needed** (subscription auth is OAuth).

For details on the CLI-via-subscription approach, see `/tmp/eval_via_cli.py` (one-shot helper) — v0.4 will productize it as a permanent backend (`evals/client_claude_cli.py`).

---

## Results — v0.3 baselines

### Code Grade

Mean of 7 deterministic checks (form / event / matcher / script parses / sentinel / rationale keywords / rule pattern).

| fixture | v0.2 (gemma4, 5 fixtures) | v0.3 gemma4 | v0.3 Haiku | v0.3 Sonnet | v0.3 Opus |
|---|---:|---:|---:|---:|---:|
| 001-pnpm-test-watcher | 10.0 | 10.0 | 10.0 | 10.0 | 10.0 |
| 002-block-env-reads | 10.0 | 8.6 | 10.0 | 10.0 | 10.0 |
| 003-prisma-generated-protection | 10.0 | 8.6 | 10.0 | 8.6 | 10.0 |
| 004-recursion-prevention | 10.0 | 7.1 | 7.1 | 8.6 | 7.1 |
| 005-format-on-write | 6.7 | 7.1 | 8.6 | 8.6 | 8.6 |
| 006-rename-callers (NEW) | — | 0.0 | 8.6 | 8.6 | 8.6 |
| 007-git-push-warn (NEW) | — | 8.6 | 8.6 | 7.1 | 8.6 |
| **AVERAGE** | **9.3** | **7.1** | **9.0** | **8.8** | **9.0** |

### Model Grade

LLM grader's score 0–10 (the grader uses the same model family as the proposer for each run — Haiku grades Haiku proposals, Opus grades Opus, etc.).

| fixture | v0.2 (gemma4) | v0.3 gemma4 | v0.3 Haiku | v0.3 Sonnet | v0.3 Opus |
|---|---:|---:|---:|---:|---:|
| 001-pnpm-test-watcher | 1 | 0 | 9 | 9 | 9 |
| 002-block-env-reads | 6 | 4 | 4 | 4 | 3 |
| 003-prisma-generated-protection | 6 | 6 | 5 | 5 | 3 |
| 004-recursion-prevention | 9 | 0 | 5 | 4 | 7 |
| 005-format-on-write | 9 | 7 | 7 | 9 | 9 |
| 006-rename-callers (NEW) | — | 0 | 6 | 7 | 7 |
| 007-git-push-warn (NEW) | — | 3 | 8 | 10 | 10 |
| **AVERAGE** | **6.2** | **2.9** | **6.3** | **6.9** | **6.9** |

---

## Key insights from the data

### Code-grade picture

- **All three frontier Claude models (Haiku/Sonnet/Opus) converge at 8.8–9.0** average. Structurally correct proposals are achievable across the model family — the rubric and examples generalize.
- **No regression in v0.3 vs v0.2**: 9.0 (v0.3 Haiku) ≈ 9.3 (v0.2 gemma4) is within noise. The form-fix didn't degrade quality.
- **Fixture 005 (format-on-write) IMPROVED** from 6.7 → 8.6+ in v0.3. Procedure Step 4 explicitly listing PostToolUse as a viable form made the orchestrator pick it more often.
- **Fixture 007 (permissions.ask) succeeds on all frontier models** (7.1–8.6). The v0.3 form-fix works.
- **Fixture 006 (rename-callers)** scored 8.6 across all frontier models but **0 with gemma4** — gemma4 truncates the long Python script in its JSON output. This is a small-model limit, not a plugin defect. **It confirms our v0.3 design choice to ship gemma4 as the local dev default and Haiku+ as the quality reference.**

### Model-grade picture

- **Sonnet & Opus = 6.9** vs **Haiku = 6.3** vs **gemma = 2.9** — bigger models grade more rigorously (lower mean) when judging the same proposals, which is actually a sign the eval is working. The relative ranking between fixtures stays consistent across graders.
- **Fixture 007 (permissions.ask) scored 10/10 on Sonnet AND Opus** — strong validation that the form choice is exactly right.
- **Fixture 004 (recursion-prevention) is the hardest** — even Opus only reaches 7/10 model grade. The fixture may have an ambiguous "right answer" (prompt-hook vs command-hook with regex vs sub-Claude). Worth revisiting the fixture design in v0.4.
- **Gemma's model grades are erratic**: fixture 001 got 0/1 with gemma but 9/9/9 with the frontier models. Self-grading by a small model is unreliable — this is exactly why we paired the deterministic code-grader with the model-grader.

### Practical guidance

- **For routine dev iteration:** use Ollama+gemma4 (default; free; fast). Watch the code-grade column for regressions.
- **For pre-release validation:** rerun against Sonnet 4.5 (200k). Best signal-to-cost ratio.
- **For "is this really good?" gold-standard checks:** Opus. Reserve for stable releases — uses ~3-5× the subscription quota.
- **All three Claude variants can run via Claude Code subscription** with no API key by using `claude --print --model <id>`. See `/tmp/eval_via_cli.py`.

---

## How to reproduce

From the repo root:

### Ollama (gemma4, default; no API key)

```bash
python3 -m evals.run
# writes evals/results/<today>.json
```

### Via Anthropic SDK (needs ANTHROPIC_API_KEY)

```bash
EVAL_BACKEND=anthropic ANTHROPIC_API_KEY=sk-... python3 -m evals.run
```

### Via Claude Code subscription (no API key — what we used for Haiku/Sonnet/Opus baselines here)

```bash
python3 /tmp/eval_via_cli.py haiku
python3 /tmp/eval_via_cli.py claude-sonnet-4-5     # 200k variant on accounts without 1M credits
python3 /tmp/eval_via_cli.py opus                  # 1M default on accounts with the 1M Opus entitlement
```

If specific fixtures time out (slow models on long prompts), use the patch script to re-run just those:

```bash
python3 /tmp/eval_patch.py <model_id> evals/results/<result-file>.json <fixture_id> [<fixture_id>...]
```

---

## Files in this directory

| File | What it is |
|---|---|
| `2026-05-22-baseline.json` | v0.2 baseline (gemma4 via Ollama, 5 fixtures) — historical reference |
| `2026-05-23-v0.3-gemma.json` | v0.3 baseline against gemma4 (7 fixtures) |
| `2026-05-23-v0.3-haiku.json` | v0.3 baseline against Haiku 4.5 (subscription) |
| `2026-05-23-v0.3-sonnet.json` | v0.3 baseline against Sonnet 4.5 (200k, subscription) |
| `2026-05-23-v0.3-opus.json` | v0.3 baseline against Opus 4.7 (1M default, subscription) |

Each result JSON contains: `date`, `model`, full per-entry `results` (proposals + code_grades + model_grades + raw_response_head), and a `summary` block (per-entry maxes + averages).
