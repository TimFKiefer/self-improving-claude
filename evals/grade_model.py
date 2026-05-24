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

Output ONLY a single-line minified JSON object — no markdown fences, no prose before or after, no trailing whitespace."""


_FENCE_OPEN_RE = re.compile(r"^```(?:json|JSON)?\s*\n?")
_FENCE_CLOSE_RE = re.compile(r"\n?```\s*$")


def _extract_json(text: str) -> str:
    """Strip ```json``` fences if present (open and close independently).

    Tolerates outputs that are missing the closing fence — common when a
    smaller local model forgets to close its fence at the token limit.
    """
    text = text.strip()
    text = _FENCE_OPEN_RE.sub("", text)
    text = _FENCE_CLOSE_RE.sub("", text)
    return text


def grade_model(*, proposal: dict, planted_problem: str, client, judge_model: str = GRADER_MODEL) -> dict:
    """Grade one proposal. Returns {strengths, weaknesses, reasoning, score, ...}."""
    user_msg = GRADER_TEMPLATE.format(
        planted_problem=planted_problem,
        proposal_json=json.dumps(proposal, indent=2),
    )
    response = client.messages.create(
        model=judge_model,
        max_tokens=2048,
        system=GRADER_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = response.content[0].text

    try:
        parsed = json.loads(_extract_json(text))
    except json.JSONDecodeError as e:
        return {
            "valid": False,
            "score": None,
            "error": f"parse_error: {e}",
            "strengths": [],
            "weaknesses": [],
            "reasoning": "",
            "raw_response": text[:500],
        }

    raw_score = parsed.get("score")
    try:
        score = max(0, min(10, int(raw_score)))
    except (TypeError, ValueError):
        return {
            "valid": False,
            "score": None,
            "error": f"bad_score: {raw_score!r}",
            "strengths": parsed.get("strengths", []),
            "weaknesses": parsed.get("weaknesses", []),
            "reasoning": parsed.get("reasoning", ""),
        }

    return {
        "valid": True,
        "score": score,
        "error": None,
        "strengths": parsed.get("strengths", []),
        "weaknesses": parsed.get("weaknesses", []),
        "reasoning": parsed.get("reasoning", ""),
    }


BATCH_SYSTEM = """You are an expert reviewer of Claude Code hook proposals. \
Score each candidate against the planted problem it must solve. Be concrete and \
honest: low scores for proposals that don't solve the problem, high scores for those \
that do. Do NOT default every item to a middling 6 — spread your scores to reflect \
real differences."""

BATCH_TEMPLATE = """<planted_problem>
{planted_problem}
</planted_problem>

Score how well EACH of the {n} candidate proposals below solves the planted problem.
Judge what the proposal DOES, not how it is phrased. Scale: 10 = exactly solves it,
7-9 strong, 4-6 partial, 1-3 misses the point, 0 irrelevant.

{proposals_block}

Respond with ONLY a single-line minified JSON array — one object per proposal, in the
same order, each with "reasoning" BEFORE "score":
[{{"index":0,"reasoning":"<one clause>","score":<int 0-10>}}, ...]
No markdown fences, no prose before or after."""


def _proposals_block(items: list[dict]) -> str:
    parts = [f'<proposal index="{i}">\n{json.dumps(p)}\n</proposal>' for i, p in enumerate(items)]
    return "<proposals>\n" + "\n".join(parts) + "\n</proposals>"


def grade_model_batch(*, items: list[dict], planted_problem: str, client,
                      judge_model: str = GRADER_MODEL) -> list[dict]:
    """Score a LIST of proposals against one planted problem in a SINGLE judge call.

    Returns a list aligned to `items` by index; each:
      {"valid": bool, "score": int|None, "reasoning": str, "error": str|None}
    A missing item or an unparseable response yields valid=False/score=None for the
    affected items — never a misleading 0 (eval-methodology.md §3 + v0.3.4 fix).
    """
    if not items:
        return []
    user_msg = BATCH_TEMPLATE.format(
        planted_problem=planted_problem, n=len(items),
        proposals_block=_proposals_block(items),
    )
    response = client.messages.create(
        model=judge_model,
        max_tokens=min(4096, 256 + 200 * len(items)),
        system=BATCH_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = response.content[0].text
    try:
        parsed = json.loads(_extract_json(text))
        if not isinstance(parsed, list):
            raise ValueError("expected a JSON array")
    except (json.JSONDecodeError, ValueError) as e:
        return [{"valid": False, "score": None, "reasoning": "",
                 "error": f"batch_parse_error: {e}"} for _ in items]

    by_index = {o["index"]: o for o in parsed if isinstance(o, dict) and "index" in o}
    out: list[dict] = []
    for i in range(len(items)):
        obj = by_index.get(i)
        if obj is None:
            out.append({"valid": False, "score": None, "reasoning": "", "error": "missing_item"})
            continue
        try:
            score = max(0, min(10, int(obj.get("score"))))
        except (TypeError, ValueError):
            out.append({"valid": False, "score": None,
                        "reasoning": obj.get("reasoning", ""), "error": f"bad_score: {obj.get('score')!r}"})
            continue
        out.append({"valid": True, "score": score, "reasoning": obj.get("reasoning", ""), "error": None})
    return out
