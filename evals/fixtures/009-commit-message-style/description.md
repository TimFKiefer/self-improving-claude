# Planted problem — verbose commit messages (a soft convention)

Claude writes long multi-paragraph git commit messages; the team wants short,
imperative one-line subjects ("Add X", not "This commit adds X and also..."). 

This is the case where the right answer is **`claude-md-note`**, not a hook or a
permission rule:
- There is no deterministic tool event to gate — commit-message style isn't reliably
  inspectable at `git commit` time, and exit-2 blocking a commit over prose style would
  be hostile.
- It's a soft preference, not a hard rule. The cheapest, most appropriate intervention
  is a one-line convention added to `CLAUDE.md` so Claude reads it as guidance.

A proposal that reaches for a `PreToolUse` Bash hook on `git commit` here is
over-engineering; the ideal proposal recognizes this belongs in `CLAUDE.md`.
