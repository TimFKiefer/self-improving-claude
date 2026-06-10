# Hooks and the Agent SDK

Source: Anthropic *Claude Code* course material. This file is the canonical reference for everything we need to know about hooks and the Agent SDK when implementing `self-improving-claude`. The plugin will both *write* hooks (its core output) and likely *use* the Agent SDK (for sub-reviews and similar workflows), so both surfaces matter.

---

## 1. What hooks are and how they fit in

Hooks let you run commands **before** or **after** Claude attempts to run a tool. They sit inside Claude Code's normal request → model → tool-call → result loop, intercepting either the proposed tool call (pre) or the completed one (post).

```
user prompt
  ↓
Claude (model) — proposes a tool call
  ↓
[PreToolUse hook fires]  ← can BLOCK the call
  ↓
Claude Code executes the tool
  ↓
[PostToolUse hook fires]  ← cannot block; can give feedback / run follow-ups
  ↓
result returns to Claude
```

They're useful for:

- **Code formatting** — auto-format files after Claude edits them
- **Testing** — run tests when files change
- **Access control** — block reads/edits of specific paths
- **Code quality** — run linters/type checkers and feed results back to Claude
- **Logging** — track tool usage
- **Validation** — enforce naming conventions or coding standards

---

## 2. Hook types (full list)

Beyond `PreToolUse` and `PostToolUse`, Claude Code supports:

| Hook | Fires when |
|---|---|
| **PreToolUse** | Before a tool is called. Can block. |
| **PostToolUse** | After a tool is called. Cannot block. |
| **Notification** | When Claude Code sends a notification (needs permission for a tool, or has been idle for 60 seconds). |
| **Stop** | When Claude Code has finished responding. |
| **SubagentStop** | When a subagent (shown as "Task" in the UI) has finished. |
| **PreCompact** | Before a compact operation occurs (manual or automatic). |
| **UserPromptSubmit** | When the user submits a prompt, before Claude processes it. |
| **SessionStart** | When starting or resuming a session. |
| **SessionEnd** | When a session ends. |

For `self-improving-claude`, the most relevant ones to generate as guardrails are `PreToolUse` (most blocks live here) and `PostToolUse` (auto-formatters, post-edit type checks, etc.). `UserPromptSubmit` and `Stop` are interesting for nudges and cleanup. `PostToolUse` is also what our bundled telemetry hook will be.

---

## 3. Configuration files and locations

Hooks live in Claude settings files. There are three locations:

| File | Scope |
|---|---|
| `~/.claude/settings.json` | **Global** — applies to all projects on your machine. |
| `.claude/settings.json` | **Project, committed** — shared with the team. |
| `.claude/settings.local.json` | **Project, not committed** — personal settings. |

You can edit these by hand or use the `/hooks` command inside Claude Code.

Top-level structure looks like:

```json
{
  "hooks": {
    "PreToolUse":  [ /* hook configs */ ],
    "PostToolUse": [ /* hook configs */ ]
  }
}
```

### PreToolUse example

```json
"PreToolUse": [
  {
    "matcher": "Read",
    "hooks": [
      {
        "type": "command",
        "command": "node /home/hooks/read_hook.js"
      }
    ]
  }
]
```

The `matcher` says which tool to target. The command runs before that tool executes and decides whether to allow or block.

### PostToolUse example

Matchers can be regex-style (using `|`) to cover multiple tools:

```json
"PostToolUse": [
  {
    "matcher": "Write|Edit",
    "hooks": [
      {
        "type": "command",
        "command": "node /home/hooks/edit_hook.js"
      }
    ]
  }
]
```

The matcher `*` matches every tool — useful for a logging/telemetry hook.

---

## 4. Building a hook — the four steps

1. **Decide Pre vs Post.** Pre can block; Post can give feedback / run follow-ups.
2. **Pick which tool(s) to watch.** Use the `matcher` field.
3. **Write a command that receives the tool call** via stdin (JSON).
4. **Communicate back to Claude via exit code.** Optionally write to stderr for messages.

### Tool call JSON (PreToolUse example, Read tool)

```json
{
  "session_id": "2d6a1e4d-6...",
  "transcript_path": "/Users/sg/...",
  "hook_event_name": "PreToolUse",
  "tool_name": "Read",
  "tool_input": {
    "file_path": "/code/queries/.env"
  }
}
```

