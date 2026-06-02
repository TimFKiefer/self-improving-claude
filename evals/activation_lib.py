from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

ACTIVATION_DIR = Path(__file__).resolve().parent / "activation"

@dataclass
class ActivationFixture:
    id: str
    skill: str
    label: str        # "fire" | "no-fire"
    scenario: str     # the prompt text

def load_activation_dataset() -> list[dict]:
    data = json.loads((ACTIVATION_DIR / "dataset.json").read_text(encoding="utf-8"))
    return data["entries"] if isinstance(data, dict) else data

def load_activation_fixture(fixture_id: str) -> ActivationFixture:
    entry = next((e for e in load_activation_dataset() if e["id"] == fixture_id), None)
    if entry is None:
        raise ValueError(f"activation fixture not found: {fixture_id}")
    scenario = (ACTIVATION_DIR / entry["scenario"]).read_text(encoding="utf-8").strip()
    return ActivationFixture(id=entry["id"], skill=entry["skill"],
                             label=entry["label"], scenario=scenario)
