# Design Notes — self-improving-claude

> **Status:** Working notes from the initial brainstorming session. Not yet a formal spec. We paused before writing the implementation spec to first gather context (Anthropic Claude Code course material, related references) into `docs/knowledge/`.

---

## Locked Decisions

| Topic | Decision |
|---|---|
| Project name | `self-improving-claude` |
| Form factor | Claude Code plugin |
| Slash commands | `/improve` (reactive, in-context) and `/improve-init` (proactive, full project pass) |
| Command args | Free-text accepted, used for feedback or directives |
| Inputs (reactive) | The current chat scrollback — the bug the user just witnessed |
| Inputs (proactive) | Project code + `~/.claude/projects/<project>/` transcripts + bundled telemetry log |
| Hook generation | Freeform LLM-written (no template library) |
| Knowledge grounding | Anthropic *Claude Code* course material, bundled as reference inside the plugin |
| Runtime | In the user's live Claude Code session — uses their subscription, no separate API key |
| Review UX | Per-hook interactive diff + approval (one at a time) |
| Trust model | Nothing installs without explicit consent; hooks live as readable, deletable files |
| Telemetry hook scope | `{tool, timestamp, summarized_args, outcome}` — args summarized, no raw secrets |
| Iteration | Re-run-driven; feedback channel via free-text command args |
| Cleanup | Skill ends by instructing user to ESC-ESC-rewind the conversation (manual for v1) |

## Out of Scope for v1

- Programmatic chat rewind (user does ESC-ESC manually)
- Background daemon / continuous learning
- Template library
- Built-in hook-disable UI (managed by editing/deleting files)
- CI integration

## Open Questions (deferred to spec-writing phase)

- Exact format and path of the telemetry log
- Plugin manifest specifics & install command
- How the Anthropic course content is distilled into the bundled reference doc — this depends on the knowledge we ingest in the next phase
- License (likely MIT)
- Whether `/improve-disable` or similar tooling is needed in v1

## Components (sketch)

1. **Skill** — markdown that runs in the user's session. Orchestrates: gather context → propose hooks → loop per-hook approval → write files → instruct rewind. Embeds the curated *Claude Code* course knowledge as reference.
2. **Two slash commands** — `/improve`, `/improve-init`. Each invokes the skill with a different mode flag.
3. **Telemetry hook** — small `PostToolUse` script (likely Python). Installed into the user's project on first run. Writes JSONL to `.claude/self-improving-claude/telemetry.jsonl` (path TBD).
4. **Plugin manifest** — registers everything.

## Data Flow — `/improve` (reactive)

1. User invokes `/improve` after seeing a problem in chat.
2. Skill reads the recent chat history as primary signal.
3. Claude drafts 1–5 candidate hooks grounded in course-material patterns.
4. For each: rationale + script + event binding → `approve / reject / edit`.
5. Approved hooks written to `.claude/hooks/<descriptive-name>.{sh,py}` and registered in `.claude/settings.json`.
6. Final message instructs user to ESC-ESC-rewind.

## Data Flow — `/improve-init` (proactive)

Same as above but inputs are project code + `~/.claude/projects/` transcripts + telemetry log. Tends to propose a larger baseline set.

## Error Handling (sketch)

- Hook scripts with obvious syntax errors are caught before approval prompt.
- Conflicts in `.claude/settings.json` surfaced to user with resolution options.
- Missing `.claude/` directory: created on first install.

## Testing Strategy (sketch)

- Fixture projects with planted bug patterns; assert proposed hooks include expected guardrails.
- Unit tests on telemetry hook (format, secret redaction).
- End-to-end: install plugin into sandbox config, run `/improve-init`, verify file outputs.

---

## Next Step (when we resume)

1. Populate `docs/knowledge/` with:
   - Notes from the Anthropic Claude Code course (hooks, skills, plugins, slash commands, settings.json)
   - Reference docs / links the user wants to ground the implementation in
2. Revisit this design with the new context — refine, add missing pieces.
3. Write the formal spec to `docs/superpowers/specs/2026-05-21-self-improving-claude-design.md`.
4. Move to implementation plan via the `writing-plans` skill.
