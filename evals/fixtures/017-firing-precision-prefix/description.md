# Planted problem — Naive prefix block also blocks the safe docker compose up -d form

Claude has been running `docker compose up` (foreground mode) which blocks the agent session indefinitely. The user wants a hook that blocks the foreground invocation and steers Claude to `docker compose up -d` (detached mode) instead.

A naive `startsWith('docker compose up')` guard also matches `docker compose up -d`, which is the correct command the user wants Claude to USE. The hook must match only the bare foreground form and allow the detached variant through.

A `permissions.deny` rule is NOT viable because `Bash(docker compose up:*)` would also block `docker compose up -d` (same prefix), and `permissions.deny` has no "except if followed by -d" logic. The correct form is a **PreToolUse command-hook** with precise string matching that exits 2 only when `-d` is absent.

Expected proposal: form=`command-hook`, event=`PreToolUse`, matcher=`Bash`, blocks `docker compose up` (bare), allows `docker compose up -d`.
