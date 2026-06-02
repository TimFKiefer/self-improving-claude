"""Tests for evals/auto_loop.py.

α scope: apply_edit (anchor-based slow-state writer). Driver/CLI/pick_target
tests come with Task 5 wiring.
"""
import pytest

from evals.auto_loop import apply_edit, SLOW_STATE_ALLOWLIST


def _make_target(tmp_path, rel, content):
    """Create a fake repo layout under tmp_path with the given file."""
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def test_apply_edit_rejects_file_outside_allowlist(tmp_path):
    ok, reason = apply_edit({
        "file": "evals/run.py",  # NOT in allowlist
        "operation": "add",
        "anchor": "import x",
        "anchor_position": "before",
        "new_content": "x",
    }, repo_root=tmp_path)
    assert ok is False
    assert "allowlist" in reason


def test_apply_edit_rejects_invalid_operation(tmp_path):
    rel = "plugin/skills/_shared/orchestrator-procedure.md"
    _make_target(tmp_path, rel, "Step 7\nbody\n")
    ok, reason = apply_edit({
        "file": rel, "operation": "wibble", "anchor": "Step 7",
        "anchor_position": "before", "new_content": "x",
    }, repo_root=tmp_path)
    assert ok is False
    assert "invalid operation" in reason


def test_apply_edit_rejects_anchor_not_found(tmp_path):
    rel = "plugin/skills/_shared/orchestrator-procedure.md"
    _make_target(tmp_path, rel, "Step 7\nbody\n")
    ok, reason = apply_edit({
        "file": rel, "operation": "replace", "anchor": "Step 999",
        "anchor_position": "before", "new_content": "x",
    }, repo_root=tmp_path)
    assert ok is False
    assert "0 times" in reason


def test_apply_edit_rejects_anchor_collision(tmp_path):
    rel = "plugin/skills/_shared/orchestrator-procedure.md"
    _make_target(tmp_path, rel, "Step 7\nbody\nStep 7\n")  # 2 occurrences
    ok, reason = apply_edit({
        "file": rel, "operation": "replace", "anchor": "Step 7",
        "anchor_position": "before", "new_content": "x",
    }, repo_root=tmp_path)
    assert ok is False
    assert "2 times" in reason


def test_apply_edit_rejects_oversized_new_content(tmp_path):
    rel = "plugin/skills/_shared/orchestrator-procedure.md"
    _make_target(tmp_path, rel, "Step 7\n")
    big = "\n".join(f"line {i}" for i in range(20))  # 20 lines >> 8
    ok, reason = apply_edit({
        "file": rel, "operation": "add", "anchor": "Step 7",
        "anchor_position": "after", "new_content": big,
    }, repo_root=tmp_path)
    assert ok is False
    assert "exceeds" in reason


def test_apply_edit_add_before(tmp_path):
    rel = "plugin/skills/_shared/orchestrator-procedure.md"
    target = _make_target(tmp_path, rel, "Step 7\nbody\n")
    ok, _ = apply_edit({
        "file": rel, "operation": "add", "anchor": "Step 7",
        "anchor_position": "before", "new_content": "PRE\n",
    }, repo_root=tmp_path)
    assert ok is True
    assert target.read_text(encoding="utf-8") == "PRE\nStep 7\nbody\n"


def test_apply_edit_add_after(tmp_path):
    rel = "plugin/skills/_shared/orchestrator-procedure.md"
    target = _make_target(tmp_path, rel, "Step 7\nbody\n")
    ok, _ = apply_edit({
        "file": rel, "operation": "add", "anchor": "Step 7",
        "anchor_position": "after", "new_content": " POST",
    }, repo_root=tmp_path)
    assert ok is True
    assert target.read_text(encoding="utf-8") == "Step 7 POST\nbody\n"


def test_apply_edit_replace(tmp_path):
    rel = "plugin/skills/_shared/orchestrator-procedure.md"
    target = _make_target(tmp_path, rel, "Step 7\nbody\n")
    ok, _ = apply_edit({
        "file": rel, "operation": "replace", "anchor": "Step 7",
        "anchor_position": "before", "new_content": "Step 7 (revised)",
    }, repo_root=tmp_path)
    assert ok is True
    assert target.read_text(encoding="utf-8") == "Step 7 (revised)\nbody\n"


