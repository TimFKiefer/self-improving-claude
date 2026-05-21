# Claude Code Tools — `tool_input` Reference

Source: compiled from the JSON examples already shown in the Anthropic *Claude Code* course material (Read, Grep, Bash, TodoWrite) plus the broadly-documented shapes of the other built-in tools. This is the lookup table our generated hooks will need to inspect `tool_input` correctly.

> **Why this matters:** every generated hook reads JSON from stdin and branches on `tool_name` to look up the right `tool_input` fields. If a hook checks `tool_input.file_path` but the tool was `Bash` (which uses `command`), the check silently does nothing. The bundled skill needs to know these shapes when drafting hooks.

---

## 1. The standard envelope

Every PreToolUse / PostToolUse stdin payload has the same outer fields. The inner `tool_input` (and `tool_response` for PostToolUse) vary per tool.

```json
{
  "session_id": "uuid",
  "transcript_path": "/path/to/transcript.jsonl",
  "hook_event_name": "PreToolUse" | "PostToolUse",
  "tool_name": "<see table below>",
  "tool_input": { ... },        // shape varies by tool
  "tool_response": { ... }      // PostToolUse only; shape varies by tool
}
```

So a generic boilerplate header for any generated hook looks like:

```js
let raw = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (d) => (raw += d));
process.stdin.on("end", () => {
  const ev = JSON.parse(raw);
  const tool = ev.tool_name;
  const input = ev.tool_input || {};
  // branch on `tool` and inspect `input`
});
```

Or in Python:

```py
import json, sys
ev = json.load(sys.stdin)
tool = ev["tool_name"]
input_ = ev.get("tool_input") or {}
```

---

## 2. Per-tool reference

The matcher column shows what to put in a hook config's `matcher` field. Matchers support `|` for alternation (e.g. `"Write|Edit"`).

### File-reading tools

| Tool | Matcher | `tool_input` shape | What to check for in hooks |
|---|---|---|---|
| **Read** | `Read` | `{ "file_path": "/abs/path" }` | Inspect `file_path` to block reads of sensitive files. Path is absolute. |
| **Glob** | `Glob` | `{ "pattern": "**/*.ts", "path": "/abs/dir" }` | `pattern` is the glob; `path` is the search root (a directory). |
| **Grep** | `Grep` | `{ "pattern": "regex", "path": "/abs/path", "glob": "*.ts", "output_mode": "...", ... }` | `path` is a search directory (or file). `pattern` is the regex. To block searches that would find a secret, inspect `pattern`. |

### File-writing tools

| Tool | Matcher | `tool_input` shape | What to check for in hooks |
|---|---|---|---|
| **Write** | `Write` | `{ "file_path": "/abs/path", "content": "..." }` | Inspect `file_path` for protected paths. Inspect `content` to block strings (e.g. accidental secrets, banned imports). |
| **Edit** | `Edit` | `{ "file_path": "/abs/path", "old_string": "...", "new_string": "...", "replace_all": false }` | Same path/content idea, applied to `new_string`. |
| **MultiEdit** *(if available)* | `MultiEdit` | `{ "file_path": "/abs/path", "edits": [ { "old_string": "...", "new_string": "..." }, ... ] }` | Same as Edit but `edits` is an array. |
| **NotebookEdit** | `NotebookEdit` | Notebook-specific cell edits. | Niche; skip for v1 unless project uses notebooks. |

### Execution tools

| Tool | Matcher | `tool_input` shape | What to check for in hooks |
|---|---|---|---|
| **Bash** | `Bash` | `{ "command": "...", "description": "...", "timeout": 120000, "run_in_background": false }` | `command` is the full shell line. Inspect for dangerous patterns (`rm -rf /`, `git push --force`, network calls to staging, etc.). Use exit 2 + stderr to explain what to run instead. |

### Search & retrieval tools

