# Prompt-Optimization Lab — iteration log

**Goal:** improve the `self-improving-claude` skill's *prompt system* so the hooks it
proposes are better — primarily higher **fire_rate** (generated command-hooks actually
block on a trigger and pass clean input), without sacrificing **install_rate**,
**code**, **model**, or **restraint**.

**Target prompt system (what we tune):** `plugin/skills/_shared/`
- `orchestrator-procedure.md` (the 10-step procedure)
- `references/prompt-rubric.md`, `references/examples.md`, `references/tools-reference.md`,
  `references/hook-patterns.md`, `references/settings-merge.md`
- After any edit: `python3 scripts/sync_skills.py` regenerates the two SKILL.md.

**Fitness:** full sandbox eval — `SANDBOX_MODEL=<m> SANDBOX_JUDGE=opus python3 -m evals.run --sandbox`
for m in {haiku, claude-sonnet-4-5, opus}. Metrics: fire_rate, install_rate, code, model, restraint.

**Rollback:** `prompt-lab/baseline/` snapshot @ git `dc6ca39`. If the whole effort is a wash,
restore that and discard `prompt-lab/`.

**Method (per the user):** generate few but high-quality, knowledge-grounded candidates;
use independent agents to *verify each candidate before it is adopted as a new route*
(overfit + restraint + knowledge-alignment review); **full eval every round**; adopt only
verified, real (non-noise) gains. ruflo MCP was added after this log started — in a resumed
session, verify it loaded (`ToolSearch select:swarm_init,agent_spawn,memory_store,memory_search,hooks_route`)
and use ruflo swarm/agents + `memory_store`; otherwise fall back to the native `Agent` tool +
this log + auto-memory.

---

## ▶ RESUME / HANDOFF — read this first (fresh session)

This is an **in-progress 5-hour autonomous loop**. It paused so the session could restart and
load the ruflo MCP server. The user authorized heavy quota (incl. Opus). Pick up here:

**0. Verify environment.**
- `ToolSearch select:swarm_init,agent_spawn,memory_store,memory_search,hooks_route` → if found, use ruflo for the agent-verification + iteration memory; if not, use the native `Agent` tool + this log.
- You're on git branch `main`, snapshot/rollback at `prompt-lab/baseline/` (orig prompt @ `dc6ca39`).

**1. Record the baseline (the number to beat).** The baseline eval (lighter override, default
effort, 3 models, opus judge) ran in the prior session.
- `ls -t evals/results/*v0.4.0-sandbox-* | head` → find the latest haiku / claude-sonnet-4-5 / opus files.
- Read each file's `summary`: `fire_rate`, `install_rate`, `average_code`, `average_model`, `average_restraint`. Fill the **Baseline reference** section + Rounds row 0 below.
- If any of the 3 files is missing/incomplete (baseline got killed early), re-run just that model: `SANDBOX_MODEL=<m> SANDBOX_JUDGE=opus python3 -m evals.run --sandbox` (from repo root).

