# self-improving-claude v0.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship v0.2 of `self-improving-claude` — the reactive `/improve` slash command (uses current-chat context as primary input) plus an `evals/` harness that scores orchestrator proposal quality on 5 hand-crafted fixtures, with a code-grader + model-grader and the first baseline committed.

**Architecture:** `/improve` is a thin user-invoked skill mirroring `/improve-init` but with `mode=reactive`; the chat history is already in Claude's context window when the slash command fires, so no special fetching is required. The eval harness is a separate Python tool that bypasses the interactive skill flow — it reads the same rubric/references/examples the skill uses, assembles them into a JSON-output prompt, drives the Anthropic SDK (Haiku for cost), parses Claude's proposals, and runs a deterministic code-grader plus a model-grader against each.

**Tech Stack:** Python 3 (stdlib for the shipped script as always), `anthropic` SDK + `pytest` for the dev-only eval harness, Markdown + YAML frontmatter for skills.

**Spec:** `docs/superpowers/specs/2026-05-22-self-improving-claude-design.md` is authoritative — §2 (user surface), §7 (eval methodology), §8 (orchestrator prompt structure), §9 (v0.2 slicing) are the load-bearing sections.

**Working directory for every command:** `~/Desktop/Projects/self-improving-claude`

**Branching:** continue on `v0.1-implementation` (12 commits ahead of `main`); after v0.2 lands, merge both versions together and tag.

---

## Task 1: Reactive `/improve` skill

**Files:**
- Create: `skills/improve/SKILL.md`

**Purpose:** The user-invoked entry skill for the reactive workflow. Mirrors `skills/improve-init/SKILL.md` structurally, but primes the orchestrator with `mode=reactive`, uses the current chat as the primary signal, and treats project snapshot / telemetry as supplemental.

Per spec §3.3, this skill is a sibling of `improve-init/SKILL.md`. The orchestrator (`skills/self-improving-claude/SKILL.md`) already supports `mode=reactive` — no orchestrator changes needed.

- [ ] **Step 1: Create the reactive entry skill**

Create `skills/improve/SKILL.md`:

```markdown
---
name: improve
description: Run /improve right after seeing Claude do something you don't want again — uses the current conversation as primary context to propose hooks / permissions.deny rules / CLAUDE.md notes that would have prevented it. Per-proposal user approval.
argument-hint: [optional directive or feedback in quotes, e.g. "block edits to src/migrations" or "the foo-hook blocked something legit"]
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, Skill, AskUserQuestion]
---

# /improve — Reactive Guardrail Proposal

Hand off to the `self-improving-claude` orchestrator with `mode=reactive`. You — the calling skill — gather the inputs below, then invoke the orchestrator (via the `Skill` tool with `skill: "self-improving-claude"`) so it can run its 10-step workflow.

The reactive workflow's primary signal is the **current conversation** — whatever the user saw Claude do that triggered the `/improve` invocation is already in your context window. You don't need to "fetch" the chat; you just need to tell the orchestrator to focus on the recent messages above.

## Step 1 — Gather inputs

**`<user_directive>`** — the literal contents of `$ARGUMENTS`, or empty string. Routing depends on shape:
- empty → default reactive mode (look at recent chat for the most recent observable problem)
- directive ("block edits to migrations/*") → propose specifically against the named target
- feedback ("the foo-hook just blocked something legit") → refine the named existing entry, do not propose new ones

The orchestrator handles classification in its Step 1; you don't pre-classify here.

**`<recent_chat>`** — the most recent ~30 messages of this conversation. You don't read this from a file; it's already in your context. Tell the orchestrator: "review the last ~30 messages above this point for evidence of the problem the user wants prevented." The orchestrator uses this as its primary candidate signal.

**`<project_snapshot>`** — supplemental in reactive mode. Read only if recent chat is thin or the problem clearly hinges on project-specific convention. Same content as `/improve-init` gathers (CLAUDE.md, manifest, README, sampled source). Cap ~5 KB.

**`<telemetry_excerpt>`** — supplemental. The most recent ~50 rows from `.claude/self-improving-claude/telemetry.jsonl` if present; useful when the problem is "Claude has done X repeatedly," less useful for one-off bugs.

**`<transcript_excerpt>`** — empty for reactive mode. The current chat is already the freshest signal; old transcripts add noise.

**`<existing_hooks>`** — the `hooks` block from `.claude/settings.json` (empty `{}` if file missing).

**`<existing_permissions>`** — the `permissions` block from `.claude/settings.json` (empty `{}` if file missing).

If `.claude/settings.json` won't parse, stop here and tell the user — do not invoke the orchestrator with broken state.

## Step 2 — Hand off to the orchestrator

Invoke the `self-improving-claude` skill, passing the inputs you gathered. The orchestrator owns everything from there: routing, inspection, drafting, self-critique, validation, approvals, writes, close-out.

You — the entry skill — do not run those steps yourself. You just gather inputs and call.

## Mode is fixed for this command

`<mode>reactive</mode>` always. The orchestrator uses this to know it should weight `<recent_chat>` over `<project_snapshot>` + `<telemetry_excerpt>`.
```

- [ ] **Step 2: Verify the skill file is well-formed**

Run from repo root:

```bash
f=skills/improve/SKILL.md
head -6 "$f"
fences=$(grep -c '^```' "$f")
echo "fence count: $fences"
test $((fences % 2)) -eq 0 && echo OK || echo "UNBALANCED FENCES"
```

Expected: frontmatter shows `name: improve` and `argument-hint:` + `allowed-tools: [..., Skill, AskUserQuestion]`; fence count is 0 (no code blocks in this file); `OK`.

- [ ] **Step 3: Verify it loads alongside `/improve-init`**

```bash
cd /tmp && claude --plugin-dir ~/Desktop/Projects/self-improving-claude --print "List all available slash commands, one name per line." 2>&1 | grep -E "^(improve|improve-init)$"
```

Expected output (order may vary):
```
improve
improve-init
```

- [ ] **Step 4: Commit**

```bash
git add skills/improve/SKILL.md
git commit -m "Add reactive /improve entry skill (mode=reactive)"
```

---

## Task 2: Eval scaffold — dependencies, dataset schema, first fixture, loader

**Files:**
- Create: `requirements-dev.txt`
- Create: `evals/__init__.py` (empty)
- Create: `evals/fixtures_lib.py`
- Create: `evals/tests/__init__.py` (empty)
- Create: `evals/tests/test_fixtures_lib.py`
- Create: `evals/dataset.json`
- Create: `evals/fixtures/001-pnpm-test-watcher/description.md`
- Create: `evals/fixtures/001-pnpm-test-watcher/expected_traits.json`
- Create: `evals/fixtures/001-pnpm-test-watcher/project/CLAUDE.md`
- Create: `evals/fixtures/001-pnpm-test-watcher/project/package.json`
- Create: `evals/fixtures/001-pnpm-test-watcher/chat.md`
- Create: `evals/fixtures/001-pnpm-test-watcher/telemetry.jsonl`

**Purpose:** Establish the `evals/` directory layout and the data shape. A *fixture* is a self-contained scenario (a planted problem with the project files, chat snippet, and telemetry rows that would surface it). The *dataset* indexes fixtures and pairs each with the expected hook traits the model should produce. `fixtures_lib.py` is the tested loader the runner uses.

`pytest` already runs from previous v0.1 tests; we add `anthropic` for the eval runner. Both are dev-only — the shipped plugin still has zero pip dependencies.

- [ ] **Step 1: Add the dev requirements file**

Create `requirements-dev.txt`:

```
anthropic>=0.40
pytest>=8
```

- [ ] **Step 2: Install dev deps locally**

```bash
pip install -r requirements-dev.txt
```

Expected: both packages install without error. (If your environment already has them, that's fine.)

- [ ] **Step 3: Write the failing fixture-loader tests**

Create `evals/__init__.py` as an empty file:

```bash
mkdir -p evals/tests
touch evals/__init__.py
touch evals/tests/__init__.py
```

Create `evals/tests/test_fixtures_lib.py`:

```python
"""Tests for evals/fixtures_lib.py — fixture loading.

Each fixture is a self-contained directory under evals/fixtures/<id>/.
The loader exposes a typed view of one entry from the dataset.

Run: python3 -m pytest evals/tests/test_fixtures_lib.py -v
"""
import json
from pathlib import Path

import pytest

from evals.fixtures_lib import (
    EVALS_DIR,
    Fixture,
    load_dataset,
    load_fixture,
)


def test_evals_dir_resolves_to_repo_evals():
    # Sanity: the package can locate its own fixtures directory.
    assert EVALS_DIR.name == "evals"
    assert (EVALS_DIR / "dataset.json").exists()


def test_load_dataset_returns_list_of_entries():
    entries = load_dataset()
    assert isinstance(entries, list)
    assert len(entries) >= 1
    first = entries[0]
    # Required fields per spec §7
    assert "id" in first
    assert "trigger" in first
    assert first["trigger"] in ("improve", "improve-init")
    assert "user_args" in first  # may be ""
    assert "fixture" in first
    assert "planted_problem" in first
    assert "expected_hook_traits" in first


