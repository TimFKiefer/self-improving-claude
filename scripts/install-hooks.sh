#!/usr/bin/env bash
# Install the repo's pre-commit guard (skill single-source drift check).
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
HOOK="$ROOT/.git/hooks/pre-commit"
if [ -f "$HOOK" ] && ! grep -q "sync_skills.py --check" "$HOOK"; then
  cp "$HOOK" "$HOOK.bak"
  echo "Backed up existing pre-commit hook to $HOOK.bak"
fi
cat > "$HOOK" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
python3 "$(git rev-parse --show-toplevel)/scripts/sync_skills.py" --check
EOF
chmod +x "$HOOK"
echo "Installed pre-commit hook: scripts/sync_skills.py --check"
