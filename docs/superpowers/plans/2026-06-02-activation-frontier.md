# Activation Frontier (v0.6.0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the autonomous loop so one run optimizes *both* the skill's output quality (procedure, existing) and its activation (the `description` frontmatter, new) — with activation measured by really running Claude and deterministically detecting whether it invoked the skill.

**Architecture:** Two cleanly-separable axes share one driver. The OUTPUT axis is unchanged (edits `_shared/orchestrator-procedure.md`, scored on rubric fixtures). The new ACTIVATION axis edits the `description:` line of the two skill preambles, scored on new activation fixtures via a `PreToolUse`/matcher-`Skill` hook that records + exit-2 blocks the skill invocation (detection + short-circuit in one). Each axis gates on its own deterministic metric set (the verifier wall, `prompt-engineering.md §8.6`); `auto_loop.main` interleaves the two axis types across iterations.

**Tech Stack:** Python 3.10 (`from __future__ import annotations`), pytest (no conftest; `tmp_path`/`monkeypatch`), the `claude` CLI sandbox (`evals/sandbox_runner.py` pattern), git-as-ratchet.

**Grounding:** `plugins-and-skills.md §4` (description drives model-invocation), `prompt-engineering.md §8.1/§8.3/§8.4/§8.6`, `eval-methodology.md §3/§Variance`, `hooks-and-sdk.md §4–5/§9`, `tools-reference.md §1` (PreToolUse stdin envelope), `agentic-patterns.md §2d`.

**Spec:** `docs/superpowers/specs/2026-06-02-activation-frontier-design.md`.

---

## File Structure

| File | Responsibility |
|---|---|
| `evals/activation/dataset.json` | `{"entries":[...]}` — activation fixtures (fire/no-fire, skill, tier, holdout, reference_fix) |
| `evals/activation/<id>/scenario.md` | the conversation/prompt fed to Claude for a fixture |
| `evals/activation/<id>/reference_fix.json` | answer-key description edit (calibration A/B) |
| `evals/activation_lib.py` | `load_activation_dataset()`, `load_activation_fixture(id)`, `ActivationFixture` dataclass |
| `evals/grade_activation.py` | pure: per-fixture firing-rates → `activation_score` + `false_positive_rate` summary |
| `evals/activation_runner.py` | sandbox run + `Skill`-hook firing detection + N-sampling; `run_activation_suite` |
| `evals/ratchet.py` | extend `strictly_better`/`regresses`/`confirmation_verdict` to accept a metric set |
| `evals/edit_proposer.py` | add preambles to `ALLOWED_FILES`; `propose_description_edit` |
| `evals/auto_loop.py` | allowlist += preambles; activation eval helpers; `pick_dual_axis_target`; `run_activation_iteration`; `main` dispatch |
| `evals/calibrate.py` | `calibrate_activation_all` + `_write_activation_tiers` |
| `evals/tests/test_*.py` | one test module per new unit |

**Established patterns to follow:** ratchet operates on **plain dicts** keyed `average_code`/`install_rate`/`fire_rate`/`average_restraint` (NOT a dataclass). `apply_edit(edit, repo_root)` already enforces the allowlist + the 8-line `MAX_NEW_CONTENT_LINES` budget — a description edit is one line, so it passes. The summary dicts come from `_aggregate_sandbox` (`evals/run.py`). Tests use `tmp_path`/`monkeypatch`, no conftest. Run tests: `python3 -m pytest evals/ -q` (add `-m "not integration"` to skip live-CLI tests).

---

## Task 0: Feasibility spike (GATES ALL BUILD WORK)

**This is an experiment, not TDD. Do not start Task 1 until this passes and the controller has reviewed it.**

**Files:**
- Create: `evals/activation/_spike/README.md` (findings), `evals/activation/_spike/scenario_fire.md`, `evals/activation/_spike/scenario_nofire.md`, `evals/activation/_spike/skill_hook.py` (the marker hook), `evals/activation/_spike/run_spike.sh`

- [ ] **Step 1: Write a fire scenario and a no-fire scenario**

`evals/activation/_spike/scenario_fire.md` — a realistic context where the skill SHOULD fire (Claude just did something the user clearly wants prevented):
```
I just watched you run `git push --force origin main` without asking me, and it
overwrote a teammate's commits. I do not want that to ever happen again on this project.
```
`evals/activation/_spike/scenario_nofire.md` — unrelated request where the skill must stay silent:
```
Can you help me write a Python function that returns the nth Fibonacci number, with memoization?
```

- [ ] **Step 2: Write the short-circuit detector hook**

`evals/activation/_spike/skill_hook.py` — a PreToolUse hook that records a `Skill` invocation and blocks it (exit 2). Branch on `tool_name` per `tools-reference.md §1`:
```python
#!/usr/bin/env python3
"""PreToolUse hook: record + block any `Skill` invocation, so we capture the
model's decision-to-invoke without paying for the full orchestrator run."""
import json, os, sys

def main() -> int:
    try:
        ev = json.load(sys.stdin)
    except Exception:
        return 0
    if ev.get("tool_name") != "Skill":
        return 0
    ti = ev.get("tool_input") or {}
    marker = os.environ.get("SPIKE_MARKER", "/tmp/sic-spike-marker.json")
    with open(marker, "w", encoding="utf-8") as fh:
        json.dump({"tool_input": ti}, fh)
    print("activation-probe: skill invocation recorded and blocked", file=sys.stderr)
    return 2  # block (PreToolUse) — hooks-and-sdk.md §4

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run the fire scenario through the real sandbox CLI**

Use the exact `evals/sandbox_runner.py` invocation, but pass the scenario as the natural prompt (NOT a slash command) and register the hook via `--append-system-prompt` is NOT how hooks load — instead write the hook into a temp project `.claude/settings.json`. Manual one-off:
```bash
bash evals/activation/_spike/run_spike.sh fire
bash evals/activation/_spike/run_spike.sh nofire
```
`run_spike.sh` must: make a temp dir; write `.claude/settings.json` with a `PreToolUse` matcher-`Skill` command hook pointing at `skill_hook.py` (absolute path); `export SPIKE_MARKER=$tmp/marker.json`; remove any stale marker; then run
```bash
claude --print \
  --model haiku \
  --plugin-dir "$REPO/plugin" \
  --permission-mode bypassPermissions \
  --output-format json \
  --no-session-persistence \
  --max-budget-usd 1.0 \
  "$(cat "$REPO/evals/activation/_spike/scenario_$1.md")"
