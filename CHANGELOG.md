# Changelog

All notable changes to `self-improving-claude` are documented here.

## [Unreleased] — v0.5.0 progress

### Added (v0.5.0-α)

#### The auto-loop, end-to-end
- **`evals/auto_loop.py`** — CLI driver: `python3 -m evals.auto_loop`. Runs `propose → apply → sync_skills → single-fixture eval → ratchet → git commit-or-reset` per iteration. Single target fixture (α scope); β adds bottom-3 rotation. SIGINT-safe summary writer. Pre-flight cleanliness check refuses to start with dirty slow-state files.
- **`evals/edit_proposer.py`** — bounded-edit proposer using Claude CLI (subscription OAuth). Anchor-based edits (operation ∈ {add, delete, replace}; anchor must appear exactly once; `new_content` ≤ 8 lines per SkillOpt §8.1 edit-budget). Strict JSON validation against an allowlist; short-circuits on `confidence < 4`.
- **`evals/ratchet.py`** — pure score-comparison. `strictly_better` rejects ties per SkillOpt §8.3. `regresses` for β's held-out gate. Gating metrics: `average_code` (ε=0.05), `install_rate` (ε=0), `fire_rate` (ε=0.05), `average_restraint` (ε=0). LLM-judge `average_model` is advisory, never gating (§8.6 verifier wall).
- **`evals/audit.py`** — JSONL audit log per run at `prompt-lab/auto-runs/<timestamp>-<proposer>/` (gitignored). Schema-validated iteration records; `last_n_rejected_edits` feeds the proposer so it doesn't retry bad ideas.
- **+50 tests** across 4 new test files. Total: **223 passing** (was 173 at v0.4.1).

#### Two smoke tests validated both ratchet paths

**Run 1 — sonnet skill-runner, fixture 010, 5 iterations, 0 kept.** Sonnet already handles fixture 010 at code 10.0 / install 1.0 — no headroom. The proposer made adaptive hypotheses (i=1 in Step 7 → i=2 re-aimed to Step 4 after rejection — exactly the design intent), but couldn't find a real gap. **Validated the reject path under "no headroom" conditions.** Plus surfaced two minor anomalies for β (see below).

**Run 2 — haiku skill-runner, fixture 010, 5 iterations, 2 kept.** Haiku's baseline was code 6.67 / install 1.0 with real headroom. The auto-loop discovered two genuine improvements **before reverting** (see held-out finding below):
- `auto-loop[i=2]` (commit `d712ba6`): clarified the rubric's "bind to one event with precise matcher" applies to **hooks only**, not permissions rules.
- `auto-loop[i=5]` (commit `cfa2ade`): added a "Classify first" preamble to Step 4 distinguishing parameter-pattern rules (→ `permissions.deny`/`ask`) from computational rules (→ hooks).

**The textbook ratchet decision:** `i=4` proposed a different edit reaching the same target code score (7.14→10.0, huge gain) BUT crashed install (1.0→0.0). `strictly_better` correctly rejected. `i=5` then found the same intent expressed differently, preserving install — accepted. **SkillOpt §8.3 doing exactly what it was specced for.**

**Visible (target-fixture) result for run 2: code 6.67 → 10.0 over 5 iterations.** Already past one of v0.5.0's exit criteria (≥ 1.5-point gain on at least one fixture).

#### α's load-bearing finding: held-out gate is essential

Post-run-2 manual held-out check (haiku, fixtures 002 / 008 / 012):

| metric | pre-auto-loop (v0.4.1 retroactive) | post-auto-loop held-out | Δ |
|---|---:|---:|---:|
| code | 7.62 | **9.00** | **+1.38** |
| model | 6.50 | **8.50** | **+2.00** |
| install | **1.00** | **0.50** | **−0.50** ❌ |

Per-fixture: **008-secret-in-source install dropped from 1.0 to 0.0.** The "classify first" edit (i=5) optimized fixture 010 (where `permissions.deny` is right) but caused haiku to misclassify 008 (where `command-hook` is right — the rule is content-scanning, not parameter-pattern). **Textbook overfitting** — exactly the failure mode β's held-out gate is designed to prevent.

**Decision:** **reverted both auto-loop commits** (`5b0d4f0` reverts `d712ba6`, `6de82c3` reverts `cfa2ade`). The kept-edit history stays in git log as evidence the loop works mechanically; the reverts keep main clean of un-gated edits. **β implements `regresses(new_holdout, old_holdout)` as a hard reject before any `git commit` happens** — exactly this scenario would have been auto-rejected.

#### Minor anomalies caught by the audit log (β backlog)
- Run-1 `i=4` proposer response had `anchor_position: null` for a non-`add` operation. Strict validation in `parse_proposer_response` correctly rejected (decision: `invalid_edit (ValueError)`). β fix: only require valid `anchor_position` when `operation == "add"`.
- Sonnet ceiling case (Run 1) showed the proposer hallucinated a "WebFetch URL parsing problem" that doesn't exist for sonnet. Mitigation in β: rotation over bottom-3 fixtures + early-stop when baseline saturates on all metrics.

