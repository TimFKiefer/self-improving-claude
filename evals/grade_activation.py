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
