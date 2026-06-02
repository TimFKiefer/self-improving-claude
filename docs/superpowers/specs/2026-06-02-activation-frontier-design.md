# v0.6.0 — Activation Frontier (design spec)

**Date:** 2026-06-02
**Status:** approved design, pre-plan
**Theme:** Self-improve the skill's *trigger* (the `description` frontmatter), not just its body — closing VISION.md's Frontier 1 (Activation) alongside the already-built Frontier 2 (Output quality).

> Grounded in `docs/knowledge/`: citations appear inline as `(doc §n)`. The load-bearing
> ones are `plugins-and-skills.md §4` (descriptions drive model-invocation),
> `prompt-engineering.md §8` (the SkillOpt disciplines + verifier wall),
> `eval-methodology.md §3/§Variance` (grader design + the noise lesson),
> `hooks-and-sdk.md §9` (the SDK/`--print` JSON message stream), and
> `agentic-patterns.md §2d` (evaluator-optimizer).

---

## 1. Goal

Extend the autonomous loop (`evals/auto_loop.py`) so that a **single run optimizes two
axes**:

- **Axis A — Output quality (existing):** edits `_shared/orchestrator-procedure.md`, scored
  on the rubric fixtures (`evals/fixtures/001–018`). Unchanged.
- **Axis B — Activation (new):** edits the `description:` frontmatter of `/improve` and
  `/improve-init`, scored on new **activation fixtures** by *really running Claude and
  deterministically detecting whether the skill fired*.

VISION.md: *"A skill that never fires is worthless, no matter how good its output."* Today the
loop only optimizes output. v0.6.0 makes activation a first-class, deterministically-gated
metric.

## 2. Locked decisions (from brainstorming)

1. **What we optimize:** the `description` as a *model-invocation decision* — "given prompt
   X, should this skill fire?" This is exactly what the description is for: skills are
   "lazily activated — only the `description` is visible until the skill is invoked via the
   `Skill` tool or typed as a slash command… `description`: used by the model to decide when
   to invoke" (plugins-and-skills.md §4).
2. **How we measure:** *real sandbox + deterministic firing detection.* No model judge in the
   gate (prompt-engineering.md §8.6, the verifier wall).
3. **Axis scope:** *dual-axis in one run.*
4. **Which descriptions:** *both* `/improve` and `/improve-init`.

## 3. The clean-separation insight

The two axes are **cleanly separable**, so we do *not* run both suites every iteration:

- The **rubric sandbox** invokes the skill by *typing* `/improve` (deterministic) — the
  `description` line is inert metadata there. **Description edits cannot move rubric scores.**
- The **activation sandbox** short-circuits the skill at the *invocation decision*, before the
  procedure runs — **procedure edits cannot move activation scores.**

Therefore each axis's edits are gated on **its own suite only**. Per-iteration cost stays
~unchanged from today, and per the verifier wall (§8.6) each axis gets a clean deterministic
gate with no cross-axis noise. "Both axes in one run" means a single `auto_loop` invocation
*interleaves* the two edit types across its iterations.

> **Validated by Task 0 (spike):** edit a description, confirm rubric scores don't move; edit
> the procedure, confirm activation scores don't move. If the isolation assumption fails, fall
> back to running both suites with cross-axis regression checks (more cost, more noise).

## 4. Architecture

```
auto_loop (one run, interleaved)
│
├── pick_target  → chooses an AXIS + a headroom target from a unified pool
│
├── if OUTPUT target:                      (today's path, unchanged)
│     edit_proposer (procedure edit)
│     → run rubric suite (evals/run sandbox)
│     → ratchet on rubric metrics
│
└── if ACTIVATION target:                  (new)
      edit_proposer (clause-level description edit)
      → run activation suite (activation_runner, N-sampled)
      → ratchet on activation metrics
```

The runner is a strict **workflow** (agentic-patterns.md §2d/§5): prepare fixture → run
scenario → detect firing → score. The loop as a whole is the **evaluator-optimizer pattern at
offline-eval scope** (agentic-patterns.md §2d) — now two evaluator-optimizers sharing one
driver.

## 5. Activation fixtures (new fixture type)

Stored separately from output fixtures (different shape + scoring):
`evals/activation/dataset.json` + `evals/activation/<id>/`.

Each entry:

```json
{
  "id": "a01-just-saw-footgun",
  "skill": "improve",
  "label": "fire",
  "scenario": "activation/a01-just-saw-footgun/scenario.md",
  "tier": "headroom",
  "rotation": true,
  "holdout": false,
  "reference_fix": "reference_fix.json"
}
```

- `scenario.md` — the conversation/prompt handed to Claude (a realistic context). For a
  **fire** fixture the situation clearly warrants the skill (e.g. Claude just did something
  the user obviously wants prevented). For a **no-fire** fixture it's an unrelated request
  (e.g. "help me refactor this function") where the skill must stay silent — the **restraint**
  of the activation axis.
- Built per eval-methodology.md §2 (self-contained, committable; generated with Haiku then
  curated) and the be-specific/XML-structure disciplines (prompt-engineering.md §3–§4).