#### Audit artifacts (local, gitignored)
- `prompt-lab/auto-runs/2026-05-28T155620Z-sonnet/` (run 1: 5 reject)
- `prompt-lab/auto-runs/2026-05-28T161246Z-sonnet/` (run 2: 2 keep + 3 reject — captures the full overfit-then-revert story in iterations.jsonl)

### Why this matters
α is the *smallest viable* cut of the auto-loop and it ran end-to-end on real fixtures. It proved:
1. The loop **mechanics work** — propose, apply, sync, eval, ratchet, audit all wired together.
2. The proposer is **adaptive** — Run 1's i=1→i=2 re-aim after rejection.
3. The ratchet **catches multi-metric trade-offs** — Run 2's i=4 rejection for install regression.
4. The loop **can discover real improvements** — Run 2's i=2 and i=5 made genuinely useful edits (now reverted but the audit log preserves them).
5. **Without a held-out gate, the loop overfits** — Run 2's improvements broke fixture 008's install in the held-out check.

(5) is the critical lesson α delivers to β. v0.5.0-β: implement the held-out gate per spec §4.1, then re-run this exact experiment and watch the gate auto-reject what we had to revert by hand.

### Notes
- α has no held-out gate, no rotation, no cost cap — those land in β / v0.5.0 per spec.
- v0.5.0 tag awaits β + 50-iteration validation run.

### Added (v0.5.0-β)

#### Held-out confirmation gate, rotation, saturation pre-check, α anomaly fix
- **`evals/auto_loop.py:run_iteration`** — gained `holdout_baseline` parameter and `holdout_gate_enabled` flag. After visible-set `strictly_better`, runs the held-out eval; on `regresses()` → True, `git checkout HEAD --` instead of `git commit`. The exact scenario α had to revert by hand is now auto-detected and auto-rejected.
- **`evals/auto_loop.py:pick_target`** — now rotates over the bottom-N (default 3) lowest-composite-score visible fixtures, skipping any in the last 2 picks. `--target-fixture` preserves α single-fixture mode.
- **`evals/auto_loop.py:is_saturated`** — short-circuits iterations where the target's baseline is at the ceiling on all gating metrics (decision: `skipped: saturated_baseline`). No proposer + eval cost wasted.
- **`evals/edit_proposer.py:parse_proposer_response`** — `anchor_position` is only required for `operation == "add"` (α anomaly fix).
- **`evals/audit.py:REQUIRED_FIELDS`** — schema extended with `scores_holdout_before`/`scores_holdout_after` (can be None when held-out wasn't run).
- **New CLI flags**: `--rotate-bottom-n` (default 3), `--no-holdout-gate` (α-compat override), `--max-iterations` default 5 → 20. `--target-fixture` becomes optional (None → rotation).
- **+14 tests** (237 passing total, was 223 at α).

#### 20-iteration β validation run — exit criteria met

Run config: rotation mode, sonnet 4.5 proposer, haiku skill-runner, opus judge.

**Decision breakdown (20 iterations):**

| count | decision |
|---:|---|
| 9 | `rejected: holdout_regression` ← **the gate fired 9 times** |
| 7 | `rejected: no_visible_gain` |
| 2 | `rejected: invalid_edit (anchor not found)` |
| 1 | `kept` ← the one that earned a commit |
| 1 | `skipped: saturated_baseline` |

5% keep rate — within SkillOpt's predicted 1–4 edits per cycle range exactly.

**Rotation worked:** 3 distinct targets visited (`007-git-push-warn` ×7, `004-recursion-prevention` ×7, `010-block-staging-fetch` ×6).

**The textbook β save — iter 1 on fixture 007:**
- Hypothesis: map "confirmation language" → `permissions.ask`
- Visible (target 007): code 5.0 → 6.67 ✅ (improvement, would have been kept under α)
- Held-out aggregate: code 10.0 → **8.33** ❌ (regression caught)
- **Decision: `rejected: holdout_regression`**
- In α, this would have been committed. In β, the gate auto-rejected it.

**The kept edit — iter 15 on fixture 010 (commit `fc8e57d`):**
Removed the phrase "uniformly across tools" from form-1 (`permissions.deny`) — the phrase was misleading because `permissions.deny` can legitimately target single-tool patterns. The clarified text is semantically tighter. **Eval-validated AND held-out-validated.** This commit stays on main — the first auto-loop deliverable to survive the gate.

### Why β matters

β is the smallest configuration that satisfies the SkillOpt §8.3 discipline end-to-end:
1. **Strict-better visible gate** ensures the loop doesn't ratchet ties.
2. **Held-out generalization gate** ensures the loop doesn't overfit (validated 9 times in a single run).
3. **Bottom-N rotation** ensures the loop doesn't chase one fixture forever (3 distinct targets).
4. **Saturation pre-check** ensures the loop doesn't burn cycles on already-perfect baselines.

The next milestone — v0.5.0 — adds cost caps (`--max-usd`, `--max-hours`), the 50-iteration validation run, and ships the loop as a tagged feature. From here it's polish, not architecture.

### Audit artifacts (local, gitignored)
- `prompt-lab/auto-runs/2026-05-28T171141Z-sonnet/` — β 20-iter validation. `iterations.jsonl` is the load-bearing evidence the gate works.

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
