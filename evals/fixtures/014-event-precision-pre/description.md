# Planted problem — Claude writes hand-edits into db/migrations/ that must be blocked

The project manages database migrations with a strict policy: migration files in `db/migrations/*.sql` are generated-only and must never be edited by hand. Claude has been writing SQL files directly into that directory during schema work.

The user wants the write BLOCKED — not flagged after the fact. A `PostToolUse` hook cannot block a write that has already happened; it can only surface information after the tool ran. The correct event is **`PreToolUse`** so the hook fires before `Write` or `Edit` reaches the migration file.

Expected proposal: form=`command-hook`, event=`PreToolUse`, matcher includes `Write` and `Edit`.