```
then print whether `$tmp/marker.json` exists.

- [ ] **Step 4: Confirm the four checks and write findings**

In `evals/activation/_spike/README.md`, record concrete answers:
1. **Spontaneous invocation:** did the model invoke a plugin skill on the *fire* scenario (marker written)? did it stay silent on *no-fire* (no marker)?
2. **Detectability:** what is the exact `tool_input` shape the `Skill` hook saw (the field naming the skill — e.g. `{"skill":"improve",...}` or `{"name":"improve-init"}`)? Record it verbatim — Task 3's detector parses this.
3. **Short-circuit:** did exit-2 block the skill (orchestrator did not run, marker present, run cheap/fast)? Note whether `bypassPermissions` still fires PreToolUse hooks.
4. **Isolation:** edit the `description:` line in `plugin/skills/_shared/preambles/improve.md`, run `python3 scripts/sync_skills.py`, run one rubric fixture (`python3 -m evals.run --sandbox --entry 001-pnpm-test-watcher`), confirm the rubric score is unchanged vs baseline; then `git checkout` the preamble + re-sync.

- [ ] **Step 5: Decision gate — commit findings, STOP for controller review**

```bash
git add evals/activation/_spike/
git commit -m "spike(v0.6.0): activation firing-detection feasibility — findings + probe"
```
**If check 1 fails** (model won't spontaneously invoke in `--print`): STOP. The measurement mechanism falls back to a constructed-choice harness (spec §13) and the plan needs re-spec before Task 3. Report to the controller. **Do not proceed to Task 1 until checks pass.**

---

## Task 1: Activation fixture schema + loader + 2 seed fixtures

**Files:**
- Create: `evals/activation_lib.py`, `evals/activation/dataset.json`, `evals/activation/a01-pushed-force-unasked/scenario.md`, `evals/activation/a02-write-fibonacci/scenario.md`
- Test: `evals/tests/test_activation_lib.py`

- [ ] **Step 1: Write the failing test**

```python
# evals/tests/test_activation_lib.py
from evals.activation_lib import load_activation_dataset, load_activation_fixture

def test_dataset_wrapper_and_entries():
    entries = load_activation_dataset()
    assert isinstance(entries, list) and len(entries) >= 2
    e = entries[0]
    for k in ("id", "skill", "label", "scenario"):
        assert k in e
    assert e["label"] in ("fire", "no-fire")
    assert e["skill"] in ("improve", "improve-init")

def test_load_fixture_reads_scenario_text():
    fx = load_activation_fixture("a01-pushed-force-unasked")
    assert fx.id == "a01-pushed-force-unasked"
    assert fx.label == "fire"
    assert "force" in fx.scenario.lower()
```

- [ ] **Step 2: Run it — expect ImportError**

Run: `python3 -m pytest evals/tests/test_activation_lib.py -q`
Expected: FAIL (`ModuleNotFoundError: evals.activation_lib`)

- [ ] **Step 3: Write the dataset + seed fixtures**

`evals/activation/dataset.json`:
```json
{
  "entries": [
    {
      "id": "a01-pushed-force-unasked",
      "skill": "improve",
      "label": "fire",
      "scenario": "a01-pushed-force-unasked/scenario.md",
      "tier": "headroom",
      "rotation": true,
      "holdout": false
    },
    {
      "id": "a02-write-fibonacci",
      "skill": "improve",
      "label": "no-fire",
      "scenario": "a02-write-fibonacci/scenario.md",
      "tier": "restraint",
      "rotation": false,
      "holdout": false
    }
  ]
}
```
`evals/activation/a01-pushed-force-unasked/scenario.md`:
```
I just watched you run `git push --force origin main` without asking me, and it
overwrote a teammate's commits. I never want that to happen again on this project.
```
`evals/activation/a02-write-fibonacci/scenario.md`:
```
Can you help me write a Python function that returns the nth Fibonacci number, with memoization?
```

- [ ] **Step 4: Write the loader**

`evals/activation_lib.py`:
```python
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

ACTIVATION_DIR = Path(__file__).resolve().parent / "activation"

@dataclass
class ActivationFixture:
    id: str
    skill: str
    label: str        # "fire" | "no-fire"
    scenario: str     # the prompt text

def load_activation_dataset() -> list[dict]:
    data = json.loads((ACTIVATION_DIR / "dataset.json").read_text(encoding="utf-8"))
    return data["entries"] if isinstance(data, dict) else data

def load_activation_fixture(fixture_id: str) -> ActivationFixture:
    entry = next((e for e in load_activation_dataset() if e["id"] == fixture_id), None)
    if entry is None:
        raise ValueError(f"activation fixture not found: {fixture_id}")
    scenario = (ACTIVATION_DIR / entry["scenario"]).read_text(encoding="utf-8").strip()
    return ActivationFixture(id=entry["id"], skill=entry["skill"],
                             label=entry["label"], scenario=scenario)
```

- [ ] **Step 5: Run tests — expect PASS, then commit**

Run: `python3 -m pytest evals/tests/test_activation_lib.py -q` → PASS
```bash
git add evals/activation_lib.py evals/activation/ evals/tests/test_activation_lib.py
git commit -m "feat(activation): fixture schema + loader + 2 seed fixtures"
```

---

## Task 2: grade_activation (pure metric grader)

**Files:**
- Create: `evals/grade_activation.py`, Test: `evals/tests/test_grade_activation.py`

- [ ] **Step 1: Write the failing test**

```python
# evals/tests/test_grade_activation.py
from evals.grade_activation import grade_activation

def _r(id, label, rate):
    return {"id": id, "skill": "improve", "label": label, "firing_rate": rate}

def test_perfect_suite_scores_ten_zero_fp():
    s = grade_activation([_r("a01", "fire", 1.0), _r("a02", "no-fire", 0.0)])
    assert s["activation_score"] == 10.0
    assert s["false_positive_rate"] == 0.0

def test_no_fire_overfiring_drives_score_down_and_fp_up():
    s = grade_activation([_r("a01", "fire", 1.0), _r("a02", "no-fire", 1.0)])
    # fire correct_rate=1.0, no-fire correct_rate=0.0 -> mean 0.5 -> 5.0
    assert s["activation_score"] == 5.0
    assert s["false_positive_rate"] == 1.0

def test_empty_suite_is_none():
    s = grade_activation([])
    assert s["activation_score"] is None
    assert s["false_positive_rate"] is None

def test_entries_carry_correct_rate():
    s = grade_activation([_r("a01", "fire", 0.6)])
    assert s["entries"][0]["correct_rate"] == 0.6
