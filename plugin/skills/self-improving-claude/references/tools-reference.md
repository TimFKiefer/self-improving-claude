# Tools Reference (runtime lookup)

What `tool_input` and `tool_response` look like per built-in tool. Generated hooks need this to branch correctly. For the full discussion of why, see `docs/knowledge/tools-reference.md`.

## Standard stdin envelope

```json
{
  "session_id": "uuid",
  "transcript_path": "/abs/path",
  "cwd": "/abs/path",
  "permission_mode": "ask|allow",
  "hook_event_name": "PreToolUse|PostToolUse|...",
  "tool_name": "<see table>",
  "tool_input":    { /* varies */ },
  "tool_response": { /* PostToolUse only, varies */ }
}
```

## Python boilerplate (use as the head of every generated command hook)

```python
import json, sys

def main():
    try:
        ev = json.load(sys.stdin)
    except Exception:
        return 0  # never break Claude Code on bad input

    tool  = ev.get("tool_name", "")
    inp   = ev.get("tool_input")    or {}
    resp  = ev.get("tool_response") or {}

    # branch on `tool`; inspect `inp` / `resp`
    # block: print to stderr and return 2
    # allow: return 0

    return 0

if __name__ == "__main__":
    sys.exit(main())
```

## Per-tool `tool_input` (with matcher)

| Tool | Matcher | `tool_input` keys |
|---|---|---|
| `Read` | `Read` | `file_path` (abs) |
| `Write` | `Write` | `file_path` (abs), `content` |
| `Edit` | `Edit` | `file_path`, `old_string`, `new_string`, `replace_all` |
| `MultiEdit` | `MultiEdit` | `file_path`, `edits` (array of `{old_string, new_string}`) |
| `Glob` | `Glob` | `pattern`, `path` (search root, a directory) |
| `Grep` | `Grep` | `pattern` (regex), `path`, `glob`, `output_mode` |
| `Bash` | `Bash` | `command`, `description`, `timeout`, `run_in_background` |
| `WebFetch` | `WebFetch` | `url`, `prompt` |
| `WebSearch` | `WebSearch` | `query` |
| `Task` | `Task` | `subagent_type`, `description`, `prompt` |
| `TodoWrite` | `TodoWrite` | `todos` (array of `{content, status, id}`) |
| `NotebookEdit` | `NotebookEdit` | notebook-specific cell edits (rare) |

## Per-tool `tool_response` (PostToolUse only, highlights)

| Tool | `tool_response` shape |
|---|---|
| `Bash` | `{ stdout, stderr, exit_code, interrupted }` — `exit_code` is the gold for telemetry |
| `Read` | file content (often with metadata) |
| `Write` / `Edit` | confirmation of write |
| `Glob` / `Grep` | matches / counts |
| `TodoWrite` | `{ oldTodos, newTodos }` |
| `Task` | subagent's final response |

When generating PostToolUse hooks, look up the response shape here; in unfamiliar cases use defensive lookups (`resp.get("exit_code", 0)`).

## Most-likely matchers we'll generate

| Matcher | Why |
|---|---|
| `Bash` | Block dangerous shell commands; gate destructive ops |
| `Read` | Block reads of secrets / sensitive paths (often beaten by `permissions.deny`) |
| `Write\|Edit\|MultiEdit` | Post-write formatter, type-check, convention enforcement |
| `Edit\|MultiEdit` | Stricter post-edit checks (e.g. import-validity) |
| `*` | Telemetry, blanket logging — we already ship this one; rarely need to generate another |

## Matcher syntax

- Exact: `"Bash"`
- Alternation: `"Read|Write|Edit"`
- Wildcard: `"*"`
- Regex: `"mcp__.*"` — matches all MCP tools (case-sensitive)

## Bash inspection — common hostile patterns

When drafting a Bash-targeting hook, check for these in `tool_input.command`:

- `rm -rf` outside `${CLAUDE_PROJECT_DIR}`
- `git push --force` or `git push -f` (especially to `main`/`master`)
- Pipes to `sh` / `bash` from `curl` / `wget`
- `eval` of unvetted input
- Project-specific anti-patterns surfaced in `<recent_chat>` or `<telemetry_excerpt>`
