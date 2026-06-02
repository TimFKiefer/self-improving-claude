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
