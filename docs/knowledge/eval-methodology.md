# Evaluation Methodology

Source: distilled from Anthropic's *Building with the Claude API* course (Section: Prompt evaluation). Confidence: **high** — directly adapted from the course's eval workflow.

> **Why this matters:** the SKILL generates **arbitrary code** that runs in the user's project on every tool call. We cannot tell whether a SKILL prompt change helps or hurts hook quality by reading it. We need a measurement.
>
> The course makes this point bluntly: most engineers test a prompt once, tweak based on a corner case, then ship. Users will then provide inputs no one anticipated and the prompt breaks. The way out is an eval pipeline that scores the prompt against a dataset, so iteration is measurable.

---

## 1. The five-step workflow

The course's standard eval workflow:

1. **Write an initial prompt** (the SKILL body — already exists).
2. **Build a dataset** of representative inputs.
3. **Run the prompt** over each dataset entry, collecting outputs.
4. **Grade the outputs** with a grader (model-based, code-based, or both).
5. **Score → iterate → re-score.** Change the prompt, re-run, compare.

Each iteration on the SKILL is a tweak → re-run → score change. Don't ship a SKILL change without re-scoring.

---

## 2. The dataset

Each entry simulates a `/improve` invocation. Shape:

```json
{
  "id": "001-pnpm-test-loop",
  "trigger": "improve",
  "user_args": "",
  "fixture": {
    "project_files": "fixtures/pnpm-test-loop/",
    "recent_chat":  "fixtures/pnpm-test-loop/chat.md",
    "telemetry":    "fixtures/pnpm-test-loop/telemetry.jsonl"
  },
  "planted_problem": "Claude keeps invoking `pnpm test` (interactive watcher) instead of `pnpm test:ci`",
  "expected_hook_traits": {
    "event": "PreToolUse",
    "matcher": "Bash",
    "blocks_command": "pnpm test",
    "suggests_alternative": "pnpm test:ci"
  }
}
```

A v1 dataset of 10–20 carefully chosen entries covers the most common Claude-in-this-repo footguns. Per the course: keep the dataset small (2–3 entries) during fast iteration and only scale up for release-candidate validation.

### Generating dataset entries

The course recommends generating dataset entries with Claude (using Haiku for speed). For us:

