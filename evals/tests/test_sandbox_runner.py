import json
from pathlib import Path

from evals.fixtures_lib import Fixture
from evals.sandbox_runner import _build_argv, _build_override, _build_sandbox


def _fx(**kw):
    base = dict(id="x", description="", expected_traits={}, project_files={}, chat="", telemetry=[])
    base.update(kw)
    return Fixture(**base)


def test_build_override_reactive_includes_chat():
    out = _build_override({"trigger": "improve"}, _fx(chat="USER: oops\n"))
    assert "ABSOLUTE DIRECTIVE" in out
    assert "USER: oops" in out


def test_build_override_proactive_excludes_chat():
    out = _build_override({"trigger": "improve-init"}, _fx(chat="USER: oops\n"))
    assert "USER: oops" not in out


def test_build_sandbox_writes_project_and_telemetry(tmp_path):
    fx = _fx(project_files={"CLAUDE.md": "# hi\n", "src/a.py": "x = 1\n"},
             telemetry=[{"tool": "Bash", "args_summary": "ls"}])
    _build_sandbox(tmp_path, fx)
    assert (tmp_path / "CLAUDE.md").read_text() == "# hi\n"
    assert (tmp_path / "src" / "a.py").read_text() == "x = 1\n"
    tel = (tmp_path / ".claude" / "self-improving-claude" / "telemetry.jsonl").read_text()
    assert json.loads(tel.splitlines()[0])["tool"] == "Bash"
    assert (tmp_path / ".claude").is_dir()


def test_build_argv_flags_and_command():
    argv = _build_argv(model="claude-sonnet-4-5", command="/improve-init",
                       plugin_path=Path("/repo/plugin"), override="OVR")
    assert argv[0:2] == ["claude", "--print"]
    assert "claude-sonnet-4-5" in argv
    assert "--plugin-dir" in argv and "/repo/plugin" in argv
    assert "bypassPermissions" in argv
    assert argv[-1] == "/improve-init"
    assert "--append-system-prompt" in argv