| Tool | Matcher | `tool_input` shape | What to check for in hooks |
|---|---|---|---|
| **WebFetch** | `WebFetch` | `{ "url": "https://...", "prompt": "..." }` | Inspect `url` to deny external domains, or to require allowlisted hosts. |
| **WebSearch** | `WebSearch` | `{ "query": "..." }` | Inspect `query` if you want to block certain searches (rare). |

### Agent control tools

| Tool | Matcher | `tool_input` shape | What to check for in hooks |
|---|---|---|---|
| **Task** | `Task` | `{ "subagent_type": "...", "description": "...", "prompt": "..." }` | Inspect `subagent_type` to police which agents can be spawned. Inspect `prompt` to enforce a rubric or banned topics. Note: `SubagentStop` hook fires when the launched agent finishes. |
| **TodoWrite** | `TodoWrite` | `{ "todos": [ { "content": "...", "status": "...", "id": "..." } ] }` | Inspect to detect anti-patterns (e.g. "wrote a single todo and immediately marked it done"). |

### Built-in tools we usually don't hook

`ExitPlanMode`, `BashOutput`, `KillShell`, `ListMcpResources`, `ReadMcpResource`, and tools provided by user-added MCP servers — these have their own shapes; generated hooks should only touch them if there's a clear reason.

---

## 3. PostToolUse `tool_response` shapes (highlights)

PostToolUse hooks also receive `tool_response`. Shapes that matter most for our telemetry hook and our generated "post-edit type check" / "post-write format" patterns:

| Tool | `tool_response` (typical keys) |
|---|---|
| `Read` | The file contents (often truncated metadata). |
| `Write` / `Edit` | Confirmation of write, possibly with the new content. |
| `Bash` | `{ "stdout": "...", "stderr": "...", "exit_code": 0, "interrupted": false }` — the **rich one**. Telemetry uses `exit_code` and a truncated `stderr` to record outcome. |
| `Glob` / `Grep` | Match results / counts. |
| `TodoWrite` | `{ "oldTodos": [...], "newTodos": [...] }`. |
| `Task` | The subagent's final response. |

Treat `tool_response` shapes as best-effort references — the safest move in a generated hook is to log the keys you actually need and tolerate missing ones.

---

## 4. Matcher patterns we'll generate most often

For `self-improving-claude`'s first wave of generated hooks, expect these matcher patterns to dominate:

| Matcher | Why we'd use it |
|---|---|
| `"Read"` | Block reads of secrets / sensitive paths. |
| `"Bash"` | Block dangerous shell commands; gate destructive ops. |
| `"Write\|Edit\|MultiEdit"` | After any file write: run formatter, run type check, enforce conventions. |
| `"Edit\|MultiEdit"` | After edits specifically: stricter post-checks (e.g. ensure imports are still valid). |
| `"*"` | The telemetry hook — match everything. |

---

## 5. Implications for `self-improving-claude`

1. **Generated-hook boilerplate.** Every script we generate starts with the stdin → JSON → branch-on-`tool_name` pattern above. We can ship a small generator that produces this boilerplate so the LLM only writes the body.
2. **Tool detection at the top.** Hooks should validate `tool_name` matches what they expect — protects against misconfigured matchers (e.g. user's matcher widens later and unexpectedly fires the hook for `Bash` when it was written for `Edit`).
3. **`Bash` is the highest-value target.** Most "Claude did something dangerous" stories live in Bash. The plugin should bias toward generating Bash-aware hooks when the bug-context warrants it.
4. **`tool_response.exit_code` is the telemetry gold.** A bash command that exits non-zero is often the moment something went wrong — that's the signal our telemetry hook needs to capture (truncated stderr + exit code) so `/improve-init` can find "the test command failed 12 times this month."
5. **Never trust schemas blindly.** Generated hooks must use defensive lookups (`input.file_path || ""`) — fields may evolve. Helper hook with `jq . > log.jsonl` (already in the main reference) is the way to verify a shape before writing a real hook.
