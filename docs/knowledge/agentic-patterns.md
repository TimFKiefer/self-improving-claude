# Agentic Patterns (Workflows, Loops, Routing)

Source: distilled from Anthropic's *Building with the Claude API* course (Section: Agents and workflows). Confidence: **high** — direct from course material with our domain mapped on top.

> **Why this matters:** the SKILL is the orchestrator behind `/improve`. The course's framing — *workflows are predefined steps; agents are goals + tools; prefer workflows when you can* — is exactly the design lens we need. Our skill is a **workflow** with a few specific agentic patterns embedded.

---

## 1. Workflow vs agent — the framing

| | Workflow | Agent |
|---|---|---|
| **You provide** | A predefined sequence of steps. | A goal + tools. |
| **Claude does** | Each step focused on one subtask. | Plans and executes its own sequence. |
| **Best for** | Tasks you can picture ahead of time. | Tasks where inputs are unpredictable. |
| **Tradeoff** | Higher reliability, easier to test, less flexible. | More flexible, lower task-completion rate, harder to instrument. |

The course's recommendation is blunt:

> *"Always focus on implementing workflows where possible, and only resort to agents when they are truly required."*

For `self-improving-claude`, `/improve` and `/improve-init` are **workflows** — we know exactly the sequence (gather context → propose → review → install → instruct rewind). Inside that workflow we use a few agentic patterns for the steps where flexibility matters.

---

## 2. The four workflow patterns we care about

### 2a. Chaining

Break a complex task into a sequence of smaller subtasks where each step's output feeds the next. Each step focuses on one thing.

**Our use:** the per-hook approval loop. For each candidate hook, run a focused chained sequence: draft → validate syntax → render diff → ask user → on approval, write file → on rejection, drop. Each step does one thing well.

The course's other example — *use a second call to fix violations of constraints the first call ignored* — is also relevant: after drafting a hook, a short chained pass that asks Claude to *self-critique* the proposal (does it meet the rubric in `prompt-engineering.md`?) before showing it to the user. Cheap quality lift.

### 2b. Routing

Categorize the input, then dispatch to a specialized pipeline. Each pipeline is optimized for one category.

**Our use:** `/improve` accepts free-text `$ARGUMENTS`. The first step of the skill is routing:

| Input shape | Route |
|---|---|
| Empty | Default mode — analyze recent chat context for the most-recent observable problem. |
| Feedback ("the foo-hook just blocked something legit") | Feedback mode — log it, refine the specific hook, no new proposals. |
| Directive ("add a rule that prevents X") | Directive mode — target the named problem, propose 1 hook. |
| Other free-text | Inquiry mode — treat as a description of a problem the user just witnessed. |

Each route uses a slightly different sub-prompt. The course's pattern: do the categorization with a focused Claude call, then dispatch.

### 2c. Parallelization

Run independent subtasks simultaneously, then aggregate.

**Our use, conservatively:** when proposing multiple hooks in `/improve-init`, each hook's drafting + validation could run in parallel (independent of one another). The course pattern: split → run in parallel → aggregate ranked results.

For v1, sequential is fine. Flag for later optimization. Document so we don't bake in sequential assumptions.

### 2d. Evaluator-Optimizer

A producer generates output. A grader evaluates it. If the grade is below a threshold, feedback goes back to the producer and the cycle repeats.

**Our use:** within the hook-drafting step. After generating a candidate hook, the skill can run a quick *grader* pass (model-based, just for the rubric in `prompt-engineering.md`). If the grade is low (e.g. missing rationale, wrong matcher), feed the critique back and ask for a revision. Cap at 2 retries.

This is the same pattern we use for the offline eval (`eval-methodology.md`), but applied at runtime inside `/improve` itself. Two retries trade a small latency cost for a meaningful quality bump on tricky cases.

---

## 3. Environment inspection (a non-negotiable agent principle)

The course makes a strong claim:

> *"Claude operates blindly. It needs to observe the results of its actions to work effectively."*

The example: before Claude can modify a file, it must read the current contents. Before clicking a button (in computer use), it needs a screenshot of the result.

**Mapping this onto our SKILL:**

| Before … | Inspect … |
|---|---|
| Drafting a hook | The current `.claude/settings.json` and `.claude/hooks/*` — so we don't propose duplicates of existing rules. |
| Suggesting a `permissions.deny` rule | The existing `permissions` block — same reason. |
| Writing to `settings.json` | The current state, so the merge is non-destructive (see `settings-and-permissions.md` §6). |
| Instructing rewind | Confirm the chat has unsaved files / no other work mid-flight that the user would lose. |

The SKILL's first concrete step (after routing) must always be *inspect current state*. The rubric forbids proposing a hook without first showing it would not collide with existing config.

---

## 4. Designing tool surfaces (Claude Code's lesson)

The course's takeaway from Claude Code itself: provide **reasonably abstract tools**, not hyper-specialized ones. Bash + Read + Write + Edit + Glob + Grep cover an enormous range; "refactor code" would have been a worse design.

**For our generated hooks**, this principle means: when designing hook scripts, prefer simple, single-purpose blocks (e.g. "block any Bash command containing `pnpm test`") over over-clever composite logic. Each hook does one thing; users compose them by enabling multiple.

When designing hooks that themselves call the Agent SDK (the "query duplication" pattern from the original hooks doc), keep the sub-Claude's prompt narrow. Pass it abstract tools (Read, Grep) and a focused goal. Don't try to build a mini-agent inside every hook.

---

## 5. When agents *would* be the right shape

The course flags scenarios where agents beat workflows: unpredictable user input, tasks whose steps can't be enumerated in advance.

**For us, the candidate agentic step is the "draft a hook from scratch" pass.** Inputs are unpredictable (any project, any bug). Steps aren't fixed (sometimes the right answer is a hook, sometimes a `permissions.deny` rule, sometimes a `CLAUDE.md` note). Treating this single step as a mini-agent — give Claude the rubric and the inspection results, let it choose the form — is the right shape.

Everything *around* that step (routing, approval loop, file writes, rewind instruction) is a strict workflow.

---

## 6. The decision rubric

Quick reference for SKILL design choices:

- **Can I enumerate the steps in advance?** → workflow.
- **Is the step inherently creative / branching?** → small agentic island inside the workflow.
- **Multiple independent candidates?** → parallelize.
- **Output keeps violating constraints?** → chain a critique/revision pass.
- **Different input types need different handling?** → route at the top.
- **Quality matters more than latency on a step?** → evaluator-optimizer with a retry cap.

---

## 7. Implications for `self-improving-claude`

1. **The SKILL is a workflow, but contains agentic islands.** Document this in the SKILL body so future contributors don't refactor it into a pure agent.
2. **Route at the top of `/improve`.** Empty input ≠ directive ≠ feedback. Each gets a focused sub-prompt.
3. **Environment-inspect before every change.** Read existing `.claude/` state; never propose without it; never write without re-reading.
4. **Use the evaluator-optimizer pattern at runtime, capped at 2 retries.** Cheap quality lift on hard cases.
5. **Use the offline eval (`eval-methodology.md`) for prompt-level iteration.** Use the runtime evaluator-optimizer for per-request quality. These are the same pattern at different scopes.
6. **Generated hooks should be small, abstract, single-purpose.** Match Claude Code's own tool-design philosophy.
7. **Defer parallelization until measured.** Sequential first; parallelize when latency in `/improve-init` becomes a real complaint.
