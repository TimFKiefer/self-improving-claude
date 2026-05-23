# self-improving-claude v0.3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship v0.3.0 — the public-ready release. Marketplace install works, only three slash commands appear in `/` menu, orchestrator picks `permissions.ask` and PostToolUse hooks where appropriate (not just CLAUDE.md notes), telemetry captures four event types, `/improve-uninstall` cleanly removes the plugin's project footprint, baselines rerun to demonstrate quality delta.

**Architecture:** Repo becomes a single-plugin marketplace (`.claude-plugin/marketplace.json` at root, plugin assets in `plugin/` subdir). The model-invoked orchestrator content moves to a non-skill shared file (`plugin/skills/shared/procedure.md`) referenced by both entry skills, hiding it from the `/` menu. Custom Python scripts replaced where Claude Code already has built-ins: SessionEnd rotation is inline bash, uninstall is a slash command, multi-event telemetry shares one `telemetry.py` that branches on `hook_event_name`.

**Tech Stack:** Python 3 (stdlib only for shipped scripts; pytest + anthropic for dev), Markdown + YAML for skills, JSON for plugin/marketplace/hook configuration. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-22-self-improving-claude-v0.3-design.md` is authoritative. Refer to its §3 (architecture) and §7 (acceptance) whenever a step references a design decision.

**Working directory for every command:** `~/Desktop/Projects/self-improving-claude`

**Branching:** All work on a fresh branch `v0.3-implementation` from `main`. Merge back at the end.

---

## Task 1: Marketplace restructure (foundation — everything depends on this)

**Files:**
- Create: `.claude-plugin/marketplace.json`
- Move: existing `.claude-plugin/plugin.json` → `plugin/.claude-plugin/plugin.json`
- Move: existing `skills/` → `plugin/skills/`
- Move: existing `hooks/` → `plugin/hooks/`
- Move: existing `scripts/` → `plugin/scripts/`
- Modify: `evals/run.py` — update `SKILL_REFS` path constant
- Modify: `evals/tests/test_run.py` — test that the path resolves (if any tests reference it)

**Purpose:** Sets up the directory layout that makes `claude plugin marketplace add` and `claude plugin install` work. All later tasks operate on the new layout. After this task, `claude --plugin-dir <repo>/plugin` becomes the new quick-test path (was `<repo>` before).

- [ ] **Step 1: Create the v0.3 branch**

```bash
git checkout -b v0.3-implementation
git status
```
Expected: clean working tree, on v0.3-implementation branch.

- [ ] **Step 2: Move plugin assets into `plugin/` subdir**

```bash
mkdir -p plugin
git mv .claude-plugin plugin/.claude-plugin
git mv skills plugin/skills
git mv hooks plugin/hooks
git mv scripts plugin/scripts
git status
```

Expected: `git status` shows all files renamed under `plugin/`. No content changes yet.

- [ ] **Step 3: Create the marketplace manifest at repo root**

Create `.claude-plugin/marketplace.json` with this exact content:

```json
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "self-improving-claude",
  "description": "Marketplace for the self-improving-claude plugin — turns the bugs you just saw into the hooks that prevent the next ones.",
  "owner": {
    "name": "Tim Kiefer",
    "email": "tim.f.kief@gmail.com"
  },
  "plugins": [
    {
      "name": "self-improving-claude",
      "description": "Proactive and reactive guardrail proposals for your Claude Code projects, with per-proposal approval.",
      "author": {
        "name": "Tim Kiefer",
        "email": "tim.f.kief@gmail.com"
      },
      "category": "productivity",
      "source": "./plugin"
    }
  ]
}
```

- [ ] **Step 4: Validate the marketplace manifest**

```bash
claude plugin validate ~/Desktop/Projects/self-improving-claude
```

Expected: `✔ Validation passed` (validates BOTH `marketplace.json` AND the inner `plugin/.claude-plugin/plugin.json` automatically when run on a directory with both).

If validation fails on the marketplace manifest, fix the JSON (most likely cause: typo or schema mismatch). If validation passes only on the plugin (no marketplace recognized), the marketplace.json may need to be at a different path — check the validator's output message and adjust.

- [ ] **Step 5: Update the eval runner's path constant**

The eval runner at `evals/run.py` has a constant pointing at the orchestrator's references directory. After Task 1 the path is `plugin/skills/self-improving-claude/references/`. After Task 2 it becomes `plugin/skills/shared/references/`. Update for Task 1 first, Task 2 will update again.

Open `evals/run.py`. Find the line:

```python
SKILL_REFS = REPO_ROOT / "skills" / "self-improving-claude" / "references"
```

Replace with:

```python
SKILL_REFS = REPO_ROOT / "plugin" / "skills" / "self-improving-claude" / "references"
```

- [ ] **Step 6: Verify all tests still pass after the restructure**

```bash
python3 -m pytest -m "not integration" 2>&1 | tail -3
```
Expected: 55 passed, 1 deselected (same as before the restructure — the move didn't break anything).

- [ ] **Step 7: Verify the plugin still loads via --plugin-dir at the new path**

```bash
cd /tmp && claude --plugin-dir ~/Desktop/Projects/self-improving-claude/plugin --print "List all available slash commands. One name per line, plain text only." 2>&1 | grep -E "^(improve|improve-init|self-improving-claude)$"
```
Expected:
```
improve
improve-init
self-improving-claude
```
(Three names — the third one is the orchestrator that we'll hide in Task 2.)

- [ ] **Step 8: Commit**

```bash
git add .claude-plugin/marketplace.json evals/run.py
git commit -m "Restructure: plugin into ./plugin/ subdir + marketplace.json at root"
```

The git mv operations from Step 2 are already staged; this commit captures both the moves and the new marketplace.json + path fix.

---

## Task 2: Orchestrator hidden — shared/procedure.md probe + apply

**Files:**
- Probe: a temporary file pair to test `@../` resolution
- Move: `plugin/skills/self-improving-claude/SKILL.md` body content → `plugin/skills/shared/procedure.md`
- Move: `plugin/skills/self-improving-claude/references/*` → `plugin/skills/shared/references/*`
- Delete: `plugin/skills/self-improving-claude/` directory
- Modify: `plugin/skills/improve/SKILL.md` — `@`-reference shared procedure
- Modify: `plugin/skills/improve-init/SKILL.md` — `@`-reference shared procedure
- Modify: `evals/run.py` — update `SKILL_REFS` to new shared/references path

**Purpose:** Remove the orchestrator skill from the `/` menu. Tries the preferred approach (`@../shared/procedure.md`) and falls back to inline duplication only if the probe fails.

- [ ] **Step 1: Probe whether `@../` resolution works**

Create a probe skill at `plugin/skills/_probe/SKILL.md`:

```markdown
---
name: probe-at-mention
description: Throwaway test skill to verify @-mentions resolve outside the skill directory. Delete after the probe.
argument-hint: 
allowed-tools: [Read]
---

# Probe

@../_probe-target.md

End of probe body.
```

Create the probe target at `plugin/skills/_probe-target.md`:

```markdown
PROBE_MARKER_RESOLVED_OK
```

Then run from `/tmp`:

```bash
cd /tmp && claude --plugin-dir ~/Desktop/Projects/self-improving-claude/plugin --print "Invoke the probe-at-mention skill and tell me whether you can see the literal text PROBE_MARKER_RESOLVED_OK from inside its body." 2>&1 | head -30
```

Expected: the output mentions `PROBE_MARKER_RESOLVED_OK` (probe success) OR explicitly says the reference couldn't be resolved (probe failure).

Record the outcome:
- ✅ Probe SUCCESS → proceed with Step 2 (shared procedure file approach).
- ❌ Probe FAILURE → skip to Step 9 (inline duplication fallback).

- [ ] **Step 2: Clean up the probe**

```bash
rm -rf plugin/skills/_probe plugin/skills/_probe-target.md
```

- [ ] **Step 3: (Probe success path) Create the shared directory and move references**

```bash
mkdir -p plugin/skills/shared
git mv plugin/skills/self-improving-claude/references plugin/skills/shared/references
```

- [ ] **Step 4: Move the orchestrator body to shared/procedure.md**

The current `plugin/skills/self-improving-claude/SKILL.md` has YAML frontmatter + body. We want the body content (the 10-step procedure) extracted to `plugin/skills/shared/procedure.md` without the frontmatter.

Read `plugin/skills/self-improving-claude/SKILL.md`. Identify the body — everything AFTER the closing `---` of the frontmatter (line 5 onwards in the v0.1/v0.2 file).

Create `plugin/skills/shared/procedure.md` with EXACTLY the body content (no YAML frontmatter). The first line should be `# self-improving-claude — Orchestrator`.

Then delete the original:

```bash
rm -rf plugin/skills/self-improving-claude
```

- [ ] **Step 5: Update `improve/SKILL.md` to reference the shared procedure**

Read `plugin/skills/improve/SKILL.md`. Find the body — after frontmatter. It currently invokes the orchestrator via the Skill tool. Replace the body so it sets the mode and `@`-mentions the shared procedure directly:

Replace the body (everything after the closing `---`) with:

```markdown

# /improve — Reactive Guardrail Proposal

You — invoked via the `/improve` slash command — are running the orchestrator workflow in REACTIVE mode. The current conversation is your primary signal — review the recent messages above for the problem the user wants prevented.

## Inputs

<mode>reactive</mode>
<user_directive>$ARGUMENTS</user_directive>

Gather these inputs before running the procedure:

- **`<recent_chat>`** — the most recent ~30 messages of this conversation (already in your context).
- **`<project_snapshot>`** — supplemental in reactive mode. Read CLAUDE.md, manifests, README, sampled source files only if recent chat is thin (≤ 5KB cap).
- **`<telemetry_excerpt>`** — supplemental. Most recent ~50 rows from `.claude/self-improving-claude/telemetry.jsonl` if it exists.
- **`<transcript_excerpt>`** — empty for reactive mode.
- **`<existing_hooks>`** — the `hooks` block from `.claude/settings.json` (empty `{}` if file missing).
- **`<existing_permissions>`** — the `permissions` block from `.claude/settings.json` (empty `{}` if file missing).

If `.claude/settings.json` won't parse, stop and tell the user — do not run the procedure with broken state.

## Procedure to follow

@../shared/procedure.md

## References used by the procedure

@../shared/references/prompt-rubric.md
@../shared/references/hook-patterns.md
@../shared/references/tools-reference.md
@../shared/references/settings-merge.md
@../shared/references/examples.md
```

- [ ] **Step 6: Update `improve-init/SKILL.md` to reference the shared procedure**

Same shape, mode=proactive. Replace the body of `plugin/skills/improve-init/SKILL.md` with:

```markdown

# /improve-init — Proactive Guardrail Scan

You — invoked via the `/improve-init` slash command — are running the orchestrator workflow in PROACTIVE mode. Project code and accumulated telemetry are your primary signals.

## Inputs

<mode>proactive</mode>
<user_directive>$ARGUMENTS</user_directive>

Gather these inputs before running the procedure:

- **`<user_directive>`** — the literal contents of `$ARGUMENTS`, or empty string.
- **`<project_snapshot>`** — a sampled, *trimmed* view of the project: `CLAUDE.md` if it exists, manifest files (package.json / pyproject.toml / Cargo.toml), `README.md` first 80 lines, a handful of representative source files. Cap ~5-8 KB total.
- **`<telemetry_excerpt>`** — most recent ~200 rows from `.claude/self-improving-claude/telemetry.jsonl` if it exists. Empty if missing.
- **`<transcript_excerpt>`** — past-session transcripts at `~/.claude/projects/<project-path>/*.jsonl`. Sample ~30 behaviorally interesting rows.
- **`<existing_hooks>`** — the `hooks` block from `.claude/settings.json` (empty `{}` if file missing).
- **`<existing_permissions>`** — the `permissions` block from `.claude/settings.json` (empty `{}` if file missing).

If `.claude/settings.json` won't parse, stop and tell the user.

## Procedure to follow

@../shared/procedure.md

## References used by the procedure

@../shared/references/prompt-rubric.md
@../shared/references/hook-patterns.md
@../shared/references/tools-reference.md
@../shared/references/settings-merge.md
@../shared/references/examples.md
```

- [ ] **Step 7: Update `evals/run.py` to point at shared references**

Open `evals/run.py`. Find:

```python
SKILL_REFS = REPO_ROOT / "plugin" / "skills" / "self-improving-claude" / "references"
```

Replace with:

```python
SKILL_REFS = REPO_ROOT / "plugin" / "skills" / "shared" / "references"
```

- [ ] **Step 8: Verify the / menu shows only the two intended skills**

```bash
cd /tmp && claude --plugin-dir ~/Desktop/Projects/self-improving-claude/plugin --print "List all available slash commands. One name per line, plain text only." 2>&1 | grep -E "^(improve|improve-init|self-improving-claude)$"
```

Expected:
```
improve
improve-init
```

The `self-improving-claude` line should be GONE. If it still appears, the orchestrator skill wasn't fully removed — recheck Step 4's `rm -rf`.

Then skip to Step 11 (verify tests + commit).

- [ ] **Step 9: (Probe failure path) Inline duplication fallback**

If Step 1's probe showed that `@../` resolution does NOT work, we inline the procedure into each entry skill instead.

Read `plugin/skills/self-improving-claude/SKILL.md`. Note the body content (the 10-step procedure).

Update `plugin/skills/improve/SKILL.md`: replace its body with:
- The reactive-mode preamble (mode, inputs, gather-inputs section)
- THEN the FULL 10-step procedure body, INLINED
- Inside the procedure, the `@`-mentions to references stay as-is BUT use relative paths inside the skill directory (move references into each entry skill's directory first):

```bash
cp -r plugin/skills/self-improving-claude/references plugin/skills/improve/references
cp -r plugin/skills/self-improving-claude/references plugin/skills/improve-init/references
```

Update the entry skills' `@`-mentions to point at their LOCAL references directory (e.g. `@references/prompt-rubric.md` not `@../shared/references/prompt-rubric.md`).

Delete the orchestrator directory:

```bash
rm -rf plugin/skills/self-improving-claude
```

Note this fallback in CHANGELOG (Task 10).

- [ ] **Step 10: Update `evals/run.py` for the fallback path**

If you took the inline path in Step 9, the references no longer live in a shared location. The eval runner needs ONE canonical path. Update `evals/run.py`:

```python
SKILL_REFS = REPO_ROOT / "plugin" / "skills" / "improve" / "references"
```

(Picks one of the duplicated copies; the runner only needs to read references for prompt assembly.)

- [ ] **Step 11: Verify tests still pass**

```bash
python3 -m pytest -m "not integration" 2>&1 | tail -3
```
Expected: 55 passed, 1 deselected.

If the eval runner tests fail, the path resolution in run.py is wrong. Check that `SKILL_REFS` resolves to a real directory containing all 5 reference markdown files.

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "Hide orchestrator from / menu — shared/procedure.md (or inline if probe failed)"
```

---

## Task 3: Form-selection fix — 5-form ladder

**Files:**
- Modify: `plugin/skills/shared/references/prompt-rubric.md` — rewrite criterion #2
- Modify: `plugin/skills/shared/procedure.md` — rewrite Step 4

**Purpose:** Encode the form-selection fix per spec §3.4. Adds `permissions.ask` as the 5th form between `deny` and prompt-hook. Tightens "Lightest viable form" to emphasize *viable*. Makes PostToolUse command-hook an explicit consideration.

(If Task 2 took the inline fallback path, both edits below apply to TWO files each — once in `plugin/skills/improve/...` and once in `plugin/skills/improve-init/...`. For clarity, the steps below show one path; do them in both places if needed.)

- [ ] **Step 1: Rewrite rubric criterion #2 in `prompt-rubric.md`**

Open `plugin/skills/shared/references/prompt-rubric.md`. Find criterion #2 (currently starts with "**Lightest viable form.**"). Replace it with:

```markdown
2. **Lightest *viable* form.** The chosen form must actually enforce the rule. CLAUDE.md notes are NOT viable for rules of shape "before X do Y" or "after X show Y" — these need a hook (Pre/PostToolUse) or a `permissions` rule. A CLAUDE.md note that relies on the model remembering is not viable for any recurring failure mode. Use one of the lighter enforceable forms (`permissions.deny`, `permissions.ask`, prompt-hook, command-hook) unless the rule is purely a stylistic preference with no enforcement need. The rationale states *why* a lighter form wouldn't work, if you didn't use one.
```

- [ ] **Step 2: Rewrite Step 4 in `procedure.md`**

Open `plugin/skills/shared/procedure.md`. Find the `## Step 4 — Choose the lightest form that does the job` section. Replace the entire section (heading + body up to but not including `## Step 5`) with:

```markdown
## Step 4 — Choose the lightest form that does the job

For each candidate, consider these forms in order. Use the FIRST one that's *viable* for this rule:

1. **`permissions.deny`** — if a glob covers the action uniformly across tools AND it should be unconditionally blocked. Cheapest: no model call, no script, no user interaction.

2. **`permissions.ask`** — if a glob covers the action AND the user is sometimes OK with it but wants to be the one to decide. Examples: `Bash(git push:*)`, `Bash(rm -rf:*)`, `Bash(npm publish:*)`. Built-in Claude Code prompts the user; we don't write any script or hook. Lighter than a prompt-hook because no LLM evaluation — the user decides directly. **This form is often missed** — use it whenever "warn and let me confirm" is the right semantic, not just "block."

3. **Prompt-based hook** (`"type": "prompt"`) — if pre-condition *reasoning* is needed (recognizing intent across novel input shapes that globs can't express) AND the event supports prompt hooks (PreToolUse, Stop, SubagentStop, UserPromptSubmit).

4. **Command-hook on PreToolUse** — if the check is fast and deterministic and must BLOCK the tool call.

5. **Command-hook on PostToolUse** — if the check needs to SURFACE context (grep results, formatter output, type errors) back to Claude AFTER an action. Often the right answer for "after editing X, show Y." Cheap, deterministic, no model call. Don't skip this form when reasoning about hooks — it's frequently the right answer for "feed information back" rules.

6. **Last resort: `CLAUDE.md` note** — only for taste-level preferences with zero enforcement need (e.g. "prefer pnpm over npm"). Never for ordering rules ("before X do Y") or context-surfacing rules ("after X show Y") — those need an enforceable form.

Prefer the lighter form when both would work. Lighter means cheaper to run, easier to audit, less code to maintain. But don't strain to make a glob fit a rule that genuinely needs logic — the priority is a guide, not an algorithm.

If you're genuinely on the fence between two forms for the same candidate (typically `permissions.deny` vs. `permissions.ask`, OR `permissions.ask` vs. prompt-hook, OR prompt-hook vs. command-hook), use `AskUserQuestion` to let the user pick — they know whether they'd rather have a stricter rule or a smarter one.
```

- [ ] **Step 3: Verify both files are well-formed**

```bash
for f in plugin/skills/shared/references/prompt-rubric.md plugin/skills/shared/procedure.md; do
  fences=$(grep -c '^```' "$f")
  echo "$f: $fences fences"
  test $((fences % 2)) -eq 0 || echo "UNBALANCED FENCES IN $f"
done
```
Expected: both files report even fence counts.

- [ ] **Step 4: Verify the procedure still has 10 numbered steps**

```bash
grep -c '^## Step ' plugin/skills/shared/procedure.md
```
Expected: `10` — Step 1 through Step 10 unchanged in count.

- [ ] **Step 5: Commit**

```bash
git add plugin/skills/shared/references/prompt-rubric.md plugin/skills/shared/procedure.md
git commit -m "Form-selection: 5-form ladder including permissions.ask, PostToolUse explicit"
```

---

## Task 4: Two new worked examples

**Files:**
- Modify: `plugin/skills/shared/references/examples.md` — add Example 4 (`grep-export-callers` PostToolUse) and Example 5 (`permissions.ask` for git push); rewrite Example 3 (prompt-hook for git push) to clarify when prompt-hook is the right answer

**Purpose:** Adds concrete examples for the two forms that were under-used in v0.2 (PostToolUse command-hook and `permissions.ask`). Both forms were missed in the dogfooding session — examples force them into the orchestrator's mental model.

- [ ] **Step 1: Read the existing examples.md to find the right insertion points**

```bash
grep -n '^## Example' plugin/skills/shared/references/examples.md
```
Expected output (line numbers will vary):
```
N: ## Example 1 — `permissions.deny` ...
M: ## Example 2 — Command hook ...
O: ## Example 3 — Prompt hook ...
```

We'll append Example 4 and Example 5 at the end of the file. Example 3 also gets its rationale tightened.

- [ ] **Step 2: Append Example 4 — `grep-export-callers` PostToolUse command-hook**

Open `plugin/skills/shared/references/examples.md`. After the last line (after Example 3's "Why it's good" section), append:

````markdown

---

## Example 4 — Command hook on PostToolUse (surface context after action)

### Observed problem

> The user just changed an exported identifier's value (`export const X = 'old'` → `export const X = 'new'`) and several hardcoded callers across the codebase broke silently because the rename wasn't grepped first. A guardrail should surface all callers of an exported identifier whenever that identifier's definition line is edited.

### Proposal

**Form:** Command hook (`"type": "command"`)
**Event:** `PostToolUse` (non-blocking — runs AFTER the edit, feeds context back via stderr)
**Matcher:** `Edit|MultiEdit`
**Script:** `.claude/hooks/grep-export-callers.py`

```python
#!/usr/bin/env python3
"""After Edit/MultiEdit on a line that defines an exported identifier, grep
for callers and feed the list back to Claude so it can verify consistency."""
import json, re, subprocess, sys

EXPORT_DEF = re.compile(
    r"export\s+(?:const|let|var|function|class|type|interface|enum)\s+(\w+)"
)

def main():
    try:
        ev = json.load(sys.stdin)
    except Exception:
        return 0
    if ev.get("tool_name") not in ("Edit", "MultiEdit"):
        return 0
    inp = ev.get("tool_input") or {}
    edits = inp.get("edits") or [
        {"old_string": inp.get("old_string", ""), "new_string": inp.get("new_string", "")}
    ]

    names: set[str] = set()
    for e in edits:
        for s in (e.get("old_string", ""), e.get("new_string", "")):
            m = EXPORT_DEF.search(s)
            if m:
                names.add(m.group(1))

    if not names:
        return 0

    for name in names:
        try:
            r = subprocess.run(
                ["grep", "-rn", "--include=*.ts", "--include=*.tsx",
                 "--include=*.js", "--include=*.jsx", name, "."],
                capture_output=True, text=True, timeout=5,
            )
            hits = [l for l in r.stdout.splitlines() if l][:20]
            if hits:
                print(f"Export `{name}` touched. References still in tree:", file=sys.stderr)
                for h in hits:
                    print(f"  {h}", file=sys.stderr)
                print("Verify these are consistent with your change.", file=sys.stderr)
                return 2
        except Exception:
            pass
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

**Settings.json delta:**

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|MultiEdit",
        "hooks": [
          {
            "name": "self-improving-claude/grep-export-callers",
            "type": "command",
            "command": "python3 ${CLAUDE_PROJECT_DIR}/.claude/hooks/grep-export-callers.py",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

**Rationale:** *Surfaces all callers after any Edit that touches an exported identifier definition; closes the failure mode where a rename lands without enumerating hardcoded usages. PostToolUse + grep is cheaper than a prompt hook and works on every Edit (not just renames the model recognizes ahead of time).*

### Why it's good

The proposal *picked PostToolUse command-hook over CLAUDE.md note* because the rule is "after editing X, show Y" — a context-surfacing rule that the orchestrator must enforce, not a taste-level preference. The script uses defensive `.get(...)`, exits 2 with stderr so Claude sees the grep results as feedback, stays under 60 LOC, carries the sentinel `name`, and runs only when an export-definition line is detected (no noise on unrelated edits).

---

## Example 5 — `permissions.ask` (when the user should decide each time)

### Observed problem

> The user noted that Claude sometimes wants to `git push` from inside the agent. Pushes to feature branches are usually fine, but pushes to `main` (especially `--force`) should always require explicit human confirmation. A blanket deny is too strict; a CLAUDE.md note is too lax; a prompt-hook would work but pays an LLM-call cost when a simpler form does the job.

### Proposal

**Form:** `permissions.ask` rule
**Event:** N/A (permissions apply uniformly across tools)
**Settings.json delta:**

```json
{
  "permissions": {
    "ask": [
      "Bash(git push:*)"
    ]
  }
}
```

**Rationale:** *Causes Claude Code to prompt the user for confirmation on every `git push` invocation regardless of arguments; no model call, no script, no hook latency — built-in Claude Code asks the user directly. Cheaper than a prompt-hook because the user's call is all the reasoning needed.*

### Why it's good

The proposal *ruled out the lighter form* (`permissions.deny` would block legitimate pushes), *ruled out the heavier form* (prompt-hook would do the same job but with an LLM evaluation per push). `permissions.ask` is the right semantic: "I want to be the one to decide." Built-in Claude Code handles the prompt; we don't author any code. One line, deterministic, exactly the right weight.
````

- [ ] **Step 3: Tighten Example 3's rationale to clarify when prompt-hook IS appropriate**

Find Example 3's "Why it's good" section in `plugin/skills/shared/references/examples.md`. Replace it with:

```markdown
### Why it's good

The proposal *picked prompt-hook over command-hook* because the check needs reasoning about `git push` invocation shape (origin name, branch, force flag combinations) that a regex would miss. Stays focused: one event, one matcher, prompt under 5 sentences. Sentinel name present.

**Note:** in many cases a simpler `permissions.ask` rule (see Example 5) does the same job without any LLM evaluation. Prefer `permissions.ask` when "just ask the user every time" suffices; reach for prompt-hooks only when there's a meaningful classification the model can do that a glob can't (e.g. "block force-pushes to main but allow regular pushes to feature branches").
```

- [ ] **Step 4: Verify examples.md is well-formed**

```bash
f=plugin/skills/shared/references/examples.md
fences=$(grep -c '^```' "$f")
echo "fences: $fences (must be even)"
examples=$(grep -c '^## Example ' "$f")
echo "examples: $examples (expected 5)"
test $((fences % 2)) -eq 0 || echo "UNBALANCED FENCES"
```

Expected: even fence count; 5 examples.

- [ ] **Step 5: Commit**

```bash
git add plugin/skills/shared/references/examples.md
git commit -m "examples.md: add Example 4 (PostToolUse grep) and Example 5 (permissions.ask)"
```

---

## Task 5: Multi-event telemetry

**Files:**
- Modify: `plugin/hooks/hooks.json` — add Notification, PreCompact, SessionStart matchers + inline-bash SessionEnd rotation
- Modify: `plugin/scripts/telemetry.py` — branch on `hook_event_name`
- Modify: `plugin/scripts/tests/test_telemetry.py` — add tests for new event types

**Purpose:** Per spec §3.5, telemetry hook listens on four event types (was only PostToolUse), capturing richer signal for `/improve-init` to mine. SessionEnd rotation uses inline bash (no Python script) to keep telemetry log size bounded per session.

- [ ] **Step 1: Write the failing tests for new event types**

Open `plugin/scripts/tests/test_telemetry.py`. Add these tests at the end of the file:

```python
def test_notification_event_logged(tmp_path):
    payload = {
        "hook_event_name": "Notification",
        "session_id": "abc",
        "cwd": str(tmp_path),
    }
    row = run_telemetry(payload, tmp_path)
    assert row["event"] == "notification"
    assert "ts" in row


def test_precompact_event_logged(tmp_path):
    payload = {
        "hook_event_name": "PreCompact",
        "session_id": "abc",
        "cwd": str(tmp_path),
    }
    row = run_telemetry(payload, tmp_path)
    assert row["event"] == "compact"
    assert "ts" in row


def test_sessionstart_event_logged(tmp_path):
    payload = {
        "hook_event_name": "SessionStart",
        "session_id": "abc",
        "cwd": str(tmp_path),
    }
    row = run_telemetry(payload, tmp_path)
    assert row["event"] == "session_start"
    assert "ts" in row


def test_existing_posttooluse_event_still_tagged(tmp_path):
    """Existing PostToolUse payloads should now carry event='tool' field too."""
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
        "tool_response": {"exit_code": 0},
    }
    row = run_telemetry(payload, tmp_path)
    assert row["event"] == "tool"
    assert row["tool"] == "Bash"
    assert row["args_summary"] == "ls"


def test_unknown_event_silently_ignored(tmp_path):
    """Unknown hook events should not crash, just write a minimal marker row."""
    payload = {
        "hook_event_name": "SomeFutureEvent",
        "session_id": "abc",
    }
    row = run_telemetry(payload, tmp_path)
    assert row["event"] == "other"
    assert "ts" in row
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest plugin/scripts/tests/test_telemetry.py::test_notification_event_logged -v
```
Expected: FAIL — `row["event"]` raises KeyError or assertion fails (current telemetry.py doesn't write an `event` field for these).

- [ ] **Step 3: Extend telemetry.py to branch on hook_event_name**

Open `plugin/scripts/telemetry.py`. The current `summarize()` function only handles tool-call events. Modify it to branch on the `hook_event_name`:

Replace the current `summarize(event)` function body (the entire function) with:

```python
def summarize(event: dict) -> dict:
    """Convert a raw hook event into a JSONL row honoring spec §3.4 redaction rules.

    Branches on hook_event_name to emit different row shapes for tool calls,
    notifications, compactions, and session boundaries. Unknown events get a
    minimal marker row.
    """
    hook_event = event.get("hook_event_name", "")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if hook_event == "PostToolUse":
        return _summarize_tool(event, ts)
    if hook_event == "Notification":
        return {"ts": ts, "event": "notification"}
    if hook_event == "PreCompact":
        return {"ts": ts, "event": "compact"}
    if hook_event == "SessionStart":
        return {"ts": ts, "event": "session_start"}

    return {"ts": ts, "event": "other"}


def _summarize_tool(event: dict, ts: str) -> dict:
    """Summarize a PostToolUse event with per-tool redaction (spec §3.4)."""
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    tool_response = event.get("tool_response") or {}

    row: dict = {
        "ts": ts,
        "event": "tool",
        "tool": tool,
    }

    if tool == "Bash":
        cmd = (tool_input.get("command") or "")[:80]
        row["args_summary"] = cmd
        exit_code = tool_response.get("exit_code", 0)
        outcome: dict = {"exit_code": exit_code}
        if exit_code != 0:
            stderr = (tool_response.get("stderr") or "")[:200]
            outcome["stderr_head"] = stderr
        row["outcome"] = outcome
    elif tool in ("Read", "Write", "Edit", "MultiEdit"):
        row["args_summary"] = tool_input.get("file_path", "")
    elif tool in ("Glob", "Grep"):
        pattern = tool_input.get("pattern", "") or ""
        if SECRET_PATTERN_RE.search(pattern):
            row["args_summary"] = "<redacted-secret-pattern>"
        else:
            row["args_summary"] = pattern
    elif tool == "WebFetch":
        url = tool_input.get("url", "") or ""
        try:
            row["args_summary"] = urlparse(url).hostname or ""
        except Exception:
            row["args_summary"] = ""
    elif tool == "Task":
        row["args_summary"] = tool_input.get("subagent_type", "")
    elif tool == "TodoWrite":
        todos = tool_input.get("todos") or []
        row["args_summary"] = f"{len(todos)} todos"

    return row
```

- [ ] **Step 4: Update all existing tests that don't yet check `event` field**

Existing v0.1+v0.2 tests assert on `row["tool"]`, `row["args_summary"]`, etc. but don't check `row["event"]`. We added `event="tool"` to the tool-call branch — these tests will still pass because they don't check absence of `event`. But the test `test_unknown_tool_logs_name_and_ts_only` may need a tweak.

Open `plugin/scripts/tests/test_telemetry.py`. Find `test_unknown_tool_logs_name_and_ts_only`. Update it to also confirm the new `event` field:

```python
def test_unknown_tool_logs_name_and_ts_only(tmp_path):
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "SomeMcpTool",
        "tool_input": {"anything": "goes here"},
    }
    row = run_telemetry(payload, tmp_path)
    assert row["tool"] == "SomeMcpTool"
    assert row["event"] == "tool"
    assert "args_summary" not in row
```

(The change: added `hook_event_name` to payload, added `event` assertion.)

Other existing tests that DON'T pass `hook_event_name` in their payload will now fall through to the "other" branch and not get tool-call summarization. So we need to make sure all tool-call tests include `hook_event_name: "PostToolUse"`.

Find each of these tests and add `"hook_event_name": "PostToolUse",` to the payload dict:

- `test_bash_logs_summary_with_exit_code`
- `test_bash_truncates_long_command_to_80_chars`
- `test_bash_truncates_stderr_to_200_chars`
- `test_bash_omits_stderr_on_success`
- `test_read_logs_path_only_not_content`
- `test_write_logs_path_only`
- `test_edit_logs_path_only`
- `test_grep_logs_pattern`
- `test_grep_redacts_secret_pattern`
- `test_glob_logs_pattern`
- `test_webfetch_logs_host_only_strips_query`
- `test_task_logs_subagent_type_only`
- `test_todowrite_logs_count_only`
- `test_creates_parent_directory_if_missing`
- `test_appends_not_overwrites` (both payloads)
- `test_multiedit_logs_path_only`
- `test_grep_redacts_token_pattern`
- `test_grep_does_not_redact_substring_match`

Use sed (one-shot, safer than 18 manual edits):

```bash
# Add hook_event_name to all payloads that have tool_name but no hook_event_name yet
python3 <<'PY'
from pathlib import Path
import re
p = Path("plugin/scripts/tests/test_telemetry.py")
src = p.read_text()
# In any payload dict that contains "tool_name" but not "hook_event_name", insert hook_event_name as the first key
def fix(match):
    body = match.group(0)
    if '"hook_event_name"' in body:
        return body
    return body.replace('"tool_name":', '"hook_event_name": "PostToolUse",\n        "tool_name":', 1)
# Match payload = {...} blocks
new = re.sub(r'payload = \{[^}]*"tool_name":[^}]*\}', fix, src, flags=re.DOTALL)
p.write_text(new)
print("Patched.")
PY
```

Verify the patch landed correctly:

```bash
grep -c '"hook_event_name"' plugin/scripts/tests/test_telemetry.py
```
Expected: at least 22 occurrences (18+ existing payloads + 5 new tests + the appends-not-overwrites two payloads).

- [ ] **Step 5: Run all tests to verify they pass**

```bash
python3 -m pytest plugin/scripts/tests/test_telemetry.py -v
```
Expected: all tests pass (27 total: 22 original + 5 new).

If any test still fails, the most likely cause is a payload that didn't get `hook_event_name` patched. Find it and add `"hook_event_name": "PostToolUse",` manually.

- [ ] **Step 6: Update `hooks/hooks.json` to register on multiple events**

Open `plugin/hooks/hooks.json`. Replace its entire content with:

```json
{
  "description": "self-improving-claude — multi-event telemetry + SessionEnd rotation",
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "name": "self-improving-claude/telemetry",
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/telemetry.py",
            "timeout": 5
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "*",
        "hooks": [
          {
            "name": "self-improving-claude/telemetry-notification",
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/telemetry.py",
            "timeout": 5
          }
        ]
      }
    ],
    "PreCompact": [
      {
        "matcher": "*",
        "hooks": [
          {
            "name": "self-improving-claude/telemetry-precompact",
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/telemetry.py",
            "timeout": 5
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          {
            "name": "self-improving-claude/telemetry-sessionstart",
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/telemetry.py",
            "timeout": 5
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "*",
        "hooks": [
          {
            "name": "self-improving-claude/rotate-telemetry",
            "type": "command",
            "command": "f=\"${CLAUDE_PROJECT_DIR}/.claude/self-improving-claude/telemetry.jsonl\"; [ -f \"$f\" ] && mv \"$f\" \"${f%.jsonl}.$(date +%Y%m%d-%H%M%S).jsonl\" && touch \"$f\" || true",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 7: Validate the hooks.json**

```bash
python3 -c "import json; json.load(open('plugin/hooks/hooks.json')); print('hooks.json OK')"
claude plugin validate ~/Desktop/Projects/self-improving-claude
```
Expected: both report success.

- [ ] **Step 8: Commit**

```bash
git add plugin/hooks/hooks.json plugin/scripts/telemetry.py plugin/scripts/tests/test_telemetry.py
git commit -m "Multi-event telemetry (PostToolUse + Notification + PreCompact + SessionStart) + inline-bash SessionEnd rotation"
```

---

## Task 6: `/improve-uninstall` slash command

**Files:**
- Create: `plugin/skills/improve-uninstall/SKILL.md`

**Purpose:** New user-invoked skill that cleans up the plugin's project-level footprint. Replaces the `scripts/uninstall.py` from the earlier design draft — uses Claude Code's skill mechanism instead of a terminal command. Three slash commands total after this task (`/improve`, `/improve-init`, `/improve-uninstall`).

- [ ] **Step 1: Create the directory and the skill file**

```bash
mkdir -p plugin/skills/improve-uninstall
```

Create `plugin/skills/improve-uninstall/SKILL.md` with EXACTLY this content:

```markdown
---
name: improve-uninstall
description: Run /improve-uninstall to cleanly remove self-improving-claude's footprint from THIS project — sentinel hooks in settings.json, generated scripts in .claude/hooks/, optionally the local telemetry log. The plugin itself stays installed; use `claude plugin uninstall self-improving-claude` for that.
argument-hint: [optional --dry-run to preview without changing files]
allowed-tools: [Read, Edit, Bash, AskUserQuestion]
---

# /improve-uninstall — Project Footprint Cleanup

You — invoked via `/improve-uninstall` — remove the plugin's footprint from THIS project. You do NOT uninstall the plugin itself; that's `claude plugin uninstall self-improving-claude`. You touch only files inside this project.

**Important:** if `$ARGUMENTS` is `--dry-run`, do NOT modify any files. Walk through Steps 1–4 read-only and present what WOULD be removed.

## Step 1 — Inspect

Read `.claude/settings.json` (in the current project's `.claude/` directory — use `${CLAUDE_PROJECT_DIR}/.claude/settings.json` or just `.claude/settings.json` relative to cwd).

If the file does not exist: nothing to clean up. Tell the user and exit.

If the file exists but fails to parse as JSON: do NOT proceed. Show the user the parse error and the file path, ask them to fix it manually first.

## Step 2 — Enumerate

From the parsed settings.json, collect:

**Plugin-installed hook entries.** Walk each `hooks.<EventName>` array. For each entry, look at its `hooks: [...]` sub-array. Collect entries whose `name` starts with `self-improving-claude/`.

**Plugin-installed permission rules.** Walk `permissions.deny`, `permissions.ask`, `permissions.allow`. These don't carry sentinels (it's just strings), so use a best-effort heuristic: collect rules that are documented in our examples (e.g. `Read(**/.env)`, `Edit(src/generated/prisma/**)`) — but mark them as "best-effort match" in the summary, so the user can confirm or override.

**Generated hook scripts.** Walk `.claude/hooks/` directory. Collect files whose names correspond to sentinel slugs we found in the hook entries above (e.g. if there's a hook entry with `name: "self-improving-claude/block-pnpm-test-watcher"`, look for `.claude/hooks/block-pnpm-test-watcher.{py,sh,js}`).

**Telemetry artifacts.** Note `.claude/self-improving-claude/` directory existence (telemetry log, archives, feedback.jsonl).

## Step 3 — Confirm with the user

Use `AskUserQuestion` to summarize what was found and ask the user how to proceed. Frame the summary concretely:

> Found:
> - N plugin-installed hook entries in settings.json
> - M generated hook scripts in .claude/hooks/
> - K possibly-plugin-installed permission rules (best-effort match — please review)
> - Telemetry directory `.claude/self-improving-claude/` (X files, Y bytes)

Options:
- **Confirm all** — remove the hook entries, delete the scripts, also clear the telemetry directory
- **Confirm hooks only** — remove hook entries + delete scripts, KEEP the telemetry directory
- **Dry-run preview** — show the exact changes that would be made to settings.json (don't modify the file)
- **Abort** — do nothing

If the user passed `--dry-run` as $ARGUMENTS in the original invocation, treat the choice as "Dry-run preview" automatically — show what would change without writing.

## Step 4 — Remove

For **non-dry-run paths only:**

- **Hook entries:** for each plugin-installed entry, remove it from its array in settings.json. Preserve all other entries. Use the same defensive merge discipline as `@../shared/references/settings-merge.md` — read, parse, modify in-memory, write atomically (write to `.tmp`, then rename). Reparse after to confirm the write produced valid JSON; if not, restore the pre-write content.
- **Permission rules:** ONLY remove rules the user explicitly confirmed in Step 3 (don't auto-remove "best-effort match" entries without user sign-off).
- **Generated scripts:** delete `.claude/hooks/<slug>.py` (or `.sh`, `.js`) for each matched script. Use `Bash` with `rm -- <path>`.
- **Telemetry directory:** if the user chose "Confirm all", `rm -rf .claude/self-improving-claude/` (use `Bash`).

After all removals, re-read settings.json one more time. If it doesn't parse, restore from the pre-write content and tell the user something went wrong.

## Step 5 — Report

End with a short summary:
- N hook entries removed (or "would be removed" in dry-run)
- M scripts deleted (or "would be deleted")
- K permission rules removed (or 0 if user declined)
- Telemetry directory: kept / cleared / would be cleared

Then remind the user:

> The plugin itself is still installed. To remove the plugin entirely, run:
> `claude plugin uninstall self-improving-claude`
>
> If you want to reinstall later: `claude plugin install self-improving-claude` from the same marketplace.
```

- [ ] **Step 2: Verify frontmatter and structure**

```bash
f=plugin/skills/improve-uninstall/SKILL.md
head -6 "$f"
fences=$(grep -c '^```' "$f")
echo "fence count: $fences"
test $((fences % 2)) -eq 0 && echo OK || echo "UNBALANCED FENCES"
```

Expected: frontmatter has `name: improve-uninstall`, `argument-hint:`, `allowed-tools: [Read, Edit, Bash, AskUserQuestion]`; even fence count; OK.

- [ ] **Step 3: Verify the / menu now shows three commands**

```bash
cd /tmp && claude --plugin-dir ~/Desktop/Projects/self-improving-claude/plugin --print "List all available slash commands. One name per line, plain text only." 2>&1 | grep -E "^(improve|improve-init|improve-uninstall|self-improving-claude)$"
```

Expected output (order may vary):
```
improve
improve-init
improve-uninstall
```

(Three names; `self-improving-claude` should NOT appear — it was hidden in Task 2.)

- [ ] **Step 4: Commit**

```bash
git add plugin/skills/improve-uninstall/SKILL.md
git commit -m "Add /improve-uninstall slash command (clean project footprint)"
```

---

## Task 7: Feedback channel formalized

**Files:**
- Modify: `plugin/skills/shared/procedure.md` — Step 1 routing extended (feedback mode writes to feedback.jsonl AND modifies target hook)
- Modify: `plugin/skills/shared/references/settings-merge.md` — document feedback.jsonl schema

**Purpose:** Per spec §3.6, formalize the feedback channel that v0.2's orchestrator routed only at the chat level. Now feedback gets persistently logged at `.claude/self-improving-claude/feedback.jsonl`, and the target hook is modified (narrowed / exception added) rather than just discussed.

- [ ] **Step 1: Extend procedure.md Step 1 routing**

Open `plugin/skills/shared/procedure.md`. Find `## Step 1 — Read the room`. Replace its body (keeping the heading) with:

```markdown
## Step 1 — Read the room

Read `<user_directive>` and classify the request. The four shapes that matter:

- **default (empty)** — propose proactively from the available signals.
- **directive** ("add a rule that prevents X") — propose specifically against X.
- **feedback** ("the foo-hook just blocked something legit", "X is too broad", "narrow Y", "Z misses Q") — refine an existing entry rather than adding new ones. Persist the feedback for future runs.
- **inquiry** — any other free-text — treat as a description of an observed problem the user wants prevented.

If the directive sits genuinely between two of these (e.g. could be a directive OR a feedback note about an existing hook), use `AskUserQuestion` to clarify before going further. Otherwise classify and continue.

### Feedback-mode handling (when classified as feedback)

When the user gives feedback about an existing hook:

1. **Identify the target.** Match by sentinel name (`self-improving-claude/<slug>`) referenced in the user's message. If the user didn't name the hook, use `AskUserQuestion` to pick from the list in `<existing_hooks>`.

2. **Persist the feedback.** Append a row to `${CLAUDE_PROJECT_DIR}/.claude/self-improving-claude/feedback.jsonl`:

   ```jsonl
   {"ts":"<ISO-8601 UTC>","target":"self-improving-claude/<slug>","mode":"<too-broad|false-positive|please-narrow|missed-case>","complaint":"<user's verbatim text>","resolution":"<one-sentence description of what you did>"}
   ```

   Create the parent directory if missing. Append, never overwrite. Each row on its own line.

3. **Modify the target hook.** Based on the complaint mode:
   - `too-broad` / `false-positive` — narrow the matcher (e.g. tighten `Bash` to `Bash(npm publish:*)` if the complaint is about npm publish), or add an explicit exception in the hook script body (return 0 early on the legit case the user named).
   - `please-narrow` — same as above, prompt user for the specific narrowing if not obvious from their message.
   - `missed-case` — broaden the matcher OR add a sibling check to cover the missed case.

4. **Use the same defensive settings.json merge** as proposed hooks (see `@references/settings-merge.md`). Modify in place; never duplicate entries.

5. **Do NOT propose new hooks** in feedback mode. Confirm the change with the user and exit (skip Steps 3-9 of this procedure).

6. **In Step 10 (close-out)**, summarize what was changed and link to the feedback.jsonl line.
```

- [ ] **Step 2: Document the feedback.jsonl schema in settings-merge.md**

Open `plugin/skills/shared/references/settings-merge.md`. At the end of the file, append:

```markdown

---

## Feedback log schema

The orchestrator writes user-reported hook misfires to `${CLAUDE_PROJECT_DIR}/.claude/self-improving-claude/feedback.jsonl`. One JSON object per line:

```jsonl
{"ts":"2026-05-23T15:30:01Z","target":"self-improving-claude/block-pnpm-test-watcher","mode":"too-broad","complaint":"blocked legitimate `pnpm test --filter foo` command","resolution":"narrowed matcher from Bash to Bash(pnpm test) with --filter exception"}
```

Required fields:
- `ts` — ISO-8601 UTC timestamp of the feedback event
- `target` — sentinel `name` (`self-improving-claude/<slug>`) of the hook complained about
- `mode` ∈ `{too-broad, false-positive, please-narrow, missed-case}`
- `complaint` — user's verbatim feedback text (trim very long inputs to ~500 chars)
- `resolution` — one-sentence description of what the orchestrator changed in response

`/improve-init` reads feedback.jsonl on subsequent runs and applies extra scrutiny when proposing similar hooks: if a recent feedback row mentions a hook whose pattern resembles a new proposal, flag the new proposal for explicit user confirmation rather than auto-accepting on the rubric alone.
```

- [ ] **Step 3: Verify the procedure still has 10 numbered steps**

```bash
grep -c '^## Step ' plugin/skills/shared/procedure.md
```
Expected: `10` (we modified Step 1's body, didn't add or remove steps).

- [ ] **Step 4: Commit**

```bash
git add plugin/skills/shared/procedure.md plugin/skills/shared/references/settings-merge.md
git commit -m "Formalize feedback channel — feedback.jsonl schema + Step 1 modify-target-hook routing"
```

---

## Task 8: Eval fixtures 006 + 007

**Files:**
- Create: `evals/fixtures/006-rename-callers/description.md`
- Create: `evals/fixtures/006-rename-callers/expected_traits.json`
- Create: `evals/fixtures/006-rename-callers/chat.md`
- Create: `evals/fixtures/006-rename-callers/project/CLAUDE.md`
- Create: `evals/fixtures/006-rename-callers/project/src/tools/example.ts`
- Create: `evals/fixtures/006-rename-callers/telemetry.jsonl`
- Create: `evals/fixtures/007-git-push-warn/description.md`
- Create: `evals/fixtures/007-git-push-warn/expected_traits.json`
- Create: `evals/fixtures/007-git-push-warn/chat.md`
- Create: `evals/fixtures/007-git-push-warn/project/CLAUDE.md`
- Create: `evals/fixtures/007-git-push-warn/telemetry.jsonl`
- Modify: `evals/dataset.json` — add 2 entries
- Modify: `evals/grade_code.py` — handle the new `form` values (`permissions.ask`) and `rule_pattern_must_contain` traits

**Purpose:** Per spec §3.4 + §7 acceptance criterion #2: fixture 006 catches the v0.2 dogfooding regression (form-selection sliding to CLAUDE.md when a hook was warranted). Fixture 007 verifies the orchestrator picks `permissions.ask` for the "warn before git push" case (the lighter form, beating the prompt-hook from v0.2 Example 3).

- [ ] **Step 1: Create fixture 006 — rename-callers (reactive)**

```bash
mkdir -p evals/fixtures/006-rename-callers/project/src/tools
```

Create `evals/fixtures/006-rename-callers/description.md`:

```markdown
# Planted problem — Claude renamed an exported identifier without checking callers

The user pasted a regression analysis showing that an Edit to a single exported constant value (`export const FILE_READ_TOOL_NAME = 'Read'` → `'View'`) silently broke ~15 hardcoded callers across the codebase. They asked for a guardrail that surfaces all references of an exported identifier whenever that identifier's definition line is edited.

This is a **reactive** fixture — the planted problem is in chat.md (recent conversation).

A `CLAUDE.md` note is NOT viable — the rule is "after editing an export, show callers" which requires enforcement. The check needs the same kind of pattern detection an EXPORT_DEF regex gives. The right form is a **PostToolUse command hook** on `Edit|MultiEdit` that runs grep and feeds results back via stderr.

A `permissions.deny` rule doesn't fit (we don't want to block edits, just surface info). A prompt-hook would work but pays an LLM-call cost per edit when a deterministic grep does the job.

Expected proposal: form=`command-hook`, event=`PostToolUse`, matcher includes `Edit|MultiEdit`.
```

Create `evals/fixtures/006-rename-callers/expected_traits.json`:

```json
{
  "form": "command-hook",
  "event": "PostToolUse",
  "matcher_must_include": ["Edit", "MultiEdit"],
  "rationale_must_mention": ["export", "caller"]
}
```

Create `evals/fixtures/006-rename-callers/project/CLAUDE.md`:

```markdown
# Project conventions

TypeScript project with many exported tool-name constants. Renames of exported identifiers must be coordinated across all files that import them or hardcode the values.
```

Create `evals/fixtures/006-rename-callers/project/src/tools/example.ts`:

```typescript
// Use a string constant for tool names to avoid circular dependencies
export const FILE_READ_TOOL_NAME = 'Read'
```

Create `evals/fixtures/006-rename-callers/chat.md`:

````markdown
USER: Ändere in src/tools/example.ts den Wert von FILE_READ_TOOL_NAME von 'Read' auf 'View'.

CLAUDE: [Edits src/tools/example.ts]

```typescript
export const FILE_READ_TOOL_NAME = 'View'
```

USER: Bitte überprüfe deine letzte Änderung auf mögliche Regressionen. Suche gezielt nach Stellen, die den alten Tool-Namen "Read" noch hart codiert verwenden.

CLAUDE: [Searches and finds 15 hardcoded 'Read' callers across telemetry, permissions, validators, agent allowlists, and skill bundles that are now broken.]

USER: Das ist genau warum ich einen guardrail will. Bitte eine hook die alle referenzen anzeigt sobald ich einen exported identifier ändere — egal wo in diesem codebase. Nicht nur für walk_tree.
````

Create `evals/fixtures/006-rename-callers/telemetry.jsonl`:

```jsonl
{"ts":"2026-05-22T16:00:01Z","event":"tool","tool":"Edit","args_summary":"/project/src/tools/example.ts"}
{"ts":"2026-05-22T16:01:00Z","event":"tool","tool":"Grep","args_summary":"Read"}
```

- [ ] **Step 2: Create fixture 007 — git-push-warn (proactive)**

```bash
mkdir -p evals/fixtures/007-git-push-warn/project
```

Create `evals/fixtures/007-git-push-warn/description.md`:

```markdown
# Planted problem — Claude should pause before any git push

The user noted that Claude sometimes wants to `git push` from inside the agent during normal work. The user wants a human in the loop for EVERY push — not a hard block, just a confirmation prompt.

A `permissions.deny` rule is too strict (it would block legitimate pushes). A CLAUDE.md note is too lax (relies on the model remembering). A prompt-hook would work but pays an LLM-call cost for what is essentially "just ask the user every time."

The right form is **`permissions.ask`** — built-in Claude Code prompts the user before any matching command. No script, no LLM call, no maintenance.

Expected proposal: form=`permissions.ask`, rule contains `Bash(git push`.
```

Create `evals/fixtures/007-git-push-warn/expected_traits.json`:

```json
{
  "form": "permissions.ask",
  "rule_pattern_must_contain": "Bash(git push",
  "rationale_must_mention": ["git push", "confirm"]
}
```

Create `evals/fixtures/007-git-push-warn/project/CLAUDE.md`:

```markdown
# Project conventions

Standard Node.js project. Feature branch workflow — pushes happen frequently but should always involve a human.
```

Create `evals/fixtures/007-git-push-warn/chat.md`:

```markdown
(Empty — proactive fixture; signal comes from project + telemetry.)
```

Create `evals/fixtures/007-git-push-warn/telemetry.jsonl`:

```jsonl
{"ts":"2026-05-22T10:00:00Z","event":"tool","tool":"Bash","args_summary":"git push origin feature/foo","outcome":{"exit_code":0}}
{"ts":"2026-05-22T11:30:00Z","event":"tool","tool":"Bash","args_summary":"git push origin main","outcome":{"exit_code":0}}
{"ts":"2026-05-22T14:15:00Z","event":"tool","tool":"Bash","args_summary":"git push --force origin main","outcome":{"exit_code":0}}
```

- [ ] **Step 3: Update dataset.json — add the 2 new entries**

Read the current `evals/dataset.json`. It has 5 entries. Add entries 6 and 7 at the end of the `entries` array. The full updated file:

```json
{
  "entries": [
    {
      "id": "001-pnpm-test-watcher",
      "trigger": "improve-init",
      "user_args": "",
      "fixture": "fixtures/001-pnpm-test-watcher",
      "planted_problem": "Claude keeps invoking `pnpm test` (interactive watcher) instead of `pnpm test:ci` (CI runner); telemetry has 3 non-zero exits, and package.json defines test:ci as the correct script.",
      "expected_hook_traits": {
        "form": "command-hook",
        "event": "PreToolUse",
        "matcher": "Bash",
        "blocks_command_prefix": "pnpm test",
        "allows_command": "pnpm test:ci",
        "rationale_must_mention": ["pnpm test:ci", "watcher"]
      }
    },
    {
      "id": "002-block-env-reads",
      "trigger": "improve-init",
      "user_args": "block reads of .env files",
      "fixture": "fixtures/002-block-env-reads",
      "planted_problem": "Claude has been reading .env and .env.local during normal work; user wants these blocked uniformly across Read/Grep/Glob.",
      "expected_hook_traits": {
        "form": "permissions.deny",
        "rule_pattern": "Read(**/.env)",
        "rationale_must_mention": [".env"]
      }
    },
    {
      "id": "003-prisma-generated-protection",
      "trigger": "improve-init",
      "user_args": "",
      "fixture": "fixtures/003-prisma-generated-protection",
      "planted_problem": "Claude edits src/generated/prisma/* (auto-generated client) and writes to prisma/dev.db (SQLite binary). CLAUDE.md forbids both but no enforcement exists.",
      "expected_hook_traits": {
        "form": "permissions.deny",
        "rule_pattern": "Edit(src/generated/prisma/**)",
        "rationale_must_mention": ["prisma", "generated"]
      }
    },
    {
      "id": "004-recursion-prevention",
      "trigger": "improve",
      "user_args": "add a guardrail so you don't introduce unbounded recursion again",
      "fixture": "fixtures/004-recursion-prevention",
      "planted_problem": "Claude refactored walk_tree from iterative to recursive without a depth bound, causing RecursionError on a 2000-leaf input. User wants a project-wide guardrail against introducing recursive helpers.",
      "expected_hook_traits": {
        "form": "prompt-hook",
        "event": "PreToolUse",
        "matcher_must_include": ["Edit", "Write"],
        "rationale_must_mention": ["recursion"]
      }
    },
    {
      "id": "005-format-on-write",
      "trigger": "improve-init",
      "user_args": "",
      "fixture": "fixtures/005-format-on-write",
      "planted_problem": "Edits to .py files aren't auto-formatted; ruff check flags them after the fact. CLAUDE.md says `ruff format` is the formatter.",
      "expected_hook_traits": {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Write|Edit|MultiEdit",
        "rationale_must_mention": ["ruff", "format"]
      }
    },
    {
      "id": "006-rename-callers",
      "trigger": "improve",
      "user_args": "add a hook that shows all references when I rename an exported identifier",
      "fixture": "fixtures/006-rename-callers",
      "planted_problem": "Claude renamed FILE_READ_TOOL_NAME from 'Read' to 'View' without grepping for hardcoded callers; ~15 places broke silently. User wants a guardrail that surfaces all references of an exported identifier whenever its definition line is edited.",
      "expected_hook_traits": {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher_must_include": ["Edit", "MultiEdit"],
        "rationale_must_mention": ["export", "caller"]
      }
    },
    {
      "id": "007-git-push-warn",
      "trigger": "improve-init",
      "user_args": "",
      "fixture": "fixtures/007-git-push-warn",
      "planted_problem": "Claude sometimes wants to git push from inside the agent. User wants a human in the loop for every push — not a hard block, just confirmation.",
      "expected_hook_traits": {
        "form": "permissions.ask",
        "rule_pattern_must_contain": "Bash(git push",
        "rationale_must_mention": ["git push", "confirm"]
      }
    }
  ]
}
```

- [ ] **Step 4: Extend grade_code.py to handle the new traits**

Open `evals/grade_code.py`. Two new things the grader needs to support:

1. `matcher_must_include` (an ARRAY of substrings the matcher must contain — different from `matcher` which is exact match)
2. `rule_pattern_must_contain` (a substring the proposal's `rule` must contain — used for `permissions.ask` and `permissions.deny`)

Find the function `_check_matcher_matches`. Replace it with:

```python
def _check_matcher_matches(p: dict, e: dict) -> int:
    if "matcher" in e:
        return 10 if p.get("matcher") == e.get("matcher") else 0
    if "matcher_must_include" in e:
        m = p.get("matcher", "") or ""
        required = e["matcher_must_include"]
        return 10 if all(piece in m for piece in required) else 0
    return 10
