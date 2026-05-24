# Capability Benchmark — Design Spec (target v0.4 / `evals/benchmark.py`)

- **Date:** 2026-05-25
- **Status:** Proposed (awaiting user review before writing-plans)
- **Relationship to existing eval:** a *separate instrument*. `evals/run.py` stays the **conformance regression tripwire** (exact-match to a narrow gold, n=1). This adds a **capability leaderboard** that ranks models on hook-authoring *quality*. Neither replaces the other.

---

## 1. Why this exists

The v0.3.4 analysis showed the conformance eval cannot answer "which model writes better hooks." It rewards exact-match to a gold shape, so it penalized Opus for writing *"watch mode"* instead of the literal keyword *"watcher"* and for splitting `.env` coverage into two rules — while the proposals were substantively fine (model grade 7-8). The conformance code-grade is a tripwire, not a capability ranking, and at n=1 per fixture its per-cell numbers are single-sample noise.

A capability benchmark answers a different question — **"on average, how good are the hooks a given model produces for these planted problems?"** — by sampling each model multiple times and scoring *quality against the planted problem* (not conformance to a gold string).

## 2. Goals

- **G1.** Rank proposer models by hook-authoring quality with a defensible average and a noise indicator (mean ± stderr over N samples), so small gaps aren't over-read.
- **G2.** Score *quality vs the planted problem*, never gold-string conformance — synonyms and richer rationales must not be penalized.
- **G3.** Keep cost controllable: a fixed judge, batched judging (~28 judge calls for the default matrix), and configurable models / N / fixtures / judge.
- **G4.** Leave the conformance eval (`run.py`) behavior unchanged.

## 3. Non-goals

- **Pairwise/Elo arena** (user chose absolute multi-sample). Future option.
- **Multi-judge / neutral-judge** ensembles to remove self-preference. Documented as a limitation; future work.
- **Behavioral/functional scoring** (does the installed hook actually fire?) — that's the v0.4 integration harness, separate.
- **Refactoring `run.py`'s** existing flow beyond extracting one shared client-factory helper.

---

## 4. Locked design decisions

| Decision | Choice |
|---|---|
| Scoring | **Absolute multi-sample quality** (0-10 vs planted problem), mean ± stderr |
| Contestants | **Models only**; default `claude-cli:haiku, claude-cli:claude-sonnet-4-5, claude-cli:opus, ollama:gemma4:e4b` (gemma = free local floor); configurable via `BENCH_MODELS` |
| Samples | **N=4** per model×fixture; configurable via `BENCH_SAMPLES` |
| Judge | **Sonnet** (`claude-cli:claude-sonnet-4-5`), fixed across all contestants; configurable via `BENCH_JUDGE` |
| Judge batching | **One judge call per (model×fixture)** scoring all that cell's proposals → ~28 calls for the default matrix; `--independent` flag falls back to one call per proposal |
| Per-sample quality | **max** over that sample's proposals (best candidate the model surfaced) |

---

## 5. Architecture & data flow

New module `evals/benchmark.py`, entry `python3 -m evals.benchmark`. Proposer and judge clients are **decoupled** — the contestant produces proposals; a fixed Sonnet judge scores them (this is what lets the gemma contestant, judged locally-impossible, still be scored by Sonnet).

```
for model in BENCH_MODELS:                      # contestant
  proposer = make_client(model)                 # e.g. claude-cli:opus  or  ollama:gemma4:e4b
  for fixture in dataset:
    samples = []                                # N proposer runs for this cell
    for i in range(N):
      raw = proposer.create(assemble_prompt(fixture), model=<contestant model>)
      samples.append(parse_proposals(raw))      # list[proposal]; may be []
    # ---- ONE batched judge call for the whole cell ----
    all_props = [(s_idx, p) for s_idx, props in enumerate(samples) for p in props]
    scores = grade_model_batch(                 # judge = Sonnet, fixed
        items=[p for _, p in all_props],
        planted_problem=fixture.planted_problem,
        client=judge_client, judge_model=BENCH_JUDGE_MODEL)
    # ---- per-sample quality = max over that sample's proposals ----
    per_sample = []
    for s_idx, props in enumerate(samples):
      sc = [scores[k] for k,(si,_) in enumerate(all_props) if si==s_idx]
      per_sample.append(max(sc) if sc else 0)   # no proposals -> quality 0, sample invalid
    cell = aggregate(per_sample)                # mean, std, stderr, valid_rate
```

`--independent` swaps the single `grade_model_batch` call for one `grade_model` call per proposal (the gold-standard, ~200-call path).

## 6. Contracts (interfaces the plan builds to)

### 6.1 Contestant / judge spec
A string `"<backend>:<model>"` — `claude-cli:opus`, `claude-cli:claude-sonnet-4-5`, `ollama:gemma4:e4b`, `anthropic:claude-haiku-4-5-20251001`. `BENCH_MODELS` is a comma-separated list; `BENCH_JUDGE` is one spec.

### 6.2 `make_client(spec) -> (client, model)` (new shared helper, `evals/clients.py`)
Parses `"backend:model"` and returns the matching client (`OllamaClient` / `ClaudeCliClient` / `Anthropic`) plus the bare `model` string. Extracted from `run.py`'s inline backend block so both can use it (run.py adoption optional, non-breaking).

