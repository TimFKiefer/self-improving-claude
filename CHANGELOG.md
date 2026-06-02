# Changelog

All notable changes to `self-improving-claude` are documented here.

## [0.6.0] — 2026-06-02 — Activation Frontier (infrastructure)

Closes VISION.md's *Frontier 1*: the loop can now self-improve the skill's **trigger**
(the `description` frontmatter), not just its body. A single `auto_loop` run (opt-in
`--activation`) interleaves two cleanly-separable axes — output quality (procedure, rubric
fixtures) and **activation** (description, new) — each gated on its own deterministic metric
(verifier wall §8.6). The dual-axis **payoff run is deferred**; this release is the validated
infrastructure (mirroring v0.5.2).

### Deterministic firing detection (live-validated)

A Task-0 spike against the real `claude` CLI confirmed the mechanism: given a natural
scenario (no `/improve` typed), the model **spontaneously invokes the skill**, and a
`PreToolUse`/matcher-`Skill` exit-2 hook **records + short-circuits** the invocation —
detection and short-circuit in one, no model judge in the gate. Findings folded in: skill
names are plugin-namespaced (`self-improving-claude:improve`); a run can invoke multiple
skills, so the hook **appends** every invocation and "fired" = the target is among them.

- `evals/activation_runner.py` — sandbox run + detection, **N-sampled** firing-rate (beats
  the per-sample Bernoulli noise per the v0.5.1 variance lesson); survives a slow/timed-out
  sample (counts as no-fire, `ACTIVATION_TIMEOUT` env-tunable).
- `evals/grade_activation.py` — firing-rate → gating `activation_score` + `false_positive_rate`.
- `evals/ratchet.py` — `strictly_better`/`regresses`/`confirmation_verdict` accept a per-axis
  metric set (`ACTIVATION_METRICS`); output defaults unchanged.
- `evals/edit_proposer.py` — clause-level `description` edit mode (preambles allowlisted).
- `evals/auto_loop.py` — `pick_dual_axis_target` (normalized cross-axis headroom),
  `run_activation_iteration` (mirrors `run_iteration`, activation-gated), opt-in `--activation`
  in `main` (default OFF → existing output-only loop byte-for-byte preserved).
- `evals/calibrate.py` — activation calibration (tiers + reference-fix A/B).

### Calibrated 12-fixture activation suite

Balanced 6 fire / 6 no-fire, both skills, 2 held-out, 6 reference-fix answer keys. Calibrated
live (opus, default effort, N=5):

