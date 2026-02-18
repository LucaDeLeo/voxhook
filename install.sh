#!/usr/bin/env bash
set -euo pipefail

# Voxhook Installer
# Installs push notifications + TTS voice cloning for Claude Code

INSTALL_DIR="$HOME/.claude/hooks/voxhook"
SETTINGS_FILE="$HOME/.claude/settings.json"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${CYAN}[voxhook]${NC} $*"; }
ok()    { echo -e "${GREEN}[voxhook]${NC} $*"; }
warn()  { echo -e "${YELLOW}[voxhook]${NC} $*"; }
err()   { echo -e "${RED}[voxhook]${NC} $*" >&2; }

# ── Determine source directory ──────────────────────────────────────────────
# If run from a cloned repo, use it; otherwise bail with instructions.
if [[ -f "$(dirname "$0")/hooks/tts/handler.py" ]]; then
    SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
elif [[ -f "./hooks/tts/handler.py" ]]; then
    SOURCE_DIR="$(pwd)"
else
    err "Cannot find voxhook source files."
    err "Run this script from the cloned voxhook repo directory."
    exit 1
fi

info "Source: ${SOURCE_DIR}"

# ── Check prerequisites ─────────────────────────────────────────────────────
info "Checking prerequisites..."

missing=()

# Python 3.11+
if command -v python3 &>/dev/null; then
    py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    py_major=$(echo "$py_version" | cut -d. -f1)
    py_minor=$(echo "$py_version" | cut -d. -f2)
    if (( py_major < 3 || (py_major == 3 && py_minor < 11) )); then
        missing+=("Python 3.11+ (found $py_version)")
    fi
else
    missing+=("python3")
fi

# uv
if ! command -v uv &>/dev/null; then
    missing+=("uv (https://docs.astral.sh/uv/)")
fi

# afplay (macOS)
if [[ "$(uname)" == "Darwin" ]] && ! command -v afplay &>/dev/null; then
    missing+=("afplay (should be built into macOS)")
fi

# Claude Code directory
if [[ ! -d "$HOME/.claude" ]]; then
    missing+=("~/.claude directory (install Claude Code first)")
fi

if (( ${#missing[@]} > 0 )); then
    err "Missing prerequisites:"
    for m in "${missing[@]}"; do
        err "  - $m"
    done
    exit 1
fi

ok "All prerequisites met."

# ── Interactive configuration ────────────────────────────────────────────────
echo ""
echo -e "${BOLD}Voxhook Setup${NC}"
echo ""

# ntfy.sh topic
random_suffix=$(head -c 4 /dev/urandom | xxd -p)
default_topic="voxhook-${random_suffix}"
read -rp "$(echo -e "${CYAN}ntfy.sh topic${NC} [${default_topic}]: ")" ntfy_topic
ntfy_topic="${ntfy_topic:-$default_topic}"

# TTS setup
echo ""
echo -e "${BOLD}TTS Voice Cloning (optional)${NC}"
echo "  Requires a reference .wav file of the voice you want to clone."
echo "  Skip this for push-notification-only mode."
echo ""
read -rp "$(echo -e "${CYAN}Path to reference voice WAV${NC} (leave empty to skip): ")" voice_path

enable_tts=false
if [[ -n "$voice_path" ]]; then
    voice_path="${voice_path/#\~/$HOME}"
    if [[ -f "$voice_path" ]]; then
        enable_tts=true
        ok "Voice file found: ${voice_path}"
    else
        err "File not found: ${voice_path}"
        read -rp "Continue without TTS? [Y/n] " cont
        if [[ "${cont,,}" == "n" ]]; then
            exit 1
        fi
    fi
fi

# Template selection
template_file="${SOURCE_DIR}/templates/default.json"
if [[ "$enable_tts" == true ]]; then
    echo ""
    echo -e "${BOLD}Message template preset:${NC}"
    echo "  1) default   - Neutral professional tone"
    echo "  2) abathur   - Evolutionary/clinical Abathur style"
    echo "  3) custom    - Provide your own JSON file"
    read -rp "$(echo -e "${CYAN}Choice${NC} [1]: ")" template_choice
    template_choice="${template_choice:-1}"

    case "$template_choice" in
        2)
            template_file="${SOURCE_DIR}/templates/abathur.json"
            ;;
        3)
            read -rp "Path to custom templates JSON: " custom_template
            custom_template="${custom_template/#\~/$HOME}"
            if [[ -f "$custom_template" ]]; then
                template_file="$custom_template"
            else
                warn "File not found, using default template."
            fi
            ;;
        *)
            template_file="${SOURCE_DIR}/templates/default.json"
            ;;
    esac
fi

# ── Install files ────────────────────────────────────────────────────────────
echo ""
info "Installing to ${INSTALL_DIR}..."