```

Find `_check_form_matches` — it already works for the new forms (`permissions.ask` is just a string compared to expected). No change.

Add a new check `_check_rule_pattern` after `_check_rationale_keywords`:

```python
def _check_rule_pattern(p: dict, e: dict) -> int:
    """For permissions.ask / permissions.deny proposals, verify the rule string."""
    if "rule_pattern" in e:
        return 10 if p.get("rule") == e["rule_pattern"] else 0
    if "rule_pattern_must_contain" in e:
        rule = p.get("rule", "") or ""
        return 10 if e["rule_pattern_must_contain"] in rule else 0
    return 10
```

Then update the `_CHECKS` dict to include it:

```python
_CHECKS = {
    "form_matches": _check_form_matches,
    "event_matches": _check_event_matches,
    "matcher_matches": _check_matcher_matches,
    "script_parses": _check_script_parses,
    "sentinel_format": _check_sentinel_format,
    "rationale_keywords": _check_rationale_keywords,
    "rule_pattern": _check_rule_pattern,
}
```

- [ ] **Step 5: Add tests for the new grader checks**

Open `evals/tests/test_grade_code.py`. Append at the end:

```python
def test_grade_matcher_must_include_passes_on_subset_match():
    proposal = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Edit|MultiEdit",
        "script": "import sys\nsys.exit(0)\n",
        "script_lang": "python",
        "rationale": "After editing an export, show callers.",
        "sentinel_name": "self-improving-claude/grep-callers",
    }
    expected = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher_must_include": ["Edit", "MultiEdit"],
        "rationale_must_mention": ["export", "caller"],
    }
    result = grade_code(proposal, expected)
    assert result["checks"]["matcher_matches"] == 10


