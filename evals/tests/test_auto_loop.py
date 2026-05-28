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
    with pytest.raises(ValueError, match="no visible"):
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