**2. Run the loop — one change per round** (start with candidate **C1**, the trace-the-fire self-check):
   1. Apply the edit to `plugin/skills/_shared/*` (procedure and/or references).
   2. `python3 scripts/sync_skills.py` (regenerates both SKILL.md) — required after any `_shared` edit.
   3. `python3 -m pytest -q` — must stay green (170 passed / 1 skipped baseline).
   4. **Verify-before-route gate:** dispatch an independent agent to check the candidate is a *general* prompt improvement (NOT fixture-coaching — fixtures 001/005/006/008… are known), doesn't weaken restraint (011/012), and aligns with `docs/knowledge/prompt-engineering.md`. Only proceed to eval if it passes.
   5. Full eval: `SANDBOX_MODEL=<m> SANDBOX_JUDGE=opus python3 -m evals.run --sandbox` for m in `haiku`, `claude-sonnet-4-5`, `opus` (run in background; you'll be notified).
   6. Compare to baseline. If a gain looks real, **confirm it's not N=1 noise** (agent review + a targeted re-run) before adopting.
   7. Adopt → keep the edit, `git commit` only the files you changed, update the Rounds table + `memory_store`. Reject → revert (`git checkout -- plugin/skills/_shared` or restore from `prompt-lab/baseline/`, then re-sync), note why.
   8. Next candidate (C2…). See the **Candidate queue** below.

**3. Locked decisions:** optimize procedure + references *together*; **full eval every round**;
ground every edit in `docs/knowledge/prompt-engineering.md`; **do NOT auto-merge** — at the end,
present the best prompt + before/after scores + the journey for the user's decision.

**4. Operational constraints (durable):**
- NEVER `git add`/commit `docs/VISION.md` or `docs/superpowers/plans/2026-05-25-capability-benchmark.md` (pre-existing untracked, not ours).
- On a usage-limit crash (`claude --print` rc=1, empty stderr): just **re-run the same plain command** once the limit resets — do NOT build retry/resume scaffolding.
- Default effort (chosen for comparability with the baseline). A `--effort max` ceiling run is a separate, user-triggered follow-up.

**5. Rollback:** restore `prompt-lab/baseline/skills/` over `plugin/skills/` (or `git checkout dc6ca39 -- plugin/skills` then re-sync) and the prompt is back to the start.

---

## Prompt-engineering principles in play (from docs/knowledge/prompt-engineering.md)

1. **Clear & direct** — imperatives, action-verb-first; the first line carries the most weight.
2. **Be specific** — output-quality guidelines *and* explicit process steps for critical-thinking tasks.
3. **XML tags** — wrap interpolated data so instructions ≠ data (already used heavily).
4. **Examples (few-shot) + explain-why** — "show, don't tell"; the *why-it's-good* line after each example is a frequently-missed, high-impact step. Negative examples inoculate against known failure modes.
5. **Measure, don't vibe** — "don't change the SKILL because it feels better; run the eval, compare, decide." → this whole loop.

## Failure-mode analysis (why hooks don't fire — from prior debugging + the N=3 probe)

- **F1 wrong stdin envelope** (`ev["tool"]`/`["args"]` instead of `tool_name`/`tool_input`) → guard never matches → silent exit 0. *Already mitigated* (Step-5 inline boilerplate + static guard) but weaker models may still regress.
- **F2 no-stdin hooks** — script ignores stdin entirely → can't react to the trigger.
- **F3 logic error** — reads the right fields but the condition doesn't match the trigger (or never returns 2).
- **F4 form mis-selection** — picks CLAUDE.md/PostToolUse-only where it can't fire/enforce, or proposes nothing for a real problem.
- **F5 genuinely hard rule** — e.g. 006 rename-callers (detect a rename *and* grep stale callers) is hard to express as a firing hook.

**Key evidence:** the N=3 probe (lighter override) lifted Opus fire_rate 33%→50% just by letting the model read its references + self-critique. So the *procedure is capable*; the gap is (a) weaker models skip/botch the firing logic, (b) some rules are genuinely hard. The procedure validates **syntax** and **stderr discipline** but **never simulates the hook actually firing** — that is the missing self-check and the highest-leverage hypothesis.

### Baseline fire-failure diagnostic (re-ran `run_firing_check` on stored baseline proposals, 2026-05-28)

Categorized every no-fire across the current baseline (haiku/sonnet@05-28/opus) on the 4 firing fixtures (001/005/006/008):

- **Dominant — `trigger_rc=0`, the hook never blocks on its trigger (F1/F3):** 5 of 7 no-fires (haiku 008, sonnet 005+006, opus 001-prop1+006). Script runs clean on BOTH inputs, never `exit 2`, empty stderr → reads wrong fields or the guard never matches. **This is exactly what C1's trace-the-fire check targets.**
- **Metadata drift leaves the denominator (F4-adjacent):** sonnet labeled 001 `form:"command"`, haiku labeled 005 `form:"hook"` → `fired=None`, not even counted. sonnet's 008 used `script_lang:"python3"` (harness only knows `"python"`) → firing check ERRORS → no-fire.
  - ⚠ **Overfit caveat:** `form`/`script_lang` are NOT defined in the skill prompt — they're fields the *sandbox echo schema* asks for (`sandbox_runner.py:43-45`); the real interactive product has no echo. Pinning `form:"command-hook"` / `script_lang:"python"` would coach the harness, not improve the product. `script_lang:"python3"` failing is a harness limitation, not a skill bug — leave it. C4 should improve form *reasoning* (prefer the enforceable firing form) generally, not coach echo strings.

Conclusion: C1 (firing-logic trace) and C2 (negative no-op example) attack the dominant, clearly-general failure; they are the right first two candidates.

## Overfitting guard (critical)

Fixtures (001/005/006/008…) are known. A candidate that *coaches fixture-specific logic* into the prompt would inflate scores without improving the real product. **Every candidate must be a general prompt-engineering improvement.** The pre-eval agent verification explicitly checks: "would this help on an unseen problem, or only on our fixtures?" Reject fixture-coaching.

---

## Candidate queue (prioritized)

### C1 — "Trace the fire" self-check (highest leverage; targets F1/F2/F3)
Add to the procedure a mandatory **behavioral trace** before finalizing any command-hook:
construct a *triggering* stdin envelope (`{"hook_event_name","tool_name","tool_input":{…}}`)
and a *clean* one, and mentally execute the script against both — confirm the trigger path
reaches `return 2` (with stderr) and the clean path reaches `return 0`. If either fails, fix
the script. This is a *general* check (the model invents the envelopes), grounded in
prompt-engineering §2/§3 (process steps for critical-thinking) and §5 (validate behavior, not
just syntax). Goes in Step 6/7 + rubric criterion. **Not** fixture-specific.

### C2 — Negative few-shot: the no-op hook (targets F1/F2)
Add one **rejected** example to examples.md: a hook that reads `ev["tool"]`/`["args"]` (or
ignores stdin) and therefore silently no-ops, with a sharp *why-it's-bad* line. Per
prompt-engineering §5, negative examples inoculate. General, not fixture-coaching.

### C3 — Sharpen the opening directive (targets weak models; F4)
The procedure opens soft ("You are operating as a workflow with a few agentic moments…").
Lead instead with a crisp action-verb directive stating the job and the bar
("…every command-hook you propose MUST fire: block on its trigger, pass clean input."). §2:
the first line carries the most weight; helps Haiku most.

### C4 — Form-selection firing lens (targets F4)
In Step 4, when the rule is "after X do Y," add an explicit prompt to prefer the
*enforceable, firing* form and to **not** silently propose nothing — surface a candidate.

> Plan: draft C1 (self + agent), get an independent agent to draft an *alternative* framing and
> to critique for overfit/restraint, eval the survivor(s). Then C2, etc. One change per round so
> gains are attributable. Re-run to confirm any gain is real before adoption.

---

## Baseline reference

- **Prior (forceful override, default effort, 2026-05-27)** — fire_rate: haiku 0% / sonnet 25% / opus 33%; install 64/73/91%. (Context only — different override.)
- **Current (lighter override, default effort, opus judge — THE NUMBER TO BEAT):**
  - haiku  (`2026-05-27-…-haiku.json`):  fire **0.50** · install 0.60 · code 7.17 · model 6.0 · restraint 0.0
  - sonnet (`2026-05-28-…-claude-sonnet-4-5.json`, latest): fire **0.00** · install 0.667 · code 9.07 · model 7.11 · restraint 0.0
  - opus   (`2026-05-27-…-opus.json`):  fire **0.333** · install 0.909 · code 7.26 · model 7.25 · restraint 0.0
  - ⚠ **fire_rate is high-variance at N=1.** The prior 05-27 sonnet run scored fire 0.25 / code 7.72 / install 0.727 — same config, swung 0.25. Denominator is tiny: only fixtures **001/005/006/008** define a `firing_test`, and a proposal is firing-checked **only if `form=="command-hook"` exactly** (drift to `command`/`hook` → `fired=None`, silently leaves the denominator). Treat single-run fire deltas ≲0.25 as noise; confirm gains with a re-run before adopting.

---

## Rounds

| # | Candidate | Change | haiku fire | sonnet fire | opus fire | install | code | model | restraint | verdict |
|---|-----------|--------|-----------|-------------|-----------|---------|------|-------|-----------|---------|
| 0 | baseline  | current prompt @ dc6ca39 (lighter override, default effort) | 0.50 | 0.00 | 0.333 | .60/.67/.91 | 7.2/9.1/7.3 | 6.0/7.1/7.3 | 0/0/0 | reference (install/code/model = h/s/o) |
| 1 | C1 trace-the-fire (N=2) | Step 7 behavioral-trace block + rubric criterion 13 | 0.0–0.33 | 0.33–0.50 | 0.40 | .64–.90/.91–1.0/.67–.80 | 5.9–7.9/7.7–8.8/8.3–9.3 | 4.3–5.3/5.2–5.3/7.4–7.6 | 0/0/0 | **refine → C1′** (fire ↑ reproducibly on sonnet; model ↓ on sonnet via form-over-selection; opus robust; haiku noise) |

**Round C1 notes (N=2 complete, 2026-05-28).** Independent review = PASS-general. Two full sandbox eval runs (3 models each) preserved in `prompt-lab/rounds/C1/` (run 1) and `prompt-lab/rounds/C1-run2/` (run 2). Per-model verdict from non-overlapping confidence intervals:

- **haiku — uninformative (pure noise).** fire spans 0.0–0.5, code 5.9–7.9 across 3 runs incl. baseline. Single-run deltas on haiku carry no signal.
- **sonnet — real fire gain AND real model regression.** fire baseline {0.0, 0.25} → C1 {0.33, 0.50} (non-overlapping, +~0.3 reproducibly). model baseline {6.2, 7.11} → C1 {5.22, 5.30} (non-overlapping, −~1.4 reproducibly). Mechanism localized per-fixture: **C1-induced form-over-selection** — 009 reproducibly switched `claude-md-note` (model 9) → `command-hook` (model 1–2) BOTH runs; 005 reproducibly tanked 8→2 BOTH runs (likely forced into a blocking shape by "trigger reaches return 2"). Other model swings (e.g. 002 `permissions.deny`, untouchable by C1, swung 9→2/3 then 9→7) are pure judge noise.
- **opus — robustly positive.** fire {0.40, 0.40} (base 0.333) — slight, reproducible up. model {7.60, 7.44} (base 7.25) — UP. code {8.26, 9.26} (base 7.26) — strongly up. clean up. Only install dips. Opus's form choices barely change between baseline and C1; it's robust to the trace's form-pressure.

**Decision: refine, don't adopt.** The fire gain on sonnet is real, but a reproducible −1.4 model regression on the same model violates "improve fire WITHOUT regressing model." C1′ adds a one-sentence **form-discipline guard** at the top of the Step 7 trace block: "this is a validation step, not a form selector — never convert a lighter form (`permissions.deny`/`permissions.ask`/`prompt-hook`/`CLAUDE.md note`) into a command-hook, or force a blocking PreToolUse where a non-blocking PostToolUse or lighter form is right, just to satisfy this trace." Grounded in Step 4's lightest-viable-form rule and prompt-engineering §3 (specific output guidelines). Re-eval after.

| 2 | C1′ form-discipline guard (N=2) | Prepend Step 7 trace block: "validation step, not a form selector — don't convert a lighter form to command-hook to earn a fires check; don't force blocking PreToolUse where PostToolUse/lighter form is right" | 0.0–0.67 | 0.33–0.50 | 0.40 | .30–.73/.85–.92/.88–.95 | 7.3–7.6/8.4–9.0/9.0–9.5 | 5.4–6.0/6.1–6.4/7.5–8.0 | 0/0/0 | **ADOPT** — sonnet fire +0.29 reproducibly, model restored 5.26→6.25 (within base noise); opus Pareto improvement (code +2.0, model +0.50); haiku noise |

**Round C1′ notes (N=2 final, 2026-05-28). ADOPTED.** Independent review = PASS-WITH-NITS (reviewer's tighter wording applied — names the mechanism "to earn a 'fires' check"). N=2 means (vs baseline):

- **sonnet** (the model that blocked C1's adoption): fire **0.125 → 0.416** (**+0.29 reproducibly**, primary target). model **6.655 → 6.250** (−0.41, **inside baseline's own 0.91 run-to-run range**, and a +0.99 recovery from C1's 5.26). install +0.19. code +0.30. Per-fixture proof: 005 model {**9, 8**} BOTH runs (was {2, 2} in C1, {8} in baseline) — the forced-blocking shape is gone.
- **opus**: fire 0.333 → 0.400 (+0.07). install 0.909 → 0.915 (recovered). code 7.26 → 9.257 (**+2.0**). model 7.25 → 7.75 (+0.50). **Pareto improvement** across every metric.
- **haiku**: pure noise. fire mean 0.334 (base 0.500) — but haiku spans 0.0–0.667 across 6 runs. Cannot load-bear in either direction.

Result JSONs preserved in `prompt-lab/rounds/C1prime/` (run 1) and `prompt-lab/rounds/C1prime-run2/` (run 2). Committed. New baseline for subsequent rounds.

| 3 | C2 negative no-op example (N=1) | Append rejected Example 6 (chmod 777 hook reading `ev["tool"]`/`ev["args"]` → silent `return 0`) to `examples.md` | 0.25 | 0.25 | 0.40 | .78/.94/.88 | 7.1/8.8/8.5 | 5.2/5.9/7.6 | 0/0/0 | **REJECT** |

**Round C2 notes (N=1, 2026-05-28). REJECTED.** Independent review = PASS-WITH-NITS (nit applied: "fix is mechanical, *if a command-hook is still the right form per Step 4*…"). Eval result: **no model showed a positive signal vs C1′.** Sonnet fire −0.17 (within noise but no gain), opus fire flat with code −0.75 and model −0.15, haiku noise. Diagnosis: **the inoculation is redundant.** Step 5 skeleton already pins `tool_name`/`tool_input`, Step 7's behavioral trace already catches the wrong-key bug, rubric criterion 13 already mirrors the check, and the C1′ commit message records the failure mode. Adding a sixth example eats context without adding leverage. Per "adopt only verified, non-noise *gains*," reverted. Result JSONs preserved in `prompt-lab/rounds/C2/`.

### Rounds C3 (sharpen opening directive) and C4 (form-selection firing lens): DEFERRED

Time budget exhausted (5-hour loop). The N=2-with-confirm protocol on C1+C1′ consumed roughly 2.5 of the 3 hours pre-C2. Given how much single-run signal we already observed evaporates as noise, the responsible call was to spend the remaining budget confirming C1′ rather than burning it on additional weak-evidence rounds. C3/C4 remain valid candidates for a future loop — see queue above.

---

## Final state for user decision

**Adopted:** C1′ (committed `abe9165`). One change vs git `dc6ca39`: a behavioral-trace block in Step 7 (procedure) with form-discipline guard, plus rubric criterion 13. 6 plugin files (`_shared/*` sources + the two synced SKILL.md trees), +48/−6 lines.

**Reproducible gains vs baseline (N=2 each, opus judge, default effort):**
- sonnet: fire **+0.29**, code +0.30, install +0.19, model −0.41 (inside baseline's own 0.91 run-to-run range)
- opus: fire +0.07, code **+2.00**, model +0.50, install +0.01 — Pareto improvement
- haiku: noise — uninformative either way

**See `prompt-lab/HANDOFF.md` for the user-facing summary + merge decision.**
