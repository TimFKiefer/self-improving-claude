#!/usr/bin/env python3
"""PreToolUse hook: record + block any `Skill` invocation, so we capture the
model's decision-to-invoke without paying for the full orchestrator run.
Branches on tool_name per tools-reference.md §1."""
import json, os, sys


def main() -> int:
    try:
        ev = json.load(sys.stdin)
    except Exception:
        return 0
    if ev.get("tool_name") != "Skill":
        return 0
    ti = ev.get("tool_input") or {}
    marker = os.environ.get("SPIKE_MARKER", "/tmp/sic-spike-marker.json")
    with open(marker, "w", encoding="utf-8") as fh:
        json.dump({"tool_input": ti}, fh)
    print("activation-probe: skill invocation recorded and blocked", file=sys.stderr)
    return 2  # block (PreToolUse) — hooks-and-sdk.md §4


if __name__ == "__main__":
    sys.exit(main())
