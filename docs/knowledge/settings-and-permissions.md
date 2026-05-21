# `settings.json` and the Permissions System

Source: course material covers the **hooks** section of `settings.json`. This file summarizes the *rest* of that file (permissions, env, etc.) and the `permissions.deny` system that the hooks doc already cross-references. Confidence is marked per section because some of this is broadly-documented Claude Code basics rather than direct course excerpts.

> **Why this matters:** `self-improving-claude` writes to `.claude/settings.json`. If it clobbers the user's existing `permissions` block or produces invalid syntax, we break their setup. We need a defensive merge, not a naive overwrite — and to do that we need to know the full schema.

---

## 1. The three settings files (recap)

Already established in `hooks-and-sdk.md`, but worth keeping handy:

| File | Scope | Source of truth for |
|---|---|---|
| `~/.claude/settings.json` | Global, per-machine | Personal defaults, sensitive tokens, machine-specific paths. |
| `.claude/settings.json` | Project, **committed** | Team-shared rules, hooks, permissions. |
| `.claude/settings.local.json` | Project, **not committed** | Personal overrides for this project. |

When the plugin writes a generated hook, it should default to **`.claude/settings.json`** so the team benefits, with an override flag to write to `settings.local.json` for personal rules. **Never** write to `~/.claude/settings.json` without explicit user confirmation — that's a different scope.

---

## 2. Top-level structure

A populated `settings.json` typically looks like this (confidence: high for the keys shown; exact shape per key is documented per section below):

```json
{
  "permissions": { ... },
  "hooks":       { ... },
  "env":         { ... },
  "model":       "claude-...",
  "statusLine":  { ... }
}
```

Keys are independent — adding `hooks` doesn't require removing or modifying `permissions`. **A safe writer is a key-level merger**, not a full-file overwrite.

---

## 3. The `permissions` block

(Confidence: medium-high. The general syntax is documented Claude Code behavior; treat specific edge cases as worth verifying against official docs.)

`permissions` is a sibling of `hooks` and controls what tools Claude is allowed to use, often more cheaply and uniformly than a hook can. It has up to three arrays:

```json
"permissions": {
  "allow": [ "Bash(git status:*)", "Read(./src/**)" ],
  "deny":  [ "Read(**/.env)", "Read(**/.env.*)", "Bash(rm -rf:*)" ],
  "ask":   [ "Bash(git push:*)" ]
}
```

### Rule syntax

Each rule is `ToolName(<pattern>)`:

- **`ToolName`** — e.g. `Read`, `Write`, `Bash`, `WebFetch`, etc.
- **`<pattern>`** — tool-specific:
  - For file tools (Read, Write, Edit, Glob, Grep): a path glob — `**/.env`, `./src/**`, `/absolute/path`.
  - For `Bash`: a command prefix — `git status`, `git push:*` (the `:*` is the common "trailing-args wildcard" idiom — exact syntax worth verifying against docs).
  - For `WebFetch`: a URL or host pattern.

A rule with no parentheses (`"Bash"`) matches the entire tool.

### Resolution order

(Behavior I'd expect, but worth verifying against docs.) Roughly:

1. `deny` always wins — if a tool call matches any deny rule, it's blocked, regardless of allow.
2. `ask` prompts the user even if `allow` would otherwise permit.
3. `allow` lets the call through silently.
4. Anything not matched falls back to Claude Code's default permission behavior for that tool.

### When to use permissions vs hooks

| Use **`permissions.deny`** when… | Use a **`PreToolUse` hook** when… |
|---|---|
| You want uniform protection across multiple tools for the same path. (One rule, no code.) | The condition is **not** expressible as a tool/path glob (e.g. "block if the file content contains `process.env.SECRET_KEY`"). |
| The block is static and unconditional. | The block depends on dynamic state (file contents, time of day, recent failures). |
| You want low overhead — no script invocation. | You also want to feed Claude a custom explanation via stderr. |

**Implication for our plugin:** when generating a guardrail, we should prefer `permissions.deny` if a glob will do, and reach for a hook only when the logic needs code. This is cheaper to maintain and runs faster.

---

## 4. The `env` block

(Confidence: medium.) Lets the project set environment variables that Claude Code (and its hook scripts) see:

```json
"env": {
  "CLAUDE_PROJECT_FLAG": "true",
  "NODE_ENV": "development"
}
```

Useful for hook scripts — a generated hook can rely on a project-defined env var without hardcoding it.

---

## 5. The `model` and `statusLine` keys

(Confidence: medium; rarely relevant to our plugin.)

- **`model`** — pins the model used for this project. Our plugin shouldn't touch this.
- **`statusLine`** — configures the status line at the bottom of the Claude Code UI (custom shell command that produces the status string). Out of scope for our plugin.

---

## 6. Defensive write strategy for our plugin

When `self-improving-claude` installs an approved hook, it must:

1. **Read** the current `.claude/settings.json` (create with `{}` if missing).
2. **Parse** to JSON. If parsing fails, refuse to write and ask the user to fix it manually.
3. **Merge at the key level:**
   - Add to `hooks.PreToolUse` / `hooks.PostToolUse` arrays, never overwrite the array.
   - Add to `permissions.deny` only when the new rule isn't already present (deduplicate).
   - Leave every other key untouched.
4. **Pretty-print** with stable 2-space indent (so git diffs are readable for the user).
5. **Show the diff** as part of the per-hook approval flow (already in the design).

If we ever write `permissions.deny` rules, we should also leave a comment-like marker — JSON doesn't allow comments, but we can use a sentinel description field on hook entries (e.g. `"name": "self-improving-claude/block-env-read"`) so they're easy to find and remove later.

---

## 7. Implications for `self-improving-claude`

1. **Prefer `permissions.deny` over a `PreToolUse` hook** when a glob suffices. Cheaper, faster, no script to audit. The skill's hook-drafting prompt should be biased this way.
2. **All approvals should show the merged file**, not just the new lines, so the user sees exactly what their `settings.json` will look like.
3. **Mark plugin-generated entries.** Add a stable identifier (e.g. on each hook entry: `"name": "self-improving-claude/<descriptive-slug>"`) so the user can find/disable them. JSON has no comments, so a sentinel field is our best signal.
4. **Conflict handling.** If a user already has a hook for the same matcher, surface that during approval and let the user choose: keep both, replace, or skip. Don't silently append duplicates.
5. **Never touch `model` or `statusLine`.** Out of scope.
6. **Settings.local.json is reachable** via the same merge logic if the user prefers personal-scope hooks. Default is the committed file.
