# Capability Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **Note:** subagent dispatch in this environment failed on a 1M-context credit requirement during v0.3.4 — if it fails again, fall back to inline execution (executing-plans).

**Goal:** Add a capability benchmark (`evals/benchmark.py`) that ranks proposer models by hook-authoring *quality* — multi-sample, judged on quality-vs-planted-problem, with a leaderboard — distinct from the conformance tripwire in `run.py`.

**Architecture:** For each `model × fixture`, run N=4 proposer samples, then **one batched Sonnet judge call per cell** scores all that cell's proposals (per-sample quality = max). Aggregate to mean ± stderr per cell and a per-model leaderboard with a "within-noise" band. Reuses `assemble_prompt`/`parse_proposals` (from `run.py`) and `grade_model` (it already scores quality vs the planted problem, never the gold). `run.py` is untouched.

**Tech Stack:** Python 3.10+ stdlib (`statistics`, `math`, `argparse`), `pytest`, the existing `evals/` clients (Ollama / claude-cli). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-25-capability-benchmark-design.md`.

---

## Knowledge-base grounding (carry into the tasks)

- **`eval-methodology.md` §3** — "ask for strengths + weaknesses + **reasoning** alongside the score, otherwise the model defaults to ~6 for everything." → The batched judge prompt (Task 3) requires a one-clause `reasoning` **before** `score` for each item. Also apply the compact-JSON discipline (the v0.3.4 truncation fix) and "use Haiku-class models for graders" — we deliberately use Sonnet (stronger) for better discrimination; note the divergence.
- **`prompt-engineering.md` §4/§2** — wrap each proposal in a named XML tag (`<proposal index="i">`) so the judge can tell them apart; lead with directive instructions.
- **`agentic-patterns.md` §2c** — cells are independent and parallelizable, but "sequential is fine for v1; flag for later." Build sequential.

---

## Current-state facts (verified this session)

- `evals/grade_model.py`: `grade_model(*, proposal, planted_problem, client)` → `{valid, score|None, error, strengths, weaknesses, reasoning}`; `GRADER_MODEL = "claude-haiku-4-5-20251001"`; helpers `_extract_json`, `GRADER_SYSTEM`, `GRADER_TEMPLATE`. **No `judge_model` param yet.**
- `evals/run.py`: exports `assemble_prompt(*, mode, user_directive, fixture)` and `parse_proposals(text)`. Backend selection is inline in `main()` (not yet extracted).
- `evals/client_ollama.py`: `OllamaClient(model=...)` (ignores per-call model). `evals/client_claude_cli.py`: `ClaudeCliClient(model=...)`, respects per-call model via `_to_cli_model`.
- `evals/fixtures_lib.py`: `EVALS_DIR`, `load_dataset()`, `load_fixture(id)`.
- `evals/tests/test_grade_model.py` already defines `_FakeClientV34` (records `last_kwargs`, returns canned text).

---

## File Structure

| File | Create / Modify | Responsibility |
|---|---|---|
| `evals/clients.py` | **Create** | `make_client(spec) -> (client, model)` — build a backend client from a `"backend:model"` spec. |
| `evals/tests/test_clients.py` | **Create** | Unit tests for spec parsing / client selection. |
| `evals/grade_model.py` | Modify | Add `judge_model` param to `grade_model`; add `grade_model_batch` (the batched judge). |
| `evals/tests/test_grade_model.py` | Modify (append) | Tests for `judge_model` override + `grade_model_batch`. |
| `evals/benchmark.py` | **Create** | Pure stats (`mean_stderr`, `aggregate_cell`, `build_leaderboard`, `within_noise`) + orchestration (`run_cell`, `run_benchmark`, `main`) + leaderboard formatting. |
| `evals/tests/test_benchmark.py` | **Create** | Unit tests for stats + orchestration (mocked clients). |
| `evals/results/README.md` | Modify | "Capability benchmark" section: what it is, how to run, caveats. |

## Dependency graph

```
Task 1 (clients) ─────────────┐
Task 2 (judge_model) → Task 3 (grade_model_batch)   [same file, sequential]
Task 4 (stats) → Task 5 (orchestration)             [same file benchmark.py, sequential]
                                   (Task 5 needs 1, 3, 4)
Task 5 → Task 6 (docs + first run)
```
Phase 1 parallel-capable: `{Task 1}`, `{Task 2→3}`, `{Task 4}`. Then Task 5, then Task 6.

---

## Task 1: `make_client` shared client factory

**Files:** Create `evals/clients.py`; Test `evals/tests/test_clients.py`

- [ ] **Step 1: Write the failing tests**

Create `evals/tests/test_clients.py`:

```python
import pytest

