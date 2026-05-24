# self-improving-claude v0.3.4 — Eval Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **⛔ BLOCKED until v0.3.3 ships.** This plan is a **delta on v0.3.3's end-state**, not the current tree. Do not start execution until the user confirms v0.3.3 is finished and merged. See `docs/superpowers/plans/2026-05-24-self-improving-claude-v0.3.3.md` for the work this builds on.

**Goal:** Make the eval a trustworthy, autonomy-gradable instrument by fixing the four verified measurement bugs the v0.3.2 analysis surfaced — contradictory fixture golds, shape-only code grading, model-grade truncation-as-0, and unreproducible/mixed-grader baselines.

**Architecture:** Six logical workstreams over the `evals/` layer + three dataset fixtures, built to the schemas in `docs/superpowers/specs/2026-05-24-eval-hardening-design.md`. The deterministic **code grade** is the autonomy-critical metric (loop-gating, binary assertions per the founding doc); the **model grade** is advisory/human-review only — so the two are reported separately, never blended.

**Tech Stack:** Python 3.10+ (stdlib only for shipped code; `pytest`), the existing `evals/` harness (Ollama / Anthropic SDK / the `claude --print` backend v0.3.3 ships).

---

## ⚠️ Why this plan omits line numbers for some files

v0.3.3 modifies `grade_code.py`, `run.py`, `client_claude_cli.py`, and their test files. Their exact line numbers won't be known until v0.3.3 lands. **For those files, target the named functions/regex constants, not line numbers.** Re-confirm against the real files at execution time. New files and `dataset.json` are line-stable and specified exactly.

**Inherited v0.3.3 end-state this plan assumes:**
- `grade_code.py`: `imperative_stderr` *extractor* already fixed (`_extract_stderr_strings` handles f-strings/bash/JS). Still an 8-check **fixed /8 denominator**; classification allowlist still the strict token set; banned list `audit|consider|verify|review|or X is unrelated`.
- `client_claude_cli.py`: exists, **ignores the `model` kwarg** (CLI model fixed at construction).
- `run.py`: `claude-cli` backend wired; proposer still hardcoded `ORCHESTRATOR_MODEL` = Haiku; aggregation is **max-only**.
- `grade_model.py`: **unchanged** (max_tokens=1024, no anti-truncation, parse-failure → score 0).
- `dataset.json`: **unchanged** (002/003/004 still contradictory/ambiguous).
- Version `0.3.3`; a `…-v0.3.3-gemma.json` baseline committed.

---

## File Structure

| File | Create / Modify | Responsibility |
|---|---|---|
| `evals/grade_model.py` | Modify (`grade_model`, `GRADER_TEMPLATE`) | Prevent truncation (compact-JSON instruction + `max_tokens=2048`); return `valid`/`score=None`/`error` instead of score-0 on failure. |
| `evals/tests/test_grade_model.py` | Modify (append) | Tests for the new schema + token floor. |
| `evals/grade_code.py` | Modify (`grade_code`, every `_check_*`, `_STDERR_REQUIRED_RE`, add `_rules_present`) | Applicable-checks denominator (N/A → `None`); broaden `imperative_stderr` classification; `form`/`event` set-membership; emit `rules_present`. |
| `evals/tests/test_grade_code.py` | Modify (append + update N/A assertions) | Tests for denominator, broadened imperative, set-membership, rules_present. |
| `evals/dataset.json` | Modify (entries 002, 003, 004) | Reconcile gold ↔ planted_problem; multi-form 004; `required_rules` for 003. |
| `evals/client_claude_cli.py` | Modify (`_create`, add model map) | **Respect** the per-call `model` kwarg (reverses v0.3.3) so the grader can be pinned while the proposer varies. |
| `evals/run.py` | Modify (`run_one_entry`, `_aggregate`, `main`) | Configurable proposer model; grader pinned to Haiku; aggregation = max + mean + clean_rate + coverage; exclude invalid model grades. |
| `evals/tests/test_run.py` | Modify (append) | Tests for proposer/grader routing + new aggregation. |
| `evals/tests/test_client_claude_cli.py` | Modify (replace the "ignores model" test) | Assert per-call model is now respected. |
| `evals/results/2026-05-24-v0.3.4-*.json` | **Create** (generated) | Fresh full-matrix baseline under new semantics. |
| `evals/results/README.md` | Modify | v0.3.4 columns; "not comparable to ≤v0.3.3" note; correct grader-model claim. |
| `plugin/.claude-plugin/plugin.json` | Modify | Version `0.3.3` → `0.3.4`. |
| `CHANGELOG.md` | Modify (prepend) | `[0.3.4]` entry. |

---

## Dependency graph (for subagent-driven scheduling)

```
Task 1 (grade_model) ─────────────┐
Task 2 → Task 3 → Task 4 (grade_code, same file, sequential) ─→ Task 5 (dataset)
Task 6 (client + run model) ──────┤
                                   └─→ Task 7 (run aggregation; needs 1,4,6) ─→ Task 8 (rerun, gated) ─→ Task 9 (release)
```
Parallelizable Phase 1: **{Task 1}**, **{Task 2→3→4→5}**, **{Task 6}**. Then Task 7, then Task 8 (human/quota gate), then Task 9.

---

## Task 1: `grade_model` — prevent truncation, separate failure from score

**Context:** `grade_model.py` uses `max_tokens=1024` and no anti-truncation, so a verbose grader runs out of tokens before the `score` field; the parse failure is then logged as **score 0**, conflating "truncated" with "wrong" (finding 3; `eval-methodology.md:109` prescribes the fix). Backends are injected (Ollama/CLI ignore SDK-only prefill/stop), so the portable fix is a compact-JSON instruction + a higher token floor + a `valid` flag.

**Files:**
- Modify: `evals/grade_model.py` (`GRADER_TEMPLATE`, the `grade_model` function)
- Test: `evals/tests/test_grade_model.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `evals/tests/test_grade_model.py`:

```python
from types import SimpleNamespace
from evals.grade_model import grade_model