```

- [ ] **Step 2: Run it — expect ImportError.** `python3 -m pytest evals/tests/test_grade_activation.py -q`

- [ ] **Step 3: Implement**

`evals/grade_activation.py`:
```python
from __future__ import annotations

def _correct_rate(label: str, firing_rate: float) -> float:
    return firing_rate if label == "fire" else 1.0 - firing_rate

def grade_activation(per_fixture: list[dict]) -> dict:
    """per_fixture items: {id, skill, label, firing_rate in [0,1]}.
    Mirrors the 0/10 code-grader convention (eval-methodology.md §3): each fixture
    contributes correct_rate*10; activation_score is the mean. Higher is better, so
    no-fire over-firing pulls it down — false_positive_rate is reported separately."""
    entries = [
        {**r, "correct_rate": _correct_rate(r["label"], r["firing_rate"])}
        for r in per_fixture
    ]
    if not entries:
        return {"activation_score": None, "false_positive_rate": None, "entries": []}
    activation_score = round(10.0 * sum(e["correct_rate"] for e in entries) / len(entries), 4)
    no_fire = [e for e in entries if e["label"] == "no-fire"]
    fp = round(sum(e["firing_rate"] for e in no_fire) / len(no_fire), 4) if no_fire else None
    return {"activation_score": activation_score, "false_positive_rate": fp, "entries": entries}
```

- [ ] **Step 4: Run — PASS. Step 5: Commit**
```bash
git add evals/grade_activation.py evals/tests/test_grade_activation.py
git commit -m "feat(activation): grade_activation — firing-rate -> activation_score + false_positive_rate"
```

---

## Task 3: activation_runner (sandbox run + firing detection + N-sampling)

**Files:**
- Create: `evals/activation_runner.py`, Test: `evals/tests/test_activation_runner.py`
- Reference: `evals/sandbox_runner.py` (`_build_argv`), `evals/activation/_spike/README.md` (Task 0 findings)

> **Task 0 resolved the detection shape (findings A & B):** the `Skill` `tool_input` field is
> `skill`, plugin-namespaced as `self-improving-claude:improve`. A run may invoke MULTIPLE/other
> skills (the no-fire probe invoked `superpowers:brainstorming`). So the production hook **APPENDS**
> every invocation (JSONL, one line per call), and "fired" = the target skill `self-improving-claude:<skill>`
> is among the recorded invocations (suffix-match `:<skill>`). Code below reflects this.

- [ ] **Step 1: Write the failing test (pure parts only — detection + N-sample aggregation; mocked)**

```python
# evals/tests/test_activation_runner.py
import evals.activation_runner as ar

def test_detect_firing_reads_appended_invocations(tmp_path):
    marker = tmp_path / "marker.jsonl"
    marker.write_text('{"skill": "superpowers:brainstorming"}\n'
                      '{"skill": "self-improving-claude:improve"}\n', encoding="utf-8")
    assert ar.detect_firing(str(marker)) == ["superpowers:brainstorming",
                                             "self-improving-claude:improve"]

def test_detect_firing_absent_marker_is_empty(tmp_path):
    assert ar.detect_firing(str(tmp_path / "nope.jsonl")) == []

def test_fired_target_suffix_match():
    assert ar.fired_target(["self-improving-claude:improve"], "improve")
    assert not ar.fired_target(["superpowers:brainstorming"], "improve")
    assert not ar.fired_target(["self-improving-claude:improve-init"], "improve")

def test_firing_rate_counts_target_skill_hits(monkeypatch):
    runs = iter([["self-improving-claude:improve"], [], ["superpowers:brainstorming"],
                 ["self-improving-claude:improve"], ["self-improving-claude:improve"]])
    monkeypatch.setattr(ar, "_run_once", lambda **kw: next(runs))
    fx = ar.ActivationFixture(id="a01", skill="improve", label="fire", scenario="...")
    rate = ar.firing_rate_for_fixture(fx, n=5, model="haiku", effort=None)
    assert rate == 0.6  # 3 of 5 runs invoked the target skill
```

- [ ] **Step 2: Run — expect ImportError.** `python3 -m pytest evals/tests/test_activation_runner.py -q`

- [ ] **Step 3: Implement**

`evals/activation_runner.py`:
```python
from __future__ import annotations
import json, os, subprocess, tempfile
from pathlib import Path

from evals.activation_lib import ActivationFixture, load_activation_fixture, load_activation_dataset
from evals.client_claude_cli import _to_cli_model
from evals.grade_activation import grade_activation

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_PATH = REPO_ROOT / "plugin"
SKILL_HOOK = REPO_ROOT / "evals" / "activation" / "skill_hook.py"  # promoted from the spike

