# Eval Suite with Headroom — Design Spec

- **Date:** 2026-06-01
- **Status:** Approved in brainstorm; awaiting user review before `writing-plans`.
- **Milestone:** Fuel for the self-improvement loop. Prerequisite that likely reshapes v0.6 — per VISION.md, *"The eval suite is the most important artifact in the system."* Version (v0.5.2 vs v0.6.0) decided at tag time.
- **Scope:** Give the auto-loop something to optimize. Build a **calibration layer** that classifies every fixture by the current orchestrator's score (saturated / headroom / brick); **retire** saturated fixtures from the rotation pool (keep them as regression guards) and triage the `003` brick; **author ~6 new "headroom" fixtures** (one per orchestrator-weakness axis), each proven mid-band *and* closable via a **withheld reference-fix A/B**; restrict the loop's target selection to headroom fixtures.
- **Companion:** the v0.5.1 reproducibility finding (`docs/superpowers/specs/2026-05-31-…`, `CHANGELOG [0.5.1]`); `docs/knowledge/eval-methodology.md` (§ Variance budget); VISION.md (§ "Evals are the fitness function").

---

## 1. Why this work exists

The v0.5.1 reproducibility run cost $113.91 and produced essentially nothing: **1 keep in 20 iterations, 0.0 aggregate movement, 0% reproducibility.** The breakdown showed why — all 20 iterations hit just 3 fixtures, two of which were dead ends:

- **6 of 8 visible fixtures are already at 10.0** (`001/004/005/006/007/009`) — saturated, nothing to improve.
- `003-prisma` sat at **0.0 across 7 attempts** — a brick the bounded-edit proposer cannot crack.
- `010-block-staging` re-measured **saturated (10.0) on 5 of 7 attempts** — noise-saturated.

You cannot run a search engine against a problem that's already solved. **The bottleneck is the suite, not the loop.** Per VISION.md: *"A weak suite produces a skill that scores 100% and still disappoints. Investing in the assertions is investing in the skill."* This work builds the missing fuel — fixtures with real, *instruction-closable* headroom — so a run can move a number.

The v0.5.1 confirmation re-run already works (it rejected 2 noise-keeps). This effort is the necessary complement: signal for it to act on.

---

## 2. Goals

- **G1 — Calibration layer.** `evals/calibrate.py` scores each fixture with the current orchestrator (N=5, median, at the loop's fidelity config) and classifies it: `saturated` (median code ≥ 8), `headroom` (3–7), `brick` (≤ 2). Tiers are written to `dataset.json`.
- **G2 — Rotation only over headroom.** `pick_target` selects only from `headroom`-tier fixtures. Saturated fixtures stay in the full eval (regression guards + held-out gate) but are never *targeted*; bricks are quarantined. No more wasted saturated-skip iterations.
- **G3 — ~6 new headroom fixtures.** One per orchestrator-weakness axis (§4.2), each authored with a **reference fix** and verified `headroom` *and* closable via the A/B (§4.3).
- **G4 — Audit the existing 12.** Saturated → `rotation:false` (kept as guards); `003` triaged (grading fixed if mis-specified, else marked `brick`); `010` drops out of rotation naturally.
- **G5 — Answer-key payoff.** Each new fixture ships a **withheld** `reference_fix` (not in the shipped orchestrator). A gated ~$100 validation run measures whether the loop moves the aggregate **≥ +1.5** and/or **rediscovers ≥ 2** reference fixes (via the `reproducibility` tool). This is the "$100 run that moves a number" proof.

## 3. Non-goals

- **No loop-eval multi-sampling.** Calibration multi-samples *once* per fixture; the loop still single-shots per iteration. De-noising the loop's per-iteration eval (the diagnosis's "Lever 4") is a separate, later effort — headroom + rotation-restriction is the higher-leverage fix and is enough to make a run productive.
- **No LLM-generated fixtures.** This round is hand-authored from the taxonomy (the calibration gate would filter generated ones, but generation is out of scope here).
- **No activation-frontier / trigger optimization** (v0.6 theme) — this is output-quality fuel only.
- **No new `grade_code` axes.** Calibration uses the existing deterministic code grade.
- **No deletion of saturated fixtures.** They remain as regression guards; only their *rotation eligibility* changes.

---

## 4. Architecture

### 4.1 Tiers + the calibration gate

A fixture's **tier** is a function of the current orchestrator's multi-sampled median code score:

