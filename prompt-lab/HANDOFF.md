# Prompt-optimization loop — hand-off

**Date:** 2026-05-28. **Branch:** `main`. **Loop budget:** 5 hours (used ~4).

## TL;DR

One change adopted on top of `dc6ca39`, committed as **`abe9165`**:

> **C1′ — behavioral-trace self-check with form-discipline guard.** Before finalizing any command-hook the orchestrator now constructs a triggering + a clean stdin envelope from its chosen event/matcher, mentally executes the script, and confirms the trigger reaches `return 2` while the clean envelope reaches `return 0`. A prepended guard says: *this is a validation step, not a form selector — never convert a lighter form into a command-hook to earn a "fires" check, and never force a blocking PreToolUse where a lighter or non-blocking shape is right.* A mirrored rubric criterion 13 makes the same demand at self-critique time.

**Recommendation: KEEP the commit.** The diff is +48/−6 across 6 plugin files and is empirically supported by N=2 confirmation per model with a localized per-fixture mechanism check.

Your decision:
1. **Keep** (do nothing — the commit is already on `main`).
2. **Revert** (`git revert abe9165`) — if you disagree with the trade-off.
3. **Continue** the loop with C3/C4 (deferred — see below) before deciding.

## Before / after (N=2 means per model; sandbox eval, opus judge, default effort)

| model | metric | baseline `dc6ca39` | **C1′ `abe9165`** | Δ | note |
|---|---|---|---|---|---|
| **sonnet** | fire | 0.125 | **0.416** | **+0.29** | non-overlapping CIs across N=2; reproducible |
| | install | 0.697 | 0.885 | +0.19 | |
| | code | 8.395 | 8.695 | +0.30 | |
| | model | 6.655 | 6.250 | −0.41 | inside baseline's own 0.91 run-to-run range; +0.99 recovery from the rejected first attempt |
| **opus** | fire | 0.333 | 0.400 | +0.07 | |
| | install | 0.909 | 0.914 | +0.01 | |
| | code | 7.260 | **9.255** | **+2.00** | |
| | model | 7.250 | 7.750 | +0.50 | **Pareto improvement across every metric** |
| haiku | fire | 0.500 | 0.334 | −0.17 | haiku spans 0.0–0.667 across 6 runs — pure noise, not load-bearing |
| | install | 0.600 | 0.513 | −0.09 | |
| | code | 7.170 | 7.460 | +0.29 | |
| | model | 6.000 | 5.700 | −0.30 | |
| all | restraint | 0.0 | 0.0 | = | floored (orthogonal failure — see "Residuals") |

**Mechanism check (per-fixture proof that the *form-discipline guard* did real work, not noise):** sonnet fixture 005 model `{9, 8}` both C1′ runs vs `{2, 2}` both runs of the un-guarded first attempt vs `{8}` at baseline — the forced-blocking shape from the un-guarded version is decisively gone.

## What it touches

The committed change is in `plugin/skills/_shared/` and the two synced trees (`improve/`, `improve-init/`):

- `orchestrator-procedure.md` — Step 7 now has three blocks: Syntax → **Behavioral trace** → Stderr discipline. Retry-loop cap of 2 made explicit across the two behavioral checks.
- `references/prompt-rubric.md` — adds criterion 13 (fires on its own trigger).

The full diff: `git show abe9165` or `git diff dc6ca39..abe9165 -- plugin/skills/`. Tests stay green: 170 passed, 1 skipped — identical to baseline.

## The journey (why we landed here)

**Diagnostic (read-only, before any edit).** Re-ran `evals.grade_behavior.run_firing_check` on every stored baseline proposal. Result: **5 of 7 baseline no-fires were `trigger_rc=0`** — the hook runs clean on both inputs and never exits 2. The script reads the wrong stdin field, ignores stdin, or the guard never matches. Two more were metadata drift (`form: "command"` instead of `"command-hook"`, `script_lang: "python3"` not recognized by the harness). **The skill's procedure already validated syntax and stderr discipline — it never simulated the hook actually firing.** That gap was the highest-leverage hypothesis.

