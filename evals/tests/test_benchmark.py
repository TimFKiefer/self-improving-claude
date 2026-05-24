"""Unit tests for evals/benchmark.py — capability benchmark stats + orchestration."""
from evals.benchmark import mean_stderr, aggregate_cell, build_leaderboard, within_noise


def test_mean_stderr_basic():
    mean, std, stderr = mean_stderr([10.0, 4.0, 8.0, 6.0])
    assert mean == 7.0
    assert round(stderr, 4) == round(std / 2, 4)        # n=4 -> sqrt(n)=2


def test_mean_stderr_empty_and_singleton():
    assert mean_stderr([]) == (0.0, 0.0, 0.0)
    assert mean_stderr([5.0]) == (5.0, 0.0, 0.0)        # std undefined for n=1 -> 0


def test_aggregate_cell_reports_valid_rate_and_mean():
    cell = aggregate_cell([8.0, 0.0, 7.0, 9.0], n_valid=3, n=4)
    assert cell["mean"] == 6.0
    assert cell["valid_rate"] == 0.75
    assert cell["n"] == 4
    assert cell["per_sample_quality"] == [8.0, 0.0, 7.0, 9.0]


def test_build_leaderboard_sorts_desc_and_averages_fixtures():
    cells = [
        {"model": "A", "mean": 9.0, "stderr": 0.1, "valid_rate": 1.0},
        {"model": "A", "mean": 7.0, "stderr": 0.1, "valid_rate": 1.0},
        {"model": "B", "mean": 5.0, "stderr": 0.1, "valid_rate": 1.0},
    ]
    lb = build_leaderboard(cells)
    assert [r["model"] for r in lb] == ["A", "B"]
    assert lb[0]["mean_quality"] == 8.0
    assert lb[0]["fixtures_scored"] == 2


def test_within_noise_flags_overlap():
    a = {"mean_quality": 8.0, "stderr": 0.5}
    b = {"mean_quality": 8.3, "stderr": 0.5}
    c = {"mean_quality": 8.0, "stderr": 0.05}
    d = {"mean_quality": 9.5, "stderr": 0.05}
    assert within_noise(a, b) is True
    assert within_noise(c, d) is False
