# self-improving-claude v0.3.3 — Measurement & Correctness Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pay down the measurement and correctness debt that accumulated across v0.3.1/v0.3.2 — fix the just-shipped leaky `imperative_stderr` grader, make the frontier eval baselines reproducible, finally re-score the dataset, and close two small correctness gaps (a dangling skill reference and undifferentiated telemetry) — without introducing any new architecture.

**Architecture:** Five independent, low-risk fixes plus a release task. No new product capability, no dual-copy edits (every change is in a single-source file: `grade_code.py`, `telemetry.py`, a new `client_claude_cli.py`, the single `improve-uninstall` skill). The headline structural work (composed PostToolUse+Stop hooks) stays in v0.4 — see `docs/superpowers/plans/2026-05-24-self-improving-claude-v0.4-backlog.md`.

**Tech Stack:** Python 3.10+ (stdlib only for shipped code; `pytest` for tests), Claude Code hooks/skills, the existing `evals/` harness (Ollama / Anthropic SDK / new `claude --print` backends).

**Why v0.3.3 exists:** v0.3.2's CHANGELOG states it made imperative-stderr "as strong as text alone can be" — the text-discipline lever is spent. But v0.3.2 (a) shipped a grader check that is blind to the dominant stderr idiom, (b) re-scored nothing, and (c) left the frontier baselines living in `/tmp`. This release makes the v0.3.1+v0.3.2 work *measurable and reproducible* so v0.4's structural change lands on solid ground.

---

## File Structure

| File | Create / Modify | Responsibility |
|---|---|---|
| `evals/grade_code.py` | Modify (`~line 113`) | Replace the leaky `_STDERR_PRINT_RE` with a multi-language stderr-literal extractor (f-strings, bash `echo`/`printf`, JS `console.error`/template literals). |
| `evals/tests/test_grade_code.py` | Modify (append) | New failing-then-passing tests covering the f-string / bash / JS blind spots. |
| `evals/client_claude_cli.py` | **Create** | `ClaudeCliClient` — wraps `claude --print` as a drop-in for `anthropic.Anthropic` / `OllamaClient`. Productizes `/tmp/eval_via_cli.py`. |
| `evals/tests/test_client_claude_cli.py` | **Create** | Unit tests mocking `subprocess.run` (mirrors `test_client_ollama.py`). |
| `evals/run.py` | Modify (`~line 161-175`) | Add `claude-cli` to backend selection + error/usage strings. |
| `plugin/skills/improve-uninstall/SKILL.md` | Modify (`line 56`) | Remove the dangling `@references/settings-merge.md` (no `references/` dir exists under this skill); describe the discipline inline. |
| `plugin/scripts/telemetry.py` | Modify (`~line 39-46`) | Capture `kind` (Notification), `reason` (PreCompact), `source` (SessionStart) so `/improve-init` can actually distinguish permission-nags from idle. |
| `plugin/scripts/tests/test_telemetry.py` | Modify (append) | Tests for the new discriminating fields. |
| `evals/results/2026-05-24-v0.3.3-gemma.json` | **Create** (generated) | Fresh baseline with the 8-check grader (regression guard). |
| `evals/results/README.md` | Modify | Add the v0.3.3 column + delta note. |
| `plugin/.claude-plugin/plugin.json` | Modify | Version `0.3.2` → `0.3.3`. |
| `CHANGELOG.md` | Modify (prepend entry) | `[0.3.3]` section. |

---

## Task 1: Fix the leaky `imperative_stderr` stderr extractor

**Context:** `evals/grade_code.py:113` defines `_STDERR_PRINT_RE = re.compile(r'print\s*\(\s*["\']...')`. The `\s*["\']` right after `print(` requires a quote immediately following the paren, so it only matches plain-string `print("...", file=sys.stderr)`. It returns **`[]` (→ check scores 10 "n/a")** for f-strings (`print(f"...")` — the idiom Example 4 itself uses), bash `echo "..." >&2`, and JS `console.error("...")`. That means the check can FALSE-PASS a passive message hidden in an f-string — the exact failure it was built to catch.

**Files:**
- Modify: `evals/grade_code.py:113-116` (the `_STDERR_PRINT_RE` definition) and `evals/grade_code.py:143-144` (where `_check_imperative_stderr` extracts strings)
- Test: `evals/tests/test_grade_code.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `evals/tests/test_grade_code.py`:

```python
# --- imperative_stderr: multi-language / f-string coverage (v0.3.3) ---

