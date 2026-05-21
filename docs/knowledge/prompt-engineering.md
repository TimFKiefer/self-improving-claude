# Prompt Engineering for the `self-improving-claude` SKILL

Source: distilled from Anthropic's *Building with the Claude API* course (Section: Prompt engineering techniques). Confidence: **high** — these are well-established Anthropic-recommended techniques.

> **Why this matters:** the `SKILL.md` we ship is *itself* a prompt — when invoked, its body becomes Claude's active instructions. Whether `/improve` proposes well-crafted hooks or sloppy ones depends almost entirely on how that prompt is written. The techniques below are how we make it reliable.

---

## 1. The five techniques, ranked by leverage

| Technique | One-line summary | Where we use it |
|---|---|---|
| **Be clear and direct** | Lead with action verbs, write instructions not questions. | Opening lines of the SKILL body and every per-step instruction. |
| **Be specific** | List output guidelines *and* (for complex tasks) process steps. | The "what makes a good hook" rubric the skill applies. |
| **Structure with XML tags** | Wrap interpolated content in named tags so Claude can tell instructions from data. | Wrapping chat-context, project-code samples, telemetry-log excerpts. |
| **Provide examples (one-shot / multi-shot)** | Show input/output pairs that demonstrate the pattern. | Example "good hook" and "rejected hook" pairs inside the SKILL. |
| **Temperature control** | Lower for deterministic tasks, higher for creative ones. | Likely irrelevant in v1 (we use the user's Claude Code session and don't control temperature) — noted for completeness. |

The first four are what we'll actually wield. Treat the rest of this doc as the spec for *how* to wield them inside the SKILL.

---

## 2. Be clear and direct

**Principles:**

- Use simple language; no ambiguity.
- Use instructions, not questions. Start with action verbs: *Write*, *Generate*, *List*, *Identify*, *Block*.
- The first line of the prompt is the most important.

**Anti-example (vague):**

> "What hooks might be good for this project?"

**Pro-example (directive):**

> "Identify up to 5 candidate hooks that would have prevented the issue described in the conversation context below."

For our SKILL, every step should be an imperative: *Read the recent chat. Identify candidate problems. Draft hooks. Show each diff. Wait for approval. Write files. Instruct the user to rewind.*

---

## 3. Be specific

Two flavors, both worth using:

### Output-quality guidelines (always use)

A list of qualities the output must have. Acts as a safety net.

For our SKILL:

> Each proposed hook must:
> - Solve a *specific* problem grounded in observed behavior, not a hypothetical
> - Bind to exactly one event (PreToolUse / PostToolUse / etc.) with a precise `matcher`
> - Use absolute paths (per the `$PWD` pattern)
> - Begin with a stdin → JSON → branch-on-`tool_name` header (see `tools-reference.md`)
> - Include a one-sentence rationale that names what bug it prevents and why a hook (not `permissions.deny`) is right for it
> - Be ≤ 60 lines

### Process steps (use for complex multi-step tasks)

A numbered procedure. Per the course: *"add step-by-step instructions when you're dealing with troubleshooting complex problems, decision-making scenarios, critical thinking tasks, or any situation where you want Claude to consider multiple angles."*

For our SKILL's hook-drafting step:

1. Identify the *specific* observed problem from the chat / telemetry.
2. Decide: is this expressible as a `permissions.deny` rule? If yes, propose that instead of a hook.
3. If a hook is needed, pick the correct event (`PreToolUse` for blocking, `PostToolUse` for follow-up).
4. Determine the correct `matcher` based on `tools-reference.md`.
5. Draft the script body following the standard boilerplate.
6. Validate the script's syntax mentally before showing to the user.
7. Write a one-sentence rationale.

The combination of *guidelines + process* is what the course calls "professional prompting." We use both.

---

## 4. Structure with XML tags

The pain point: when a prompt interpolates lots of content (chat history, code, logs), Claude can struggle to tell instructions from data. XML tags solve this.

**Anti-pattern:**

```
Here is the chat context and the project file. Suggest hooks.
{chat_context}
{file_contents}
```

**Pattern (with XML):**

```
Suggest hooks based on the following.

<recent_chat>
{chat_context}
</recent_chat>

<project_snapshot>
{file_contents}
</project_snapshot>

<telemetry_excerpt>
{telemetry_log}
</telemetry_excerpt>
```

