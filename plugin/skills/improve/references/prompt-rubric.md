# Hook Proposal Rubric

Every proposal you draft must satisfy every item below before you show it to the user. If a draft fails, revise (up to 2 retries); if it still fails, drop the candidate and note one-line why.

## Mandatory criteria

1. **Grounded in observed behavior.** The proposal points to a specific event in `<recent_chat>` / `<telemetry_excerpt>` / `<project_snapshot>` — not a hypothetical. If you can't quote the evidence in one sentence, the candidate isn't strong enough.

2. **Lightest viable form.** You chose the form (permissions.deny → prompt-hook → command-hook → CLAUDE.md note) by ruling out lighter options. The rationale states *why* a lighter form wouldn't work, if you didn't use one.

3. **One event, one matcher.** The hook binds to exactly one event (`PreToolUse`, `PostToolUse`, etc.) with a precise `matcher` (exact tool, an alternation that's tighter than `*`, or — only when truly universal — `*`).

4. **Small.** Command-hook scripts are ≤ 60 lines. `permissions.deny` is a single rule string. Prompt-hook prompts are ≤ 5 sentences. If you can't fit, the candidate is doing too much — split it into two.

5. **Sentinel name.** Every settings.json entry you create carries `"name": "self-improving-claude/<descriptive-kebab-slug>"`. See `settings-merge.md` for slug rules.

6. **Portable paths.** Scripts use `${CLAUDE_PROJECT_DIR}` (project-side) or `${CLAUDE_PLUGIN_ROOT}` (plugin-side). No absolute paths. No `~`. No relative paths that depend on cwd.

7. **One-sentence rationale.** A single sentence that names the bug AND why this form (not a lighter one) was correct. Goes in front of the user as part of the approval prompt.

8. **Boilerplate at the head.** Command-hook scripts (Python preferred, then bash, then JS) start with the stdin → JSON → branch boilerplate from `tools-reference.md`. Even short scripts — matchers can widen later.

9. **Defensive lookups.** Scripts use `.get(...)`-style access for `tool_input` / `tool_response` fields. They tolerate missing keys silently and never crash on unexpected payload shapes.

10. **Validated syntax.** Before you show it: `bash -n` for shell, `python -m py_compile` for Python, `node --check` for JS, `json.loads` for permission rules / settings entries. A draft that doesn't parse never reaches the user.

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