def test_load_fixture_001_returns_complete_fixture():
    fx = load_fixture("001-pnpm-test-watcher")
    assert isinstance(fx, Fixture)
    assert fx.id == "001-pnpm-test-watcher"
    assert fx.description.strip() != ""
    assert isinstance(fx.expected_traits, dict)
    assert "event" in fx.expected_traits
    # Project snapshot is a dict {filename → content}
    assert isinstance(fx.project_files, dict)
    assert "CLAUDE.md" in fx.project_files
    assert "package.json" in fx.project_files
    # Chat is a string (markdown body) — may be empty for proactive fixtures.
    assert isinstance(fx.chat, str)
    # Telemetry is a list of dicts (parsed from JSONL).
    assert isinstance(fx.telemetry, list)


def test_load_fixture_raises_clear_error_on_missing():
    with pytest.raises(FileNotFoundError) as ei:
        load_fixture("999-does-not-exist")
    assert "999-does-not-exist" in str(ei.value)


def test_load_fixture_handles_missing_optional_files(tmp_path, monkeypatch):
    """If chat.md or telemetry.jsonl is missing, loader returns empty defaults."""
    # Construct a minimal fixture in tmp_path
    fid = "test-minimal"
    fdir = tmp_path / "fixtures" / fid
    (fdir / "project").mkdir(parents=True)
    (fdir / "description.md").write_text("minimal")
    (fdir / "expected_traits.json").write_text('{"event": "PreToolUse"}')
    (fdir / "project" / "CLAUDE.md").write_text("ok")
    # No chat.md, no telemetry.jsonl, no package.json

    monkeypatch.setattr("evals.fixtures_lib.EVALS_DIR", tmp_path)
    fx = load_fixture(fid)
    assert fx.chat == ""
    assert fx.telemetry == []
    assert "CLAUDE.md" in fx.project_files
    assert "package.json" not in fx.project_files


def test_telemetry_jsonl_parses_each_line(tmp_path, monkeypatch):
    fid = "test-telemetry"
    fdir = tmp_path / "fixtures" / fid
    (fdir / "project").mkdir(parents=True)
    (fdir / "description.md").write_text("t")
    (fdir / "expected_traits.json").write_text('{}')
    telemetry = [
        {"ts": "2026-05-22T10:00:00Z", "tool": "Bash", "args_summary": "pnpm test"},
        {"ts": "2026-05-22T10:01:00Z", "tool": "Read", "args_summary": "/p"},
    ]
    (fdir / "telemetry.jsonl").write_text("\n".join(json.dumps(r) for r in telemetry) + "\n")

    monkeypatch.setattr("evals.fixtures_lib.EVALS_DIR", tmp_path)
    fx = load_fixture(fid)
    assert fx.telemetry == telemetry
```

- [ ] **Step 4: Run the tests to verify they fail**

```bash
python3 -m pytest evals/tests/test_fixtures_lib.py -v
```

Expected: all tests fail with `ModuleNotFoundError` for `evals.fixtures_lib` (the module doesn't exist yet).

- [ ] **Step 5: Implement `evals/fixtures_lib.py`**

Create `evals/fixtures_lib.py`:

```python
"""Fixture & dataset loading for the eval harness.

A fixture lives at evals/fixtures/<id>/ and contains:
- description.md             — planted-problem prose
- expected_traits.json       — what the proposed hook must look like
- project/                   — sampled project files (CLAUDE.md, manifests, etc.)
- chat.md                    — planted recent-chat content (reactive fixtures)
- telemetry.jsonl            — planted telemetry rows (proactive fixtures)

dataset.json indexes fixtures and pairs each with trigger + user_args.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent


@dataclass
class Fixture:
    id: str
    description: str
    expected_traits: dict
    project_files: dict[str, str] = field(default_factory=dict)
    chat: str = ""
    telemetry: list[dict] = field(default_factory=list)


def load_dataset() -> list[dict]:
    """Return the parsed dataset.json as a list of entries."""
    path = EVALS_DIR / "dataset.json"
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return data["entries"] if isinstance(data, dict) else data


def load_fixture(fixture_id: str) -> Fixture:
    """Load one fixture directory into a Fixture dataclass."""
    fdir = EVALS_DIR / "fixtures" / fixture_id
    if not fdir.exists():
        raise FileNotFoundError(f"Fixture not found: {fixture_id} (looked in {fdir})")

    description = (fdir / "description.md").read_text(encoding="utf-8") if (fdir / "description.md").exists() else ""
    expected_traits = json.loads((fdir / "expected_traits.json").read_text(encoding="utf-8"))

    project_files: dict[str, str] = {}
    project_dir = fdir / "project"
    if project_dir.exists():
        for f in sorted(project_dir.rglob("*")):
            if f.is_file():
                rel = f.relative_to(project_dir).as_posix()
                project_files[rel] = f.read_text(encoding="utf-8", errors="replace")

    chat = (fdir / "chat.md").read_text(encoding="utf-8") if (fdir / "chat.md").exists() else ""

    telemetry: list[dict] = []
    tpath = fdir / "telemetry.jsonl"
    if tpath.exists():
        for line in tpath.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            telemetry.append(json.loads(line))

    return Fixture(
        id=fixture_id,
        description=description,
        expected_traits=expected_traits,
        project_files=project_files,
        chat=chat,
        telemetry=telemetry,
    )
```

- [ ] **Step 6: Create dataset.json with the first entry**

Create `evals/dataset.json`:

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
    }
  ]
}
```

- [ ] **Step 7: Create fixture 001 files**

Create `evals/fixtures/001-pnpm-test-watcher/description.md`:

```markdown
# Planted problem — pnpm test watcher trap

Claude has been invoking `pnpm test` directly in this project. The project's
package.json defines `pnpm test` as the interactive Vitest watcher (which
never exits), while `pnpm test:ci` is the non-interactive CI runner Claude
should actually be using.

Telemetry shows 3 recent `pnpm test` invocations that exited with non-zero
codes (Claude killed them after timeout). CLAUDE.md does not currently flag
this.

An ideal proposal blocks `pnpm test` via a PreToolUse Bash hook and steers
Claude to `pnpm test:ci`. A `permissions.deny` rule does NOT fit because
the rule string `Bash(pnpm test)` would also block `pnpm test:ci` (same
prefix).
```

Create `evals/fixtures/001-pnpm-test-watcher/expected_traits.json`:

```json
{
  "form": "command-hook",
  "event": "PreToolUse",
  "matcher": "Bash",
  "blocks_command_prefix": "pnpm test",
  "allows_command": "pnpm test:ci",
  "rationale_must_mention": ["pnpm test:ci", "watcher"]
}
```

Create `evals/fixtures/001-pnpm-test-watcher/project/CLAUDE.md`:

```markdown
# Project conventions

This is a Node project using pnpm. Run lint with `pnpm lint` before committing.
```

Create `evals/fixtures/001-pnpm-test-watcher/project/package.json`:

```json
{
  "name": "fixture-001",
  "version": "0.0.0",
  "scripts": {
    "test": "vitest",
    "test:ci": "vitest run",
    "lint": "eslint ."
  },
  "devDependencies": {
    "vitest": "^1.0.0"
  }
}
```

Create `evals/fixtures/001-pnpm-test-watcher/chat.md`:

```markdown
(Empty — this is a proactive fixture. The orchestrator uses project + telemetry, not chat.)
```

Create `evals/fixtures/001-pnpm-test-watcher/telemetry.jsonl`:

```jsonl
{"ts":"2026-05-20T09:14:02Z","tool":"Bash","args_summary":"pnpm test","outcome":{"exit_code":143,"stderr_head":"timed out after 120s waiting for prompt"}}
{"ts":"2026-05-20T11:32:55Z","tool":"Bash","args_summary":"pnpm test","outcome":{"exit_code":143,"stderr_head":"timed out after 120s waiting for prompt"}}
{"ts":"2026-05-21T15:01:10Z","tool":"Bash","args_summary":"pnpm test","outcome":{"exit_code":143,"stderr_head":"timed out after 120s waiting for prompt"}}
{"ts":"2026-05-21T15:02:30Z","tool":"Read","args_summary":"/project/package.json"}
{"ts":"2026-05-21T15:03:01Z","tool":"Bash","args_summary":"pnpm lint","outcome":{"exit_code":0}}
```

- [ ] **Step 8: Run the tests to verify they pass**

```bash
python3 -m pytest evals/tests/test_fixtures_lib.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 9: Commit**

```bash
git add requirements-dev.txt evals/
git commit -m "Add evals scaffold — fixtures_lib, dataset schema, first fixture (TDD)"
```

---

## Task 3: Code grader (TDD)

**Files:**
- Create: `evals/grade_code.py`
- Create: `evals/tests/test_grade_code.py`

**Purpose:** The deterministic half of the grader. Given a proposal (a dict that Claude produces) and `expected_traits` (from the fixture), score it against syntactic and structural rules — does the script parse, does the matcher fit, does the rationale mention the expected keywords. Each check returns 0 or 10 (course convention from `docs/knowledge/eval-methodology.md`), and the overall code-grade is the mean.

This grader runs pure Python, no API calls, no network. Fast and deterministic — the foundation of the eval signal.

- [ ] **Step 1: Write the failing tests**

Create `evals/tests/test_grade_code.py`:

```python
"""Tests for evals/grade_code.py — deterministic proposal grader.

