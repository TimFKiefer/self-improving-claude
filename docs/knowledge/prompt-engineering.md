# Prompt Engineering for the `self-improving-claude` SKILL

Source: distilled from Anthropic's *Building with the Claude API* course (Section: Prompt engineering techniques). Confidence: **high** — these are well-established Anthropic-recommended techniques.

> **Why this matters:** the `SKILL.md` we ship is *itself* a prompt — when invoked, its body becomes Claude's active instructions. Whether `/improve` proposes well-crafted hooks or sloppy ones depends almost entirely on how that prompt is written. The techniques below are how we make it reliable.

---

## 1. The five techniques, ranked by leverage

| Technique | One-line summary | Where we use it |
|---|---|---|
| **Be clear and direct** | Lead with action verbs, write instructions not questions. | Opening lines of the SKILL body and every per-step instruction. |
| **Be specific** | List output guidelines *and* (for complex tasks) process steps. | The "what makes a good hook" rubric the skill applies. |
| **Structure with XML tags** | Wrap interpolated content in named tags so Claude can tell instructions from data. | Wrapping chat-context, project-code samples, telemetry-log excerpts. |
| **Provide examples (one-shot / multi-shot)** | Show input/output pairs that demonstrate the pattern. | Example "good hook" and "rejected hook" pairs inside the SKILL. |
| **Temperature control** | Lower for deterministic tasks, higher for creative ones. | Likely irrelevant in v1 (we use the user's Claude Code session and don't control temperature) — noted for completeness. |

The first four are what we'll actually wield. Treat the rest of this doc as the spec for *how* to wield them inside the SKILL.

---

## 2. Be clear and direct

**Principles:**

- Use simple language; no ambiguity.
- Use instructions, not questions. Start with action verbs: *Write*, *Generate*, *List*, *Identify*, *Block*.
- The first line of the prompt is the most important.

**Anti-example (vague):**

> "What hooks might be good for this project?"

**Pro-example (directive):**

> "Identify up to 5 candidate hooks that would have prevented the issue described in the conversation context below."

For our SKILL, every step should be an imperative: *Read the recent chat. Identify candidate problems. Draft hooks. Show each diff. Wait for approval. Write files. Instruct the user to rewind.*

### Amplifier: prefer numeric anchors over vague adjectives

"Be concise" is weak; "≤ 25 words" is enforceable. When you can attach a specific number — line counts, sentence limits, max examples, retry caps — do so. Models treat numbers as hard rules and adjectives as taste-level preferences.

In our rubric: command-hook scripts ≤ 60 LOC, prompt-hook prompts ≤ 5 sentences, ~5 candidates per `/improve` run, cap 2 revision passes. The numbers live *inside* the criterion so the model self-checks against them, not in a separate doc that gets ignored.

### Amplifier: negative imperatives suppress default behaviours

Models have defaults — narrate before acting, write decorative comments, summarise-and-stop, hedge with "consider" or "verify." A positive imperative ("be direct") often loses to those defaults. A negative imperative *names the behaviour to suppress* and beats them more reliably.

Pattern: name the *default* you're suppressing, then give the alternative.

- "Don't explain WHAT the code does — identifiers already do that. Explain WHY when the why is non-obvious."
- "Do not use `audit`, `consider`, `verify`, `review` in stderr — they license inaction. Use `Fix each`, `Update each`, `BLOCKING:`."
- "Don't silently propose nothing for a real problem — surface a candidate."

A bare negative rule without an alternative often leaves the model with no fallback, so it backslides. Always name what to do *instead*.

---

## 3. Be specific

Three flavors, all worth using:

### Output-quality guidelines (always use)

A list of qualities the output must have. Acts as a safety net.

For our SKILL:

> Each proposed hook must:
> - Solve a *specific* problem grounded in observed behavior, not a hypothetical
> - Bind to exactly one event (PreToolUse / PostToolUse / etc.) with a precise `matcher`
> - Use absolute paths (per the `$PWD` pattern)
> - Begin with a stdin → JSON → branch-on-`tool_name` header (see `tools-reference.md`)
> - Include a one-sentence rationale that names what bug it prevents and why a hook (not `permissions.deny`) is right for it
> - Be ≤ 60 lines