def test_apply_edit_delete(tmp_path):
    rel = "plugin/skills/_shared/orchestrator-procedure.md"
    target = _make_target(tmp_path, rel, "Step 7\nbody\n")
    ok, _ = apply_edit({
        "file": rel, "operation": "delete", "anchor": "Step 7\n",
        "anchor_position": "before", "new_content": "",
    }, repo_root=tmp_path)
    assert ok is True
    assert target.read_text(encoding="utf-8") == "body\n"


def test_apply_edit_preserves_file_on_rejection(tmp_path):
    rel = "plugin/skills/_shared/orchestrator-procedure.md"
    original = "Step 7\nbody\n"
    target = _make_target(tmp_path, rel, original)
    apply_edit({
        "file": rel, "operation": "replace", "anchor": "MISSING",
        "anchor_position": "before", "new_content": "x",
    }, repo_root=tmp_path)
    assert target.read_text(encoding="utf-8") == original


def test_allowlist_contains_expected_paths():
    assert "plugin/skills/_shared/orchestrator-procedure.md" in SLOW_STATE_ALLOWLIST
    assert "plugin/skills/_shared/references/prompt-rubric.md" in SLOW_STATE_ALLOWLIST
    assert "plugin/skills/_shared/references/examples.md" in SLOW_STATE_ALLOWLIST
    # hook-patterns / tools-reference / settings-merge should NOT be editable
    assert "plugin/skills/_shared/references/hook-patterns.md" not in SLOW_STATE_ALLOWLIST


# ----- driver helper tests --------------------------------------------------

from evals.auto_loop import pick_target


def test_pick_target_returns_specified_fixture():
    visible_baseline = {"entries": [
        {"id": "a", "code_max": 9.0, "install_rate": 1.0},
        {"id": "b", "code_max": 3.0, "install_rate": 0.0},
    ]}
    assert pick_target(visible_baseline, "a") == "a"
    assert pick_target(visible_baseline, "b") == "b"


def test_pick_target_picks_lowest_composite_when_unspecified():
    visible_baseline = {"entries": [
        {"id": "high", "code_max": 9.0, "install_rate": 1.0},   # composite 19
        {"id": "low",  "code_max": 3.0, "install_rate": 0.0},   # composite 3
        {"id": "mid",  "code_max": 7.0, "install_rate": 0.5},   # composite 12
    ]}
    assert pick_target(visible_baseline, None) == "low"


def test_pick_target_raises_on_empty_baseline():
    with pytest.raises(ValueError, match="no eligible"):
        pick_target({"entries": []}, None)


def test_pick_target_tolerates_none_install_rate():
    """install_rate can be None when no proposals install; pick_target shouldn't crash."""
    visible_baseline = {"entries": [
        {"id": "a", "code_max": 9.0, "install_rate": None},     # composite 9
        {"id": "b", "code_max": 3.0, "install_rate": None},     # composite 3
    ]}
    assert pick_target(visible_baseline, None) == "b"


# ----- β: pick_target rotation tests ---------------------------------------

def test_pick_target_rotation_avoids_recent_picks():
    visible_baseline = {"entries": [
        {"id": "low",  "code_max": 3.0, "install_rate": 0.0},   # composite 3 (bottom 1)
        {"id": "mid",  "code_max": 5.0, "install_rate": 0.5},   # composite 10 (bottom 2)
        {"id": "high", "code_max": 7.0, "install_rate": 0.5},   # composite 12 (bottom 3)
        {"id": "top",  "code_max": 9.0, "install_rate": 1.0},   # composite 19 (outside bottom-3)
    ]}
    # Without recent_picks, picks the lowest
    assert pick_target(visible_baseline, None, recent_picks=[]) == "low"
    # With "low" recently picked, picks the next
    assert pick_target(visible_baseline, None, recent_picks=["low"]) == "mid"
    # With "low" and "mid" recently picked, picks the third in bottom-3
    assert pick_target(visible_baseline, None, recent_picks=["low", "mid"]) == "high"


def test_pick_target_rotation_falls_back_when_all_bottom_picked():
    visible_baseline = {"entries": [
        {"id": "a", "code_max": 3.0, "install_rate": 0.0},
        {"id": "b", "code_max": 5.0, "install_rate": 0.5},
        {"id": "c", "code_max": 7.0, "install_rate": 0.5},
        {"id": "d", "code_max": 9.0, "install_rate": 1.0},
    ]}
    # All bottom-3 (a, b, c) picked in the last 2 → only look at last 2
    # recent_picks[-2:] = ["b", "c"] — so "a" is fresh
    assert pick_target(visible_baseline, None, recent_picks=["a", "b", "c"]) == "a"


