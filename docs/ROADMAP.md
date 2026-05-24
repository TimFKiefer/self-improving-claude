# self-improving-claude — Roadmap (v0.1 → v1.0)

> **North star:** [`docs/VISION.md`](VISION.md) — the project's name is a promise; v1.0 is when we keep it.

This document is the single, linear roadmap from v0.1 (initial scaffold) through v1.0 (the vision realized). It captures:
- **What's already shipped** (v0.1 – v0.3.x) — with patch history and lessons learned.
- **What's planned** (v0.4 – v1.0) — with scope, exit criteria, and decision gates between releases.
- **The patch policy** that governs hand-testing and stabilization between major versions.

The roadmap is intended to be read **top-to-bottom, then worked through step-by-step**. Each major release has an explicit exit criteria; when those are met, we tag, dogfood, patch as needed (v0.x.y), and only then start the next major.

---

## How we use this roadmap

### The cycle for each major release

```
brainstorm  →  spec  →  plan (writing-plans)  →  execute (subagent-driven)
                                                         ↓
                                              tag v0.x.0 + merge to main
                                                         ↓
                                              hand-test + dogfood
                                                         ↓
                              ──── any bugs / friction found? ────
                                  ↓ yes                       ↓ no
                          patch as v0.x.y                  exit criteria met?
                          (small, focused,                       ↓ yes
                           dual-copy-safe)                  start v0.(x+1)
                                  ↓
                          back to dogfood
```

### When to bump x vs y

| Bump | Trigger | Examples |
|---|---|---|
| **Patch (v0.x.y)** | Bug found in dogfooding; small refinement; missed test; doc fix | v0.3.1 stderr discipline; v0.3.2 prompt-eng retrospective |
| **Minor (v0.x.0 → v0.(x+1).0)** | All exit criteria for current major met + previous patches stabilized + meaningful new scope ready | v0.2 → v0.3 = public release; v0.3 → v0.4 = trust foundation |
| **Major (v0.x → v1.0)** | The vision is literally realized — autonomous self-improvement loop runs unattended overnight | v0.9 → v1.0 |

### Rules of the road

