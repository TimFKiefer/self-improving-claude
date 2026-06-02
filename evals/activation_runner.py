from __future__ import annotations
import json, os, subprocess, tempfile
from pathlib import Path

from evals.activation_lib import ActivationFixture, load_activation_fixture, load_activation_dataset
from evals.client_claude_cli import _to_cli_model
from evals.grade_activation import grade_activation

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_PATH = REPO_ROOT / "plugin"
SKILL_HOOK = REPO_ROOT / "evals" / "activation" / "skill_hook.py"

def detect_firing(marker_path: str) -> list[str]:
    """Return the skills invoked during the run (raw, plugin-namespaced), in order.
    Empty if the marker is absent. The hook appends one JSON line per Skill call."""
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
    plugin-namespaced form 'self-improving-claude:improve'."""
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

def _run_once(*, scenario: str, model: str, effort: str | None) -> list[str]:
    """One sandbox run; returns the skills invoked. Short-circuited by the Skill hook
    (exit 2), so the orchestrator never runs."""
    tmp = tempfile.mkdtemp(prefix="sic-act-")
    try:
        claude_dir = Path(tmp) / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        (claude_dir / "settings.json").write_text(
            json.dumps(_settings_with_skill_hook()), encoding="utf-8")
        marker = Path(tmp) / "marker.jsonl"
        env = {**os.environ, "SPIKE_MARKER": str(marker)}
        subprocess.run(_build_argv(model=model, scenario=scenario, effort=effort),
                       cwd=tmp, capture_output=True, text=True, timeout=300, env=env)
        return detect_firing(str(marker))
    finally:
        import shutil; shutil.rmtree(tmp, ignore_errors=True)

def firing_rate_for_fixture(fx: ActivationFixture, *, n: int, model: str,
                            effort: str | None) -> float:
    """N-sample the invocation decision: fraction of runs that invoked THIS fixture's
    target skill."""
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
