USER: Ändere in src/tools/example.ts den Wert von FILE_READ_TOOL_NAME von 'Read' auf 'View'.

CLAUDE: [Edits src/tools/example.ts]

```typescript
export const FILE_READ_TOOL_NAME = 'View'
```

USER: Bitte überprüfe deine letzte Änderung auf mögliche Regressionen. Suche gezielt nach Stellen, die den alten Tool-Namen "Read" noch hart codiert verwenden.

CLAUDE: [Searches and finds 15 hardcoded 'Read' callers across telemetry, permissions, validators, agent allowlists, and skill bundles that are now broken.]

USER: Das ist genau warum ich einen guardrail will. Bitte eine hook die alle referenzen anzeigt sobald ich einen exported identifier ändere — egal wo in diesem codebase. Nicht nur für walk_tree.