class _FakeClient:
    def __init__(self, text):
        self._text = text
        self.last_kwargs = None
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self._text)])


def test_grade_model_valid_score():
    c = _FakeClient('{"strengths":[],"weaknesses":[],"reasoning":"ok","score":8}')
    r = grade_model(proposal={"form": "x"}, planted_problem="p", client=c)
    assert r["valid"] is True
    assert r["score"] == 8
    assert r["error"] is None


def test_grade_model_truncation_is_invalid_not_zero():
    # A cut-off response: valid prefix, never closes -> json.loads fails.
    c = _FakeClient('{"strengths":["good"],"weaknesses":["')
    r = grade_model(proposal={"form": "x"}, planted_problem="p", client=c)
    assert r["valid"] is False
    assert r["score"] is None          # NOT 0
    assert r["error"]                  # non-empty reason


def test_grade_model_requests_higher_token_floor():
    c = _FakeClient('{"score":5}')
    grade_model(proposal={"form": "x"}, planted_problem="p", client=c)
    assert c.last_kwargs["max_tokens"] >= 2048
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest evals/tests/test_grade_model.py -k "valid or truncation or token_floor" -v`
Expected: FAIL — current code returns `score: 0` (not `None`) on parse failure, has no `valid` key, and uses `max_tokens=1024`.

- [ ] **Step 3: Edit `GRADER_TEMPLATE` (compact-JSON instruction)**

In `evals/grade_model.py`, change the final line of `GRADER_TEMPLATE` from:

```python
Output ONLY the JSON. No prose before or after."""
```

to:

```python
Output ONLY a single-line minified JSON object — no markdown fences, no prose before or after, no trailing whitespace."""
```

- [ ] **Step 4: Rewrite the `grade_model` function body**

Replace the `client.messages.create(...)` call's `max_tokens=1024` with `max_tokens=2048`, and replace the parse/return block with:

```python
    text = response.content[0].text

    try:
        parsed = json.loads(_extract_json(text))
    except json.JSONDecodeError as e:
        return {
            "valid": False,
            "score": None,
            "error": f"parse_error: {e}",
            "strengths": [],
            "weaknesses": [],
            "reasoning": "",
            "raw_response": text[:500],
        }

    raw_score = parsed.get("score")
    try:
        score = max(0, min(10, int(raw_score)))
    except (TypeError, ValueError):
        return {
            "valid": False,
            "score": None,
            "error": f"bad_score: {raw_score!r}",
            "strengths": parsed.get("strengths", []),
            "weaknesses": parsed.get("weaknesses", []),
            "reasoning": parsed.get("reasoning", ""),
        }

    return {
        "valid": True,
        "score": score,
        "error": None,
        "strengths": parsed.get("strengths", []),
        "weaknesses": parsed.get("weaknesses", []),
        "reasoning": parsed.get("reasoning", ""),
    }
```

- [ ] **Step 5: Keep `run.py` aggregation green (minimal guard)**

`run.py`'s existing `_aggregate` does `max((m["score"] for m in r["model_grades"]), default=0)`, which now crashes on `score=None`. In `evals/run.py`, change that line (inside `_aggregate`) to:

```python
        best_model = max((m["score"] for m in r["model_grades"]
                          if m.get("score") is not None), default=0)
```

(Task 7 replaces `_aggregate` wholesale; this keeps the suite green in between.)

- [ ] **Step 6: Run tests**

Run: `python3 -m pytest evals/tests/test_grade_model.py evals/tests/test_run.py -v`
Expected: PASS — new grade_model tests green; existing run tests still green.

- [ ] **Step 7: Commit**

```bash
git add evals/grade_model.py evals/tests/test_grade_model.py evals/run.py
git commit -m "$(cat <<'EOF'
fix(eval): grade_model no longer scores truncated responses as 0

Raises max_tokens to 2048 + asks for compact single-line JSON, and returns
{valid:false, score:null, error} on parse/score failure instead of a silent 0,
so truncation stops polluting the model-grade average (finding 3).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `grade_code` — applicable-checks denominator (N/A → `None`)

**Context:** Non-applicable checks return a free `10` (finding 2), so a wrong-form/no-op proposal still scores ~7 and the "code grade" measures shape, not quality. Switch N/A to `None` and average only applicable checks (fork 1).

**Files:**
- Modify: `evals/grade_code.py` (every `_check_*` that returns 10-for-N/A, and `grade_code`)
- Test: `evals/tests/test_grade_code.py` (append + update existing N/A assertions)

- [ ] **Step 1: Write the failing tests**

Append to `evals/tests/test_grade_code.py`:

```python
def test_na_checks_are_none_and_excluded():
    proposal = {"form": "permissions.deny", "rule": "Read(**/.env*)",
                "rationale": "block .env reads"}
    expected = {"form": "permissions.deny", "rule_pattern": "Read(**/.env*)",
                "rationale_must_mention": [".env"]}
    r = grade_code(proposal, expected)
    assert r["checks"]["event_matches"] is None
    assert r["checks"]["matcher_matches"] is None
    assert r["checks"]["script_parses"] is None
    assert r["checks"]["sentinel_format"] is None
    assert r["checks"]["imperative_stderr"] is None
    # applicable checks (form, rule_pattern, rationale) all pass -> mean 10
    assert r["mean"] == 10.0


def test_wrong_form_scored_below_right_form():
    expected = {"form": "command-hook", "event": "PostToolUse",
                "matcher": "Edit", "rationale_must_mention": ["x"]}
    right = {"form": "command-hook", "event": "PostToolUse", "matcher": "Edit",
             "script": "import sys", "script_lang": "python",
             "rationale": "x reason", "sentinel_name": "self-improving-claude/a"}
    wrong = {**right, "form": "permissions.deny"}  # form_matches -> 0
    assert grade_code(wrong, expected)["mean"] < grade_code(right, expected)["mean"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest evals/tests/test_grade_code.py -k "na_checks_are_none or wrong_form_scored" -v`
Expected: FAIL — N/A checks currently return `10`, not `None`.

- [ ] **Step 3: Change each N/A return from `10` to `None`**