def test_grade_matcher_must_include_fails_when_missing():
    proposal = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Write",  # missing both Edit and MultiEdit
        "script": "import sys\nsys.exit(0)\n",
        "script_lang": "python",
        "rationale": "After editing an export, show callers.",
        "sentinel_name": "self-improving-claude/grep-callers",
    }
    expected = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher_must_include": ["Edit", "MultiEdit"],
        "rationale_must_mention": ["export", "caller"],
    }
    result = grade_code(proposal, expected)
    assert result["checks"]["matcher_matches"] == 0


def test_grade_permissions_ask_proposal():
    proposal = {
        "form": "permissions.ask",
        "rule": "Bash(git push:*)",
        "rationale": "Causes Claude Code to confirm before every git push.",
    }
    expected = {
        "form": "permissions.ask",
        "rule_pattern_must_contain": "Bash(git push",
        "rationale_must_mention": ["git push", "confirm"],
    }
    result = grade_code(proposal, expected)
    assert result["mean"] >= 8.0
    assert result["checks"]["form_matches"] == 10
    assert result["checks"]["rule_pattern"] == 10
    assert result["checks"]["rationale_keywords"] == 10


def test_grade_rule_pattern_must_contain_substring():
    proposal = {"form": "permissions.deny", "rule": "Read(**/.env.production)", "rationale": "Block reads of .env files"}
    expected = {"form": "permissions.deny", "rule_pattern_must_contain": ".env", "rationale_must_mention": [".env"]}
    result = grade_code(proposal, expected)
    assert result["checks"]["rule_pattern"] == 10
