#!/usr/bin/env bash
set -euo pipefail

# Voxhook Installer
# Push notifications + TTS for Claude Code

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
if command -v xxd &>/dev/null; then
    random_suffix=$(head -c 4 /dev/urandom | xxd -p)
else
    random_suffix=$(python3 -c 'import secrets; print(secrets.token_hex(4))')
fi
default_topic="voxhook-${random_suffix}"
read -rp "$(echo -e "${CYAN}ntfy.sh topic${NC} [${default_topic}]: ")" ntfy_topic
ntfy_topic="${ntfy_topic:-$default_topic}"

# Sanitize topic: only allow alphanumeric, hyphens, underscores
if [[ ! "$ntfy_topic" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    err "Topic name must contain only letters, numbers, hyphens, and underscores."
    exit 1
fi

# ── TTS voice mode ──────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}TTS Voice Mode:${NC}"
echo "  1) GLaDOS (recommended) — sardonic AI commentary on what Claude did"
echo "  2) Custom voice          — clone any voice from a reference WAV (Chatterbox)"
echo "  3) None                  — push notifications only"
read -rp "$(echo -e "${CYAN}Choice${NC} [1]: ")" tts_choice
tts_choice="${tts_choice:-1}"

enable_tts=false
tts_engine=""
use_dynamic=false
template_file=""
voice_path=""

case "$tts_choice" in
    1)
        # ── GLaDOS mode ─────────────────────────────────────────────────
        enable_tts=true
        tts_engine="piper"
        use_dynamic=true
        template_file="${SOURCE_DIR}/templates/glados.json"

        # Check that the ONNX model exists in the repo
        if [[ ! -f "${SOURCE_DIR}/models/glados/glados_piper_medium.onnx" ]]; then
            err "GLaDOS model not found at models/glados/glados_piper_medium.onnx"
            err "Make sure you cloned the repo with the model files."
            exit 1
        fi
        ok "GLaDOS mode selected."
        ;;
    2)
        # ── Custom voice (Chatterbox) ───────────────────────────────────
        enable_tts=true
        tts_engine="chatterbox"
        use_dynamic=false

        echo ""
        echo -e "${BOLD}Custom Voice Setup${NC}"
        echo "  Requires a reference .wav file (5-30 seconds of clear speech)."
        echo ""
        read -rp "$(echo -e "${CYAN}Path to reference voice WAV${NC}: ")" voice_path

        voice_path="${voice_path/#\~/$HOME}"
        if [[ -z "$voice_path" || ! -f "$voice_path" ]]; then
            err "File not found: ${voice_path:-<empty>}"
            read -rp "Continue without TTS? [Y/n] " cont
            if [[ "$cont" == "n" || "$cont" == "N" ]]; then
                exit 1
            fi
            enable_tts=false
        else
            ok "Voice file found: ${voice_path}"
        fi

        # Template selection (only for Chatterbox)
        if [[ "$enable_tts" == true ]]; then
            echo ""
            echo -e "${BOLD}Message template preset:${NC}"
            echo "  1) default         - Neutral professional tone"
            echo "  2) abathur         - Evolutionary/clinical Abathur style"
            echo "  3) glados          - Sardonic GLaDOS tone"
            echo "  4) reptilian-brain - Primal urgency"
            echo "  5) custom          - Provide your own JSON file"
            read -rp "$(echo -e "${CYAN}Choice${NC} [1]: ")" template_choice
            template_choice="${template_choice:-1}"

            case "$template_choice" in
                2) template_file="${SOURCE_DIR}/templates/abathur.json" ;;
                3) template_file="${SOURCE_DIR}/templates/glados.json" ;;
                4) template_file="${SOURCE_DIR}/templates/reptilian-brain.json" ;;
                5)
                    read -rp "Path to custom templates JSON: " custom_template
                    custom_template="${custom_template/#\~/$HOME}"
                    if [[ -f "$custom_template" ]]; then
                        template_file="$custom_template"
                    else
                        warn "File not found, using default template."
                        template_file="${SOURCE_DIR}/templates/default.json"
                    fi
                    ;;
                *) template_file="${SOURCE_DIR}/templates/default.json" ;;
            esac
        fi
        ;;
    3)
        # ── No TTS ──────────────────────────────────────────────────────
        ok "Push notifications only."
        ;;
    *)
        err "Invalid choice: ${tts_choice}"
        exit 1
        ;;
esac

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

# Copy selected template (remove first — source tts/ may contain a symlink)
if [[ "$enable_tts" == true && -n "$template_file" ]]; then
    rm -f "$INSTALL_DIR/tts/templates.json"
    cp "$template_file" "$INSTALL_DIR/tts/templates.json"
fi

# Copy reference voice (Chatterbox only)
if [[ "$enable_tts" == true && -n "$voice_path" && -f "$voice_path" ]]; then
    mkdir -p "$INSTALL_DIR/tts/reference"
    cp "$voice_path" "$INSTALL_DIR/tts/reference/voice.wav"
    ok "Voice file copied."
fi

# Copy GLaDOS model (Piper mode)
if [[ "$tts_engine" == "piper" ]]; then
    mkdir -p "$INSTALL_DIR/tts/models/glados"
    cp "${SOURCE_DIR}/models/glados/glados_piper_medium.onnx" "$INSTALL_DIR/tts/models/glados/"
    cp "${SOURCE_DIR}/models/glados/glados_piper_medium.onnx.json" "$INSTALL_DIR/tts/models/glados/"
    ok "GLaDOS model installed."
fi

# Create cache directory
mkdir -p "$INSTALL_DIR/tts/cache"

