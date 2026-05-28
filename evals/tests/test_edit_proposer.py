"""Tests for evals/edit_proposer.py — prompt assembly + response parsing."""
import json
from types import SimpleNamespace

import pytest

from evals.edit_proposer import (
    assemble_proposer_prompt,
    parse_proposer_response,
    propose_edit,
    EditProposal,
    ALLOWED_FILES,
)


def _fixture():
    return {
        "id": "010-block-staging-fetch",
        "planted_problem": "Claude pulls staging into local feature branches.",
        "expected_traits": {"form": "permissions.ask", "rule_pattern": "Bash(git fetch:*)"},
        "actual_proposal": {"form": "permissions.deny", "rule": "Bash(git fetch:*)"},
        "scores": {"code": 3.3, "install": 0, "fire": None, "model": 9},
    }


def _valid_response():
    return {
        "file": "plugin/skills/_shared/orchestrator-procedure.md",
        "operation": "add",
        "anchor": "## Step 4 — Choose the lightest form that does the job",
        "anchor_position": "after",
        "new_content": "\n\n(extra guidance for git fetch case)\n",
        "hypothesis": "Nudge model toward permissions.ask for git fetch-style commands.",
        "confidence": 7,
    }


def test_assemble_prompt_includes_all_context_blocks():
    prompt = assemble_proposer_prompt(
        fixture_failure=_fixture(),
        procedure="PROCEDURE_BODY",
        rubric="RUBRIC_BODY",
        history=[],
    )
    assert "<failing_fixture>" in prompt
    assert "010-block-staging-fetch" in prompt
    assert "<current_procedure>" in prompt
    assert "PROCEDURE_BODY" in prompt
    assert "<rubric>" in prompt
    assert "RUBRIC_BODY" in prompt
    assert "<recently_rejected_edits>" in prompt
    assert "(none yet)" in prompt  # empty history rendered cleanly


def test_assemble_prompt_renders_history():
    prompt = assemble_proposer_prompt(
        fixture_failure=_fixture(),
        procedure="P", rubric="R",
        history=[{
            "i": 3,
            "edit": {"operation": "add", "file": "x.md", "anchor": "Step Y"},
            "hypothesis": "tried adding a banner",
            "decision": "rejected: no_visible_gain",
        }],
    )
    assert "iteration 3" in prompt
    assert "tried adding a banner" in prompt
    assert "(none yet)" not in prompt


def test_parse_accepts_valid_json():
    raw = json.dumps(_valid_response())
    p = parse_proposer_response(raw)
    assert isinstance(p, EditProposal)
    assert p.confidence == 7
    assert p.operation == "add"


def test_parse_accepts_json_in_fences():
    raw = "Here is my proposal:\n```json\n" + json.dumps(_valid_response()) + "\n```\n"
    p = parse_proposer_response(raw)
    assert p.confidence == 7


def test_parse_accepts_unfenced_json_with_preamble():
    raw = "Some chatty prefix\n\n" + json.dumps(_valid_response())
    p = parse_proposer_response(raw)
    assert p.confidence == 7


def test_parse_rejects_missing_field():
    data = _valid_response()
    del data["hypothesis"]
    with pytest.raises(ValueError, match="hypothesis"):
        parse_proposer_response(json.dumps(data))


def test_parse_rejects_invalid_operation():
    data = _valid_response()
    data["operation"] = "wibble"
    with pytest.raises(ValueError, match="invalid operation"):
        parse_proposer_response(json.dumps(data))


def test_parse_rejects_invalid_anchor_position():
    data = _valid_response()
    data["anchor_position"] = "inside"
    with pytest.raises(ValueError, match="anchor_position"):
        parse_proposer_response(json.dumps(data))


def test_parse_rejects_file_outside_allowlist():
    data = _valid_response()
    data["file"] = "evals/run.py"
    with pytest.raises(ValueError, match="allowlist"):
        parse_proposer_response(json.dumps(data))


def test_parse_rejects_confidence_out_of_range():
    data = _valid_response()
    data["confidence"] = 15
    with pytest.raises(ValueError, match="confidence"):
        parse_proposer_response(json.dumps(data))


def test_parse_rejects_empty_anchor():
    data = _valid_response()
    data["anchor"] = ""
    with pytest.raises(ValueError, match="anchor"):
        parse_proposer_response(json.dumps(data))


# β: anchor_position is only required for add (α anomaly fix)
def test_parse_accepts_delete_with_null_anchor_position():
    data = _valid_response()
    data["operation"] = "delete"
    data["anchor_position"] = None
    data["new_content"] = ""
    p = parse_proposer_response(json.dumps(data))
    assert p.operation == "delete"
    # anchor_position defaulted to 'before' (ignored for delete)
    assert p.anchor_position == "before"


def test_parse_accepts_replace_with_missing_anchor_position():
    data = _valid_response()
    data["operation"] = "replace"
    del data["anchor_position"]
    p = parse_proposer_response(json.dumps(data))
    assert p.operation == "replace"
    assert p.anchor_position == "before"  # defaulted


def test_parse_still_rejects_add_with_invalid_anchor_position():
    data = _valid_response()
    data["operation"] = "add"
    data["anchor_position"] = "inside"
    with pytest.raises(ValueError, match="anchor_position"):
        parse_proposer_response(json.dumps(data))


def test_parse_still_rejects_add_with_null_anchor_position():
    """β: this is the exact α run-1 i=4 anomaly."""
    data = _valid_response()
    data["operation"] = "add"
    data["anchor_position"] = None
    with pytest.raises(ValueError, match="anchor_position"):
        parse_proposer_response(json.dumps(data))


class _FakeClient:
    def __init__(self, response_text):
        self._response_text = response_text
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        # Mirror the Anthropic SDK / ClaudeCliClient response shape
        return SimpleNamespace(content=[SimpleNamespace(text=self._response_text)])


def test_propose_edit_returns_none_on_low_confidence():
    data = _valid_response()
    data["confidence"] = 2  # below LOW_CONFIDENCE_THRESHOLD
    client = _FakeClient(json.dumps(data))
    out = propose_edit(
        fixture_failure=_fixture(), procedure="P", rubric="R",
        history=[], client=client, model="claude-sonnet-4-5",
    )
    assert out is None


def test_propose_edit_returns_proposal_on_good_confidence():
    client = _FakeClient(json.dumps(_valid_response()))
    out = propose_edit(
        fixture_failure=_fixture(), procedure="P", rubric="R",
        history=[], client=client, model="claude-sonnet-4-5",
    )
    assert isinstance(out, EditProposal)
    assert out.confidence == 7


def test_allowed_files_match_apply_edit_allowlist():
    """Cross-check that proposer allowlist == apply_edit allowlist."""
    from evals.auto_loop import SLOW_STATE_ALLOWLIST
    assert set(ALLOWED_FILES) == SLOW_STATE_ALLOWLIST