def test_imperative_stderr_catches_banned_word_in_fstring():
    """A passive word hidden in an f-string must be caught (was a false pass pre-v0.3.3)."""
    proposal = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Edit",
        "script": 'import sys\nprint(f"Audit the {n} callers of {name}.", file=sys.stderr)\n',
        "script_lang": "python",
        "rationale": "x",
        "sentinel_name": "self-improving-claude/x",
    }
    result = grade_code(proposal, EXPECTED_HOOK)
    assert result["checks"]["imperative_stderr"] == 0


def test_imperative_stderr_requires_action_phrase_in_fstring_only_message():
    """Non-blocking stderr that is ONLY a neutral f-string (no action phrase) fails."""
    proposal = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Edit",
        "script": 'import sys\nprint(f"Found {n} references.", file=sys.stderr)\n',
        "script_lang": "python",
        "rationale": "x",
        "sentinel_name": "self-improving-claude/x",
    }
    result = grade_code(proposal, EXPECTED_HOOK)
    assert result["checks"]["imperative_stderr"] == 0


def test_imperative_stderr_passes_imperative_fstring():
    """An action-forcing f-string passes (it was previously scored n/a by accident)."""
    proposal = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Edit",
        "script": 'import sys\nprint(f"BLOCKING: {n} stale refs. Fix each. Do not stop.", file=sys.stderr)\n',
        "script_lang": "python",
        "rationale": "x",
        "sentinel_name": "self-improving-claude/x",
    }
    result = grade_code(proposal, EXPECTED_HOOK)
    assert result["checks"]["imperative_stderr"] == 10


def test_imperative_stderr_catches_passive_bash_echo():
    """Bash hooks that echo passive text to stderr must be caught."""
    proposal = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Edit",
        "script": 'echo "consider reviewing these references" >&2\nexit 2\n',
        "script_lang": "bash",
        "rationale": "x",
        "sentinel_name": "self-improving-claude/x",
    }
    result = grade_code(proposal, EXPECTED_HOOK)
    assert result["checks"]["imperative_stderr"] == 0


def test_imperative_stderr_catches_passive_console_error():
    """JS hooks using console.error with passive text must be caught."""
    proposal = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Edit",
        "script": 'console.error("Audit these usages");\nprocess.exit(2);\n',
        "script_lang": "javascript",
        "rationale": "x",
        "sentinel_name": "self-improving-claude/x",
    }
    result = grade_code(proposal, EXPECTED_HOOK)
    assert result["checks"]["imperative_stderr"] == 0


def test_imperative_stderr_passes_imperative_js_template_literal():
    """A JS template literal with an action phrase passes."""
    proposal = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Edit",
        "script": 'console.error(`BLOCKING: ${n} refs. Fix each. Do not stop.`);\n',
        "script_lang": "javascript",
        "rationale": "x",
        "sentinel_name": "self-improving-claude/x",
    }
    result = grade_code(proposal, EXPECTED_HOOK)
    assert result["checks"]["imperative_stderr"] == 10


def test_imperative_stderr_adjacent_stdout_print_not_scanned():
    """A stdout print's text must not bleed into the stderr scan."""
    proposal = {
        "form": "command-hook",
        "event": "PostToolUse",
        "matcher": "Edit",
        "script": (
            'import sys\n'
            'print("audit summary")\n'                      # stdout — must be ignored
            'print(f"BLOCKING: {n}. Fix each. Do not stop.", file=sys.stderr)\n'
        ),
        "script_lang": "python",
        "rationale": "x",
        "sentinel_name": "self-improving-claude/x",
    }
    result = grade_code(proposal, EXPECTED_HOOK)
    # "audit" lives only on the stdout line — must NOT trigger the banned check.
    assert result["checks"]["imperative_stderr"] == 10
