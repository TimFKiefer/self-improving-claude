# Hook Proposal Rubric

Every proposal you draft must satisfy every item below before you show it to the user. If a draft fails, revise (up to 2 retries); if it still fails, drop the candidate and note one-line why.

## Mandatory criteria

1. **Grounded in observed behavior.** The proposal points to a specific event in `<recent_chat>` / `<telemetry_excerpt>` / `<project_snapshot>` — not a hypothetical. If you can't quote the evidence in one sentence, the candidate isn't strong enough.

2. **Lightest *viable* form.** The chosen form must actually enforce the rule. CLAUDE.md notes are NOT viable for rules of shape "before X do Y" or "after X show Y" — these need a hook (Pre/PostToolUse) or a `permissions` rule. A CLAUDE.md note that relies on the model remembering is not viable for any recurring failure mode. Use one of the lighter enforceable forms (`permissions.deny`, `permissions.ask`, prompt-hook, command-hook) unless the rule is purely a stylistic preference with no enforcement need. The rationale states *why* a lighter form wouldn't work, if you didn't use one.

3. **One event, one matcher.** The hook binds to exactly one event (`PreToolUse`, `PostToolUse`, etc.) with a precise `matcher` (exact tool, an alternation that's tighter than `*`, or — only when truly universal — `*`).

4. **Small.** Command-hook scripts are ≤ 60 lines. `permissions.deny` is a single rule string. Prompt-hook prompts are ≤ 5 sentences. If you can't fit, the candidate is doing too much — split it into two.

5. **Sentinel name.** Every settings.json entry you create carries `"name": "self-improving-claude/<descriptive-kebab-slug>"`. See `settings-merge.md` for slug rules.

6. **Portable paths.** Scripts use `${CLAUDE_PROJECT_DIR}` (project-side) or `${CLAUDE_PLUGIN_ROOT}` (plugin-side). No absolute paths. No `~`. No relative paths that depend on cwd.

7. **One-sentence rationale.** A single sentence that names the bug AND why this form (not a lighter one) was correct. Goes in front of the user as part of the approval prompt.

8. **Boilerplate at the head.** Command-hook scripts (Python preferred, then bash, then JS) start with the stdin → JSON → branch boilerplate from `tools-reference.md`. Even short scripts — matchers can widen later.

9. **Defensive lookups.** Scripts use `.get(...)`-style access for `tool_input` / `tool_response` fields. They tolerate missing keys silently and never crash on unexpected payload shapes.

10. **Validated syntax.** Before you show it: `bash -n` for shell, `python -m py_compile` for Python, `node --check` for JS, `json.loads` for permission rules / settings entries. A draft that doesn't parse never reaches the user.

11. **Enforcement-shape check.** For rules of shape "after X, the model must do Y" (where Y is multi-step or scope-expanding), recognize that PostToolUse exit-2 stderr is *informational*, not *imperative* — the model may summarize and stop instead of acting. If the rule genuinely requires action, prefer a form that can BLOCK (`permissions.deny` / `permissions.ask` when a glob fits). If you stay with PostToolUse alone, the rationale must name explicitly why surfacing alone is sufficient here (typically: "this is a one-shot nudge", not "the model must act now"). Composed PostToolUse+Stop hooks are the structural fix for genuine enforcement — slated for v0.4.

12. **Imperative stderr.** Hook scripts that surface context via stderr MUST use imperative voice. Required phrasing: "REQUIRED FOLLOW-UP", "Do not stop until", "Fix each, then summarize", "Update X, then proceed", "BLOCKING". Banned phrasing (treat as a rubric failure — revise before showing the user): "audit", "consider", "verify these are", "review", "or X is unrelated" (the escape hatch). The cost-of-asking must exceed the cost-of-acting — passive phrasing inverts that and licenses inaction.

   **Concrete bad/good pairs** (for PostToolUse hooks specifically — PreToolUse exit-2 blocks the tool, so its stderr is just explanation):

   ❌ Passive (would let the model summarize-and-stop):
   > "Verify these are consistent with your change."
   > "Audit hardcoded usages or verify the usage is unrelated."
   > "Found N references. Review them for correctness."

   ✅ Imperative (forces action):
   > "REQUIRED FOLLOW-UP: N stale references remain. Fix each, then summarize. Do not stop until done."
   > "BLOCKING: update each reference, then continue."
   > "Update each occurrence to the new value, then proceed. Do not ask."

   The pattern: lead with `REQUIRED FOLLOW-UP` or `BLOCKING`, name the action verb explicitly (`Fix`, `Update`, not `verify`/`audit`), close with `Do not stop` / `Do not ask`. Brevity beats argumentation — short imperatives override scope discipline more reliably than long justifications.

## Disqualifiers (drop the candidate immediately)

- The rule duplicates an existing entry (verified against `<existing_hooks>` / `<existing_permissions>`).
- The rule contradicts `CLAUDE.md`.
- The rule encodes a personal preference the user hasn't expressed.
- The rule depends on machine-specific state (a developer's home directory, a particular shell, a specific Node version).
- The rule needs network access to evaluate (we avoid hooks that call out to external services in v0.1).

## Anti-patterns (revise, don't drop)

- Vague rationale ("this is a good idea") → tighten to one specific bug.
- Matcher too broad (`"*"` when `"Bash"` would do) → narrow it.
- Logic in the matcher that belongs in the script (regex with bash-specific shape) → simplify.
- `print()` debug noise in the script → remove.
- Hard-coded paths that should be env-vars → fix.
