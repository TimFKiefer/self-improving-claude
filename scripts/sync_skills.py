"""Single-source the orchestrator skills.

Canonical sources under plugin/skills/_shared/: orchestrator-procedure.md (shared
Steps 1-10 body), preambles/<skill>.md (per-skill head), references/*.md (5 docs).
`build` writes each plugin/skills/<skill>/SKILL.md = preamble + procedure and copies
references/ into each skill. Byte-preserving, so regenerating a correctly-seeded tree
is a no-op. `--check` (pre-commit) fails on drift.

Usage:
  python3 scripts/sync_skills.py            # build
  python3 scripts/sync_skills.py --check    # verify on-disk == generated (exit 1 on drift)
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILLS = REPO / "plugin" / "skills"
SHARED = SKILLS / "_shared"
PROCEDURE = SHARED / "orchestrator-procedure.md"
PREAMBLES = SHARED / "preambles"
SHARED_REFS = SHARED / "references"
TARGETS = ("improve", "improve-init")
REF_FILES = ("prompt-rubric.md", "hook-patterns.md", "tools-reference.md",
             "settings-merge.md", "examples.md")


def _generated_files() -> dict[Path, str]:
    procedure = PROCEDURE.read_text(encoding="utf-8")
    refs = {r: (SHARED_REFS / r).read_text(encoding="utf-8") for r in REF_FILES}
    out: dict[Path, str] = {}
    for skill in TARGETS:
        preamble = (PREAMBLES / f"{skill}.md").read_text(encoding="utf-8")
        out[SKILLS / skill / "SKILL.md"] = preamble + procedure
        for r in REF_FILES:
            out[SKILLS / skill / "references" / r] = refs[r]
    return out


def build() -> None:
    for path, content in _generated_files().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def check() -> int:
    drift = [path.relative_to(REPO) for path, content in _generated_files().items()
             if (path.read_text(encoding="utf-8") if path.exists() else None) != content]
    if drift:
        print("Skill files are out of sync with plugin/skills/_shared/ — run "
              "`python3 scripts/sync_skills.py`:", file=sys.stderr)
        for p in drift:
            print(f"  {p}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--check" in argv:
        return check()
    build()
    print("Generated SKILL.md + references for: " + ", ".join(TARGETS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