```

- [ ] **Step 2: Run the new tests to verify they fail against the current regex**

Run: `python3 -m pytest evals/tests/test_grade_code.py -k imperative_stderr -v`
Expected: the 5 discriminating tests FAIL —
`test_imperative_stderr_catches_banned_word_in_fstring`,
`test_imperative_stderr_requires_action_phrase_in_fstring_only_message`,
`test_imperative_stderr_catches_passive_bash_echo`,
`test_imperative_stderr_catches_passive_console_error`,
`test_imperative_stderr_adjacent_stdout_print_not_scanned`
all return `10` where the test asserts `0` (or vice-versa). The two `passes_imperative_*` tests may already pass — that is fine.

- [ ] **Step 3: Replace the extractor in `evals/grade_code.py`**

Replace the current block (lines ~113-116):

```python
_STDERR_PRINT_RE = re.compile(
    r'print\s*\(\s*["\']([^"\']+)["\'].*?file\s*=\s*sys\.stderr',
    re.DOTALL,
)
```

with:

```python
# Stderr-writing calls across the three languages we generate.
_JS_STDERR_CALL_RE = re.compile(r"console\.error\s*\((.*?)\)", re.DOTALL)
_SH_STDERR_CALL_RE = re.compile(r"(?:echo|printf)\b(.*?)>&\s*2", re.DOTALL)
# String literals: double / single / backtick. f-, r-, b- prefixes sit OUTSIDE
# the quote, so capturing the quoted span works regardless of prefix.
_STRING_LITERAL_RE = re.compile(r'"([^"]*)"|\'([^\']*)\'|`([^`]*)`')


def _extract_stderr_strings(script: str) -> list[str]:
    """Pull literal text from every stderr-writing call (Python / JS / bash).

    Handles f-strings, r-strings, multiple calls, and JS template literals.
    Interpolation braces ({name}, ${n}) stay inside the captured text —
    harmless for phrase matching. Returns [] when the script writes no stderr.

    Python prints are isolated per-call (split before each `print(`) so a
    preceding stdout print cannot bleed its text into a later stderr scan.
    """
    regions: list[str] = []
    for call in re.split(r"(?=\bprint\s*\()", script):
        if re.search(r"file\s*=\s*sys\.stderr", call):
            m = re.match(r"print\s*\((.*?)file\s*=\s*sys\.stderr", call, re.DOTALL)
            if m:
                regions.append(m.group(1))
    for rx in (_JS_STDERR_CALL_RE, _SH_STDERR_CALL_RE):
        regions.extend(rx.findall(script))

    out: list[str] = []
    for region in regions:
        for dq, sq, bq in _STRING_LITERAL_RE.findall(region):
            lit = dq or sq or bq
            if lit:
                out.append(lit)
    return out
```

Then in `_check_imperative_stderr`, replace the extraction line (was `stderr_strings = _STDERR_PRINT_RE.findall(script)`):

```python
    stderr_strings = _extract_stderr_strings(script)
```

- [ ] **Step 4: Run the full grader test file to verify pass + no regressions**

Run: `python3 -m pytest evals/tests/test_grade_code.py -v`
Expected: PASS — all pre-existing `imperative_stderr` tests (6 from v0.3.2) plus the 7 new ones, and every other grader test, green.

- [ ] **Step 5: Commit**

```bash
git add evals/grade_code.py evals/tests/test_grade_code.py
git commit -m "$(cat <<'EOF'
fix(eval): imperative_stderr grader now sees f-strings, bash, and JS stderr

The v0.3.2 extractor matched only plain-string print(..., file=sys.stderr),
so it false-passed passive messages hidden in f-strings (the idiom Example 4
itself uses), bash echo >&2, and console.error. Replace with a per-language
literal extractor + per-call Python isolation. Adds 7 tests covering the
previously-blind cases.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Productize the `claude-cli` eval backend

**Context:** The Haiku/Sonnet/Opus baselines in `evals/results/` were produced by `/tmp/eval_via_cli.py` — uncommitted, hardcoded to one machine's absolute path, gone on reboot. `evals/results/README.md` and the v0.3.2 CHANGELOG both point reproduction at `/tmp`. This task moves that logic into the repo as a proper backend so the frontier baselines are reproducible with no `ANTHROPIC_API_KEY` (subscription OAuth).

**Files:**
- Create: `evals/client_claude_cli.py`
- Create: `evals/tests/test_client_claude_cli.py`
- Modify: `evals/run.py:161-175` (backend selection)

- [ ] **Step 1: Write the failing tests**

Create `evals/tests/test_client_claude_cli.py`:

