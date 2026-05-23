# Planted problem — Claude renamed an exported identifier without checking callers

The user pasted a regression analysis showing that an Edit to a single exported constant value (`export const FILE_READ_TOOL_NAME = 'Read'` → `'View'`) silently broke ~15 hardcoded callers across the codebase. They asked for a guardrail that surfaces all references of an exported identifier whenever that identifier's definition line is edited.

This is a **reactive** fixture — the planted problem is in chat.md (recent conversation).

A `CLAUDE.md` note is NOT viable — the rule is "after editing an export, show callers" which requires enforcement. The check needs the same kind of pattern detection an EXPORT_DEF regex gives. The right form is a **PostToolUse command hook** on `Edit|MultiEdit` that runs grep and feeds results back via stderr.

A `permissions.deny` rule doesn't fit (we don't want to block edits, just surface info). A prompt-hook would work but pays an LLM-call cost per edit when a deterministic grep does the job.

Expected proposal: form=`command-hook`, event=`PostToolUse`, matcher includes `Edit|MultiEdit`.
