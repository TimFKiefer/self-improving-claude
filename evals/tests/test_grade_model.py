"""Tests for evals/grade_model.py — model-based grader.

Mocks the Anthropic client so tests are deterministic and offline.
The real API integration is tested in evals/tests/test_run.py with
@pytest.mark.integration and a real key.

Run: python3 -m pytest evals/tests/test_grade_model.py -v
"""
import json
from types import SimpleNamespace

import pytest

from evals.grade_model import grade_model


class FakeAnthropicClient:
    """Mocks the anthropic.Anthropic client; returns canned responses."""

    def __init__(self, response_text: str, captured_calls: list):
        self.response_text = response_text
        self.captured_calls = captured_calls
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.captured_calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.response_text)])


def test_grade_model_parses_perfect_score():
    captured: list = []
    response = json.dumps({
        "strengths": ["targets the right bug", "specific matcher"],
        "weaknesses": [],
        "reasoning": "Hook correctly identifies pnpm test watcher and suggests test:ci.",
        "score": 10,
    })
    client = FakeAnthropicClient(response, captured)
    result = grade_model(
        proposal={"form": "command-hook", "rationale": "blocks watcher"},
        planted_problem="Claude keeps invoking pnpm test",
        client=client,
    )
    assert result["score"] == 10
    assert result["strengths"] == ["targets the right bug", "specific matcher"]
    assert result["weaknesses"] == []
    assert "reasoning" in result
    # The grader sent exactly one call to Anthropic
    assert len(captured) == 1
    # The model used should be a Haiku family
    assert "haiku" in captured[0]["model"].lower()


def test_grade_model_parses_low_score():
    captured: list = []
    response = json.dumps({
        "strengths": [],
        "weaknesses": ["wrong matcher", "no rationale"],
        "reasoning": "Proposal targets the wrong tool.",
        "score": 3,
    })
    client = FakeAnthropicClient(response, captured)
    result = grade_model(proposal={}, planted_problem="x", client=client)
    assert result["score"] == 3
    assert len(result["weaknesses"]) == 2


def test_grade_model_extracts_json_from_fenced_response():
    """Some models wrap JSON in ```json ... ``` even when asked not to."""
    captured: list = []
    response = """```json
{"strengths": ["a"], "weaknesses": [], "reasoning": "ok", "score": 7}
```"""
    client = FakeAnthropicClient(response, captured)
    result = grade_model(proposal={}, planted_problem="x", client=client)
    assert result["score"] == 7


def test_grade_model_handles_malformed_response_gracefully():
    """Garbage response -> valid:false + score:None (no misleading 0)."""
    captured: list = []
    response = "not json at all"
    client = FakeAnthropicClient(response, captured)
    result = grade_model(proposal={}, planted_problem="x", client=client)
    assert result["valid"] is False
    assert result["score"] is None
    assert "parse_error" in result["error"]


def test_grade_model_clamps_out_of_range_score():
    """Defensive: if model returns score=42 or score=-3, clamp to [0,10]."""
    captured: list = []
    for given, expected in [(42, 10), (-3, 0), (10, 10), (0, 0)]:
        response = json.dumps({"strengths": [], "weaknesses": [], "reasoning": "x", "score": given})
        client = FakeAnthropicClient(response, captured)
        result = grade_model(proposal={}, planted_problem="x", client=client)
        assert result["score"] == expected, f"score={given} should clamp to {expected}"


def test_grade_model_prompt_includes_planted_problem_and_proposal():
    captured: list = []
    response = json.dumps({"strengths": [], "weaknesses": [], "reasoning": "x", "score": 5})
    client = FakeAnthropicClient(response, captured)
    grade_model(
        proposal={"form": "command-hook", "matcher": "Bash"},
        planted_problem="Claude runs pnpm test",
        client=client,
    )
    sent_messages = captured[0]["messages"]
    combined = json.dumps(sent_messages)
    assert "Claude runs pnpm test" in combined
    assert "Bash" in combined