Each check returns a score 0 or 10. The overall code-grade is the mean.
The proposal dict shape is documented in evals/grade_code.py.

Run: python3 -m pytest evals/tests/test_grade_code.py -v
"""
import pytest

from evals.grade_code import grade_code


PERFECT_BASH_BLOCK_HOOK = {
    "form": "command-hook",
    "event": "PreToolUse",
    "matcher": "Bash",
    "rationale": "Blocks `pnpm test` (interactive watcher); steers Claude to `pnpm test:ci`.",
    "script_lang": "python",
    "script": """import json, sys
def main():
    try:
        ev = json.load(sys.stdin)
    except Exception:
        return 0
    if ev.get("tool_name") != "Bash":
        return 0
    cmd = (ev.get("tool_input") or {}).get("command", "")
    if cmd.strip().startswith("pnpm test") and "test:ci" not in cmd:
        print("Use pnpm test:ci", file=sys.stderr)
        return 2
    return 0
if __name__ == "__main__":
    sys.exit(main())
""",
    "sentinel_name": "self-improving-claude/block-pnpm-test-watcher",
}

EXPECTED_001 = {
    "form": "command-hook",
    "event": "PreToolUse",
    "matcher": "Bash",
    "blocks_command_prefix": "pnpm test",
    "allows_command": "pnpm test:ci",
    "rationale_must_mention": ["pnpm test:ci", "watcher"],
}


def test_perfect_proposal_gets_full_marks():
    result = grade_code(PERFECT_BASH_BLOCK_HOOK, EXPECTED_001)
    assert result["mean"] == 10.0
    # Each individual check should also pass
    for check, score in result["checks"].items():
        assert score == 10, f"Check {check!r} failed unexpectedly"


def test_grade_rejects_wrong_form():
    bad = dict(PERFECT_BASH_BLOCK_HOOK, form="permissions.deny")
    result = grade_code(bad, EXPECTED_001)
    assert result["checks"]["form_matches"] == 0
    assert result["mean"] < 10.0


def test_grade_rejects_wrong_event():
    bad = dict(PERFECT_BASH_BLOCK_HOOK, event="PostToolUse")
    result = grade_code(bad, EXPECTED_001)
    assert result["checks"]["event_matches"] == 0


def test_grade_rejects_wrong_matcher():
    bad = dict(PERFECT_BASH_BLOCK_HOOK, matcher="Write")
    result = grade_code(bad, EXPECTED_001)
    assert result["checks"]["matcher_matches"] == 0


def test_grade_rejects_script_with_syntax_error():
    bad = dict(PERFECT_BASH_BLOCK_HOOK, script="def x(:\n    pass")
    result = grade_code(bad, EXPECTED_001)
    assert result["checks"]["script_parses"] == 0


def test_grade_rejects_missing_sentinel():
    bad = dict(PERFECT_BASH_BLOCK_HOOK, sentinel_name="my-hook")
    result = grade_code(bad, EXPECTED_001)
    assert result["checks"]["sentinel_format"] == 0


def test_grade_rejects_rationale_missing_required_keywords():
    bad = dict(PERFECT_BASH_BLOCK_HOOK, rationale="A nice idea.")
    result = grade_code(bad, EXPECTED_001)
    assert result["checks"]["rationale_keywords"] == 0


def test_grade_handles_permissions_deny_proposal():
    """For form='permissions.deny', there's no script — only the rule string."""
    proposal = {
        "form": "permissions.deny",
        "rule": "Read(**/.env)",
        "rationale": "Blocks .env reads uniformly across tools.",
        "sentinel_name": None,  # permissions.deny rules don't carry sentinels
    }
    expected = {
        "form": "permissions.deny",
        "rule_pattern": "Read(**/.env)",
        "rationale_must_mention": [".env"],
    }
    result = grade_code(proposal, expected)
    assert result["mean"] >= 7.0  # at least 70% of checks pass for a clean match


def test_grade_returns_per_check_dict():
    """Caller needs the breakdown to render scorecards."""
    result = grade_code(PERFECT_BASH_BLOCK_HOOK, EXPECTED_001)
    assert "checks" in result
    assert "mean" in result
    assert isinstance(result["checks"], dict)
    # Specific keys we promise
    for key in ("form_matches", "event_matches", "matcher_matches",
                "script_parses", "sentinel_format", "rationale_keywords"):
        assert key in result["checks"]


def test_grade_script_lang_javascript_parses():
    """If the model picks JS, we still check syntax (with node --check)."""
    proposal = dict(
        PERFECT_BASH_BLOCK_HOOK,
        script_lang="javascript",
        script="""process.stdin.on("data", d => { try { JSON.parse(d); } catch(e) {} });""",
    )
    result = grade_code(proposal, EXPECTED_001)
    # As long as the JS parses, the script_parses check should pass.
    assert result["checks"]["script_parses"] == 10
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest evals/tests/test_grade_code.py -v
```

Expected: all tests fail with `ModuleNotFoundError` for `evals.grade_code`.

- [ ] **Step 3: Implement `evals/grade_code.py`**

Create `evals/grade_code.py`:

```python
"""Deterministic code-based grader for proposed hooks.

Proposal dict shape (produced by the model in eval mode):

  {
    "form": "command-hook" | "prompt-hook" | "permissions.deny" | "claude-md-note",
    "event": "PreToolUse" | "PostToolUse" | ...        (omit for permissions.deny)
    "matcher": "Bash" | "Read|Write" | "*" | ...        (omit for permissions.deny)
    "rationale": str,                                   (one-sentence why)
    "script_lang": "python" | "bash" | "javascript" | None
    "script": str | None,                               (the hook body, if command-hook)
    "prompt": str | None,                               (the prompt body, if prompt-hook)
    "rule": str | None,                                 (the deny string, if permissions.deny)
    "claude_md_line": str | None,                       (the # line, if claude-md-note)
    "sentinel_name": str | None,                        ("self-improving-claude/<slug>")
  }

Each check returns 0 or 10. The overall mean is in result["mean"].
"""
from __future__ import annotations

import ast
import json
import re
import subprocess

SENTINEL_RE = re.compile(r"^self-improving-claude/[a-z][a-z0-9-]*[a-z0-9]$")


def _check_form_matches(p: dict, e: dict) -> int:
    return 10 if p.get("form") == e.get("form") else 0


def _check_event_matches(p: dict, e: dict) -> int:
    if "event" not in e:
        return 10  # not applicable (e.g. permissions.deny)
    return 10 if p.get("event") == e.get("event") else 0


def _check_matcher_matches(p: dict, e: dict) -> int:
    if "matcher" not in e:
        return 10
    return 10 if p.get("matcher") == e.get("matcher") else 0


def _check_script_parses(p: dict, e: dict) -> int:
    form = p.get("form")
    if form != "command-hook":
        return 10  # not applicable
    lang = (p.get("script_lang") or "").lower()
    script = p.get("script") or ""
    if not script:
        return 0
    if lang == "python":
        try:
            ast.parse(script)
            return 10
        except SyntaxError:
            return 0
    if lang == "bash":
        try:
            subprocess.run(["bash", "-n"], input=script, text=True, check=True, capture_output=True)
            return 10
        except (subprocess.CalledProcessError, FileNotFoundError):
            return 0
    if lang in ("javascript", "js", "node"):
        try:
            subprocess.run(["node", "--check", "/dev/stdin"], input=script, text=True, check=True, capture_output=True)
            return 10
        except (subprocess.CalledProcessError, FileNotFoundError):
            return 0
    return 0  # unknown language


def _check_sentinel_format(p: dict, e: dict) -> int:
    if p.get("form") in ("permissions.deny", "claude-md-note"):
        return 10  # these forms don't carry sentinels
    name = p.get("sentinel_name") or ""
    return 10 if SENTINEL_RE.match(name) else 0


def _check_rationale_keywords(p: dict, e: dict) -> int:
    required = e.get("rationale_must_mention") or []
    if not required:
        return 10
    rationale = (p.get("rationale") or "").lower()
    return 10 if all(kw.lower() in rationale for kw in required) else 0


_CHECKS = {
    "form_matches": _check_form_matches,
    "event_matches": _check_event_matches,
    "matcher_matches": _check_matcher_matches,
    "script_parses": _check_script_parses,
    "sentinel_format": _check_sentinel_format,
    "rationale_keywords": _check_rationale_keywords,
}