- Each entry pairs a **planted bug pattern** with a **fixture project** and (optionally) a **fake chat transcript** that shows Claude tripping the bug.
- Fixtures live in `evals/fixtures/<id>/` so each is self-contained and committable.
- Some entries are hand-crafted (real-world bugs we've seen). Others can be model-generated.

---

## 3. The grader

The course's three options apply directly:

### Code-based grader (cheap, deterministic)

Programmatic checks on each proposed hook:

| Check | What it tests |
|---|---|
| Valid script syntax | `node --check` for JS, `python -m py_compile` for Python, `bash -n` for shell. |
| Stdin-reading boilerplate present | Regex / structural match against the standard header (`tools-reference.md`). |
| Absolute path in `command` | No relative paths. |
| Matcher matches a known event type | One of the 9 hook types we documented. |
| Generated `settings.json` is valid JSON | Parse it. |
| Generated `settings.json` doesn't clobber existing keys | Compare merge diff to expected. |

Each check returns 0 or 10 (course convention). Mean across checks = the syntax/format score.

### Model-based grader (flexible, slightly capricious)

A second Claude call rates how well a proposal solves the planted problem. The course's lesson: ask for **strengths + weaknesses + reasoning** alongside the score, otherwise the model defaults to ~6 for everything.

Prompt skeleton (adapted from the course):

```
You are an expert reviewer of Claude Code hook proposals. Evaluate
the proposed hook against the planted problem.

<planted_problem>
{planted_problem}
</planted_problem>

<proposed_hook>
{proposed_hook}
</proposed_hook>

<expected_traits>
{expected_hook_traits as JSON}
</expected_traits>

Provide your evaluation as JSON with:
- "strengths": 1-3 specific things the proposal does right
- "weaknesses": 1-3 specific things it does wrong or misses
- "reasoning": 2-3 sentences explaining the score
- "score": integer 1-10 where 10 = exactly solves the planted problem
```

Pre-fill the assistant message with ` ```json ` and stop on ` ``` ` to get clean JSON (course's structured-data technique).

### Combining scores

The course's pattern:

```
final_score = mean(code_score, model_score)
```

Equal weight by default; reweight if one matters more.

---

## 4. Running the eval

Sketch of the test runner (adapted from course code, but our domain):

```python
def run_test_case(entry):
    # 1. Prepare fixture: copy fixture files to temp dir, plant chat / telemetry
    workspace = prepare_fixture(entry["fixture"])

    # 2. Invoke /improve in a sandboxed Claude Code session (or a SKILL test harness)
    proposed = invoke_skill(
        skill="self-improving-claude",
        workspace=workspace,
        user_args=entry["user_args"],
    )

    # 3. Grade
    code_score  = grade_by_code(proposed, entry["expected_hook_traits"])
    model_score = grade_by_model(proposed, entry["planted_problem"])

    return {
        "id":           entry["id"],
        "proposed":     proposed,
        "code_score":   code_score,
        "model_score":  model_score,
        "final_score":  (code_score + model_score) / 2,
        "reasoning":    model_score_reasoning,
    }
```

Report: a JSON file + a tabular summary. Per-entry score + dataset average. Track scores in git so prompt-engineering progress is visible over time.

---

## 5. What the eval *can't* tell us

A high eval score doesn't guarantee the generated hook works in production. The eval tests:

- Does the proposal target the right problem?
- Is the script syntactically valid?
- Does it follow our conventions?

The eval doesn't test:

- **Does the hook fire correctly when installed?** That's an integration test (start a sandbox Claude Code session, install the hook, trigger the matching tool, confirm exit-code 2 / formatter ran / etc.).
- **Does the hook generate false positives in normal use?** Requires the dogfooding loop — the user runs `/improve` "the foo-hook blocked something legit" feedback channel.

So the eval is a *guardrail*, not a green light. We pair it with:

- Integration tests for a handful of canonical hooks (probably hand-written in v1).
- The dogfooding feedback channel.

---

## 6. Implications for `self-improving-claude`

1. **`evals/` directory at repo root.** Holds `dataset.json`, `fixtures/`, and the runner.
2. **Build the eval before scaling the SKILL.** Even 5 dataset entries beat 0. Without it, every SKILL change is a guess.
3. **Track scores in git.** Commit eval results as JSON next to the SKILL. Reviewers can see "this change took the average from 7.2 to 8.1."
4. **Code grader > model grader where both apply.** Cheaper, faster, deterministic. Use the model grader only for the "did it actually understand the problem" dimension.
5. **Use Haiku-class models for graders and dataset generation.** Course's recommendation; faster and cheaper for evaluative tasks.
6. **A failing eval entry is a unit test.** Treat it the same way: don't ship a SKILL change that regresses a previously-passing entry without a documented reason.
7. **Pair with at least one integration test.** Eval scores the proposal; integration tests confirm the proposal *runs* correctly when installed.

## Variance budget (v0.5.1)

The sandbox eval runs each fixture **once** per measurement. Single-shot scores
carry **~±3 points/fixture** of run-to-run variance (LLM nondeterminism in both
the skill-runner and the judge). That noise floor is larger than the small score
deltas the auto-loop ratchet gates on — so a noise spike can clear epsilon and
get a bad edit committed. This is the load-bearing v0.5.0 lesson: the haiku
50-iter run kept 5 commits that all passed their in-iter held-out gates, but a
*fresh* re-check (same code, different scores) showed the held-out had drifted,
and all 5 were reverted.

Two responses, both shipped in v0.5.1:

1. **Confirmation re-run (best-of-3).** Before a candidate keep is committed, the
   loop re-measures the target + held-out twice more and commits only if the
   visible gain holds in the majority AND held-out never regresses. See
   `evals.ratchet.confirmation_verdict`.
2. **Fidelity config.** Use the strongest skill-runner + max thinking effort for
   any run whose keeps you intend to trust. The opus + max-effort RC run produced
   keeps that survived a fresh re-check; haiku + default effort did not.

**Canonical fidelity command:**

```bash
python3 -m evals.auto_loop \
  --proposer claude-sonnet-4-5 --skill-runner opus --judge opus --effort max \
  --rotate-bottom-n 3 --max-iterations 20 --confirm-reruns 2 \
  --max-usd 200 --max-hours 10
```

**Reproducibility caveats.** Keep-set reproducibility depends on more than eval
noise: the edit-proposer is stochastic, and rotation picks the bottom-N by a
noisy baseline, so two runs can target different fixtures and discover different
(but equally valid) keeps. v0.5.1 documents this rather than forcing determinism
(no fixed proposer seed). Measure reproducibility with `evals.reproducibility`,
which reports a deterministic by-fixture floor and an advisory judge headline.