from evals.clients import make_client
from evals.client_ollama import OllamaClient
from evals.client_claude_cli import ClaudeCliClient


def test_make_client_ollama_keeps_colon_in_model():
    client, model = make_client("ollama:gemma4:e4b")
    assert isinstance(client, OllamaClient)
    assert model == "gemma4:e4b"          # partition splits on the FIRST colon only


def test_make_client_claude_cli():
    client, model = make_client("claude-cli:claude-sonnet-4-5")
    assert isinstance(client, ClaudeCliClient)
    assert model == "claude-sonnet-4-5"


def test_make_client_rejects_specless_or_unknown_backend():
    with pytest.raises(ValueError):
        make_client("haiku")                # no backend prefix
    with pytest.raises(ValueError):
        make_client("openai:gpt-4")         # unknown backend
```

- [ ] **Step 2: Run, expect fail**

Run: `python3 -m pytest evals/tests/test_clients.py -v`
Expected: collection/`ModuleNotFoundError: No module named 'evals.clients'`.

- [ ] **Step 3: Create `evals/clients.py`**

```python
"""Build an eval backend client from a 'backend:model' spec.

Specs: 'ollama:gemma4:e4b', 'claude-cli:haiku', 'claude-cli:claude-sonnet-4-5',
'anthropic:claude-haiku-4-5-20251001'. Returns (client, model) where `model` is the
bare model string callers pass to client.messages.create(model=...).
"""
from __future__ import annotations


def make_client(spec: str):
    """Return (client, model) for a 'backend:model' spec. Raises ValueError on a
    malformed spec or unknown backend."""
    backend, sep, model = spec.partition(":")
    if not sep or not model:
        raise ValueError(f"client spec must be 'backend:model', got {spec!r}")
    if backend == "ollama":
        from evals.client_ollama import OllamaClient
        return OllamaClient(model=model), model
    if backend == "claude-cli":
        from evals.client_claude_cli import ClaudeCliClient
        return ClaudeCliClient(model=model), model
    if backend == "anthropic":
        from anthropic import Anthropic
        return Anthropic(), model
    raise ValueError(
        f"unknown backend {backend!r} in {spec!r} (expected ollama|claude-cli|anthropic)"
    )
```

- [ ] **Step 4: Run, expect pass**

Run: `python3 -m pytest evals/tests/test_clients.py -v`
Expected: 3 passed. (The `anthropic` branch isn't unit-tested — constructing `Anthropic()` needs a key. It's exercised only when that backend is selected at runtime.)

- [ ] **Step 5: Commit**

```bash
git add evals/clients.py evals/tests/test_clients.py
git commit -m "$(cat <<'EOF'
feat(eval): make_client factory — build a backend client from 'backend:model'

Shared helper so the benchmark (and later run.py) can construct any backend from a
spec string. Returns (client, model); model is the per-call model to pass through.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `grade_model` gains a `judge_model` param

**Context:** `grade_model` hardcodes `GRADER_MODEL` (Haiku). The benchmark judges with Sonnet, and `grade_model_batch` (Task 3) shares the same wiring. Add an optional override; `run.py` keeps the Haiku default untouched.

**Files:** Modify `evals/grade_model.py`; Test `evals/tests/test_grade_model.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `evals/tests/test_grade_model.py`:

```python
from evals.grade_model import GRADER_MODEL


def test_grade_model_uses_judge_model_override():
    c = _FakeClientV34('{"strengths":[],"weaknesses":[],"reasoning":"x","score":7}')
    grade_model(proposal={"form": "x"}, planted_problem="p", client=c,
                judge_model="claude-sonnet-4-5")
    assert c.last_kwargs["model"] == "claude-sonnet-4-5"


def test_grade_model_defaults_to_grader_model():
    c = _FakeClientV34('{"strengths":[],"weaknesses":[],"reasoning":"x","score":7}')
    grade_model(proposal={"form": "x"}, planted_problem="p", client=c)
    assert c.last_kwargs["model"] == GRADER_MODEL