def test_pick_target_rotation_respects_bottom_n_parameter():
    visible_baseline = {"entries": [
        {"id": f"f{i}", "code_max": float(i), "install_rate": 0.0} for i in range(5)
    ]}
    # Default bottom_n=3 → bottom 3 are f0, f1, f2
    assert pick_target(visible_baseline, None, recent_picks=[]) == "f0"
    # bottom_n=2 → only f0 and f1 in pool
    assert pick_target(visible_baseline, None, recent_picks=["f0"], rotate_bottom_n=2) == "f1"


def test_pick_target_target_fixture_overrides_rotation():
    """β: explicit --target-fixture preserves α behavior."""
    visible_baseline = {"entries": [
        {"id": "low",  "code_max": 3.0, "install_rate": 0.0},
        {"id": "high", "code_max": 9.0, "install_rate": 1.0},
    ]}
    assert pick_target(visible_baseline, "high", recent_picks=["high"]) == "high"


# ----- β: is_saturated tests -----------------------------------------------

from evals.auto_loop import is_saturated


def test_is_saturated_true_when_all_metrics_max():
    assert is_saturated({"average_code": 10.0, "install_rate": 1.0,
                         "fire_rate": None, "average_restraint": None}) is True


def test_is_saturated_false_when_code_below_max():
    assert is_saturated({"average_code": 8.5, "install_rate": 1.0,
                         "fire_rate": None, "average_restraint": None}) is False


def test_is_saturated_false_when_install_below_max():
    assert is_saturated({"average_code": 10.0, "install_rate": 0.9,
                         "fire_rate": None, "average_restraint": None}) is False


def test_is_saturated_true_for_restraint_only_fixture():
    """A restraint fixture has None code/install but maxed restraint."""
    assert is_saturated({"average_code": None, "install_rate": None,
                         "fire_rate": None, "average_restraint": 10.0}) is True


def test_is_saturated_tolerates_floating_point_near_max():
    assert is_saturated({"average_code": 10.0 - 1e-9, "install_rate": 1.0,
                         "fire_rate": None, "average_restraint": None}) is True


def test_is_saturated_false_when_restraint_below_max_and_others_unset():
    assert is_saturated({"average_code": None, "install_rate": None,
                         "fire_rate": None, "average_restraint": 5.0}) is False


# ----- v0.5.0 RC: cost estimation tests -----------------------------------

from evals.auto_loop import (
    _estimate_eval_cost_usd, _estimate_proposer_cost_usd,
    _estimate_iteration_cost_usd, _estimate_initial_baselines_cost_usd,
)


def test_eval_cost_positive_and_scales_linearly():
    one = _estimate_eval_cost_usd("haiku", "opus", n_fixtures=1)
    nine = _estimate_eval_cost_usd("haiku", "opus", n_fixtures=9)
    assert one > 0
    assert abs(nine - 9 * one) < 1e-9


def test_eval_cost_orders_haiku_lt_sonnet_lt_opus():
    h = _estimate_eval_cost_usd("haiku", "haiku", n_fixtures=1)
    s = _estimate_eval_cost_usd("claude-sonnet-4-5", "haiku", n_fixtures=1)
    o = _estimate_eval_cost_usd("opus", "haiku", n_fixtures=1)
    assert h < s < o


def test_eval_cost_unknown_model_uses_default():
    """Unknown model falls back to DEFAULT_PRICING (sonnet-ish). Must not raise."""
    out = _estimate_eval_cost_usd("future-model-9000", "haiku", n_fixtures=1)
    assert out > 0


def test_proposer_cost_positive_orders_correctly():
    h = _estimate_proposer_cost_usd("haiku")
    s = _estimate_proposer_cost_usd("claude-sonnet-4-5")
    o = _estimate_proposer_cost_usd("opus")
    assert 0 < h < s < o


