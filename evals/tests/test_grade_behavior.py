from evals.grade_behavior import run_firing_check

_GUARD = """import json, sys
d = json.loads(sys.stdin.read())
cmd = d.get("tool_input", {}).get("command", "")
if cmd.startswith("pnpm test") and not cmd.startswith("pnpm test:ci"):
    print("Run pnpm test:ci instead — pnpm test is the watcher.", file=sys.stderr)
    sys.exit(2)
sys.exit(0)
"""
_FT = {"trigger":     {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                       "tool_input": {"command": "pnpm test"}},
       "passthrough": {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                       "tool_input": {"command": "pnpm test:ci"}},
       "stderr_must_include": "test:ci"}


def test_fires_on_trigger_and_passes_clean():
    out = run_firing_check({"form": "command-hook", "script_lang": "python", "script": _GUARD}, _FT)
    assert out["fired"] is True
    assert out["blocked_on_trigger"] is True and out["passed_on_clean"] is True
    assert out["evidence"]["trigger_rc"] == 2 and out["evidence"]["clean_rc"] == 0


def test_noop_hook_does_not_fire():
    out = run_firing_check({"form": "command-hook", "script_lang": "python",
                            "script": "import sys; sys.exit(0)"}, _FT)
    assert out["blocked_on_trigger"] is False and out["fired"] is False


def test_overbroad_hook_fails_clean():
    out = run_firing_check({"form": "command-hook", "script_lang": "python",
                            "script": "import sys; print('x', file=sys.stderr); sys.exit(2)"}, _FT)
    assert out["blocked_on_trigger"] is True and out["passed_on_clean"] is False
    assert out["fired"] is False


def test_stderr_substring_required():
    script = """import json, sys
d = json.loads(sys.stdin.read())
if d.get("tool_input", {}).get("command", "").startswith("pnpm test") and "ci" not in d["tool_input"]["command"]:
    print("nope", file=sys.stderr); sys.exit(2)
sys.exit(0)
"""
    out = run_firing_check({"form": "command-hook", "script_lang": "python", "script": script}, _FT)
    assert out["blocked_on_trigger"] is False


def test_unsupported_lang_sets_error():
    out = run_firing_check({"form": "command-hook", "script_lang": "ruby", "script": "x"}, _FT)
    assert out["error"] and out["fired"] is False


def test_empty_script_sets_error():
    out = run_firing_check({"form": "command-hook", "script_lang": "python", "script": ""}, _FT)
    assert out["error"] and out["fired"] is False


def test_bash_hook_fires():
    script = 'read -r line\ncase "$line" in *"pnpm test:ci"*) exit 0;; *"pnpm test"*) echo "use test:ci" >&2; exit 2;; esac\nexit 0\n'
    ft = {"trigger": {"tool_input": {"command": "pnpm test"}},
          "passthrough": {"tool_input": {"command": "pnpm test:ci"}},
          "stderr_must_include": "test:ci"}
    out = run_firing_check({"form": "command-hook", "script_lang": "bash", "script": script}, ft)
    assert out["fired"] is True
