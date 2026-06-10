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

13. **Fires on its own trigger (command-hooks).** Before showing the user, trace the hook against two stdin envelopes you construct from the chosen event + matcher: a *triggering* one and a *clean* one. The triggering envelope must reach `return 2` (with stderr); the clean envelope must reach `return 0`. A hook that can't be traced to block its own trigger and pass clean input silently no-ops once installed — the usual cause is reading `ev["tool"]`/`ev["args"]` instead of `tool_name`/`tool_input`, ignoring stdin, or a guard condition that never matches.

14. **Loop-safe (terminates).** Trace the feedback path: hook output → the model's most likely responding tool call → does that call re-fire this hook with the same output? Per shape:
    - **PostToolUse** whose stderr demands tool calls its own matcher would catch: the check must be *convergent* — the script recomputes the violating condition on every fire and exits 0 once clean, or fails only on NEW violations relative to a recorded baseline (pre-existing debt must not keep the check permanently red), or exempts the corrective action (early `return 0`), or the matcher excludes it. Criterion 12's imperative stderr is only shippable on a convergent check: "Do not stop until done" on a check that can never come back clean is an infinite loop, not enforcement.
    - **PreToolUse** blocking stderr must name an alternative action (an off-ramp), and that alternative must not be blocked by this same hook or by an existing `permissions.deny` rule — otherwise the model retries variants of the blocked call forever. The alternative may be a non-tool-call action ("stop and ask the user") — that terminates by construction and needs no follow-up trace; do not invent a tool-call alternative just to have one.
    - **Hooks that spawn `claude` or the Agent SDK**: a child that loads the same project settings (the default for `claude -p` in the project directory) re-fires the hook — a fork bomb. Set a sentinel env var when spawning and exit 0 at the top of the script when it's present; restricting the child's tools is supplementary only — `allowedTools` leaves the tool in the child's tool list and PreToolUse hooks fire on attempts before the permission check (only bare-name `disallowedTools` removal, or a PostToolUse-only matcher, makes tool restriction sufficient).
    - **Stop / SubagentStop hooks** must exit 0 (allow stopping) when stdin `stop_hook_active` is `true`.

    A failed trace is revisable within the preamble's retry cap (add a guard, re-trace); a hook that still fails after the cap is a drop or a re-form at Step 4 — never ship it hoping the model breaks the loop on its own.

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
