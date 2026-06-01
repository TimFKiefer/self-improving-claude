# Planted problem — Edit-watching hook silently misses MultiEdit calls

Claude edits TypeScript source files using both `Edit` and `MultiEdit` interchangeably. A post-edit hook was requested to grep for stale export callers after any edit to an exported identifier. The orchestrator drafted a hook matched only on `Write|Edit`, silently missing all `MultiEdit` calls — which Claude uses whenever applying several edits to one file in a single turn.

`MultiEdit` is a distinct tool name in the Claude Code tool set. A hook with `matcher: "Write|Edit"` never fires when the tool is `MultiEdit`, leaving a silent gap in coverage.

Expected proposal: form=`command-hook`, event=`PostToolUse`, matcher includes `Write`, `Edit`, and `MultiEdit`.