```

- [ ] **Step 6: Run grader tests to verify**

```bash
python3 -m pytest evals/tests/test_grade_code.py -v
```
Expected: all tests pass (10 original + 4 new = 14 total).

- [ ] **Step 7: Verify both new fixtures load and dataset has 7 entries**

```bash
python3 -c "
from evals.fixtures_lib import load_dataset, load_fixture
ds = load_dataset()
print(f'{len(ds)} entries')
for entry in ds:
    fx = load_fixture(entry['id'])
    print(f'  {entry[\"id\"]:42} trigger={entry[\"trigger\"]:14} form={entry[\"expected_hook_traits\"][\"form\"]}')
"
```

Expected:
```
7 entries
  001-pnpm-test-watcher                      trigger=improve-init   form=command-hook
  002-block-env-reads                        trigger=improve-init   form=permissions.deny
  003-prisma-generated-protection            trigger=improve-init   form=permissions.deny
  004-recursion-prevention                   trigger=improve        form=prompt-hook
  005-format-on-write                        trigger=improve-init   form=command-hook
  006-rename-callers                         trigger=improve        form=command-hook
  007-git-push-warn                          trigger=improve-init   form=permissions.ask
```

- [ ] **Step 8: Run full eval test suite to confirm nothing regressed**

```bash
python3 -m pytest evals/ -v -m "not integration"
```
Expected: all eval unit tests pass (was 33 in v0.2; now 37 with 4 new grader tests).

- [ ] **Step 9: Commit**

```bash
git add evals/fixtures/006-rename-callers/ evals/fixtures/007-git-push-warn/ \
        evals/dataset.json evals/grade_code.py evals/tests/test_grade_code.py