# Write config for the chosen mode
if [[ "$enable_tts" == true ]]; then
    if [[ "$tts_engine" == "piper" ]]; then
        cat > "$INSTALL_DIR/tts/config.json" << 'EOF'
{
  "volume": 0.6,
  "playback_speed": 1.0,
  "tts_engine": "piper",
  "piper_model": "models/glados/glados_piper_medium.onnx",
  "dynamic_tts": true,
  "enabled": true,
  "sound_enabled": true,
  "ntfy_enabled": true,
  "suppress_delegate_mode": true
}
EOF
    else
        cat > "$INSTALL_DIR/tts/config.json" << 'EOF'
{
  "volume": 0.6,
  "playback_speed": 1.0,
  "tts_engine": "chatterbox",
  "dynamic_tts": false,
  "enabled": true,
  "sound_enabled": true,
  "ntfy_enabled": true,
  "suppress_delegate_mode": true
}
EOF
    fi
    ok "Config written."
fi

ok "Files installed."

# ── Patch settings.json ──────────────────────────────────────────────────────
info "Configuring Claude Code hooks..."

# Use inline Python for safe JSON manipulation
VOXHOOK_TOPIC="$ntfy_topic" VOXHOOK_TTS="$enable_tts" python3 << 'PYEOF'
import json
import os
import sys
from pathlib import Path

ntfy_topic = os.environ["VOXHOOK_TOPIC"]
enable_tts = os.environ.get("VOXHOOK_TTS", "false") == "true"

settings_path = Path(os.path.expanduser("~/.claude/settings.json"))

try:
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
    else:
        settings = {}
except (json.JSONDecodeError, OSError) as e:
    print(f"[voxhook] WARNING: Could not parse settings.json: {e}", file=sys.stderr)
    print("[voxhook] Creating backup and starting fresh.", file=sys.stderr)
    if settings_path.exists():
        settings_path.rename(settings_path.with_suffix(".json.bak"))
    settings = {}

hooks = settings.setdefault("hooks", {})

def has_voxhook_path(entries, path_fragment):
    """Check if a specific voxhook path exists in hook entries."""
    for entry in entries:
        for h in entry.get("hooks", []):
            if path_fragment in h.get("command", ""):
                return True
    return False

def remove_voxhook_entries(entries):
    """Remove all voxhook entries from a hook list."""
    return [e for e in entries if not any("voxhook" in h.get("command", "") for h in e.get("hooks", []))]

# Clean existing voxhook entries first, then re-add (idempotent reinstall)
stop_hooks = hooks.setdefault("Stop", [])
stop_hooks[:] = remove_voxhook_entries(stop_hooks)

# Push notification hook (Stop) - always added
stop_hooks.append({
    "hooks": [{
        "type": "command",
        "command": f"nohup uv run ~/.claude/hooks/voxhook/notify/handler.py --topic={ntfy_topic} &"
    }]
})

if enable_tts:
    # TTS hook (Stop)
    stop_hooks.append({
        "hooks": [{
            "type": "command",
            "command": f"uv run ~/.claude/hooks/voxhook/tts/handler.py --ntfy-topic={ntfy_topic}",
            "timeout": 10
        }]
    })

    # TTS hook (Notification)
    notif_hooks = hooks.setdefault("Notification", [])
    notif_hooks[:] = remove_voxhook_entries(notif_hooks)
    notif_hooks.append({
        "hooks": [{
            "type": "command",
            "command": "uv run ~/.claude/hooks/voxhook/tts/handler.py",
            "timeout": 10
        }]
    })

settings_path.write_text(json.dumps(settings, indent=2) + "\n")
print("[voxhook] settings.json updated.")
PYEOF

ok "Hooks configured."

# ── Pre-generation + smoke test ──────────────────────────────────────────────
if [[ "$enable_tts" == true ]]; then
    if [[ "$tts_engine" == "piper" ]]; then
        # Piper is fast (~5s total), always pre-generate
        echo ""
        info "Pre-generating TTS audio cache (Piper — this is quick)..."
        if uv run --python 3.11 "$INSTALL_DIR/tts/generate_piper.py" --pre-generate; then
            ok "Audio cache ready."

            # Smoke test: play a random cached WAV
            sample_wav=$(find "$INSTALL_DIR/tts/cache" -name '*.wav' -type f 2>/dev/null | head -1)
            if [[ -n "$sample_wav" ]]; then
                echo ""
                info "Playing smoke test..."
                afplay -v 0.6 "$sample_wav" &
                wait $!
                ok "Audio working!"
            fi
        else
            warn "Pre-generation had errors. TTS will generate on-demand instead."
        fi
    else
        # Chatterbox: optional, takes minutes
        echo ""
        echo -e "${BOLD}Pre-generate TTS audio cache?${NC}"
        echo "  This generates WAV files for all template messages upfront."
        echo "  Takes a few minutes but ensures instant playback from the start."
        read -rp "$(echo -e "${CYAN}Pre-generate?${NC} [y/N]: ")" pregen
        if [[ "$pregen" == "y" || "$pregen" == "Y" ]]; then
            info "Starting pre-generation (this will take a while)..."
            uv run --python 3.11 "$INSTALL_DIR/tts/generate.py" --pre-generate || {
                warn "Pre-generation had errors. TTS will generate on-demand instead."
            }
        fi
    fi
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}Voxhook installed successfully!${NC}"
echo ""
echo -e "  ${BOLD}ntfy.sh topic:${NC}  ${ntfy_topic}"
echo -e "  ${BOLD}Subscribe:${NC}      https://ntfy.sh/${ntfy_topic}"
if [[ "$enable_tts" == true ]]; then
    echo -e "  ${BOLD}TTS engine:${NC}     ${tts_engine}"
    if [[ "$use_dynamic" == true ]]; then
        echo -e "  ${BOLD}Dynamic TTS:${NC}    enabled (GLaDOS commentary via Agent SDK)"
    fi
fi
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
