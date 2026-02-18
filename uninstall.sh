#!/usr/bin/env bash
set -euo pipefail

# Voxhook Uninstaller
# Removes voxhook files and hook entries from Claude Code settings

INSTALL_DIR="$HOME/.claude/hooks/voxhook"
SETTINGS_FILE="$HOME/.claude/settings.json"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[voxhook]${NC} $*"; }
ok()    { echo -e "${GREEN}[voxhook]${NC} $*"; }
err()   { echo -e "${RED}[voxhook]${NC} $*" >&2; }

echo "Voxhook Uninstaller"
echo ""

# ── Remove installed files ───────────────────────────────────────────────────
if [[ -d "$INSTALL_DIR" ]]; then
    info "Removing ${INSTALL_DIR}..."
    rm -rf "$INSTALL_DIR"
    ok "Files removed."
else
    info "No installation found at ${INSTALL_DIR}."
fi

# ── Clean settings.json ─────────────────────────────────────────────────────
if [[ -f "$SETTINGS_FILE" ]]; then
    info "Cleaning hook entries from settings.json..."

    python3 << 'PYEOF'
import json
from pathlib import Path

settings_path = Path.home() / ".claude" / "settings.json"
settings = json.loads(settings_path.read_text())
hooks = settings.get("hooks", {})
changed = False

for event_name in list(hooks.keys()):
    entries = hooks[event_name]
    if not isinstance(entries, list):
        continue

    filtered = []
    for entry in entries:
        keep = True
        for h in entry.get("hooks", []):
            if "voxhook" in h.get("command", ""):
                keep = False
                break
        if keep:
            filtered.append(entry)

    if len(filtered) != len(entries):
        hooks[event_name] = filtered
        changed = True

    # Remove empty event arrays
    if not hooks[event_name]:
        del hooks[event_name]
        changed = True

if changed:
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    print("[voxhook] settings.json cleaned.")
else:
    print("[voxhook] No voxhook entries found in settings.json.")
PYEOF

    ok "Settings cleaned."
else
    info "No settings.json found."
fi

echo ""
ok "Voxhook uninstalled."