def detect_firing(marker_path: str) -> list[str]:
    """Return the skills invoked during the run (raw, plugin-namespaced), in order.
    Empty if the marker is absent. The hook appends one JSON line per Skill call
    (Task 0 finding B)."""
    p = Path(marker_path)
    if not p.exists():
        return []
    out: list[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        name = rec.get("skill") or rec.get("name")
        if name:
            out.append(name)
    return out

def fired_target(invoked: list[str], target: str) -> bool:
    """True if the target skill (e.g. 'improve') is among the invoked skills, matching the
    plugin-namespaced form 'self-improving-claude:improve' (Task 0 finding A)."""
    return any(s == f"self-improving-claude:{target}" or s.endswith(f":{target}")
               for s in invoked)

def _settings_with_skill_hook() -> dict:
    return {"hooks": {"PreToolUse": [{"matcher": "Skill", "hooks": [
        {"type": "command", "command": f"python3 {SKILL_HOOK}"}]}]}}

def _build_argv(*, model: str, scenario: str, effort: str | None) -> list[str]:
    argv = [
        "claude", "--print",
        "--model", _to_cli_model(model),
        "--plugin-dir", str(PLUGIN_PATH),
        "--permission-mode", "bypassPermissions",
        "--output-format", "json",
        "--no-session-persistence",
        "--max-budget-usd", "1.0",
    ]
    if effort:
        argv += ["--effort", effort]
    argv += [scenario]   # the scenario is a NATURAL prompt, not a slash command
    return argv

def _run_once(*, scenario: str, model: str, effort: str | None) -> str | None:
    """One sandbox run; returns the invoked skill name or None. Short-circuited by the
    Skill hook (exit 2), so the orchestrator never runs."""
    tmp = tempfile.mkdtemp(prefix="sic-act-")
    try:
        claude_dir = Path(tmp) / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        (claude_dir / "settings.json").write_text(
            json.dumps(_settings_with_skill_hook()), encoding="utf-8")
        marker = Path(tmp) / "marker.json"
        env = {**os.environ, "SPIKE_MARKER": str(marker)}
        subprocess.run(_build_argv(model=model, scenario=scenario, effort=effort),
                       cwd=tmp, capture_output=True, text=True, timeout=300, env=env)
        return detect_firing(str(marker))
    finally:
        import shutil; shutil.rmtree(tmp, ignore_errors=True)

def firing_rate_for_fixture(fx: ActivationFixture, *, n: int, model: str,
                            effort: str | None) -> float:
    """N-sample the invocation decision (eval-methodology.md §Variance): fraction of
    runs that invoked THIS fixture's target skill."""
    hits = 0
    for _ in range(n):
        if fired_target(_run_once(scenario=fx.scenario, model=model, effort=effort), fx.skill):
            hits += 1
    return round(hits / n, 4)

def run_activation_suite(*, n: int, model: str, effort: str | None,
                         filter_predicate=None) -> tuple[dict, list[dict]]:
    entries = load_activation_dataset()
    if filter_predicate is not None:
        entries = [e for e in entries if filter_predicate(e)]
    per_fixture = []
    for e in entries:
        fx = load_activation_fixture(e["id"])
        per_fixture.append({"id": fx.id, "skill": fx.skill, "label": fx.label,
                            "firing_rate": firing_rate_for_fixture(
                                fx, n=n, model=model, effort=effort)})
    return grade_activation(per_fixture), per_fixture
```

- [ ] **Step 4: Write the production hook (APPENDS — Task 0 finding B)**

The spike hook overwrote the marker; the production hook must append one JSON line per
`Skill` call so multi-skill runs are captured. `evals/activation/skill_hook.py`:
```python
#!/usr/bin/env python3
"""PreToolUse hook: append each `Skill` invocation to $SPIKE_MARKER (JSONL) and exit-2
block it — detection + short-circuit in one (Task 0)."""
import json, os, sys

def main() -> int:
    try:
        ev = json.load(sys.stdin)
    except Exception:
        return 0
    if ev.get("tool_name") != "Skill":
        return 0
    ti = ev.get("tool_input") or {}
    marker = os.environ.get("SPIKE_MARKER", "/tmp/sic-act-marker.jsonl")
    with open(marker, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"skill": ti.get("skill") or ti.get("name")}) + "\n")
    print("activation-probe: skill invocation recorded and blocked", file=sys.stderr)
    return 2

if __name__ == "__main__":
    sys.exit(main())
```
Keep `evals/activation/_spike/` (scenarios + README) for provenance.

- [ ] **Step 5: Run pure tests — PASS. Step 6: Commit**
```bash
git add evals/activation_runner.py evals/activation/skill_hook.py evals/tests/test_activation_runner.py
git commit -m "feat(activation): activation_runner — Skill-hook firing detection + N-sampling"
```

---

## Task 4: ratchet — accept a per-axis metric set

**Files:** Modify `evals/ratchet.py`; Test: extend `evals/tests/test_ratchet.py`

- [ ] **Step 1: Write the failing test**

```python
# append to evals/tests/test_ratchet.py
from evals.ratchet import strictly_better, regresses, ACTIVATION_METRICS, ACTIVATION_EPSILON

def test_activation_metric_set_gates_on_activation_score():
    old = {"activation_score": 5.0}
    new = {"activation_score": 7.0}
    assert strictly_better(new, old, metrics=ACTIVATION_METRICS, epsilon=ACTIVATION_EPSILON)
    assert not regresses(new, old, metrics=ACTIVATION_METRICS, epsilon=ACTIVATION_EPSILON)

def test_activation_regression_detected():
    assert regresses({"activation_score": 4.0}, {"activation_score": 6.0},
                     metrics=ACTIVATION_METRICS, epsilon=ACTIVATION_EPSILON)

def test_output_calls_unchanged_by_default():
    assert strictly_better({"average_code": 9.0}, {"average_code": 8.0})
```

- [ ] **Step 2: Run — expect ImportError on `ACTIVATION_METRICS`.** `python3 -m pytest evals/tests/test_ratchet.py -q`

- [ ] **Step 3: Implement — parameterize, keep output defaults**

In `evals/ratchet.py`, after the existing `EPSILON`/`GATING_METRICS`:
```python
ACTIVATION_EPSILON = {"activation_score": 0.10}
ACTIVATION_METRICS = tuple(ACTIVATION_EPSILON.keys())
```
Change the three function signatures to accept the metric set (defaults preserve today's behavior):
```python
def strictly_better(new: dict, old: dict, metrics=GATING_METRICS, epsilon=EPSILON) -> bool:
    saw_improvement = False
    for m in metrics:
        d = _delta(new.get(m), old.get(m))
        if d > epsilon[m]:
            saw_improvement = True
        elif d < -epsilon[m]:
            return False
    return saw_improvement

def regresses(new: dict, old: dict, metrics=GATING_METRICS, epsilon=EPSILON) -> bool:
    for m in metrics:
        d = _delta(new.get(m), old.get(m))
        if d < -epsilon[m]:
            return True
    return False

def confirmation_verdict(targets, holdouts, baseline, holdout_baseline,
                         metrics=GATING_METRICS, epsilon=EPSILON) -> bool:
    if not targets:
        return False
    majority = len(targets) // 2 + 1
    visible_hits = sum(1 for t in targets if strictly_better(t, baseline, metrics, epsilon))
    if visible_hits < majority:
        return False
    if holdout_baseline is not None:
        if any(regresses(h, holdout_baseline, metrics, epsilon) for h in holdouts):
            return False
    return True
```

- [ ] **Step 4: Run full ratchet suite — PASS (old + new).** `python3 -m pytest evals/tests/test_ratchet.py -q`
- [ ] **Step 5: Commit**
```bash
git add evals/ratchet.py evals/tests/test_ratchet.py
git commit -m "feat(activation): ratchet accepts a per-axis metric set (ACTIVATION_METRICS)"
```

---

## Task 5: edit_proposer — description-edit mode

**Files:** Modify `evals/edit_proposer.py`; Test: extend `evals/tests/test_edit_proposer.py`

- [ ] **Step 1: Write the failing test**

```python
# append to evals/tests/test_edit_proposer.py
from evals.edit_proposer import parse_proposer_response, ALLOWED_FILES, propose_description_edit

def test_preambles_are_allowed_files():
    assert "plugin/skills/_shared/preambles/improve.md" in ALLOWED_FILES
    assert "plugin/skills/_shared/preambles/improve-init.md" in ALLOWED_FILES

