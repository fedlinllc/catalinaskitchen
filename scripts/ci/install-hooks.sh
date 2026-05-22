#!/usr/bin/env bash
# ============================================================
# Installs local git hooks from scripts/ci/
#
# Usage (from repo root):
#   bash scripts/ci/install-hooks.sh
# ============================================================

set -euo pipefail

HOOKS_SRC="scripts/ci"
HOOKS_DST=".git/hooks"

if [[ ! -d ".git" ]]; then
  echo "Error: must be run from the repo root (directory containing .git/)"
  exit 1
fi

echo ""
echo "  Installing local git hooks from $HOOKS_SRC/ → $HOOKS_DST/"
echo ""

INSTALLED=0
SKIPPED=0

for hook in pre-commit pre-push; do
  src="$HOOKS_SRC/$hook"
  dst="$HOOKS_DST/$hook"

  if [[ ! -f "$src" ]]; then
    echo "  ⚠  $src not found — skipped"
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  if [[ -f "$dst" ]] && ! diff -q "$src" "$dst" &>/dev/null; then
    echo "  ⚠  $dst already exists and differs — backing up as $dst.bak"
    cp "$dst" "$dst.bak"
  fi

  cp "$src" "$dst"
  chmod +x "$dst"
  echo "  ✓  $hook"
  INSTALLED=$((INSTALLED + 1))
done

echo ""
echo "  $INSTALLED hook(s) installed, $SKIPPED skipped."
echo ""
echo "  The hooks run automatically:"
echo "    pre-commit  — on every 'git commit' (Gitleaks: staged secret scan)"
echo "    pre-push    — on every 'git push'   (TypeScript check + Trivy SCA)"
echo ""
echo "  Emergency bypass (avoid unless truly necessary):"
echo "    git commit --no-verify"
echo "    git push   --no-verify"
echo ""
