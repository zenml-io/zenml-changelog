#!/bin/bash
# Installs git hooks for this repository

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"

cat > "$HOOKS_DIR/pre-commit" << 'EOF'
#!/bin/bash
# Validates changelog.json against schema before commit

# Only run if changelog.json is staged
if git diff --cached --name-only | grep -q '^changelog\.json$'; then
    echo "Validating changelog.json..."
    uv run scripts/validate_changelog.py
    exit $?
fi
EOF

chmod +x "$HOOKS_DIR/pre-commit"
echo "Git hooks installed successfully!"
