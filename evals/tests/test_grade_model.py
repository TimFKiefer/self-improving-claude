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
    """If the model returns garbage, we get score 0 + an error note rather than a crash."""
    captured: list = []
    response = "not json at all"
    client = FakeAnthropicClient(response, captured)
    result = grade_model(proposal={}, planted_problem="x", client=client)
    assert result["score"] == 0
    assert "parse_error" in result
    assert isinstance(result["parse_error"], str)


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
