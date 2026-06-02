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

def test_run_once_survives_timeout(monkeypatch):
    import subprocess as sp
    def boom(*a, **k):
        raise sp.TimeoutExpired(cmd="claude", timeout=1)
    monkeypatch.setattr(ar.subprocess, "run", boom)
    # a timed-out decision must NOT crash — it counts as no fire (empty marker)
    assert ar._run_once(scenario="x", model="haiku", effort=None) == []