def test_parse_accepts_description_replace_on_preamble():
    raw = '''{"file":"plugin/skills/_shared/preambles/improve.md",
      "operation":"replace","anchor":"right after seeing Claude",
      "anchor_position":"before",
      "new_content":"the moment you notice Claude do something you want prevented",
      "hypothesis":"sharpen the fire trigger","confidence":7}'''
    p = parse_proposer_response(raw)
    assert p.file.endswith("preambles/improve.md")
    assert p.operation == "replace"

class _FakeResp:
    def __init__(self, text): self.content = [type("C", (), {"text": text})]
class _FakeClient:
    def __init__(self, text): self._t = text
    class _M:
        def __init__(self, t): self._t = t
        def create(self, **kw): return _FakeResp(self._t)
    @property
    def messages(self): return _FakeClient._M(self._t)

def test_propose_description_edit_returns_proposal():
    raw = '{"file":"plugin/skills/_shared/preambles/improve.md","operation":"replace",' \
          '"anchor":"X","anchor_position":"before","new_content":"Y",' \
          '"hypothesis":"h","confidence":8}'
    p = propose_description_edit(
        activation_failure={"skill": "improve", "current_description": "...X...",
                            "missed_fire": ["a01"], "false_fire": []},
        history=[], client=_FakeClient(raw), model="haiku")
    assert p is not None and p.operation == "replace"
```

- [ ] **Step 2: Run — expect ImportError on `propose_description_edit`.**

- [ ] **Step 3: Implement**

In `evals/edit_proposer.py`, extend the constant:
```python
ALLOWED_FILES = (
    "plugin/skills/_shared/orchestrator-procedure.md",
    "plugin/skills/_shared/references/prompt-rubric.md",
    "plugin/skills/_shared/references/examples.md",
    "plugin/skills/_shared/preambles/improve.md",
    "plugin/skills/_shared/preambles/improve-init.md",
)
```
Add the activation prompt assembler + proposer (mirrors `propose_edit`'s client call; `parse_proposer_response` is reused unchanged — preambles are now allowed):
```python
def assemble_activation_proposer_prompt(*, activation_failure: dict, history: list[dict]) -> str:
    skill = activation_failure["skill"]
    return (
        "You tune the `description:` frontmatter of a Claude Code skill so the model "
        "invokes it at exactly the right moment and never otherwise.\n\n"
        f"<skill>{skill}</skill>\n"
        f"<current_description>{activation_failure['current_description']}</current_description>\n"
        f"<missed_fire_scenarios>{activation_failure.get('missed_fire', [])}</missed_fire_scenarios>\n"
        f"<false_fire_scenarios>{activation_failure.get('false_fire', [])}</false_fire_scenarios>\n"
        f"<recent_attempts>{_format_history(history)}</recent_attempts>\n\n"
        "Propose ONE bounded clause-level edit to the description (operation=replace, "
        "anchor=a unique substring of the current description, new_content=the rewritten "
        "clause). Do NOT rewrite the whole description. Output ONLY JSON with keys: "
        "file, operation, anchor, anchor_position, new_content, hypothesis, confidence."
    )

def propose_description_edit(*, activation_failure: dict, history: list[dict],
                             client, model: str) -> Optional[EditProposal]:
    prompt = assemble_activation_proposer_prompt(
        activation_failure=activation_failure, history=history)
    resp = client.messages.create(
        model=model, max_tokens=2048, messages=[{"role": "user", "content": prompt}])
    proposal = parse_proposer_response(resp.content[0].text)
    if proposal.confidence < LOW_CONFIDENCE_THRESHOLD:
        return None
    return proposal
```

- [ ] **Step 4: Run — PASS. Step 5: Commit**
```bash
git add evals/edit_proposer.py evals/tests/test_edit_proposer.py
git commit -m "feat(activation): edit_proposer description-edit mode (preambles allowlisted)"
```

> **Note:** `apply_edit` in `auto_loop.py` validates against `SLOW_STATE_ALLOWLIST`; Task 6 adds the preambles there so applied description edits aren't rejected.

---

## Task 6: auto_loop — allowlist + activation eval helpers + saturation

**Files:** Modify `evals/auto_loop.py`; Test: extend `evals/tests/test_auto_loop.py`

- [ ] **Step 1: Write the failing test**

```python
# append to evals/tests/test_auto_loop.py
from evals.auto_loop import SLOW_STATE_ALLOWLIST, is_activation_saturated

def test_preambles_in_allowlist():
    assert "plugin/skills/_shared/preambles/improve.md" in SLOW_STATE_ALLOWLIST
    assert "plugin/skills/_shared/preambles/improve-init.md" in SLOW_STATE_ALLOWLIST

def test_activation_saturated_at_ceiling():
    assert is_activation_saturated({"activation_score": 10.0})
    assert not is_activation_saturated({"activation_score": 8.0})
    assert is_activation_saturated({"activation_score": None})  # N/A counts as saturated
```

- [ ] **Step 2: Run — expect ImportError / assertion fail.**

- [ ] **Step 3: Implement**

In `evals/auto_loop.py`, extend the allowlist:
```python
SLOW_STATE_ALLOWLIST = frozenset({
    "plugin/skills/_shared/orchestrator-procedure.md",
    "plugin/skills/_shared/references/prompt-rubric.md",
    "plugin/skills/_shared/references/examples.md",
    "plugin/skills/_shared/preambles/improve.md",
    "plugin/skills/_shared/preambles/improve-init.md",
})
```
Add the activation saturation check + eval helpers (lazy import, mirroring `run_visible_eval`):
```python
def is_activation_saturated(summary: dict) -> bool:
    s = summary.get("activation_score")
    return s is None or s >= 10.0 - 0.10  # ACTIVATION_EPSILON

def run_activation_eval(skill_model: str, effort: str | None,
                        holdout: bool | None) -> tuple[dict, list[dict]]:
    """holdout=None -> all; False -> visible only; True -> holdout only."""
    from evals.activation_runner import run_activation_suite
    if holdout is None:
        pred = None
    else:
        pred = (lambda e: bool(e.get("holdout")) == holdout)
    n = int(os.environ.get("ACTIVATION_N", "3"))
    return run_activation_suite(n=n, model=skill_model, effort=effort, filter_predicate=pred)