# Remove previous install if present
if [[ -d "$INSTALL_DIR" ]]; then
    warn "Existing installation found, replacing..."
    rm -rf "$INSTALL_DIR"
fi

# Copy hook files
mkdir -p "$INSTALL_DIR"
cp -R "${SOURCE_DIR}/hooks/common" "$INSTALL_DIR/common"
cp -R "${SOURCE_DIR}/hooks/notify" "$INSTALL_DIR/notify"
cp -R "${SOURCE_DIR}/hooks/tts"    "$INSTALL_DIR/tts"

# Copy selected template
if [[ "$enable_tts" == true ]]; then
    cp "$template_file" "$INSTALL_DIR/tts/templates.json"
fi

# Copy reference voice
if [[ "$enable_tts" == true ]]; then
    mkdir -p "$INSTALL_DIR/tts/reference"
    cp "$voice_path" "$INSTALL_DIR/tts/reference/voice.wav"
    ok "Voice file copied."
fi

# Create cache directory
mkdir -p "$INSTALL_DIR/tts/cache"

ok "Files installed."

# ── Patch settings.json ──────────────────────────────────────────────────────
info "Configuring Claude Code hooks..."

# Use inline Python for safe JSON manipulation
python3 << PYEOF
import json
import sys
from pathlib import Path

settings_path = Path("${SETTINGS_FILE}")

# Load existing settings or create minimal structure
if settings_path.exists():
    settings = json.loads(settings_path.read_text())
else:
    settings = {}

hooks = settings.setdefault("hooks", {})

# Check if voxhook entries already exist
def has_voxhook(entries):
    for entry in entries:
        for h in entry.get("hooks", []):
            if "voxhook" in h.get("command", ""):
                return True
    return False

# Push notification hook (Stop)
stop_hooks = hooks.setdefault("Stop", [])
if not has_voxhook(stop_hooks):
    stop_hooks.append({
        "hooks": [{
            "type": "command",
            "command": "nohup uv run ~/.claude/hooks/voxhook/notify/handler.py --topic=${ntfy_topic} &"
        }]
    })

# TTS hooks (Stop + Notification)
enable_tts = ${enable_tts}
if enable_tts:
    if not any("voxhook/tts" in h.get("command", "") for entry in stop_hooks for h in entry.get("hooks", [])):
        stop_hooks.append({
            "hooks": [{
                "type": "command",
                "command": "uv run ~/.claude/hooks/voxhook/tts/handler.py --ntfy-topic=${ntfy_topic}",
                "timeout": 5
            }]
        })

    notif_hooks = hooks.setdefault("Notification", [])
    if not has_voxhook(notif_hooks):
        notif_hooks.append({
            "hooks": [{
                "type": "command",
                "command": "uv run ~/.claude/hooks/voxhook/tts/handler.py",
                "timeout": 5
            }]
        })

settings_path.write_text(json.dumps(settings, indent=2) + "\n")
print("[voxhook] settings.json updated.")
PYEOF

ok "Hooks configured."

# ── Optional pre-generation ──────────────────────────────────────────────────
if [[ "$enable_tts" == true ]]; then
    echo ""
    echo -e "${BOLD}Pre-generate TTS audio cache?${NC}"
    echo "  This generates WAV files for all template messages upfront."
    echo "  Takes a few minutes but ensures instant playback from the start."
    read -rp "$(echo -e "${CYAN}Pre-generate?${NC} [y/N]: ")" pregen
    if [[ "${pregen,,}" == "y" ]]; then
        info "Starting pre-generation (this will take a while)..."
        uv run --python 3.11 "$INSTALL_DIR/tts/generate.py" --pre-generate || {
            warn "Pre-generation had errors. TTS will generate on-demand instead."
        }
    fi
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}Voxhook installed successfully!${NC}"
echo ""
echo -e "  ${BOLD}ntfy.sh topic:${NC}  ${ntfy_topic}"
echo -e "  ${BOLD}Subscribe:${NC}      https://ntfy.sh/${ntfy_topic}"
echo -e "  ${BOLD}TTS enabled:${NC}    ${enable_tts}"
echo -e "  ${BOLD}Install path:${NC}   ${INSTALL_DIR}"
echo ""
echo "  To receive push notifications, subscribe to your topic:"
echo "    - Web:     https://ntfy.sh/${ntfy_topic}"
echo "    - iOS/Android: Install ntfy app, subscribe to '${ntfy_topic}'"
echo ""
if [[ "$enable_tts" == true ]]; then
    echo "  TTS will play audio notifications when Claude Code completes tasks."
    echo "  Edit ${INSTALL_DIR}/tts/config.json to adjust volume and settings."
    echo ""
fi
echo "  To uninstall: ./uninstall.sh"