def test_iteration_cost_with_holdout_is_proposer_plus_4_fixtures():
    """Per spec: proposer + visible single-fixture + held-out 3-fixture = 4 fixture evals."""
    p = _estimate_proposer_cost_usd("claude-sonnet-4-5")
    four_evals = _estimate_eval_cost_usd("haiku", "opus", n_fixtures=4)
    expected = p + four_evals
    actual = _estimate_iteration_cost_usd(
        skill_model="haiku", judge_model="opus",
        proposer_model="claude-sonnet-4-5", holdout_gate_on=True,
    )
    assert abs(actual - expected) < 1e-9


def test_iteration_cost_without_holdout_is_proposer_plus_1_fixture():
    """No held-out gate → no held-out eval."""
    p = _estimate_proposer_cost_usd("claude-sonnet-4-5")
    one_eval = _estimate_eval_cost_usd("haiku", "opus", n_fixtures=1)
    actual = _estimate_iteration_cost_usd(
        skill_model="haiku", judge_model="opus",
        proposer_model="claude-sonnet-4-5", holdout_gate_on=False,
    )
    assert abs(actual - (p + one_eval)) < 1e-9


def test_initial_baseline_cost_rotation_with_gate_is_12_fixtures():
    expected = _estimate_eval_cost_usd("haiku", "opus", n_fixtures=12)
    actual = _estimate_initial_baselines_cost_usd(
        skill_model="haiku", judge_model="opus",
        rotation_mode=True, holdout_gate_on=True,
    )
    assert abs(actual - expected) < 1e-9


def test_initial_baseline_cost_rotation_without_gate_is_9_fixtures():
    expected = _estimate_eval_cost_usd("haiku", "opus", n_fixtures=9)
    actual = _estimate_initial_baselines_cost_usd(
        skill_model="haiku", judge_model="opus",
        rotation_mode=True, holdout_gate_on=False,
    )
    assert abs(actual - expected) < 1e-9


def test_initial_baseline_cost_fixed_mode_with_gate_is_3_fixtures():
    """α-compat mode skips visible-9, only runs held-out-3."""
    expected = _estimate_eval_cost_usd("haiku", "opus", n_fixtures=3)
    actual = _estimate_initial_baselines_cost_usd(
        skill_model="haiku", judge_model="opus",
        rotation_mode=False, holdout_gate_on=True,
    )
    assert abs(actual - expected) < 1e-9


def test_initial_baseline_cost_fixed_mode_without_gate_is_zero():
    """No visible baseline (fixed mode), no held-out → no upfront cost."""
    actual = _estimate_initial_baselines_cost_usd(
        skill_model="haiku", judge_model="opus",
        rotation_mode=False, holdout_gate_on=False,
    )
    assert actual == 0.0


# v0.5.0 RC: cap enforcement integration tests (mock eval + proposer)
class _FakeProposer:
    def __init__(self):
        self.messages = type("M", (), {"create": self._create})()
    def _create(self, **k):
        import json
        from types import SimpleNamespace
        # Return a low-confidence proposal so apply_edit isn't called (cheap unit test)
        body = json.dumps({
            "file": "plugin/skills/_shared/orchestrator-procedure.md",
            "operation": "add", "anchor": "## Step 4",
            "anchor_position": "after", "new_content": "x",
            "hypothesis": "stub", "confidence": 2,
        })
        return SimpleNamespace(content=[SimpleNamespace(text=body)])


