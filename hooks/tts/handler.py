#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx",
#     "anthropic",
#     "piper-tts",
#     "numpy",
# ]
# ///
"""
Voxhook TTS Hook Handler.

Reads Claude Code hook JSON from stdin, generates or picks a message,
plays WAV via afplay, and optionally sends an ntfy.sh push notification.

Dynamic mode (tts_engine=piper): calls Haiku to generate a GLaDOS-style
one-liner from last_assistant_message, then Piper TTS for instant WAV.
Falls back to pre-generated cache on failure.

For Stop events with a project name, plays two WAVs in sequence:
  1. Project name (e.g. "daylight")
  2. Message WAV
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
MUTE_FILE = SCRIPT_DIR.parent / ".muted"
CONFIG_FILE = SCRIPT_DIR / "config.json"
GENERATE_SCRIPT = SCRIPT_DIR / "generate.py"
GENERATE_PIPER_SCRIPT = SCRIPT_DIR / "generate_piper.py"
GLADOSIFY_SCRIPT = SCRIPT_DIR / "gladosify.py"
IDLE_COOLDOWN_FILE = SCRIPT_DIR / ".idle_cooldown"
IDLE_COOLDOWN_SECONDS = 300  # 5 minutes

# Add parent dir for common module, and script dir for local modules
sys.path.insert(0, str(SCRIPT_DIR.parent))
sys.path.insert(0, str(SCRIPT_DIR))

from common.awareness import detect_awareness, AwarenessTier
from message_templates import get_message, message_hash
from audio_queue import audio_lock
import cache_manager


def load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {
            "volume": 0.6,
            "enabled": True,
            "sound_enabled": True,
            "ntfy_enabled": True,
            "suppress_delegate_mode": True,
        }


def extract_project_name(cwd: str) -> str:
    """Extract project name from the working directory path."""
    if not cwd:
        return ""
    return Path(cwd).name


def categorize_notification(message: str) -> str:
    """Categorize a notification message into a template sub-type."""
    if not message:
        return "general"
    lower = message.lower()
    if "permission" in lower and "use" in lower:
        return "permission_request"
    if "waiting for your input" in lower or "waiting for input" in lower:
        return "idle_timeout"
    if any(k in lower for k in ("error", "failed", "exception", "critical")):
        return "error"
    if any(k in lower for k in ("warning", "warn", "caution")):
        return "warning"
    return "general"


def play_audio(wav_path, volume: float, speed: float = 1.0):
    """Play a WAV file via afplay, serialized by cross-process lock."""
    cmd = ["afplay", "-v", str(volume)]
    if speed != 1.0:
        cmd += ["-r", str(speed)]
    cmd.append(str(wav_path))
    with audio_lock():
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def play_sequence(wav_paths: list, volume: float, speed: float = 1.0) -> None:
    """Play WAVs back-to-back, serialized by cross-process lock.

    Holds the lock for the entire sequence so no other process can
    interleave audio between the project name and message WAVs.
    """
    cmd_base = ["afplay", "-v", str(volume)]
    if speed != 1.0:
        cmd_base += ["-r", str(speed)]
    with audio_lock():
        for wav_path in wav_paths:
            subprocess.run(
                cmd_base + [str(wav_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


def send_ntfy(topic: str, text: str, server: str, priority: int, tags: str, title: str) -> None:
    """Send ntfy.sh push notification in a fire-and-forget subprocess."""
    import json as _json
    # Pass all parameters as a JSON blob via stdin to avoid shell/code injection
    payload = _json.dumps({
        "url": f"{server.rstrip('/')}/{topic}",
        "text": text,
        "title": title,
        "priority": str(priority),
        "tags": tags,
    })
    code = (
        "import sys, json, httpx; "
        "d = json.load(sys.stdin); "
        "httpx.post(d['url'], content=d['text'].encode('utf-8'), "
        "headers={'Title': d['title'], 'Priority': d['priority'], 'Tags': d['tags']})"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    proc.stdin.write(payload.encode())
    proc.stdin.close()


def _get_generate_script(config: dict) -> Path:
    """Return the correct generator script based on tts_engine config."""
    engine = config.get("tts_engine", "chatterbox")
    if engine == "piper":
        return GENERATE_PIPER_SCRIPT
    return GENERATE_SCRIPT


def spawn_gladosify(input_data: dict) -> None:
    """Spawn gladosify.py in background to generate and play dynamic GLaDOS TTS."""
    import os

    # Agent SDK launches Claude Code CLI, which refuses to run inside
    # an existing session.  Strip the nesting-detection env var.
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    payload = json.dumps(input_data)
    proc = subprocess.Popen(
        ["uv", "run", "--python", "3.11", str(GLADOSIFY_SCRIPT)],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    proc.stdin.write(payload.encode())
    proc.stdin.close()


def spawn_background_generate(flag: str, value: str, config: dict | None = None) -> None:
    """Spawn the appropriate generator in the background to warm the cache."""
    script = _get_generate_script(config or {})
    subprocess.Popen(
        ["uv", "run", "--python", "3.11", str(script), flag, value],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def is_idle_on_cooldown() -> bool:
    """Check if idle notification is still in cooldown period."""
    try:
        last = float(IDLE_COOLDOWN_FILE.read_text().strip())
        return (time.time() - last) < IDLE_COOLDOWN_SECONDS
    except (OSError, ValueError):
        return False


def mark_idle_cooldown() -> None:
    """Record that an idle notification just fired."""
    IDLE_COOLDOWN_FILE.write_text(str(time.time()))


def lookup_project_wav(project_name: str):
    """Look up cached WAV for a project name."""
    h = message_hash(f"project:{project_name}")
    return cache_manager.lookup(h)


def main() -> None:
    parser = argparse.ArgumentParser(description="Voxhook TTS handler")
    parser.add_argument("--ntfy-topic", type=str, default=None, help="ntfy.sh topic for push notifications")
    args = parser.parse_args()

    # Global mute
    if MUTE_FILE.exists():
        sys.exit(0)

    config = load_config()

    if not config.get("enabled", True):
        sys.exit(0)

    # Read hook JSON from stdin
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        input_data = {}

    event_type = input_data.get("hook_event_name", "Stop")

    # Per-project suppress
    cwd_raw = input_data.get("cwd", "")
    if cwd_raw and (Path(cwd_raw) / ".voxhook-suppress").exists():
        sys.exit(0)

    # Suppress for delegate (agent) sessions
    if config.get("suppress_delegate_mode", True):
        session_mode = input_data.get("session_mode", "")
        permission_mode = input_data.get("permission_mode", "")
        if session_mode == "delegate" or permission_mode == "delegate":
            sys.exit(0)

    # Extract project name from cwd
    cwd = input_data.get("cwd", "")
    project_name = extract_project_name(cwd)

    # Determine notification sub-type for Notification events
    notification_type = None
    if event_type == "Notification":
        # Prefer the notification_type field from Claude Code's JSON payload
        raw_notif_type = input_data.get("notification_type", "")
        is_idle = raw_notif_type == "idle_prompt"

        # Fall back to message text parsing if field is missing
        message = input_data.get("message", "")
        notification_type = categorize_notification(message)
        if not is_idle:
            is_idle = notification_type == "idle_timeout"

        # Enforce cooldown only for idle notifications
        if is_idle:
            notification_type = "idle_timeout"  # normalize for gladosify
            if is_idle_on_cooldown():
                sys.exit(0)
            mark_idle_cooldown()

    # Awareness-based notification tiering
    tier = detect_awareness(config, project_name)
    should_tts = tier is None or tier == AwarenessTier.NEARBY
    should_push = tier is None or tier == AwarenessTier.AWAY

    # Select message (never project-templated)
    text = get_message(event_type, project_name=None, notification_type=notification_type)

    # Build the ntfy text (include project name for context)
    ntfy_text = f"{project_name}: {text}" if project_name else text

    # Dynamic TTS: spawn GLaDOS to generate a contextual quip.
    # When dynamic TTS fires, skip the template audio — gladosify handles
    # everything (including the project name) so we don't double-play.
    use_dynamic = (
        config.get("dynamic_tts", False)
        and config.get("tts_engine") == "piper"
    )

    if use_dynamic and should_tts:
        # Pass notification sub-type so gladosify can tailor its response
        if notification_type:
            input_data["notification_type"] = notification_type
        spawn_gladosify(input_data)
    elif should_tts and config.get("sound_enabled", True):
        volume = config.get("volume", 0.6)
        speed = config.get("playback_speed", 1.0)

        # Look up the generic message WAV
        msg_hash = message_hash(text)
        msg_wav = cache_manager.lookup(msg_hash)

        if project_name:
            # Try to play: [project_name.wav] -> [message.wav]
            proj_wav = lookup_project_wav(project_name)

            if proj_wav and msg_wav:
                play_sequence([proj_wav, msg_wav], volume, speed)
            elif proj_wav:
                play_audio(proj_wav, volume, speed)
                spawn_background_generate("--text", text, config)
            elif msg_wav:
                play_audio(msg_wav, volume, speed)
                spawn_background_generate("--project", project_name, config)
            else:
                fallback = cache_manager.get_any_cached_file()
                if fallback:
                    play_audio(fallback, volume, speed)
                spawn_background_generate("--text", text, config)
                spawn_background_generate("--project", project_name, config)
        else:
            # No project name -- just play the message
            if msg_wav:
                play_audio(msg_wav, volume, speed)
            else:
                fallback = cache_manager.get_any_cached_file()
                if fallback:
                    play_audio(fallback, volume, speed)
                spawn_background_generate("--text", text, config)

    # Send ntfy push notification
    ntfy_topic = args.ntfy_topic
    if ntfy_topic and should_push and config.get("ntfy_enabled", True):
        server = config.get("ntfy_server", "https://ntfy.sh")
        priority = config.get("ntfy_priority", 3)
        tags = config.get("ntfy_tags", "brain")
        ntfy_title = config.get("ntfy_title", "Voxhook")
        send_ntfy(ntfy_topic, ntfy_text, server, priority, tags, ntfy_title)

    sys.exit(0)


if __name__ == "__main__":
    main()
