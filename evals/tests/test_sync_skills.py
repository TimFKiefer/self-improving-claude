import scripts.sync_skills as ss


def _seed_tmp(tmp_path, monkeypatch):
    skills = tmp_path / "plugin" / "skills"
    shared = skills / "_shared"
    (shared / "preambles").mkdir(parents=True)
    (shared / "references").mkdir(parents=True)
    (shared / "orchestrator-procedure.md").write_text("# self-improving-claude — Orchestrator\nBODY\n")
    (shared / "preambles" / "improve.md").write_text("PRE-A\n")
    (shared / "preambles" / "improve-init.md").write_text("PRE-B\n")
    for r in ss.REF_FILES:
        (shared / "references" / r).write_text(f"REF {r}\n")
    monkeypatch.setattr(ss, "REPO", tmp_path)
    monkeypatch.setattr(ss, "SKILLS", skills)
    monkeypatch.setattr(ss, "SHARED", shared)
    monkeypatch.setattr(ss, "PROCEDURE", shared / "orchestrator-procedure.md")
    monkeypatch.setattr(ss, "PREAMBLES", shared / "preambles")
    monkeypatch.setattr(ss, "SHARED_REFS", shared / "references")
    return skills


def test_build_assembles_skill_md_and_refs(tmp_path, monkeypatch):
    skills = _seed_tmp(tmp_path, monkeypatch)
    ss.build()
    assert (skills / "improve" / "SKILL.md").read_text() == "PRE-A\n# self-improving-claude — Orchestrator\nBODY\n"
    assert (skills / "improve-init" / "SKILL.md").read_text() == "PRE-B\n# self-improving-claude — Orchestrator\nBODY\n"
    assert (skills / "improve" / "references" / "examples.md").read_text() == "REF examples.md\n"


def test_check_passes_then_detects_drift(tmp_path, monkeypatch):
    skills = _seed_tmp(tmp_path, monkeypatch)
    ss.build()
    assert ss.check() == 0
    ss.build()
    assert ss.check() == 0
    (skills / "improve" / "SKILL.md").write_text("HAND EDITED\n")
    assert ss.check() == 1
