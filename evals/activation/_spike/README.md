# Task 0 — Activation firing-detection feasibility (FINDINGS)

**Date:** 2026-06-02 · **Result: GO** — the core mechanism works.

## The four checks

1. **Spontaneous invocation — PASS.** The `fire` scenario (a force-push footgun the user
   wants prevented) caused `claude --print` to invoke the skill *on its own*, with no
   `/improve` typed. returncode 0.
2. **Detectability + shape — PASS (with a key finding).** The `Skill` tool's `tool_input`
   names the skill **plugin-namespaced**:
   ```json
   {"tool_input": {"skill": "self-improving-claude:improve"}}
   ```
   (an `args` field may also be present). The field is `skill`. Detection must match the
   namespaced form, e.g. suffix `:improve` / `:improve-init`.
3. **Short-circuit — PASS.** The `PreToolUse` / matcher-`Skill` hook (exit 2) blocked the
   invocation; the orchestrator never ran — the model received the block message and fell
   back to a conversational reply. `bypassPermissions` does **not** skip PreToolUse hooks.
4. **Isolation — logically sound; empirical confirmation deferred to Task 6.** The
   `description` frontmatter is invocation-metadata, not the execution prompt: when the
   rubric sandbox *types* `/improve`, the skill body runs regardless of the description text.
   Confirm cheaply during Task 6 by running one rubric fixture before/after a description
   edit (expect no score change).

## Build-affecting findings (fold into Task 3)

- **A. Plugin-namespaced names.** Match `self-improving-claude:<skill>` (or `endswith(":"+skill)`),
  not bare `<skill>`.
- **B. Runs can invoke multiple/other skills.** The `no-fire` Fibonacci scenario invoked
  `superpowers:brainstorming` (NOT our skill). Therefore:
  - The **production hook APPENDS** every `Skill` invocation (one run may invoke several) —
    a JSONL marker, one line per call — instead of overwriting.
  - **"Did the target skill fire?"** = is `self-improving-claude:<target>` among the recorded
    invocations. Other skills firing is irrelevant to our metric — measurement is robust.

## Confirmed mechanism

- Sandbox: temp project with `.claude/settings.json` registering a `PreToolUse`/matcher-`Skill`
  command hook; plugin loaded via `--plugin-dir`; `--output-format json`; `bypassPermissions`;
  `--no-session-persistence`; `--max-budget-usd`.
- Hook records invoked skill(s) to `$SPIKE_MARKER` and exit-2 blocks (detection + short-circuit
  in one).
- Per-fixture firing-rate = fraction of N runs in which the target skill appears.

**Decision: proceed to Tasks 1–11** with findings A and B folded into Task 3.