### Process steps (use for complex multi-step tasks)

A numbered procedure. Per the course: *"add step-by-step instructions when you're dealing with troubleshooting complex problems, decision-making scenarios, critical thinking tasks, or any situation where you want Claude to consider multiple angles."*

For our SKILL's hook-drafting step:

1. Identify the *specific* observed problem from the chat / telemetry.
2. Decide: is this expressible as a `permissions.deny` rule? If yes, propose that instead of a hook.
3. If a hook is needed, pick the correct event (`PreToolUse` for blocking, `PostToolUse` for follow-up).
4. Determine the correct `matcher` based on `tools-reference.md`.
5. Draft the script body following the standard boilerplate.
6. Validate the script's syntax mentally before showing to the user.
7. Write a one-sentence rationale.

### Decision boundaries: pair "when to use" with "when NOT to use"

Per-tool / per-form guidance is twice as strong when it explicitly names both sides of the decision. Listing only "when to use" teaches *mechanism*; pairing it with "when NOT to use" teaches the decision *boundary*. Without the negative side, the model over-applies the tool to cases that look superficially similar.

For our SKILL:

> **Use `permissions.ask`** when "warn and let me confirm" is the right semantic (`git push`, `npm publish`).
> **Do NOT use it** when the action should be uniformly blocked (use `permissions.deny`) or when the check needs to reason about *intent* across novel invocation shapes (use a prompt-hook).

Already applied in Step 4's lightest-viable-form rule; the principle is to extend it to every form/tool guidance line, not just form selection. The C1′ form-discipline guard (Step 7) is another concrete instance — "apply the trace to command-hooks already chosen per Step 4; **do not** convert a lighter form to a command-hook to earn a fires check."

The combination of *guidelines + process + decision-boundaries* is what the course calls "professional prompting." We use all three.

---

## 4. Structure with XML tags

The pain point: when a prompt interpolates lots of content (chat history, code, logs), Claude can struggle to tell instructions from data. XML tags solve this.

**Anti-pattern:**

```
Here is the chat context and the project file. Suggest hooks.
{chat_context}
{file_contents}
```

**Pattern (with XML):**

```
Suggest hooks based on the following.

<recent_chat>
{chat_context}
</recent_chat>

<project_snapshot>
{file_contents}
</project_snapshot>

<telemetry_excerpt>
{telemetry_log}
</telemetry_excerpt>
```

Use **descriptive names** (`<recent_chat>` beats `<data>`). For our SKILL the natural tags are:

| Tag | Contains |
|---|---|
| `<recent_chat>` | Last N messages from the live session (reactive `/improve`) |
| `<project_snapshot>` | Sampled code / CLAUDE.md / package.json |
| `<telemetry_excerpt>` | Relevant rows from `.claude/self-improving-claude/telemetry.jsonl` |
| `<existing_hooks>` | What's already in `.claude/settings.json` so we don't propose duplicates |
| `<user_directive>` | The free-text `$ARGUMENTS` if the user gave any |
| `<rubric>` | The output-quality guidelines from §3 |
| `<examples>` | One-shot / multi-shot example hook proposals |

This is the structure the SKILL builds before drafting hooks.

---

## 5. Provide examples (one-shot, multi-shot)

The course's strongest signal: *"examples are particularly powerful because they show rather than tell."* Instead of describing what a good hook looks like, demonstrate it.

**Pattern:**

```
<example>
  <observed_problem>
    Claude ran `pnpm test` 3 times in this session; each failed because the
    project uses `pnpm test:ci` (the bare `pnpm test` opens an interactive
    watcher, never exits).
  </observed_problem>

  <proposed_hook>
    Event: PreToolUse
    Matcher: Bash
    Script: <inline JS that blocks `pnpm test` and suggests `pnpm test:ci`>
    Rationale: A deterministic block is cheaper than relying on Claude to
    remember; a permissions.deny rule wouldn't work because the substring
    "pnpm test" is also the prefix of the correct command.
  </proposed_hook>
</example>
```