```

- [ ] **Step 4: Run — PASS. Step 5: Commit**
```bash
git add evals/auto_loop.py evals/tests/test_auto_loop.py
git commit -m "feat(activation): allowlist preambles + activation eval helpers + saturation check"
```

---

## Task 7: auto_loop — dual-axis target picker

**Files:** Modify `evals/auto_loop.py`; Test: extend `evals/tests/test_auto_loop.py`

- [ ] **Step 1: Write the failing test**

```python
# append to evals/tests/test_auto_loop.py
from evals.auto_loop import pick_dual_axis_target

def test_picks_axis_with_most_headroom():
    out = {"entries": [{"id": "001", "code_max": 9.5, "install_rate": 1.0}]}   # norm ~0.975
    act = {"entries": [{"id": "a01", "label": "fire", "correct_rate": 0.4}]}    # norm 0.40
    axis, tid = pick_dual_axis_target(out, act, recent_picks=[],
                                      eligible_output_ids={"001"},
                                      eligible_activation_ids={"a01"})
    assert (axis, tid) == ("activation", "a01")

def test_avoids_recent_picks():
    out = {"entries": [{"id": "001", "code_max": 2.0, "install_rate": 0.0}]}   # norm 0.10
    act = {"entries": [{"id": "a01", "label": "fire", "correct_rate": 0.9}]}    # norm 0.90
    axis, tid = pick_dual_axis_target(out, act, recent_picks=["001"],
                                      eligible_output_ids={"001"},
                                      eligible_activation_ids={"a01"})
    assert (axis, tid) == ("activation", "a01")  # 001 skipped despite more headroom
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement (normalized cross-axis headroom)**

```python
def _output_headroom_norm(e: dict) -> float:
    return ((e.get("code_max") or 0.0) / 10.0 + (e.get("install_rate") or 0.0)) / 2.0

def pick_dual_axis_target(output_baseline: dict, activation_baseline: dict,
                          recent_picks: list[str], *,
                          eligible_output_ids: set[str],
                          eligible_activation_ids: set[str]) -> tuple[str, str]:
    """Return (axis, target_id) for the eligible fixture with the LOWEST normalized
    score (most headroom) across both axes, avoiding the last-2 recent picks. Normalized
    score in [0,1]; output uses (code_max/10 + install_rate)/2, activation uses correct_rate."""
    recent = set(recent_picks[-2:])
    cands: list[tuple[float, str, str]] = []
    for e in output_baseline.get("entries", []):
        if e["id"] in eligible_output_ids:
            cands.append((_output_headroom_norm(e), "output", e["id"]))
    for e in activation_baseline.get("entries", []):
        if e["id"] in eligible_activation_ids:
            cands.append((float(e.get("correct_rate") or 0.0), "activation", e["id"]))
    if not cands:
        raise ValueError("no eligible dual-axis targets")
    fresh = [c for c in cands if c[2] not in recent] or cands
    fresh.sort(key=lambda c: (c[0], c[2]))  # lowest score, stable by id
    score, axis, tid = fresh[0]
    return axis, tid
```

> Note: the activation `entries` carry `correct_rate` (added by `grade_activation`, Task 2). The output `entries` carry `code_max`/`install_rate` (from `_aggregate_sandbox`).

- [ ] **Step 4: Run — PASS. Step 5: Commit**
```bash
git add evals/auto_loop.py evals/tests/test_auto_loop.py
git commit -m "feat(activation): dual-axis target picker (normalized cross-axis headroom)"
```

---

## Task 8: auto_loop — run_activation_iteration

**Files:** Modify `evals/auto_loop.py`; Test: extend `evals/tests/test_auto_loop.py`

Mirrors `run_iteration` but for the activation axis: propose description edit → apply → sync → activation visible eval → activation ratchet (`ACTIVATION_METRICS`) → activation held-out gate → confirmation → keep/revert + audit.

- [ ] **Step 1: Write the failing test (keep/revert via monkeypatch — no live CLI)**

```python
# append to evals/tests/test_auto_loop.py
import evals.auto_loop as al

def test_activation_iteration_reverts_on_no_gain(monkeypatch):
    # proposer returns a valid edit; eval shows no gain -> revert, decision recorded
    from evals.edit_proposer import EditProposal
    prop = EditProposal(file="plugin/skills/_shared/preambles/improve.md",
                        operation="replace", anchor="X", anchor_position="before",
                        new_content="Y", hypothesis="h", confidence=8)
    monkeypatch.setattr(al, "propose_description_edit", lambda **kw: prop)
    monkeypatch.setattr(al, "apply_edit", lambda *a, **k: (True, "applied"))
    monkeypatch.setattr(al, "run_sync_skills", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr(al, "run_activation_eval",
                        lambda *a, **k: ({"activation_score": 5.0, "entries": []}, []))
    monkeypatch.setattr(al, "git_reset_sync_paths", lambda *a, **k: None)
    audit = al.AuditLog(root=None) if False else _StubAudit()
    base = {"activation_score": 5.0, "entries": []}
    new_base, decision = al.run_activation_iteration(
        i=1, target_id="a01", baseline=base, holdout_baseline=None,
        audit=audit, client=object(), proposer_model="haiku", skill_model="haiku",
        effort=None, confirmation_reruns=0)
    assert decision.startswith("rejected: no_visible_gain")
    assert new_base == base

class _StubAudit:
    def last_n_rejected_edits(self, n): return []
    def write_iteration(self, rec): self.rec = rec
```

- [ ] **Step 2: Run — expect ImportError on `run_activation_iteration`.**

- [ ] **Step 3: Implement (structure mirrors run_iteration; uses ACTIVATION metric set)**

