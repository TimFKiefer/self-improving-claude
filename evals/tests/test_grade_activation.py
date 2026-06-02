from evals.grade_activation import grade_activation

def _r(id, label, rate):
    return {"id": id, "skill": "improve", "label": label, "firing_rate": rate}

def test_perfect_suite_scores_ten_zero_fp():
    s = grade_activation([_r("a01", "fire", 1.0), _r("a02", "no-fire", 0.0)])
    assert s["activation_score"] == 10.0
    assert s["false_positive_rate"] == 0.0

def test_no_fire_overfiring_drives_score_down_and_fp_up():
    s = grade_activation([_r("a01", "fire", 1.0), _r("a02", "no-fire", 1.0)])
    assert s["activation_score"] == 5.0
    assert s["false_positive_rate"] == 1.0

def test_empty_suite_is_none():
    s = grade_activation([])
    assert s["activation_score"] is None
    assert s["false_positive_rate"] is None

def test_entries_carry_correct_rate():
    s = grade_activation([_r("a01", "fire", 0.6)])
    assert s["entries"][0]["correct_rate"] == 0.6