Use **descriptive names** (`<recent_chat>` beats `<data>`). For our SKILL the natural tags are:

| Tag | Contains |
|---|---|
| `<recent_chat>` | Last N messages from the live session (reactive `/improve`) |
| `<project_snapshot>` | Sampled code / CLAUDE.md / package.json |
| `<telemetry_excerpt>` | Relevant rows from `.claude/self-improving-claude/telemetry.jsonl` |
| `<existing_hooks>` | What's already in `.claude/settings.json` so we don't propose duplicates |
| `<user_directive>` | The free-text `$ARGUMENTS` if the user gave any |
| `<rubric>` | The output-quality guidelines from §3 |
| `<examples>` | One-shot / multi-shot example hook proposals |

This is the structure the SKILL builds before drafting hooks.

---

## 5. Provide examples (one-shot, multi-shot)

The course's strongest signal: *"examples are particularly powerful because they show rather than tell."* Instead of describing what a good hook looks like, demonstrate it.

**Pattern:**

```
<example>
  <observed_problem>
    Claude ran `pnpm test` 3 times in this session; each failed because the
    project uses `pnpm test:ci` (the bare `pnpm test` opens an interactive
    watcher, never exits).
  </observed_problem>

  <proposed_hook>
    Event: PreToolUse
    Matcher: Bash
    Script: <inline JS that blocks `pnpm test` and suggests `pnpm test:ci`>
    Rationale: A deterministic block is cheaper than relying on Claude to
    remember; a permissions.deny rule wouldn't work because the substring
    "pnpm test" is also the prefix of the correct command.
  </proposed_hook>
</example>
```

**Best practices from the course:**

- Wrap each part in clearly named XML tags.
- Be explicit: "Here is an example of a problem and an ideal hook proposal."
- After the example, **explain why the output is good** (one sentence). The course flags this as a frequently-missed step that significantly improves results.
- Include examples that match your highest-value failure cases — most-common, most-painful, most-easily-mishandled bugs.
- Use multi-shot when you need to cover meaningfully different scenarios (different tools, different bug types).

For our SKILL: maintain 3–5 curated examples in the SKILL body (or in `references/examples.md` and `@`-mentioned). Cover at minimum: a Bash-blocking hook, a `permissions.deny` rule (to demonstrate when to prefer it), and a `PostToolUse` formatter.

---

## 6. Temperature (note for completeness)

The API course covers temperature (0 = deterministic, 1 = creative). For deterministic tasks like syntax-validation, low temperature wins; for brainstorming hooks, higher is fine.

**Relevance to us in v1:** none — we run inside the user's Claude Code session and don't control the model's sampling parameters. Flagged only so we recognise it later if we ever move the analyzer to a dedicated Agent SDK call (architecture option B from the original brainstorm).

---

## 7. Connection to evals (preview)

The course emphasizes pairing prompt engineering with *measurement* — write a prompt, evaluate it against a dataset, iterate. We adopt that approach in a sibling doc: see `eval-methodology.md` for how we'll grade the SKILL's hook-generation quality so we know whether changes actually improve it.

The short version: don't change the SKILL "because it feels better." Run the eval, compare scores, decide.

---

## 8. Implications for `self-improving-claude`

1. **Skeleton of the SKILL.md.** The body uses the structure §4 implies: a brief directive opening, then the rubric (§3 guidelines), then the procedure (§3 process steps), then `<examples>`, then placeholders for the runtime-injected `<recent_chat>` / `<project_snapshot>` / `<telemetry_excerpt>` / `<existing_hooks>` / `<user_directive>`.
2. **The rubric is load-bearing.** Without explicit "what makes a good hook" criteria, the model defaults to plausible-looking but vague proposals. The rubric in §3 is a starter; evolve it via the eval loop.
3. **Examples cost tokens but earn quality.** Keep the example set tight (3–5), curate carefully, and explain *why* each example is good. Don't pad.
4. **Imperatives everywhere.** Every line of the SKILL body that asks Claude to do something should start with a verb. No "would it be a good idea to…" type phrasing.
5. **XML tags are not optional.** Even at small interpolation sizes, the discipline of always wrapping injected data makes the SKILL robust as it grows.