In `evals/grade_code.py`, in these functions replace the N/A `return 10` with `return None`:
- `_check_event_matches`: the `if "event" not in e:` branch.
- `_check_matcher_matches`: the final fall-through `return` (neither `matcher` nor `matcher_must_include`).
- `_check_script_parses`: the `if form != "command-hook":` branch.
- `_check_sentinel_format`: the `if p.get("form") in ("permissions.deny", "claude-md-note"):` branch.
- `_check_rule_pattern`: the final fall-through `return`.
- `_check_imperative_stderr`: BOTH N/A branches (`if p.get("form") != "command-hook":` and `if not stderr_strings:`).

(Leave `_check_form_matches` and `_check_rationale_keywords` returning `10`/`0` — they always apply.)

- [ ] **Step 4: Rewrite `grade_code` to average only applicable checks**

Replace the body of `grade_code` with:

```python
def grade_code(proposal: dict, expected: dict) -> dict:
    """Return {checks: {name: 0|10|None}, mean, degenerate, rules_present}.

    A check returning None does not apply and is excluded from the mean
    (applicable-checks denominator). `rules_present` is populated in Task 4.
    """
    checks = {name: fn(proposal, expected) for name, fn in _CHECKS.items()}
    applicable = [v for v in checks.values() if v is not None]
    mean = (sum(applicable) / len(applicable)) if applicable else 0.0
    return {"checks": checks, "mean": mean, "degenerate": len(applicable) == 0}
```

- [ ] **Step 5: Update pre-existing tests that asserted an N/A check == 10**

Run: `python3 -m pytest evals/tests/test_grade_code.py -v`
Some pre-existing tests (from v0.3.0–v0.3.3) assert `result["checks"]["<name>"] == 10` for a proposal where that check does **not** apply (e.g. `event_matches`/`script_parses`/`sentinel_format`/`rule_pattern`/`imperative_stderr` on a `permissions.deny` proposal, or `event_matches` when expected has no `event`). For each such failure, change that assertion from `== 10` to `is None`. Do **not** change assertions where the check genuinely ran (a `0` or a `10` from real evaluation stays).

- [ ] **Step 6: Run the full grader suite**

Run: `python3 -m pytest evals/tests/test_grade_code.py -v`
Expected: PASS — all tests green, including the two new ones.

- [ ] **Step 7: Commit**

```bash
git add evals/grade_code.py evals/tests/test_grade_code.py
git commit -m "$(cat <<'EOF'
fix(eval): code grade averages only applicable checks (no free N/A passes)

Non-applicable checks now return None and are excluded from the mean, so a
wrong-form or no-op proposal can no longer collect ~4 free points (finding 2).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `grade_code` — broaden `imperative_stderr` classification

**Context:** v0.3.3 fixed the stderr *extractor*; the *classification* allowlist is still a fixed token set (`REQUIRED FOLLOW-UP|DO NOT STOP|FIX EACH|BLOCKING|DO NOT ASK`), so a genuinely imperative message like Opus's ruff hook *"Fix the reported issues before continuing."* scores 0 (finding 2 / fork 2). Per the founding doc, keep it a **binary pattern match** — broaden the *pattern*, do not introduce fuzzy scoring. Broaden the REQUIRED set to also accept a clause-leading imperative verb; leave the banned list untouched (avoids regressing v0.3.2/v0.3.3 banned-word tests).

**Files:**
- Modify: `evals/grade_code.py` (`_STDERR_REQUIRED_RE`)
- Test: `evals/tests/test_grade_code.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `evals/tests/test_grade_code.py`:

```python
def _post_hook(script):
    return {"form": "command-hook", "event": "PostToolUse", "matcher": "Edit",
            "script": script, "script_lang": "python",
            "rationale": "x", "sentinel_name": "self-improving-claude/x"}


def test_imperative_stderr_accepts_fix_directive():
    p = _post_hook('import sys\nprint("ruff check failed. Fix the reported issues before continuing.", file=sys.stderr)\n')
    expected = {"form": "command-hook"}
    assert grade_code(p, expected)["checks"]["imperative_stderr"] == 10


def test_imperative_stderr_still_fails_neutral_found_message():
    p = _post_hook('import sys\nprint("Found 3 references.", file=sys.stderr)\n')
    expected = {"form": "command-hook"}
    assert grade_code(p, expected)["checks"]["imperative_stderr"] == 0
```

- [ ] **Step 2: Run to verify the first fails**

Run: `python3 -m pytest evals/tests/test_grade_code.py -k "accepts_fix_directive or still_fails_neutral" -v`
Expected: `test_imperative_stderr_accepts_fix_directive` FAILS (returns 0); the neutral test already passes.

- [ ] **Step 3: Broaden `_STDERR_REQUIRED_RE`**

In `evals/grade_code.py`, replace the `_STDERR_REQUIRED_RE` definition with:

```python
# Action-forcing phrasing: the explicit v0.3.1 tokens, OR a clause that LEADS with
# an imperative action verb (so "Fix the reported issues before continuing." counts).
# Stays a binary pattern match per the founding doc — no fuzzy/NLP scoring.
_STDERR_REQUIRED_RE = re.compile(
    r"\b(REQUIRED FOLLOW-UP|DO NOT STOP|FIX EACH|BLOCKING|DO NOT ASK)\b"
    r"|(?:^|[.\n]\s*)(Fix|Run|Update|Replace|Remove|Add|Rerun|Regenerate|Revert|Migrate|Delete|Rename)\b",
    re.IGNORECASE,
)
```

- [ ] **Step 4: Run the imperative tests + full grader suite**

Run: `python3 -m pytest evals/tests/test_grade_code.py -v`
Expected: PASS — both new tests green, all v0.3.2/v0.3.3 imperative tests still green (banned list unchanged; neutral "Found…" still fails).

- [ ] **Step 5: Commit**

