"""Edit-proposer for the auto-loop.

Reads a failing fixture's eval data, the current skill body, and recent
rejected edits, then proposes ONE bounded edit (per SkillOpt §8.1) to one of
three allowed slow-state files. Uses Claude CLI for the LLM call (subscription
OAuth, no API key).

Output is JSON-structured (see EditProposal); a confidence below 4 short-
circuits the iteration (skip apply, log decision="low_confidence").
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from typing import Optional

ALLOWED_OPERATIONS = ("add", "delete", "replace")
ALLOWED_ANCHOR_POSITIONS = ("before", "after")
ALLOWED_FILES = (
    "plugin/skills/_shared/orchestrator-procedure.md",
    "plugin/skills/_shared/references/prompt-rubric.md",
    "plugin/skills/_shared/references/examples.md",
    "plugin/skills/_shared/preambles/improve.md",
    "plugin/skills/_shared/preambles/improve-init.md",
)
LOW_CONFIDENCE_THRESHOLD = 4


@dataclass
class EditProposal:
    file: str
    operation: str
    anchor: str
    anchor_position: str
    new_content: str
    hypothesis: str
    confidence: int

    def to_edit_dict(self) -> dict:
        return asdict(self)


PROMPT_TEMPLATE = """<role>
You are a prompt-optimization agent. Your task is to propose ONE bounded edit
to a Claude Code skill that will improve its eval score on a specific failing
fixture.
</role>

<discipline>
- One edit only. Add, delete, or replace — at most 8 lines of new content.
- Edit only these files (the slow-state allowlist):
  - plugin/skills/_shared/orchestrator-procedure.md
  - plugin/skills/_shared/references/prompt-rubric.md
  - plugin/skills/_shared/references/examples.md
- Do NOT rewrite from scratch.
- Compactness matters — a deletion that does not regress the score is a win.
- The anchor field must be a UNIQUE substring of the target file (exactly one
  occurrence). Pick a distinctive sentence or phrase.
</discipline>

<failing_fixture>
id: {fixture_id}
planted_problem: {planted_problem}
expected_traits: {expected_traits}
actual_proposal: {actual_proposal}
scores: {scores}
</failing_fixture>

<current_procedure>
{procedure}
</current_procedure>

<rubric>
{rubric}
</rubric>

<recently_rejected_edits>
{history}
</recently_rejected_edits>