**Target:** ≥10 fixtures, balanced fire/no-fire, ≥2 held-out, covering both skills, each
carrying a `reference_fix.json` answer key (a known-good description tweak proving the fixture
is closable — the v0.5.2 reference-fix A/B discipline).

## 6. Measurement — deterministic firing detection

`evals/activation_runner.py`:

1. **Prepare** a sandbox with the plugin loaded (reuse `sandbox_runner.py`'s plugin-load path
   — the v0.4 harness already drives the real skill via `claude --print`).
2. **Run** the scenario as the prompt — *without* typing `/improve` — via
   `claude --print --output-format stream-json` (equivalently the Agent SDK `query()`; both
   emit "a stream of JSON message events (tool calls, tool results, Claude's text)" —
   hooks-and-sdk.md §9). Restrict tools so the meaningful action is whether the model invokes
   the skill (`allowedTools` includes `Skill`).
3. **Detect** deterministically: scan the message stream for a `Skill` tool-call naming the
   target skill (`improve` / `improve-init`).
4. **Short-circuit** the full orchestrator: a `PreToolUse` hook with matcher `Skill` records
   the invocation and exit-2 blocks it (hooks-and-sdk.md §4–5). We capture the model's
   *decision to invoke*, not an expensive full run.
5. **Default deciding model: haiku** (eval-methodology.md §5: Haiku-class for eval roles),
   configurable to opus/sonnet + max effort for trustworthy keep runs (the §Variance fidelity
   config).

### N-sampling (the variance lesson)

A fixture's outcome is a *stochastic* invocation decision — a Bernoulli draw. The v0.5.1
variance lesson (single-shot ±3pt; the haiku 50-iter keeps that all reverted —
eval-methodology.md §Variance) applies doubly. So each fixture runs **N times** (N=3 in-loop,
N=5 calibration — mirrors `calibrate.py`), scored as a **firing-rate** ∈ [0,1] rather than one
coin-flip. A smooth rate gives the ratchet a usable gradient.

## 7. Metric design (classified per the verifier wall §8.6)

