# Worked Examples

Three exemplars of approved proposals. They demonstrate the lightest-viable-form principle, the rationale style, and the boilerplate.

After each one, the **Why it's good** line names the property the model should imitate.

---

## Example 1 — `permissions.deny` (when a glob suffices)

### Observed problem

> The user said "stop reading my `.env` files," and the chat shows three recent `Read` calls against `.env`, `.env.local`, `.env.production`.

### Proposal

**Form:** `permissions.deny` rule
**Event:** N/A (permissions apply uniformly across tools)
**Settings.json delta:**

```json
{
  "permissions": {
    "deny": [
      "Read(**/.env)",
      "Read(**/.env.*)"
    ]
  }
}
```

**Rationale:** *Blocks reads of `.env` and `.env.*` across all tools (Read, Grep, Glob, etc.) with a single rule — cheaper than per-tool hooks and uniformly enforced.*

### Why it's good

The proposal *ruled out the lighter form first* (there is none — `permissions.deny` is already lightest), picked the most surgical pattern (two specific globs, not `**/*.env*` which over-matches), and the rationale explicitly says why this beats a `PreToolUse` hook.

---

## Example 2 — Command hook (when the check is deterministic)

### Observed problem

> Telemetry shows `pnpm test` invocations exit non-zero 5 times this week, and the project's `package.json` defines `test:ci` (non-interactive) as the correct script. The bare `pnpm test` opens an interactive watcher.

### Proposal

**Form:** Command hook (`"type": "command"`)
**Event:** `PreToolUse`
**Matcher:** `Bash`
**Script:** `.claude/hooks/block-pnpm-test-watcher.py`

```python
#!/usr/bin/env python3
"""Block `pnpm test` (interactive watcher); steer Claude to `pnpm test:ci`."""
import json, sys

def main():
    try:
        ev = json.load(sys.stdin)
    except Exception:
        return 0
    if ev.get("tool_name") != "Bash":
        return 0
    cmd = (ev.get("tool_input") or {}).get("command", "")
    if cmd.strip().startswith("pnpm test") and "test:ci" not in cmd:
        print("Use `pnpm test:ci` instead — `pnpm test` opens an interactive watcher and won't return.", file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

**Settings.json delta:**

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "name": "self-improving-claude/block-pnpm-test-watcher",
            "type": "command",
            "command": "python3 ${CLAUDE_PROJECT_DIR}/.claude/hooks/block-pnpm-test-watcher.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

**Rationale:** *Blocks the recurring `pnpm test` watcher trap by inspecting the Bash command before it runs and pointing Claude at `pnpm test:ci`; a `permissions.deny` rule would also block the correct `pnpm test:ci` because it has the same prefix.*

### Why it's good

The proposal *had to use a hook* because `permissions.deny` can't distinguish `pnpm test` from `pnpm test:ci` (same prefix). The script branches on `tool_name`, uses defensive `.get(...)`, exits 2 with a useful stderr message, stays well under 60 LOC, carries the sentinel `name`, uses `${CLAUDE_PROJECT_DIR}`.

---

## Example 3 — Prompt hook (when reasoning is needed)

### Observed problem

> The user noted "Claude keeps trying to git-push from inside the agent — I want a human in the loop." The check needs context (which branch, force or not, into which remote) that's hard to express deterministically.

### Proposal

**Form:** Prompt hook (`"type": "prompt"`)
**Event:** `PreToolUse`
**Matcher:** `Bash`
**Settings.json delta:**

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "name": "self-improving-claude/gate-git-push",
            "type": "prompt",
            "prompt": "Evaluate this Bash command. If it is a `git push` (or `git push --force`, `git push -f`), respond with `deny` and explain that pushes require human confirmation. If it is not a git push, respond with `allow`.",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

**Rationale:** *Gates all `git push` invocations behind LLM evaluation that can read intent (e.g. recognize `git push origin feature-x` vs `git push --force origin main`) without trying to anticipate every shape with regex; a deterministic script could miss novel invocation forms.*

### Why it's good

The proposal *picked prompt-hook over command-hook* because the check genuinely needs reasoning about `git push` invocation shape (origin name, branch, force flag combinations). Stays focused: one event, one matcher, prompt under 5 sentences. Sentinel name present. The rationale names the bug and explicitly says why a regex would be brittle.