- **Don't start v0.(x+1) while v0.x is still surfacing patches.** Stabilization first, scope expansion second.
- **Every patch is dual-copy-safe** (until v0.4's Track 7 single-sources references — then drift is structurally impossible).
- **Every release tags `main`.** No floating WIP after a major.
- **Decision gates between releases are explicit** — if v0.4 finishes and the vision-loop scope looks different than we thought, we re-spec v0.5 before starting.

---

## Done (v0.1 – v0.3.x)

### v0.1.0 — Foundational scaffold (2026-05-22)

**What landed:** Plugin scaffold, `/improve-init` proactive scan, bundled `PostToolUse: "*"` telemetry hook with strict redaction, per-proposal `AskUserQuestion`-driven approval, 10-step orchestrator procedure grounded in Anthropic's Claude Code course material.

**Tests:** 22 telemetry redaction tests.

**Why it mattered:** Established the architectural pattern — plugin = manifest + skill + bundled hook + references. Proved the orchestrator-skill approach works end-to-end on real projects.

---

### v0.2.0 — Reactive mode and measurement (2026-05-22)

**What landed:** Reactive `/improve` slash command (uses live chat context). Eval harness with 5 fixtures, code-grader (deterministic) + model-grader (Haiku). First committed baseline. Pluggable backend (`EVAL_BACKEND={ollama|anthropic}`) — default Ollama, no API key.

**Tests:** 55 total (22 telemetry + 33 eval).

**Why it mattered:** Gave us numbers. From this point on, every orchestrator change is paired with a delta — no more "feels better."

---

### v0.3.0 — Public release foundation (2026-05-23)

**What landed:** Marketplace restructure (plugin in `plugin/` subdir + marketplace.json at root → `claude plugin install` works). Orchestrator hidden from `/` menu (inline-duplication fallback since `@../` probe failed). `permissions.ask` added as 5th recognized guardrail form. Multi-event telemetry (PostToolUse + Notification + PreCompact + SessionStart) + SessionEnd inline-bash rotation. Formalized feedback channel (`feedback.jsonl`). `/improve-uninstall` slash command. 7-fixture baseline across gemma4 + Haiku + Sonnet 4.5 + Opus 4.7.

**Tests:** 64 total.

**Why it mattered:** Crosses the "installable for strangers" threshold. Three slash commands, working install path, baselines documented for four model backends.

---

### v0.3.1 — Enforcement-shape check + imperative stderr (2026-05-24)

**Patch trigger:** Dogfooded the `FILE_READ_TOOL_NAME 'Read' → 'View'` scenario. The PostToolUse + grep hook fired (passed eval at 8.6/10) but the model stopped to ask the user instead of fixing the regressions. Root cause: stderr was *informational* not *imperative*.

**What landed:** Rubric criteria 11 (enforcement-shape check) + 12 (imperative stderr). Procedure Step 7 expanded with stderr-discipline check. Example 4's stderr rewritten to imperative voice.

---

### v0.3.2 — Prompt-engineering retrospective (2026-05-24)

**Patch trigger:** Self-reviewed v0.3.1 against the project's own knowledge base. Seven gaps surfaced relative to prompt-engineering best practices.

**What landed:** Concrete bad/good stderr pairs in criterion 12. Procedure Step 4 inline gate referencing criterion 11. Step 7 deterministic pattern-match (banned/required phrases) + retry loop. New code-grader check `imperative_stderr` (8th deterministic check). hook-patterns.md PostToolUse limitation footnote. Example 4 stderr tightened to bare imperatives.

**Tests:** 70 total (+6 imperative_stderr tests).

---

### v0.3.3 — *In progress* (2026-05-24)

Small, non-structural slice from the v0.3.2 analysis. Companion plan at `docs/superpowers/plans/2026-05-24-self-improving-claude-v0.3.3.md`. Ships before v0.4 brainstorming starts.

---

## Planned (v0.4 – v1.0)

### v0.4.0 — Foundation for Autonomy

**Theme:** Make the eval trustworthy and the knowledge base the single source of truth — so that everything after v0.4 can build *on top of* a measurable, ratchetable substrate.

**Headline:**
- **Track 6 — Eval integrity.** Sandbox harness verifies generated hooks actually fire (not just pass shape checks). Eval drives the real `SKILL.md`, not the `prompt_template.md` proxy. Noise-penalizing aggregation + a fixed grader. Negative / restraint fixtures.
- **Track 7 — Knowledge re-grounding.** Back-propagate v0.3 lessons into `docs/knowledge/`. Single-source the references (generated from knowledge or via `@../` if a re-probe shows it now works).

**Opportunistic polish:**
- Track 3 — eval expansion to ~12-15 fixtures, conflict UX smoke test, fixture 004 redesign.
- Track 4 — productize `claude-cli` as third eval backend, GitHub Actions CI scaffolding.
- Track 5 — `/improve-uninstall` real-project smoke test, document the dogfooding loop in CONTRIBUTING.md.

**Explicitly deferred (was originally v0.4):**
- Composed PostToolUse + Stop hooks (Tracks 1+2) — moved to v0.5 candidates because they're features, not foundation. May be obsoleted by v0.5's loop if it surfaces them automatically.

**Exit criteria — all required before tagging v0.4.0:**
- [ ] `evals/run.py` drives the actual `SKILL.md` (not a separate template)
- [ ] Sandbox harness can install a generated hook into a temp project and verify it fires
- [ ] At least 2 negative / restraint fixtures present
- [ ] References are single-sourced (`@../` resolves OR generator script in pre-commit)
- [ ] All four prior baselines (gemma / Haiku / Sonnet / Opus) re-run against the new eval; deltas committed
- [ ] No `# TODO` or `# FIXME` in `docs/knowledge/`

**Decision gate at exit:** Look at v0.4's baseline scores. Are they meaningfully different from v0.3.2? If the new behavioral eval surfaces failures the shape-eval missed, those become v0.4.x patches BEFORE v0.5 starts.

**Bigger decision gate:** Vision-first or features-first for v0.5? (See v0.5 below.)

---

### v0.5.0 — *The fork in the road*

**Two candidate themes; choose during v0.4 dogfooding, before brainstorming v0.5.**

#### Path A — "The Self-Improvement Loop" (vision-aligned)

The moment "self-improving-claude" becomes literal. Build the autonomous loop from VISION.md.

Components:
- **Bootstrapped binary assertions** — per `## Step N` heading, generate pass/fail checks (Claude drafts, human curates). This replaces the subjective model-grader axis with deterministic behavioral assertions, which the loop can optimize against.
- **Edit-proposer** — a script/skill that proposes ONE small change to a SKILL/reference file each iteration.
- **Score delta vs git baseline** — `evals/run.py` extended to auto-compare against the previous committed baseline.
- **Git ratchet** — commit if score went up; `git reset --hard` if down.
- **Loop driver** — runs N iterations with cost-cap, time-cap, edit-count-cap, full audit log.
- **CLI command** — `python3 -m self_improving_claude.auto` or similar; you start it before bed, you read the log in the morning.

**Why this path:** Honors the project name. v0.4 made it possible; v0.5 makes it real.

**Risk:** Genuinely hard. The binary-assertion bootstrapping is itself a mini-project.

**Bonus:** If the loop works, it may discover composed hooks (Path B's headline) on its own — by editing the procedure / rubric / examples until proposals start including them. The loop replaces hand-coded feature development.

#### Path B — "Composed Hooks + Auto-Collect" (feature-aligned)

The original v0.4 headline before vision-prioritization. Build the structural enforcement primitive.

- **Track 1 — Composed PostToolUse + Stop** with shared state file, recursion-guard, new Example 6, new feedback mode `weak-enforcement`, fixture 008.
- **Track 2 — Auto-collect** Stop hook for pattern detection, opt-in env-var, candidates.jsonl flow, telemetry schema extension.

**Why this path:** Concrete user value. Closes a known gap from v0.3 dogfooding. Lower risk than building the auto-loop.

**Risk:** If we ship Path B without ever building the loop, the project name remains aspirational. v0.6+ becomes "we'll get there eventually."

**Recommendation if forced:** **Path A.** The vision says "self-improving" is not a metaphor. v0.5 is where that promise either gets paid or gets quietly converted into a different project. Path B's deliverables can re-emerge naturally from Path A's loop — composed hooks is the kind of orchestrator-rubric change the loop will discover when it tries to drive `fixture 006`'s score upward.

**Exit criteria (Path A):**
- [ ] Loop completes 50+ iterations unattended without crashing
- [ ] At least one fixture's average score improves by ≥1.5 points across the run
- [ ] Audit log shows every edit, its score delta, and the keep/reset decision
- [ ] Reproducible: re-running the loop from the same baseline produces similar (not identical, but directionally consistent) improvements

**Exit criteria (Path B):**
- [ ] Form 5b (composed hooks) is in the procedure ladder, with Example 6
- [ ] Fixture 008 catches the composed-hook regression case
- [ ] Auto-collect produces non-empty candidates.jsonl in real dogfooding sessions
- [ ] Stop-hook recursion-guard verified (no infinite loop possible)

---

### v0.6.0 — Activation Frontier (assumes v0.5 = Path A)

**Theme:** Self-improve the *trigger* of the skill, not just the body.

A skill that never fires is worthless (VISION.md §"Two frontiers"). Currently `/improve` and `/improve-init` are user-triggered by typing — but the project will eventually grow model-invoked skills, and even the user-invoked ones have descriptions that affect when Claude suggests them.

Components:
- **Trigger-accuracy fixtures** — synthetic "should this skill fire for prompt X?" pairs. Some positive ("user just saw a bug" → /improve should fire), some negative ("user asks for unrelated help" → /improve should NOT be suggested).
- **Description-optimization in the same loop** — the auto-research loop from v0.5 extended to also edit skill frontmatter `description` fields, scoring against trigger-accuracy fixtures.

**Exit criteria:**
- [ ] At least 10 trigger-accuracy fixtures (5 positive, 5 negative)
- [ ] Loop can optimize both axes (description for trigger, procedure for output) in one run
- [ ] False-positive rate on negative fixtures stays under 10%

*(If v0.5 went Path B, v0.6 either becomes Path A — the loop — or activation-frontier is conditional on the loop existing. Likely re-plan at v0.5 exit.)*

---

### v0.7.0 — Night-Shift Packaging

**Theme:** Make the loop genuinely unattended-overnight-safe.

VISION.md §"The night shift" — the deepest temporal shift. Improvement decouples from human attention.

Components:
- **Resource caps** — wall-clock time, total cost, total edits, model-call count. Loop respects all and stops cleanly.
- **Stop conditions** — perfect score reached; N iterations with no improvement; cost cap hit; manual interrupt.
- **Sleep-safe logging** — every edit, every score, every decision logged with timestamps. Read-the-log-in-the-morning UX.
- **Notification hooks** — optional: "wake me when score crosses X" or "wake me when the run finishes."
- **Resume-from-checkpoint** — runs that interrupt cleanly can resume from the last committed state.

**Exit criteria:**
- [ ] Loop runs for 8+ hours unattended without intervention
- [ ] Reads cleanly from log: "ran 247 iterations, kept 31, score 7.4 → 8.9"
- [ ] Cost-cap enforcement validated against a real run
- [ ] Recovery from mid-run crash returns to last-good state

---

### v0.8.0 — Multi-Skill Generalization

**Theme:** The loop works on ANY skill, not just self-improving-claude's own.

The most consequential extension. Up to v0.7 the loop optimizes `plugin/skills/improve/SKILL.md` against `evals/`. The vision says any skill should be able to self-improve.

Components:
- **Generic skill input** — `improve-skill <path/to/SKILL.md> --eval <path/to/evals/>` works for any skill that ships with an eval suite.
- **Eval scaffolding helper** — when a skill ships without an eval suite, a separate sub-command (`improve-skill scaffold-evals <skill>`) bootstraps an initial set of binary assertions from the skill's own instructions (the VISION.md "Authoring the suite should itself be assisted" pattern).
- **Documentation overhaul** — README + CONTRIBUTING explain how to add `improve-skill`-compatible evals to a new skill.
- **Cross-skill validation** — running on a different skill (e.g. superpowers:writing-plans) catches assumptions baked into the loop that wouldn't generalize.

**Exit criteria:**
- [ ] Loop successfully optimizes at least one external skill (a real one from the superpowers plugin or similar)
- [ ] `scaffold-evals` produces a usable starting eval suite for a fresh skill
- [ ] Documented onboarding: from "I have a skill" to "my skill is now self-improving" in ≤30 minutes

---

### v0.9.0 — Hardening & Sharing

**Theme:** The loop is production-grade.

Components:
- **CI / GitHub Actions** integration — the loop can run as scheduled overnight job on a repo.
- **Reproducibility** — every committed improvement carries a metadata blob (iteration log, baseline scores, model used) so others can verify it wasn't lucky noise.
- **Diff sharing** — `improve-skill share-last` produces a PR-ready diff with metadata for sharing improvements back upstream.
- **Backpressure** — long runs surface intermediate state via heartbeat; orphaned runs get cleaned up.
- **Marketplace publish** — submit PR to `anthropics/claude-plugins-official` (the `docs/anthropic-marketplace-pr.md` template made real).

**Exit criteria:**
- [ ] GitHub Actions workflow can run the loop on a schedule (e.g. nightly cron)
- [ ] Every kept-improvement commit includes a reproducibility blob
- [ ] PR submitted to anthropics/claude-plugins-official
- [ ] 3rd party can clone the repo and run a single loop iteration with no extra setup

---

### v1.0.0 — General Availability

**Theme:** The project's name is no longer a promise — it's a description.

What v1.0 means concretely (from VISION.md "Success looks like"):
- [ ] A new skill can ship with its eval suite from day one (tooling supports it, docs make it easy)
- [ ] "Make this skill better" is a runnable command (the v0.7+ unattended loop)
- [ ] Every improvement is provable (committed diff tied to score delta)
- [ ] Available via `claude plugin install self-improving-claude` from the official marketplace
- [ ] At least one external skill (not ours) is documented as having been self-improved using the loop, with before/after scores

v1.0 is when humans on the project spend their hours on **taste and targets**, never on the grind of manual iteration. The loop owns the mechanical. The human owns the meaning.

---

## Patch policy (v0.x.y between majors)

### What qualifies as a patch

- A real bug surfaced in dogfooding (e.g. v0.3.1's enforcement-shape gap)
- A small refinement that's text/config-only, not structural (e.g. v0.3.2's bad/good stderr pairs)
- A missing test added retroactively (e.g. v0.3.2's `imperative_stderr` grader)
- A documentation fix surfaced by reader confusion
- A knowledge-base back-propagation (e.g. anything in Track 7 that gets ad-hoc-fixed before v0.4)

### What does NOT qualify as a patch (= bump minor instead)

- A new user-facing feature (new slash command, new form, new event-hook integration)
- A new eval grader axis (those need their own minor-version conversation about what they measure)
- Structural changes to skill / reference layout
- Anything that requires brainstorming → spec → plan flow

### Patch shipping checklist

- [ ] Branch + commit + dual-copy verified (until v0.4 makes this structural)
- [ ] All tests pass on the patched branch
- [ ] CHANGELOG entry under correct version heading
- [ ] `plugin.json` version bumped
- [ ] `evals/results/README.md` baseline notes updated if grader behavior changed
- [ ] Tag annotated with one-line description
- [ ] If patch addresses something in a feedback memory, the memory gets a "→ resolved in vX.Y.Z" footnote

### When to stop patching and bump minor

When the issues found in dogfooding stop touching the same surface. If v0.3.1 fixed stderr discipline and v0.3.2 added measurement for it and v0.3.3 fixed [whatever you're patching], and then a week of dogfooding surfaces no patches, v0.3 is stable. Now v0.4 is the next conversation.

---

## Decision gates that survive across versions

Two open questions worth holding in mind through every release until they get answered:

1. **Will the v0.5 fork resolve to Path A (loop) or Path B (composed hooks)?** — depends on what v0.4 dogfooding surfaces. Likely re-decide at v0.4 exit. Default assumption: Path A.

2. **At what point does the orchestrator stop being human-authored?** — Right now, every change to `plugin/skills/improve/SKILL.md` is hand-written. After v0.5 Path A, some changes may come from the loop. After v0.6+, possibly *most* changes. v0.8 makes this true for any user skill, not just ours. v1.0 is when this is the norm, not the exception. There's no specific release where this flips — but it's worth tracking as a *trend* between releases.

---

## How to use this roadmap practically

1. **At session start:** read the current "in progress" or "planned" section for the version you're working on. Re-read the exit criteria. Refresh memories listed there.

2. **Before starting v0.(x+1):** confirm v0.x's exit criteria are checked off. If patches are still surfacing in dogfooding, don't start the next major — finish the current one.

3. **Brainstorming a new major release:**
   - Reload feedback memories from `~/.claude/projects/-Users-timkiefer-Desktop-Projects/memory/`
   - Reload the relevant section of this roadmap
   - Reload the v0.4-backlog (or its successor) if there are unresolved tracks
   - Then run `superpowers:brainstorming` → spec → `writing-plans` → `subagent-driven-development`

4. **Mid-version dogfooding** (e.g. between v0.4.0 and a possible v0.4.1):
   - Note friction in feedback memories
   - If a patch is warranted, follow the patch shipping checklist above
   - If the friction is bigger than a patch, it goes in the NEXT major's backlog, not the current major's

5. **When tagging a major:**
   - Update this roadmap's "Done" section with what landed and the key dogfooding lessons
   - Update the version's "Why it mattered" — this is forward-looking when written, becomes retrospective when filled in
   - Move the version from "Planned" to "Done"

---

## Living document

This file is rewritten freely between releases. The roadmap is a tool for forward planning, not a contract. If v0.5 turns out to be different than what's written above (e.g. v0.4 surfaces something that demands its own release), rewrite this doc as part of the v0.5 brainstorm.

The only invariants:
- **VISION.md is the north star** — it doesn't change.
- **v1.0 means the vision is realized** — it doesn't slip to a feature release.
- **Patches don't introduce features** — that's what minors are for.
- **Majors don't ship without exit criteria** — measure first, declare done second.

---

**Last updated:** 2026-05-24, alongside v0.3.3 development.

**Linked artifacts:**
- [`docs/VISION.md`](VISION.md) — what we're building toward
- [`docs/superpowers/specs/`](superpowers/specs/) — design specs per major
- [`docs/superpowers/plans/`](superpowers/plans/) — implementation plans (writing-plans output) per major
- [`docs/knowledge/`](knowledge/) — distilled Claude Code course material
- [`evals/results/README.md`](../evals/results/README.md) — baseline reference document
- [`CHANGELOG.md`](../CHANGELOG.md) — what landed when, with notes