```python
"""Unit tests for evals/client_claude_cli.py.

Mocks subprocess.run so tests never invoke the real `claude` CLI.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from evals.client_claude_cli import ClaudeCliClient


def _fake_run_factory(stdout: str, returncode: int = 0, stderr: str = ""):
    def _fake(cmd, **kwargs):
        _fake.captured = {"cmd": cmd, "kwargs": kwargs}
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)
    return _fake


def test_create_returns_anthropic_shape():
    client = ClaudeCliClient(model="haiku")
    with patch("evals.client_claude_cli.subprocess.run",
               new=_fake_run_factory("hello world")):
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",  # caller's name — ignored
            max_tokens=256,
            messages=[{"role": "user", "content": "say hi"}],
        )
    assert len(resp.content) == 1
    assert resp.content[0].type == "text"
    assert resp.content[0].text == "hello world"


def test_create_uses_cli_model_not_caller_model():
    fake = _fake_run_factory("ok")
    client = ClaudeCliClient(model="opus")
    with patch("evals.client_claude_cli.subprocess.run", new=fake):
        client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=10,
                               messages=[{"role": "user", "content": "x"}])
    cmd = fake.captured["cmd"]
    assert cmd[cmd.index("--model") + 1] == "opus"


def test_create_prepends_system_prompt():
    fake = _fake_run_factory("ok")
    client = ClaudeCliClient(model="haiku")
    with patch("evals.client_claude_cli.subprocess.run", new=fake):
        client.messages.create(model="x", max_tokens=10, system="You are a grader.",
                               messages=[{"role": "user", "content": "review this"}])
    prompt = fake.captured["cmd"][-1]   # prompt is the last positional arg
    assert prompt.startswith("You are a grader.")
    assert "review this" in prompt


def test_create_raises_on_nonzero_exit():
    client = ClaudeCliClient(model="haiku")
    with patch("evals.client_claude_cli.subprocess.run",
               new=_fake_run_factory("", returncode=1, stderr="boom")):
        with pytest.raises(RuntimeError) as ei:
            client.messages.create(model="x", max_tokens=10,
                                   messages=[{"role": "user", "content": "x"}])
    assert "failed" in str(ei.value).lower()


def test_create_raises_when_cli_missing():
    def _missing(cmd, **kwargs):
        raise FileNotFoundError("claude")
    client = ClaudeCliClient(model="haiku")
    with patch("evals.client_claude_cli.subprocess.run", new=_missing):
        with pytest.raises(RuntimeError) as ei:
            client.messages.create(model="x", max_tokens=10,
                                   messages=[{"role": "user", "content": "x"}])
    assert "not found" in str(ei.value).lower()
```