**Judge wiring:** `BENCH_JUDGE` (default `claude-cli:claude-sonnet-4-5`) is parsed once via `make_client` → `(judge_client, judge_model)`. The `judge_model` string (e.g. `claude-sonnet-4-5`) is what's passed to `grade_model_batch(..., judge_model=...)`; `claude-cli` then routes that to `--model claude-sonnet-4-5`. So "BENCH_JUDGE_MODEL" used in the pseudocode = the model component of `BENCH_JUDGE`.

### 6.3 `grade_model_batch(*, items, planted_problem, client, judge_model) -> list[dict]` (new, in `grade_model.py`)
One judge call scoring a *list* of proposals against one planted problem. Judge prompt asks for a JSON array, one object per item **in input order**:
```jsonc
[{"index": 0, "score": 7, "reasoning": "..."}, {"index": 1, "score": 4, "reasoning": "..."}, ...]
```
Returns a list aligned to `items` by index. Robustness: higher `max_tokens` (scales with item count), the same compact-JSON discipline as `grade_model`, and per-item fallback — any item missing from the parsed array (or whole-response parse failure) yields `{"score": None, "valid": False, "error": ...}` for that item, never a misleading 0. Empty `items` → `[]` with no call.

### 6.4 `grade_model` change (backward-compatible)
Add optional `judge_model: str = GRADER_MODEL`; pass it to `client.messages.create(model=judge_model)`. `run.py` keeps the Haiku default untouched. Used by the `--independent` path and shared by `grade_model_batch`.

### 6.5 Benchmark result schema (`evals/results/benchmark/<date>-bench.json`)
```jsonc
{
  "date": "...", "judge": "claude-cli:claude-sonnet-4-5", "samples_per_cell": 4,
  "cells": [
    {"model": "claude-cli:opus", "fixture": "002-block-env-reads",
     "per_sample_quality": [6, 7, 6, 5], "mean": 6.0, "std": 0.71, "stderr": 0.35,
     "valid_rate": 1.0, "n": 4}
  ],
  "leaderboard": [
    {"model": "claude-cli:haiku", "mean_quality": 6.4, "stderr": 0.5,
     "fixtures_scored": 7, "avg_valid_rate": 0.96}
  ]
}
```

## 7. Statistics & leaderboard

- **Per cell:** `mean`, sample `std`, `stderr = std/√N`, `valid_rate` (fraction of N samples that produced ≥1 parseable proposal; samples with none score 0).
- **Per model:** `mean_quality` = mean of cell means across fixtures; `stderr` = std(cell means)/√(#fixtures) — a coarse between-fixture spread.
- **Leaderboard:** models sorted by `mean_quality`; the printed table marks a pair **"within noise"** when `|Δmean| < 2 × √(stderrₐ² + stderr_b²)`. Stats are *indicative, not formal hypothesis tests* — stated explicitly in the output.

## 8. Cost & the Opus gate

Default matrix: 4 models × 7 fixtures × N=4 = **112 proposer calls** (gemma local/free; haiku/sonnet/opus = 28 cloud each) + **~28 Sonnet judge calls** (one per cell). The first run **pauses for explicit user go-ahead before the Opus contestant** (premium quota), as the v0.3.4 matrix did. Everything is configurable: drop models (`BENCH_MODELS`), lower `BENCH_SAMPLES`, or subset fixtures (`--fixture`).

## 9. Caveats (documented in output + README)

1. **Single-judge self-preference.** Sonnet judges all contestants, including the Sonnet contestant — mild bias toward its own family. Accepted for v1; multi-judge is future work.
2. **Absolute 0-10 is the judge's subjective scale.** Mitigated by N=4 averaging and a fixed judge, but levels aren't calibrated truth — read *relative* model ordering, not absolute numbers.
3. **Batched judging mildly anchors a cell's samples relative to each other** (compresses within-cell variance). Cross-*model* scoring stays independent (separate calls per cell). `--independent` removes this for a rigorous run.
4. **Sample diversity depends on backend default temperature.** `claude --print` can't force a temperature, so N samples may vary less than ideal → stderr can be understated.
5. **n=4** → treat the ± as a noise band, not a precise CI.

## 10. Testing

Mocked proposer + judge clients (no real API):
- N-sample loop runs the proposer exactly N times per cell.
- `grade_model_batch` parses an in-order array, maps scores to items, and falls back to `valid:False`/`score:None` on a missing item or unparseable response (never 0).
- Per-sample quality = max over the sample's proposals; a sample with no proposals scores 0 and lowers `valid_rate`.
- `aggregate` computes mean/std/stderr/valid_rate correctly on a known vector.
- Leaderboard ordering + the "within noise" flag fire on crafted means/stderrs.
- Routing: proposer calls use the contestant model; the batched judge call uses `BENCH_JUDGE_MODEL` (Sonnet), via `grade_model`'s new `judge_model` param.
- `make_client` returns the right client type per `backend:model` spec.

## 11. Out of scope / future

Pairwise arena; multi-judge ensembles; behavioral/integration scoring; using the benchmark to gate the self-improvement loop on *prompt* versions (the design is model-only now, but `make_client` + the spec format leave room to add prompt-version contestants later).