```python
def _activation_failure(target_id: str, baseline: dict, skill: str, description: str) -> dict:
    missed = [e["id"] for e in baseline.get("entries", [])
              if e["label"] == "fire" and (e.get("correct_rate") or 0) < 1.0]
    false_fire = [e["id"] for e in baseline.get("entries", [])
                  if e["label"] == "no-fire" and (e.get("correct_rate") or 1) < 1.0]
    return {"skill": skill, "current_description": description,
            "missed_fire": missed, "false_fire": false_fire}

def run_activation_iteration(*, i: int, target_id: str, baseline: dict,
                             holdout_baseline: dict | None, audit, client,
                             proposer_model: str, skill_model: str,
                             effort: str | None = None,
                             confirmation_reruns: int = 2) -> tuple[dict, str]:
    from evals.ratchet import (strictly_better, regresses, confirmation_verdict,
                               ACTIVATION_METRICS, ACTIVATION_EPSILON)
    import datetime as _dt
    ts = "n/a"
    rec = {"i": i, "ts": ts, "axis": "activation", "fixture": target_id}

    if is_activation_saturated(baseline):
        rec["decision"] = "skipped: saturated_baseline"; audit.write_iteration(rec)
        return baseline, rec["decision"]

    # locate skill + current description from the activation entry + preamble
    from evals.activation_lib import load_activation_fixture
    skill = load_activation_fixture(target_id).skill
    preamble_rel = f"plugin/skills/_shared/preambles/{skill}.md"
    description = _read_description(REPO_ROOT / preamble_rel)

    try:
        proposal = propose_description_edit(
            activation_failure=_activation_failure(target_id, baseline, skill, description),
            history=audit.last_n_rejected_edits(5), client=client, model=proposer_model)
    except Exception as ex:
        rec["decision"] = f"rejected: invalid_edit ({ex})"; audit.write_iteration(rec)
        return baseline, rec["decision"]
    if proposal is None:
        rec["decision"] = "rejected: low_confidence"; audit.write_iteration(rec)
        return baseline, rec["decision"]
    rec["edit"] = proposal.to_edit_dict(); rec["hypothesis"] = proposal.hypothesis

    ok, reason = apply_edit(proposal.to_edit_dict())
    if not ok:
        rec["decision"] = f"rejected: invalid_edit ({reason})"; audit.write_iteration(rec)
        return baseline, rec["decision"]
    ok, reason = run_sync_skills()
    if not ok:
        git_reset_sync_paths(); rec["decision"] = f"rejected: sync_failed ({reason})"
        audit.write_iteration(rec); return baseline, rec["decision"]

    try:
        new_base, _ = run_activation_eval(skill_model, effort, holdout=False)
    except Exception as ex:
        git_reset_sync_paths(); rec["decision"] = f"rejected: eval_failed ({ex})"
        audit.write_iteration(rec); return baseline, rec["decision"]
    rec["scores_before"] = baseline; rec["scores_after"] = new_base

    if not strictly_better(new_base, baseline, ACTIVATION_METRICS, ACTIVATION_EPSILON):
        git_reset_sync_paths(); rec["decision"] = "rejected: no_visible_gain"
        audit.write_iteration(rec); return baseline, rec["decision"]

    targets, holdouts = [new_base], []
    if holdout_baseline is not None:
        new_hold, _ = run_activation_eval(skill_model, effort, holdout=True)
        if regresses(new_hold, holdout_baseline, ACTIVATION_METRICS, ACTIVATION_EPSILON):
            git_reset_sync_paths(); rec["decision"] = "rejected: holdout_regression"
            audit.write_iteration(rec); return baseline, rec["decision"]
        holdouts.append(new_hold)
    for _ in range(confirmation_reruns):
        t, _ = run_activation_eval(skill_model, effort, holdout=False); targets.append(t)
        if holdout_baseline is not None:
            h, _ = run_activation_eval(skill_model, effort, holdout=True); holdouts.append(h)
    if not confirmation_verdict(targets, holdouts, baseline, holdout_baseline,
                                ACTIVATION_METRICS, ACTIVATION_EPSILON):
        git_reset_sync_paths(); rec["decision"] = "rejected: confirmation_failed"
        audit.write_iteration(rec); return baseline, rec["decision"]

    sha = git_commit_iteration(f"auto-loop[i={i}][activation]: {proposal.hypothesis[:70]}")
    rec["decision"] = "kept"; rec["commit_sha"] = sha; audit.write_iteration(rec)
    return new_base, "kept"
```
Add the helper:
```python
def _read_description(preamble_path: Path) -> str:
    for line in preamble_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("description:"):
            return line[len("description:"):].strip()
    return ""
```

- [ ] **Step 4: Run — PASS. Step 5: Commit**
```bash
git add evals/auto_loop.py evals/tests/test_auto_loop.py
git commit -m "feat(activation): run_activation_iteration (mirror of run_iteration, activation gate)"
```

---

## Task 9: auto_loop — main dispatch (interleave both axes)

**Files:** Modify `evals/auto_loop.py` (`main`); Test: a focused dispatch test in `evals/tests/test_auto_loop.py`

- [ ] **Step 1: Write the failing test (dispatch routing only; monkeypatch both iteration fns)**

```python
# append to evals/tests/test_auto_loop.py
def test_main_dispatches_by_axis(monkeypatch):
    routed = []
    monkeypatch.setattr(al, "pick_dual_axis_target",
                        lambda *a, **k: ("activation", "a01"))
    monkeypatch.setattr(al, "run_activation_iteration",
                        lambda **k: routed.append("activation") or ({"activation_score": 10.0}, "kept"))
    monkeypatch.setattr(al, "run_iteration",
                        lambda **k: routed.append("output") or ({}, None, None))
    # the dispatch helper is the unit under test (extracted so main stays testable):
    al.dispatch_iteration(axis="activation", i=1, target_id="a01",
                          activation_baseline={"activation_score": 5.0},
                          activation_holdout=None, output_state={}, common={})
    assert routed == ["activation"]
```

- [ ] **Step 2: Run — expect ImportError on `dispatch_iteration`.**

- [ ] **Step 3: Implement the dispatch seam, then wire `main`**

Extract a small router so `main` stays thin and testable:
```python
def dispatch_iteration(*, axis: str, i: int, target_id: str,
                       activation_baseline: dict, activation_holdout: dict | None,
                       output_state: dict, common: dict):
    if axis == "activation":
        return run_activation_iteration(
            i=i, target_id=target_id, baseline=activation_baseline,
            holdout_baseline=activation_holdout, **common)
    return run_iteration(i=i, target_id=target_id, baseline=output_state["target_baseline"],
                         last_result=output_state["last_result"],
                         holdout_baseline=output_state["holdout_baseline"], **common["output"])
```
In `main`, after computing the existing output `eligible_ids`, also compute the activation pool and baselines, then route each iteration:
```python
    activation_eligible = {e["id"] for e in load_activation_dataset()
                           if e.get("tier") == "headroom" and e.get("rotation", True)}
    # baselines for the picker (rotation mode):
    activation_baseline, _ = run_activation_eval(args.skill_runner, effort, holdout=None)
    activation_holdout = None
    if holdout_gate_on:
        activation_holdout, _ = run_activation_eval(args.skill_runner, effort, holdout=True)
    # inside the loop, replacing the single-axis pick_target call:
    axis, target_id = pick_dual_axis_target(
        state["visible_baseline"], activation_baseline, recent_picks,
        eligible_output_ids=eligible_ids, eligible_activation_ids=activation_eligible)
```
Add `--activation-n` (default 3) and `--no-activation` flags; `--no-activation` makes `activation_eligible` empty so the picker stays output-only (back-compat / cheap runs). Extend `_estimate_iteration_cost_usd` with an activation branch (`ACTIVATION_N × #activation_fixtures` haiku decisions) — keep it advisory.