- [ ] **Step 2: Run the tests to verify they fail (module doesn't exist yet)**

Run: `python3 -m pytest evals/tests/test_client_claude_cli.py -v`
Expected: FAIL at collection — `ModuleNotFoundError: No module named 'evals.client_claude_cli'`.

- [ ] **Step 3: Create `evals/client_claude_cli.py`**

```python
"""Claude CLI client that mimics the anthropic.Anthropic interface.

Wraps `claude --print --model <X>` (OAuth subscription) so the eval harness
can run against Haiku/Sonnet/Opus with NO ANTHROPIC_API_KEY — auth is the
user's Claude Code subscription. Same `.messages.create(**kwargs)` shape as
the Anthropic SDK and OllamaClient, so grade_model / run_one_entry stay
backend-agnostic.

Default model: `haiku`. Override via CLAUDE_CLI_MODEL env var.
"""
from __future__ import annotations

import json
import os
import subprocess
from types import SimpleNamespace

DEFAULT_MODEL = os.environ.get("CLAUDE_CLI_MODEL", "haiku")
DEFAULT_TIMEOUT = float(os.environ.get("CLAUDE_CLI_TIMEOUT", "600"))


class ClaudeCliClient:
    """Drop-in for `anthropic.Anthropic` using the `claude --print` CLI."""

    def __init__(self, model: str = DEFAULT_MODEL, timeout: float = DEFAULT_TIMEOUT):
        self.cli_model = model
        self.timeout = timeout
        # mirror anthropic.Anthropic's surface: client.messages.create(**kwargs)
        self.messages = SimpleNamespace(create=self._create)

    def _build_prompt(self, system: str | None, messages: list) -> str:
        parts: list[str] = []
        if system:
            parts.append(system)
            parts.append("")
        for msg in messages:
            content = msg["content"]
            if not isinstance(content, str):
                content = json.dumps(content)
            parts.append(content)
        return "\n\n".join(parts)

    def _create(self, *, model: str, max_tokens: int, messages: list,
                system: str | None = None, **_ignored):
        """Issue one completion via `claude --print`. The Anthropic `model`
        kwarg (a cloud model name) is ignored; the CLI model is fixed at
        construction. `max_tokens` has no CLI equivalent and is ignored."""
        prompt = self._build_prompt(system, messages)
        try:
            result = subprocess.run(
                [
                    "claude", "--print",
                    "--model", self.cli_model,
                    "--disable-slash-commands",
                    "--no-session-persistence",
                    "--exclude-dynamic-system-prompt-sections",
                    prompt,
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except FileNotFoundError as e:
            raise RuntimeError(
                "`claude` CLI not found on PATH — is Claude Code installed?"
            ) from e
        if result.returncode != 0:
            raise RuntimeError(
                f"`claude --print` failed (rc={result.returncode}): "
                f"{result.stderr[:500]}"
            )
        # Anthropic SDK shape: response.content is a list of blocks with .type/.text.
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=result.stdout)]
        )
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `python3 -m pytest evals/tests/test_client_claude_cli.py -v`
Expected: PASS — all 5 tests green.

- [ ] **Step 5: Wire `claude-cli` into `evals/run.py` backend selection**

In `evals/run.py`, replace the backend-selection block (the `elif backend == "ollama":` … `else:` portion, ~lines 169-175):

```python
    elif backend == "ollama":
        from evals.client_ollama import OllamaClient, DEFAULT_MODEL
        client = OllamaClient()
        model_label = f"ollama:{DEFAULT_MODEL}"
    else:
        print(f"Unknown EVAL_BACKEND={backend!r} (expected: ollama|anthropic)", file=sys.stderr)
        return 2
```

with:

```python
    elif backend == "ollama":
        from evals.client_ollama import OllamaClient, DEFAULT_MODEL
        client = OllamaClient()
        model_label = f"ollama:{DEFAULT_MODEL}"
    elif backend == "claude-cli":
        from evals.client_claude_cli import ClaudeCliClient, DEFAULT_MODEL as CLI_MODEL
        client = ClaudeCliClient()
        model_label = f"claude-cli:{CLI_MODEL}"
    else:
        print(f"Unknown EVAL_BACKEND={backend!r} (expected: ollama|anthropic|claude-cli)", file=sys.stderr)
        return 2
```

- [ ] **Step 6: Verify the backend is selectable (smoke check, mocked)**

Run:
```bash
python3 -c "import os; os.environ['EVAL_BACKEND']='claude-cli'; from evals.client_claude_cli import ClaudeCliClient, DEFAULT_MODEL; print('claude-cli backend importable; default model =', DEFAULT_MODEL)"
```
Expected: `claude-cli backend importable; default model = haiku`

- [ ] **Step 7: Commit**

```bash
git add evals/client_claude_cli.py evals/tests/test_client_claude_cli.py evals/run.py
git commit -m "$(cat <<'EOF'
feat(eval): productize claude-cli backend (EVAL_BACKEND=claude-cli)

Moves the throwaway /tmp/eval_via_cli.py into the repo as a proper backend
so the Haiku/Sonnet/Opus baselines are reproducible without ANTHROPIC_API_KEY
(subscription OAuth). Mirrors the OllamaClient interface; 5 mocked-subprocess
tests.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Fix the dangling reference in `improve-uninstall`

**Context:** `plugin/skills/improve-uninstall/SKILL.md:56` says *"Use the same defensive merge discipline as `@references/settings-merge.md`"*, but there is **no `references/` directory** under `plugin/skills/improve-uninstall/` (only `improve/` and `improve-init/` carry references — a leftover from v0.3's shared→inline pivot). The `@`-mention cannot resolve. The discipline is already partly described inline, so the fix is to drop the broken mention and make the inline description self-contained.

**Files:**
- Modify: `plugin/skills/improve-uninstall/SKILL.md:56`

- [ ] **Step 1: Edit the dangling mention**

Replace this text on line 56:

```
- **Hook entries:** for each plugin-installed entry, remove it from its array in settings.json. Preserve all other entries. Use the same defensive merge discipline as `@references/settings-merge.md` — read, parse, modify in-memory, write atomically (write to `.tmp`, then rename). Reparse after to confirm the write produced valid JSON; if not, restore the pre-write content.
```

with:

```
- **Hook entries:** for each plugin-installed entry, remove it from its array in settings.json. Preserve all other entries. Use the same defensive merge discipline `/improve` uses: read → parse → modify in-memory → write atomically to a `.tmp` file, then rename → reparse to confirm valid JSON → restore the pre-write content on failure.
```

- [ ] **Step 2: Verify no dangling `@references` remain in the skill**

Run: `grep -c '@references' plugin/skills/improve-uninstall/SKILL.md`
Expected: `0`

- [ ] **Step 3: Commit**

```bash
git add plugin/skills/improve-uninstall/SKILL.md
git commit -m "$(cat <<'EOF'
fix(uninstall): remove dangling @references/settings-merge.md mention

improve-uninstall has no references/ dir (leftover from v0.3's shared->inline
pivot), so the @-mention could not resolve. Describe the merge discipline
inline instead.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Capture discriminating telemetry fields (`kind` / `reason` / `source`)

**Context:** Spec §3.5 promised `Notification → {kind: "waiting_for_permission"|"idle"}` and `PreCompact → {reason}`, and the README sells "permission/idle notifications … give /improve-init richer signal to mine." But `telemetry.py:39-46` emits bare `{event:"notification"}` / `{event:"compact"}`, so a consumer can only *count* notifications, never tell a permission-nag from an idle-timeout. This adds the discriminating fields defensively (this signal is the input v0.4's auto-collect/close-the-loop work will mine).

> **Field-name caveat:** the exact Notification/PreCompact/SessionStart payload field names are not in `docs/knowledge/`. The code below is defensive (`.get` + keyword classification + `"other"`/`""` fallbacks) so it degrades gracefully if a field is named differently. Confirm against a real session with the `jq . > log.json` technique (`hooks-and-sdk.md §8`) and adjust keywords if needed — no crash either way.

**Files:**
- Modify: `plugin/scripts/telemetry.py` (the `summarize` function, ~lines 39-46) + add a helper
- Test: `plugin/scripts/tests/test_telemetry.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `plugin/scripts/tests/test_telemetry.py`:

```python
def test_notification_kind_permission(tmp_path):
    payload = {"hook_event_name": "Notification",
               "message": "Claude needs your permission to use Bash"}
    row = run_telemetry(payload, tmp_path)
    assert row["event"] == "notification"
    assert row["kind"] == "waiting_for_permission"


def test_notification_kind_idle(tmp_path):
    payload = {"hook_event_name": "Notification",
               "message": "Claude is waiting for your input"}
    row = run_telemetry(payload, tmp_path)
    assert row["kind"] == "idle"


def test_notification_kind_other_when_no_message(tmp_path):
    payload = {"hook_event_name": "Notification"}
    row = run_telemetry(payload, tmp_path)
    assert row["kind"] == "other"


def test_precompact_reason_from_trigger(tmp_path):
    payload = {"hook_event_name": "PreCompact", "trigger": "auto"}
    row = run_telemetry(payload, tmp_path)
    assert row["event"] == "compact"
    assert row["reason"] == "auto"


def test_precompact_reason_empty_when_absent(tmp_path):
    payload = {"hook_event_name": "PreCompact"}
    row = run_telemetry(payload, tmp_path)
    assert row["reason"] == ""


def test_sessionstart_source_captured(tmp_path):
    payload = {"hook_event_name": "SessionStart", "source": "resume"}
    row = run_telemetry(payload, tmp_path)
    assert row["event"] == "session_start"
    assert row["source"] == "resume"
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest plugin/scripts/tests/test_telemetry.py -k "kind or reason or source" -v`
Expected: FAIL with `KeyError: 'kind'` / `'reason'` / `'source'` — the fields don't exist yet.

- [ ] **Step 3: Implement the discriminating fields in `plugin/scripts/telemetry.py`**

Add this helper just above `def summarize(` (after the `SECRET_PATTERN_RE` block):

```python
def _notification_kind(event: dict) -> str:
    """Classify a Notification by its message text (best-effort, defensive).

    Claude Code notifies both when it needs tool permission and when it has
    been idle. Field name isn't documented in our knowledge base, so we read
    `message` and classify by keyword, defaulting to "other".
    """
    msg = (event.get("message") or "").lower()
    if "permission" in msg or "approve" in msg or "allow" in msg:
        return "waiting_for_permission"
    if "idle" in msg or "waiting" in msg:
        return "idle"
    return "other"
```

Then replace these three lines inside `summarize` (currently ~lines 39-44):

```python
    if hook_event == "Notification":
        return {"ts": ts, "event": "notification"}
    if hook_event == "PreCompact":
        return {"ts": ts, "event": "compact"}
    if hook_event == "SessionStart":
        return {"ts": ts, "event": "session_start"}
```

with:

```python
    if hook_event == "Notification":
        return {"ts": ts, "event": "notification", "kind": _notification_kind(event)}
    if hook_event == "PreCompact":
        return {"ts": ts, "event": "compact", "reason": event.get("trigger") or event.get("reason") or ""}
    if hook_event == "SessionStart":
        return {"ts": ts, "event": "session_start", "source": event.get("source") or ""}
```

- [ ] **Step 4: Run the full telemetry test file to verify pass + no regressions**

Run: `python3 -m pytest plugin/scripts/tests/test_telemetry.py -v`
Expected: PASS — the 6 new tests plus all pre-existing ones (the old `test_notification_event_logged` etc. still pass; they only assert `event`/`ts`, and we added fields, didn't remove any).

- [ ] **Step 5: Commit**

```bash
git add plugin/scripts/telemetry.py plugin/scripts/tests/test_telemetry.py
git commit -m "$(cat <<'EOF'
feat(telemetry): capture notification kind, compact reason, session source

Spec 3.5 promised these discriminating fields but telemetry.py emitted bare
event markers, so /improve-init could not tell a permission-nag from an idle
timeout. Adds defensive keyword classification (degrades to "other"/"" if a
payload field is named differently). This is the signal v0.4 auto-collect mines.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Re-score the dataset and commit a fresh baseline

**Context:** `eval-methodology.md §1` is explicit: *"Don't ship a SKILL change without re-scoring."* v0.3.1 and v0.3.2 both changed the SKILL/rubric and re-scored nothing. Now that Task 1 fixed the grader and Task 2 made the backend reproducible, run the eval and commit the number so the v0.3.1+v0.3.2 work finally registers as a measured delta.

> **Prerequisite:** a working backend. Default path uses Ollama + `gemma4:e4b` (no credentials, fully reproducible — the repo's daily-dev backend). If Ollama isn't available, use `EVAL_BACKEND=claude-cli` (needs the user's Claude Code subscription). Tasks 1 and 2 must be committed first.

- [ ] **Step 1: Run the eval against the reproducible gemma backend**

Run: `EVAL_BACKEND=ollama python3 -m evals.run`
Expected: per-entry progress on stderr, then a summary like `Average code score:  X.X/10` / `Average model score: X.X/10`, and `Results written to evals/results/2026-05-24.json`.
(Model output is non-deterministic; do not assert exact scores — the goal is a committed measurement produced by the 8-check grader.)

- [ ] **Step 2: Rename the result to the versioned convention**

Run: `mv evals/results/2026-05-24.json evals/results/2026-05-24-v0.3.3-gemma.json`
Expected: the file now matches the `YYYY-MM-DD-v0.X-<backend>.json` naming used by the existing baselines.

- [ ] **Step 3: (Optional, user-run with subscription) regenerate a frontier reference**

Run: `EVAL_BACKEND=claude-cli CLAUDE_CLI_MODEL=haiku python3 -m evals.run && mv evals/results/2026-05-24.json evals/results/2026-05-24-v0.3.3-haiku.json`
Expected: a Haiku baseline produced via the now-committed backend (proves Task 2's reproducibility end-to-end). Skip if no subscription is available in the execution environment.

- [ ] **Step 4: Record the delta in `evals/results/README.md`**

Add a row/column to the results table noting the v0.3.3 gemma average and, in one line, how it compares to the v0.3 gemma baseline (`7.1` code / `2.9` model). Note explicitly that this is the first run with the fixed 8-check `imperative_stderr` grader. Replace the "see `/tmp/eval_via_cli.py`" reproduction note with: `EVAL_BACKEND=claude-cli CLAUDE_CLI_MODEL=haiku python3 -m evals.run` (now in-repo).

- [ ] **Step 5: Commit**

```bash
git add evals/results/2026-05-24-v0.3.3-gemma.json evals/results/README.md
# include the frontier file only if Step 3 was run:
# git add evals/results/2026-05-24-v0.3.3-haiku.json
git commit -m "$(cat <<'EOF'
test(eval): v0.3.3 baseline — first re-score since v0.3.0 with 8-check grader

Re-scores the dataset after the v0.3.1/v0.3.2 SKILL changes (per
eval-methodology.md "don't ship a SKILL change without re-scoring") using the
fixed imperative_stderr grader and the now-in-repo claude-cli backend. Updates
the results README reproduction note off /tmp.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Release — version bump, CHANGELOG, full test sweep

**Files:**
- Modify: `plugin/.claude-plugin/plugin.json` (version)
- Modify: `CHANGELOG.md` (new entry)

- [ ] **Step 1: Bump the plugin version**

In `plugin/.claude-plugin/plugin.json`, change the version string from `0.3.2` to `0.3.3`.

- [ ] **Step 2: Verify the bump**

Run: `grep '"version"' plugin/.claude-plugin/plugin.json`
Expected: `"version": "0.3.3"`

- [ ] **Step 3: Prepend the CHANGELOG entry**

Insert directly below the `All notable changes…` line in `CHANGELOG.md`:

```markdown
## [0.3.3] — 2026-05-24

### Fixed
- **`imperative_stderr` grader was blind to f-strings, bash, and JS.** v0.3.2's extractor matched only plain-string `print(..., file=sys.stderr)`, so it returned "n/a (pass)" for f-string stderr (the idiom Example 4 itself uses), `echo >&2`, and `console.error` — meaning a passive message hidden in an f-string was a silent false-pass. Replaced with a per-language literal extractor (`evals/grade_code.py`), with per-call Python isolation so an adjacent stdout `print` can't bleed into the scan. 7 new tests.
- **Dangling `@references/settings-merge.md` in `/improve-uninstall`.** That skill has no `references/` dir (leftover from v0.3's shared→inline pivot); the merge discipline is now described inline.

### Added
- **`claude-cli` eval backend (`EVAL_BACKEND=claude-cli`).** Productizes the throwaway `/tmp/eval_via_cli.py` as `evals/client_claude_cli.py` (mirrors `OllamaClient`), so the Haiku/Sonnet/Opus baselines are reproducible with no `ANTHROPIC_API_KEY` (subscription OAuth). 5 mocked-subprocess tests.
- **Discriminating telemetry fields.** `Notification` rows now carry `kind` (`waiting_for_permission` | `idle` | `other`), `PreCompact` rows carry `reason`, `SessionStart` rows carry `source` — delivering the §3.5 signal the README already advertised. Defensive classification (degrades to `other`/`""`). 6 new tests.

### Changed
- **Re-scored the dataset** with the fixed 8-check grader (first re-score since v0.3.0) — `evals/results/2026-05-24-v0.3.3-gemma.json`. Reproduction note in the results README moved off `/tmp`.

### Why this is a hygiene release
v0.3.2 declared the text-discipline lever spent ("as strong as text alone can be"). v0.3.3 makes that work *measurable and reproducible* — it fixes the leaky check that would have mis-measured it, commits the backend that produces the frontier numbers, and captures the telemetry signal v0.4 needs. No new architecture. The structural fix (composed PostToolUse + Stop hooks) remains v0.4.
```

- [ ] **Step 4: Run the entire test suite**

Run: `python3 -m pytest -q`
Expected: all tests pass, integration tests skipped by default (per `pyproject.toml` marker config). No failures, no errors.

- [ ] **Step 5: Commit**

```bash
git add plugin/.claude-plugin/plugin.json CHANGELOG.md
git commit -m "$(cat <<'EOF'
v0.3.3: measurement & correctness hygiene — 5 gaps closed

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage** — every v0.3.3-scoped finding from the analysis maps to a task:
- Leaky `imperative_stderr` grader → Task 1 ✓
- Non-reproducible frontier baselines / `client_claude_cli.py` absent → Task 2 ✓
- Dangling `@references/settings-merge.md` → Task 3 ✓
- Telemetry `kind`/`reason` not captured (spec §3.5) → Task 4 ✓
- Two releases owe a re-score (`eval-methodology.md §1`) → Task 5 ✓
- Release plumbing → Task 6 ✓

**Deliberately deferred to v0.4** (documented in the backlog, not this plan): composed PostToolUse+Stop primitive; verify-before-surface integration harness; making the eval exercise the real `SKILL.md` instead of `prompt_template.md`; noise-penalizing aggregation + fixed grader; negative/"propose-nothing" restraint fixtures (need grader support); knowledge-base re-grounding + single-source reference generation.

**Type/name consistency:** `ClaudeCliClient` / `DEFAULT_MODEL` used identically in Task 2's client, tests, and the `run.py` import (`DEFAULT_MODEL as CLI_MODEL`). `_extract_stderr_strings` (Task 1) and `_notification_kind` (Task 4) are each defined once and called once. `EXPECTED_HOOK` reused in Task 1 tests already exists in `test_grade_code.py:231`.

**No placeholders:** every code step shows complete, runnable code; every run step gives an exact command and expected output.

**Dual-copy note:** none of these tasks touch the dual-copied `references/` or SKILL procedure bodies — every edit is in a single-source file. v0.3.3 pays zero dual-copy tax.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-24-self-improving-claude-v0.3.3.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