**Best practices from the course:**

- Wrap each part in clearly named XML tags.
- Be explicit: "Here is an example of a problem and an ideal hook proposal."
- After the example, **explain why the output is good** (one sentence). The course flags this as a frequently-missed step that significantly improves results.
- Include examples that match your highest-value failure cases — most-common, most-painful, most-easily-mishandled bugs.
- Use multi-shot when you need to cover meaningfully different scenarios (different tools, different bug types).

**Why the "explain why" line is load-bearing.** The example shows the *surface*; the "why" line extracts the *principle* the model generalises from. Without it, models imitate the wrong feature of the example (the specific tool name, the variable shape) instead of the property you meant. The same holds in reverse for negative/rejected examples — the "why it's *bad*" line is what inoculates against the failure mode; the bad code is just an illustration. Treat the "why" line as the example's payload, not its caption.

**Use rejected/negative examples for known failure modes.** A negative example with a sharp "why it's bad" line beats a positive-only rule for failure modes the model has a default tendency toward (e.g. reading the wrong stdin field, decorative comments, premature summary). Keep them rare and high-value — one or two in `examples.md` next to 3–5 positives is the right ratio; more dilutes the signal. Caveat (from our own eval, 2026-05-28): if the failure mode is already heavily inoculated by procedure + rubric + skeleton, an additional negative example may be *redundant* and yield no measurable gain — measure before committing.

For our SKILL: maintain 3–5 curated examples in the SKILL body (or in `references/examples.md` and `@`-mentioned). Cover at minimum: a Bash-blocking hook, a `permissions.deny` rule (to demonstrate when to prefer it), and a `PostToolUse` formatter.

---

## 6. Temperature (note for completeness)

The API course covers temperature (0 = deterministic, 1 = creative). For deterministic tasks like syntax-validation, low temperature wins; for brainstorming hooks, higher is fine.

**Relevance to us in v1:** none — we run inside the user's Claude Code session and don't control the model's sampling parameters. Flagged only so we recognise it later if we ever move the analyzer to a dedicated Agent SDK call (architecture option B from the original brainstorm).

---

## 7. Connection to evals (preview)

The course emphasizes pairing prompt engineering with *measurement* — write a prompt, evaluate it against a dataset, iterate. We adopt that approach in a sibling doc: see `eval-methodology.md` for how we'll grade the SKILL's hook-generation quality so we know whether changes actually improve it.

The short version: don't change the SKILL "because it feels better." Run the eval, compare scores, decide.

---

## 8. The optimization loop — treat the prompt as trainable parameters

The earlier sections covered *writing* a prompt. This section is about how a prompt *evolves over time*. The framing: stop treating the skill body as a static document and start treating it as the parameters of a trainable network, where text edits are the gradient steps and the eval score is the loss. The SkillOpt approach (Microsoft Research, 2026) formalizes this; the discipline applies whether you cite the paper or not.

### The ML-analogue mapping

| ML concept | Text-space equivalent |
|---|---|
| Parameter | The skill document (`SKILL.md` / `orchestrator-procedure.md`) |
| Gradient step | One reflection-driven edit informed by an observed failure trajectory |
| Learning rate | The *edit budget* — how much text is allowed to change per step |
| Validation set | A held-out fixture subset never touched during iteration |
| Epoch / batch | Multiple rollouts (N≥2) before the keep/revert decision |

The mapping is not metaphor. Each row corresponds to a concrete artifact in the loop. Where one is missing, the loop is unstable in a predictable way (see §8.1–8.6).

### 8.1 Bounded edits (the textual learning rate)

A full rewrite of a working skill is catastrophic forgetting. The model *will* delete working logic to chase a marginal improvement on the metric in front of it. The fix is structural: cap each iteration to a small number of `add` / `delete` / `replace` edits — SkillOpt's reported sweet spot is 4–8.