# --- v0.3.4: truncation prevention + valid/score-None schema ---

class _FakeClientV34:
    def __init__(self, text):
        self._text = text
        self.last_kwargs = None
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self._text)])


def test_grade_model_valid_score():
    c = _FakeClientV34('{"strengths":[],"weaknesses":[],"reasoning":"ok","score":8}')
    r = grade_model(proposal={"form": "x"}, planted_problem="p", client=c)
    assert r["valid"] is True
    assert r["score"] == 8
    assert r["error"] is None


def test_grade_model_truncation_is_invalid_not_zero():
    c = _FakeClientV34('{"strengths":["good"],"weaknesses":["')
    r = grade_model(proposal={"form": "x"}, planted_problem="p", client=c)
    assert r["valid"] is False
    assert r["score"] is None
    assert r["error"]


def test_grade_model_requests_higher_token_floor():
    c = _FakeClientV34('{"score":5}')
    grade_model(proposal={"form": "x"}, planted_problem="p", client=c)
    assert c.last_kwargs["max_tokens"] >= 2048


# --- capability benchmark: judge_model override + batched judge ---

from evals.grade_model import GRADER_MODEL


def test_grade_model_uses_judge_model_override():
    c = _FakeClientV34('{"strengths":[],"weaknesses":[],"reasoning":"x","score":7}')
    grade_model(proposal={"form": "x"}, planted_problem="p", client=c,
                judge_model="claude-sonnet-4-5")
    assert c.last_kwargs["model"] == "claude-sonnet-4-5"


def test_grade_model_defaults_to_grader_model():
    c = _FakeClientV34('{"strengths":[],"weaknesses":[],"reasoning":"x","score":7}')
    grade_model(proposal={"form": "x"}, planted_problem="p", client=c)
    assert c.last_kwargs["model"] == GRADER_MODEL


from types import SimpleNamespace as _NS
from evals.grade_model import grade_model_batch


def test_grade_model_batch_scores_in_order_and_routes_judge():
    c = _FakeClientV34('[{"index":0,"reasoning":"good","score":9},{"index":1,"reasoning":"bad","score":2}]')
    out = grade_model_batch(items=[{"a": 1}, {"a": 2}], planted_problem="p",
                            client=c, judge_model="claude-sonnet-4-5")
    assert [o["score"] for o in out] == [9, 2]
    assert all(o["valid"] for o in out)
    assert c.last_kwargs["model"] == "claude-sonnet-4-5"


def test_grade_model_batch_maps_by_index_not_position():
    c = _FakeClientV34('[{"index":1,"reasoning":"b","score":3},{"index":0,"reasoning":"a","score":8}]')
    out = grade_model_batch(items=[{"a": 0}, {"a": 1}], planted_problem="p", client=c, judge_model="x")
    assert out[0]["score"] == 8 and out[1]["score"] == 3


def test_grade_model_batch_missing_item_is_invalid_not_zero():
    c = _FakeClientV34('[{"index":0,"reasoning":"ok","score":7}]')   # index 1 omitted
    out = grade_model_batch(items=[{"a": 1}, {"a": 2}], planted_problem="p", client=c, judge_model="x")
    assert out[0]["score"] == 7
    assert out[1]["valid"] is False and out[1]["score"] is None


def test_grade_model_batch_unparseable_marks_all_invalid():
    c = _FakeClientV34("not json at all")
    out = grade_model_batch(items=[{"a": 1}, {"a": 2}], planted_problem="p", client=c, judge_model="x")
    assert all((not o["valid"] and o["score"] is None) for o in out)


def test_grade_model_batch_empty_makes_no_call():
    calls = []
    class _C:
        def __init__(self):
            self.messages = _NS(create=self._c)
        def _c(self, **k):
            calls.append(k)
            return _NS(content=[_NS(type="text", text="[]")])
    out = grade_model_batch(items=[], planted_problem="p", client=_C(), judge_model="x")
    assert out == [] and calls == []
