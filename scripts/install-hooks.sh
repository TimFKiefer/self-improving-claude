#!/usr/bin/env bash
# Install the repo's pre-commit guard (skill single-source drift check).
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
HOOK="$ROOT/.git/hooks/pre-commit"
cat > "$HOOK" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
python3 "$(git rev-parse --show-toplevel)/scripts/sync_skills.py" --check
EOF
chmod +x "$HOOK"
echo "Installed pre-commit hook: scripts/sync_skills.py --check"
