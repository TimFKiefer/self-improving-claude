# `evals/` — measuring hook-proposal quality

This directory measures how well the `/improve` orchestrator turns observed footguns
into good Claude Code hooks. It holds **two distinct instruments** over one shared
dataset of planted-problem fixtures.

> Methodology background: `docs/knowledge/eval-methodology.md`. Baselines, the results
> tables, and their caveats live in `results/README.md`.

---

## The two instruments

| | **Conformance eval** (`run.py`) | **Capability benchmark** (`benchmark.py`) |
|---|---|---|
| Question | "Did the orchestrator still produce a *conformant* hook?" | "On average, how *good* are the hooks a model produces?" |
| Role | **Regression tripwire** — fails loudly when a prompt change breaks a fixture | **Leaderboard** — ranks proposer models by quality |
| Grader | `grade_code` — deterministic, exact-match checks (form/event/matcher/rule/rationale-keywords/script-parses/imperative-stderr) | `grade_model` / `grade_model_batch` — an LLM judge scores quality vs the planted problem |
| Samples | 1 per fixture | N per model×fixture (default 4) → mean ± stderr |
| Strength | Cheap, fast, deterministic, no API needed (gemma) | Tolerates synonyms/varied phrasing; meaningful model comparison |
| Blind spot | Penalizes a correct hook for wording (e.g. "watch mode" ≠ literal "watcher") | Subjective scale; single-judge self-preference; quota cost |

They are complementary: the conformance grade is the **autonomy-gating** signal (binary,
deterministic — suitable for a commit/reset loop); the model grade is **advisory**, for
ranking and human review. They are never blended into one number.

---

## Running them

```bash
# Conformance eval (regression tripwire)
python3 -m evals.run                                   # default: Ollama + gemma4 (free, no key)
EVAL_BACKEND=claude-cli CLAUDE_CLI_MODEL=haiku python3 -m evals.run
EVAL_BACKEND=anthropic ANTHROPIC_API_KEY=sk-... python3 -m evals.run

# Capability benchmark (leaderboard)
python3 -m evals.benchmark                             # default 4-model matrix, Sonnet judge, N=4
BENCH_MODELS="claude-cli:haiku,claude-cli:claude-sonnet-4-5,ollama:gemma4:e4b" python3 -m evals.benchmark
python3 -m evals.benchmark --fixture 008-secret-in-source
python3 -m evals.benchmark --independent               # one judge call per proposal (gold standard)
```

Backends are built from `"backend:model"` specs by `clients.py:make_client` —
`ollama:gemma4:e4b`, `claude-cli:haiku`, `claude-cli:claude-sonnet-4-5` (200k),
`claude-cli:opus`, `anthropic:<model-id>`. The benchmark pins its judge (default
`claude-cli:claude-sonnet-4-5`) while the proposer model varies.

---

## The dataset (10 fixtures)

Each entry in `dataset.json` pairs a planted problem with a fixture directory and the
`expected_hook_traits` the proposal should satisfy. Fixtures are chosen so each exercises
a *specific form / mechanism*:

| # | id | Tests | Expected form |
|---|---|---|---|
| 001 | pnpm-test-watcher | same-prefix Bash command a deny-glob can't express | command-hook · PreToolUse · Bash |
| 002 | block-env-reads | uniform path block (incl. `.env` variants) | permissions.deny · `Read(**/.env*)` |
| 003 | prisma-generated-protection | two unrelated forbidden paths (union coverage) | permissions.deny · `required_rules` |
| 004 | recursion-prevention | reasoning-heavy guardrail; method-dependent | prompt-hook **or** PostToolUse command-hook |
| 005 | format-on-write | run a formatter after edits | command-hook · PostToolUse |
| 006 | rename-callers | surface references after an identifier edit | command-hook · PostToolUse |
| 007 | git-push-warn | confirmation, not a hard block | permissions.ask · `Bash(git push:*)` |
| 008 | secret-in-source | **content**, not path — a glob can't see it | command-hook · PreToolUse · Write/Edit |
| 009 | commit-message-style | soft convention, nothing to enforce | **claude-md-note** |
| 010 | block-staging-fetch | non-file tool surface | permissions.deny · `WebFetch(...)` |

Form/mechanism coverage: command-hook (Pre & Post), `permissions.deny`,
`permissions.ask`, `prompt-hook`, `claude-md-note`, content-inspection, and a non-file
tool (WebFetch).

---

## Adding a new fixture

1. Create `fixtures/<NNN-slug>/` with:
   - `expected_traits.json` — **required** (`load_fixture` errors without it). Mirror the
     dataset entry's `expected_hook_traits`.
   - At least one signal: `chat.md` (reactive `/improve`) **or** `telemetry.jsonl`
     (proactive `/improve-init`, one JSON object per line: `{"ts","tool","args_summary"}`).
   - Optional `description.md` (planted-problem prose) and `project/` files (e.g.
     `CLAUDE.md`, manifests) for realistic context.
2. Add an entry to `dataset.json` with `id`, `trigger` (`improve`=reactive |
   `improve-init`=proactive), `user_args`, `fixture`, `planted_problem`, and
   `expected_hook_traits`.
3. Keep `expected_traits.json` and the dataset's `expected_hook_traits` **in sync** — the
   dataset copy is canonical for grading; the fixture copy is loaded for completeness.
4. `expected_hook_traits` knobs (see `grade_code.py`): `form` (string or list for
   multiple valid forms), `event` (string or list; omit for permissions), `matcher` /
   `matcher_must_include`, `rule_pattern` / `rule_pattern_must_contain`, `required_rules`
   (union-coverage across proposals), `rationale_must_mention` (substring keywords — keep
   these robust; the check is literal and will miss synonyms).
5. Verify: `python3 -c "from evals.fixtures_lib import load_fixture; load_fixture('<id>')"`
   and `python3 -m pytest evals/ -q`.

---

## Files

| Path | What |
|---|---|
| `dataset.json` | the 10 entries (planted problem + expected traits per fixture) |
| `fixtures/<id>/` | per-fixture planted inputs (chat / telemetry / project / expected_traits) |
| `run.py` | conformance eval runner (assemble → propose → parse → grade → aggregate) |
| `benchmark.py` | capability benchmark (multi-sample → batched judge → leaderboard) |
| `grade_code.py` | deterministic conformance grader |
| `grade_model.py` | LLM quality judge (`grade_model`, `grade_model_batch`) |
| `clients.py` | `make_client("backend:model")` factory |
| `client_ollama.py` / `client_claude_cli.py` | the two local/subscription backends |
| `results/` | committed baselines + `results/README.md` (scores, caveats); `results/benchmark/` (leaderboards) |