def grade_code(proposal: dict, expected: dict) -> dict:
    """Return {checks: {name: 0|10}, mean: float}."""
    checks = {name: fn(proposal, expected) for name, fn in _CHECKS.items()}
    mean = sum(checks.values()) / len(checks)
    return {"checks": checks, "mean": mean}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest evals/tests/test_grade_code.py -v
```

Expected: all 10 tests pass.

- [ ] **Step 5: Commit**

```bash
git add evals/grade_code.py evals/tests/test_grade_code.py
git commit -m "Add deterministic code-grader with 10 unit tests"
```

---

## Task 4: Model grader (TDD with mocked Anthropic call)

**Files:**
- Create: `evals/grade_model.py`
- Create: `evals/tests/test_grade_model.py`

**Purpose:** The second grading dimension — does the proposal *actually solve* the planted problem? Code-grader checks form; model-grader checks substance. Asks Haiku to score the proposal against the planted problem with strengths/weaknesses/score JSON, per `docs/knowledge/eval-methodology.md` §3.

For testability, the model-grader takes the Anthropic client as a dependency-injection parameter. Unit tests mock the client; integration tests in Task 5 use the real one.

- [ ] **Step 1: Write the failing tests**

Create `evals/tests/test_grade_model.py`:

```python
"""Tests for evals/grade_model.py — model-based grader.

Mocks the Anthropic client so tests are deterministic and offline.
The real API integration is tested in evals/tests/test_run.py with
@pytest.mark.integration and a real key.

Run: python3 -m pytest evals/tests/test_grade_model.py -v
"""
import json
from types import SimpleNamespace

import pytest

from evals.grade_model import grade_model


class FakeAnthropicClient:
    """Mocks the anthropic.Anthropic client; returns canned responses."""

    def __init__(self, response_text: str, captured_calls: list):
        self.response_text = response_text
        self.captured_calls = captured_calls
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.captured_calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.response_text)])


def test_grade_model_parses_perfect_score():
    captured: list = []
    response = json.dumps({
        "strengths": ["targets the right bug", "specific matcher"],
        "weaknesses": [],
        "reasoning": "Hook correctly identifies pnpm test watcher and suggests test:ci.",
        "score": 10,
    })
    client = FakeAnthropicClient(response, captured)
    result = grade_model(
        proposal={"form": "command-hook", "rationale": "blocks watcher"},
        planted_problem="Claude keeps invoking pnpm test",
        client=client,
    )
    assert result["score"] == 10
    assert result["strengths"] == ["targets the right bug", "specific matcher"]
    assert result["weaknesses"] == []
    assert "reasoning" in result
    # The grader sent exactly one call to Anthropic
    assert len(captured) == 1
    # The model used should be a Haiku family
    assert "haiku" in captured[0]["model"].lower()


def test_grade_model_parses_low_score():
    captured: list = []
    response = json.dumps({
        "strengths": [],
        "weaknesses": ["wrong matcher", "no rationale"],
        "reasoning": "Proposal targets the wrong tool.",
        "score": 3,
    })
    client = FakeAnthropicClient(response, captured)
    result = grade_model(proposal={}, planted_problem="x", client=client)
    assert result["score"] == 3
    assert len(result["weaknesses"]) == 2


def test_grade_model_extracts_json_from_fenced_response():
    """Some models wrap JSON in ```json ... ``` even when asked not to."""
    captured: list = []
    response = """```json
{"strengths": ["a"], "weaknesses": [], "reasoning": "ok", "score": 7}
```"""
    client = FakeAnthropicClient(response, captured)
    result = grade_model(proposal={}, planted_problem="x", client=client)
    assert result["score"] == 7


def test_grade_model_handles_malformed_response_gracefully():
    """If the model returns garbage, we get score 0 + an error note rather than a crash."""
    captured: list = []
    response = "not json at all"
    client = FakeAnthropicClient(response, captured)
    result = grade_model(proposal={}, planted_problem="x", client=client)
    assert result["score"] == 0
    assert "parse_error" in result
    assert isinstance(result["parse_error"], str)


def test_grade_model_clamps_out_of_range_score():
    """Defensive: if model returns score=42 or score=-3, clamp to [0,10]."""
    captured: list = []
    for given, expected in [(42, 10), (-3, 0), (10, 10), (0, 0)]:
        response = json.dumps({"strengths": [], "weaknesses": [], "reasoning": "x", "score": given})
        client = FakeAnthropicClient(response, captured)
        result = grade_model(proposal={}, planted_problem="x", client=client)
        assert result["score"] == expected, f"score={given} should clamp to {expected}"


def test_grade_model_prompt_includes_planted_problem_and_proposal():
    captured: list = []
    response = json.dumps({"strengths": [], "weaknesses": [], "reasoning": "x", "score": 5})
    client = FakeAnthropicClient(response, captured)
    grade_model(
        proposal={"form": "command-hook", "matcher": "Bash"},
        planted_problem="Claude runs pnpm test",
        client=client,
    )
    sent_messages = captured[0]["messages"]
    combined = json.dumps(sent_messages)
    assert "Claude runs pnpm test" in combined
    assert "Bash" in combined
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest evals/tests/test_grade_model.py -v
```

Expected: all tests fail with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `evals/grade_model.py`**

Create `evals/grade_model.py`:

```python
"""Model-based grader: ask Haiku to score how well a proposal solves the planted problem.

The grader prompt (from docs/knowledge/eval-methodology.md §3) asks for
strengths + weaknesses + reasoning + score. Score is clamped to [0, 10].

The Anthropic client is injected so unit tests can mock it. The real
client is used by the eval runner (evals/run.py).
"""
from __future__ import annotations

import json
import re

GRADER_MODEL = "claude-haiku-4-5-20251001"

GRADER_SYSTEM = """You are an expert reviewer of Claude Code hook proposals. \
Evaluate proposals against the planted problem they're supposed to solve. \
Be concrete: name specific strengths and weaknesses. Avoid defaulting to a \
"6 out of 10" — score honestly, with low scores for proposals that don't \
solve the problem and high scores for proposals that do."""

GRADER_TEMPLATE = """<planted_problem>
{planted_problem}
</planted_problem>

<proposed_solution>
{proposal_json}
</proposed_solution>

Respond with a JSON object exactly matching this schema:

{{
  "strengths": [ "1-3 specific things the proposal does right" ],
  "weaknesses": [ "1-3 specific things it misses or does wrong" ],
  "reasoning": "2-3 sentences explaining the score",
  "score": <integer 0 to 10; 10 = exactly solves the planted problem>
}}

Output ONLY the JSON. No prose before or after."""


_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)


def _extract_json(text: str) -> str:
    """Strip ```json``` fences if present; otherwise return text unchanged."""
    m = _FENCE_RE.match(text.strip())
    return m.group(1) if m else text