```bash
git add evals/grade_code.py evals/tests/test_grade_code.py
git commit -m "$(cat <<'EOF'
fix(eval): imperative_stderr accepts clause-leading action verbs

Broadens the required-phrase pattern so a real imperative ("Fix the reported
issues before continuing.") passes instead of being dinged for not matching a
literal token like FIX EACH. Stays a binary pattern match (founding-doc rule);
banned list unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `grade_code` — `form`/`event` set-membership + `rules_present`

**Context:** 004's right answer is genuinely method-dependent (prompt-hook OR PostToolUse command-hook), so `form`/`event` must accept a set (fork 4). 003 needs two unrelated deny rules that no single proposal's `rule` can express, so grade_code must expose which required substrings a proposal covers, for run.py to union (fork 3).

**Files:**
- Modify: `evals/grade_code.py` (`_check_form_matches`, `_check_event_matches`, add `_rules_present`, `grade_code`)
- Test: `evals/tests/test_grade_code.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `evals/tests/test_grade_code.py`:

```python
def test_form_set_membership():
    expected = {"form": ["prompt-hook", "command-hook"]}
    assert grade_code({"form": "command-hook"}, expected)["checks"]["form_matches"] == 10
    assert grade_code({"form": "prompt-hook"}, expected)["checks"]["form_matches"] == 10
    assert grade_code({"form": "permissions.deny"}, expected)["checks"]["form_matches"] == 0


def test_event_set_membership():
    expected = {"form": "command-hook", "event": ["PreToolUse", "PostToolUse"]}
    p = {"form": "command-hook", "event": "PostToolUse", "script": "import sys",
         "script_lang": "python", "rationale": "y",
         "sentinel_name": "self-improving-claude/x"}
    assert grade_code(p, expected)["checks"]["event_matches"] == 10


def test_required_rules_presence():
    expected = {"form": "permissions.deny",
                "required_rules": ["src/generated/prisma", "prisma/dev.db"]}
    p = {"form": "permissions.deny", "rule": "Edit(src/generated/prisma/**)",
         "rationale": "block generated"}
    assert grade_code(p, expected)["rules_present"] == ["src/generated/prisma"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest evals/tests/test_grade_code.py -k "set_membership or required_rules_presence" -v`
Expected: FAIL — list-valued `form`/`event` aren't handled; `rules_present` key doesn't exist.

- [ ] **Step 3: Make `_check_form_matches` / `_check_event_matches` accept a list**

In `evals/grade_code.py` replace both functions with:

```python
def _check_form_matches(p: dict, e: dict) -> int:
    exp = e.get("form")
    if isinstance(exp, list):
        return 10 if p.get("form") in exp else 0
    return 10 if p.get("form") == exp else 0


def _check_event_matches(p: dict, e: dict):
    if "event" not in e:
        return None
    exp = e["event"]
    if isinstance(exp, list):
        return 10 if p.get("event") in exp else 0
    return 10 if p.get("event") == exp else 0
```

- [ ] **Step 4: Add `_rules_present` and surface it from `grade_code`**

Add this helper near the other `_check_*` helpers in `evals/grade_code.py`:

```python
def _rules_present(p: dict, e: dict):
    """For coverage fixtures: which required substrings the proposal's rule covers.

    Returns None when the fixture has no `required_rules` (run.py then skips
    coverage for it). Not a 0/10 check — it feeds the cross-proposal coverage
    rollup in run.py.
    """
    req = e.get("required_rules")
    if not req:
        return None
    rule = p.get("rule") or ""
    return [r for r in req if r in rule]
```

Then in `grade_code`, add `rules_present` to the returned dict:

```python
    return {
        "checks": checks,
        "mean": mean,
        "degenerate": len(applicable) == 0,
        "rules_present": _rules_present(proposal, expected),
    }
```

- [ ] **Step 5: Run the full grader suite**

Run: `python3 -m pytest evals/tests/test_grade_code.py -v`
Expected: PASS — three new tests green; no regressions.

- [ ] **Step 6: Commit**

```bash
git add evals/grade_code.py evals/tests/test_grade_code.py
git commit -m "$(cat <<'EOF'
feat(eval): form/event set-membership + rules_present for coverage fixtures

form/event expected traits may now be a list (004's prompt-hook OR command-hook),
and grade_code exposes rules_present so run.py can union multi-rule coverage (003).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Reconcile fixtures 002 / 003 / 004 (gold ↔ planted_problem)

**Context:** 002's gold `Read(**/.env)` doesn't match `.env.local` (finding 1); 003's gold covers only one of two forbidden paths; 004 pins a single form the evidence contradicts. The model-grade-3-on-a-10-code contradiction comes from gold and planted_problem disagreeing. Make them agree.

> **PRECONDITION — verify-then-write (do this first).** The knowledge base contradicts itself on whether a `Read(...)` deny rule also blocks Grep/Glob/`Bash cat` (`settings-and-permissions.md` §3 = one tool per rule; `hooks-and-sdk.md:200` = "applies uniformly across tools"). Confirm the real Claude Code behavior (docs or a quick sandbox test). **If a `Read(...)` rule does NOT cover Grep/Glob, the 002 planted_problem must not claim "uniform across Read/Grep/Glob"** — keep it to "block reads of `.env` files (bare + variants)" so the single-glob gold is correct. If it DOES cover uniformly, you may keep the uniform wording. The variants gap (`.env.local`) and the two-path 003 case are correct under either reading.

**Files:**
- Modify: `evals/dataset.json` (entries 002, 003, 004 only)

- [ ] **Step 1: Rewrite entry 002 (`002-block-env-reads`)**

Replace its `planted_problem` and `expected_hook_traits` with (conservative wording; widen only if the precondition confirmed uniform coverage):

```json
      "planted_problem": "Claude has been reading .env and .env.local during normal work; the user wants reads of .env files blocked. A correct rule must cover the bare file AND its variants (.env.local, .env.production), which a bare **/.env glob does not.",
      "expected_hook_traits": {
        "form": "permissions.deny",
        "rule_pattern": "Read(**/.env*)",
        "rationale_must_mention": [".env"]
      }
