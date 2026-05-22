"""Model-based grader: ask Haiku to score how well a proposal solves the planted problem.

The grader prompt (from docs/knowledge/eval-methodology.md §3) asks for
strengths + weaknesses + reasoning + score. Score is clamped to [0, 10].

The Anthropic client is injected so unit tests can mock it. The real
client is used by the eval runner (evals/run.py).
"""
from __future__ import annotations

import json
import re

GRADER_MODEL = "claude-haiku-4-5-20251001"

GRADER_SYSTEM = """You are an expert reviewer of Claude Code hook proposals. \
Evaluate proposals against the planted problem they're supposed to solve. \
Be concrete: name specific strengths and weaknesses. Avoid defaulting to a \
"6 out of 10" — score honestly, with low scores for proposals that don't \
solve the problem and high scores for proposals that do."""

GRADER_TEMPLATE = """<planted_problem>
{planted_problem}
</planted_problem>

<proposed_solution>
{proposal_json}
</proposed_solution>

Respond with a JSON object exactly matching this schema:

{{
  "strengths": [ "1-3 specific things the proposal does right" ],
  "weaknesses": [ "1-3 specific things it misses or does wrong" ],
  "reasoning": "2-3 sentences explaining the score",
  "score": <integer 0 to 10; 10 = exactly solves the planted problem>
}}

Output ONLY the JSON. No prose before or after."""


_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)


def _extract_json(text: str) -> str:
    """Strip ```json``` fences if present; otherwise return text unchanged."""
    m = _FENCE_RE.match(text.strip())
    return m.group(1) if m else text


def grade_model(*, proposal: dict, planted_problem: str, client) -> dict:
    """Grade one proposal. Returns {strengths, weaknesses, reasoning, score, ...}."""
    user_msg = GRADER_TEMPLATE.format(
        planted_problem=planted_problem,
        proposal_json=json.dumps(proposal, indent=2),
    )
    response = client.messages.create(
        model=GRADER_MODEL,
        max_tokens=1024,
        system=GRADER_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = response.content[0].text

    try:
        parsed = json.loads(_extract_json(text))
    except json.JSONDecodeError as e:
        return {
            "strengths": [],
            "weaknesses": [],
            "reasoning": "",
            "score": 0,
            "parse_error": str(e),
            "raw_response": text[:500],
        }

    score = parsed.get("score", 0)
    try:
        score = int(score)
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(10, score))  # clamp

    return {
        "strengths": parsed.get("strengths", []),
        "weaknesses": parsed.get("weaknesses", []),
        "reasoning": parsed.get("reasoning", ""),
        "score": score,
    }