def grade_model(*, proposal: dict, planted_problem: str, client) -> dict:
    """Grade one proposal. Returns {strengths, weaknesses, reasoning, score, ...}."""
    user_msg = GRADER_TEMPLATE.format(
        planted_problem=planted_problem,
        proposal_json=json.dumps(proposal, indent=2),
    )
    response = client.messages.create(
        model=GRADER_MODEL,
        max_tokens=1024,
        system=GRADER_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = response.content[0].text

    try:
        parsed = json.loads(_extract_json(text))
    except json.JSONDecodeError as e:
        return {
            "strengths": [],
            "weaknesses": [],
            "reasoning": "",
            "score": 0,
            "parse_error": str(e),
            "raw_response": text[:500],
        }

    score = parsed.get("score", 0)
    try:
        score = int(score)
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(10, score))  # clamp

    return {
        "strengths": parsed.get("strengths", []),
        "weaknesses": parsed.get("weaknesses", []),
        "reasoning": parsed.get("reasoning", ""),
        "score": score,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest evals/tests/test_grade_model.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add evals/grade_model.py evals/tests/test_grade_model.py
git commit -m "Add model-based grader (Haiku) with mocked-client unit tests"
```

---

## Task 5: Eval runner — prompt template + assembly + Anthropic invocation

**Files:**
- Create: `evals/prompt_template.md`
- Create: `evals/run.py`
- Create: `evals/tests/test_run.py`

**Purpose:** The orchestrator that ties everything together. For each dataset entry: load the fixture, assemble a prompt that mirrors what the orchestrator skill sees at runtime (rubric, references, examples, fixture inputs), call Anthropic to produce JSON proposals, parse them, run both graders, write per-entry + average scores to `evals/results/<date>.json`.

Bypasses the interactive Claude Code flow — we cannot drive AskUserQuestion approvals headlessly, so the eval prompt asks the model to *output* proposals as JSON instead of going through the skill's per-proposal approval loop. This tests the prompt CONTENT (which is identical to the skill's content — read from disk) without testing the skill's runtime envelope. The smoke test (Phase 4 in v0.1 guide) continues to verify the runtime end-to-end.

Most of the logic in run.py is pure (prompt assembly, parsing) and unit-testable without a network call. The actual Anthropic call is the one piece that touches real API; that's behind an `@pytest.mark.integration` marker.

- [ ] **Step 1: Create the eval prompt template**

Create `evals/prompt_template.md` — uses distinctive `<<<NAME>>>` placeholders for string substitution (cannot use Python `.format()` because the substituted reference files contain raw `{` from JSON examples that would crash the formatter):

````markdown
<role>
You are evaluating which Claude Code guardrails (hooks, permissions.deny rules, CLAUDE.md notes) would best prevent the planted problem described below. Output your proposals as machine-readable JSON. Do NOT propose interactive approvals or write files — just produce the JSON.
</role>

<rubric>
<<<RUBRIC>>>
</rubric>

<hook_reference>
<<<HOOK_PATTERNS>>>

---

<<<TOOLS_REFERENCE>>>

---

<<<SETTINGS_MERGE>>>
</hook_reference>

<examples>
<<<EXAMPLES>>>
</examples>

<mode><<<MODE>>></mode>
<user_directive><<<USER_DIRECTIVE>>></user_directive>

<recent_chat>
<<<RECENT_CHAT>>>
</recent_chat>

<project_snapshot>
<<<PROJECT_SNAPSHOT>>>
</project_snapshot>

<telemetry_excerpt>
<<<TELEMETRY_EXCERPT>>>
</telemetry_excerpt>

<existing_hooks><<<EXISTING_HOOKS>>></existing_hooks>
<existing_permissions><<<EXISTING_PERMISSIONS>>></existing_permissions>

<task>
Based on the inputs above and the rubric, identify up to 3 candidate guardrails. For each, follow the orchestrator's Step 4 — choose the lightest viable form (permissions.deny → prompt-hook → command-hook → CLAUDE.md note). Apply the rubric. Cap each proposal to one event and one matcher.

Output your proposals as a single JSON object with this exact shape, and NOTHING else (no prose, no fences):

{
  "proposals": [
    {
      "form": "permissions.deny" | "prompt-hook" | "command-hook" | "claude-md-note",
      "event": "PreToolUse" | "PostToolUse" | "Stop" | "SubagentStop" | "UserPromptSubmit" | null,
      "matcher": "Bash" | "Read|Write|Edit" | "*" | null,
      "rationale": "one-sentence explanation that names the bug AND why this form",
      "script_lang": "python" | "bash" | "javascript" | null,
      "script": "...full script body..." | null,
      "prompt": "...prompt body for prompt-hooks..." | null,
      "rule": "Read(**/.env)" | null,
      "claude_md_line": "# Some preference..." | null,
      "sentinel_name": "self-improving-claude/<descriptive-slug>" | null
    }
  ]
}

Rules for the output:
- Only include fields that apply to the chosen form (e.g. command-hook has script + sentinel_name; permissions.deny has only rule + rationale).
- The sentinel_name follows the slug rules in <hook_reference> (kebab-case, ≤50 chars).
- Output the JSON object directly — no ```json fence, no prose before or after.
</task>
````

- [ ] **Step 2: Write the failing tests**

Create `evals/tests/test_run.py`:

```python
"""Tests for evals/run.py — prompt assembly and proposal parsing.

The Anthropic-call integration is tested with @pytest.mark.integration
which requires ANTHROPIC_API_KEY in the environment. Skipped by default;
run with: python3 -m pytest evals/tests/test_run.py -m integration

Run unit tests: python3 -m pytest evals/tests/test_run.py -v -m "not integration"
"""
import json
import os
from types import SimpleNamespace

import pytest

from evals.fixtures_lib import load_fixture
from evals.run import (
    assemble_prompt,
    parse_proposals,
    run_one_entry,
)


def test_assemble_prompt_includes_fixture_signals():
    fx = load_fixture("001-pnpm-test-watcher")
    prompt = assemble_prompt(
        mode="proactive",
        user_directive="",
        fixture=fx,
    )
    # The fixture's planted-problem evidence must show up in the prompt
    assert "pnpm test" in prompt
    assert "test:ci" in prompt
    assert "<rubric>" in prompt
    assert "<examples>" in prompt
    # Mode is set
    assert "<mode>proactive</mode>" in prompt
    # Empty user directive renders cleanly
    assert "<user_directive></user_directive>" in prompt


def test_assemble_prompt_pulls_references_from_skill():
    """The prompt must include the SAME references the skill ships — read live from disk."""
    fx = load_fixture("001-pnpm-test-watcher")
    prompt = assemble_prompt(mode="proactive", user_directive="", fixture=fx)
    # A signature line from the rubric
    assert "Mandatory criteria" in prompt
    # A signature line from hook-patterns
    assert "Hook events at a glance" in prompt
    # A signature line from examples
    assert "Worked Examples" in prompt


def test_parse_proposals_extracts_valid_json():
    raw = json.dumps({
        "proposals": [
            {"form": "command-hook", "event": "PreToolUse", "matcher": "Bash",
             "rationale": "x", "script": "import sys", "script_lang": "python",
             "sentinel_name": "self-improving-claude/x"},
        ]
    })
    proposals = parse_proposals(raw)
    assert len(proposals) == 1
    assert proposals[0]["form"] == "command-hook"


def test_parse_proposals_strips_fences():
    raw = "```json\n" + json.dumps({"proposals": [{"form": "permissions.deny", "rule": "Read(**/.env)"}]}) + "\n```"
    proposals = parse_proposals(raw)
    assert proposals[0]["rule"] == "Read(**/.env)"


def test_parse_proposals_returns_empty_on_garbage():
    proposals = parse_proposals("not json")
    assert proposals == []


def test_run_one_entry_uses_mocked_client(monkeypatch, tmp_path):
    """End-to-end with a fake Anthropic client — verifies the pipeline."""
    canned_response = json.dumps({
        "proposals": [{
            "form": "command-hook",
            "event": "PreToolUse",
            "matcher": "Bash",
            "rationale": "Blocks pnpm test (watcher); steers Claude to pnpm test:ci.",
            "script_lang": "python",
            "script": "import sys\ndef main(): return 0\nif __name__=='__main__': sys.exit(main())\n",
            "sentinel_name": "self-improving-claude/block-pnpm-test-watcher",
        }]
    })

    class FakeClient:
        def __init__(self):
            self.messages = SimpleNamespace(create=self._create)

        def _create(self, **kwargs):
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=canned_response)])

    entries = [{
        "id": "001-pnpm-test-watcher",
        "trigger": "improve-init",
        "user_args": "",
        "fixture": "fixtures/001-pnpm-test-watcher",
        "planted_problem": "Claude keeps invoking pnpm test",
        "expected_hook_traits": {
            "form": "command-hook",
            "event": "PreToolUse",
            "matcher": "Bash",
            "rationale_must_mention": ["pnpm test:ci", "watcher"],
        }
    }]

    result = run_one_entry(entries[0], client=FakeClient())
    assert result["id"] == "001-pnpm-test-watcher"
    assert "proposals" in result
    assert "code_grades" in result
    assert "model_grades" in result
    # With the canned proposal that mirrors expected_traits, code_grade should be high
    assert result["code_grades"][0]["mean"] >= 8.0


@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set")
def test_integration_real_api_call():
    """Smoke: a real Haiku call returns parseable proposals.

    Skipped unless ANTHROPIC_API_KEY is set. Costs ~$0.01 per run.
    Run with: python3 -m pytest evals/tests/test_run.py::test_integration_real_api_call -v -s
    """
    from anthropic import Anthropic
    client = Anthropic()
    fx = load_fixture("001-pnpm-test-watcher")
    prompt = assemble_prompt(mode="proactive", user_directive="", fixture=fx)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text
    proposals = parse_proposals(text)
    assert len(proposals) >= 1, f"Got no proposals. Raw: {text[:500]}"
```

- [ ] **Step 3: Run unit tests to verify they fail**

```bash
python3 -m pytest evals/tests/test_run.py -v -m "not integration"
```

Expected: 5 unit tests fail with `ModuleNotFoundError`.

- [ ] **Step 4: Implement `evals/run.py`**

Create `evals/run.py`:

```python
"""Eval runner — drives the orchestrator's prompt content against Anthropic, grades proposals.

Usage:
    python3 -m evals.run                    # run all entries, write evals/results/<date>.json
    python3 -m evals.run --entry 001-...    # run one entry

Requires ANTHROPIC_API_KEY in the environment.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

from evals.fixtures_lib import EVALS_DIR, Fixture, load_dataset, load_fixture
from evals.grade_code import grade_code
from evals.grade_model import grade_model

REPO_ROOT = EVALS_DIR.parent
SKILL_REFS = REPO_ROOT / "skills" / "self-improving-claude" / "references"
PROMPT_TEMPLATE_PATH = EVALS_DIR / "prompt_template.md"

ORCHESTRATOR_MODEL = "claude-haiku-4-5-20251001"

_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)


def _read_ref(name: str) -> str:
    return (SKILL_REFS / name).read_text(encoding="utf-8")


def _format_project_snapshot(files: dict[str, str], cap_bytes: int = 6000) -> str:
    """Render a {filename → content} dict as one inline snapshot, capped in size."""
    parts: list[str] = []
    used = 0
    for name, content in files.items():
        head = f"=== {name} ===\n"
        chunk = head + content + "\n"
        if used + len(chunk) > cap_bytes:
            parts.append(head + "(truncated)\n")
            break
        parts.append(chunk)
        used += len(chunk)
    return "".join(parts).strip() or "(no project files in fixture)"


def _format_telemetry(rows: list[dict]) -> str:
    if not rows:
        return "(no telemetry rows)"
    return "\n".join(json.dumps(r) for r in rows)


def assemble_prompt(*, mode: str, user_directive: str, fixture: Fixture) -> str:
    """Build the full eval prompt from skill references + fixture inputs.

    Uses string replacement (not .format()) because the substituted reference
    files contain raw `{` from JSON examples that would crash the formatter.
    """
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    substitutions = {
        "<<<RUBRIC>>>":              _read_ref("prompt-rubric.md"),
        "<<<HOOK_PATTERNS>>>":       _read_ref("hook-patterns.md"),
        "<<<TOOLS_REFERENCE>>>":     _read_ref("tools-reference.md"),
        "<<<SETTINGS_MERGE>>>":      _read_ref("settings-merge.md"),
        "<<<EXAMPLES>>>":            _read_ref("examples.md"),
        "<<<MODE>>>":                mode,
        "<<<USER_DIRECTIVE>>>":      user_directive,
        "<<<RECENT_CHAT>>>":         fixture.chat.strip() or "(none — proactive run)",
        "<<<PROJECT_SNAPSHOT>>>":    _format_project_snapshot(fixture.project_files),
        "<<<TELEMETRY_EXCERPT>>>":   _format_telemetry(fixture.telemetry),
        "<<<EXISTING_HOOKS>>>":      "{}",
        "<<<EXISTING_PERMISSIONS>>>": "{}",
    }
    out = template
    for marker, value in substitutions.items():
        out = out.replace(marker, value)
    return out


def parse_proposals(text: str) -> list[dict]:
    """Extract proposals from the model's response. Return empty list on parse failure."""
    text = text.strip()
    m = _FENCE_RE.match(text)
    if m:
        text = m.group(1)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(obj, dict) and "proposals" in obj:
        return obj["proposals"] or []
    if isinstance(obj, list):
        return obj
    return []


def run_one_entry(entry: dict, *, client) -> dict:
    """Run one dataset entry end-to-end: assemble → call → parse → grade."""
    fx = load_fixture(entry["id"])
    mode = "reactive" if entry["trigger"] == "improve" else "proactive"
    prompt = assemble_prompt(
        mode=mode,
        user_directive=entry.get("user_args", ""),
        fixture=fx,
    )
    resp = client.messages.create(
        model=ORCHESTRATOR_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text
    proposals = parse_proposals(raw)

    code_grades = [grade_code(p, entry["expected_hook_traits"]) for p in proposals]
    model_grades = [
        grade_model(proposal=p, planted_problem=entry["planted_problem"], client=client)
        for p in proposals
    ]

    return {
        "id": entry["id"],
        "trigger": entry["trigger"],
        "user_args": entry.get("user_args", ""),
        "proposals": proposals,
        "code_grades": code_grades,
        "model_grades": model_grades,
        "raw_response_head": raw[:500],
    }


def _aggregate(per_entry_results: list[dict]) -> dict:
    """Compute dataset-level averages and a flat scorecard."""
    if not per_entry_results:
        return {"average_code": 0, "average_model": 0, "entries": []}

    # If an entry has multiple proposals, take the BEST (max) — credits a strong proposal
    # even when others are weak, which matches the orchestrator's "pick the best candidates" intent.
    per_entry = []
    for r in per_entry_results:
        best_code = max((c["mean"] for c in r["code_grades"]), default=0.0)
        best_model = max((m["score"] for m in r["model_grades"]), default=0)
        per_entry.append({"id": r["id"], "code": best_code, "model": best_model})

    avg_code = sum(p["code"] for p in per_entry) / len(per_entry)
    avg_model = sum(p["model"] for p in per_entry) / len(per_entry)
    return {"average_code": avg_code, "average_model": avg_model, "entries": per_entry}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--entry", help="run only one entry by id")
    args = parser.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 2

    from anthropic import Anthropic  # local import so tests don't need the package
    client = Anthropic()

    entries = load_dataset()
    if args.entry:
        entries = [e for e in entries if e["id"] == args.entry]
        if not entries:
            print(f"No entry with id={args.entry}", file=sys.stderr)
            return 2

    per_entry_results = []
    for entry in entries:
        print(f"Running {entry['id']}...", file=sys.stderr)
        per_entry_results.append(run_one_entry(entry, client=client))

    agg = _aggregate(per_entry_results)
    output = {
        "date": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": ORCHESTRATOR_MODEL,
        "results": per_entry_results,
        "summary": agg,
    }

    results_dir = EVALS_DIR / "results"
    results_dir.mkdir(exist_ok=True)
    out_path = results_dir / f"{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d')}.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nResults written to {out_path}")
    print(f"Average code score:  {agg['average_code']:.1f}/10")
    print(f"Average model score: {agg['average_model']:.1f}/10")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run unit tests to verify they pass**

```bash
python3 -m pytest evals/tests/test_run.py -v -m "not integration"
```

Expected: 5 unit tests pass (the integration test is skipped without `ANTHROPIC_API_KEY`).

- [ ] **Step 6: Commit**

```bash
git add evals/prompt_template.md evals/run.py evals/tests/test_run.py
git commit -m "Add eval runner — prompt assembly, Anthropic invocation, grading orchestration"
```

---

## Task 6: Four more fixtures (002–005)

**Files:**
- Create: `evals/fixtures/002-block-env-reads/` (full fixture set: description.md, expected_traits.json, project/CLAUDE.md, chat.md, telemetry.jsonl)
- Create: `evals/fixtures/003-prisma-generated-protection/` (same set)
- Create: `evals/fixtures/004-recursion-prevention/` (same set)
- Create: `evals/fixtures/005-format-on-write/` (same set)
- Modify: `evals/dataset.json` (add 4 entries)

**Purpose:** Reach 5 dataset entries per spec §7. Each fixture covers a different `form` to give the grader broad signal:

- 001 — command-hook (already exists, pnpm test watcher)
- 002 — `permissions.deny` (.env reads)
- 003 — `permissions.deny` (Prisma generated files — modeled on the user's real uigen result)
- 004 — prompt-hook (recursion-error prevention — the case the user wanted to test)
- 005 — command-hook on `PostToolUse` (Python format-on-write)

This spread also tests that the orchestrator picks the *lightest viable form* per the rubric.

- [ ] **Step 1: Create fixture 002 (block .env reads via permissions.deny)**

```bash
mkdir -p evals/fixtures/002-block-env-reads/project
```

Create `evals/fixtures/002-block-env-reads/description.md`:

```markdown
# Planted problem — Claude reads .env files

The user has flagged that Claude has been reading `.env` and `.env.local` files
during normal work. They want these blocked uniformly across Read, Grep, and
Glob tools. Telemetry confirms three recent `Read(/project/.env)` calls.

The ideal proposal is a single `permissions.deny` glob rule (or pair —
`.env` and `.env.*`) since this is exactly the use case a glob expresses
uniformly across all tools. A `PreToolUse` hook on `Read` alone would miss
`Grep`/`Glob` over the same files.
```

Create `evals/fixtures/002-block-env-reads/expected_traits.json`:

```json
{
  "form": "permissions.deny",
  "rule_pattern": "Read(**/.env)",
  "rationale_must_mention": [".env"]
}
```

Create `evals/fixtures/002-block-env-reads/project/CLAUDE.md`:

```markdown
# Project notes

A Next.js app. Secrets live in .env.local; .env is checked-in but only with example values.
```

Create `evals/fixtures/002-block-env-reads/chat.md`:

```markdown
(Empty — proactive fixture.)
```

Create `evals/fixtures/002-block-env-reads/telemetry.jsonl`:

```jsonl
{"ts":"2026-05-19T08:01:14Z","tool":"Read","args_summary":"/project/.env"}
{"ts":"2026-05-20T10:32:01Z","tool":"Read","args_summary":"/project/.env.local"}
{"ts":"2026-05-21T14:47:20Z","tool":"Read","args_summary":"/project/.env"}
```

- [ ] **Step 2: Create fixture 003 (Prisma generated protection)**

```bash
mkdir -p evals/fixtures/003-prisma-generated-protection/project/prisma
mkdir -p evals/fixtures/003-prisma-generated-protection/project/src/generated/prisma
```

Create `evals/fixtures/003-prisma-generated-protection/description.md`:

```markdown
# Planted problem — Claude edits the regenerated Prisma client

This is a Next.js + Prisma project. `src/generated/prisma/` is the Prisma
client output — it is regenerated by `prisma generate` and should never be
hand-edited. `prisma/dev.db` is a SQLite binary; schema changes go through
migrations, never direct writes.

CLAUDE.md explicitly says "do not edit src/generated/prisma." But there is
no enforcement.

Ideal proposal: `permissions.deny` rules blocking `Edit(src/generated/prisma/**)`,
`Write(src/generated/prisma/**)`, `Edit(prisma/dev.db)`, `Write(prisma/dev.db)`.
A single proposal containing the deny rules is fine; the grader checks for
the presence of the protective glob.
```

Create `evals/fixtures/003-prisma-generated-protection/expected_traits.json`:

```json
{
  "form": "permissions.deny",
  "rule_pattern": "Edit(src/generated/prisma/**)",
  "rationale_must_mention": ["prisma", "generated"]
}
```

Create `evals/fixtures/003-prisma-generated-protection/project/CLAUDE.md`:

```markdown
# Project conventions

This is a Next.js 14 + Prisma project.

- Run lint: `pnpm lint`
- Run tests: `pnpm test:ci`
- Do NOT edit `src/generated/prisma/` — it is regenerated by `prisma generate`.
- Do NOT write to `prisma/dev.db` directly — schema changes go through `prisma migrate`.
```

Create `evals/fixtures/003-prisma-generated-protection/project/prisma/schema.prisma`:

```
generator client {
  provider = "prisma-client-js"
  output   = "../src/generated/prisma"
}

datasource db {
  provider = "sqlite"
  url      = "file:./dev.db"
}

model User {
  id    Int    @id @default(autoincrement())
  email String @unique
}
```

Create `evals/fixtures/003-prisma-generated-protection/project/src/generated/prisma/index.d.ts`:

```ts
// auto-generated, do not edit
export class PrismaClient {}
```

Create `evals/fixtures/003-prisma-generated-protection/chat.md`:

```markdown
(Empty — proactive fixture.)
```

Create `evals/fixtures/003-prisma-generated-protection/telemetry.jsonl`:

```jsonl
{"ts":"2026-05-20T12:00:00Z","tool":"Edit","args_summary":"/project/src/generated/prisma/index.d.ts"}
```

- [ ] **Step 3: Create fixture 004 (recursion-error prevention — REACTIVE)**

```bash
mkdir -p evals/fixtures/004-recursion-prevention/project/src
```

Create `evals/fixtures/004-recursion-prevention/description.md`:

```markdown
# Planted problem — Claude wrote recursive code that overflowed

The user pasted a traceback showing a RecursionError in `walk_tree()` — a
function Claude just refactored from iteration to recursion in a way that
loses the depth bound. The user wants a guardrail so Claude pauses before
introducing recursive helpers in this codebase.

This is a **reactive** fixture — the planted problem is in chat.md (recent
conversation), not in code or telemetry.

The check needs reasoning (recognizing "added recursion without a depth
bound" across novel code shapes) — `permissions.deny` cannot express this,
and a command hook would need brittle regex. A **prompt-hook** on
`PreToolUse` matching `Write|Edit|MultiEdit` is the right shape.
```

Create `evals/fixtures/004-recursion-prevention/expected_traits.json`:

```json
{
  "form": "prompt-hook",
  "event": "PreToolUse",
  "matcher_must_include": ["Edit", "Write"],
  "rationale_must_mention": ["recursion"]
}
```

Create `evals/fixtures/004-recursion-prevention/project/CLAUDE.md`:

```markdown
# Project conventions

Pure-Python tree-walking project. The walk_tree helper used to be iterative.
```

Create `evals/fixtures/004-recursion-prevention/project/src/tree.py`:

```python
def walk_tree(node, visit):
    """Iterative DFS — depth-bounded by the worklist size."""
    worklist = [node]
    while worklist:
        cur = worklist.pop()
        visit(cur)
        worklist.extend(cur.children)
```

Create `evals/fixtures/004-recursion-prevention/chat.md`:

```markdown
USER: Can you refactor walk_tree to be recursive — easier to read.

CLAUDE: [Edits src/tree.py]

```python
def walk_tree(node, visit):
    visit(node)
    for child in node.children:
        walk_tree(child, visit)
```

USER: Now my test is failing with RecursionError: maximum recursion depth exceeded. I had a tree with 2000 leaves. Can you put a guardrail in so you don't make this mistake again — anywhere in this codebase, not just walk_tree.
```

Create `evals/fixtures/004-recursion-prevention/telemetry.jsonl`:

```jsonl
{"ts":"2026-05-22T16:00:01Z","tool":"Edit","args_summary":"/project/src/tree.py"}
{"ts":"2026-05-22T16:00:30Z","tool":"Bash","args_summary":"python -m pytest","outcome":{"exit_code":1,"stderr_head":"RecursionError: maximum recursion depth exceeded"}}
```

- [ ] **Step 4: Create fixture 005 (Python format-on-write)**

```bash
mkdir -p evals/fixtures/005-format-on-write/project/src
```

Create `evals/fixtures/005-format-on-write/description.md`:

```markdown
# Planted problem — Python files aren't being formatted after Claude edits

The project uses `ruff format` as the formatter (per CLAUDE.md). Telemetry
shows recent Edits to `src/*.py` files with no formatting follow-up;
subsequent `pnpm lint`-equivalent (`ruff check`) runs flagged formatting
issues.

Ideal proposal: a `PostToolUse` command-hook on `Write|Edit|MultiEdit` that
runs `ruff format` on the affected file. Cannot be a prompt-hook because
PostToolUse doesn't support prompt-type. Cannot be permissions.deny — this
is a follow-up action, not a block.
```

Create `evals/fixtures/005-format-on-write/expected_traits.json`:

```json
{
  "form": "command-hook",
  "event": "PostToolUse",
  "matcher": "Write|Edit|MultiEdit",
  "rationale_must_mention": ["ruff", "format"]
}
```

Create `evals/fixtures/005-format-on-write/project/CLAUDE.md`:

```markdown
# Project conventions

Pure-Python project. Format with `ruff format`; lint with `ruff check`.
```

Create `evals/fixtures/005-format-on-write/project/pyproject.toml`:

```toml
[tool.ruff]
line-length = 100

[tool.ruff.format]
quote-style = "double"
```

Create `evals/fixtures/005-format-on-write/project/src/main.py`:

```python
def hello(name):
   print(f'hi {name}')
```

Create `evals/fixtures/005-format-on-write/chat.md`:

```markdown
(Empty — proactive fixture.)
```

Create `evals/fixtures/005-format-on-write/telemetry.jsonl`:

```jsonl
{"ts":"2026-05-21T09:00:00Z","tool":"Edit","args_summary":"/project/src/main.py"}
{"ts":"2026-05-21T09:01:00Z","tool":"Bash","args_summary":"ruff check","outcome":{"exit_code":1,"stderr_head":"src/main.py:2: indentation contains mixed spaces and tabs"}}
{"ts":"2026-05-21T13:00:00Z","tool":"Edit","args_summary":"/project/src/main.py"}
{"ts":"2026-05-21T13:01:00Z","tool":"Bash","args_summary":"ruff check","outcome":{"exit_code":1,"stderr_head":"src/main.py:2: indentation"}}
```

- [ ] **Step 5: Add the 4 new entries to dataset.json**

Replace `evals/dataset.json` with:

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
    }
  ]
}
```

- [ ] **Step 6: Verify dataset.json parses and all fixtures load**

```bash
python3 -c "from evals.fixtures_lib import load_dataset, load_fixture; ds = load_dataset(); print(f'{len(ds)} entries'); [load_fixture(e['id']) for e in ds]; print('all fixtures load')"
```

Expected:
```
5 entries
all fixtures load
```

- [ ] **Step 7: Update fixture-loader tests for additional ids (optional sanity)**

Run the existing test suite to confirm nothing regressed:

```bash
python3 -m pytest evals/ -v -m "not integration"
```

Expected: all eval unit tests still pass (21 of them across all test files), 1 integration test skipped.

- [ ] **Step 8: Commit**

```bash
git add evals/fixtures/ evals/dataset.json
git commit -m "Add fixtures 002-005: env-reads, prisma-generated, recursion (reactive), format-on-write"
```

---

## Task 7: Run baseline + extend orchestrator's prompt-hook bias (if needed) + ship docs

**Files:**
- Create: `evals/results/2026-05-22-baseline.json` (generated, then committed)
- Modify: `skills/self-improving-claude/SKILL.md` (only if baseline shows prompt-hook bias is too weak; otherwise leave)
- Modify: `README.md` (mention `/improve`, evals, status update)
- Modify: `docs/superpowers/specs/2026-05-22-self-improving-claude-design.md` (update §9 — v0.2 ships)

**Purpose:** Run the eval against all 5 entries, commit the first baseline scores, update docs to reflect v0.2 status. If the baseline shows the model is under-using prompt-hooks where the event supports them (e.g. fixture 004 produces a command-hook instead), tighten the rubric's Step 4 bias.

This task uses a real Anthropic API call (~$0.05 total). Requires `ANTHROPIC_API_KEY`.

- [ ] **Step 1: Confirm the API key is set**

```bash
test -n "$ANTHROPIC_API_KEY" && echo "API key set: ✓" || echo "Set ANTHROPIC_API_KEY first"
```

Expected: `API key set: ✓`. If not, export it before continuing.

- [ ] **Step 2: Run the eval and write the baseline**

```bash
python3 -m evals.run 2>&1 | tail -20
```

Expected: 5 entries run, results written to `evals/results/2026-05-22.json` (or current date), and summary lines like:

```
Running 001-pnpm-test-watcher...
Running 002-block-env-reads...
...
Average code score:  X.X/10
Average model score: Y.Y/10
```

- [ ] **Step 3: Inspect the baseline**

```bash
python3 -c "
import json
from pathlib import Path
res = sorted(Path('evals/results').glob('*.json'))[-1]
data = json.loads(res.read_text())
print(f'File: {res}')
print(f\"Average code:  {data['summary']['average_code']:.1f}/10\")
print(f\"Average model: {data['summary']['average_model']:.1f}/10\")
print()
for e in data['summary']['entries']:
    print(f\"  {e['id']:40} code={e['code']:>4.1f}  model={e['model']:>2}\")
"
```

Expected output similar to:

```
File: evals/results/2026-05-22.json
Average code:  8.2/10
Average model: 7.6/10

  001-pnpm-test-watcher                      code= 9.0  model= 8
  002-block-env-reads                        code= 8.0  model= 9
  003-prisma-generated-protection            code= 8.0  model= 8
  004-recursion-prevention                   code= 7.0  model= 7
  005-format-on-write                        code= 9.0  model= 8
```

(Exact numbers vary — that's expected; we're establishing a baseline, not hitting a target.)

If average code < 6/10 OR fixture 004 produces a non-prompt-hook form (which is the spec's v0.2 explicit requirement: "default to prompt where event supports it"), continue to Step 4. Otherwise skip to Step 5.

- [ ] **Step 4 (CONDITIONAL — only if baseline reveals a bias gap): Tighten the orchestrator's Step 4 prompt-hook bias**

Open `skills/self-improving-claude/SKILL.md` and replace the Step 4 section:

```markdown
## Step 4 — Choose the lightest form that does the job

For each candidate, decide what shape the guardrail should take. The options, roughly from lightest to heaviest:

- `permissions.deny` rule — when a glob can express the rule uniformly
- prompt-based hook (`"type": "prompt"`) — when the check needs reasoning AND the event supports prompt hooks (PreToolUse, Stop, SubagentStop, UserPromptSubmit)
- command hook (`"type": "command"`) — when the check is fast and deterministic, or when the event doesn't support prompt hooks (PostToolUse, SessionStart, etc.)
- a soft note that the user pastes into `CLAUDE.md` themselves — when the rule is taste-level, not safety-level

Prefer the lighter form when both would work. Lighter means cheaper to run, easier to audit, less code to maintain. But don't strain to make a glob fit a rule that genuinely needs logic — the priority is a guide, not an algorithm.

If you're genuinely on the fence between two forms for the same candidate (typically `permissions.deny` vs. a prompt hook), use `AskUserQuestion` to let the user pick — they know whether they'd rather have a stricter broad rule or a smarter narrow one.
```

with:

```markdown
## Step 4 — Choose the lightest form that does the job

For each candidate, decide what shape the guardrail should take. The options, roughly from lightest to heaviest:

- `permissions.deny` rule — when a glob can express the rule uniformly across tools
- prompt-based hook (`"type": "prompt"`) — when the check needs *reasoning* (recognizing intent, classifying novel input shapes, judging context) AND the event supports prompt hooks (PreToolUse, Stop, SubagentStop, UserPromptSubmit). **Prefer this over command-hooks whenever the event supports it** — prompt hooks are cheaper to author, easier for the user to audit, and degrade more gracefully on novel input than brittle regex/AST checks.
- command hook (`"type": "command"`) — only when the check is genuinely deterministic and fast (e.g. "block any Bash starting with `rm -rf /`"), OR when the event doesn't support prompt hooks (PostToolUse, SessionStart, etc., need a command hook for formatters/linters/loggers).
- a soft note that the user pastes into `CLAUDE.md` themselves — when the rule is taste-level, not safety-level.

Prefer the lighter form when both would work. Lighter means cheaper to run, easier to audit, less code to maintain. But don't strain to make a glob fit a rule that genuinely needs logic — the priority is a guide, not an algorithm.

If you're genuinely on the fence between two forms for the same candidate (typically `permissions.deny` vs. a prompt hook, OR prompt-hook vs. command-hook for a PreToolUse check that *could* be deterministic but is brittle), use `AskUserQuestion` to let the user pick — they know whether they'd rather have a stricter broad rule, a smarter narrow one, or a brittle but fast deterministic check.
```

Then re-run the eval:

```bash
python3 -m evals.run 2>&1 | tail -10
```

Compare scores. If fixture 004 now produces a prompt-hook, the bias change worked. Either way, take the latest result file as the v0.2 baseline.

- [ ] **Step 5: Rename and commit the baseline**

```bash
BASELINE=$(ls -t evals/results/*.json | head -1)
mv "$BASELINE" evals/results/2026-05-22-baseline.json
git add evals/results/2026-05-22-baseline.json
git status --short
```

If Step 4's conditional changes were made, also stage those:

```bash
git add skills/self-improving-claude/SKILL.md
```

Commit:

```bash
git commit -m "Add v0.2 baseline eval scores (5 entries)"
```

- [ ] **Step 6: Update the README to reflect v0.2**

Open `README.md` and replace the **Status** line near the top:

```markdown
**Status:** v0.1.0 — `/improve-init` (proactive scan) works end-to-end. `/improve` (reactive) is v0.2.
```

with:

```markdown
**Status:** v0.2.0 — `/improve-init` (proactive scan) AND `/improve` (reactive) both work end-to-end. Eval harness with 5 fixtures and a committed baseline scorecard.
```

In the **Usage** section, after the `/improve-init` block, add:

```markdown
### `/improve`

Run *right after* seeing Claude do something you don't want again. Unlike `/improve-init`, this command uses the **current conversation** as its primary signal — the bug you just saw is already in scrollback, and the orchestrator looks there first.

```
/improve
/improve "add a guardrail against unbounded recursion"
/improve "the foo-hook just blocked something legit"
```

Accepts free-text args for directives or feedback; otherwise scans recent chat for the most-recent observable problem.
```

In the **Roadmap** section, replace the v0.1 / v0.2 / v0.3 block with:

```markdown
- **v0.1** — `/improve-init` proactive scan, per-proposal approval, bundled telemetry hook.
- **v0.2** (current) — `/improve` reactive mode; `evals/` harness with 5 fixtures and committed scored baselines; orchestrator biased toward prompt-based hooks where the event supports them.
- **v0.3+** — formal feedback channel (`/improve "the foo-hook blocked something legit"` becomes a structured log), expanded eval coverage, marketplace publish.
```

- [ ] **Step 7: Update the spec's §9 MVP slicing to mark v0.2 shipped**

Open `docs/superpowers/specs/2026-05-22-self-improving-claude-design.md` and find the §9 v0.2.0 block. Replace:

```markdown
### v0.2.0 — "reactive mode and measurement"

- `skills/improve/SKILL.md` (reactive mode).
- `$ARGUMENTS` routing across both commands.
- `evals/` with 5 entries + code-grader + model-grader; first scored baseline committed.
- Generated hooks default to `"type": "prompt"` where the event supports it.
```

with:

```markdown
### v0.2.0 — "reactive mode and measurement" (✅ shipped)

- ✅ `skills/improve/SKILL.md` (reactive mode).
- ✅ `$ARGUMENTS` routing across both commands (orchestrator Step 1 already handles this since v0.1).
- ✅ `evals/` with 5 entries + code-grader + model-grader; baseline committed at `evals/results/2026-05-22-baseline.json`.
- ✅ Orchestrator's Step 4 explicitly biases toward `"type": "prompt"` where the event supports it.
```

- [ ] **Step 8: Run all tests one final time**

```bash
python3 -m pytest -v -m "not integration"
```

Expected: 22 v0.1 telemetry tests + 6 fixture-loader tests + 10 code-grader tests + 6 model-grader tests + 5 run.py unit tests = **49 tests pass**, integration test skipped.

- [ ] **Step 9: Commit docs and tag v0.2.0**

```bash
git add README.md docs/superpowers/specs/2026-05-22-self-improving-claude-design.md
git commit -m "v0.2: update README usage section + mark spec §9 v0.2 shipped"
git tag -a v0.2.0 -m "v0.2.0 — reactive /improve + 5-fixture eval baseline"
git log --oneline -8
```

v0.2.0 is shipped. The reactive `/improve` is in user's hands; the eval harness is the measurement substrate for all future orchestrator-prompt changes.
