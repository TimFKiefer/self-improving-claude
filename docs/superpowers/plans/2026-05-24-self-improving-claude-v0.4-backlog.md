# self-improving-claude v0.4 — Backlog & Design Notes

**Status:** Backlog / design notes — NOT a finalized implementation plan yet. The proper spec + writing-plans-skill output happens once we brainstorm v0.4 formally (probably after another round of dogfooding on v0.3.2).

**Sources for this document:**
- v0.1+v0.2 spec §9 "v0.3.0+ — polish" items that got pushed to v0.4
- v0.3 dogfooding feedback memories:
  - `memory/feedback_enforcement_gap.md` — the analysis from the other Claude Code session
  - `memory/feedback_orchestrator_form_bias.md` — partially addressed by v0.3.1/v0.3.2 form-selection fixes
  - `memory/feedback_distribution_ux.md` — addressed by v0.3.0 mostly
  - `memory/feedback_ollama_first.md` — eval backend preferences (already implemented in v0.2)
- v0.3 baseline observations (`evals/results/README.md` insights section)

**What v0.4 is about (in one sentence):** v0.3.x made the orchestrator pick the right *form* and write the right *text*; v0.4 gives it a new structural primitive — composed hooks that can actually **enforce** post-action follow-through, not just suggest it.

**What v0.4 is also about (added 2026-05-24, from the v0.3.2 analysis):** giving the eval *behavioral* eyes (does the generated hook actually fire when installed?) and re-grounding the knowledge base. These are not side-quests: a loop-closing, proactively-surfacing plugin (Track 2) must only push guardrails it can *vouch* for, and the orchestrator's grounding must match what the plugin actually relies on. See new Track 6 (eval integrity) and Track 7 (knowledge re-grounding). The small, non-structural slice of the v0.3.2 analysis ships first as **v0.3.3** — see `docs/superpowers/plans/2026-05-24-self-improving-claude-v0.3.3.md`.

---

## Track 1 — Composed PostToolUse + Stop hooks (the headline feature)

The single biggest gap v0.3.x couldn't close: PostToolUse exit-2 stderr is *information*, not *imperative*. Even with perfect criterion-12 wording, a model in heavy scope-discipline mode can still summarize and ask. The structural fix is to pair the PostToolUse hook with a Stop hook that re-verifies findings and blocks turn-end if they persist.

### 1.1 New form in the priority ladder

Add **form 5b** to procedure Step 4, between form 5 (PostToolUse alone) and form 6 (CLAUDE.md note):

> **5b. Composed PostToolUse + Stop hooks** — when the rule's failure mode is "model sees info and shrugs" (failed rubric criterion 11 for form 5 alone). Two coordinated hooks share state at `.claude/self-improving-claude/state/<slug>.json`. The PostToolUse hook detects regressions and writes the state; the Stop hook reads the state, re-verifies (don't trust stale state), and exits 2 to refuse turn-end if findings still exist. Uses `stop_hook_active` for recursion-guard. This is the only form in v0.4+ that can BLOCK turn-end without being a permissions rule.

Form 5b is heavier than form 5 (two hooks instead of one) but the only form that can actually enforce "after X do all of Y" semantics through to completion.

### 1.2 State-file convention

Spec a clean state-file shape. Tentative:

```jsonl
{"ts": "ISO-8601", "trigger_hook": "<sentinel-name>", "session_id": "...",
 "findings": [{"file": "...", "line": N, "context": "..."}, ...],
 "status": "pending|verified|resolved"}
```

Path: `.claude/self-improving-claude/state/<sentinel-slug>.jsonl` (one file per composed-hook pair, append-only inside a session, periodically rotated).

Schema documented in `references/settings-merge.md` (alongside the v0.3.1 feedback.jsonl schema) or in a new dedicated `references/composition-state.md`.

### 1.3 Recursion guard

Per Claude Code hooks docs, Stop hooks must respect `stop_hook_active`:

> `stop_hook_active` is set to `true` when the Stop hook is already running (to prevent infinite loops where a Stop hook forces continuation, which triggers another Stop hook).

Composed-hook authoring needs to embed this defensively — the Stop side should bail early if `stop_hook_active` is true.

### 1.4 New worked Example 6 in `examples.md`