```

- [ ] **Step 2: Rewrite entry 003 (`003-prisma-generated-protection`)**

Replace its `planted_problem` and `expected_hook_traits` with:

```json
      "planted_problem": "Claude edits src/generated/prisma/* (auto-generated client) and writes to prisma/dev.db (SQLite binary). CLAUDE.md forbids BOTH paths and no enforcement exists; a complete solution must protect both.",
      "expected_hook_traits": {
        "form": "permissions.deny",
        "required_rules": ["src/generated/prisma", "prisma/dev.db"],
        "rationale_must_mention": ["prisma", "generated"]
      }
```

- [ ] **Step 3: Rewrite entry 004 (`004-recursion-prevention`) expected traits**

Replace its `expected_hook_traits` with (accept both genuinely-valid forms):

```json
      "expected_hook_traits": {
        "form": ["prompt-hook", "command-hook"],
        "event": ["PreToolUse", "PostToolUse"],
        "matcher_must_include": ["Edit", "Write"],
        "rationale_must_mention": ["recursion"]
      }
```

- [ ] **Step 4: Validate JSON + schema**

Run: `python3 -c "import json; d=json.load(open('evals/dataset.json')); ids=[e['id'] for e in d['entries']]; print('entries:', ids)"`
Expected: prints all 7 entry ids, no `JSONDecodeError`.

- [ ] **Step 5: Confirm grade_code reads the new shapes (smoke)**

Run:
```bash
python3 -c "
import json
from evals.grade_code import grade_code
e = {x['id']: x['expected_hook_traits'] for x in json.load(open('evals/dataset.json'))['entries']}
print('002 rule pass:', grade_code({'form':'permissions.deny','rule':'Read(**/.env*)','rationale':'.env'}, e['002-block-env-reads'])['mean'])
print('003 rules_present:', grade_code({'form':'permissions.deny','rule':'Write(prisma/dev.db)'}, e['003-prisma-generated-protection'])['rules_present'])
print('004 form ok:', grade_code({'form':'command-hook','event':'PostToolUse','matcher':'Edit|Write','script':'import sys','script_lang':'python','rationale':'recursion','sentinel_name':'self-improving-claude/x'}, e['004-recursion-prevention'])['checks']['form_matches'])
"
```
Expected: `002 rule pass: 10.0`; `003 rules_present: ['prisma/dev.db']`; `004 form ok: 10`.

- [ ] **Step 6: Commit**

```bash
git add evals/dataset.json
git commit -m "$(cat <<'EOF'
fix(eval): reconcile fixtures 002/003/004 with their planted problems

002 gold -> Read(**/.env*) (covers .env.local); 003 -> required_rules covering
both forbidden paths; 004 accepts prompt-hook OR PostToolUse command-hook. Ends
the code-10/model-3 contradiction where the gold failed its own planted problem.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `claude-cli` respects the `model` kwarg + run.py proposer/grader split

**Context:** v0.3.3's `ClaudeCliClient` ignores the `model` kwarg, so the grader runs on the same model as the proposer (Opus run graded by Opus) — the mixed-grader problem (finding 4). Fork 6: respect the per-call model so the grader is pinned to Haiku for **every** run while the proposer varies, giving comparable, reproducible columns.

**Files:**
- Modify: `evals/client_claude_cli.py` (`_create`, add a model map)
- Modify: `evals/run.py` (`run_one_entry`, `main` — proposer model wiring)
- Test: `evals/tests/test_client_claude_cli.py` (replace the "ignores model" test); `evals/tests/test_run.py` (append)

- [ ] **Step 1: Replace the v0.3.3 "ignores model" test + add routing test**

In `evals/tests/test_client_claude_cli.py`, **delete** `test_create_uses_cli_model_not_caller_model` (it asserted the now-reversed behavior) and append:

```python
def test_create_respects_per_call_model():
    fake = _fake_run_factory("ok")
    client = ClaudeCliClient(model="opus")
    with patch("evals.client_claude_cli.subprocess.run", new=fake):
        client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=10,
                               messages=[{"role": "user", "content": "x"}])
    cmd = fake.captured["cmd"]
    assert cmd[cmd.index("--model") + 1] == "haiku"   # mapped from the grader id


def test_create_falls_back_to_construction_model():
    fake = _fake_run_factory("ok")
    client = ClaudeCliClient(model="sonnet")
    with patch("evals.client_claude_cli.subprocess.run", new=fake):
        client.messages.create(model=None, max_tokens=10,
                               messages=[{"role": "user", "content": "x"}])
    cmd = fake.captured["cmd"]
    assert cmd[cmd.index("--model") + 1] == "sonnet"
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest evals/tests/test_client_claude_cli.py -v`
Expected: FAIL — current `_create` ignores `model`, always emits the construction model.

- [ ] **Step 3: Add the model map + respect the kwarg in `_create`**

In `evals/client_claude_cli.py`, add near the top (after the constants):

```python
# Map Anthropic model IDs (what grade_model / run pass) to `claude --print` aliases.
_CLI_MODEL_MAP = {
    "claude-haiku-4-5-20251001": "haiku",
    "claude-sonnet-4-5": "sonnet",
    "claude-opus-4-7": "opus",
}


def _to_cli_model(model: str) -> str:
    return _CLI_MODEL_MAP.get(model, model)
```

Then in `_create`, resolve the per-call model (falling back to the construction default) and use it for `--model`:

```python
    def _create(self, *, model: str | None = None, max_tokens: int, messages: list,
                system: str | None = None, **_ignored):
        cli_model = _to_cli_model(model) if model else self.cli_model
        prompt = self._build_prompt(system, messages)
        try:
            result = subprocess.run(
                [
                    "claude", "--print",
                    "--model", cli_model,
                    "--disable-slash-commands",
                    "--no-session-persistence",
                    "--exclude-dynamic-system-prompt-sections",
                    prompt,
                ],
                capture_output=True, text=True, timeout=self.timeout,
            )
        except FileNotFoundError as e:
            raise RuntimeError(
                "`claude` CLI not found on PATH — is Claude Code installed?"
            ) from e
        if result.returncode != 0:
            raise RuntimeError(
                f"`claude --print` failed (rc={result.returncode}): {result.stderr[:500]}"
            )
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=result.stdout)])
```

