"""Behavioral grader — verify a generated command-hook actually fires.

Drives the hook script as a subprocess with synthetic stdin payloads (the hook
stdin envelope) and checks BOTH directions: it fires on the trigger input
(exit 2, plus an optional stderr substring) and passes the clean input (exit 0).
No Claude session, no network. Only meaningful for command-hooks; callers pass
fired=None for other forms.

Spec: docs/superpowers/specs/2026-05-27-v0.4.0-hook-firing-harness-design.md
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

_EXT = {"python": ".py", "bash": ".sh", "javascript": ".js", "js": ".js", "node": ".js"}
_RUNNER = {"python": ["python3"], "bash": ["bash"],
           "javascript": ["node"], "js": ["node"], "node": ["node"]}


def _run_script(script: str, lang: str, payload: dict, timeout: float):
    ext, runner = _EXT.get(lang), _RUNNER.get(lang)
    if ext is None or runner is None:
        return None, f"unsupported script_lang: {lang!r}"
    tmpdir = Path(tempfile.mkdtemp(prefix="sic-fire-"))
    try:
        f = tmpdir / f"hook{ext}"
        f.write_text(script, encoding="utf-8")
        try:
            proc = subprocess.run(runner + [str(f)], input=json.dumps(payload),
                                  capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError:
            return None, f"interpreter not found for {lang!r}"
        except subprocess.TimeoutExpired:
            return None, "timeout"
        return proc, None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def run_firing_check(proposal: dict, firing_test: dict, *, timeout: float = 10) -> dict:
    """Verify a command-hook fires on the trigger payload and passes the clean one.

    Returns {fired, blocked_on_trigger, passed_on_clean, evidence, error}.
    fired = blocked_on_trigger AND passed_on_clean. On any run failure → error set, fired False.
    """
    out = {"fired": False, "blocked_on_trigger": False, "passed_on_clean": False,
           "evidence": {}, "error": None}
    script = proposal.get("script") or ""
    lang = (proposal.get("script_lang") or "").lower()
    if not script:
        out["error"] = "no script"
        return out
    trig, terr = _run_script(script, lang, firing_test["trigger"], timeout)
    if terr:
        out["error"] = terr
        return out
    clean, cerr = _run_script(script, lang, firing_test["passthrough"], timeout)
    if cerr:
        out["error"] = cerr
        return out
    need = firing_test.get("stderr_must_include")
    passed = clean.returncode == 0
    if passed:
        # Selective hook: correct fire requires both exit 2 and the expected stderr signal.
        blocked = (trig.returncode == 2) and (need is None or need in (trig.stderr or ""))
    else:
        # Overbroad hook (also blocks the clean case): record raw exit-2 as a diagnostic.
        blocked = trig.returncode == 2
    out.update(blocked_on_trigger=blocked, passed_on_clean=passed,
               fired=(blocked and passed),
               evidence={"trigger_rc": trig.returncode,
                         "trigger_stderr": (trig.stderr or "")[:300],
                         "clean_rc": clean.returncode})
    return out
