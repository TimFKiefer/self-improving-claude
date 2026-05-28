# Hook Patterns (runtime reference)

The patterns you need at draft time. For the full rationale, see the project's `docs/knowledge/hooks-and-sdk.md`.

## Hook events at a glance

| Event | Fires when | Can block? | Supports `type: prompt`? |
|---|---|---|---|
| PreToolUse | Before a tool runs | Yes (exit 2 / `permissionDecision: deny`) | Yes |
| PostToolUse | After a tool ran | No*, but stderr is fed back to Claude | No |
| UserPromptSubmit | User submits a prompt | Yes (block before model sees it) | Yes |
| Stop | Main agent considers stopping | Yes (force continue) | Yes |
| SubagentStop | Subagent considers stopping | Yes | Yes |
| SessionStart | New session begins | No | No |
| SessionEnd | Session ends | No | No |
| PreCompact | Before context compaction | No | No |
| Notification | A notification is sent | No | No |

\* **PostToolUse limitation.** Exit-2 stderr feeds the model *information*, not an imperative — the model can summarize and stop instead of acting on the feedback. For rules of shape "after X, ensure Y" where Y requires multi-step follow-up:
- Strong imperative phrasing (rubric criterion 12: `REQUIRED FOLLOW-UP`, `Do not stop`, `Fix each`) helps but doesn't guarantee compliance.
- For genuine enforcement, prefer a `permissions.deny` / `permissions.ask` rule when a glob fits, OR wait for v0.4's composed PostToolUse + Stop pattern (paired hooks sharing a state file; the Stop hook re-verifies findings and blocks turn-end if they persist).

## Where to write hook entries

`.claude/settings.json` (committed, team-shared) — default.
`.claude/settings.local.json` (not committed, personal) — when the rule is one developer's preference.
Never `~/.claude/settings.json` without an explicit user-confirmed reason — that's a different scope.

## The two hook types

**Prompt-based** (`"type": "prompt"`) — the LLM evaluates each invocation. Best for reasoning-heavy checks. Available only on PreToolUse, Stop, SubagentStop, UserPromptSubmit. Costs a model call per fire.

```json
{
  "type": "prompt",
  "prompt": "Evaluate if this Bash command is safe. Deny if it would push to main, force-push anywhere, or rm -rf outside the project. Otherwise allow.",
  "timeout": 30
}
```

**Command** (`"type": "command"`) — a shell command (typically Python or bash) runs. Best for fast deterministic checks. Available on every event. No model call.

```json
{
  "type": "command",
  "command": "python3 ${CLAUDE_PROJECT_DIR}/.claude/hooks/block-rm-outside-cwd.py",
  "timeout": 10
}
```

## When to prefer which (priority order)

1. `permissions.deny` rule — for uniform path/glob-based blocks across all tools (cheapest, fastest).
2. Prompt hook — when the check needs context and the event supports it.
3. Command hook — when the check is fast and deterministic, or the event doesn't support prompt hooks (most `PostToolUse` formatters/linters fall here).
4. `CLAUDE.md` note — when the rule is taste-level, not safety-level (offer as a `#`-line for the user to paste; don't write `CLAUDE.md` directly).

## Settings-file structure (where to merge)

```json
{
  "permissions": { "deny": ["Read(**/.env)"] },
  "hooks": {
    "PreToolUse":  [ { "matcher": "Bash", "hooks": [ /* ... */ ] } ],
    "PostToolUse": [ { "matcher": "Write|Edit", "hooks": [ /* ... */ ] } ]
  }
}
```

Hook entries within an event array each carry a `matcher` (tool name, `|`-separated alternation, or `*`) and a `hooks: []` list of executors.

## Hook event stdin (PreToolUse / PostToolUse common shape)

```json
{
  "session_id": "uuid",
  "cwd": "/abs/path",
  "permission_mode": "ask|allow",
  "hook_event_name": "PreToolUse" | "PostToolUse",
  "tool_name": "Bash",
  "tool_input": { /* tool-specific, see tools-reference.md */ },
  "tool_response": { /* PostToolUse only */ }
}
```

## Exit codes (command hooks)

- `0` — let the tool proceed; stdout shown in transcript.
- `2` — block (PreToolUse) or feed-stderr-back-to-Claude (PostToolUse). Whatever you wrote to stderr becomes Claude's explanation.
- Anything else — non-blocking error.

## Portable paths

- `${CLAUDE_PLUGIN_ROOT}` — the plugin's install directory. Use this for scripts shipped *by* the plugin (e.g. our telemetry hook).
- `${CLAUDE_PROJECT_DIR}` — the user's project root. Use this for scripts you write *into* a project (e.g. generated `.claude/hooks/*.py`).

## Generated hook conventions (what we write)

Every command-hook script we generate begins with the stdin-reading boilerplate from `tools-reference.md`. Generated scripts target one event, ≤ 60 LOC, carry the `"name": "self-improving-claude/<slug>"` sentinel in their settings.json entry.

## Restart caveat

Hooks load at session start. A hook we install during `/improve-init` only fires after the user restarts Claude Code. Always tell the user this in the close-out message.
