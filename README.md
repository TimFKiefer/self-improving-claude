# self-improving-claude

> A Claude Code plugin that turns the bugs you just saw into the hooks that prevent the next ones — using the conversation you're already in.

**Status:** 🌱 Design locked, implementation not started.

---

## The Big Idea

You're working with Claude Code. It does something annoying — runs the wrong test command, edits a file it shouldn't, forgets a migration step. Today, you sigh, fix it manually, and hope it doesn't happen again.

**With this plugin, you type `/improve` *right then*.** While the context of what just went wrong is still in the chat, Claude reviews what happened, proposes hooks that would have caught it, walks you through approving each one, installs them — and then the conversation rewinds to the moment you typed `/improve`. The fix sticks; the chat noise doesn't.

It's a Claude Code add-on that helps Claude Code get better at *your* project, the moment you notice it isn't.

---

## Two Commands

| Command | When to use it | How it works |
|---|---|---|
| **`/improve`** | Reactive — "I just saw a bug / pattern I don't want again." | Runs inside the current session. Uses the live chat context (the bug is right there in scrollback). Proposes targeted hooks, gets per-hook approval, installs, then asks you to ESC-ESC-rewind. |
| **`/improve-init`** | Proactive — first-time setup, or periodic full sweep. | Reads project code + docs + accumulated telemetry log. Proposes a baseline set of guardrails. Same per-hook approval flow. |

Both commands accept free-text args:
- `/improve "add a rule that prevents X"` — directive
- `/improve "the foo-hook just blocked something legit"` — feedback signal for next run

---

## Why Hooks (And Not Just More Prompt)

Hooks are deterministic. A model can forget a rule from a system prompt — a `PreToolUse` hook cannot. By converting learned lessons into hooks, we move project knowledge from the prompt (fragile, expensive, optional) to the harness (cheap, mandatory, fast).

Skills tell Claude *how* to do something. Hooks enforce *what* must or must not happen. This plugin uses the model to *generate* those deterministic guardrails, tuned to one specific project.

---

## How It Works

```
   /improve  (you just saw a bug)              /improve-init  (first time / full pass)
        │                                              │
        │  uses current chat context                   │  reads project files
        │  as primary signal                           │  + ~/.claude/projects transcripts
        │                                              │  + bundled telemetry log
        ▼                                              ▼
   ┌────────────────────────────────────────────────────────┐
   │  Skill running in current Claude Code session          │
   │  (no separate API key — uses your subscription)        │
   │                                                        │
   │  • Identifies candidate problems                       │
   │  • Drafts freeform hook scripts                        │
   │  • Grounded in Anthropic's Claude Code course material │
   └────────────────────────────────────────────────────────┘
        │
        ▼
   Per-hook interactive review:
   ─ what problem this hook solves
   ─ full hook script (diff)
   ─ which event it binds to (PreToolUse, etc.)
   ─ approve / reject / edit
        │
        ▼
   Writes:
   ─ .claude/settings.json (hook registration)
   ─ .claude/hooks/*.sh|*.py (the actual scripts)
        │
        ▼
   "Done. Press ESC twice and select the message
    where you ran /improve to clean up this conversation."
```

A passive **telemetry hook** ships with the plugin. On each tool use it appends `{tool, timestamp, summarized_args, outcome}` to a local log. Secrets aren't captured (args are summarized, not raw). `/improve-init` mines this log to find patterns; `/improve` doesn't strictly need it.

---

## Trust Model

Generated hooks are **freeform LLM-written code**, which means each one is arbitrary. We compensate with strict review UX:

- **No hook is installed without your approval.** Per-hook diff + y/n.
- **Each proposed hook explains itself** — what bug it prevents, why it fires, when.
- **Easy to remove.** The plugin's hooks live in `.claude/hooks/` with descriptive filenames so you can delete or edit them by hand later.

---

## Knowledge Source

Hook suggestions are grounded in Anthropic's public **Claude Code** course material — the canonical patterns for what hooks exist, what they're good at, and how to write them idiomatically. The plugin bundles a curated reference; the model leans on it when drafting hooks.

---

## Architecture Snapshot

- **Form factor:** Claude Code plugin
- **Slash commands:** `/improve`, `/improve-init`
- **Bundled assets:** the skill that drives the flow, the telemetry hook, a reference doc distilling the Claude Code course knowledge
- **Runtime:** entirely in the user's existing Claude Code session — uses their subscription, their model, their context
- **Side effects on user's project:** writes to `.claude/settings.json` and creates files under `.claude/hooks/`

---

## Status — Locked Decisions

✅ Name: `self-improving-claude`
✅ Form factor: Claude Code plugin
✅ Slash commands: `/improve` (in-context, reactive) and `/improve-init` (full project pass, proactive)
✅ Both accept free-text args for feedback and directives
✅ Inputs: current chat (for `/improve`) + project code + session transcripts + telemetry log (for `/improve-init`)
✅ Hook generation: freeform LLM-written, grounded in Claude Code course material
✅ Review: per-hook interactive diff + approval
✅ Trust: nothing installs without explicit consent; hooks live as readable files
✅ Telemetry: moderate (tool + summarized args + outcome) to a local log
✅ Iteration: re-run-driven, with feedback channel via command args
✅ Cleanup: skill ends by prompting user to ESC-ESC-rewind the chat detour

## Status — Still TBD

- License (likely MIT)
- Exact format of the telemetry log
- Plugin manifest specifics & install command
- How the Claude Code course knowledge is distilled into the bundled reference

These will be worked out in the design spec and implementation plan.

---

## License

TBD (likely MIT).

---

## Contributing

Not open for contributions yet — design phase only.