| Tier | Band (median code) | Rotation? | Role |
|---|---|---|---|
| `saturated` | ≥ 8 | no | Regression guard — runs in the full eval + held-out gate; never targeted. |
| `headroom` | 3 ≤ m < 8 | **yes** | The loop's fuel. |
| `brick` | < 3 | no | Quarantined; flagged for investigation. |
| `restraint` | (n/a — `expect_no_proposal`) | no | Restraint guard (011/012); scored on the restraint axis, not a rotation target. |

Cutoffs are closed with no gap: `median ≥ 8 → saturated`, else `median ≥ 3 → headroom`, else `brick`. `classify_tier(median_code, has_expect_no_proposal) -> str` is a **pure function** (unit-tested) — a fixture with `expect_no_proposal` is always `restraint` regardless of score. Calibration runs N=5 single-fixture evals, takes the median, and classifies.

### 4.2 The taxonomy — ~6 new fixtures (one per weakness axis)

Each targets a failure mode where today's orchestrator scores *partially* (mid-band), and each is authored alongside the instruction edit that would close it:

1. **Multi-rule completeness** — a `permissions.deny` requiring 3 forbidden paths; the orchestrator reliably covers ~2. (A *calibrated* `003` — lands mid-band, not 0.) Reference fix: a procedure cue to enumerate *all* CLAUDE.md-forbidden paths.
2. **Matcher precision** — prefix-vs-exact / glob breadth where the orchestrator over- or under-matches (the `001` keep hinted here). Reference fix: a rubric line on exact-vs-prefix Bash matching.
3. **Form disambiguation** — a scenario sitting between `permissions.ask` / `.deny` / command-hook where the orchestrator picks a defensible-but-suboptimal form. Reference fix: a Step-4 decision cue (human-in-loop → `.ask`; hard-forbid → `.deny`; logic → hook).
4. **Content-vs-path** — a defect a path glob can't catch (needs content scanning), with a twist beyond the easy `008`. Reference fix: an anti-pattern note "path globs can't gate on content."
5. **Composed multi-hook** — a footgun genuinely needing *two* coordinated hooks (e.g., PreToolUse block + PostToolUse check); the orchestrator proposes one. Reference fix: an example of a composed solution.
6. **Restraint edge case** — the correct answer is a *narrow* rule; the orchestrator over-blocks (harder than `011/012`). Reference fix: a restraint cue to scope rules minimally.

Each new fixture follows the existing `dataset.json` shape (`planted_problem`, `expected_hook_traits`, optional `firing_test`) plus a fixture-dir project snapshot, exactly like the current 12.

### 4.3 The reference-fix A/B (the headroom proof)

Each new fixture dir carries `reference_fix.json` — a **bounded edit in the exact edit-proposer format** (`file`, `operation`, `anchor`, `anchor_position`, `new_content`) targeting the slow-state allowlist. Calibration verifies closability by *reusing the loop's own machinery*:

```
base = median(eval(fixture) ×N)
tier = classify_tier(base, ...)
if tier == "headroom" and reference_fix exists:
    apply_edit(reference_fix)            # reuse evals.auto_loop.apply_edit
    run_sync_skills()                    # reuse evals.auto_loop.run_sync_skills
    fixed = median(eval(fixture) ×N)
    git_reset_sync_paths()               # REVERT — the fix is never shipped
    headroom_verified = (fixed - base >= 2) and (fixed >= 8)
```

`ab_verdict(base_median, fixed_median) -> bool` (the `Δ≥2 and fixed≥8` rule) is a **pure function** (unit-tested). The reference fix is applied to the working-tree slow-state, scored, then reverted (`git_reset_sync_paths`) — it never lands in the shipped orchestrator, so the loop must *rediscover* it. This is the answer key for G5.

### 4.4 Dataset schema additions

Per `dataset.json` entry: `tier` (`saturated|headroom|brick|restraint`), `rotation` (bool, derived from tier), and — for new fixtures — a `reference_fix` pointer (`reference_fix.json` in the fixture dir). `fixtures_lib.load_dataset` reads them; absent fields default safely (`tier` absent → treated as eligible until calibrated, `rotation` absent → True).

### 4.5 Loop integration

`pick_target` gains an `eligible_ids: set[str] | None` parameter; when provided, it filters its candidate pool to those ids before the bottom-N rotation. `main` computes `eligible_ids = {e.id for e in dataset if e.tier == "headroom"}` and passes it. The full eval (visible aggregate + held-out gate) is **unchanged** — it still scores every non-retired fixture, so regressions are caught; only *target selection* narrows. (Calibration already excludes bricks, so the runtime saturation-skip and a quarantine-after-K-failures mechanism become unnecessary — noted, not built.)

---

