#!/usr/bin/env bash
# Task 0 feasibility spike: does `claude --print` spontaneously invoke a plugin skill,
# and can a PreToolUse/matcher-Skill hook detect + short-circuit it?
# Usage: bash run_spike.sh fire|nofire
set -u
REPO="~/Desktop/Projects/self-improving-claude"
SCN="${1:?usage: run_spike.sh fire|nofire}"
HOOK="$REPO/evals/activation/_spike/skill_hook.py"
PROMPT="$(cat "$REPO/evals/activation/_spike/scenario_${SCN}.md")"

tmp="$(mktemp -d -t sic-spike-XXXXXX)"
mkdir -p "$tmp/.claude"
cat > "$tmp/.claude/settings.json" <<EOF
{"hooks":{"PreToolUse":[{"matcher":"Skill","hooks":[{"type":"command","command":"python3 $HOOK"}]}]}}
EOF
export SPIKE_MARKER="$tmp/marker.json"
rm -f "$SPIKE_MARKER"

cd "$tmp" || exit 1
claude --print --model haiku --plugin-dir "$REPO/plugin" \
  --permission-mode bypassPermissions --output-format json \
  --no-session-persistence --max-budget-usd 1.0 "$PROMPT" \
  > "$tmp/out.json" 2> "$tmp/err.txt"
rc=$?

echo "=== scenario: $SCN  (returncode: $rc) ==="
if [ -f "$SPIKE_MARKER" ]; then
  echo "FIRING: YES — skill was invoked. marker tool_input:"
  cat "$SPIKE_MARKER"; echo
else
  echo "FIRING: NO — no skill invocation recorded"
fi
echo "=== stderr (head) ==="; head -5 "$tmp/err.txt" 2>/dev/null
echo "=== result text (first 400 chars) ==="
python3 -c "import json;print(json.load(open('$tmp/out.json')).get('result','')[:400])" 2>/dev/null \
  || head -c 400 "$tmp/out.json" 2>/dev/null
echo
echo "=== tmp: $tmp ==="