<output_format>
Return ONLY a single JSON object (no prose, no preamble) with these fields:
{{
  "file": "<one of the allowlist paths>",
  "operation": "add" | "delete" | "replace",
  "anchor": "<unique substring from the target file>",
  "anchor_position": "before" | "after",
  "new_content": "<the new text, or empty string for delete>",
  "hypothesis": "<one sentence: why this edit should improve the failing fixture>",
  "confidence": <integer 1-10>
}}
</output_format>"""


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(none yet)"
    lines = []
    for h in history:
        edit = h.get("edit", {})
        lines.append(
            f"- iteration {h.get('i')}: {edit.get('operation', '?')} on {edit.get('file', '?')} "
            f"(anchor: {repr(edit.get('anchor', ''))[:60]}); "
            f"hypothesis: {h.get('hypothesis', '')}; "
            f"rejected because: {h.get('decision', '')}"
        )
    return "\n".join(lines)


def assemble_proposer_prompt(*, fixture_failure: dict, procedure: str, rubric: str,
                             history: list[dict]) -> str:
    """Build the proposer prompt from the live context."""
    return PROMPT_TEMPLATE.format(
        fixture_id=fixture_failure.get("id", "?"),
        planted_problem=fixture_failure.get("planted_problem", ""),
        expected_traits=json.dumps(fixture_failure.get("expected_traits", {})),
        actual_proposal=json.dumps(fixture_failure.get("actual_proposal", {})),
        scores=json.dumps(fixture_failure.get("scores", {})),
        procedure=procedure,
        rubric=rubric,
        history=_format_history(history),
    )


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json(raw: str) -> dict:
    """Pull a JSON object out of the model response, tolerating ```json fences."""
    raw = raw.strip()
    fence = _JSON_FENCE_RE.search(raw)
    candidate = fence.group(1).strip() if fence else raw
    # Find the first '{' and the matching closing '}' — fallback for prose-wrapped output
    if not candidate.startswith("{"):
        start = candidate.find("{")
        if start < 0:
            raise ValueError("no JSON object found in response")
        candidate = candidate[start:]
    # Try to parse from the candidate; trim trailing prose if any
    for end in range(len(candidate), 0, -1):
        try:
            return json.loads(candidate[:end])
        except json.JSONDecodeError:
            continue
    raise ValueError("could not parse JSON from response")


def parse_proposer_response(raw: str) -> EditProposal:
    """Parse the proposer's raw text response into an EditProposal.
    Raises ValueError on malformed / out-of-spec output.
    """
    data = _extract_json(raw)
    # anchor_position is only required for "add"; checked after operation
    required = ("file", "operation", "anchor", "new_content", "hypothesis", "confidence")
    missing = [f for f in required if f not in data]
    if missing:
        raise ValueError(f"missing fields: {missing}")
    if data["file"] not in ALLOWED_FILES:
        raise ValueError(f"file not in allowlist: {data['file']}")
    if data["operation"] not in ALLOWED_OPERATIONS:
        raise ValueError(f"invalid operation: {data['operation']}")
    if data["operation"] == "add":
        if data.get("anchor_position") not in ALLOWED_ANCHOR_POSITIONS:
            raise ValueError(
                f"add requires anchor_position before|after, got: {data.get('anchor_position')!r}"
            )
    else:
        # delete/replace ignore anchor_position; default to 'before' for the dataclass
        data.setdefault("anchor_position", "before")
        if data.get("anchor_position") is None:
            data["anchor_position"] = "before"
    if not isinstance(data["confidence"], int) or not (1 <= data["confidence"] <= 10):
        raise ValueError(f"confidence must be int 1-10, got: {data['confidence']!r}")
    if not isinstance(data["anchor"], str) or not data["anchor"]:
        raise ValueError("anchor must be a non-empty string")
    if not isinstance(data["new_content"], str):
        raise ValueError("new_content must be a string")
    if not isinstance(data["hypothesis"], str):
        raise ValueError("hypothesis must be a string")
    return EditProposal(
        file=data["file"],
        operation=data["operation"],
        anchor=data["anchor"],
        anchor_position=data["anchor_position"],
        new_content=data["new_content"],
        hypothesis=data["hypothesis"],
        confidence=data["confidence"],
    )


def assemble_activation_proposer_prompt(*, activation_failure: dict, history: list[dict]) -> str:
    skill = activation_failure["skill"]
    return (
        "You tune the `description:` frontmatter of a Claude Code skill so the model "
        "invokes it at exactly the right moment and never otherwise.\n\n"
        f"<skill>{skill}</skill>\n"
        f"<current_description>{activation_failure['current_description']}</current_description>\n"
        f"<missed_fire_scenarios>{activation_failure.get('missed_fire', [])}</missed_fire_scenarios>\n"
        f"<false_fire_scenarios>{activation_failure.get('false_fire', [])}</false_fire_scenarios>\n"
        f"<recent_attempts>{_format_history(history)}</recent_attempts>\n\n"
        "Propose ONE bounded clause-level edit to the description (operation=replace, "
        "anchor=a unique substring of the current description, new_content=the rewritten "
        "clause). Do NOT rewrite the whole description. Output ONLY JSON with keys: "
        "file, operation, anchor, anchor_position, new_content, hypothesis, confidence."
    )


def propose_description_edit(*, activation_failure: dict, history: list[dict],
                             client, model: str) -> Optional[EditProposal]:
    prompt = assemble_activation_proposer_prompt(
        activation_failure=activation_failure, history=history)
    resp = client.messages.create(
        model=model, max_tokens=2048, messages=[{"role": "user", "content": prompt}])
    proposal = parse_proposer_response(resp.content[0].text)
    if proposal.confidence < LOW_CONFIDENCE_THRESHOLD:
        return None
    return proposal


def propose_edit(*, fixture_failure: dict, procedure: str, rubric: str,
                 history: list[dict], client, model: str) -> Optional[EditProposal]:
    """Call the proposer; return the EditProposal, or None on low confidence.

    `client` mirrors the Anthropic SDK / ClaudeCliClient shape:
    `client.messages.create(model=..., max_tokens=..., messages=[...]).content[0].text`
    """
    prompt = assemble_proposer_prompt(
        fixture_failure=fixture_failure,
        procedure=procedure,
        rubric=rubric,
        history=history,
    )
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text  # ClaudeCliClient + Anthropic SDK both expose this
    proposal = parse_proposer_response(raw)
    if proposal.confidence < LOW_CONFIDENCE_THRESHOLD:
        return None
    return proposal
