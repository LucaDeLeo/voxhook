#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "claude-agent-sdk",
#     "piper-tts",
#     "numpy",
# ]
# ///
"""
Dynamic GLaDOS TTS via Agent SDK + Piper.

Reads hook JSON from stdin, uses Agent SDK (Haiku via CloudMax) to
generate a GLaDOS-style one-liner about what Claude actually did,
then synthesises + plays the WAV via Piper.

Designed to run as a fire-and-forget background process spawned by
handler.py — the cached template phrase has already played, so
failure here is silent and harmless.
"""

import asyncio
import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"

sys.path.insert(0, str(SCRIPT_DIR))
from audio_queue import audio_lock

GLADOS_PROMPT = """\
You are GLaDOS from Portal. Respond with exactly one short sardonic quip. \
Max 12 words. Mention one detail from the input. \
Plain text only. No quotes, no dashes, no asterisks. \
Do not explain, reason, ask questions, or add commentary. Output the quip and nothing else."""

# Cache the Piper voice globally within this process
_voice = None


def load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _get_model_path(config: dict) -> Path:
    model_path = config.get("piper_model", "")
    if model_path:
        p = Path(model_path)
        if p.exists():
            return p
        p = SCRIPT_DIR / model_path
        if p.exists():
            return p
    default = SCRIPT_DIR.parent.parent / "models" / "glados" / "glados_piper_medium.onnx"
    if default.exists():
        return default
    default = SCRIPT_DIR / "models" / "glados" / "glados_piper_medium.onnx"
    if default.exists():
        return default
    raise FileNotFoundError("Piper model not found. Set 'piper_model' in config.json")


def _get_voice(config: dict):
    global _voice
    if _voice is not None:
        return _voice
    from piper import PiperVoice

    model_path = _get_model_path(config)
    _voice = PiperVoice.load(str(model_path))
    return _voice


def generate_and_play(text: str, config: dict) -> None:
    """Synthesise text with Piper and play via afplay."""
    voice = _get_voice(config)

    chunks = list(voice.synthesize(text))
    audio = np.concatenate([c.audio_float_array for c in chunks])
    audio_int16 = (audio * 32767).astype(np.int16)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
        with wave.open(tmp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(voice.config.sample_rate)
            wf.writeframes(audio_int16.tobytes())

    try:
        volume = config.get("volume", 0.6)
        speed = config.get("playback_speed", 1.0)
        cmd = ["afplay", "-v", str(volume)]
        if speed != 1.0:
            cmd += ["-r", str(speed)]
        cmd.append(tmp_path)
        with audio_lock():
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def get_glados_text(input_text: str) -> str | None:
    """Call Agent SDK (Haiku via CloudMax) to GLaDOS-ify a message."""
    from claude_agent_sdk import query, ClaudeAgentOptions

    result = None
    async for message in query(
        prompt=input_text,
        options=ClaudeAgentOptions(
            model="claude-haiku-4-5",
            system_prompt=GLADOS_PROMPT,
            max_turns=1,
            tools=[],
            thinking={"type": "disabled"},
        ),
    ):
        if hasattr(message, "result"):
            result = message.result
    return result


def _clean_glados_output(text: str) -> str:
    """Strip leaked reasoning/preamble and enforce word limit."""
    # Take only the last non-empty line (reasoning tends to come first)
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    # Filter out lines that look like reasoning or preamble
    filtered = [
        l for l in lines
        if not l.lower().startswith(("here", "i ", "i'", "let me", "sure", "okay"))
        and ":" not in l[:20]  # skip "Here's a quip: ..." style lines
    ]
    result = (filtered[-1] if filtered else lines[-1]) if lines else text.strip()
    # Strip wrapping quotes
    result = result.strip('"').strip("'")
    # Hard cap at 15 words — truncate gracefully at sentence boundary or just chop
    words = result.split()
    if len(words) > 15:
        result = " ".join(words[:15])
        # Try to end at a natural point
        if "." in result:
            result = result[:result.rindex(".") + 1]
    return result


async def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(1)

    last_message = input_data.get("last_assistant_message", "")
    if not last_message:
        sys.exit(0)

    # Truncate to keep the Agent SDK call fast
    truncated = last_message[:200]
    if len(last_message) > 200:
        truncated += "..."

    config = load_config()

    glados_text = await get_glados_text(truncated)
    if not glados_text:
        sys.exit(1)

    # Clean up model output: strip reasoning, enforce word limit
    glados_text = _clean_glados_output(glados_text)

    # Prepend project name so GLaDOS announces which project she's commenting on
    cwd = input_data.get("cwd", "")
    project_name = Path(cwd).name if cwd else ""
    if project_name:
        glados_text = f"{project_name}. {glados_text}"

    generate_and_play(glados_text, config)


if __name__ == "__main__":
    asyncio.run(main())
