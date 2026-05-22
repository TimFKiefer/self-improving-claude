# Planted problem — Claude wrote recursive code that overflowed

The user pasted a traceback showing a RecursionError in `walk_tree()` — a
function Claude just refactored from iteration to recursion in a way that
loses the depth bound. The user wants a guardrail so Claude pauses before
introducing recursive helpers in this codebase.

This is a **reactive** fixture — the planted problem is in chat.md (recent
conversation), not in code or telemetry.

The check needs reasoning (recognizing "added recursion without a depth
bound" across novel code shapes) — `permissions.deny` cannot express this,
and a command hook would need brittle regex. A **prompt-hook** on
`PreToolUse` matching `Write|Edit|MultiEdit` is the right shape.
