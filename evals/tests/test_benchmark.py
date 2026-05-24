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


import json
from types import SimpleNamespace

from evals.benchmark import run_cell


def _proposer_returning_one_env_rule():
    body = ('{"proposals":[{"form":"permissions.deny","rule":"Read(**/.env*)",'
            '"rationale":"block .env reads"}]}')
    class _P:
        def __init__(self):
            self.models = []
            self.messages = SimpleNamespace(create=self._c)
        def _c(self, *, model, **k):
            self.models.append(model)
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=body)])
    return _P()


def _batched_judge_scoring_all_8():
    """Returns score 8 for however many proposals the prompt contains."""
    class _J:
        def __init__(self):
            self.models = []
            self.messages = SimpleNamespace(create=self._c)
        def _c(self, *, model, messages, **k):
            self.models.append(model)
            count = messages[0]["content"].count('<proposal index=')
            arr = json.dumps([{"index": i, "reasoning": "ok", "score": 8} for i in range(count)])
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=arr)])
    return _J()


_ENTRY = {"id": "002-block-env-reads", "trigger": "improve-init",
          "user_args": "", "planted_problem": "block .env reads"}


def test_run_cell_samples_n_times_and_batches_one_judge_call():
    prop = _proposer_returning_one_env_rule()
    judge = _batched_judge_scoring_all_8()
    cell = run_cell(entry=_ENTRY, proposer_client=prop, proposer_model="opus",
                    judge_client=judge, judge_model="claude-sonnet-4-5", samples=4)
    assert prop.models == ["opus"] * 4          # N=4 proposer calls
    assert judge.models == ["claude-sonnet-4-5"]  # exactly ONE batched judge call
    assert cell["mean"] == 8.0                   # each sample's best == 8
    assert cell["valid_rate"] == 1.0


def test_run_cell_empty_proposals_score_zero_and_lower_valid_rate():
    class _Empty:
        def __init__(self):
            self.messages = SimpleNamespace(create=lambda **k:
                SimpleNamespace(content=[SimpleNamespace(type="text", text="not json")]))
    judge = _batched_judge_scoring_all_8()
    cell = run_cell(entry=_ENTRY, proposer_client=_Empty(), proposer_model="m",
                    judge_client=judge, judge_model="j", samples=3)
    assert cell["mean"] == 0.0
    assert cell["valid_rate"] == 0.0
    assert judge.models == []                    # no proposals -> no judge call


def test_run_cell_independent_judges_each_proposal():
    prop = _proposer_returning_one_env_rule()
    calls = []
    class _J1:
        def __init__(self):
            self.messages = SimpleNamespace(create=self._c)
        def _c(self, *, model, **k):
            calls.append(model)
            return SimpleNamespace(content=[SimpleNamespace(type="text",
                text='{"score":6,"strengths":[],"weaknesses":[],"reasoning":"x"}')])
    cell = run_cell(entry=_ENTRY, proposer_client=prop, proposer_model="m",
                    judge_client=_J1(), judge_model="claude-sonnet-4-5", samples=2,
                    independent=True)
    assert len(calls) == 2                       # one judge call per proposal (2 samples x 1 prop)
    assert cell["mean"] == 6.0
