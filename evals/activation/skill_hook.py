#!/usr/bin/env python3
"""PreToolUse hook: append each `Skill` invocation to $SPIKE_MARKER (JSONL) and exit-2
block it — detection + short-circuit in one (Task 0)."""
import json, os, sys

def main() -> int:
    try:
        ev = json.load(sys.stdin)
    except Exception:
        return 0
    if ev.get("tool_name") != "Skill":
        return 0
    ti = ev.get("tool_input") or {}
    marker = os.environ.get("SPIKE_MARKER", "/tmp/sic-act-marker.jsonl")
    with open(marker, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"skill": ti.get("skill") or ti.get("name")}) + "\n")
    print("activation-probe: skill invocation recorded and blocked", file=sys.stderr)
    return 2

if __name__ == "__main__":
    sys.exit(main())
