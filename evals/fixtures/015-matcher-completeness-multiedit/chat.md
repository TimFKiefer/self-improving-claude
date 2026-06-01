USER: Please rename FILE_READ_TOOL_NAME from 'Read' to 'View' in src/tools/example.ts and also update the other constant.

CLAUDE: [Uses MultiEdit on src/tools/example.ts to update both constants at once]

USER: Great. Now I want a guardrail that greps for stale callers whenever you edit any exported identifier — I don't want silent regressions. Make sure it catches both Edit and MultiEdit.

CLAUDE: [Proposes a PostToolUse hook on Write|Edit that greps for export callers — but omits MultiEdit from the matcher]

USER: That hook missed the MultiEdit I just did. MultiEdit is a separate tool and it won't fire on it with that matcher.