### Exit code semantics

| Exit code | Meaning |
|---|---|
| `0` | Everything's fine — let the tool call proceed. |
| `2` | Block the tool call (PreToolUse only). Anything written to **stderr** is sent to Claude as the explanation. |

PostToolUse hooks can't block (the tool already ran), but they can still write to stderr to feed information back to Claude.

---

## 5. Worked example — block reading `.env`

### Settings

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read",
        "hooks": [
          { "type": "command", "command": "node $PWD/hooks/read_hook.js" }
        ]
      }
    ]
  }
}
```

### The script (`hooks/read_hook.js`)

```js
process.stdin.setEncoding("utf8");
let input = "";
process.stdin.on("data", (d) => (input += d));
process.stdin.on("end", () => {
  const toolArgs = JSON.parse(input);
  const readPath = toolArgs.tool_input?.file_path || "";
  if (readPath.includes(".env")) {
    console.error("You cannot read the .env file");
    process.exit(2);
  }
  process.exit(0);
});
```

When Claude tries `Read("/path/.env")`, the hook blocks it and Claude sees the stderr message ("You cannot read the .env file").

### Important caveat — input shape differs per tool

Each tool has its own `tool_input` shape:

| Tool | Key fields |
|---|---|
| `Read` | `{ "file_path": "..." }` |
| `Grep` | `{ "pattern": "...", "path": "..." }` — `path` is a search directory, not a file |
| `Bash` | `{ "command": "..." }` |
| `Edit` / `Write` | own shapes too |

So a check on `tool_input.file_path` catches `Read` but not a `Grep` over the project or a `cat .env` via `Bash`. For comprehensive file protection, **combine hooks with `permissions.deny` rules** (e.g. `"Read(**/.env)"`) which apply uniformly across tools.

---

## 6. Security recommendation — absolute paths + the `$PWD` pattern

The Claude Code docs recommend using **absolute paths** for hook scripts to mitigate path interception and binary planting attacks. But absolute paths make it hard to share a `settings.json` between machines.

Workaround: use a `$PWD` placeholder in a checked-in `settings.example.json`, and provide a setup script that:

1. Installs dependencies.
2. Reads `settings.example.json`.
3. Substitutes `$PWD` with the actual absolute path of the project on this machine.
4. Writes the result to `settings.local.json`.

This is how the course's reference projects ship hooks safely. **`self-improving-claude` should adopt this pattern when it writes hook configs that reference scripts by path.**

---

## 7. Patterns worth stealing for our generated hooks

### TypeScript type-check after edits

Claude often updates a function signature in one file but misses callers. A `PostToolUse` hook on `Write|Edit`:

- Runs `tsc --noEmit`.
- Captures any type errors.
- Writes them to stderr so Claude sees them and gets prompted to fix.

Generalises to any language with a type checker (or linter, or test suite).

### Query-duplication prevention via sub-Claude

In repos with many similar files (e.g. `./queries/*.ts`), Claude sometimes writes a new function instead of reusing an existing one. Pattern:

- `PostToolUse` matcher on files inside `./queries/`.
- Hook launches a separate Claude instance via the **Agent SDK**.
- That sub-Claude reviews the change against existing files and flags duplicates.
- If duplicates exist, original Claude gets feedback to consolidate.

Trade-off: powerful but costs time + API calls per fired hook. Apply to high-value directories only.

### General principle

> Use compiler/linter output to provide immediate feedback. Implement code-review processes using separate AI instances. Focus monitoring on high-value directories where consistency matters most. Balance automation benefits against performance costs.

---

## 8. Discovering the actual stdin shape (debug helper)

Because stdin differs per hook type **and** per tool, the easiest way to learn the exact structure is to log it once:

```json
"PostToolUse": [
  {
    "matcher": "*",
    "hooks": [
      { "type": "command", "command": "jq . > post-log.json" }
    ]
  }
]
```

Then trigger the hook in a session and inspect `post-log.json`. Useful for both authoring real hooks and for `self-improving-claude` itself when its generated hooks need to inspect unfamiliar tool inputs.

### Stdin shape examples

`PostToolUse` watching `TodoWrite`:

```json
{
  "session_id": "9ecf22fa-...",
  "transcript_path": "...",
  "hook_event_name": "PostToolUse",
  "tool_name": "TodoWrite",
  "tool_input":  { "todos": [...] },
  "tool_response": { "oldTodos": [...], "newTodos": [...] }
}
```

`Stop`:

```json
{
  "session_id": "af9f50b6-...",
  "transcript_path": "...",
  "hook_event_name": "Stop",
  "stop_hook_active": false
}
```

Note: `PostToolUse` includes a `tool_response`, `PreToolUse` does not (the tool hasn't run yet). `Stop` and other non-tool hooks have entirely different fields.

---

## 9. The Claude Agent SDK

The Agent SDK lets you run Claude Code programmatically. It's available for **TypeScript** and **Python** and exposes the same agent loop as the CLI — file reading, editing, tool use — under your control.

Useful in `self-improving-claude` for:

- **Sub-reviews** (the query-duplication pattern above).
- Any "second opinion" or batch-analysis step where we don't want to pollute the user's main session.

### Install (TypeScript)

```bash
mkdir sdk-demo
cd sdk-demo
npm init -y
npm install @anthropic-ai/claude-agent-sdk
```

> Heads-up: the package is **`@anthropic-ai/claude-agent-sdk`**. The similarly-named `@anthropic-ai/claude-code` is the CLI itself and can't be imported.

### Minimal example (`index.mjs`)

```js
import { query } from "@anthropic-ai/claude-agent-sdk";

const prompt = "List the files in the current directory";

for await (const message of query({ prompt })) {
  console.log(JSON.stringify(message, null, 2));
}
```

Run: `node index.mjs`. You get a stream of JSON message events (tool calls, tool results, Claude's text) — same as the CLI shows.

### Restricting tools

```js
for await (const message of query({
  prompt,
  options: { allowedTools: ["Read", "Glob"] },
})) {
  // ...
}
```

Equivalent of the CLI's `--allowedTools`. Useful when a generated hook calls the SDK and we want to scope it.

### What else the SDK supports

Same as the CLI: custom system prompts, MCP servers, **hooks**, subagents, session resumption. We'll lean on this for any generated hook that needs to invoke Claude to make a decision (e.g. "is this query duplicated?").

---

## 10. Recursion and feedback loops — designing hooks that terminate

A hook script's own side effects (writing files, running formatters) do **not** fire hooks — hooks intercept only *Claude's* tool calls. Loops enter through the **feedback path**: hook output → Claude reacts with a tool call → that call matches the same hook → it fires again. Four loop shapes, each with a required guard:

### Loop A — PostToolUse echo loop

A `PostToolUse` hook on `Write|Edit` emits exit-2 stderr demanding edits; the demanded edits match `Write|Edit` again. If the check is not **convergent** — i.e. the stderr only fires while the violating condition persists, and the demanded action actually clears it — the loop never exits. Imperative stderr (rubric criterion 12, "Do not stop until done") makes a non-convergent hook *worse*, not better: the imperative forbids the model from breaking out. Canonical failure: a matcher-`Write|Edit` hook demanding "update the changelog" fires again on the changelog edit itself, demanding a changelog entry for the changelog entry.

Guards (any one suffices):

1. **Condition-gated stderr** — recompute the violating condition on every fire and exit 0 once it's clean (e.g. re-run the grep/type-check and emit only if hits remain).
2. **Baseline delta** — record the pre-existing state (e.g. the type-error list at session start) and fail only on NEW violations relative to it. Without this, pre-existing debt keeps the check permanently red and the demanded fix can never converge — the most common way an otherwise well-meant type-check/lint hook becomes a loop.
3. **Corrective-path exemption** — early `return 0` when `tool_input` *is* the corrective action (e.g. exempt edits to the changelog file the hook demands).
4. **Narrower matcher** — scope the matcher so the corrective action falls outside it.

Last-resort circuit breaker (a supplement to one of the guards above, never a substitute): a per-session fire-count cap — persist a counter in a state file and exit 0 after N fires on the same condition. This is the hook-land analogue of an agent harness's hard step cap; it bounds the damage when the convergence reasoning was wrong — it does not replace that reasoning.

### Loop B — PreToolUse retry loop

A blocking hook whose stderr names no viable alternative leaves the model retrying variants of the blocked call: block → retry → block. Worse, stderr that recommends an action which the same hook (or an existing `permissions.deny` rule) *also* blocks wedges the session entirely. Guard: blocking stderr must name an off-ramp ("run `pnpm db:migrate:new` instead"), and that off-ramp must be traced to NOT match the same guard or any existing deny rule.

### Loop C — sub-agent fork bomb

A hook that spawns Claude (Agent SDK, §9, or `claude -p`) can create a child session that loads the same project settings — including the hook itself (`claude -p` run in the project directory does this by default; the SDK does when configured to load settings). The child's tool calls then re-fire the hook, which spawns a grandchild, and so on. Because inheritance depends on spawn configuration that's easy to get wrong, the guard is mandatory either way: set a sentinel env var when spawning (e.g. `MY_REVIEW_HOOK_ACTIVE=1`) and exit 0 at the top of the hook when it's present. Tool restriction is defense-in-depth, not a substitute: `allowedTools` is a permission allowlist, not tool removal — the matched tool stays in the child's tool list, and PreToolUse hooks fire on attempted calls *before* the permission check, so even an attempt that permissions would deny re-fires the hook. Restricting tools breaks the loop only for PostToolUse matchers (a denied tool never runs, so PostToolUse never fires) or when a bare-name `disallowedTools` entry removes every matcher-matched tool from the child's context entirely.

### Loop D — Stop-hook continuation loop

A `Stop` hook that forces continuation fires again when the model next tries to stop. The Stop stdin carries `stop_hook_active` (§8) — `true` means the current turn is already running because a Stop hook forced it; the hook MUST exit 0 (allow stopping) in that case. Same for `SubagentStop`. (Also documented in `plugins-and-skills.md`.) Best practice: say so in the stderr — "fix these before stopping, or the next stop attempt will be allowed through" — so the model knows the demand is bounded and doesn't thrash.

### The pre-install test

Loops A and B are catchable before installation with one simulation: construct the tool call the model would most likely make *in response to* the hook's output, and trace it through the hook. If it re-triggers the same output and nothing has converged, the artifact is an infinite loop, not a guardrail.

---

## 11. Implications for `self-improving-claude`

Distilling everything above into design implications:

1. **What we generate.** Almost always `PreToolUse` (for blocks) and `PostToolUse` (for post-action checks/feedback/formatting). Rarely `UserPromptSubmit` or `Stop`.
2. **Where we write.** `.claude/settings.json` (project, shared) for hooks the team should get, and `.claude/settings.local.json` if the user prefers them personal. Default to `settings.json` so the value compounds across the team.
3. **Path convention.** Hook commands must use absolute paths. We adopt the `$PWD` template + setup-script pattern so the repo is shareable.
4. **Hook script home.** `.claude/hooks/<descriptive-name>.{sh,js,py}` — readable filenames so users can audit/delete by hand.
5. **Telemetry hook (bundled).** A `PostToolUse` with matcher `"*"`. Writes `{ tool_name, ts, summarized_args, outcome }` JSONL to `.claude/self-improving-claude/telemetry.jsonl`. We rely on `tool_response` being present in PostToolUse stdin to capture outcome.
6. **Generated hooks that need reasoning.** Use the Agent SDK from inside the hook script (the query-duplication pattern). The plugin can offer these as a "premium" hook category — flag them clearly to the user during approval because they cost API calls.
7. **Stdin parsing in generated hooks.** Generated scripts must read JSON from stdin and consult `tool_input` (Pre) or `tool_input` + `tool_response` (Post). Helper template suggested: each generated hook starts with the same stdin-reading boilerplate (Node or Python), then branches on tool name.
8. **Combine hooks with `permissions.deny` where appropriate.** For uniform file-path protection across all tools, `permissions.deny` is cheaper and more reliable than per-tool hooks. The plugin should know when to prefer one over the other.
9. **Defensive design for blocked tools.** Exit code 2 + stderr message. The stderr text becomes Claude's explanation — generated messages should be specific and actionable ("Don't edit `src/migrations/*.sql` directly — run `pnpm db:migrate:new` instead.").
10. **Loop-safety first (§10).** Before drafting any Pre/PostToolUse hook body, trace the feedback path: does the corrective action the hook demands (or the alternative its block message names) re-fire the same hook non-convergently? Generated hooks must carry one of the §10 guards; SDK-spawning hooks need the sentinel-env guard; Stop hooks must honor `stop_hook_active`. A hook that still fails §10's pre-install test after revision is dropped, never shipped.