- [ ] **Step 4: Wire the proposer model through `run.py`**

In `evals/run.py`, ensure the **proposal** call uses the run's proposer model (not the hardcoded `ORCHESTRATOR_MODEL`), while the grader keeps using `grade_model.GRADER_MODEL`. Change `run_one_entry`'s signature and its proposal `create` call:

```python
def run_one_entry(entry: dict, *, client, proposer_model: str) -> dict:
    ...
    resp = client.messages.create(
        model=proposer_model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
```

In `main`, resolve `proposer_model` per backend and pass it in:
- `anthropic` backend → `proposer_model = ORCHESTRATOR_MODEL`
- `ollama` backend → `proposer_model = DEFAULT_MODEL` (ignored by the client, but labels stay correct)
- `claude-cli` backend → `proposer_model = CLI_MODEL` (the `CLAUDE_CLI_MODEL` value)

and update the call site: `per_entry_results.append(run_one_entry(entry, client=client, proposer_model=proposer_model))`.

- [ ] **Step 5: Add a run.py routing test**

Append to `evals/tests/test_run.py`:

```python
from types import SimpleNamespace
from evals import run as run_mod
from evals.grade_model import GRADER_MODEL


def test_proposer_and_grader_models_route_separately(monkeypatch):
    seen = []

    class _Recorder:
        def __init__(self):
            self.messages = SimpleNamespace(create=self._create)

        def _create(self, *, model, max_tokens, messages, system=None, **kw):
            seen.append(model)
            # proposal call -> return a parseable single proposal; grader -> a score
            text = ('{"proposals":[{"form":"permissions.deny","rule":"Read(**/.env*)",'
                    '"rationale":".env"}]}' if system is None
                    else '{"score":7,"strengths":[],"weaknesses":[],"reasoning":"x"}')
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])

    entry = {"id": "002-block-env-reads", "trigger": "improve-init", "user_args": "",
             "planted_problem": "p",
             "expected_hook_traits": {"form": "permissions.deny",
                                      "rule_pattern": "Read(**/.env*)",
                                      "rationale_must_mention": [".env"]}}
    run_mod.run_one_entry(entry, client=_Recorder(), proposer_model="opus")
    assert "opus" in seen                 # proposal used the proposer model
    assert GRADER_MODEL in seen           # grading used the pinned grader model
```

- [ ] **Step 6: Run the tests**

Run: `python3 -m pytest evals/tests/test_client_claude_cli.py evals/tests/test_run.py -v`
Expected: PASS — client respects per-call model; proposer/grader route separately.

- [ ] **Step 7: Commit**

```bash
git add evals/client_claude_cli.py evals/run.py evals/tests/test_client_claude_cli.py evals/tests/test_run.py
git commit -m "$(cat <<'EOF'
fix(eval): pin grader to Haiku; claude-cli respects per-call model

ClaudeCliClient now honors the model kwarg (mapped to a CLI alias), and run.py
routes the proposal through the run's proposer model while grade_model keeps
using the fixed GRADER_MODEL. Frontier columns are now graded by one model =
comparable + reproducible (finding 4 / fork 6).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `run.py` aggregation — max + mean + clean_rate + coverage, exclude invalid

**Context:** Max-only aggregation hides bad proposals and the (now-`None`) invalid model grades must be excluded from averages (fork 5 / finding G1). Add `mean`, `clean_rate`, and per-fixture `coverage` for `required_rules` fixtures.

**Files:**
- Modify: `evals/run.py` (`run_one_entry` to carry `expected_hook_traits`; replace `_aggregate`; add `CLEAN_THRESHOLD`)
- Test: `evals/tests/test_run.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `evals/tests/test_run.py`:

```python
from evals.run import _aggregate


def _mk_entry(id, code_means, model_scores, expected=None, rules_present=None):
    return {
        "id": id,
        "proposals": [{} for _ in code_means],
        "expected_hook_traits": expected or {},
        "code_grades": [{"mean": m, "rules_present": (rules_present[i] if rules_present else None)}
                        for i, m in enumerate(code_means)],
        "model_grades": [{"valid": s is not None, "score": s} for s in model_scores],
    }


def test_aggregate_excludes_invalid_model_grades():
    agg = _aggregate([_mk_entry("a", [10.0], [None])])
    e = agg["entries"][0]
    assert e["model_max"] is None and e["n_model_valid"] == 0
    assert agg["average_model"] is None


def test_aggregate_reports_mean_and_clean_rate():
    agg = _aggregate([_mk_entry("a", [10.0, 4.0, 8.0], [9, 3, 7])])
    e = agg["entries"][0]
    assert e["code_max"] == 10.0
    assert round(e["code_mean"], 2) == 7.33
    assert round(e["clean_rate"], 2) == 0.67   # 2 of 3 >= 7.0


def test_aggregate_computes_coverage_union():
    expected = {"required_rules": ["src/generated/prisma", "prisma/dev.db"]}
    entry = _mk_entry("c", [10.0, 8.6], [5, 5], expected=expected,
                      rules_present=[["src/generated/prisma"], ["prisma/dev.db"]])
    agg = _aggregate([entry])
    assert agg["entries"][0]["coverage"] == 1.0
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest evals/tests/test_run.py -k aggregate -v`
Expected: FAIL — current `_aggregate` lacks `model_max=None`, `code_mean`, `clean_rate`, `coverage`.

- [ ] **Step 3: Carry `expected_hook_traits` out of `run_one_entry`**

In `evals/run.py`, add the expected traits to the dict `run_one_entry` returns:

```python
    return {
        "id": entry["id"],
        "trigger": entry["trigger"],
        "user_args": entry.get("user_args", ""),
        "expected_hook_traits": entry["expected_hook_traits"],
        "proposals": proposals,
        "code_grades": code_grades,
        "model_grades": model_grades,
        "raw_response_head": raw[:500],
    }
```

- [ ] **Step 4: Replace `_aggregate` (and add the threshold constant)**