Concrete walkthrough of the rename-callers scenario solved with form 5b:
- The PostToolUse script (similar to current Example 4 but writes findings to state-file in addition to stderr)
- The Stop script (reads state, re-greps to verify findings still exist, exits 2 with imperative stderr if so, exits 0 if findings were resolved)
- The settings.json delta showing BOTH hook entries with consistent sentinel-name pair
- "Why it's good" note: explicitly names why one event is insufficient and walks through the state-file lifecycle.

### 1.5 New section in `hook-patterns.md`

"Composing PostToolUse + Stop for enforcement" — documents:
- The pattern (paired hooks, shared state)
- The state-file convention
- The recursion-guard (`stop_hook_active`)
- Re-verify on Stop (don't trust stale state — the user might have already fixed it manually)
- Cross-reference from form 5b in Step 4

### 1.6 5th feedback mode: `weak-enforcement`

Procedure Step 1 routing. Heuristic triggers: user message contains "why aren't you / didn't you / should have automatically / why didn't it fix" within ~2 turns of a `self-improving-claude/*` hook firing.

Resolution: tighten the stderr imperative AND add a Stop companion to the existing PostToolUse hook. This is the canonical upgrade path from form 5 to form 5b — when real-world feedback shows surfacing alone wasn't enough.

The four existing feedback modes (`too-broad`, `false-positive`, `please-narrow`, `missed-case`) plus this new fifth one cover the realistic spectrum of how guardrails fail in practice.

### 1.7 New eval fixture 008 — composed-enforcement

A reactive fixture (`trigger: improve`) that plants a scenario where surfacing alone is provably insufficient. Expected: orchestrator picks form 5b (composed). Code grader passes if both hook entries are present with consistent sentinel-name pair. Catches regressions where v0.4's form-5b logic isn't reaching the right cases.

---

## Track 2 — Opt-in Stop-hook auto-collect (deferred from v0.3)

Original v0.3 plan had this; YAGNI'd until dogfood evidence appears. Now that we're building Stop-hook composition for Track 1, the auto-collect use case becomes a free convergence — same primitives (Stop event handler, state file, careful re-verify).

### 2.1 Stop hook for pattern detection

`scripts/stop.py` (new): on Stop, examines current session's `telemetry.jsonl` for patterns (3+ failed Bash exits, repeated edits same file, suspicious tool patterns), writes findings to `.claude/self-improving-claude/candidates.jsonl` for next `/improve` to surface. Pure pattern detection — no model call.

### 2.2 Opt-in gating

Via env var `SELF_IMPROVING_CLAUDE_AUTO_COLLECT` in user's settings.json `env` block. Default off. Documented in README.

### 2.3 Data flow

```
Session work → telemetry accumulates → Stop fires → stop.py checks env flag
   → if enabled: mines patterns → appends candidates.jsonl (no model call)
SessionEnd fires → existing rotation continues
Next session → user runs /improve → orchestrator reads candidates.jsonl as
   ADDITIONAL input alongside chat → surfaces pre-collected candidates with
   normal per-proposal approval
```

### 2.4 Telemetry schema extension

Add a `user_followup_required` flag to telemetry rows — set when a nudge pattern follows a hook fire within ~2 turns (e.g. user said "why aren't you fixing" after `self-improving-claude/*` hook executed). `/improve-init` proactive mode mines these to find guardrails worth tightening.

This closes the loop: the plugin learns from cases where its OWN hooks underperformed.

---

## Track 3 — Quality & eval polish

### 3.1 Conflict UX (deferred from v0.3 spec §6)

When a proposed matcher overlaps with an existing hook entry, the orchestrator currently uses `AskUserQuestion` with three sub-choices: `keep both`, `replace existing`, `skip`. This was documented in v0.1 procedure Step 8 but never tested in real-world conditions or covered by a fixture.

v0.4 work:
- Manual smoke test: install a hook, run `/improve` proposing something that overlaps, walk through the prompts
- Add eval fixture 009: `<existing_hooks>` already contains a Bash matcher; the orchestrator must detect overlap and present the keep/replace/skip choice
- Tighten the wording if the smoke test surfaces friction

### 3.2 Fixture 004 — re-evaluate

Baseline showed fixture 004 (`recursion-prevention`) is the hardest — even Opus only reaches 7/10 model grade. Worth revisiting:
- Is the "right answer" actually ambiguous? (prompt-hook vs command-hook with regex vs sub-Claude via Agent SDK)
- Is the planted problem too vague?
- Can the `expected_hook_traits` be sharpened to reward the spectrum of valid answers?

Either: redesign the fixture, OR accept it as a "hard case" and document why it's expected to score lower.

### 3.3 Eval entry expansion (deferred from v0.3 spec)

Spec §9 v0.3 deferred "10–20 eval entries; documented score thresholds." v0.4 could grow to ~12-15 entries covering:
- Composed-enforcement (fixture 008 above)
- Conflict resolution (fixture 009 above)
- 1-3 more "form choice" cases not yet covered (e.g. UserPromptSubmit hooks, Bash command-blocking with subtle regex)
- Maybe a fixture that intentionally has a 2-or-3-form-tie to test the `AskUserQuestion` clarification path

Plus document concrete score thresholds: "if avg code drops below 7.0 on the gemma baseline, that's a regression." Currently we just compare deltas; an absolute floor would let CI catch big regressions without needing prior baseline.

### 3.4 Dual-copy maintenance — automation

v0.3's inline-fallback created 4 dual-copy pairs (rubric, examples, hook-patterns, settings-merge) plus the procedure body in both SKILL.md files. Every v0.3.1/v0.3.2 fix has had to manually mirror. Two automation options:

- **Pre-commit hook in the repo's `.git/hooks/pre-commit`**: validate that the dual-copies stay byte-identical (or procedure-body-identical for SKILL.md). Block commit if drift detected. Zero CI dependency.
- **GitHub Actions CI check**: same logic, runs on PR. Better if/when the repo goes public.

Either prevents the maintenance burden from drifting silently.

### 3.5 Pre-commit hook — broader

Beyond dual-copy check, a pre-commit hook could also:
- Validate `plugin/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` (`claude plugin validate`)
- Run `python3 -m pytest -m "not integration"` (fast, 64+ tests)
- Validate `evals/dataset.json` parses + every fixture loads

These guard against shipping a broken plugin. Optional but cheap.

---

## Track 4 — Distribution & infrastructure

### 4.1 Productize `claude-cli` as a third eval backend

Currently `/tmp/eval_via_cli.py` is a one-shot helper. The user's session-by-session use proved it works and is preferable when no API key is around. Move it into the repo proper:

- Create `evals/client_claude_cli.py` mirroring `OllamaClient` and `Anthropic` interfaces
- Extend `evals/run.py`'s backend selection: `EVAL_BACKEND={ollama|anthropic|claude-cli}`
- Support `--model` env var (`OLLAMA_MODEL`, `CLAUDE_CLI_MODEL`) for picking which Claude variant
- Default behavior: if `ANTHROPIC_API_KEY` is unset AND Ollama isn't running, auto-fall-back to claude-cli (with a clear warning)
- Unit tests with mocked subprocess (mirrors the `client_ollama.py` test pattern)

### 4.2 GitHub Actions CI

Auto-run on PR:
- `pytest -m "not integration"` (the 70+ tests)
- `claude plugin validate <repo>` (catches broken manifests)
- Optional: a small `claude --print` smoke test via OAuth credentials (would need GitHub-stored secret)
- Optional: a gemma eval run (would need Ollama in the runner — heavy)

Probably: PR check (`pytest + validate`) + nightly cron (full eval against gemma) is the right balance.

### 4.3 Anthropic-marketplace PR

`docs/anthropic-marketplace-pr.md` already exists with PR-ready materials. Once v0.4 is stable and the repo is public on GitHub:
- Update `<user>` placeholders to the actual repo URL
- Get the `git rev-parse v0.4.0` SHA
- Submit the PR to `anthropics/claude-plugins-official`

Outside our control once submitted — external review timeline.

### 4.4 Demo materials

Non-code launch workstream. Could include:
- A short asciinema/gif of `/improve-init` running on a real project
- A blog-post-style README addition with the "before / after" framing
- A 2-minute video walkthrough (optional)

Not in the v0.4 spec; lives parallel to engineering work.

---

## Track 5 — Smaller items / cleanup

### 5.1 Auto-rewind investigation (stretch from v0.3)

The original v0.1 design had a "rewind chat history after /improve runs" idea that got deferred. Worth re-investigating in v0.4 only if (a) Claude Code grows a programmatic rewind API, or (b) we find a workaround. Currently: skill ends with "press ESC twice and pick the message where you ran /improve."

### 5.2 Document the dogfooding loop

v0.3.x produced a meta-pattern: dogfood → write feedback memory → patch in next minor release. Worth documenting in CONTRIBUTING.md or similar so the workflow stays legible to anyone (including future-us) who picks up the project.

### 5.3 Plugin uninstall verification

`/improve-uninstall` was added in v0.3 but only validated via spec-compliance review (the structure is correct). Has not been smoke-tested on a real project with installed hooks. v0.4 should:
- Run `/improve-init` on a sandbox project, install a few hooks
- Run `/improve-uninstall --dry-run` and verify the preview
- Run `/improve-uninstall` and verify cleanup
- Confirm settings.json round-trip is non-destructive

---

## Track 6 — Eval integrity & trustworthy generation (added 2026-05-24)

The v0.3.2 analysis surfaced that the eval measures *proposal shape*, not *runtime behavior* — and that the harness grades a proxy, not the shipped skill. These gaps are tolerable while the plugin is pull-only (the human reviews every proposal). They become **blocking** the moment Track 2 starts *pushing* proposals proactively: you cannot auto-surface a guardrail you can't vouch for. Track 6 gives the eval behavioral eyes and removes the proxy.

### 6.1 Verify-before-surface — behavioral / integration harness (the trust enabler)

`eval-methodology.md §5` names this explicitly and v0.3 spec §5 deferred it: the eval never installs a generated hook and confirms it *fires*. A proposal can score 10/10 and be a hook that no-ops — and the v0.3.1/v0.3.2 enforcement-shape saga (a hook that "passes every check yet fails to compel action") is precisely a *behavioral* failure a shape-eval is structurally blind to.

Build a sandbox harness that, for a generated proposal:
- writes the hook + settings.json into a throwaway temp project
- starts a scoped Claude Code session (or drives the hook script directly with a synthetic stdin payload from `tools-reference.md`)
- triggers the matching tool and asserts the observable effect: PreToolUse exit-2 blocks; PostToolUse stderr is emitted; a formatter actually ran; a permissions rule actually denies/asks
- returns a pass/fail + captured evidence

**Cross-reference Track 2:** this is what makes auto-collect safe. Each proactively-surfaced candidate carries a `✓ verified: blocks X / allows Y` line produced by this harness. Without 6.1, Track 2 is a nagging-risk; with it, it's trustworthy.

Start with the canonical hooks (the 5 worked examples) as hand-written integration tests; generalize to "verify any proposal" once the harness shape is proven.

### 6.2 Eval the real `SKILL.md`, not the `prompt_template.md` proxy

`evals/run.py` assembles its prompt from `evals/prompt_template.md` + the five `references/*.md` — it **never reads `SKILL.md`**. The orchestrator's actual procedure (routing, self-critique, the Step-7 stderr check, the approval loop) is untested, and the Step-4 form ladder now lives in **three** places that must stay in sync (`SKILL.md`, `prompt-rubric.md`, `prompt_template.md`). A SKILL regression can pass green.

v0.4 work: either drive the eval through the real skill body, or generate `prompt_template.md` from `SKILL.md` so there is one source. Pairs naturally with Track 7's single-sourcing.

### 6.3 Noise-penalizing aggregation + a fixed grader

- `run.py:_aggregate` takes the **max** across a fixture's proposals — 1 great + 2 junk scores identically to 1 clean great one. The real UX cost of junk (and of over-proposing) is invisible. Add a penalty for low-quality extra proposals, or report both max and mean so noise is visible.
- The model-grader uses the **same model family** as the proposer (Opus grades Opus). Switch to one fixed strong grader so cross-model numbers are comparable and self-grading bias is removed.

### 6.4 Negative / restraint fixtures (needs grader support)

Every current fixture is a positive case ("should propose X"). None tests restraint ("should propose **nothing**" or "this tempting guardrail would over-block"). Restraint is the trust-critical dimension and is currently unmeasured.

- Extend `dataset.json` + `run.py` with an `expect_no_proposal: true` mode: score 10 when the orchestrator proposes nothing (or declines the tempting-but-wrong form), 0 otherwise.
- Add 2-3 negative fixtures (e.g. a project where a `permissions.deny` would block legitimate work; a one-off bug that doesn't warrant any standing guardrail).

---

## Track 7 — Knowledge re-grounding & single-source references (added 2026-05-24)

The v0.3.2 analysis's headline meta-finding: **the implementation has outrun its knowledge base.** `docs/knowledge/` grounded v0.1; the plugin now relies on facts it never captured, and in one file still lists resolved questions as open. This track re-grounds the docs and eliminates the dual/triple-copy drift at its root.

### 7.1 Back-propagate resolved facts into `docs/knowledge/`

- `plugins-and-skills.md` is still marked "biggest gap / low-medium confidence," lists as *open* questions that v0.3 answered (marketplace.json works; `@../` cross-dir mentions do **not** resolve → inline fallback; plugin hooks register via `hooks.json`), and shows the **abandoned** `skills/self-improving-claude/shared/` layout. Rewrite it to current reality.
- The `type:"prompt"` hook contract (`permissionDecision: deny` / "respond deny/allow"), the advanced JSON hook output, `Stop` force-continue, `${CLAUDE_PLUGIN_ROOT}`/`${CLAUDE_PROJECT_DIR}`, and the `marketplace.json` schema are all **relied upon but uncaptured** in the knowledge base (they live only in skill `references/`). The prompt-hook form especially is the least-grounded, least-verified output the plugin emits — capture and verify it.

### 7.2 Single-source the references (supersedes Track 3.4)

v0.3's inline fallback created 4 dual-copy reference pairs + the procedure body in both SKILL.md files. Track 3.4 proposed a byte-identical *guard*; that's a band-aid. The real fix is to make `plugin/skills/*/references/*.md` (and the eval's `prompt_template.md` form-ladder) **generated** from `docs/knowledge/` so there is exactly one source of truth.

- Build a small `scripts/sync_references.py` that renders the runtime references from the knowledge base, run in pre-commit/CI.
- Keep Track 3.4's byte-identical check as the transition guard until generation is in place.

### 7.3 Re-probe `@../` resolution (also Open Question #6)

If a current Claude Code version resolves `@../shared/...` from inside a skill directory, the entire inline-duplication burden disappears — revert to a single `shared/` directory and delete the copies. A 5-minute probe at v0.4 start; do it before 7.2 (it may make the generator unnecessary).

---

## Open design questions (resolve before v0.4 implementation)

1. **State-file granularity.** One file per composed-hook pair (`state/<slug>.jsonl`) or one shared file across all pairs (`state.jsonl` with discriminator field)? Tradeoff: per-pair is cleaner for cleanup; shared is simpler for the Stop hook to read. Tentative: per-pair.

2. **State-file lifecycle.** When are state files cleared? Options:
   - On Stop hook running with all findings resolved (auto-clear)
   - On SessionEnd (cleared regardless of state)
   - Never — accumulate forever (rotation responsibility on the user)
   Tentative: auto-clear on resolution, fallback rotation at SessionEnd.

3. **Composed-hook approval UX.** Currently `/improve` shows one proposal at a time. A composed pair is TWO hook entries — show as one approval (atomic) or two (granular)? Tentative: one atomic approval, since the two are useless without each other.

4. **auto-collect storage.** Should `candidates.jsonl` be cleared after `/improve` reads it, or accumulate? Tentative: read once, archive to `candidates-archive.jsonl` and clear the working file. Otherwise the same patterns surface every run.

5. **Feedback-mode `weak-enforcement` detection accuracy.** "Why aren't you fixing it" is a fuzzy heuristic. False positives are possible. Tentative: surface candidates via `AskUserQuestion` ("It looks like the X hook didn't compel action — want to upgrade it to a Stop pair?") rather than auto-tighten.

6. **Dual-copy: keep inline, or revisit `@../shared/` probe?** The v0.3 probe failed; maybe a newer Claude Code version supports `@../` traversal? Worth a 5-minute re-probe at v0.4 start. If it works now, eliminates the duplication burden entirely.

7. **Should there be a v0.3.3?** ✅ **Decided — yes, and it's planned.** A "measurement & correctness hygiene" release: `docs/superpowers/plans/2026-05-24-self-improving-claude-v0.3.3.md`. Scope: fix the leaky `imperative_stderr` grader (f-strings/bash/JS), productize the `claude-cli` eval backend, re-score the dataset, capture telemetry `kind`/`reason`/`source`, fix the dangling uninstall reference. It deliberately **excludes** the structural and eval-rework items — fixture-004 redesign (Track 3.2), dual-copy automation (Track 3.4), the verify-before-surface harness (Track 6.1), and knowledge re-grounding (Track 7) all stay v0.4. Rationale: v0.3.3 makes the v0.3.1/v0.3.2 work measurable and reproducible so v0.4's structural change lands on solid ground.

---

## Out of scope for v0.4

Explicitly NOT v0.4 work — these get later releases or remain stretch goals:

- Telemetry encryption at rest (telemetry is local-only by design; encryption is overkill for the threat model)
- Plugin marketplace UI inside Claude Code (Anthropic territory)
- Per-user analytics dashboards
- Multi-language hook script generation beyond Python/Bash/JS (current set covers 95%+ of real-world cases)
- Cross-machine telemetry aggregation (privacy footgun without strong reason)
- Plugin auto-update logic (Claude Code handles this via marketplace)
- Windows-specific testing (deferred until requested by a Windows user)

---

## Estimated scope

Rough sizing (subject to writing-plans output):

| Track | Tasks | Effort | Risk |
|---|---|---|---|
| 1. Composed hooks | ~6-8 | Medium-high | Highest — new primitive, state-file design, recursion-guard |
| 2. Auto-collect | ~3-4 | Medium | Low — converges with Track 1 primitives |
| 3. Quality & eval | ~4-5 | Low-medium | Low — incremental |
| 4. Distribution | ~3-4 | Medium | Medium — CI config, marketplace PR external |
| 5. Cleanup | ~2-3 | Low | Low |
| 6. Eval integrity & trustworthy generation | ~5-7 | Medium-high | Medium — sandbox harness is new infra; **gates** Track 2's safety |
| 7. Knowledge re-grounding & single-source | ~3-4 | Medium | Low-medium — touches build/docs, not runtime |

**Rough total:** 26-35 tasks (was 18-24 before the v0.3.2 analysis added Tracks 6-7; minus the ~5 hygiene tasks now peeled off into v0.3.3). v0.4 is genuinely bigger than v0.3 (10 tasks) because Track 1 is a new primitive AND Track 6 gives the eval behavioral eyes for the first time.

Suggested slicing:
- **v0.3.3** (shipped first, separate plan) — measurement & correctness hygiene.
- **v0.4.0** — Track 1 (composed hooks) + Track 6.1 (verify-before-surface). Ship the enforcement primitive *with* the harness that proves generated hooks fire — they reinforce each other.
- **v0.4.1** — Track 2 (auto-collect, now safe to push because 6.1 verifies) + the rest of Track 6 (proxy removal, scoring, restraint fixtures).
- **v0.4.2** — Tracks 3 + 4 + 5 + 7 (polish, distribution, re-grounding).

Decide the exact cut during brainstorming.

---

## Recommended next step

When you're ready to start v0.4:

1. **Dogfood v0.3.2 more.** The new `imperative_stderr` grader is in; rerun the baseline against any backend to see if v0.3.1+v0.3.2 actually moved fixture 006's score upward, and to surface any NEW failure modes the new rubric criteria might cause.
2. **Re-probe `@../` resolution** in current Claude Code — if it now works, we can revert v0.3's inline-fallback and dramatically reduce maintenance burden BEFORE v0.4 work starts.
3. **Brainstorm v0.4 formally** using the `superpowers:brainstorming` skill. This backlog document is INPUT to that brainstorm, not output of it. The brainstorm will validate / refine / slice the scope, produce a spec, then `writing-plans` produces the bite-sized implementation plan.
4. **Execute via `subagent-driven-development`** — same flow that worked for v0.1, v0.2, v0.3.

---

## Memories to load when v0.4 brainstorming starts

The following feedback memories are directly load-bearing for v0.4 design decisions:

- `~/.claude/projects/-Users-timkiefer-Desktop-Projects/memory/feedback_enforcement_gap.md` — the canonical analysis of why composed hooks are needed
- `~/.claude/projects/-Users-timkiefer-Desktop-Projects/memory/feedback_orchestrator_form_bias.md` — partially addressed in v0.3; v0.4 closes the remaining structural gap
- `~/.claude/projects/-Users-timkiefer-Desktop-Projects/memory/feedback_ollama_first.md` — eval backend preferences (productize claude-cli)
- `~/.claude/projects/-Users-timkiefer-Desktop-Projects/memory/feedback_distribution_ux.md` — install/UX work (mostly v0.3; some carry-over)
