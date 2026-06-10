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

The proposal *picked prompt-hook over command-hook* because the check needs reasoning about `git push` invocation shape (origin name, branch, force flag combinations) that a regex would miss. Stays focused: one event, one matcher, prompt under 5 sentences. Sentinel name present.

**Note:** in many cases a simpler `permissions.ask` rule (see Example 5) does the same job without any LLM evaluation. Prefer `permissions.ask` when "just ask the user every time" suffices; reach for prompt-hooks only when there's a meaningful classification the model can do that a glob can't (e.g. "block force-pushes to main but allow regular pushes to feature branches").

---

## Example 4 — Command hook on PostToolUse (surface context after action)

### Observed problem

> The user just changed an exported identifier's value (`export const X = 'old'` → `export const X = 'new'`) and several hardcoded callers across the codebase broke silently because the rename wasn't grepped first. A guardrail should surface all callers of an exported identifier whenever that identifier's definition line is edited.

### Proposal

**Form:** Command hook (`"type": "command"`)
**Event:** `PostToolUse` (non-blocking — runs AFTER the edit, feeds context back via stderr)
**Matcher:** `Edit|MultiEdit`
**Script:** `.claude/hooks/grep-export-callers.py`

```python
#!/usr/bin/env python3
"""After Edit/MultiEdit on a line that defines an exported identifier, grep
for callers and feed the list back to Claude so it can verify consistency."""
import json, re, subprocess, sys

EXPORT_DEF = re.compile(
    r"export\s+(?:const|let|var|function|class|type|interface|enum)\s+(\w+)"
)

def main():
    try:
        ev = json.load(sys.stdin)
    except Exception:
        return 0
    if ev.get("tool_name") not in ("Edit", "MultiEdit"):
        return 0
    inp = ev.get("tool_input") or {}
    edits = inp.get("edits") or [
        {"old_string": inp.get("old_string", ""), "new_string": inp.get("new_string", "")}
    ]

    names: set[str] = set()
    for e in edits:
        for s in (e.get("old_string", ""), e.get("new_string", "")):
            m = EXPORT_DEF.search(s)
            if m:
                names.add(m.group(1))

    if not names:
        return 0

    for name in names:
        try:
            r = subprocess.run(
                ["grep", "-rn", "--include=*.ts", "--include=*.tsx",
                 "--include=*.js", "--include=*.jsx", name, "."],
                capture_output=True, text=True, timeout=5,
            )
            hits = [l for l in r.stdout.splitlines() if l][:20]
            if hits:
                print(f"BLOCKING: export `{name}` was edited. {len(hits)} stale references remain:", file=sys.stderr)
                for h in hits:
                    print(f"  {h}", file=sys.stderr)
                print("Fix each, then summarize. Do not stop. Do not ask.", file=sys.stderr)
                return 2
        except Exception:
            pass
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

**Settings.json delta:**

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|MultiEdit",
        "hooks": [
          {
            "name": "self-improving-claude/grep-export-callers",
            "type": "command",
            "command": "python3 ${CLAUDE_PROJECT_DIR}/.claude/hooks/grep-export-callers.py",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

**Rationale:** *Surfaces all callers after any Edit that touches an exported identifier definition; closes the failure mode where a rename lands without enumerating hardcoded usages. PostToolUse + grep is cheaper than a prompt hook and works on every Edit (not just renames the model recognizes ahead of time).*

### Why it's good

The proposal *picked PostToolUse command-hook over CLAUDE.md note* because the rule is "after editing X, show Y" — a context-surfacing rule that the orchestrator must enforce, not a taste-level preference. The script uses defensive `.get(...)`, exits 2 with stderr so Claude sees the grep results as feedback, stays under 60 LOC, carries the sentinel `name`, and runs only when an export-definition line is detected (no noise on unrelated edits).

**Note on the imperative stderr.** The stderr text uses the action-forcing pattern from rubric criterion 12: `BLOCKING:` prefix, explicit count of stale references, then short bare imperatives — `Fix each. Do not stop. Do not ask.` Brevity beats argumentation here: a passive phrasing ("Verify these are consistent" / "Audit these usages") would let the model summarize-and-stop, and a long justification ("installing this hook authorizes the scope") invites the model to disagree with the justification. Reading only the stderr, you should feel obligated to act, not informed; that's the bar.

**Loop check (criterion 14).** This hook's stderr demands edits, and its matcher is `Edit|MultiEdit` — so the corrective edits WILL re-enter the hook. It terminates via *corrective-path exemption*, not convergence: the `EXPORT_DEF` gate exempts the fix-edits — call-site edits contain no `export` definition line, so `names` stays empty and each follow-up envelope early-returns 0 before the grep runs. (The grep itself never converges — it matches the identifier name, so the definition line and legitimate imports keep the hit count nonzero forever; that's fine because the gate, not the grep, is the guard.) One bounded re-entry remains: the hit list includes the definition line itself, so a model that "fixes" that hit re-edits an export line and re-fires the hook — bounded, because each re-fire needs a fresh export-definition edit while the demanded fixes are call-site edits. A variant that grepped unconditionally on every edit would re-emit the same stderr forever — and its "Do not stop" imperative would forbid the model from breaking out. That variant is an infinite loop and unshippable per criterion 14.

**Limitation.** Even with imperative voice, PostToolUse exit-2 cannot literally block turn-end — only Stop hooks can. The model *usually* acts on a strong imperative, but a model in heavy scope-discipline mode may still defer. The structural fix (composed PostToolUse + Stop with re-verify) is slated for v0.4.

---

## Example 5 — `permissions.ask` (when the user should decide each time)

### Observed problem

> The user noted that Claude sometimes wants to `git push` from inside the agent. Pushes to feature branches are usually fine, but pushes to `main` (especially `--force`) should always require explicit human confirmation. A blanket deny is too strict; a CLAUDE.md note is too lax; a prompt-hook would work but pays an LLM-call cost when a simpler form does the job.

### Proposal

**Form:** `permissions.ask` rule
**Event:** N/A (permissions apply uniformly across tools)
**Settings.json delta:**

```json
{
  "permissions": {
    "ask": [
      "Bash(git push:*)"
    ]
  }
}
```

**Rationale:** *Causes Claude Code to prompt the user for confirmation on every `git push` invocation regardless of arguments; no model call, no script, no hook latency — built-in Claude Code asks the user directly. Cheaper than a prompt-hook because the user's call is all the reasoning needed.*

### Why it's good

The proposal *ruled out the lighter form* (`permissions.deny` would block legitimate pushes), *ruled out the heavier form* (prompt-hook would do the same job but with an LLM evaluation per push). `permissions.ask` is the right semantic: "I want to be the one to decide." Built-in Claude Code handles the prompt; we don't author any code. One line, deterministic, exactly the right weight.
