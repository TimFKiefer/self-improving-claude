# Knowledge Base

Drop reference material here that should inform how `self-improving-claude` reasons about hooks.

Intended sources for the first pass:

- **Anthropic *Claude Code* course** — what hooks exist, how `settings.json` works, idiomatic skill/plugin patterns, examples of well-designed guardrails.
- **Claude Code official docs** — the canonical reference for hook events, slash commands, plugin structure.
- **Real examples from the wild** — community plugins, useful hook patterns, anti-patterns to avoid.

Suggested layout:

```
docs/knowledge/
├── README.md                    (this file)
├── claude-code-course/          (notes / excerpts from the course)
│   ├── hooks.md
│   ├── skills.md
│   ├── plugins.md
│   └── ...
├── official-docs/               (links + distilled summaries)
└── patterns/                    (hook idioms, common pitfalls)
```

This material will eventually be distilled into the reference doc that ships *inside* the plugin and grounds the LLM when it drafts hooks.