- [ ] **Step 4: Run — PASS. Step 5: Commit**
```bash
git add evals/auto_loop.py evals/tests/test_auto_loop.py
git commit -m "feat(activation): main interleaves both axes via dispatch_iteration"
```

---

## Task 10: calibrate — activation calibration

**Files:** Modify `evals/calibrate.py`; Test: `evals/tests/test_calibrate.py`

- [ ] **Step 1: Write the failing test**

```python
# append to evals/tests/test_calibrate.py
from evals.calibrate import classify_activation_tier

def test_activation_tier_saturated():
    assert classify_activation_tier({"activation_score": 10.0}, expect_no_proposal=False,
                                    ab_passed=None) == "saturated"

def test_activation_tier_headroom_when_ab_passes():
    assert classify_activation_tier({"activation_score": 6.0}, expect_no_proposal=False,
                                    ab_passed=True) == "headroom"

def test_activation_tier_restraint_for_no_fire():
    assert classify_activation_tier({"activation_score": 9.0}, expect_no_proposal=True,
                                    ab_passed=None) == "restraint"
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement (reuse the v0.5.2 tier shape, activation metric)**

```python
def classify_activation_tier(median_sum: dict, *, expect_no_proposal: bool,
                             ab_passed: bool | None) -> str:
    if expect_no_proposal:
        return "restraint"
    score = median_sum.get("activation_score")
    if score is not None and score >= 10.0 - 0.10:
        return "saturated"
    if ab_passed is True:
        return "headroom"
    if ab_passed is False:
        return "brick"
    return "headroom" if (score or 0.0) >= 5.0 else "brick"
```
Add `calibrate_activation_all(*, n, skill_model, effort, only, write)` that runs `firing_rate_for_fixture` N times per fixture, builds a median activation summary, runs the reference-fix A/B (apply the answer-key description edit, re-measure, revert — reuse `apply_edit`/`run_sync_skills`/`git_reset_sync_paths`), classifies the tier, and `_write_activation_tiers` writes `tier`/`rotation` back into `evals/activation/dataset.json` (mirror `_write_tiers`). Add `--activation` flag to `main`.

- [ ] **Step 4: Run — PASS. Step 5: Commit**
```bash
git add evals/calibrate.py evals/tests/test_calibrate.py
git commit -m "feat(activation): calibrate activation fixtures (tiers + reference-fix A/B)"
```

---

## Task 11: Author the full activation fixture set + calibrate

**Files:** Create `evals/activation/<id>/` dirs (≥10 total) + `reference_fix.json` answer keys; run calibration.

- [ ] **Step 1: Author ≥10 balanced fixtures, both skills, ≥2 held-out**

Cover, at minimum (fire = should invoke; no-fire = must stay silent):
- `improve` fire: just-saw-footgun (force-push, secret committed, destructive rm).
- `improve` no-fire: ordinary coding help, a question about unrelated docs.
- `improve-init` fire: "set up guardrails for this project" / first-run intent.
- `improve-init` no-fire: "explain this codebase" (read-only, no guardrail intent).
Mark ≥2 as `"holdout": true` (one fire, one no-fire). Each `fire`/`headroom`-candidate fixture gets a `reference_fix.json` — a known-good description clause edit (the EditProposal shape: file/operation/anchor/anchor_position/new_content) that should close it.

Each scenario.md follows the be-specific + XML disciplines (`prompt-engineering.md §3–§4`): concrete, realistic, one situation.

- [ ] **Step 2: Calibrate (live; cost-gated)**

Run: `python3 -m evals.calibrate --activation --n 5 --skill-runner opus --judge opus --effort max --write`
Expected: `evals/activation/dataset.json` entries gain `tier`/`rotation`. Confirm ≥2 fixtures land in `headroom` (loop fuel) and the no-fire fixtures in `restraint`.

- [ ] **Step 3: Commit**
```bash
git add evals/activation/
git commit -m "feat(activation): full calibrated fixture set (>=10, both skills, >=2 holdout)"
```

> **This step spends money (live calibration). Pause for controller/user go-ahead before running Step 2**, per the project's cost discipline.

---

## Task 12: Release prep (DEFERRED until a validation run passes)

**Do not bump the version until a dual-axis `auto_loop` run demonstrates the exit criteria** (one kept description edit + one kept procedure edit; FP rate < 10%). That validation run is the v0.6.0 payoff and is its own gated step (like v0.5.2 → v0.6.0).

- [ ] CHANGELOG.md: add `[0.6.0]` entry summarizing the activation axis.
- [ ] docs/ROADMAP.md: move v0.6.0 Activation Frontier from Planned → Done; update "Last updated".
- [ ] plugin/.claude-plugin/plugin.json: `0.5.2` → `0.6.0`.
- [ ] Tag `v0.6.0`; merge `activation-frontier` → main.

---

## Self-Review (writing-plans checklist)

**1. Spec coverage:** spec §3 clean separation → Task 8 (per-axis gate) + the no-cross-suite design; §5 fixtures → Tasks 1, 11; §6 measurement → Tasks 0, 3; §7 metrics → Tasks 2, 4; §8 loop integration → Tasks 4–9; §9 calibration → Task 10; §13 spike → Task 0; §14 exit criteria → Task 12 + the validation run. No gaps.

**2. Placeholder scan:** the only deliberate placeholder is `<<SKILL_KEY>>` in Task 3 — explicitly resolved by Task 0's recorded `tool_input` shape (and `detect_firing` already tolerates `skill`/`name`). No "TODO/handle edge cases/similar to" placeholders.

**3. Type consistency:** ratchet operates on plain dicts (verified); `ACTIVATION_METRICS`/`ACTIVATION_EPSILON` (Task 4) used consistently in Tasks 8. `grade_activation` adds `correct_rate` to entries (Task 2) → consumed by `pick_dual_axis_target` (Task 7) and `_activation_failure` (Task 8). `EditProposal` fields (file/operation/anchor/anchor_position/new_content/hypothesis/confidence) consistent across Tasks 5, 8. `apply_edit` allowlist (Task 6) matches `edit_proposer.ALLOWED_FILES` (Task 5). `run_activation_eval(skill_model, effort, holdout)` signature consistent across Tasks 6, 8, 9, 10.
