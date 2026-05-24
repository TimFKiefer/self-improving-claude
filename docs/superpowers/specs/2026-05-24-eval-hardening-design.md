# Eval Hardening — Design Spec (target release v0.3.3)

- **Date:** 2026-05-24
- **Status:** Proposed (awaiting user review before writing-plans)
- **Scope:** the `evals/` measurement layer, dataset fixtures (002/003/004), a committed CLI backend, and a refreshed full-matrix baseline.
- **Execution model:** subagent-driven. Four parallel implementation workstreams (WS1–WS4) build to the contracts defined in §4; a final sequential integration pass (WS5) runs tests + the baseline rerun.

---

## 1. Why this work exists

The eval is the instrument we use to decide whether a SKILL/prompt change helps or hurts hook quality (`docs/knowledge/eval-methodology.md` §1: *"don't change the SKILL because it feels better. Run the eval, compare scores, decide."*). A miscalibrated instrument makes every downstream decision suspect.

**Founding context (why reliability is non-negotiable):** the project implements the Karpathy "auto-research" loop documented in `docs/knowledge/Analyse & Dokumentation_ Self-Improving Claude Code Skills.pdf` — change → run eval → if score improves, `git commit`; if it drops, `git reset`; loop autonomously. The eval score therefore *gates automated commit/reset decisions*, so a miscalibrated score doesn't merely mislead a human — it makes the loop **commit regressions and discard improvements**. That doc's central rule is that automation requires **binary/deterministic assertions, not subjective criteria** ("subjective criteria break automation"). This maps onto our two graders: the **deterministic code grade is the autonomy-critical, loop-gating metric**; the **model grade is advisory / for human side-by-side review only**. This framing is *why* the four findings below are bugs and not nitpicks.

A verification pass against the v0.3.2 codebase + the four committed baselines found the instrument is miscalibrated in four independent ways.

### Verified findings this spec addresses