git commit -m "Add fixtures 006 (rename-callers) and 007 (git-push-warn) + grader support for permissions.ask and matcher_must_include"
```

---

## Task 9: Baseline reruns (gemma + Haiku)

**Files:**
- Create: `evals/results/2026-05-23-v0.3-gemma.json` (generated by the eval runner)
- Create: `evals/results/2026-05-23-v0.3-haiku.json` (generated; optional — requires ANTHROPIC_API_KEY)

**Purpose:** Per spec §7 acceptance criterion #3: rerun the eval against both gemma4 (local) and Haiku (cloud) using the v0.3 orchestrator content (with the form-selection fix applied). Compare deltas against the v0.2 baseline.

- [ ] **Step 1: Confirm Ollama is running with gemma4 available**

```bash
curl -s http://localhost:11434/api/tags 2>&1 | python3 -c "import json, sys; d=json.load(sys.stdin); m=[t['name'] for t in d.get('models',[])]; print('Models:', m); assert 'gemma4:e4b' in m, 'gemma4:e4b not pulled'; print('OK')"
```

Expected: lists models, ends with `OK`. If gemma4:e4b is missing, pull it with `ollama pull gemma4:e4b` (will be ~9.6 GB).

- [ ] **Step 2: Run the eval against the local gemma backend**

```bash
EVAL_BACKEND=ollama python3 -m evals.run 2>&1 | tail -15
```

Expected: 7 entries run sequentially (about 5–8 minutes), results written to `evals/results/2026-05-23.json` with summary like:

```
Running 001-pnpm-test-watcher...
...
Running 007-git-push-warn...