In `evals/run.py`, add near the top-level constants:

```python
CLEAN_THRESHOLD = 7.0  # a proposal at/above this code mean counts as "clean"
```

Replace the entire `_aggregate` function with:

```python
def _aggregate(per_entry_results: list[dict]) -> dict:
    """Dataset-level rollup.

    Headline = max code grade (best-candidate intent). Also reports code_mean
    and clean_rate so noisy proposal sets are visible, and per-fixture coverage
    for required_rules fixtures. Invalid model grades (score is None) are
    excluded — never counted as 0.
    """
    if not per_entry_results:
        return {"average_code": 0.0, "average_model": None,
                "average_clean_rate": 0.0, "entries": []}

    entries = []
    for r in per_entry_results:
        codes = [c["mean"] for c in r["code_grades"]]
        valid_models = [m["score"] for m in r["model_grades"]
                        if m.get("valid") and m.get("score") is not None]
        entry = {
            "id": r["id"],
            "code_max": max(codes, default=0.0),
            "code_mean": (sum(codes) / len(codes)) if codes else 0.0,
            "model_max": max(valid_models, default=None),
            "model_mean": (sum(valid_models) / len(valid_models)) if valid_models else None,
            "clean_rate": (sum(1 for c in codes if c >= CLEAN_THRESHOLD) / len(codes)) if codes else 0.0,
            "n_proposals": len(r.get("proposals", [])),
            "n_model_valid": len(valid_models),
        }
        required = (r.get("expected_hook_traits") or {}).get("required_rules")
        if required:
            covered = set()
            for cg in r["code_grades"]:
                for rp in (cg.get("rules_present") or []):
                    covered.add(rp)
            entry["coverage"] = len(covered) / len(required)
        entries.append(entry)

    model_maxes = [e["model_max"] for e in entries if e["model_max"] is not None]
    return {
        "average_code": sum(e["code_max"] for e in entries) / len(entries),
        "average_model": (sum(model_maxes) / len(model_maxes)) if model_maxes else None,
        "average_clean_rate": sum(e["clean_rate"] for e in entries) / len(entries),
        "entries": entries,
    }
```

- [ ] **Step 5: Fix the `main` summary print for a possibly-None model average**

In `evals/run.py`'s `main`, replace the model-average print line with:

```python
    am = agg["average_model"]
    print(f"Average model score: {am:.1f}/10" if am is not None else "Average model score: n/a (no valid grades)")
```

- [ ] **Step 6: Run the run-suite**

Run: `python3 -m pytest evals/tests/test_run.py -v`
Expected: PASS — aggregation tests green; existing run tests still green.

- [ ] **Step 7: Commit**

```bash
git add evals/run.py evals/tests/test_run.py
git commit -m "$(cat <<'EOF'
feat(eval): aggregation adds mean + clean_rate + coverage; excludes invalid grades

Keeps max as the headline but surfaces code_mean and clean_rate so a good+bad
proposal set is no longer invisible, computes per-fixture coverage for
required_rules fixtures (003), and excludes invalid (None) model grades from
averages instead of treating them as 0.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Full-matrix rerun under the new semantics (HUMAN/QUOTA-GATED)

**Context:** Scoring semantics changed (Tasks 2–7), so all baselines must be regenerated; the README table is otherwise stale. The user chose the **full matrix**. This task is non-deterministic and spends subscription quota — **do not assert exact scores**.

**Files:**
- Create: `evals/results/2026-05-24-v0.3.4-{gemma,haiku,sonnet,opus}.json`
- Modify: `evals/results/README.md`

- [ ] **Step 1: gemma (free, local)**

Run: `EVAL_BACKEND=ollama python3 -m evals.run && mv evals/results/$(date -u +%F).json evals/results/2026-05-24-v0.3.4-gemma.json`
Expected: a results file with the new `summary` shape (`code_mean`/`clean_rate`/`coverage`/`average_model` possibly null where grades failed).

- [ ] **Step 2: Haiku (cheap cloud reference)**

Run: `EVAL_BACKEND=claude-cli CLAUDE_CLI_MODEL=haiku python3 -m evals.run && mv evals/results/$(date -u +%F).json evals/results/2026-05-24-v0.3.4-haiku.json`
Expected: proposer = Haiku, grader = Haiku (pinned); clean Claude-quality grades (no parse failures).

- [ ] **Step 3: Sonnet**

Run: `EVAL_BACKEND=claude-cli CLAUDE_CLI_MODEL=sonnet python3 -m evals.run && mv evals/results/$(date -u +%F).json evals/results/2026-05-24-v0.3.4-sonnet.json`
Expected: proposer = Sonnet, grader = Haiku (pinned) — verify the grader stayed Haiku.

- [ ] **Step 4: PAUSE — get explicit user go-ahead before the Opus leg (premium quota)**

Do not run Step 5 until the user confirms. Report the gemma/Haiku/Sonnet results first.

- [ ] **Step 5: Opus (premium, after go-ahead)**

Run: `EVAL_BACKEND=claude-cli CLAUDE_CLI_MODEL=opus python3 -m evals.run && mv evals/results/$(date -u +%F).json evals/results/2026-05-24-v0.3.4-opus.json`

- [ ] **Step 6: Update `evals/results/README.md`**

- Add the v0.3.4 columns (Code Grade + Model Grade) for all four backends.
- Add a bold note: **"v0.3.4 changed scoring semantics (applicable-checks denominator, reconciled fixtures 002/003/004, valid-only model grades). Numbers are NOT directly comparable to ≤v0.3.3."**
- Correct the grader-model claim to: **"the grader is pinned to Haiku (`GRADER_MODEL`) for every run, so columns are comparable; the proposer model is what varies."**
- Note the new per-fixture fields (`code_mean`, `clean_rate`, `coverage`).

- [ ] **Step 7: Commit**

```bash
git add evals/results/2026-05-24-v0.3.4-*.json evals/results/README.md
git commit -m "$(cat <<'EOF'
test(eval): v0.3.4 full-matrix baseline under new scoring semantics