def test_main_aborts_when_initial_baselines_exceed_max_usd(monkeypatch, tmp_path):
    """Pre-flight: if --max-usd can't even cover initial baselines, refuse to start."""
    import evals.auto_loop as al
    monkeypatch.setattr(al, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(al, "_check_clean_tree", lambda: None)
    # rotation mode + holdout gate = 12-fixture initial baseline; set max-usd absurdly low
    rc = al.main(["--max-iterations", "5", "--max-usd", "0.01",
                  "--skill-runner", "opus", "--judge", "opus"])
    assert rc == 2  # refused


def _setup_main_mocks(monkeypatch, tmp_path):
    """Common scaffold for cap-enforcement tests: stub all heavy I/O on al + on
    run_iteration's collaborators so the loop body never makes real calls."""
    import evals.auto_loop as al
    import evals.fixtures_lib as fl
    monkeypatch.setattr(al, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(al, "_check_clean_tree", lambda: None)
    # Provide a headroom-tier fixture so the eligible_ids guard doesn't abort.
    headroom_dataset = [{"id": "fx-1", "code_max": 5, "install_rate": 0.5,
                         "tier": "headroom", "rotation": True}]
    monkeypatch.setattr(fl, "load_dataset", lambda: headroom_dataset)
    visible_stub = {"entries": [{"id": "fx-1", "code_max": 5, "install_rate": 0.5}],
                    "average_code": 5.0, "install_rate": 0.5,
                    "fire_rate": None, "average_restraint": None}
    monkeypatch.setattr(al, "run_visible_eval", lambda *a, **k: (visible_stub, []))
    monkeypatch.setattr(al, "run_holdout_eval", lambda *a, **k:
                        ({"average_code": 5.0, "install_rate": 1.0,
                          "fire_rate": None, "average_restraint": None,
                          "entries": [], "restraint_entries": []}, []))
    monkeypatch.setattr(al, "_run_eval_and_extract_result", lambda *a, **k:
                        (visible_stub, {"proposals": []}))
    monkeypatch.setattr(al, "_read_slow_state", lambda: ("procedure", "rubric"))
    # Mock run_iteration entirely so we don't depend on dataset lookups
    def _stub_iter(*, i, target_id, baseline, last_result, holdout_baseline, audit, **kw):
        audit.write_iteration({
            "i": i, "ts": "0", "fixture": target_id,
            "edit": {}, "hypothesis": "", "confidence": 0,
            "scores_before": dict(baseline), "scores_after": None,
            "scores_holdout_before": dict(holdout_baseline) if holdout_baseline else None,
            "scores_holdout_after": None,
            "decision": "rejected: stub", "commit_sha": None,
        })
        return baseline, last_result, holdout_baseline
    monkeypatch.setattr(al, "run_iteration", _stub_iter)
    monkeypatch.setattr(al, "pick_target", lambda *a, **k: "fx-1")
    from evals.client_claude_cli import ClaudeCliClient
    monkeypatch.setattr(ClaudeCliClient, "__init__", lambda self, **k: None)
    return al


def test_main_aborts_mid_loop_when_max_usd_hit(monkeypatch, tmp_path):
    """During the loop: usd_spent + lookahead > max_usd should break before next iter."""
    al = _setup_main_mocks(monkeypatch, tmp_path)
    rc = al.main(["--max-iterations", "100",
                  "--max-usd", "3.5",  # ~$2.16 baselines + ~$0.76/iter = ~2 iter
                  "--skill-runner", "haiku", "--judge", "opus",
                  "--proposer", "claude-sonnet-4-5"])
    assert rc == 0
    runs = list((tmp_path / "prompt-lab" / "auto-runs").iterdir())
    assert len(runs) == 1
    iters = (runs[0] / "iterations.jsonl").read_text(encoding="utf-8").splitlines()
    n = len([l for l in iters if l.strip()])
    assert 0 < n < 10, f"expected cap to abort early, got {n} iterations"


def test_main_aborts_mid_loop_when_max_hours_hit(monkeypatch, tmp_path):
    """The --max-hours cap fires when elapsed time exceeds the limit."""
    al = _setup_main_mocks(monkeypatch, tmp_path)
    # First call (state init) returns 0; later calls advance past --max-hours
    counter = [0]
    def fake_monotonic():
        counter[0] += 1
        # First call: 0 (start); next: 0 (summary call check); then advance fast
        return 0.0 if counter[0] <= 1 else counter[0] * 1000.0
    monkeypatch.setattr(al.time, "monotonic", fake_monotonic)
    rc = al.main(["--max-iterations", "100", "--max-hours", "0.2",
                  "--skill-runner", "haiku", "--judge", "opus",
                  "--proposer", "claude-sonnet-4-5"])
    assert rc == 0
    runs = list((tmp_path / "prompt-lab" / "auto-runs").iterdir())
    iters = (runs[0] / "iterations.jsonl").read_text(encoding="utf-8").splitlines()
    n = len([l for l in iters if l.strip()])
    assert n < 100, f"expected --max-hours to abort early, got {n}"


def test_main_returns_2_when_no_headroom_fixtures(monkeypatch, tmp_path):
    """Rotation mode with an uncalibrated/empty headroom set must refuse to start."""
    al = _setup_main_mocks(monkeypatch, tmp_path)
    import evals.fixtures_lib as fl
    monkeypatch.setattr(fl, "load_dataset", lambda: [])  # no headroom-tier fixtures
    rc = al.main(["--skill-runner", "haiku", "--judge", "opus",
                  "--proposer", "claude-sonnet-4-5"])
    assert rc == 2


# ----- v0.5.1: --confirm-reruns flag tests ---------------------------------

def test_confirm_reruns_flag_defaults_to_two():
    import argparse
    from evals.auto_loop import main
    captured = {}
    orig = argparse.ArgumentParser.parse_args

    def spy(self, argv=None):
        ns = orig(self, argv)
        captured["ns"] = ns
        raise SystemExit(0)  # stop before the loop runs

    argparse.ArgumentParser.parse_args = spy
    try:
        with pytest.raises(SystemExit):
            main([])
    finally:
        argparse.ArgumentParser.parse_args = orig
    assert captured["ns"].confirm_reruns == 2


def test_confirm_reruns_flag_override():
    import argparse
    from evals.auto_loop import main
    captured = {}
    orig = argparse.ArgumentParser.parse_args

    def spy(self, argv=None):
        ns = orig(self, argv)
        captured["ns"] = ns
        raise SystemExit(0)

    argparse.ArgumentParser.parse_args = spy
    try:
        with pytest.raises(SystemExit):
            main(["--confirm-reruns", "0"])
    finally:
        argparse.ArgumentParser.parse_args = orig
    assert captured["ns"].confirm_reruns == 0


# ----- v0.5.1: _estimate_confirmation_cost_usd tests ----------------------

def test_confirmation_cost_zero_when_no_reruns():
    from evals.auto_loop import _estimate_confirmation_cost_usd
    assert _estimate_confirmation_cost_usd("opus", "opus", 0) == 0.0

def test_confirmation_cost_is_four_fixture_evals_per_rerun():
    from evals.auto_loop import _estimate_confirmation_cost_usd, _estimate_eval_cost_usd
    # 2 reruns × (1 target + 3 holdout) = 8 fixture-evals
    expected = _estimate_eval_cost_usd("opus", "opus", n_fixtures=8)
    assert abs(_estimate_confirmation_cost_usd("opus", "opus", 2) - expected) < 1e-9

def test_confirmation_cost_scales_linearly_with_reruns():
    from evals.auto_loop import _estimate_confirmation_cost_usd
    one = _estimate_confirmation_cost_usd("haiku", "opus", 1)
    three = _estimate_confirmation_cost_usd("haiku", "opus", 3)
    assert abs(three - 3 * one) < 1e-9


# ----- eval-suite-headroom: eligible_ids filtering -------------------------

def test_pick_target_filters_to_eligible_ids():
    visible_baseline = {"entries": [
        {"id": "low",  "code_max": 3.0, "install_rate": 0.0},   # lowest, but not eligible
        {"id": "mid",  "code_max": 5.0, "install_rate": 0.5},   # eligible
        {"id": "high", "code_max": 9.0, "install_rate": 1.0},
    ]}
    # 'low' is saturated/retired → excluded; 'mid' is the lowest ELIGIBLE
    assert pick_target(visible_baseline, None, eligible_ids={"mid", "high"}) == "mid"

def test_pick_target_eligible_none_means_all():
    visible_baseline = {"entries": [
        {"id": "low",  "code_max": 3.0, "install_rate": 0.0},
        {"id": "high", "code_max": 9.0, "install_rate": 1.0},
    ]}
    assert pick_target(visible_baseline, None, eligible_ids=None) == "low"

def test_pick_target_raises_when_no_eligible():
    visible_baseline = {"entries": [{"id": "a", "code_max": 3.0, "install_rate": 0.0}]}
    with pytest.raises(ValueError, match="no eligible"):
        pick_target(visible_baseline, None, eligible_ids=set())


# ----- Task 6: activation helpers ------------------------------------------

from evals.auto_loop import SLOW_STATE_ALLOWLIST as _ALLOW, is_activation_saturated


def test_preambles_in_allowlist():
    assert "plugin/skills/_shared/preambles/improve.md" in _ALLOW
    assert "plugin/skills/_shared/preambles/improve-init.md" in _ALLOW


def test_activation_saturated_at_ceiling():
    assert is_activation_saturated({"activation_score": 10.0})
    assert not is_activation_saturated({"activation_score": 8.0})
    assert is_activation_saturated({"activation_score": None})  # N/A counts as saturated