Results written to ~/Desktop/Projects/self-improving-claude/evals/results/2026-05-23.json
Average code score:  X.X/10
Average model score: Y.Y/10
```

- [ ] **Step 3: Rename the result file to mark it as the v0.3 gemma baseline**

```bash
mv evals/results/2026-05-23.json evals/results/2026-05-23-v0.3-gemma.json
ls evals/results/
```

Expected: `2026-05-22-baseline.json` (v0.2) and `2026-05-23-v0.3-gemma.json` (just produced) both present.

- [ ] **Step 4: Print the per-entry comparison**

```bash
python3 -c "
import json
v02 = json.load(open('evals/results/2026-05-22-baseline.json'))['summary']
v03 = json.load(open('evals/results/2026-05-23-v0.3-gemma.json'))['summary']
v02_map = {e['id']: e for e in v02['entries']}
v03_map = {e['id']: e for e in v03['entries']}
all_ids = sorted(set(v02_map.keys()) | set(v03_map.keys()))
print(f\"{'fixture':<42} v0.2-code  v0.3-code   Δ    v0.2-model  v0.3-model   Δ\")
for fid in all_ids:
    a = v02_map.get(fid)
    b = v03_map.get(fid)
    if a is None:
        print(f\"  {fid:<40} (new in v0.3)                       code={b['code']:.1f}    model={b['model']}\")
        continue
    dc = b['code'] - a['code']
    dm = b['model'] - a['model']
    print(f\"  {fid:<40} {a['code']:>6.1f}     {b['code']:>6.1f}     {dc:+5.1f}  {a['model']:>6}      {b['model']:>6}     {dm:+5}\")
print()
print(f\"avg code: v0.2={v02['average_code']:.1f}  v0.3={v03['average_code']:.1f}  Δ={v03['average_code']-v02['average_code']:+.1f}\")
print(f\"avg model: v0.2={v02['average_model']:.1f}  v0.3={v03['average_model']:.1f}  Δ={v03['average_model']-v02['average_model']:+.1f}\")
"
```

Expected: per-entry table + average deltas. Specifically, fixtures 006 and 007 should appear as "new in v0.3" rows. The Δ on existing fixtures (001-005) should be near-zero — they're unchanged by v0.3's form-selection rewording (since their expected forms are already correctly identified). Fixture 006 should score ≥7/10 code (the form-selection fix means Gemma should pick command-hook over CLAUDE.md note). Fixture 007 should score ≥7/10 code (Gemma should pick permissions.ask now that it's an explicit option).

If 006 or 007 score below 7/10, the form-selection wording change wasn't strong enough — go back to Task 3 and tighten the rubric/procedure wording, then rerun Steps 2–4.

- [ ] **Step 5: Optional Haiku rerun (if ANTHROPIC_API_KEY is set)**

```bash
if [ -n "$ANTHROPIC_API_KEY" ]; then
  EVAL_BACKEND=anthropic python3 -m evals.run 2>&1 | tail -10
  mv evals/results/$(date -u +%Y-%m-%d).json evals/results/2026-05-23-v0.3-haiku.json
  echo "Haiku baseline at evals/results/2026-05-23-v0.3-haiku.json"
else
  echo "ANTHROPIC_API_KEY not set — skipping Haiku baseline. Run later manually with EVAL_BACKEND=anthropic python3 -m evals.run."
fi
```

If skipped: note it in CHANGELOG (Task 10) and the user can run the Haiku rerun later when convenient.

- [ ] **Step 6: Commit**

```bash
git add evals/results/
git commit -m "v0.3 baseline scores (gemma4; Haiku optional)"
```

---

## Task 10: README + CHANGELOG + Anthropic-marketplace PR materials

**Files:**
- Modify: `README.md` — full rewrite for public audience
- Create: `CHANGELOG.md`
- Create: `docs/anthropic-marketplace-pr.md`
- Modify: `docs/superpowers/specs/2026-05-22-self-improving-claude-design.md` — §9 mark v0.3 shipped

**Purpose:** Make the repo first-visitor-friendly. README leads with what the plugin does and how to install in three lines. CHANGELOG records the v0.3 breaking change (`--plugin-dir` path moved). `docs/anthropic-marketplace-pr.md` contains the materials for a future PR to the official Anthropic marketplace.

- [ ] **Step 1: Rewrite README.md for public audience**

Open `README.md`. Replace its entire content with:

```markdown
# self-improving-claude

> A Claude Code plugin that turns the bugs you just saw into the hooks that prevent the next ones — per-project guardrails proposed by Claude itself, installed only with your explicit approval.

**Status:** v0.3.0 — public release.

## What it does

Claude Code is powerful by default, but every project has its own footguns. A test command that's `pnpm test:ci` not `pnpm test`. A generated directory that should never be hand-edited. A push command that should always require human confirmation. A constant rename that needs a callers-grep first.

`self-improving-claude` watches your Claude Code sessions, then — when you ask — proposes a tailored set of guardrails for THIS project: `permissions.deny` rules, `permissions.ask` prompts, hooks, or `CLAUDE.md` notes. You approve each one individually. The plugin generates the code; you decide what installs.

Three commands:

| Command | When to use |
|---|---|
| `/improve` | Right after seeing Claude do something you don't want again. Uses the live conversation as primary context. |
| `/improve-init` | First time, or periodic full sweep. Reads your project's code, recent session transcripts, and the bundled telemetry log. |
| `/improve-uninstall` | Cleanly remove the plugin's footprint from THIS project (settings.json entries, generated scripts, optionally telemetry). The plugin itself stays installed. |

## Install

```bash
# Add this repo as a marketplace
claude plugin marketplace add github:tim/self-improving-claude

# Install the plugin
claude plugin install self-improving-claude

# Restart Claude Code so the plugin loads
exit && claude
```

Inside any session: type `/improve-init` to run a first scan.

### Local dev / per-session use

If you're hacking on the plugin itself, clone the repo and use `--plugin-dir`:

```bash
git clone <this-repo> ~/code/self-improving-claude
claude --plugin-dir ~/code/self-improving-claude/plugin
```

Or alias it:

```bash
echo 'alias claude="command claude --plugin-dir ~/code/self-improving-claude/plugin"' >> ~/.zshrc
```

## How it works

When you run `/improve` or `/improve-init`, the plugin's orchestrator skill:

1. **Reads what already exists** in your project: `CLAUDE.md`, `.claude/settings.json`, the bundled telemetry log, recent session transcripts.
2. **Identifies up to 5 candidate guardrails** based on what it sees (a CHAT message describing a bug, repeated tool-call failures, project conventions encoded in CLAUDE.md, etc.).
3. **For each candidate, picks the lightest viable form:**
   - `permissions.deny` rule (cheapest)
   - `permissions.ask` rule (built-in Claude Code asks you each time)
   - prompt-based hook (LLM evaluates each tool call)
   - command hook on PreToolUse (deterministic block)
   - command hook on PostToolUse (surface context after action)
   - `CLAUDE.md` note (last resort, taste-level only)
4. **Self-critiques** the draft against an explicit rubric. Drops candidates that don't measure up.
5. **Walks you through approval** one at a time. You see the actual code, the rationale, where it merges into your `.claude/settings.json`. Approve, edit, or skip per candidate.
6. **Writes approved files** to `.claude/hooks/` and merges entries into `.claude/settings.json` (defensively — never overwrites your existing config).
7. **Tells you to restart Claude Code** so the new hooks load.

## Telemetry & privacy

The plugin installs one passive telemetry hook that logs summarized tool usage to `.claude/self-improving-claude/telemetry.jsonl` in each project where Claude Code is active.

**Redaction is strict** (tested in `plugin/scripts/tests/test_telemetry.py`):

- File `Read`/`Write`/`Edit` log only the path, never content.
- `Bash` logs the first 80 chars of the command and (only on non-zero exit) the first 200 chars of stderr.
- `Grep`/`Glob` redact patterns that match known secret prefixes (`API_KEY`, `SECRET`, `TOKEN`, etc.).
- `WebFetch` logs only the URL host — never query strings.
- `Task`/`TodoWrite` log type/counts only — never the prompt or todo content.

In v0.3 the telemetry hook also captures session boundaries (`SessionStart`), compaction events (`PreCompact`), and permission/idle notifications (`Notification`) — these give `/improve-init` richer signal to mine.

The log rotates at session end (renamed to `telemetry.<YYYYMMDD-HHMMSS>.jsonl`, fresh empty file for the next session).

**All telemetry stays on your local machine.** Nothing is sent anywhere.

## Inspecting & troubleshooting

Use Claude Code's built-in commands:

- `/hooks` — list all currently-loaded hooks (yours + plugins')
- `/memory` — open and edit your project's `CLAUDE.md`
- `claude plugin list` — show installed plugins
- `claude --debug` — verbose logging, including hook execution
- `claude plugin uninstall self-improving-claude` — remove the plugin itself (does NOT touch your project's `.claude/` directory — for that, use `/improve-uninstall`)

If a generated hook ever misfires:

```
/improve "the <name> hook just blocked something legit"
```

This is feedback-mode — it logs your complaint to `.claude/self-improving-claude/feedback.jsonl` and narrows the affected hook automatically.

## Design docs & evals

- `docs/superpowers/specs/` — full design specs for v0.1, v0.2, v0.3
- `docs/superpowers/plans/` — implementation plans
- `docs/knowledge/` — distilled Claude Code course material that grounds the design
- `docs/anthropic-marketplace-pr.md` — materials for publishing to the official marketplace
- `evals/` — dev-only eval harness. Run `pip install -r requirements-dev.txt && python3 -m evals.run` to reproduce the baseline (uses local Ollama by default; cloud Anthropic via `EVAL_BACKEND=anthropic`).

Baselines committed to `evals/results/`.

## Roadmap

- **v0.1** — `/improve-init` proactive scan, per-proposal approval, bundled telemetry hook.
- **v0.2** — `/improve` reactive mode, eval harness with 5 fixtures + code & model graders.
- **v0.3** (current) — public release: marketplace install, hidden orchestrator, `permissions.ask` as form option, multi-event telemetry, `/improve-uninstall`, formalized feedback channel, 7-fixture eval baseline.
- **v0.4+** — opt-in Stop-hook auto-collect (proactive pattern detection), conflict-resolution UX expansion, 10–20 eval entries, Anthropic-marketplace PR.

## License

MIT. See `LICENSE`.
```

- [ ] **Step 2: Create CHANGELOG.md**

Create `CHANGELOG.md` with this content:

```markdown
# Changelog

All notable changes to `self-improving-claude` are documented here.

## [0.3.0] — 2026-05-23

### Added
- **Marketplace install.** Repo is now a single-plugin marketplace; `claude plugin marketplace add` + `claude plugin install self-improving-claude` works for both local and GitHub paths.
- **`/improve-uninstall` slash command.** Cleanly removes the plugin's project-level footprint (sentinel entries in `.claude/settings.json`, generated hook scripts, optionally telemetry). The plugin itself stays installed.
- **`permissions.ask` as a 5th recognized guardrail form.** Built-in Claude Code prompts the user for confirmation — lighter than a prompt-hook (no LLM evaluation), heavier than `permissions.deny` (interactive). Often the right answer for "warn before X" rules like `Bash(git push:*)`.
- **Multi-event telemetry.** Bundled telemetry hook now listens on `PostToolUse`, `Notification`, `PreCompact`, and `SessionStart` (was only PostToolUse), providing richer signal for `/improve-init` to mine.
- **SessionEnd telemetry rotation.** Inline-bash hook renames `telemetry.jsonl` at session end and starts a fresh file; archives keep history without bloating the active log.
- **Feedback channel.** `/improve "the <hook> blocked something legit"` now persistently logs the complaint to `.claude/self-improving-claude/feedback.jsonl` AND modifies the named hook in-place (narrows matcher / adds exception).
- **Two new eval fixtures.** Fixture 006 (rename-callers, reactive) and fixture 007 (git-push-warn, proactive — tests the `permissions.ask` form).
- **CHANGELOG.md** (this file).

### Changed
- **Orchestrator hidden from `/` menu.** The model-invoked `self-improving-claude` skill content moved to `plugin/skills/shared/procedure.md` (a non-skill content file). Only `/improve`, `/improve-init`, `/improve-uninstall` appear in the slash-command listing now.
- **Form-selection rubric tightened.** Rubric criterion #2 explicitly emphasizes *viable* — CLAUDE.md notes are no longer treated as "lightest" when the rule needs enforcement. Procedure Step 4 now lists 5 forms in priority order, with `permissions.ask` and PostToolUse command-hook explicit (both were under-used in v0.2).
- **README rewrite.** First-time-visitor hero pitch, three-line install, trust + privacy + troubleshooting sections pointing at Claude Code's built-in commands.

### Removed
- **No more `--plugin-dir <repo-root>`.** The plugin lives at `<repo>/plugin/` now. Use `--plugin-dir <repo>/plugin` for local dev, or `claude plugin install self-improving-claude` after `marketplace add` for permanent install. (Breaking change vs v0.2 local-dev workflow.)
- Speculative auto-collect / Stop-hook pattern-detection feature **deferred to v0.4** (YAGNI — no dogfood evidence it's wanted yet).

### Fixed
- Form-selection bias bug from v0.2 dogfooding: the orchestrator slid to CLAUDE.md note whenever a hook seemed "expensive," missing both `permissions.ask` and PostToolUse command-hook as forms. Eval fixture 006 (the dogfooding case) and fixture 007 (the `permissions.ask` case) catch regressions.

## [0.2.0] — 2026-05-22

- Reactive `/improve` slash command (uses live chat context).
- Eval harness with 5 fixtures, code-grader (deterministic) + model-grader (Haiku).
- First scored baseline committed (gemma4 via Ollama).
- Pluggable eval backend (`EVAL_BACKEND={ollama|anthropic}`).

## [0.1.0] — 2026-05-22

- `/improve-init` proactive scan with per-proposal approval.
- Bundled telemetry hook (PostToolUse, redacted JSONL).
- Per-proposal `AskUserQuestion`-driven approval flow.
- 10-step orchestrator procedure grounded in Anthropic's Claude Code course material.
```

- [ ] **Step 3: Create docs/anthropic-marketplace-pr.md**

Create `docs/anthropic-marketplace-pr.md`:

```markdown
# Anthropic Marketplace PR — Materials

This document contains everything needed to submit a PR to `anthropics/claude-plugins-official` that adds self-improving-claude to the official marketplace.

**Pre-submit checklist:**

- [ ] Repo is publicly accessible on GitHub
- [ ] Plugin manifest at `plugin/.claude-plugin/plugin.json` passes `claude plugin validate`
- [ ] README clearly explains what the plugin does, install steps, trust/privacy
- [ ] At least one tagged release exists (`v0.3.0`)
- [ ] LICENSE is OSI-approved (MIT)
- [ ] All sentinel-related conventions documented (so reviewers can understand the security model)

## Proposed addition to anthropics/claude-plugins-official/.claude-plugin/marketplace.json

Insert this entry into the `plugins` array (alphabetical ordering — find the right slot):

```json
{
  "name": "self-improving-claude",
  "description": "Proactive and reactive guardrail proposals for your Claude Code projects, with per-proposal approval. Analyzes telemetry, project conventions, and current conversation to suggest hooks, permissions.deny/ask rules, or CLAUDE.md notes — and installs only what you approve.",
  "author": {
    "name": "Tim Kiefer",
    "email": "tim.f.kief@gmail.com"
  },
  "category": "productivity",
  "source": {
    "source": "git-subdir",
    "url": "https://github.com/<user>/self-improving-claude.git",
    "path": "plugin",
    "ref": "v0.3.0",
    "sha": "<sha-of-v0.3.0-tag>"
  },
  "homepage": "https://github.com/<user>/self-improving-claude"
}
```

Replace `<user>` with the actual GitHub username/org. Replace `<sha-of-v0.3.0-tag>` with the commit SHA the tag points to (`git rev-parse v0.3.0`).

## Draft PR body

```
## Adds: self-improving-claude

`self-improving-claude` is a Claude Code plugin that watches your sessions and
proposes per-project guardrails (`permissions.deny` / `.ask`, hooks, CLAUDE.md notes)
based on observed behavior. Per-proposal user approval — nothing installs silently.

### What it does

- `/improve` (reactive) — propose guardrails based on the current conversation
- `/improve-init` (proactive) — periodic full scan of project + telemetry
- `/improve-uninstall` — clean project-level footprint

### Trust model

- All generated hooks live as readable files under the user's `.claude/hooks/` with a `self-improving-claude/<slug>` sentinel
- Telemetry is local-only (redacted JSONL); strict rules tested in repo
- Per-proposal approval — user sees the actual code/rule before anything writes

### Evals

5-fixture baseline (gemma4 local + Haiku cloud), code-grader + model-grader,
committed scores at `evals/results/`. Form-selection regression catches the
v0.2 bias bug from real-world dogfooding.

### Compliance with marketplace schema

- `plugin.json` validates against the official schema
- Plugin lives in `plugin/` subdir (matches `git-subdir` source pattern)
- MIT licensed; LICENSE file present
- README clearly documents install + usage + privacy
```

## After submission

If the PR is accepted, update the README's install section from `claude plugin marketplace add github:tim/self-improving-claude` to `claude plugin install self-improving-claude` (no separate marketplace add needed for plugins in the official one).
```

- [ ] **Step 4: Update v0.1 spec §9 to mark v0.3 shipped**

Open `docs/superpowers/specs/2026-05-22-self-improving-claude-design.md`. Find the v0.3.0 section in §9. Replace:

```markdown
### v0.3.0+ — polish

- Feedback channel formalized: `/improve "the foo-hook blocked something legit"` logs to `.claude/self-improving-claude/feedback.jsonl`; next run reads it.
- Conflict UX (keep/replace/skip) for matcher overlaps.
- 10–20 eval entries; documented score thresholds.
- (Stretch) auto-rewind investigation.
```

with:

```markdown
### v0.3.0 — "public release" (✅ shipped 2026-05-23)

- ✅ Marketplace install (repo became a single-plugin marketplace).
- ✅ Orchestrator hidden from `/` menu (`shared/procedure.md` content file).
- ✅ `permissions.ask` added as 5th recognized guardrail form.
- ✅ Multi-event telemetry (PostToolUse + Notification + PreCompact + SessionStart) + SessionEnd inline-bash rotation.
- ✅ Feedback channel formalized — `feedback.jsonl` persisted, target hook modified in-place.
- ✅ `/improve-uninstall` slash command.
- ✅ 7-fixture eval baseline rerun (gemma4 + Haiku).
- ✅ Public README + CHANGELOG + Anthropic-marketplace PR materials.

### v0.4.0+ — polish (deferred from earlier roadmap)

- Opt-in Stop-hook auto-collect (proactive pattern detection — deferred from v0.3 as YAGNI until dogfood evidence appears).
- Conflict UX (keep/replace/skip) for matcher overlaps — fixture + manual smoke test.
- 10–20 eval entries; documented score thresholds.
- (Stretch) auto-rewind investigation.
```

- [ ] **Step 5: Verify all tests still pass**

```bash
python3 -m pytest -m "not integration" 2>&1 | tail -3
```
Expected: still passes — none of these changes touch test code. Should be 60 tests (55 from v0.2 + 5 from v0.3 multi-event telemetry tests + 4 from grader extensions = 64, give or take based on actual final counts).

- [ ] **Step 6: Final commit**

```bash
git add README.md CHANGELOG.md docs/anthropic-marketplace-pr.md \
        docs/superpowers/specs/2026-05-22-self-improving-claude-design.md
git commit -m "v0.3 docs — README rewrite + CHANGELOG + Anthropic-marketplace PR materials + spec §9 ✅"
```

- [ ] **Step 7: Merge to main and tag v0.3.0**

```bash
git checkout main
git merge v0.3-implementation
python3 -m pytest -m "not integration" 2>&1 | tail -3  # confirm tests pass on merged main
git tag -a v0.3.0 -m "v0.3.0 — public release: marketplace install, hidden orchestrator, permissions.ask, multi-event telemetry, feedback channel, /improve-uninstall"
git branch -d v0.3-implementation
git log --oneline -8
git tag
```

Expected:
- merged main now at the latest commit
- tests still pass on main
- branch deleted
- tags: `v0.2.0`, `v0.3.0`

v0.3.0 is shipped locally. To go public:
1. Create the GitHub repo (named `self-improving-claude`)
2. `git remote add origin git@github.com:<user>/self-improving-claude.git`
3. `git push -u origin main && git push origin --tags`
4. Verify public install works: in a fresh terminal on a different machine (or after restarting Claude Code), `claude plugin marketplace add github:<user>/self-improving-claude` + `claude plugin install self-improving-claude`
5. Update `<user>` placeholders in `docs/anthropic-marketplace-pr.md`
6. Submit the PR to `anthropics/claude-plugins-official` when ready

Those steps are outside the v0.3 implementation plan — they happen after v0.3 is implemented and validated locally.