Each fixture scores 0–10 like every code-grader check (eval-methodology.md §3: "each check
returns 0 or 10… mean across checks"), here derived from the firing-rate:

| Metric | Type | Definition |
|---|---|---|
| `activation_score` | **gating (deterministic)** | mean over fixtures of `rate` (fire) / `1−rate` (no-fire), ×10 |
| `false_positive_rate` | **gating (deterministic)** | mean firing-rate over **no-fire** fixtures (roadmap exit: < 10%) |
| `activation_judge` | advisory only | a model "should it fire?" opinion — flags candidates, never gates (§8.6) |

`evals/grade_activation.py` computes these; results split visible/held-out like the rubric
metrics.

## 8. Loop integration

Grounded in the SkillOpt disciplines (prompt-engineering.md §8):

- **Allowlist (§8.4 slow-state):** `auto_loop.SLOW_STATE_ALLOWLIST` += `_shared/preambles/improve.md`,
  `_shared/preambles/improve-init.md`. Slow-state, eval-gated edits — exactly what §8.4
  sanctions. `sync_skills.py` regenerates the `SKILL.md` (the existing `SYNC_AFFECTED_PATHS`
  already covers preambles); the pre-commit `--check` keeps the slow-state boundary structural.
- **Bounded edits (§8.1):** the proposer makes *clause-level* add/replace edits to the
  `description:` line — **never** a full rewrite (a full rewrite of a working description is
  the "catastrophic forgetting" §8.1 warns against). Keeps the description tight (§8.2).
- **Axis-aware `pick_target`:** the eligible pool unifies output-headroom *and*
  activation-headroom fixtures. An activation target ⇒ description edit + activation suite; an
  output target ⇒ procedure edit + rubric suite (unchanged).
- **Held-out + reject ties (§8.3):** ≥2 held-out activation fixtures, invisible during
  iteration; `strictly_better` / `regresses` extended to the activation metrics.
- **Confirmation re-run (v0.5.1):** `confirmation_verdict` generalizes per-axis — a keep holds
  in the majority of re-measurements AND held-out never regresses.

## 9. Calibration (reuse v0.5.2 `calibrate.py`)

Calibrate activation fixtures into the same tiers: **saturated** (already fires correctly — no
headroom, becomes a guard), **headroom** (loop fuel), **restraint** (the no-fire negatives —
over-firing guard), **brick** (quarantine). Each new fixture's `reference_fix.json` is its
answer key, applied/scored/reverted via the existing A/B harness.

## 10. Cost & caps

Per activation iteration: `N × (#headroom activation fixtures + held-out)` Claude *decisions* —
cheap because the deciding model defaults to haiku and the skill is short-circuited (no full
orchestrator run). Headroom-rotation + the existing `--max-usd` / `--max-hours` caps bound a
run. Fidelity config (sonnet/opus + max effort) reserved for trustworthy keep runs
(eval-methodology.md §Variance).

## 11. File manifest

| File | Change |
|---|---|
| `evals/activation/dataset.json` + `evals/activation/<id>/` | **new** — ≥10 fixtures (balanced, ≥2 held-out, both skills) + reference fixes |
| `evals/activation_runner.py` | **new** — sandbox run + deterministic `Skill`-tool-call detection (N-sampled), short-circuit hook |
| `evals/grade_activation.py` | **new** — firing-rate → `activation_score` + `false_positive_rate` |
| `evals/auto_loop.py` | allowlist += preambles; axis-aware `pick_target`; ratchet wiring |
| `evals/edit_proposer.py` | clause-level description-edit mode (anchored on `description:`) |
| `evals/calibrate.py` | calibrate activation fixtures (tiers + reference-fix A/B) |
| `evals/ratchet.py` | `strictly_better` / `regresses` / `confirmation_verdict` include activation metrics |
| `evals/tests/test_grade_activation.py` | **new** — firing-rate, FP rate |
| `evals/tests/test_activation_runner.py` | **new** — stream-parse detection (mocked stream) |
| `evals/tests/test_auto_loop.py` (extend) | axis-aware pick + ratchet |
| `evals/tests/test_edit_proposer.py` (extend) | description-edit validation/allowlist |
| `docs/ROADMAP.md`, `CHANGELOG.md`, `plugin/.claude-plugin/plugin.json` | v0.5.2 → 0.6.0 at tag |

## 12. Testing strategy

Deterministic units (eval-methodology.md §4 + the TDD discipline): the firing-detection parser
is tested against a **mocked** message stream (no live Claude). `grade_activation`,
axis-aware `pick_target`, and the ratchet extension are pure-function tests. The
description-edit proposer is tested for allowlist + anchor validation. Live behavior is
proven by Task 0 (spike) and the eventual payoff run — not by unit tests (§5: the eval is a
guardrail, not a green light).

## 13. Task 0 — feasibility spike (gates all build work)

Before any production code, confirm on **one hand-built fire/no-fire pair**:

1. `claude --print` (plugin loaded) **spontaneously invokes** a plugin skill from a natural
   scenario prompt (premise lowered by plugins-and-skills.md §4, but unproven in `--print`).
2. The `Skill` tool-call is **detectable** in the `--output-format stream-json` stream.
3. It is **short-circuitable** via a `PreToolUse`/matcher-`Skill` exit-2 hook.
4. The **isolation assumption** holds (description edit doesn't move rubric scores; procedure
   edit doesn't move activation scores).

If (1) fails, fall back to a **constructed-choice harness** ("here are the available skills;
which, if any, applies?") — still a real model decision, deterministically scored, but less
natural. Re-spec measurement before proceeding.

## 14. Exit criteria

- [ ] Task 0 spike passes (all four checks) **before** build work begins
- [ ] ≥10 activation fixtures (balanced fire/no-fire), ≥2 held-out, both skills, calibrated with reference-fix answer keys
- [ ] One `auto_loop` run interleaves both edit types; at least one kept description edit **and** one kept procedure edit (or demonstrably capable of both)
- [ ] `false_positive_rate` on no-fire fixtures < 10%
- [ ] Activation gates on deterministic firing only (model-judge advisory)
- [ ] All tests pass; CHANGELOG + ROADMAP updated
- [ ] `plugin.json` 0.5.2 → 0.6.0; tag annotated

## 15. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Spontaneous invocation in `--print` doesn't happen | Task 0 gate; constructed-choice fallback |
| Axis isolation assumption is false | Task 0 check #4; fallback = run both suites + cross-axis regression checks |
| Binary outcome noise | N-sampling (firing-rate) + confirmation re-run (§Variance, §8.3) |
| Adding gating metrics raises noise floor for keeps | Clean separation means activation metrics gate only activation edits; held-out + confirmation absorb residual noise |
| Cost of N-sampled live runs | haiku deciding model + short-circuit + headroom-only rotation + `--max-usd` |

## 16. Out of scope (YAGNI)

- Optimizing descriptions of any skill beyond `/improve` and `/improve-init`.
- A generic "autotune any user's project guardrails" loop (a distinct future direction; the
  engine optimizes skills-with-eval-suites, not arbitrary projects).
- Trigger optimization for hooks the plugin *generates* (that is `fire_rate`, already covered).
- Parallelizing the activation suite (agentic-patterns.md §2c: defer until measured).

## 17. Knowledge-base citations (index)

- `plugins-and-skills.md §4` — descriptions drive model-invocation via the `Skill` tool; single-sourcing in `_shared/preambles/`.
- `prompt-engineering.md §8` — bounded edits (§8.1), compactness (§8.2), held-out + reject ties (§8.3), slow/fast state (§8.4), procedural-knowledge-as-asset (§8.5), the verifier wall (§8.6).
- `eval-methodology.md §2–§5, §Variance` — fixture/grader design, 0/10 checks, Haiku graders, the single-shot variance budget + confirmation re-run.
- `hooks-and-sdk.md §4–§5, §9` — PreToolUse exit-2 block + stdin shape; the Agent SDK / `--print` JSON message stream.
- `agentic-patterns.md §2d, §5` — evaluator-optimizer; workflow-vs-agent (the runner is a workflow).