- **Perfect restraint** — all 6 no-fire fixtures fired at 0.0 → **0% false-positive rate**
  (the roadmap's `<10%` exit criterion already met).
- **4 saturated** (`a01`/`a07`/`a08`/`a11` @ 1.0) — the descriptions already fire reliably on
  clear footguns + setup/harden intent (a finding: the trigger is already strong).
- **1 verified-closable headroom** (`a05` recurring-typecheck @ 0.6, reference-fix A/B passed)
  — the activation axis's loop fuel.
- **1 brick** (`a03` committed-secret @ 0.2, A/B didn't help) — quarantined for redesign.

### Deferred / follow-ups

- The **dual-axis validation run** (prove a run moves `activation_score` and/or `average_code`)
  — a v0.6.x payoff candidate.
- Thin activation axis (1 headroom) — author more borderline fire fixtures.
- `a03` brick redesign; advance the activation held-out baseline after a keep; pin the target
  file path in the activation proposer prompt (wasted-iteration robustness).

## [0.5.2] — 2026-06-02 — Eval suite with headroom (infrastructure)

Builds the fuel the loop was missing. v0.5.1 proved the *suite* was the
bottleneck (a $114 run moved nothing because the orchestrator already maxed its
test set); v0.5.2 adds a calibration layer, a harder fixture set, and restricts
the loop to fixtures it can actually improve. The payoff run (proving a run now
moves a number) is **deferred** — this release is the infrastructure.

### Calibration layer (`evals/calibrate.py`)

Classifies each fixture by the current orchestrator's N=5 median score, reusing
the loop's own gating functions (`is_saturated`/`strictly_better`) so
"calibration-headroom" means exactly "loop-improvable": `saturated` (regression
guard, never targeted) / `headroom` (the loop's fuel) / `brick` (quarantined) /
`restraint`. New fixtures additionally pass a **reference-fix A/B** — a withheld
bounded edit must provably lift the fixture to ceiling — proving closability and
leaving an answer key for the deferred payoff. CLI: `python3 -m evals.calibrate`.

### Headroom-only rotation

`pick_target` now rotates only over `headroom`-tier fixtures; saturated ones stay
in the full eval as regression guards but are never targeted — killing the
saturated-skip waste that consumed ~40% of the v0.5.1 run.

### Calibrated 18-fixture suite

- **Audit of the 12** (N=5 median, opus+max): multi-sampling revealed the suite
  is *less* saturated than the v0.5.1 single-shot run implied — **4 real headroom
  targets** (`001/002/005/006`) the noise had masked, plus 4 saturated guards and
  2 restraint.
- **6 new fixtures** (`013–018`), each grounded in a v0.5.0 reverted-keep gap.
  **2 of 6 verified-closable** (`015` matcher-completeness, `017` firing-precision
  — with answer keys); `013`/`016` came back saturated (the orchestrator already
  nails those gaps — a finding in itself); `014`/`018` bricked (below).

### Measurement-integrity fix (`_installed_ok`)

The install check did exact single-string membership of a proposal's `rule`
against the written `permissions` array — so a *correct* multi-rule proposal
(echoed as a list or newline-joined string) always scored `install_ok=False`.
This **falsely bricked `003`** (code 10, valid install). Fixed to normalize
`rule` to a list and require all present; `003` is now a saturated guard.

### Findings carried forward

- `014` is a mis-designed fixture (its path-block scenario is correctly solved by
  `permissions.deny`, not the command-hook it demanded) — drop/redesign.
- `009` is flaky (N=5 median 0.0 vs 8.33 single-shot) — investigate separately.
- `_check_rule_pattern` shares the multi-rule string-only assumption (latent) — follow-up.
- Headroom pool stands at **6 targets** (`001/002/005/006/015/017`, 2 with answer
  keys), ready for the deferred ~$100 payoff run (the v0.6.0 candidate).

### Tests

Calibration pure functions + revert-safety, `pick_target` eligibility + the
no-headroom guard, `_installed_ok` multi-rule. Suite: **272 passing.**

## [0.5.1] — 2026-06-01 — Sampling fidelity & reproducibility

Pays off the two items v0.5.0 deferred: act on the sampling-fidelity lesson, and
run the reproducibility check.

### Confirmation re-run (best-of-3)

A candidate keep must now survive a fresh re-check before commit: the visible
gain must hold in ≥2 of 3 target measurements AND held-out must never regress
across all 3 (`evals.ratchet.confirmation_verdict` + a stage in `run_iteration`).
New flag `--confirm-reruns` (default 2; `0` reproduces v0.5.0 exactly).
Confirmation measurements are recorded on each audit row. The `--max-usd` cap now
bills the confirmation re-runs that fire on a keep.

### Reproducibility check — measured, and the answer is *no* (with a precise why)

One fresh layered run from the pre-RC baseline (`15cb51e`; opus+max, 20 iter,
$113.91, 11.3h) compared to the RC keep-set via the new `evals.reproducibility`
tool (deterministic by-fixture floor + advisory judge headline):

- **0% keep-set overlap** (by-fixture 0%, judge 0%) — below the >50% spec bar.
  The run kept 1/20 (`001-pnpm-test-watcher`), none of RC's `003`/`006`/`007`.
- **The confirmation re-run did its job:** it rejected 2 noise-driven keeps the
  v0.5.0 single-shot loop would have committed.
- **Root cause (the v0.5.1 lesson):** reproducibility is dominated by *target
  selection*, which rides on a single-shot baseline measurement. `006`/`007`
  scored 10.0 (saturated → never targeted) in this run; same code, different
  scores. The confirmation re-run hardens the keep *decision* but runs *after*
  target selection. **Carries to v0.6:** the rotation/baseline needs the same
  noise-robustness the keep decision now has.

### Docs & tests

`docs/knowledge/eval-methodology.md` gains a "Variance budget" section; the
canonical fidelity command is documented in `evals/results/README.md`. New tests
cover `confirmation_verdict` (incl. the n=2 boundary), the `--confirm-reruns`
flag, the reproducibility overlap math + judge unparseable-fallback, and the
confirmation cost billing. Suite: **246 passing, 1 skipped.**

### Reproducibility note

This is one fresh run vs the RC keep-set, not a two-run gold standard — the RC
used the pre-confirmation methodology, so it measures "do RC's keeps re-emerge
under the stronger loop." A two-fresh-run comparison remains available later.

## [0.5.0] — 2026-05-29 — The Self-Improvement Loop

The project's name stops being a promise. v0.5.0 ships the auto-loop as a tagged, runnable command — `python3 -m evals.auto_loop` — with cost caps, held-out gating, and an audit log per run. Auto-discovered improvements that survive the gate land as `auto-loop[i=N]: ...` commits on `main`. Three such commits ship in this tag; four prior auto-loop kepts (across α and β attempts) were reverted after held-out re-check exposed eval-sampling variance — those reverts are the load-bearing lesson v0.5.0 delivers to v0.5.1.

### Headline result (opus + max effort, 20-iter validation)

The release-validation run discovered three real improvements:

| commit | iter | what it does |
|---|---|---|
| `c6c5bac` | 1 | Added a "Common anti-patterns worth proposing when observed" list to Step 3 — generated code, binary files, lock files, vendor/, and a `CLAUDE.md → permissions.deny` mapping cue |
| `f627357` | 2 | Added one more anti-pattern bullet — "exports without tracking call sites" (covers fixture 006-rename-callers) |
| `4915a20` | 6 | **Caught a real structural bug**: the orchestrator was outputting `"permissions-ask"` (hyphen) instead of `"permissions.ask"` (dot). Added explicit dot-notation guidance to Step 4 |

Plus β's earlier kept commit `fc8e57d` (removed misleading "uniformly across tools" from form-1 `permissions.deny`) stays on main. **Four auto-loop discoveries total** — a number from a number that went up.

**Validation:**
- In-iter held-out measurements at each kept iteration: code 3.57 → 5.00 (iter 1, +1.43), stable thereafter
- Fresh held-out re-check at opus+max post-run: code 8.57, **fixture 008 firing (fire_rate 1.0)** — a multi-axis win the haiku runs never saw
- 3 in-iter held-out rejections (iter 14, 15, 18) all caught the same multi-metric tradeoff: code +3.57 but install −0.33 → gate correctly rejected per SkillOpt §8.3

### What v0.5.0 ships (architecturally complete)

#### Auto-loop driver (`evals/auto_loop.py`)
- CLI: `python3 -m evals.auto_loop`
- Flags: `--max-iterations`, `--target-fixture`, `--rotate-bottom-n`, `--proposer`, `--skill-runner`, `--judge`, `--effort`, `--dry-run`, `--no-holdout-gate`, **`--max-usd`**, **`--max-hours`**
- Pre-flight clean-tree check; SIGINT-safe summary writer
- Rotation mode (no `--target-fixture`) picks from bottom-N visible-9 fixtures, skipping recent picks
- Saturation pre-check (`is_saturated`) skips iterations whose target is already at the ceiling

#### Bounded edit proposer (`evals/edit_proposer.py`)
- Anchor-based edits to a 3-file slow-state allowlist (`orchestrator-procedure.md`, `prompt-rubric.md`, `examples.md`)
- Operation ∈ {`add`, `delete`, `replace`}; `new_content` ≤ 8 lines (SkillOpt §8.1 edit-budget)
- Strict JSON validation; short-circuits on `confidence < 4`
- `anchor_position` only required for `add` (β anomaly fix)

#### Ratchet (`evals/ratchet.py`)
- `strictly_better(new, old)`: rejects ties per §8.3
- `regresses(new, old)`: held-out gate
- Gating metrics: `average_code` (ε=0.05), `install_rate` (ε=0), `fire_rate` (ε=0.05), `average_restraint` (ε=0)
- LLM-judge `average_model` is **advisory, never gating** (§8.6 verifier wall)

#### Audit log (`evals/audit.py`)
- Per-run dir at `prompt-lab/auto-runs/<timestamp>-<proposer>/` (gitignored)
- `iterations.jsonl` schema-validated; `summary.md` polished with decision breakdown, kept-commits list, per-fixture Δ, USD/time

#### Cost discipline (Tasks 1-5 of RC plan)
- Coarse USD estimation from token counts × per-model pricing
- `--max-usd` pre-flight + per-iter lookahead with clean abort
- `--max-hours` wall-clock cap (per-iter elapsed check via `time.monotonic`)
- `--effort` threads thinking-effort through skill-runner + judge

### What v0.5.0 did NOT ship cleanly (the load-bearing lesson)

#### The first RC run (haiku + default, 50-iter) was reverted

The initial v0.5.0 RC validation used **haiku + default effort** for the skill-runner. 50 iterations completed, 5 keeps, $40 spent, 5.13h wall-clock. All 5 kept commits passed their per-iteration held-out gates at commit time, and on inspection looked sensible.

**But fresh post-run re-checks showed the held-out had drifted significantly:**

| metric | initial held-out (start of run) | fresh re-check (post-run) | Δ |
|---|---:|---:|---|
| code | 9.0 | 6.0 | **−3.0** |
| install | 0.5 | 0.5 | 0 |
| Per-fixture 002 code | (high) | 3.33 | **collapsed** |

The in-iter gates measured held-out at 9.0 → 10.0 across all kept iterations; the fresh re-check showed 6.0. **Same code, different scores.** This is single-shot eval variance at haiku precision: ~±3 points per fixture.

**Decision: reverted all 5 haiku-RC kept commits** (`f476714` ... `e1f5625`). They might be net-positive at lower variance, but we can't confirm. The reverts preserve the discoveries in git log without committing main to uncertain changes.

#### The opus + max re-run validated the gate works at higher precision

When the skill-runner was switched to **opus + max thinking-effort**, the eval became less noisy. The 20-iter validation produced:
- 3 keeps with consistent in-iter measurements (each held-out scored stably across iterations)
- 3 held-out rejections with concrete multi-metric tradeoff signal (code +, install −)
- 11 visible-no-gain rejections (the strict-better gate)
- 3 saturation skips (where the target was already at ceiling)
- Cost: $113.91, wall-clock 8.73h

Post-run fresh re-check confirmed the 3 kept commits hold (held-out aggregate code 8.57, fixture 008 now firing — a multi-axis win). **Tagged.**

### The load-bearing v0.5.0 finding: sampling fidelity matters as much as gate discipline

α + β established that the **held-out gate** is the structural safeguard against overfit. The two RC runs revealed a second axis the spec didn't anticipate: **the gate is only as reliable as its measurements.** Single-shot evals at haiku precision have ~±3 point variance per fixture — large enough to wash out the typical per-iteration Δ that drives gate decisions.

For v0.5.1+: **N-of-K sampling at each gate** (run held-out 3× before deciding) OR **always use opus + max for gate evaluations** even when proposer + visible runs use cheaper config. The architecture supports both; the choice is a cost/precision tradeoff.

### Files changed in v0.5.0 (cumulative across α, β, RC)

#### New modules
- `evals/auto_loop.py` — driver + CLI + cost estimation + saturation + rotation + caps
- `evals/edit_proposer.py` — bounded edit proposer + anchor-based application
- `evals/ratchet.py` — pure score comparison
- `evals/audit.py` — JSONL audit log + summary writer

#### Specs / plans
- `docs/superpowers/specs/2026-05-28-v0.5.0-auto-loop-design.md`
- `docs/superpowers/plans/2026-05-28-v0.5.0-alpha-auto-loop.md`
- `docs/superpowers/plans/2026-05-28-v0.5.0-beta-auto-loop.md`
- `docs/superpowers/plans/2026-05-28-v0.5.0-release-auto-loop.md`

#### Auto-loop commits surviving on main
- `fc8e57d` — β's keep (removed "uniformly across tools")
- `c6c5bac`, `f627357`, `4915a20` — opus+max RC's keeps

#### Reverted auto-loop commits (preserved in git log)
- α: `d712ba6` (reverted by `5b0d4f0`), `cfa2ade` (reverted by `6de82c3`)
- RC-haiku: `7f1506e`, `73cb8f5`, `50a1585`, `7d64e77`, `120691f` (reverted by `f476714` ... `e1f5625`)

#### Tests
- 255 → 273 passing across v0.5.0 sub-milestones (+18 cost/cap/summary tests in RC; +14 β; +50 α)

### Why this release

VISION.md: *"The name of this project is a promise. 'Self-improving' is not a metaphor. It is a loop we intend to actually run."*

v0.5.0 makes that promise concrete:
- The loop is a tagged, runnable command
- It has run for 75+ unattended iterations across three validation runs
- It has discovered four improvements that survive both ratchet gates **and** post-run fresh re-checks
- It honestly documents the case where the gate ratcheted commits that didn't survive re-check, and the variance fix that resolved it

v0.5.1 lands sampling-fidelity discipline (N-of-K or opus-only gates). v0.6 reuses the proposer + held-out gate for description-frontmatter optimization (activation frontier). v0.7 packages the loop for unattended-overnight resume-from-crash. v0.8 generalizes to any skill, not just ours.

The name stops being aspirational. The loop is real.

## [0.4.1] — 2026-05-28

### Added
- **Held-out validation subset.** `dataset.json` entries 002, 008, 012 now carry `"holdout": true`. New `run.py --no-holdout` (iteration mode) and `--holdout-only` (confirmation mode) flags, mutually exclusive. Result JSON gains `summary_visible` and `summary_holdout` blocks alongside `summary`, so a candidate that wins on the visible 9 but regresses on the held-out 3 is now visible at-a-glance. `holdout_mode` field records which subset was actually run. Closes the SkillOpt §8.3 gap that v0.4.0 dogfooding surfaced.
- **`skill_size` advisory metric.** Each sandbox result JSON records `chars_per_invocation`, `approx_tokens_per_invocation`, and a breakdown (procedure / preamble_max / references). Non-gating — just visibility. Current baseline is ~56k chars / ~14k tokens per invocation, ~15× SkillOpt's reported median; future rounds can include deletion-only candidates with measurable size delta.
- **`plugin/skills/_shared/README.md` — slow-state declaration.** Names this directory as the canonical source; documents the slow/fast state boundary (`_shared/` vs `.claude/self-improving-claude/`); confirms `sync_skills.py` + pre-commit `--check` enforces the invariant structurally. Documentation of structure that already exists.
- **3 new tests** in `evals/tests/test_run.py` — dataset holdout split, empty-aggregation handling, skill_size live read. Total: 173 passing (was 170 at v0.4.0 tag, 170 in baseline + 3 new = 173).

### Changed
- Sandbox result filenames bumped from `v0.4.0` to `v0.4.1` in the date-prefix template. Pre-tag baselines remain at `evals/results/2026-05-28-v0.4.0-*.json` for reference.

### Held-out subset rationale
| id | type | why held-out |
|---|---|---|
| **002** (block-env-reads) | shape (permissions.deny) | tests Step-4 lightest-form discipline; haiku 6.67 code / 4 model has real headroom |
| **008** (secret-in-source) | firing (PreToolUse Bash grep) | least manipulated by recent prompt-lab work (vs 005 which was the C1 regression target) |
| **012** (one-off-bug-no-guardrail) | restraint | harder of the two restraint fixtures (still at 0 across all models); 011 stays visible as the success to extend |

### Retroactive split of the v0.4.0 release baseline

Computed from per-fixture entries in the v0.4.0 result JSONs (no re-run). For each model, the held-out fixtures are genuinely harder than the visible average — exactly what we want for a generalization test:

| model | subset | code | model | install | restraint |
|---|---|---:|---:|---:|---:|
| haiku | visible (9) | 7.33 | 6.25 | 75% | **10.00** |
| haiku | holdout (3) | 7.62 | 6.50 | 100% | 0.00 |
| sonnet 4.5 | visible (9) | 9.44 | 7.50 | 71% | 0.00 |
| sonnet 4.5 | holdout (3) | 8.33 | 6.00 | 100% | 0.00 |
| opus | visible (9) | 9.84 | 7.88 | 100% | 0.00 |
| opus | holdout (3) | 8.33 | 6.50 | 100% | 0.00 |

Notable: haiku's restraint=5 on the full set is **entirely** from the visible fixture 011 — the held-out 012 stays at 0. So when v0.5+ iterations run against `--no-holdout`, they will see visible restraint=10 and the held-out restraint=0 is the "did the gain generalize beyond the one success?" test.

### Why this patch
v0.4.0 dogfooding (the prompt-lab loop) practiced bounded edits, reject-ties, slow/fast separation, and verifier-wall discipline without enforcing them structurally. v0.4.1 lands the three SkillOpt §8 disciplines we identified as gaps:
- **§8.3 Validation gating** — held-out subset now exists; tie-rejection was already in place.
- **§8.2 Compactness** — now measured; deletion-only candidate rounds become possible.
- **§8.4 Slow/fast state** — invariant documented (already enforced by `sync_skills.py`).

This unblocks v0.5 Path A: an automated edit-proposer can now iterate against the visible 9 and consult the held-out 3 for the confirmation gate.

### Not in v0.4.1 (still deferred)
- **Composed PostToolUse + Stop hooks** — v0.5 candidate per ROADMAP. The Path A loop may surface this form automatically.
- **Auto-collect Stop hook for pattern detection** — v0.5 candidate.
- **Edit-proposer agent** — the v0.5 brainstorm.
- **Compactness gating** — once we have a few rounds of `skill_size` deltas to calibrate, a "size doesn't grow without a measurable score gain" policy becomes feasible. v0.4.2 if dogfooding surfaces a need.

## [0.4.0] — 2026-05-28

### Added

#### Track 6 — Eval integrity (the autonomy gate)
- **Real-skill sandbox harness.** `python3 -m evals.run --sandbox` drives the actual `/improve` / `/improve-init` slash commands via `claude --print` against an isolated project sandbox per fixture. The eval now measures *what we ship*, not a `prompt_template.md` proxy. Configurable proposer / judge / effort via `SANDBOX_MODEL` / `SANDBOX_JUDGE` / `SANDBOX_EFFORT` env vars (Claude models only). New per-fixture aggregation: `code_max`, `code_mean`, `clean_rate`, `n_proposals`, `install_rate`.
- **`fire_rate` metric — hooks must actually fire.** `grade_behavior.run_firing_check` installs each generated command-hook into a fresh sandbox, then constructs a triggering stdin envelope and a clean envelope from the hook's chosen event/matcher. A hook scores `fired = true` only if the triggering envelope exits 2 (blocking) AND the clean envelope exits 0. Fixtures 001/005/006/008 carry firing-test payloads.
- **Restraint fixtures (011 + 012).** First negative fixtures — `expect_no_proposal` semantic. Fixture 011 (no-overblock-deny) and 012 (one-off-bug-no-guardrail) score `restraint = 10` when the model correctly declines to propose, `0` when it pushes a guardrail anyway. Closes a known gap from v0.3.x (the eval previously only graded proposed hooks, rewarding any output regardless of whether the situation warranted one).
- **Stdin-envelope check (`grade_code.stdin_envelope`).** Flags command-hooks that read the wrong fields (`tool`, `args`) instead of the actual Claude Code envelope (`tool_name`, `tool_input`). The single most common silent-failure mode for generated hooks.
- **Capability benchmark.** Separate cross-model proposal-quality leaderboard (`evals/results/benchmark/`). 4-model baseline (gemma / haiku / sonnet / opus). Sets the bar for honest cross-model comparison; canonical runs use extended thinking + max effort + opus judge.

#### Track 7 — Knowledge re-grounding + single-source
- **`scripts/sync_skills.py` — single-source skill generator.** `plugin/skills/_shared/` is now the canonical source (orchestrator-procedure.md, preambles/, references/). `python3 scripts/sync_skills.py` builds each `plugin/skills/<skill>/SKILL.md` = preamble + procedure and copies references into each skill tree. Byte-preserving — regenerating a correctly-seeded tree is a no-op. The pre-commit hook (`scripts/install-hooks.sh`) runs `--check` and fails on drift. Closes v0.4 exit criterion "references single-sourced."
- **Knowledge re-grounding into `docs/knowledge/`.** Prompt-engineering amplifiers (§2–§3): numeric anchors over adjectives; negative imperatives suppress defaults; "when to use" + "when NOT to use" pairing; the "explain why" line is the example's payload, not its caption. New §8 (optimization-loop discipline, informed by SkillOpt framing): ML-analogue mapping, bounded edits, compactness as a measurable axis, validation gating (held-out + reject ties), slow/fast state invariants, verifier wall. Updated plugins-and-skills.md.

#### Skill body — validated improvements via prompt-lab loop
- **C1′ — behavioral-trace self-check (Step 7) + rubric criterion 13.** Before finalizing any command-hook, the orchestrator constructs a triggering + clean stdin envelope from its chosen event/matcher, mentally executes the script, and confirms `return 2` for trigger and `return 0` for clean. A form-discipline guard prepended: *the trace is a validation step, not a form selector — never convert a lighter form to a command-hook to earn a "fires" check; never force a blocking PreToolUse where a lighter shape is right.*
- **Phase 1+2 — ask-first selection (Step 3.5) + persistent user preferences.** New Step 3.5 uses `AskUserQuestion` to surface candidates for selection in default mode (skipped on directive mode or single overwhelming-evidence candidate). Two-layer markdown preferences (global `${HOME}/.claude/self-improving-claude/preferences.md` + per-project `${CLAUDE_PROJECT_DIR}/.claude/self-improving-claude/preferences.md`) with `## Avoid` / `## Prefer` / `## Authorize` sections. Read at Step 2, Avoid-filter at Step 3, Prefer-bias at Step 4, Authorize honor at Step 8, capture offered at Step 10.

#### Eval & dataset polish
- **`stdin-envelope` boilerplate inlined into orchestrator Step 5.** Generated hooks read the right fields by construction. Reduces the most common no-op failure mode.
- **Lighter (non-sabotaging) sandbox override.** Default sandbox overlay no longer forces command-hook output when a lighter form would be correct.
- **Sandbox subprocess timeout handling.** A single slow run no longer kills the batch.
- **Per-call judge / effort plumbing.** `evals/client_claude_cli.py` accepts effort per-call; judge model selectable independently from proposer.

### Changed
- **Plugin version bumped to 0.4.0** in `plugin/.claude-plugin/plugin.json`.
- **Per-run schema extended.** Sandbox result JSON now records `mode`, `proposer`, `judge`, `effort`, per-fixture `clean_rate`, restraint sub-aggregation.

### Baseline (v0.4.0 release-state, opus judge, default effort, 12 fixtures)

| proposer | code | model | install | fire | restraint |
|---|---:|---:|---:|---:|---:|
| haiku | 7.39 | 6.30 | 80% | 25% | **5.00** |
| sonnet 4.5 | 9.22 | 7.20 | 82% | 50% | 0.00 |
| opus | 9.54 | 7.60 | **100%** | 40% | 0.00 |

Results: `evals/results/2026-05-28-v0.4.0-sandbox-{haiku,claude-sonnet-4-5,opus}.json`.

Not directly comparable to v0.3.x — the v0.4 sandbox eval measures behaviors the v0.3 shape eval couldn't see (real install path, real firing, restraint floor). The prompt-lab loop's pre-Phase-1+2 numbers (preserved at `prompt-lab/rounds/C1prime-run2/`) are the intra-v0.4.0 reference if you want to attribute gains to the loop itself.

### Why this release
v0.4.0 is "Foundation for Autonomy" per `docs/ROADMAP.md`. Two coupled pieces:

1. **The eval is finally trustworthy enough to gate a Karpathy-style auto-improve loop.** The sandbox runs the real skill against real fixtures and verifies hooks actually fire; restraint fixtures catch over-proposing; the stdin-envelope check catches the most common silent-failure mode. Until v0.4, "code grade went up" could mean a wrong-form proposal looked right on paper — now the metric reflects what would actually install and fire.
2. **The skill body shows measurable gains from a hand-run version of that loop.** The prompt-lab journey (C1, C1′, C2, C3, then Phase 1+2) demonstrated the loop pattern on real candidates with real keep/reject decisions. C1′ (behavioral-trace + form-discipline guard) was kept based on N=2 confirmation. C2 (negative example) and C3 (imperative opening) were rejected on no-positive-signal. Phase 1+2 was added separately as user-experience scope and the v0.4.0 release baseline confirms it improves on every model.

That second piece is *evidence* the v0.5 Path A loop is realistic — not just an abstract roadmap commitment. v0.4.1 will land the held-out validation subset and compactness tracking (the SkillOpt disciplines we don't yet enforce structurally); v0.5 brainstorm picks up the edit-proposer agent that automates what we did manually in prompt-lab.

### Not in v0.4.0 (deferred)
- **Composed PostToolUse + Stop hooks** — moved from "v0.4 headline" to v0.5 candidate during the vision-first reprioritization (see ROADMAP). The Path A loop may surface this form automatically by editing the procedure.
- **Held-out validation subset** — queued for v0.4.1. Without it, every "kept" edit is partially overfit to the visible 12 fixtures.
- **Compactness as a measured axis** — queued for v0.4.1. Current skill body is ~6× SkillOpt's reported median; a deletion-only candidate round is overdue.
- **Auto-collect Stop hook for pattern detection** — moved to v0.5 candidates.

## [0.3.4] — 2026-05-24

### Fixed
- **Code grade no longer rewards shape.** Non-applicable checks return `None` and are excluded from the mean (applicable-checks denominator), so a wrong-form or no-op proposal can't collect free points (`evals/grade_code.py`). Surfaced and fixed a latent bug where `permissions.ask` was penalized by the sentinel check (masked by the old free-N/A-pass scheme).
- **`imperative_stderr` scores intent, not exact tokens.** Accepts a clause-leading imperative verb ("Fix the reported issues before continuing.") in addition to the v0.3.1 tokens — still a binary pattern match per the founding doc.
- **Model grade stops counting truncation as 0.** `grade_model` asks for compact JSON, raises `max_tokens` to 2048, and returns `{valid:false, score:null}` on parse failure; `run.py` excludes invalid grades from averages.
- **Fixtures 002/003/004 reconciled with their planted problems.** 002 → `Read(**/.env*)` (covers `.env.local`); 003 → `required_rules` covering both forbidden paths (graded by union coverage); 004 accepts prompt-hook OR PostToolUse command-hook. Ends the code-10/model-3 contradiction where the gold failed its own planted problem.

### Changed
- **Grader pinned to Haiku for every run; `claude-cli` respects the per-call model.** Frontier columns are now graded by one model (comparable + reproducible); the proposer model is what varies. Corrects the README's prior "same-family grading" claim.
- **Aggregation adds `code_mean`, `clean_rate`, and per-fixture `coverage`** alongside the max headline, so noisy proposal sets and partial multi-rule coverage are visible. Code and model grades are reported separately (never blended) — the deterministic code grade is the autonomy-gating metric; the model grade is advisory.
- **Full-matrix baseline re-scored** under the new semantics (`evals/results/2026-05-24-v0.3.4-*.json`). Not directly comparable to ≤v0.3.3 (scoring semantics changed).

### Why this release
v0.3.3 was measurement *hygiene*; v0.3.4 is measurement *correctness* — it makes the eval score trustworthy enough to gate the autonomous Karpathy loop the project is built around (commit-if-better / reset-if-worse). The structural enforcement primitive remains v0.4.

## [0.3.3] — 2026-05-24

### Fixed
- **`imperative_stderr` grader was blind to f-strings, bash, and JS.** v0.3.2's extractor matched only plain-string `print(..., file=sys.stderr)`, so it returned "n/a (pass)" for f-string stderr (the idiom Example 4 itself uses), `echo >&2`, and `console.error` — meaning a passive message hidden in an f-string was a silent false-pass. Replaced with a per-language literal extractor (`evals/grade_code.py`), with per-call Python isolation so an adjacent stdout `print` can't bleed into the scan. 7 new tests.
- **Dangling `@references/settings-merge.md` in `/improve-uninstall`.** That skill has no `references/` dir (leftover from v0.3's shared→inline pivot); the merge discipline is now described inline.

### Added
- **`claude-cli` eval backend (`EVAL_BACKEND=claude-cli`).** Productizes the throwaway `/tmp/eval_via_cli.py` as `evals/client_claude_cli.py` (mirrors `OllamaClient`), so the Haiku/Sonnet/Opus baselines are reproducible with no `ANTHROPIC_API_KEY` (subscription OAuth). 5 mocked-subprocess tests.
- **Discriminating telemetry fields.** `Notification` rows now carry `kind` (`waiting_for_permission` | `idle` | `other`), `PreCompact` rows carry `reason`, `SessionStart` rows carry `source` — delivering the §3.5 signal the README already advertised. Defensive classification (degrades to `other`/`""`). 6 new tests.

### Changed
- **Re-scored the dataset** with the fixed 8-check grader (first re-score since v0.3.0) — `evals/results/2026-05-24-v0.3.3-gemma.json` (gemma 6.1 code / 3.7 model). The dip vs v0.3 gemma (7.1) is gemma JSON truncation on fixtures 003+004 this run, not a regression — `imperative_stderr` scored 10 on all 5 parseable proposals. Results README documents this and the 8-check grader; reproduction note moved off `/tmp`.

### Why this is a hygiene release
v0.3.2 declared the text-discipline lever spent ("as strong as text alone can be"). v0.3.3 makes that work *measurable and reproducible* — it fixes the leaky check that would have mis-measured it, commits the backend that produces the frontier numbers, and captures the telemetry signal v0.4 needs. No new architecture. The structural fix (composed PostToolUse + Stop hooks) remains v0.4.

## [0.3.2] — 2026-05-24

### Added
- **Eval grader `imperative_stderr` (8th deterministic check).** New code-grader function in `evals/grade_code.py` that pattern-matches stderr text in command-hook scripts: catches banned phrasing (`audit`, `consider`, `verify`, `review`, `or X is unrelated`) and requires action-forcing phrasing (`REQUIRED FOLLOW-UP`, `Do not stop`, `Fix each`, `BLOCKING`, `Do not ask`) on non-blocking events. Event-aware: blocking events (PreToolUse / Stop / SubagentStop / UserPromptSubmit) only need to avoid banned phrasing since the hook actually halts the model; non-blocking events (PostToolUse and others) need at least one required phrase too. 6 new unit tests in `test_grade_code.py`. Total grader checks: 8 (was 7). This lets future baseline reruns MEASURE whether the v0.3.1+v0.3.2 stderr discipline actually improves proposal quality, instead of relying on dogfooding signal.
- **Concrete bad/good stderr pairs** appended to rubric criterion 12. Three side-by-side examples in each direction, plus a pattern note: "lead with `REQUIRED FOLLOW-UP` or `BLOCKING`, name the action verb explicitly, close with `Do not stop` / `Do not ask`. Brevity beats argumentation."
- **Step 4 inline gate referencing criterion 11.** Before selecting form 5 (PostToolUse), the procedure now explicitly requires applying the enforcement-shape check. Catches the misfit at form-selection time rather than in Step 6 post-hoc self-critique.
- **Hook-patterns.md PostToolUse limitation footnote** in both dual-copies. Documents the "exit-2 stderr is information not imperative" gotcha right where someone reads the docs.

### Changed
- **Step 7 made deterministic.** v0.3.1 introduced a subjective behavioral check ("would I, reading only this, continue or ask?"). v0.3.2 replaces it with a pattern-matching check on the literal stderr strings: banned-phrase scan + action-phrase requirement (for non-blocking events). Pattern matching is more reliable than self-introspection. Added a retry loop (cap 2) — failed stderr triggers revision per criterion 12 instead of silent drop.
- **Example 4 stderr tightened further.** v0.3.1 used a 3-sentence imperative including the contextual justification "installing this hook authorizes the scope". v0.3.2 shortens to bare imperatives: `BLOCKING: ... Fix each. Do not stop. Do not ask.` Justifications invite disagreement; bare imperatives don't. The "Why it's good" note updated to teach this brevity principle.

### Why these are all small fixes
This release is the prompt-engineering-knowledge-applied retrospective on v0.3.1. The same root failure mode (v0.2 form-selection bias, addressed by v0.3.1 with criteria 11 + 12) gets a tighter set of guardrails: examples in the rubric (show-don't-tell), check at form-selection (process steps), deterministic Step 7 (no self-introspection), eval grader (measurement before iteration). All gaps relative to the project's own knowledge-base advice on prompt engineering.

### Not in v0.3.2
The structural fix — composed PostToolUse + Stop hooks with shared state — remains v0.4 work. v0.3.2 makes the partial-solution-via-imperative-stderr as strong as text alone can be; v0.4 will provide the real enforcement primitive.

### Optional follow-up
A baseline rerun against any backend (`python3 -m evals.run` for gemma, or `python3 /tmp/eval_via_cli.py haiku|claude-sonnet-4-5|opus` via subscription) would show the new `imperative_stderr` check in action and let the v0.3.1+v0.3.2 changes register as measurable score deltas. Not auto-run in this release — leaves quota choices to the user.

## [0.3.1] — 2026-05-24

### Fixed
- **Enforcement-shape gap** in form-selection. Dogfooding revealed that PostToolUse + grep hooks (the v0.3 form for "after editing X, show callers") pass every eval check (8.6/10 code grade) yet fail to compel action in real use: the model reads the stderr as informational and stops to ask the user, instead of acting. Root cause is two-layered: PostToolUse exit-2 stderr is *information* not *imperative*, and the proposed text used passive verbs ("Verify these are consistent") that explicitly license inaction.

### Added
- **Rubric criterion 11: Enforcement-shape check.** For rules of shape "after X, the model must do Y," the rubric now requires either a blocking form (`permissions.deny` / `permissions.ask` when a glob fits) OR an explicit rationale for why PostToolUse-alone suffices. Otherwise the proposal is asking the model to act on info — and the model may decline. Composed PostToolUse+Stop hooks are slated for v0.4 as the proper structural fix.
- **Rubric criterion 12: Imperative stderr.** Hook scripts that surface context via stderr must use action-forcing language. Required phrasing includes "REQUIRED FOLLOW-UP", "Do not stop until", "Fix each, then summarize". Banned phrasing (treated as a rubric failure): "audit", "consider", "verify these are", "review", "or X is unrelated" (the escape hatch).
- **Procedure Step 7 behavioral check.** Alongside the syntax checks (`bash -n`, `py_compile`, etc.), Step 7 now asks: "if I were Claude in auto-mode and read ONLY this stderr after my Edit, would I continue the work or would I summarize and ask?" If you'd likely ask, the message is too passive — revise before showing the user.

### Changed
- **Example 4 (`grep-export-callers`) stderr rewritten** to imperative voice: "REQUIRED FOLLOW-UP: export was edited. N references remain. Fix each (update to new value or import the constant), then summarize. Do not stop until done. Do not ask before fixing — installing this hook authorizes the scope." Replaces the previous "Verify these are consistent with your change." which was the canonical passive failure surfaced in dogfooding.
- **Example 4's "Why it's good" expanded** to explicitly teach the imperative-stderr pattern AND acknowledge the limitation: even imperative voice doesn't literally block turn-end on PostToolUse — that's what composed PostToolUse+Stop will provide in v0.4.

### Why these are text-only fixes
The deeper structural fix (composed PostToolUse + Stop hooks with shared state files, recursion-guards, re-verify-on-Stop) is deferred to v0.4. v0.3.1 reduces the failure rate by tightening proposal text discipline; v0.4 will eliminate it by enabling hooks that can actually block turn-end.

### Caveat
Dual-copy synchronization (from v0.3's inline-fallback) means rubric and procedure changes must be applied to BOTH `plugin/skills/improve/` and `plugin/skills/improve-init/` directories. v0.3.1's commit modifies four files for this reason.

## [0.3.0] — 2026-05-23

### Added
- **Marketplace install.** Repo is now a single-plugin marketplace; `claude plugin marketplace add` + `claude plugin install self-improving-claude` works for both local and GitHub paths.
- **`/improve-uninstall` slash command.** Cleanly removes the plugin's project-level footprint (sentinel entries in `.claude/settings.json`, generated hook scripts, optionally telemetry). The plugin itself stays installed.
- **`permissions.ask` as a 5th recognized guardrail form.** Built-in Claude Code prompts the user for confirmation — lighter than a prompt-hook (no LLM evaluation), heavier than `permissions.deny` (interactive). Often the right answer for "warn before X" rules like `Bash(git push:*)`.
- **Multi-event telemetry.** Bundled telemetry hook now listens on `PostToolUse`, `Notification`, `PreCompact`, and `SessionStart` (was only PostToolUse), providing richer signal for `/improve-init` to mine.
- **SessionEnd telemetry rotation.** Inline-bash hook renames `telemetry.jsonl` at session end and starts a fresh file; archives keep history without bloating the active log.
- **Feedback channel.** `/improve "the <hook> blocked something legit"` now persistently logs the complaint to `.claude/self-improving-claude/feedback.jsonl` AND modifies the named hook in-place (narrows matcher / adds exception).
- **Two new eval fixtures.** Fixture 006 (rename-callers, reactive) and fixture 007 (git-push-warn, proactive — tests the `permissions.ask` form).
- **CHANGELOG.md** (this file).

### Changed
- **Orchestrator hidden from `/` menu.** The model-invoked `self-improving-claude` skill was eliminated. The probe for `@`-mention resolution outside the skill directory FAILED, so the implementation took the **inline duplication fallback** — the 10-step orchestrator procedure is now inlined in both `plugin/skills/improve/SKILL.md` and `plugin/skills/improve-init/SKILL.md`, and references are duplicated in `plugin/skills/improve/references/` and `plugin/skills/improve-init/references/`. Future changes to the procedure or references must be applied to BOTH copies.
- **Form-selection rubric tightened.** Rubric criterion #2 explicitly emphasizes *viable* — CLAUDE.md notes are no longer treated as "lightest" when the rule needs enforcement. Procedure Step 4 now lists 5 forms in priority order, with `permissions.ask` and PostToolUse command-hook explicit (both were under-used in v0.2).
- **README rewrite.** First-time-visitor hero pitch, three-line install, trust + privacy + troubleshooting sections pointing at Claude Code's built-in commands.

### Removed
- **No more `--plugin-dir <repo-root>`.** The plugin lives at `<repo>/plugin/` now. Use `--plugin-dir <repo>/plugin` for local dev, or `claude plugin install self-improving-claude` after `marketplace add` for permanent install. (Breaking change vs v0.2 local-dev workflow.)
- Speculative auto-collect / Stop-hook pattern-detection feature **deferred to v0.4** (YAGNI — no dogfood evidence it's wanted yet).

### Fixed
- Form-selection bias bug from v0.2 dogfooding: the orchestrator slid to CLAUDE.md note whenever a hook seemed "expensive," missing both `permissions.ask` and PostToolUse command-hook as forms. Eval fixture 006 (the dogfooding case) and fixture 007 (the `permissions.ask` case) catch regressions.
- **Eval prompt template bug** (found during baseline run): `evals/prompt_template.md` did not list `permissions.ask` in the form ladder or the JSON output schema, preventing the model from selecting it in evals. Added inline during Task 9.

### Baseline notes (v0.3 vs v0.2)
- **v0.3 Haiku baseline (cloud reference):** avg code **9.0/10**, avg model **6.3/10** across 7 fixtures. Produced via the user's Claude Max subscription using `claude --print --model haiku` (no `ANTHROPIC_API_KEY` needed). File: `evals/results/2026-05-23-v0.3-haiku.json`.
- **v0.3 gemma4 baseline (local reference):** avg code 7.1/10, avg model 2.9/10. File: `evals/results/2026-05-23-v0.3-gemma.json`.
- **v0.2 baseline:** avg code 9.3/10, avg model 6.2/10 across 5 fixtures. File: `evals/results/2026-05-22-baseline.json`.
- Haiku result is essentially equivalent to v0.2 (9.0 vs 9.3 code; 6.3 vs 6.2 model) — confirms the v0.3 changes did NOT regress quality. The 2 new fixtures (006 + 007) add coverage cleanly.
- Fixture 006 (rename-callers) scored **8.6/10 with Haiku** but **0/10 with gemma4** — confirms the gemma score was a JSON-truncation limitation of the small local model, NOT a plugin defect. The plugin's form selection is correct in both cases; only gemma's JSON output for the long Python script truncated.
- Fixture 007 (`permissions.ask`) scored 8.6/10 with both backends — validates the v0.3 form-selection fix works as designed across model families.

## [0.2.0] — 2026-05-22

- Reactive `/improve` slash command (uses live chat context).
- Eval harness with 5 fixtures, code-grader (deterministic) + model-grader (Haiku).
- First scored baseline committed (gemma4 via Ollama).
- Pluggable eval backend (`EVAL_BACKEND={ollama|anthropic}`).

## [0.1.0] — 2026-05-22

- `/improve-init` proactive scan with per-proposal approval.
- Bundled telemetry hook (PostToolUse, redacted JSONL).
- Per-proposal `AskUserQuestion`-driven approval flow.
- 10-step orchestrator procedure grounded in Anthropic's Claude Code course material.