First baseline with applicable-checks denominator, reconciled fixtures, pinned
Haiku grader, and valid-only model grades. README notes the semantics break
(not comparable to <=v0.3.3) and the pinned-grader change.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Release — version bump, CHANGELOG, full test sweep

**Files:**
- Modify: `plugin/.claude-plugin/plugin.json` (version)
- Modify: `CHANGELOG.md` (new entry)

- [ ] **Step 1: Bump the plugin version**

In `plugin/.claude-plugin/plugin.json`, change `"version": "0.3.3"` to `"version": "0.3.4"`.

- [ ] **Step 2: Verify the bump**

Run: `grep '"version"' plugin/.claude-plugin/plugin.json`
Expected: `"version": "0.3.4"`

- [ ] **Step 3: Prepend the CHANGELOG entry**

Insert directly below the `All notable changes…` line in `CHANGELOG.md`:

```markdown
## [0.3.4] — 2026-05-24

### Fixed
- **Code grade no longer rewards shape.** Non-applicable checks return `None` and are excluded from the mean (applicable-checks denominator), so a wrong-form or no-op proposal can't collect free points (`evals/grade_code.py`).
- **`imperative_stderr` scores intent, not exact tokens.** Accepts a clause-leading imperative verb ("Fix the reported issues before continuing.") in addition to the v0.3.1 tokens — still a binary pattern match per the founding doc.
- **Model grade stops counting truncation as 0.** `grade_model` asks for compact JSON, raises `max_tokens` to 2048, and returns `{valid:false, score:null}` on parse failure; `run.py` excludes invalid grades from averages.
- **Fixtures 002/003/004 reconciled with their planted problems.** 002 → `Read(**/.env*)`; 003 → `required_rules` covering both forbidden paths (graded by union coverage); 004 accepts prompt-hook OR PostToolUse command-hook.

### Changed
- **Grader pinned to Haiku for every run; `claude-cli` respects the per-call model.** Frontier columns are now graded by one model (comparable + reproducible); the proposer model is what varies. Corrects the README's prior "same-family grading" claim.
- **Aggregation adds `code_mean`, `clean_rate`, and per-fixture `coverage`** alongside the max headline, so noisy proposal sets and partial multi-rule coverage are visible. Code and model grades are reported separately (never blended) — the deterministic code grade is the autonomy-gating metric; the model grade is advisory.
- **Full-matrix baseline re-scored** under the new semantics (`evals/results/2026-05-24-v0.3.4-*.json`). Not comparable to ≤v0.3.3.

### Why this release
v0.3.3 was measurement *hygiene*; v0.3.4 is measurement *correctness* — it makes the eval score trustworthy enough to gate the autonomous Karpathy loop the project is built around (commit-if-better / reset-if-worse). The structural enforcement primitive remains v0.4.
```

- [ ] **Step 4: Run the entire test suite**

Run: `python3 -m pytest -q`
Expected: all tests pass; integration tests skipped per `pyproject.toml`. No failures.

- [ ] **Step 5: Commit**

```bash
git add plugin/.claude-plugin/plugin.json CHANGELOG.md
git commit -m "$(cat <<'EOF'
v0.3.4: eval-measurement correctness — 4 findings closed

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage** — every approved fork / goal maps to a task:
- Fork 1 (applicable denominator) → Task 2 ✓
- Fork 2 (broaden imperative_stderr, stay binary) → Task 3 ✓
- Fork 3 (002/003 golds + coverage) → Task 4 (`rules_present`) + Task 5 (dataset) + Task 7 (coverage rollup) ✓
- Fork 4 (004 multi-form) → Task 4 (set-membership) + Task 5 (dataset) ✓
- Fork 5 (max + mean + clean_rate, don't blend) → Task 7 ✓
- Fork 6 (pin grader, respect model) → Task 6 ✓
- G1 (model-grade valid/null, exclude from avg) → Task 1 + Task 7 ✓
- G4 (reproducible + full matrix) → Task 6 + Task 8 ✓
- Spec §4 contracts (expected_hook_traits, grade_code, grade_model, run.py summary, client) → Tasks 1,2,4,6,7 ✓

**Type/name consistency:** `valid`/`score`/`error` (Task 1) consumed by `_aggregate` (Task 7). `rules_present` produced by `grade_code` (Task 4), consumed by `_aggregate` (Task 7). `_to_cli_model`/`_CLI_MODEL_MAP` defined and used in Task 6. `CLEAN_THRESHOLD`, `run_one_entry(proposer_model=...)`, `expected_hook_traits` carried (Tasks 6,7) used consistently. `GRADER_MODEL` imported from `grade_model` in the Task 6 test.

**No placeholders:** every code step shows complete code; every run step gives an exact command + expected output. The two unavoidable judgment steps are explicit: Task 2 Step 5 (update pre-existing N/A assertions — necessary because v0.3.3's end-state test file is unknown) and Task 5 precondition (verify Read-vs-Grep/Glob semantics — the knowledge base is self-contradictory). Both name exactly what to decide and the conservative default.

**Delta correctness:** builds on (does not recreate) v0.3.3's `_extract_stderr_strings`, `client_claude_cli.py`, and `claude-cli` backend wiring; reverses exactly one v0.3.3 decision (model-kwarg) with an explicit test replacement (Task 6 Step 1).

**Out of scope (deferred):** behavioral/integration harness, eval-the-real-SKILL.md, knowledge-base re-grounding — these are v0.4 Track 6/7 (the parallel v0.4 backlog already owns them).

---

## Execution Handoff

⛔ **HOLD.** Per the user's instruction, do not execute until they confirm **v0.3.3 is finished and merged** (this plan is a delta on that end-state). When that signal comes, the recommended path is **subagent-driven** (REQUIRED SUB-SKILL: superpowers:subagent-driven-development) — one fresh subagent per task with review between tasks, scheduling the three Phase-1 groups (`{Task 1}`, `{Task 2→3→4→5}`, `{Task 6}`) in parallel, then Task 7, then the human/quota-gated Task 8, then Task 9.
