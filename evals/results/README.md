# Eval Baseline Results — Reference

## 🏁 Capability Benchmark — Leaderboard

> **Updated 2026-05-25** · judge: Sonnet 4.5 · N=4 samples/cell · 7 shared fixtures · source: [`benchmark/2026-05-25-bench.json`](benchmark/2026-05-25-bench.json)

| Rank | Model (proposer) | Mean quality | valid |
|---:|---|---:|---:|
| 1 | Sonnet 4.5 | **8.21** ± 0.69 | 100% |
| 2 | Opus 4.7 | **8.18** ± 0.85 | 100% |
| 3 | Haiku 4.5 | **7.75** ± 0.56 | 100% |
| 4 | gemma4:e4b (local) | **5.25** ± 1.14 | 71% |

**Verdict:** the three frontier models are a **statistical tie** — Sonnet, Opus, and Haiku all sit inside each other's ± noise bands, so none is measurably better at hook authoring here (**Opus is *not* ahead**). gemma trails, and its 71% valid-rate shows it often fails to emit a parseable proposal on the reasoning-heavy fixtures.

*This is the **capability** instrument (`python3 -m evals.benchmark`) — it scores hook **quality** vs the planted problem with a fixed LLM judge. It is **not** the conformance tripwire below (which is exact-match to a gold and can't rank models). N=4 over 7 fixtures with a single judge is **directional, not definitive**; see [the capability-benchmark section](#capability-benchmark-python3--m-evalsbenchmark) for the full caveats. Opus also scored the new fixtures 008–010 (opus-only so far).*

---

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

Mean of 8 deterministic checks (was 7 before v0.3.2 added `imperative_stderr`). Each check returns 0 or 10. So per fixture the possible code grades are: 0.0, 1.25, 2.5, 3.75, 5.0, 6.25, 7.5, 8.75, 10.0 (i.e. `n × 10 ÷ 8`).

The 8 checks (see `../grade_code.py`):

| Check | What it verifies |
|---|---|
| `form_matches` | The proposal's `form` field matches the fixture's expected form (e.g. `command-hook`, `permissions.ask`, ...) |
| `event_matches` | The proposal's `event` field matches (e.g. `PreToolUse`, `PostToolUse`). N/A for `permissions.*` forms. |
| `matcher_matches` | The proposal's `matcher` is the exact string OR contains all required substrings (`matcher_must_include`). |
| `script_parses` | Python/Bash/JS script syntactically parses (via `ast.parse` / `bash -n` / `node --check`). N/A for non-script forms. |
| `sentinel_format` | The proposal's `sentinel_name` matches `self-improving-claude/<kebab-slug>` regex. N/A for `permissions.*` and `claude-md-note`. |
| `rationale_keywords` | The proposal's `rationale` contains all required keywords from `expected_hook_traits.rationale_must_mention`. |
| `imperative_stderr` | For command-hooks that write stderr: banned passive phrasing (`audit`/`consider`/`verify`/`review`) fails; non-blocking events (PostToolUse, etc.) also require an action phrase (`REQUIRED FOLLOW-UP`/`Do not stop`/`Fix each`/`BLOCKING`/`Do not ask`). N/A for non-script forms and stderr-less scripts. |
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

For the CLI-via-subscription approach, use `EVAL_BACKEND=claude-cli` (implemented in `evals/client_claude_cli.py` as of v0.3.3 — it productized the former `/tmp/eval_via_cli.py` one-shot helper).

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

LLM grader's score 0–10. **(Historical note: these v0.3 numbers were produced with the grader matching the proposer family — Haiku grades Haiku, Opus grades Opus. v0.3.4 changed this: the grader is now pinned to Haiku for *every* run so columns are comparable — see the v0.3.4 section below.)**

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

## v0.3.3 re-score (2026-05-24)

First re-score since v0.3.0, and the first run with the **8-check grader** — the v0.3.2 `imperative_stderr` check now actually inspects f-string / bash / JS stderr (it previously only saw plain-string `print()`; see CHANGELOG 0.3.3). File: `2026-05-24-v0.3.3-gemma.json`.

| metric | v0.3 gemma | v0.3.3 gemma |
|---|---:|---:|
| avg code | 7.1 | 6.1 |
| avg model | 2.9 | 3.7 |

**The code dip is gemma noise, not a regression — read the per-fixture data before concluding anything:**
- The new 8th check (`imperative_stderr`) scored **10 on all 5 fixtures** where gemma produced a parseable proposal. The fixed (stricter) grader did **not** spuriously fail any correct hook.
- The 7.1→6.1 drop is driven entirely by gemma emitting **no parseable JSON** for fixtures 003 and 004 this run (`forms=[]` → 0.0). This is the documented gemma small-model truncation: different fixtures fail on different runs (006 truncated in the v0.3 gemma run but succeeded here).
- Net: treat the gemma baseline as a **regression tripwire**, not a quality signal. For a clean read of the v0.3.1/v0.3.2/v0.3.3 changes, run the frontier reference: `EVAL_BACKEND=claude-cli CLAUDE_CLI_MODEL=haiku python3 -m evals.run`.

---

## Results — v0.3.4 baselines (current)

> **⚠️ Scoring semantics changed in v0.3.4 — these numbers are NOT directly comparable to ≤v0.3.3.** Changes: (1) code grade now averages only *applicable* checks (N/A excluded, no free passes); (2) fixtures 002/003/004 reconciled with their planted problems (002 gold → `Read(**/.env*)`, 003 → two-path `required_rules` coverage, 004 accepts prompt-hook OR PostToolUse command-hook); (3) model grade returns *no data* on truncation instead of 0; (4) **the grader is pinned to Haiku for every run** (proposer varies), so the Model Grade columns are comparable. Files: `2026-05-24-v0.3.4-{gemma,haiku,sonnet,opus}.json`.

### Code Grade (max across proposals; applicable-checks denominator)

| fixture | gemma4 | Haiku | Sonnet (200k) | Opus |
|---|---:|---:|---:|---:|
| 001-pnpm-test-watcher | 10.0 | 10.0 | 10.0 | 8.6 |
| 002-block-env-reads | 6.7 | 10.0 | 6.7 | 6.7 |
| 003-prisma-generated-protection | 10.0 | 10.0 | 10.0 | 10.0 |
| 004-recursion-prevention | 10.0 | 8.6 | 10.0 | 10.0 |
| 005-format-on-write | 7.1 | 8.6 | 7.1 | 10.0 |
| 006-rename-callers | 8.6 | 10.0 | 8.6 | 10.0 |
| 007-git-push-warn | 6.7 | 10.0 | 10.0 | 6.7 |
| **AVERAGE** | **8.4** | **9.6** | **8.9** | **8.8** |

### Model Grade (grader = Haiku for ALL runs)

| fixture | gemma4 | Haiku | Sonnet (200k) | Opus |
|---|---:|---:|---:|---:|
| 001-pnpm-test-watcher | 7 | 8 | 7 | 8 |
| 002-block-env-reads | 9 | 8 | 2 | 3 |
| 003-prisma-generated-protection | 4 | 4 | 3 | 3 |
| 004-recursion-prevention | 6 | 7 | 7 | 5 |
| 005-format-on-write | 4 | 6 | 2 | 7 |
| 006-rename-callers | 5 | 4 | 6 | 7 |
| 007-git-push-warn | 7 | 6 | 4 | 7 |
| **AVERAGE** | **6.0** | **6.1** | **4.4** | **5.7** |

### Clean rate + coverage (new v0.3.4 metrics)

| backend | avg clean_rate | 003 coverage |
|---|---:|---:|
| gemma4 | 0.71 | 0.50 |
| Haiku | 0.81 | 0.50 |
| Sonnet | 0.86 | 0.50 |
| Opus | 0.71 | 0.50 |

### What the v0.3.4 data shows

- **The truncation artifact is gone.** Zero invalid/parse-failed model grades on *any* backend this run, including gemma (which logged several truncation-0s pre-v0.3.4). gemma's model average is now a real signal (6.0), not a parsing floor (was 2.9).
- **003 coverage is 0.50 on every model** — all four cover only *one* of the two forbidden prisma paths. The old max-only grade hid this as a clean 10.0; the coverage metric exposes the consistent gap (a genuine orchestrator weakness for two-pronged protections, candidate for a future prompt fix).
- **The 002 contradiction is resolved.** Haiku now scores 002 at code 10 / model 8 (gold and planted problem agree). Opus/Sonnet score it lower on *both* axes — genuinely weaker proposals against the corrected gold, no longer masked.
- **Grader pinned to Haiku makes columns comparable.** Sonnet's lower model average (4.4) reflects weaker proposals as judged by one consistent grader — not grader drift.

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

### Via Claude Code subscription (no API key — for the Haiku/Sonnet/Opus references)

As of v0.3.3 this is an in-repo backend (`evals/client_claude_cli.py`), no longer a `/tmp` helper:

```bash
EVAL_BACKEND=claude-cli CLAUDE_CLI_MODEL=haiku python3 -m evals.run
EVAL_BACKEND=claude-cli CLAUDE_CLI_MODEL=claude-sonnet-4-5 python3 -m evals.run
EVAL_BACKEND=claude-cli CLAUDE_CLI_MODEL=opus python3 -m evals.run
```

`CLAUDE_CLI_MODEL` defaults to `haiku`. Auth is your Claude Code subscription (OAuth) — no `ANTHROPIC_API_KEY` needed.

---

## Files in this directory

| File | What it is |
|---|---|
| `2026-05-22-baseline.json` | v0.2 baseline (gemma4 via Ollama, 5 fixtures) — historical reference |
| `2026-05-23-v0.3-gemma.json` | v0.3 baseline against gemma4 (7 fixtures) |
| `2026-05-23-v0.3-haiku.json` | v0.3 baseline against Haiku 4.5 (subscription) |
| `2026-05-23-v0.3-sonnet.json` | v0.3 baseline against Sonnet 4.5 (200k, subscription) |
| `2026-05-23-v0.3-opus.json` | v0.3 baseline against Opus 4.7 (1M default, subscription) |
| `2026-05-24-v0.3.3-gemma.json` | v0.3.3 re-score against gemma4 (first run with the 8-check grader; see the v0.3.3 note above) |
| `2026-05-24-v0.3.4-gemma.json` | v0.3.4 baseline, gemma4 (new scoring semantics; grader pinned to Haiku) |
| `2026-05-24-v0.3.4-haiku.json` | v0.3.4 baseline, Haiku proposer (grader Haiku) |
| `2026-05-24-v0.3.4-sonnet.json` | v0.3.4 baseline, Sonnet 4.5 200k proposer (grader Haiku) |
| `2026-05-24-v0.3.4-opus.json` | v0.3.4 baseline, Opus 4.7 proposer (grader Haiku) |

Each result JSON contains: `date`, `model`, full per-entry `results` (proposals + code_grades + model_grades + raw_response_head), and a `summary` block (per-entry maxes + averages).

---

## Capability benchmark (`python3 -m evals.benchmark`)

A **separate instrument** from the conformance tables above. Those are a *regression tripwire* — exact-match to a narrow gold, n=1; they answer "did the orchestrator still produce a conformant hook?" and deliberately penalize a model for, e.g., writing "watch mode" instead of the literal keyword "watcher". They **cannot** rank models by quality.

The capability benchmark answers the other question — **"on average, how good are the hooks a model produces?"** — by sampling each model multiple times and scoring *quality against the planted problem* (never gold conformance), then ranking.

**How it works:** for each `model × fixture`, run `N` proposer samples; **one batched judge call per cell** (fixed Sonnet judge) scores all that cell's proposals; per-sample quality = the best (max) proposal; aggregate to mean ± stderr per cell and a per-model leaderboard. Reuses `grade_model` (which already scores quality vs the planted problem).

**Run it:**
```bash
python3 -m evals.benchmark                       # defaults below
BENCH_MODELS="claude-cli:haiku,claude-cli:claude-sonnet-4-5,ollama:gemma4:e4b" python3 -m evals.benchmark
python3 -m evals.benchmark --fixture 002-block-env-reads
python3 -m evals.benchmark --independent         # one judge call per proposal (gold-standard)
```
- `BENCH_MODELS` (default `claude-cli:haiku,claude-cli:claude-sonnet-4-5,claude-cli:opus,ollama:gemma4:e4b`) — comma-separated `backend:model` specs.
- `BENCH_JUDGE` (default `claude-cli:claude-sonnet-4-5`) — the fixed judge.
- `BENCH_SAMPLES` (default `4`) — samples per model×fixture.

**Cost:** ~`models × fixtures × N` proposer calls + ~`models × fixtures` Sonnet judge calls (batched; `--independent` multiplies the judge calls by the proposal count). Opus is premium — run deliberately.

**Caveats (don't over-read the numbers):**
1. **Single-judge self-preference** — Sonnet judges all contestants, including the Sonnet one; mild bias toward its own family.
2. **Absolute 0-10 is the judge's subjective scale** — read *relative* model ordering, not the absolute values.
3. **Batched judging mildly compresses within-cell variance** (co-scoring a cell's samples). Use `--independent` for a rigorous run.
4. **Sample diversity is bounded by the backend's default temperature** — `claude --print` can't force one, so stderr may be understated.
5. **n=4 is a noise band, not a CI** — the leaderboard flags pairs "within noise" so small gaps aren't over-read.

**Output:** `evals/results/benchmark/<date>-bench.json` (per-cell stats + leaderboard).

---

## Real-skill sandbox eval (`python3 -m evals.run --sandbox`) — v0.4.0

The **canonical conformance eval as of v0.4.0**. Unlike the legacy tables above — which assemble a *proxy* prompt from `prompt_template.md` + the references and never read `SKILL.md` — this mode drives the **real `/improve` / `/improve-init` slash command end-to-end**: it builds a throwaway temp project from the fixture, invokes the actual plugin command headlessly via `claude --print`, lets the orchestrator run its real Steps 1–9 (real Read/Grep/Bash tool use, real file writes), and grades what it produces. This closes the proxy gap (Track 6.2): a `SKILL.md` regression can now be caught.

The legacy prompt path is **retained** (still imported by `benchmark.py`) but is no longer the canonical conformance instrument.

**How to run** (one model per invocation):
```bash
SANDBOX_MODEL=haiku            python3 -m evals.run --sandbox
SANDBOX_MODEL=claude-sonnet-4-5 python3 -m evals.run --sandbox
SANDBOX_MODEL=opus             python3 -m evals.run --sandbox   # premium — run deliberately
```
Output: `evals/results/<date>-v0.4.0-sandbox-<model>.json`.

**How it works:** for each fixture, `evals/sandbox_runner.py` writes the fixture's project files + telemetry into a temp dir, then runs `claude --print --plugin-dir <repo>/plugin --permission-mode bypassPermissions --output-format json --append-system-prompt <override> "/improve[-init] <args>"`. The override suppresses the interactive Step 8 approval, auto-applies surviving candidates (real Step 9 writes), and makes the final message a single JSON echo of the proposals. The echo is graded by the **unchanged** `grade_code` / `grade_model` (grader pinned to Haiku). Two extra axes: `install_rate` (did the echoed proposal actually land + parse on disk — the seed of a future firing harness) and `average_restraint` (the `expect_no_proposal` fixtures 011/012 score 10 iff the run proposes nothing **and** writes nothing).

**Caveats (read before trusting the numbers):**
1. **Claude-models-only.** Running the real slash command needs a Claude Code runtime, so gemma-via-Ollama is **dropped** from this baseline (it has no skill/tool runtime). The free no-key local reference lives only on the legacy prompt path now.
2. **N=1, non-deterministic.** Each cell is one full agentic run; agentic tool-use varies run to run. Read **gross drift**, not fine deltas.
3. **Coercive override → possible rubric distortion.** The run uses `bypassPermissions` in a throwaway temp dir plus a *forceful* non-interactive override (a mild one let Step 8 dominate). Under that pressure a smaller model can go off-rubric (in spike testing one Haiku run proposed a command-hook instead of the gold `permissions.deny`; another chose correctly). Treat proposals as produced under a non-interactive override, not the interactive UX.
4. **Integrity stops at "exists + parses,"** not hook *firing*. Verifying a generated hook actually fires in a live session is deferred to the 6.1 behavioral harness.
5. **Not comparable to the v0.3.4 prompt-path numbers** — the instrument changed (real skill vs. proxy). This is a re-baseline, not a trend line.

**Cost:** each cell is a full agentic procedure (multiple tool calls), materially pricier than the legacy single-prompt path. The Opus leg is quota-gated.

### First baseline — 2026-05-26 (Opus judge)

Files: `2026-05-26-v0.4.0-sandbox-{haiku,claude-sonnet-4-5,opus}.json`. Proposers run the real `/improve[-init]`; judge = Opus 4.7; N=1; default effort.

| Proposer | avg code | avg model (Opus judge) | install_rate | restraint (011/012) |
|---|---:|---:|---:|---:|
| Haiku 4.5 | 6.7 | 5.1 | 100% | 0/10 |
| Sonnet 4.5 (200k) | **8.1** | 5.9 | 54% | 0/10 |
| Opus 4.7 | 5.6 | **7.1** | 67% | **10/10** |

**Reading it (directional only):**
- **Code vs. model invert for Opus.** Opus has the lowest deterministic code grade (5.6) yet the highest judge grade (7.1). It emitted *no gradeable proposal* on 3 positive fixtures (004 recursion, 007 git-push, 008 secret-in-source → 0/0), dragging its code mean; on the 7 it did answer, the judge rated it highest. Sonnet is the conformance leader (8.1) — most reliably hits the exact gold form.
- **Only Opus exercised restraint (10/10)** — it correctly proposed nothing on the healthy-project (011) and one-off-bug (012) fixtures. Haiku and Sonnet both over-proposed (0/10); Haiku even fabricated a `pnpm test` guardrail on a clean project and emitted malformed `form` values (`"command"`/`"hook"`) there.
- **install_rate** (did the echoed proposal land + parse on disk) varies independently of quality: Haiku 100%, Opus 67%, Sonnet 54%.

**Heavy caveats:** N=1 (non-deterministic agentic runs); **Opus-judges-Opus self-preference** inflates the Opus model column; and every proposal was produced under the *forceful non-interactive override* (the bypassPermissions path) — the restraint results show this can coerce over-proposing in the smaller models. Read this as a first exercise of the real-skill harness, not a definitive ranking. A true "ceiling" run (per the benchmark-thinking-config preference) would add `--effort max`, now exposed by `claude --print` (≥ v2.1.150).

### Ceiling baseline — 2026-05-26, `--effort max` (Opus judge)

Same harness with `SANDBOX_EFFORT=max` on both proposer and judge. Files: `2026-05-26-v0.4.0-sandbox-{haiku,claude-sonnet-4-5,opus}-effort-max.json`.

| Proposer | code (def → max) | model (def → max) | install (def → max) | restraint (def → max) |
|---|--:|--:|--:|--:|
| Haiku 4.5 | 6.7 → 5.8 | 5.1 → 4.7 | 100% → 80% | 0 → 0 |
| Sonnet 4.5 (200k) | 8.1 → 8.3 | 5.9 → 4.7 | 54% → 73% | 0 → 0 |
| Opus 4.7 | 5.6 → **8.7** | 7.1 → **8.0** | 67% → 67% | **10 → 0** |

**Two clear effects:**
- **Max effort vindicates measuring frontier models at their ceiling.** At default effort Opus emitted *no gradeable proposal* on 3 positive fixtures (004/007/008 → 0/0); at max effort it scores **code 10** on all three (004 10/8, 008 10/9). Opus goes from looking worst on conformance (5.6) to the clear leader on **both** axes (code 8.7, model 8.0). The default run under-represented it — exactly the artifact the benchmark-thinking-config preference guards against.
- **Restraint collapses for everyone at max effort** — Opus drops 10 → 0; all three now over-propose on the negative fixtures (011/012). More reasoning ⇒ more eager to find *something* to propose. A real tradeoff: the ceiling config that surfaces Opus's positive-case strength also defeats restraint.
- Haiku does **not** benefit from more effort (slightly worse); Sonnet's conformance is flat and its judged score drops. The ceiling lift is a frontier-model phenomenon here.

Caveats unchanged (N=1; Opus-judges-Opus; forceful override). Net: at the models' ceiling, **Opus is the strongest hook author** in this harness — but under the forceful override no model exercises restraint.

### Hook-firing baseline + the envelope fix — 2026-05-27 (Opus judge, default effort)

The first firing-harness run found that **generated command-hooks mostly didn't fire**, and *why*: hooks read `data["tool"]`/`data["args"]` instead of the real `tool_name`/`tool_input` envelope, so the guard never matched and the hook exited 0. Root cause (controlled probe): the skill's `@references/*.md` load **lazily** (Read-on-demand, not inlined), so under the headless override the model skipped the boilerplate and invented field names. **Fix:** inline the stdin skeleton into the orchestrator (`e5eb395`) + a static `grade_code.stdin_envelope` guard (`e20306a`).

Pre-fix run is committed at git `4fdd670`; the current `2026-05-27-v0.4.0-sandbox-{...}.json` files are the **post-fix** re-baseline.

| Proposer | code (pre→post) | model (pre→post) | install (pre→post) | **fire_rate (pre→post)** |
|---|--:|--:|--:|--:|
| Haiku 4.5 | 6.9 → 5.9 | 4.9 → 4.2 | 50% → 64% | **0% → 0%** |
| Sonnet 4.5 (200k) | 8.0 → 7.7 | 5.0 → 6.2 | 77% → 73% | **25% → 25%** |
| Opus 4.7 | 8.3 → 7.3 | 6.9 → 7.2 | 77% → 91% | **40% → 33%** |

**What the fix did — and didn't:**
- **The envelope bug is gone.** Post-fix, *every* command-hook reads `tool_name`/`tool_input`; **zero** read `tool`/`args` (the new `stdin_envelope` check is 10 wherever a hook reads stdin). The systematic wrong-envelope failure is fixed at the source.
- **`fire_rate` did NOT lift.** The no-op problem is **multi-causal** — the envelope was only one cause. The remaining failure modes the harness now surfaces:
  - **command-hooks that don't read stdin at all** (post-fix haiku/008, sonnet/006 → can't inspect the tool call);
  - **logic errors** (read the envelope correctly but mis-match the trigger or over-fire on the clean input);
  - **heavy N=1 noise** — the 008-Haiku hook *fired* in a one-off smoke but came back a no-stdin no-op in this baseline (same fixture+model, different run).
- **Net:** the targeted bug is fixed and statically guarded; the firing harness is now doing its deeper job — pointing at the *next* layer of hook-quality failures. A real `fire_rate` lift needs N>1 (to beat the noise) plus addressing the no-stdin / logic failure modes (and likely the override-fidelity issue — the headless override still yields rushed, variable proposals). Restraint also dropped to 0/0/0 (Opus lost its 5/10 from the pre-fix run) — within N=1 noise.

Caveats unchanged (N=1, Opus-judges-Opus, forceful override). `stdin_envelope` was added to `grade_code` after the pre-fix run, so the post column's code grades include it.

## Auto-loop fidelity & reproducibility (v0.5.1)

The auto-loop's keeps are only trustworthy at a high-fidelity config. Run with
opus skill-runner + max effort + `--confirm-reruns 2` (best-of-3 confirmation)
for any run whose commits you intend to keep. See
`docs/knowledge/eval-methodology.md` § "Variance budget" for the rationale.

**Reproducibility check (deferred from v0.5.0):** measured with
`python3 -m evals.reproducibility <reference_run_dir> <candidate_run_dir>`.

**v0.5.1 result (2026-06-01):** one fresh layered run (opus skill-runner, max
effort, `--confirm-reruns 2`, 20 iter, $113.91, 11.3h) from the pre-RC baseline
(`15cb51e`) vs the RC keep-set (`c6c5bac`/`f627357`/`4915a20`):

- **by-fixture overlap: 0%** · **judge overlap: 0%** — the run kept 1/20
  (`001-pnpm-test-watcher`, a Bash prefix-vs-exact matcher fix), none of the 3
  RC keeps. **Below the >50% spec bar.**
- **The confirmation re-run worked:** 2 `confirmation_failed` rejections caught
  noise-driven keeps the single-shot v0.5.0 loop would have committed (+2
  held-out-regression rejections).
- **Why 0%:** reproducibility is gated by *target selection*, not just the keep
  decision. In this run's baseline `006`/`007` scored 10.0 (saturated → never
  targeted) and `003` was targeted but yielded no passing edit — same code,
  different scores (±3-pt baseline noise). The confirmation re-run hardens the
  keep *decision* but runs *after* target selection, so it can't make the
  rotation pick the same fixtures. **v0.6 input:** noise-robust target selection
  (multi-sample the baseline, or fix targets) is the missing piece for
  reproducible keep-sets.