## 5. Components & file structure

| File | Create / Modify | Responsibility |
|---|---|---|
| `evals/calibrate.py` | **Create** | Pure tier classification (`classify_tier`, `ab_verdict`, `median`) + orchestration (per-fixture N-sample eval, reference-fix A/B via reused `apply_edit`/`run_sync_skills`/`git_reset_sync_paths`), writes tiers to `dataset.json` + a calibration report. CLI: `python3 -m evals.calibrate`. |
| `evals/tests/test_calibrate.py` | **Create** | Unit tests for `classify_tier` (band boundaries), `ab_verdict` (Δ + ceiling), `median`. |
| `evals/dataset.json` | Modify | Add `tier`/`rotation` per entry; add ~6 new entries with `reference_fix`. |
| `evals/fixtures/<6 new dirs>/` | **Create** | Project snapshot + telemetry per new fixture + `reference_fix.json`. |
| `evals/auto_loop.py` | Modify | `pick_target` gains `eligible_ids`; `main` computes + passes it from dataset tiers. |
| `evals/tests/test_auto_loop.py` | Modify (append) | `pick_target` headroom-filtering tests. |
| `evals/fixtures_lib.py` | Modify | `load_dataset` surfaces `tier`/`rotation`/`reference_fix`. |
| `evals/results/README.md` + `CHANGELOG.md` + `docs/ROADMAP.md` | Modify | Record the calibration result, the new suite, and the payoff-run outcome. |

**Phasing (for the plan):** (1) calibration engine + schema + pure tests → (2) audit the existing 12 (operational run) → (3) author the 6 fixtures + reference fixes → (4) calibrate the new fixtures (operational A/B) → (5) loop integration (`pick_target`) → (6) gated payoff run + record.

---

## 6. Testing

- **Unit (in the suite, no model calls):** `classify_tier` band boundaries (7.9→headroom, 8.0→saturated, 2.0→brick, 3.0→headroom), `ab_verdict` (Δ≥2 & ≥8 true; Δ=1 false; fixed=7 false), `median` (odd/even), `pick_target` with `eligible_ids` (filters to headroom; falls back sanely if the set is empty), `load_dataset` surfacing new fields.
- **Operational (not unit-tested):** the calibration runs (audit of 12, A/B of 6) and the payoff run — validated by their reports, consistent with the project's existing decision not to unit-mock the full claude-cli chain.

---

## 7. Risks & open questions

- **R1 — Few axes may yield instruction-fixable headroom.** The orchestrator is already strong; some weaknesses may need more *capability*, not better instructions. Mitigation: the reference-fix A/B is the gate — a fixture that can't be shown closable doesn't qualify. **If < 4 of 6 qualify, that is itself the finding:** the orchestrator is near its instruction ceiling and further gains need a different lever (context, proposer, capability) — redirecting v0.6. Honest either way.
- **R2 — Calibration noise.** N=5 median can mis-tier a boundary fixture. Mitigation: bands have buffer (gap between 7 and 8); re-calibration is cheap and idempotent.
- **R3 — "Teaching to the test."** Withholding the reference fix avoids shipping the answer, but the axes must reflect *real* Claude Code hook footguns, not eval-gaming. Mitigation: the taxonomy is grounded in observed orchestrator failure modes (the v0.5.0/v0.5.1 keeps, the 003 multi-rule gap, the 001 matcher gap).
- **R4 — Cost.** ~$140 calibration (one-time infra) + ~$100 payoff run. Bounded; amortized over every future run.
- **R5 — `003` triage outcome is unknown.** It may be a grading bug (fixable) or genuinely unfixable. The calibration audit settles it empirically; either resolution is acceptable (fix grading → it may become headroom; else mark brick).

---

## 8. Success criteria (exit)

- [ ] `evals/calibrate.py` classifies all fixtures; `tier`/`rotation` written to `dataset.json`; pure logic unit-tested.
- [ ] Existing 12 audited: saturated set `rotation:false`; `003` triaged (grading fixed or marked `brick`).
- [ ] ≥ 4 of ~6 new fixtures are **verified headroom** (mid-band median + reference-fix A/B passed: Δ ≥ +2 to ≥ 8).
- [ ] `pick_target` rotates only over `headroom` fixtures; unit-tested; full eval still scores all non-retired fixtures.
- [ ] Gated payoff run completed: aggregate code **≥ +1.5** across the run **and/or** ≥ 2 reference-fix rediscoveries (measured with `evals.reproducibility`).
- [ ] Suite green; CHANGELOG/ROADMAP/results updated; version bumped + tag annotated.