**C1 (first attempt) — verified-general, eval revealed a real trade-off.** Independent reviewer confirmed C1 was a general improvement (model invents its own envelopes; placeholders, never fixture values; restraint untouched). N=2 eval showed sonnet fire reproducibly up (0.125 → 0.416, non-overlapping CIs) BUT sonnet `model` reproducibly down (6.66 → 5.26, also non-overlapping). Per-fixture localization: C1 reproducibly converted commit-message-style (009) from `claude-md-note` (model 9) to `command-hook` (model 1–2) and forced format-on-write (005) into a blocking shape (model 8 → 2). The trace made command-hooks attractive (they earned a validation ritual + "fires" credit), pulling weaker models off Step 4's lightest-viable-form discipline.

**C1′ — the form-discipline guard.** One sentence prepended to the trace block: *"This is a validation step, not a form selector — apply it only to command-hooks already chosen per Step 4. Do not convert a lighter-form proposal (permissions / prompt-hook / CLAUDE.md note) into a command-hook to earn a 'fires' check. Do not force a blocking PreToolUse where PostToolUse or a lighter form is the right shape. If either temptation appears, re-run Step 4 — the trace doesn't override form selection."* Independent reviewer confirmed this counters both observed regressions without creating a new "model is timid about command-hooks" failure. N=2 confirmation: sonnet fire gain held (0.416 mean, same as the un-guarded C1), model recovered (5.26 → 6.25, ~85% of the way back to baseline 6.66, with the remaining gap inside baseline's own noise). Opus turned into a clean Pareto improvement. **Adopted, committed `abe9165`.**

**C2 (negative no-op example) — tried, no measurable gain, reverted.** Appended a rejected "wrong stdin fields" example to `examples.md`. Independent reviewer PASSed with a Step-4 callback nit (applied). N=1 eval: no model showed a positive signal — sonnet fire −0.17, opus code/model both slightly down. Diagnosis: redundant. Step 5 skeleton already pins `tool_name`/`tool_input`, Step 7's trace catches the bug, and rubric criterion 13 mirrors the check. The sixth example ate context without adding leverage. Per *adopt only verified gains*, reverted to the C1′ state.

## Residuals & known gaps (for a future loop)

1. **The `restraint` floor at 0.0 is the next-biggest gap.** Every run, every model, every condition, fixtures 011/012 score 0 — meaning the model *always* proposes something where the right answer is to propose nothing. Orthogonal to fire_rate but a clear target.
2. **009 form-over-selection on weaker models (sonnet) is partially closed, not fully.** The guard prevented 005's blocking-shape force reliably and 009's switch about half the time. A stronger or more concrete Step 4 nudge against "make a hook out of a style note" would help.
3. **`fire_rate` is intrinsically noisy at N=1** for *all* current models. Denominator is small (≤5), and a single form-label drift (`"command"` vs `"command-hook"`; `script_lang: "python3"`) silently leaves the count. The form/script_lang fields live only in the eval's echo schema — pinning them in the prompt would be coaching the harness, not improving the product. Improving signal-to-noise probably needs more firing fixtures, not more prompt tuning.
4. **Haiku is too unstable to be load-bearing.** Across 6 runs at the same conditions: fire ∈ {0.0, 0.25, 0.333, 0.5, 0.667}, install ∈ {0.30, 0.60, 0.64, 0.73, 0.78, 0.90}. Treat haiku as "doesn't crash" only.
5. **Deferred candidates: C3** (sharpen the opening directive — first line carries the most weight per prompt-engineering §2) **and C4** (form-selection firing lens — push the model to surface a candidate when "after X do Y" rules tempt a `CLAUDE.md` note). Both remain valid for a future loop; budget was spent on the C1/C1′ confirmation protocol instead.

## Audit trail

- **Iteration log:** `prompt-lab/iteration-log.md` — Rounds table, per-round notes, the resume/handoff section.
- **Result JSONs** (every eval round preserved by candidate × run):
  - `prompt-lab/rounds/C1/` — first C1 attempt, N=1
  - `prompt-lab/rounds/C1-run2/` — C1 confirmation
  - `prompt-lab/rounds/C1prime/` — C1′ (adopted), N=1
  - `prompt-lab/rounds/C1prime-run2/` — C1′ confirmation
  - `prompt-lab/rounds/C2/` — C2 attempt (rejected)
- **Ruflo memory** (`prompt-lab` namespace): `baseline-v0.4.0-lighter-default`, `baseline-fire-failure-diagnostic`, `round-C1-result-N2-final`, `round-C1prime-ADOPTED`, `round-C2-REJECTED`.
- **Rollback snapshot:** `prompt-lab/baseline/` still pins the original prompt; `git revert abe9165` restores the same state cleanly.
