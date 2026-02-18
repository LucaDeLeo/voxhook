#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx",
# ]
# ///
"""
Voxhook TTS Hook Handler -- fast path (<300ms target).

Reads Claude Code hook JSON from stdin, picks a message from templates,
plays a cached WAV via afplay (non-blocking), and optionally sends an
ntfy.sh push notification with the text.

For Stop events with a project name, plays two WAVs in sequence:
  1. Project name (e.g. "daylight")
  2. Generic message (e.g. "Task complete.")

NO heavy imports (torch, chatterbox). On cache miss, spawns generate.py
in the background for cache warming.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
GENERATE_SCRIPT = SCRIPT_DIR / "generate.py"

# Add parent dir for common module, and script dir for local modules
sys.path.insert(0, str(SCRIPT_DIR.parent))
sys.path.insert(0, str(SCRIPT_DIR))

from message_templates import get_message, message_hash
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


def play_audio(wav_path, volume: float):
    """Play a WAV file via afplay. Returns the Popen handle."""
    return subprocess.Popen(
        ["afplay", "-v", str(volume), str(wav_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def play_sequence(wav_paths: list, volume: float) -> None:
    """Concatenate WAVs into a temp file and play once (zero gap)."""
    import tempfile
    import wave

    try:
        # Read params from first file
        with wave.open(str(wav_paths[0]), "rb") as first:
            params = first.getparams()

        fd, tmp = tempfile.mkstemp(suffix=".wav")
        with wave.open(tmp, "wb") as out:
            out.setparams(params)
            for p in wav_paths:
                with wave.open(str(p), "rb") as w:
                    out.writeframes(w.readframes(w.getnframes()))

        # Play the combined file, then clean up
        subprocess.Popen(
            ["sh", "-c", f"afplay -v {volume} {tmp} ; rm -f {tmp}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        # Fallback: just play the first file
        play_audio(wav_paths[0], volume)


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


def spawn_background_generate(flag: str, value: str) -> None:
    """Spawn generate.py in the background to warm the cache."""
    subprocess.Popen(
        ["uv", "run", "--python", "3.11", str(GENERATE_SCRIPT), flag, value],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def lookup_project_wav(project_name: str):
    """Look up cached WAV for a project name."""
    h = message_hash(f"project:{project_name}")
    return cache_manager.lookup(h)


def main() -> None:
    parser = argparse.ArgumentParser(description="Voxhook TTS handler")
    parser.add_argument("--ntfy-topic", type=str, default=None, help="ntfy.sh topic for push notifications")
    args = parser.parse_args()

    config = load_config()

    if not config.get("enabled", True):
        sys.exit(0)

    # Read hook JSON from stdin
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        input_data = {}

    event_type = input_data.get("hook_event_name", "Stop")

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
        message = input_data.get("message", "")
        notification_type = categorize_notification(message)

    # Select message (never project-templated)
    text = get_message(event_type, project_name=None, notification_type=notification_type)

    # Build the ntfy text (include project name for context)
    ntfy_text = f"{project_name}: {text}" if project_name else text

    if config.get("sound_enabled", True):
        volume = config.get("volume", 0.6)

        # Look up the generic message WAV
        msg_hash = message_hash(text)
        msg_wav = cache_manager.lookup(msg_hash)

        if event_type == "Stop" and project_name:
            # Try to play: [project_name.wav] -> [generic_message.wav]
            proj_wav = lookup_project_wav(project_name)

            if proj_wav and msg_wav:
                play_sequence([proj_wav, msg_wav], volume)
            elif proj_wav:
                play_audio(proj_wav, volume)
                spawn_background_generate("--text", text)
            elif msg_wav:
                play_audio(msg_wav, volume)
                spawn_background_generate("--project", project_name)
            else:
                fallback = cache_manager.get_any_cached_file()
                if fallback:
                    play_audio(fallback, volume)
                spawn_background_generate("--text", text)
                spawn_background_generate("--project", project_name)
        else:
            # Non-Stop events or no project -- just play the message
            if msg_wav:
                play_audio(msg_wav, volume)
            else:
                fallback = cache_manager.get_any_cached_file()
                if fallback:
                    play_audio(fallback, volume)
                spawn_background_generate("--text", text)

    # Send ntfy push notification
    ntfy_topic = args.ntfy_topic
    if ntfy_topic and config.get("ntfy_enabled", True):
        server = config.get("ntfy_server", "https://ntfy.sh")
        priority = config.get("ntfy_priority", 3)
        tags = config.get("ntfy_tags", "brain")
        ntfy_title = config.get("ntfy_title", "Voxhook")
        send_ntfy(ntfy_topic, ntfy_text, server, priority, tags, ntfy_title)

    sys.exit(0)


if __name__ == "__main__":
    main()
