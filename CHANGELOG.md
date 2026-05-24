# Changelog

All notable changes to `self-improving-claude` are documented here.

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
