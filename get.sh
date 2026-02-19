#!/usr/bin/env bash
set -euo pipefail

# Voxhook one-line installer
# Usage: bash <(curl -fsSL https://raw.githubusercontent.com/LucaDeLeo/voxhook/main/get.sh)

CLONE_DIR="${TMPDIR:-/tmp}/voxhook-$$"
trap 'rm -rf "$CLONE_DIR"' EXIT

echo "Downloading voxhook..."
git clone --depth 1 https://github.com/LucaDeLeo/voxhook.git "$CLONE_DIR" 2>&1 | grep -v '^remote:'

"$CLONE_DIR/install.sh"
