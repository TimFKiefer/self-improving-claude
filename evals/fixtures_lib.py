"""Fixture & dataset loading for the eval harness.

A fixture lives at evals/fixtures/<id>/ and contains:
- description.md             — planted-problem prose
- expected_traits.json       — what the proposed hook must look like
- project/                   — sampled project files (CLAUDE.md, manifests, etc.)
- chat.md                    — planted recent-chat content (reactive fixtures)
- telemetry.jsonl            — planted telemetry rows (proactive fixtures)

dataset.json indexes fixtures and pairs each with trigger + user_args.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent


@dataclass
class Fixture:
    id: str
    description: str
    expected_traits: dict
    project_files: dict[str, str] = field(default_factory=dict)
    chat: str = ""
    telemetry: list[dict] = field(default_factory=list)


def load_dataset() -> list[dict]:
    """Return the parsed dataset.json as a list of entries."""
    path = EVALS_DIR / "dataset.json"
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return data["entries"] if isinstance(data, dict) else data


def load_fixture(fixture_id: str) -> Fixture:
    """Load one fixture directory into a Fixture dataclass."""
    fdir = EVALS_DIR / "fixtures" / fixture_id
    if not fdir.exists():
        raise FileNotFoundError(f"Fixture not found: {fixture_id} (looked in {fdir})")

    description = (fdir / "description.md").read_text(encoding="utf-8") if (fdir / "description.md").exists() else ""
    expected_traits = json.loads((fdir / "expected_traits.json").read_text(encoding="utf-8"))

    project_files: dict[str, str] = {}
    project_dir = fdir / "project"
    if project_dir.exists():
        for f in sorted(project_dir.rglob("*")):
            if f.is_file():
                rel = f.relative_to(project_dir).as_posix()
                project_files[rel] = f.read_text(encoding="utf-8", errors="replace")

    chat = (fdir / "chat.md").read_text(encoding="utf-8") if (fdir / "chat.md").exists() else ""

    telemetry: list[dict] = []
    tpath = fdir / "telemetry.jsonl"
    if tpath.exists():
        for line in tpath.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            telemetry.append(json.loads(line))

    return Fixture(
        id=fixture_id,
        description=description,
        expected_traits=expected_traits,
        project_files=project_files,
        chat=chat,
        telemetry=telemetry,
    )