```

- [ ] **Step 2: Run, expect fail**

Run: `python3 -m pytest evals/tests/test_grade_model.py -k "judge_model or defaults_to_grader" -v`
Expected: `test_grade_model_uses_judge_model_override` FAILS (model is always `GRADER_MODEL`).

- [ ] **Step 3: Add the param**

In `evals/grade_model.py`, change the `grade_model` signature and the `create` call:

```python
def grade_model(*, proposal: dict, planted_problem: str, client, judge_model: str = GRADER_MODEL) -> dict:
```
and
```python
    response = client.messages.create(
        model=judge_model,
        max_tokens=2048,
        system=GRADER_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
```

- [ ] **Step 4: Run, expect pass**

Run: `python3 -m pytest evals/tests/test_grade_model.py -v`
Expected: all pass (new two + existing).

- [ ] **Step 5: Commit**

```bash
git add evals/grade_model.py evals/tests/test_grade_model.py
git commit -m "$(cat <<'EOF'
feat(eval): grade_model accepts a judge_model override (default unchanged)

Lets the capability benchmark judge with Sonnet while run.py keeps the Haiku
default. Backward compatible.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `grade_model_batch` — one judge call scores a list of proposals

**Context:** The benchmark judges all of a cell's proposals in ONE call (per-(model×fixture) batching). Per `eval-methodology.md` §3, require a one-clause `reasoning` **before** the `score` per item or the judge collapses to ~6; per `prompt-engineering.md` §4, wrap each proposal in an XML tag. Apply the v0.3.4 truncation discipline (compact JSON, scaled `max_tokens`, failure → `score:None` not 0).

**Files:** Modify `evals/grade_model.py`; Test `evals/tests/test_grade_model.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `evals/tests/test_grade_model.py`:

```python
from types import SimpleNamespace as _NS
from evals.grade_model import grade_model_batch


def test_grade_model_batch_scores_in_order_and_routes_judge():
    c = _FakeClientV34('[{"index":0,"reasoning":"good","score":9},{"index":1,"reasoning":"bad","score":2}]')
    out = grade_model_batch(items=[{"a": 1}, {"a": 2}], planted_problem="p",
                            client=c, judge_model="claude-sonnet-4-5")
    assert [o["score"] for o in out] == [9, 2]
    assert all(o["valid"] for o in out)
    assert c.last_kwargs["model"] == "claude-sonnet-4-5"


def test_grade_model_batch_maps_by_index_not_position():
    c = _FakeClientV34('[{"index":1,"reasoning":"b","score":3},{"index":0,"reasoning":"a","score":8}]')
    out = grade_model_batch(items=[{"a": 0}, {"a": 1}], planted_problem="p", client=c, judge_model="x")
    assert out[0]["score"] == 8 and out[1]["score"] == 3


def test_grade_model_batch_missing_item_is_invalid_not_zero():
    c = _FakeClientV34('[{"index":0,"reasoning":"ok","score":7}]')   # index 1 omitted
    out = grade_model_batch(items=[{"a": 1}, {"a": 2}], planted_problem="p", client=c, judge_model="x")
    assert out[0]["score"] == 7
    assert out[1]["valid"] is False and out[1]["score"] is None


def test_grade_model_batch_unparseable_marks_all_invalid():
    c = _FakeClientV34("not json at all")
    out = grade_model_batch(items=[{"a": 1}, {"a": 2}], planted_problem="p", client=c, judge_model="x")
    assert all((not o["valid"] and o["score"] is None) for o in out)


def test_grade_model_batch_empty_makes_no_call():
    calls = []
    class _C:
        def __init__(self):
            self.messages = _NS(create=self._c)
        def _c(self, **k):
            calls.append(k)
            return _NS(content=[_NS(type="text", text="[]")])
    out = grade_model_batch(items=[], planted_problem="p", client=_C(), judge_model="x")
    assert out == [] and calls == []
```

- [ ] **Step 2: Run, expect fail**

Run: `python3 -m pytest evals/tests/test_grade_model.py -k batch -v`
Expected: `ImportError`/`AttributeError` — `grade_model_batch` doesn't exist.

- [ ] **Step 3: Implement `grade_model_batch`**

Add to `evals/grade_model.py` (below `grade_model`):

```python
BATCH_SYSTEM = """You are an expert reviewer of Claude Code hook proposals. \
Score each candidate against the planted problem it must solve. Be concrete and \
honest: low scores for proposals that don't solve the problem, high scores for those \
that do. Do NOT default every item to a middling 6 — spread your scores to reflect \
real differences."""

BATCH_TEMPLATE = """<planted_problem>
{planted_problem}
</planted_problem>

Score how well EACH of the {n} candidate proposals below solves the planted problem.
Judge what the proposal DOES, not how it is phrased. Scale: 10 = exactly solves it,
7-9 strong, 4-6 partial, 1-3 misses the point, 0 irrelevant.

{proposals_block}

Respond with ONLY a single-line minified JSON array — one object per proposal, in the
same order, each with "reasoning" BEFORE "score":
[{{"index":0,"reasoning":"<one clause>","score":<int 0-10>}}, ...]
No markdown fences, no prose before or after."""


def _proposals_block(items: list[dict]) -> str:
    parts = [f'<proposal index="{i}">\n{json.dumps(p)}\n</proposal>' for i, p in enumerate(items)]
    return "<proposals>\n" + "\n".join(parts) + "\n</proposals>"


def grade_model_batch(*, items: list[dict], planted_problem: str, client,
                      judge_model: str = GRADER_MODEL) -> list[dict]:
    """Score a LIST of proposals against one planted problem in a SINGLE judge call.

    Returns a list aligned to `items` by index; each:
      {"valid": bool, "score": int|None, "reasoning": str, "error": str|None}
    A missing item or an unparseable response yields valid=False/score=None for the
    affected items — never a misleading 0 (eval-methodology.md §3 + v0.3.4 fix).
    """
    if not items:
        return []
    user_msg = BATCH_TEMPLATE.format(
        planted_problem=planted_problem, n=len(items),
        proposals_block=_proposals_block(items),
    )
    response = client.messages.create(
        model=judge_model,
        max_tokens=min(4096, 256 + 200 * len(items)),
        system=BATCH_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = response.content[0].text
    try:
        parsed = json.loads(_extract_json(text))
        if not isinstance(parsed, list):
            raise ValueError("expected a JSON array")
    except (json.JSONDecodeError, ValueError) as e:
        return [{"valid": False, "score": None, "reasoning": "",
                 "error": f"batch_parse_error: {e}"} for _ in items]

    by_index = {o["index"]: o for o in parsed if isinstance(o, dict) and "index" in o}
    out: list[dict] = []
    for i in range(len(items)):
        obj = by_index.get(i)
        if obj is None:
            out.append({"valid": False, "score": None, "reasoning": "", "error": "missing_item"})
            continue
        try:
            score = max(0, min(10, int(obj.get("score"))))
        except (TypeError, ValueError):
            out.append({"valid": False, "score": None,
                        "reasoning": obj.get("reasoning", ""), "error": f"bad_score: {obj.get('score')!r}"})
            continue
        out.append({"valid": True, "score": score, "reasoning": obj.get("reasoning", ""), "error": None})
    return out
```

- [ ] **Step 4: Run, expect pass**

Run: `python3 -m pytest evals/tests/test_grade_model.py -v`
Expected: all pass (5 new batch tests + existing).

- [ ] **Step 5: Commit**

```bash
git add evals/grade_model.py evals/tests/test_grade_model.py
git commit -m "$(cat <<'EOF'
feat(eval): grade_model_batch — score a list of proposals in one judge call

Per-(model x fixture) batched judging for the capability benchmark: XML-tagged
proposals, reasoning-before-score (eval-methodology.md §3, avoids the 6-default),
index-mapped results, and per-item valid:false/score:null fallback on
missing/unparseable output (no misleading 0s).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Benchmark statistics (pure functions)

**Files:** Create `evals/benchmark.py` (stats only this task); Test `evals/tests/test_benchmark.py`

- [ ] **Step 1: Write the failing tests**

Create `evals/tests/test_benchmark.py`:

```python
from evals.benchmark import mean_stderr, aggregate_cell, build_leaderboard, within_noise


def test_mean_stderr_basic():
    mean, std, stderr = mean_stderr([10.0, 4.0, 8.0, 6.0])
    assert mean == 7.0
    assert round(stderr, 4) == round(std / 2, 4)        # n=4 -> sqrt(n)=2


def test_mean_stderr_empty_and_singleton():
    assert mean_stderr([]) == (0.0, 0.0, 0.0)
    assert mean_stderr([5.0]) == (5.0, 0.0, 0.0)        # std undefined for n=1 -> 0


def test_aggregate_cell_reports_valid_rate_and_mean():
    cell = aggregate_cell([8.0, 0.0, 7.0, 9.0], n_valid=3, n=4)
    assert cell["mean"] == 6.0
    assert cell["valid_rate"] == 0.75
    assert cell["n"] == 4
    assert cell["per_sample_quality"] == [8.0, 0.0, 7.0, 9.0]


def test_build_leaderboard_sorts_desc_and_averages_fixtures():
    cells = [
        {"model": "A", "mean": 9.0, "stderr": 0.1, "valid_rate": 1.0},
        {"model": "A", "mean": 7.0, "stderr": 0.1, "valid_rate": 1.0},
        {"model": "B", "mean": 5.0, "stderr": 0.1, "valid_rate": 1.0},
    ]
    lb = build_leaderboard(cells)
    assert [r["model"] for r in lb] == ["A", "B"]
    assert lb[0]["mean_quality"] == 8.0
    assert lb[0]["fixtures_scored"] == 2


def test_within_noise_flags_overlap():
    a = {"mean_quality": 8.0, "stderr": 0.5}
    b = {"mean_quality": 8.3, "stderr": 0.5}
    c = {"mean_quality": 8.0, "stderr": 0.05}
    d = {"mean_quality": 9.5, "stderr": 0.05}
    assert within_noise(a, b) is True
    assert within_noise(c, d) is False
```

- [ ] **Step 2: Run, expect fail**

Run: `python3 -m pytest evals/tests/test_benchmark.py -v`
Expected: `ModuleNotFoundError: No module named 'evals.benchmark'`.

- [ ] **Step 3: Create `evals/benchmark.py` with the stats functions**

```python
"""Capability benchmark — rank proposer models by hook-authoring quality.

Multi-sample (N per model x fixture), judged on quality-vs-planted-problem by a fixed
judge (default Sonnet), aggregated to a leaderboard. Separate instrument from the
conformance tripwire in run.py. See docs/superpowers/specs/2026-05-25-capability-benchmark-design.md.
"""
from __future__ import annotations

import math
import statistics


def mean_stderr(values: list[float]) -> tuple[float, float, float]:
    """Return (mean, std, stderr). std is the sample std (0 for n<2); stderr=std/sqrt(n)."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0, 0.0
    mean = sum(values) / n
    std = statistics.stdev(values) if n > 1 else 0.0
    return mean, std, (std / math.sqrt(n))


def aggregate_cell(per_sample_quality: list[float], *, n_valid: int, n: int) -> dict:
    """One (model x fixture) cell. per_sample_quality has one number per sample
    (0 for samples that produced no proposal). n_valid = samples with >=1 proposal."""
    mean, std, stderr = mean_stderr(per_sample_quality)
    return {
        "mean": round(mean, 3),
        "std": round(std, 3),
        "stderr": round(stderr, 3),
        "valid_rate": round(n_valid / n, 3) if n else 0.0,
        "n": n,
        "per_sample_quality": per_sample_quality,
    }


def build_leaderboard(cells: list[dict]) -> list[dict]:
    """Group cells by model, average cell means across fixtures, sort desc."""
    by_model: dict[str, list[dict]] = {}
    for c in cells:
        by_model.setdefault(c["model"], []).append(c)
    rows = []
    for model, cs in by_model.items():
        mean, _std, stderr = mean_stderr([c["mean"] for c in cs])
        rows.append({
            "model": model,
            "mean_quality": round(mean, 3),
            "stderr": round(stderr, 3),
            "fixtures_scored": len(cs),
            "avg_valid_rate": round(sum(c["valid_rate"] for c in cs) / len(cs), 3),
        })
    rows.sort(key=lambda r: r["mean_quality"], reverse=True)
    return rows


def within_noise(a: dict, b: dict) -> bool:
    """True if two leaderboard rows' means differ by less than 2x combined stderr."""
    band = 2 * math.sqrt(a["stderr"] ** 2 + b["stderr"] ** 2)
    return abs(a["mean_quality"] - b["mean_quality"]) < band
```

- [ ] **Step 4: Run, expect pass**

Run: `python3 -m pytest evals/tests/test_benchmark.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add evals/benchmark.py evals/tests/test_benchmark.py
git commit -m "$(cat <<'EOF'
feat(eval): benchmark statistics (mean/stderr, cell aggregate, leaderboard)

Pure functions for the capability benchmark: per-cell mean +/- stderr + valid_rate,
per-model leaderboard sorted by mean quality, and a within-noise band so small gaps
aren't over-read.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Benchmark orchestration (`run_cell`, `run_benchmark`, `main`)

**Files:** Modify `evals/benchmark.py` (append orchestration); Test `evals/tests/test_benchmark.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `evals/tests/test_benchmark.py`:

```python
import json
from types import SimpleNamespace

from evals.benchmark import run_cell


def _proposer_returning_one_env_rule():
    body = ('{"proposals":[{"form":"permissions.deny","rule":"Read(**/.env*)",'
            '"rationale":"block .env reads"}]}')
    class _P:
        def __init__(self):
            self.models = []
            self.messages = SimpleNamespace(create=self._c)
        def _c(self, *, model, **k):
            self.models.append(model)
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=body)])
    return _P()


def _batched_judge_scoring_all_8():
    """Returns score 8 for however many proposals the prompt contains."""
    class _J:
        def __init__(self):
            self.models = []
            self.messages = SimpleNamespace(create=self._c)
        def _c(self, *, model, messages, **k):
            self.models.append(model)
            count = messages[0]["content"].count('<proposal index=')
            arr = json.dumps([{"index": i, "reasoning": "ok", "score": 8} for i in range(count)])
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=arr)])
    return _J()


_ENTRY = {"id": "002-block-env-reads", "trigger": "improve-init",
          "user_args": "", "planted_problem": "block .env reads"}


def test_run_cell_samples_n_times_and_batches_one_judge_call():
    prop = _proposer_returning_one_env_rule()
    judge = _batched_judge_scoring_all_8()
    cell = run_cell(entry=_ENTRY, proposer_client=prop, proposer_model="opus",
                    judge_client=judge, judge_model="claude-sonnet-4-5", samples=4)
    assert prop.models == ["opus"] * 4         # N=4 proposer calls
    assert judge.models == ["claude-sonnet-4-5"]  # exactly ONE batched judge call
    assert cell["mean"] == 8.0                  # each sample's best == 8
    assert cell["valid_rate"] == 1.0


def test_run_cell_empty_proposals_score_zero_and_lower_valid_rate():
    class _Empty:
        def __init__(self):
            self.messages = SimpleNamespace(create=lambda **k:
                SimpleNamespace(content=[SimpleNamespace(type="text", text="not json")]))
    judge = _batched_judge_scoring_all_8()
    cell = run_cell(entry=_ENTRY, proposer_client=_Empty(), proposer_model="m",
                    judge_client=judge, judge_model="j", samples=3)
    assert cell["mean"] == 0.0
    assert cell["valid_rate"] == 0.0
    assert judge.models == []                   # no proposals -> no judge call


def test_run_cell_independent_judges_each_proposal():
    prop = _proposer_returning_one_env_rule()
    calls = []
    class _J1:
        def __init__(self):
            self.messages = SimpleNamespace(create=self._c)
        def _c(self, *, model, **k):
            calls.append(model)
            return SimpleNamespace(content=[SimpleNamespace(type="text",
                text='{"score":6,"strengths":[],"weaknesses":[],"reasoning":"x"}')])
    cell = run_cell(entry=_ENTRY, proposer_client=prop, proposer_model="m",
                    judge_client=_J1(), judge_model="claude-sonnet-4-5", samples=2,
                    independent=True)
    assert len(calls) == 2                      # one judge call per proposal (2 samples x 1 prop)
    assert cell["mean"] == 6.0
```

- [ ] **Step 2: Run, expect fail**

Run: `python3 -m pytest evals/tests/test_benchmark.py -k run_cell -v`
Expected: `ImportError` — `run_cell` not defined.

- [ ] **Step 3: Append orchestration to `evals/benchmark.py`**

Add imports at the top of `evals/benchmark.py` (below the existing `import math`/`statistics`):

```python
import argparse
import datetime as dt
import json
import os
import sys

from evals.clients import make_client
from evals.fixtures_lib import EVALS_DIR, load_dataset, load_fixture
from evals.grade_model import grade_model, grade_model_batch
from evals.run import assemble_prompt, parse_proposals

DEFAULT_MODELS = "claude-cli:haiku,claude-cli:claude-sonnet-4-5,claude-cli:opus,ollama:gemma4:e4b"
DEFAULT_JUDGE = "claude-cli:claude-sonnet-4-5"
DEFAULT_SAMPLES = 4
```

Then append the orchestration functions:

```python
def run_cell(*, entry: dict, proposer_client, proposer_model: str,
             judge_client, judge_model: str, samples: int, independent: bool = False) -> dict:
    """Run N proposer samples for one (model x fixture), judge them, aggregate.

    Per-sample quality = max valid judge score over that sample's proposals (0 if the
    sample produced none). Judging is one batched call per cell unless `independent`.
    """
    fx = load_fixture(entry["id"])
    mode = "reactive" if entry["trigger"] == "improve" else "proactive"
    prompt = assemble_prompt(mode=mode, user_directive=entry.get("user_args", ""), fixture=fx)
    planted = entry["planted_problem"]

    sample_props: list[list[dict]] = []
    for _ in range(samples):
        resp = proposer_client.messages.create(
            model=proposer_model, max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        sample_props.append(parse_proposals(resp.content[0].text))

    flat = [(si, p) for si, props in enumerate(sample_props) for p in props]
    if not flat:
        scores: list = []
    elif independent:
        scores = [grade_model(proposal=p, planted_problem=planted, client=judge_client,
                              judge_model=judge_model).get("score") for _, p in flat]
    else:
        graded = grade_model_batch(items=[p for _, p in flat], planted_problem=planted,
                                   client=judge_client, judge_model=judge_model)
        scores = [g.get("score") for g in graded]

    per_sample: list[float] = []
    n_valid = 0
    for si, props in enumerate(sample_props):
        if props:
            n_valid += 1
        sc = [scores[k] for k, (s, _) in enumerate(flat) if s == si and scores[k] is not None]
        per_sample.append(float(max(sc)) if sc else 0.0)

    return aggregate_cell(per_sample, n_valid=n_valid, n=samples)


def run_benchmark(*, model_specs: list[str], judge_spec: str, samples: int,
                  fixture_id: str | None = None, independent: bool = False) -> dict:
    entries = load_dataset()
    if fixture_id:
        entries = [e for e in entries if e["id"] == fixture_id]
    judge_client, judge_model = make_client(judge_spec)
    cells = []
    for spec in model_specs:
        proposer_client, proposer_model = make_client(spec)
        for entry in entries:
            print(f"  {spec} x {entry['id']} ...", file=sys.stderr)
            cell = run_cell(entry=entry, proposer_client=proposer_client,
                            proposer_model=proposer_model, judge_client=judge_client,
                            judge_model=judge_model, samples=samples, independent=independent)
            cell["model"] = spec
            cell["fixture"] = entry["id"]
            cells.append(cell)
    return {
        "date": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "judge": judge_spec,
        "samples_per_cell": samples,
        "independent": independent,
        "cells": cells,
        "leaderboard": build_leaderboard(cells),
    }


def _format_leaderboard(leaderboard: list[dict]) -> str:
    lines = ["", "Leaderboard (mean quality, judge-graded; indicative ± stderr):"]
    for i, r in enumerate(leaderboard):
        flag = ""
        if i > 0 and within_noise(leaderboard[i - 1], r):
            flag = "  (within noise of above)"
        lines.append(f"  {r['mean_quality']:5.2f} ± {r['stderr']:.2f}  "
                     f"{r['model']:32s} valid={r['avg_valid_rate']:.0%}{flag}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Capability benchmark for hook proposers.")
    ap.add_argument("--fixture", help="run only one fixture id")
    ap.add_argument("--independent", action="store_true",
                    help="judge each proposal in its own call (gold-standard; ~7x more judge calls)")
    args = ap.parse_args(argv)

    model_specs = [s.strip() for s in os.environ.get("BENCH_MODELS", DEFAULT_MODELS).split(",") if s.strip()]
    judge_spec = os.environ.get("BENCH_JUDGE", DEFAULT_JUDGE)
    samples = int(os.environ.get("BENCH_SAMPLES", DEFAULT_SAMPLES))

    print(f"Benchmark: models={model_specs} judge={judge_spec} N={samples} "
          f"independent={args.independent}", file=sys.stderr)
    result = run_benchmark(model_specs=model_specs, judge_spec=judge_spec, samples=samples,
                           fixture_id=args.fixture, independent=args.independent)

    out_dir = EVALS_DIR / "results" / "benchmark"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d')}-bench.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nResults written to {out_path}")
    print(_format_leaderboard(result["leaderboard"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the benchmark tests**

Run: `python3 -m pytest evals/tests/test_benchmark.py -v`
Expected: all pass (stats + the three `run_cell` tests).

- [ ] **Step 5: Smoke-check the module imports and CLI parses**

Run: `python3 -c "from evals.benchmark import main, run_benchmark, run_cell; print('ok')"`
Expected: `ok` (no import errors; confirms the `evals.run` / `evals.clients` / `evals.grade_model` imports resolve).

- [ ] **Step 6: Commit**

```bash
git add evals/benchmark.py evals/tests/test_benchmark.py
git commit -m "$(cat <<'EOF'
feat(eval): capability benchmark orchestration (run_cell/run_benchmark/main)

N proposer samples per (model x fixture), one batched judge call per cell (or
--independent), per-sample max, leaderboard with within-noise band. Reuses
assemble_prompt/parse_proposals (run.py) and the make_client factory; proposer and
judge clients decoupled. Configurable via BENCH_MODELS / BENCH_JUDGE / BENCH_SAMPLES.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Docs + first benchmark run

**Files:** Modify `evals/results/README.md`; Create `evals/results/benchmark/<date>-bench.json` (generated)

- [ ] **Step 1: Add a "Capability benchmark" section to `evals/results/README.md`**

Append a section documenting:
- **What it is:** a leaderboard ranking proposer models by hook-authoring quality — *distinct from the conformance tables above* (which are a regression tripwire, exact-match, n=1). The benchmark is multi-sample and quality-judged.
- **How to run:** `python3 -m evals.benchmark` (defaults: models `haiku,sonnet,opus,gemma`, judge `claude-sonnet-4-5`, N=4). Configure with `BENCH_MODELS`, `BENCH_JUDGE`, `BENCH_SAMPLES`; `--fixture <id>` for one fixture; `--independent` for one judge call per proposal.
- **Cost:** ~`models × fixtures × N` proposer calls + ~`models × fixtures` Sonnet judge calls (batched). Opus is premium — run deliberately.
- **Caveats (verbatim from the spec §9):** single-judge self-preference; absolute 0-10 is the judge's subjective scale (read relative ordering); batched judging mildly compresses within-cell variance (use `--independent` for a rigorous run); sample diversity is bounded by backend default temperature; n=4 is a noise band, not a CI.
- **Output:** `evals/results/benchmark/<date>-bench.json`.

- [ ] **Step 2: Commit the docs**

```bash
git add evals/results/README.md
git commit -m "$(cat <<'EOF'
docs(eval): document the capability benchmark (run, cost, caveats)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Full test sweep**

Run: `python3 -m pytest -q`
Expected: all pass, 1 integration skipped. No failures.

- [ ] **Step 4: (OPERATIONAL — quota; not a code step) First benchmark run with the Opus gate**

Run the cheaper contestants first, then gate Opus:
```bash
BENCH_MODELS="claude-cli:haiku,claude-cli:claude-sonnet-4-5,ollama:gemma4:e4b" python3 -m evals.benchmark
```
Report the leaderboard, then **get explicit user go-ahead before adding `claude-cli:opus`** (premium quota), exactly as the v0.3.4 matrix did. This step produces `evals/results/benchmark/<date>-bench.json`; commit it once the full set (incl. Opus, after approval) has run. Output is non-deterministic — do not assert exact scores.

---

## Self-Review

**Spec coverage** — every spec section maps to a task:
- §4 absolute multi-sample / models / Sonnet judge / N=4 / batched / max-per-sample → Tasks 3 (batch), 5 (sampling+max), defaults in Task 5 ✓
- §6.1 contestant/judge spec + §6.2 make_client → Task 1 ✓
- §6.3 grade_model_batch → Task 3 ✓
- §6.4 grade_model judge_model → Task 2 ✓
- §6.5 result schema → Task 5 (`run_benchmark` output) ✓
- §7 stats (mean/stderr/valid_rate/leaderboard/within-noise) → Task 4 ✓
- §8 cost + Opus gate → Task 6 Step 4 (operational) ✓
- §9 caveats → Task 6 Step 1 (README) ✓
- §10 testing → Tasks 1-5 tests ✓

**Type/name consistency:** `make_client` returns `(client, model)` (Task 1) and is called that way in Task 5. `grade_model_batch(items=, planted_problem=, client=, judge_model=)` defined in Task 3, called identically in Task 5. `aggregate_cell(per_sample_quality, n_valid=, n=)` (Task 4) called with those kwargs in Task 5. `build_leaderboard`/`within_noise` read `mean`/`stderr`/`mean_quality` consistently across Tasks 4 and 5. Cell dicts gain `model`/`fixture` in `run_benchmark` before `build_leaderboard` reads `c["model"]`/`c["mean"]`.

**No placeholders:** every code step is complete and runnable; every run step has an exact command + expected output. The only non-code step (Task 6 Step 4) is explicitly marked operational/quota and is the benchmark *run*, not authoring.

**Out of scope (per spec §11):** pairwise/Elo, multi-judge, behavioral harness, prompt-version contestants, and refactoring `run.py` to adopt `make_client` (left as a non-breaking future cleanup).

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-05-25-capability-benchmark.md`. Two options:
1. **Subagent-Driven** (REQUIRED SUB-SKILL: superpowers:subagent-driven-development) — but note subagent dispatch hit a 1M-context credit error in this environment during v0.3.4.
2. **Inline Execution** (REQUIRED SUB-SKILL: superpowers:executing-plans) — the practical fallback; Tasks 1-5 are pure code+tests (no quota), Task 6 Step 4 is the only quota step and is gated.

Which approach?