1. **Contradictory fixtures (002/003).** The gold `expected_hook_traits` fail their own `planted_problem`. Opus's exact-gold string for 002 (`Read(**/.env)`) scores **code 10 / model 3** on the *same* proposal (`evals/results/2026-05-23-v0.3-opus.json:96,123`). The `**/.env` glob does not match `.env.local` — confirmed by `settings-and-permissions.md:50`, which lists `Read(**/.env)` **and** `Read(**/.env.*)` as separate rules. 003 has the same shape (generated-dir **and** `prisma/dev.db`; gold covers one).
2. **Code grade is shape-only.** Non-applicable checks return a free `10` (`evals/grade_code.py:34,45,50,79,100`), so a wrong-form or no-op proposal still scores ~7 (gemma 004's detection is fully commented out yet scores 7.1; Opus 004 has wrong form *and* event yet scores 7.1). v0.3.2's new `imperative_stderr` is another free-pass-on-N/A and uses literal-token matching that scores **0** for genuinely imperative stderr ("Fix the reported issues before continuing." fails because it isn't the token `FIX EACH`), dragging Opus's 9/10 ruff hook down.
3. **Model-grade truncation.** `grade_model.py` uses `max_tokens=1024` with no prefill/stop. Verbose graders run out of tokens before the `score` field and the parse failure is logged as **score 0**, conflated with genuine "wrong" 0s. gemma's 2.9 average is mostly this artifact (`evals/results/2026-05-23-v0.3-gemma.json:41` — glowing review, truncated, scored 0). The fix is exactly the technique `eval-methodology.md:109` already prescribes (prefill ` ```json `, stop on ` ``` `).
4. **Unreproducible + mixed graders.** The Haiku/Sonnet/Opus baselines came from an uncommitted `/tmp/eval_via_cli.py` (`evals/results/README.md:110`). `grade_model.py:14` hardcodes a Haiku grader, contradicting the README's "Opus-grades-Opus" claim. The cross-column AVERAGE therefore mixes graders and isn't reproducible from the repo.

Plus the consequence surfaced live: re-grading the stored proposals with v0.3.2's 8-check grader changes **nearly every cell** of the README table — there is currently no valid v0.3.2 baseline.

---

## 2. Goals

- **G1.** The model-grade column is trustworthy: truncation is prevented, and a parse/truncation failure is recorded as *no data*, never as a quality score of 0.
- **G2.** The code grade reflects the quality of the *applicable* dimensions, not proposal shape: non-applicable checks are excluded from the mean, and `imperative_stderr` scores imperative *intent* rather than a fixed token whitelist.
- **G3.** Fixtures 002/003/004 are internally consistent — the gold answer actually solves its own planted problem, and 004 accepts the genuinely-valid alternative forms.
- **G4.** Every baseline is reproducible from the repo via a committed backend, all graded by one fixed model for comparability, and the full matrix is refreshed under the new semantics (v0.3.3 baseline).

## 3. Non-goals

- **Integration tests** that install a generated hook and fire it in a live session. `eval-methodology.md` §5 is explicit that the eval cannot prove a hook works in production; that is separate (future) work.
- The **v0.4 structural enforcement primitive** (composed PostToolUse + Stop with shared state). Explicitly deferred by the v0.3.2 CHANGELOG.
- Further **SKILL/rubric prompt changes.** v0.3.2 already did that pass; this spec only touches the measurement layer + fixtures.
- **Back-comparability** with pre-v0.3.3 numbers. The scoring semantics change (G2), so v0.3.3 establishes a *new* baseline; the README must say pre-v0.3.3 numbers are not directly comparable rather than imply a trend line.

---

## 4. Contracts (the interfaces parallel agents build to)

These schemas are the coordination mechanism. Each workstream owns a disjoint file set and depends only on these contracts, not on another agent's in-progress code.

### 4.1 `expected_hook_traits` schema (consumed by grade_code; authored in dataset.json)

```jsonc
{
  // form/event accept a string OR a list-of-strings (set membership) — enables fork 4 (004).
  "form":  "command-hook" | ["prompt-hook", "command-hook"],
  "event": "PostToolUse"  | ["PreToolUse", "PostToolUse"],   // omit => N/A

  "matcher": "Bash",                       // exact, OR:
  "matcher_must_include": ["Edit", "Write"],

  "rule_pattern": "Read(**/.env*)",        // exact single-rule match, OR:
  "rule_pattern_must_contain": "Bash(git push",

  // NEW (fork 3): coverage fixtures — the union of permission-form proposals must
  // include ALL of these substrings. Graded across proposals in run.py (§4.4), not per-proposal.
  "required_rules": ["src/generated/prisma", "prisma/dev.db"],

  "rationale_must_mention": ["ruff", "format"]
}
```

### 4.2 `grade_code` result schema (WS1)

```jsonc
{
  "checks": { "form_matches": 10 | 0 | null, ... },  // null === not applicable
  "mean": <average over non-null checks only>,        // applicable-denominator (fork 1)
  "rules_present": ["src/generated/prisma"]           // present only for permission forms; used by §4.4
}
```
- A check returns `null` (not `10`) when it does not apply. `mean` divides by the count of non-null checks. A proposal with zero applicable checks scores `0` with a `degenerate: true` flag.

### 4.3 `grade_model` result schema (WS2)

```jsonc
{
  "valid": true,                 // false on parse failure / truncation
  "score": 7 | null,             // null when valid=false — NEVER 0 for a failure
  "error": null | "truncated",   // reason when valid=false
  "strengths": [...], "weaknesses": [...], "reasoning": "..."
}
```
- Prevention: `max_tokens` raised to ≥ 2048 and the grader call prefills the assistant turn with ` ```json ` and stops on ` ``` ` per `eval-methodology.md:109`. Detection: a response that still fails to parse sets `valid=false, score=null, error="truncated"`.

### 4.4 `run.py` output schema + aggregation (WS3)

```jsonc
"summary": {
  "entries": [{
    "id": "...",
    "code_max": 10.0, "code_mean": 8.3,           // max kept as headline; mean added (fork 5)
    "model_max": 9, "model_mean": 7.5,
    "clean_rate": 0.67,                            // fraction of proposals with code mean >= CLEAN_THRESHOLD (default 7.0, tunable constant in run.py)
    "n_proposals": 3, "n_model_valid": 2,          // invalid model grades excluded from model_* (G1)
    "coverage": 1.0                                 // present iff fixture has required_rules: fraction covered by union of proposals
  }],
  "average_code": <mean of code_max over fixtures>,
  "average_model": <mean of model_max over fixtures with >=1 valid grade>,
  "average_clean_rate": <mean of clean_rate>
}
```
- **Aggregation (fork 5):** keep `max` as the headline (matches the orchestrator's "surface the best candidate" intent) but also report `mean` and `clean_rate` so a run that emits one good + two bad proposals is no longer invisible.
- **Coverage (fork 3):** for a fixture carrying `required_rules`, `coverage` = fraction of required substrings present across the *union* of that fixture's permission-form proposals. This is the honest grading unit for genuinely multi-path protection (003), where one deny rule cannot cover two unrelated paths.
- **Invalid-grade exclusion (G1):** `average_model` and `model_*` are computed only over grades with `valid=true`.

### 4.5 `client_claude_cli.py` backend (WS3)

- Mimics `anthropic.Anthropic`: exposes `.messages.create(model, max_tokens, system, messages, ...)`.
- Shells `claude --print --model <model> [--append-system-prompt <system>]`, feeds the prompt on stdin/arg, returns the Anthropic content-block shape (`SimpleNamespace(content=[SimpleNamespace(type="text", text=...)])`).
- **Respects the `model` kwarg** (unlike `client_ollama.py`, which ignores it). This is what lets the grader be pinned while the proposer varies.
- `run.py` gains a configurable **proposer** model (CLI arg / env), replacing the hardcoded `ORCHESTRATOR_MODEL`. The **grader** stays `grade_model.GRADER_MODEL` (Haiku) for *every* run → comparable columns + reproducible from the repo (fork 6). The README's "same-family grading" claim is corrected.

---

## 5. Design decisions (the six approved forks + knowledge grounding)

| # | Decision | Grounding / rationale |
|---|---|---|
| 1 | **Applicable-checks denominator** — N/A checks are `null`, excluded from the mean. | `eval-methodology.md` §3 says "mean across checks"; scoring a check that *doesn't apply* as a pass measures shape, not quality (finding 2). |
| 2 | **Loosen `imperative_stderr`, keep it a BINARY pattern match.** Stay deterministic (pattern-based True/False) per the founding doc's binary-assertion rule — do **not** introduce fuzzy/NLP/LLM "intent scoring." The fix is to improve the *patterns*: broaden the required-phrase allowlist to accept any explicit directive (e.g. a leading imperative verb such as "Fix…/Run…/Update…", not just the literal tokens `FIX EACH`/`BLOCKING`), and correct the banned-list so words used in a genuine directive (e.g. "verify"/"review") don't false-trigger. Keep the blocking/non-blocking split. | `hooks-and-sdk.md` §2/§4 (only PreToolUse blocks) + §10.9 ("generated messages should be specific and actionable") + §4 ("PostToolUse… can still write to stderr to feed information back"). For non-blocking events the stderr IS the enforcement, so requiring imperative phrasing is right. The founding-doc thesis (binary assertions) means we sharpen the pattern, not replace it with a fuzzy judgment. **Note:** `_BLOCKING_EVENTS` includes Stop/SubagentStop/UserPromptSubmit; the knowledge doc (§4) only documents PreToolUse blocking, but real exit-2 semantics do extend to those events — keep the broader set and add a code comment citing the discrepancy. |
| 3 | **002/003 golds made consistent.** 002 → single better glob `Read(**/.env*)` (covers `.env` + `.env.local` + `.env.production`). 003 → `required_rules` coverage across proposals. **Precondition:** WS4 must first verify against authoritative Claude Code permission semantics whether a `Read(...)` deny rule also blocks Grep/Glob/`Bash cat`, because the knowledge base is self-contradictory (`settings-and-permissions.md` §3 names one tool per rule vs `hooks-and-sdk.md:200` "applies uniformly across tools"). Then write BOTH the gold and the `planted_problem` to match verified reality so they cannot contradict. | Findings 1; `settings-and-permissions.md:50`. |
| 4 | **004 accepts multiple valid forms** (`prompt-hook` OR PostToolUse `command-hook`). | Every frontier model + the model-grader prefer the command-hook (Opus AST detector, model 7, "would have caught the exact walk_tree regression"); `evals/results/README.md:162` already flags 004 for redesign. |
| 5 | **Keep `max` headline; add `mean` + `clean_rate`.** Do **not** blend code+model into one `final_score`. | Deliberate divergence from `eval-methodology.md:116`: code (shape-correctness) and model (problem-solving) are orthogonal; blending hides the 002 contradiction (10 & 3 → a bland 6.5). |
| 6 | **Pin grader to one model (Haiku) for all runs; correct README.** Keep `expected_traits` OUT of the grader prompt. | `eval-methodology.md` implication 5 ("use Haiku-class models for graders"). Omitting `expected_traits` (a divergence from §3) is deliberate: it keeps the grader an *independent* check that can catch future gold defects — exactly how it caught 002/003 here. |

---

## 6. Workstream breakdown (subagent decomposition)

Disjoint file ownership → WS1–WS4 run in parallel with no merge collisions. WS5 is sequential and gated on WS1–WS4 merging.

### WS1 — Code grader
- **Owns:** `evals/grade_code.py`, `evals/tests/test_grade_code.py`
- **Build:** applicable-denominator (`null` for N/A, mean over non-null); loosened `imperative_stderr` (intent detection, fixed false-positives, blocking comment cite); `form`/`event` set-membership; `rule_pattern` for the new single-glob golds; emit `rules_present` for permission forms.
- **Done when:** new + existing unit tests pass; a wrong-form proposal scores strictly below a right-form one; Opus's fixture-005 stderr ("Fix the reported issues before continuing.") passes `imperative_stderr`; a no-op script does not score ≥ a working one on applicable checks.

### WS2 — Model grader
- **Owns:** `evals/grade_model.py`, `evals/tests/test_grade_model.py`
- **Build:** `max_tokens` ≥ 2048; prefill ` ```json ` + stop ` ``` `; result carries `valid`/`error`; failures → `score=null` not 0.
- **Done when:** a simulated truncated response yields `valid=false, score=null` (not 0); a clean response parses to a 1–10 score; tests cover both.

### WS3 — Runner + CLI backend
- **Owns:** `evals/run.py`, new `evals/client_claude_cli.py`, `evals/tests/test_run.py` (+ a new `test_client_claude_cli.py`)
- **Build:** `client_claude_cli.py` per §4.5 (respects `model`); configurable proposer model; grader pinned to Haiku; aggregation per §4.4 (max + mean + clean_rate + coverage); exclude `valid=false` grades from model averages.
- **Done when:** `EVAL_BACKEND=claude_cli` runs end-to-end (mockable in tests); aggregation excludes invalid grades; coverage computed for a fixture with `required_rules`; backend selection documented.

### WS4 — Fixtures
- **Owns:** `evals/dataset.json` (entries 002, 003, 004 only), and any fixture `description.md` text that must stay consistent with the planted_problem.
- **Build:** (1) verify the Read-vs-Grep/Glob semantics question; (2) 002 → `Read(**/.env*)` gold + planted_problem reconciled; (3) 003 → `required_rules` + planted_problem reconciled; (4) 004 → multi-form `form`/`event`.
- **Done when:** for each touched fixture, the documented gold *does* satisfy its own planted_problem; the schema additions match §4.1.
- **Dependency note:** WS4 authors data against the §4.1 contract, so it does not need WS1's code — but WS5 integration confirms WS1 actually reads the new fields.

### WS5 — Integration + baseline rerun (sequential, human-gated)
- **Owns:** `evals/results/*.json`, `evals/results/README.md`, top-level `README.md` (results table), `CHANGELOG.md`, `plugin/.claude-plugin/plugin.json` (version bump).
- **Build:** run the full `pytest` suite; then rerun the **full matrix** (gemma via Ollama; Haiku/Sonnet/Opus via the committed CLI backend) — **pause for explicit user go-ahead before spending Opus quota**; commit fresh v0.3.3 baselines; rewrite the README table + add the "not comparable to pre-v0.3.3" note; CHANGELOG v0.3.3; bump plugin version.
- **Done when:** every test passes; the README table matches what the current grader produces; baselines reproducible via a single documented command.

### Dependency graph

```
WS1 ─┐
WS2 ─┤  (parallel, Phase 1)
WS3 ─┤
WS4 ─┘
       └─► WS5 (Phase 2: tests → [user gate] → full-matrix rerun → docs/version)
```

---

## 7. Risks & mitigations

- **Coverage grading adds cross-proposal logic in run.py.** Mitigation: it is opt-in per fixture (`required_rules`); fixtures without it use the existing per-proposal path unchanged.
- **`claude --print` CLI flags drift.** Mitigation: isolate the exact invocation in `client_claude_cli.py`, cover it with a mocked test, and document the CLI version assumption.
- **Read-vs-Grep/Glob verification is inconclusive.** Mitigation: if authoritative behavior can't be confirmed, write the planted_problem to the *conservative* reading (require explicit per-tool coverage) so the gold is correct under either interpretation.
- **Opus rerun quota.** Mitigation: WS5 hard-stops for user confirmation before the premium run; gemma+Haiku can land first.

## 8. Out-of-repo / one-time actions requiring user involvement

- The full-matrix rerun consumes subscription quota (the user chose full matrix). WS5 will pause before the Opus leg.
