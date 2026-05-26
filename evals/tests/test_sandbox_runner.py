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


from evals.sandbox_runner import _parse_echo, _read_written


def test_parse_echo_plain_object():
    props, valid = _parse_echo('{"proposals":[{"form":"permissions.deny","rule":"Read(**/.env*)"}]}')
    assert valid is True and props[0]["rule"] == "Read(**/.env*)"


def test_parse_echo_trailing_object_after_prose():
    text = "Here is what I installed.\n\n{\"proposals\":[{\"form\":\"claude-md-note\"}]}"
    props, valid = _parse_echo(text)
    assert valid is True and props[0]["form"] == "claude-md-note"


def test_parse_echo_empty_proposals_is_valid():
    props, valid = _parse_echo('{"proposals":[]}')
    assert props == [] and valid is True


def test_parse_echo_garbage_is_invalid():
    props, valid = _parse_echo("no json here")
    assert props == [] and valid is False


def test_read_written_reads_settings_hooks_perms(tmp_path):
    cdir = tmp_path / ".claude"; (cdir / "hooks").mkdir(parents=True)
    (cdir / "hooks" / "block-env.py").write_text("# hook\n")
    (cdir / "settings.json").write_text(json.dumps(
        {"permissions": {"deny": ["Read(**/.env*)"]}, "hooks": {"PreToolUse": []}}))
    w = _read_written(tmp_path)
    assert w["settings_parses"] is True
    assert "Read(**/.env*)" in w["permission_rules"]
    assert "block-env.py" in w["hook_files"]


def test_read_written_unparseable_settings(tmp_path):
    cdir = tmp_path / ".claude"; cdir.mkdir()
    (cdir / "settings.json").write_text("{ not json")
    w = _read_written(tmp_path)
    assert w["settings_parses"] is False and w["permission_rules"] == []


from types import SimpleNamespace
import evals.sandbox_runner as sr


def test_run_in_sandbox_orchestrates(monkeypatch):
    captured = {}

    def fake_run(argv, *, cwd, capture_output, text, timeout):
        captured["argv"] = argv
        captured["cwd"] = cwd
        cdir = Path(cwd) / ".claude"; (cdir / "hooks").mkdir(parents=True, exist_ok=True)
        (cdir / "settings.json").write_text(json.dumps({"permissions": {"deny": ["Read(**/.env*)"]}}))
        result = {"result": '{"proposals":[{"form":"permissions.deny","rule":"Read(**/.env*)"}]}'}
        return SimpleNamespace(returncode=0, stdout=json.dumps(result), stderr="")

    monkeypatch.setattr(sr.subprocess, "run", fake_run)
    fx = _fx(project_files={"CLAUDE.md": "# p\n"})
    out = sr.run_in_sandbox(entry={"id": "x", "trigger": "improve-init", "user_args": ""},
                            fixture=fx, model="haiku", plugin_path=Path("/repo/plugin"))
    assert out["echo"][0]["rule"] == "Read(**/.env*)"
    assert out["echo_valid"] is True
    assert out["written"]["settings_parses"] is True
    assert "Read(**/.env*)" in out["written"]["permission_rules"]
    assert out["returncode"] == 0 and out["error"] is None
    assert captured["argv"][-1] == "/improve-init"
    assert not Path(captured["cwd"]).exists()


def test_run_in_sandbox_nonzero_returncode_sets_error(monkeypatch):
    monkeypatch.setattr(sr.subprocess, "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="boom"))
    out = sr.run_in_sandbox(entry={"id": "x", "trigger": "improve", "user_args": "do it"},
                            fixture=_fx(chat="USER: x\n"), model="haiku", plugin_path=Path("/p"))
    assert out["returncode"] == 1 and "boom" in out["error"]
    assert out["echo"] == [] and out["echo_valid"] is False