**Where we already align:** the prompt-lab loop (May 2026) capped itself at one change per round — even tighter than 4–8. C1, C1′, C2, C3 were each a single localized addition. This is why C1 → C1′ recovery was clean: when C1's sonnet `model` regression was identified, we could attribute it to the specific block added and write a one-sentence fix (the form-discipline guard) without unwinding anything else.

**Implication:** keep the per-round edit cap explicit when launching future loops. If a candidate touches three steps and two references, it's not one candidate — it's three, and they need to be evaluated separately or the score delta is uninterpretable.

### 8.2 Compactness (skill files want to be short)

SkillOpt reports a median successful skill file of ~920 tokens. Long prompts give the illusion of capability but dilute the signal — every additional sentence is more attention budget the model spends parsing instructions rather than executing them.

**Where we DON'T align:** our skill is ~6× SkillOpt's median.

| File | Bytes | Approx tokens |
|---|---:|---:|
| `orchestrator-procedure.md` | 23,527 | ~5,500 |
| `SKILL.md` (preamble + procedure) | 25,249 | ~6,000 |
| `references/examples.md` | 11,011 | ~2,700 |

Two readings of this gap, both worth holding:

1. **Our task is genuinely more complex** than the median skill in SkillOpt's corpus — multi-form proposal generation with rubric self-critique, sandbox-fired hooks, deterministic stderr discipline, and explicit user approvals. A 920-token skill cannot cover that surface.
2. **We have real bloat to cut** — Step descriptions that could be tightened, repeated rubric callbacks, examples that are redundant given the procedure already inoculates against the failure mode (cf. the C2 negative-example experiment: rejected because it was redundant with Step 5's skeleton + Step 7's trace + rubric #13).

The honest test: cut a section. If the eval doesn't move, the section was bloat. The C2 round already validated this method.

**Implication:** treat compactness as a measurable axis in the next loop. A round whose only change is a deletion is a legitimate candidate — and if it doesn't regress, it's an improvement (less context budget consumed).

### 8.3 Validation gating: hold a set out, reject ties

Two coupled disciplines:

- **Held-out fixtures.** Some fixtures must never be visible to the iteration loop — they're the validation set. Edits that improve the training subset but regress on held-out are the textual equivalent of overfitting. Without held-out fixtures, every "improvement" is suspect.
- **Reject ties.** If an edit doesn't strictly improve the score, drop it. The cost of bloat is real (§8.2) and a neutral-effect edit pays that cost for no return.

**Where we already align:** the prompt-lab loop rejected C2 on a strict no-positive-signal rule (sonnet fire −0.17, opus code/model both slightly down — no positive across any model). We also rejected C3 reproducibly on sonnet model regression. The keep/reject discipline is in place.

**Where we DON'T align:** we have no held-out set. All 12 fixtures are visible to every iteration. SkillOpt would predict our adopted edits are partially overfit to the visible set; we cannot disprove this without holding some out.

**Implication for v0.4.x+:** carve a held-out subset (probably 3 of the 12 — one firing, one restraint, one shape-only) that's invisible during iteration and only consulted after a candidate clears the visible set. An edit that wins on visible but ties or regresses on held-out is rejected.

**Expected acceptance rate.** SkillOpt reports 1–4 edits actually clear the gate in a well-run optimization session. Our prompt-lab loop ran 5 candidates (C1, C1-confirm, C1′, C2, C3) and kept 1 (C1′). That's exactly the predicted range. If you find yourself keeping 4 out of 5 candidates, the gate is too lenient or the score noise is too high — probably both.

### 8.4 Slow state vs. fast state — and the protected-section invariant

A skill carries two kinds of memory and they don't mix:

- **Slow state.** Core identity, fundamental rules, procedure steps, rubric criteria. Changes only through deliberate, eval-gated iteration (the SkillOpt loop). Lives in `plugin/skills/_shared/`.
- **Fast state.** Per-session, per-project context. Changes every invocation. Lives in `preferences.md` (per-project + global), `feedback.jsonl`, `telemetry.jsonl`.

The hazard is structural: a fast-state mechanism that can write into slow-state files will eventually overwrite a hard-won lesson with a one-session preference. The fix is a hardcoded invariant — fast-state writers physically cannot touch slow-state paths.

**Where we already align:** Phase 1+2's preferences mechanism writes only to `${HOME}/.claude/self-improving-claude/preferences.md` and `${CLAUDE_PROJECT_DIR}/.claude/self-improving-claude/preferences.md` — never into `plugin/skills/**`. The `sync_skills.py` generator + pre-commit `--check` enforces the slow-state boundary structurally: any out-of-band edit to a generated skill file fails the pre-commit gate.

**Implication:** when adding new write paths (next-session context capture, learned-pattern persistence), preserve the invariant — fast-state files live under `.claude/self-improving-claude/`, never under `plugin/skills/`. Treat the boundary as a build-time check, not a convention.

### 8.5 Procedural knowledge is the real asset

A well-optimized skill file is more portable than the harness around it. The same optimized procedure can be loaded into Codex, Claude Code, or another agent runtime and reproduce the gains. The corollary: the highest-leverage place to invest is the skill *body*, not framework code around it.

**The small-model meta-strategy.** A small, cheap model paired with a heavily optimized skill file can approach frontier performance on procedural tasks — at a fraction of inference cost. Our prompt-lab data weakly supports this: at C1′, haiku reaches sonnet-class `code` and `install_rate` on several fixtures, though it stays noisier overall. The optimization absorbs the headroom the small model would otherwise lose.

**Implication:** treat the skill file as the product. The Python/eval scaffolding can be rewritten; the orchestrator procedure earned through iteration is what carries the value forward.

### 8.6 The verifier wall

This entire loop runs on an auto-grader. Where the grader is reliable (binary checks on hook shape, deterministic stderr-discipline patterns, "did the hook fire on its trigger envelope") the loop converges. Where the grader is unreliable (subjective rubric scores from an LLM judge with variance ≥ 0.5 per run) the loop chases noise.

This is exactly the boundary VISION.md draws ("binary truth, not taste"). SkillOpt's contribution is naming it as a hard wall, not a soft preference: subjective rubric axes don't just slow the loop, they actively *mislead* it — a candidate that earns +0.5 on a noisy axis and −0.05 on a deterministic one will look like a win, and the loop will keep it.

**Implication:** every new metric we add to the eval should be classified explicitly — deterministic (gating) vs. subjective (advisory). The deterministic ones decide keep/reject. The subjective ones flag candidates for human review but never gate the ratchet on their own. We already do this for `code` (deterministic, gating) vs. `model` (LLM-judge, advisory); the discipline is to keep it that way as the eval grows.

---

## 9. Implications for `self-improving-claude`

1. **Skeleton of the SKILL.md.** The body uses the structure §4 implies: a brief directive opening, then the rubric (§3 guidelines), then the procedure (§3 process steps), then `<examples>`, then placeholders for the runtime-injected `<recent_chat>` / `<project_snapshot>` / `<telemetry_excerpt>` / `<existing_hooks>` / `<user_directive>`.
2. **The rubric is load-bearing.** Without explicit "what makes a good hook" criteria, the model defaults to plausible-looking but vague proposals. The rubric in §3 is a starter; evolve it via the eval loop.
3. **Examples cost tokens but earn quality.** Keep the example set tight (3–5), curate carefully, and explain *why* each example is good. Don't pad.
4. **Imperatives everywhere.** Every line of the SKILL body that asks Claude to do something should start with a verb. No "would it be a good idea to…" type phrasing.
5. **XML tags are not optional.** Even at small interpolation sizes, the discipline of always wrapping injected data makes the SKILL robust as it grows.
6. **The skill body is the parameter grid (§8).** Treat each iteration as a gradient step: bounded edits, held-out validation, reject ties, separate slow state from fast state, classify metrics as gating vs. advisory. The loop is only as strong as these disciplines.
