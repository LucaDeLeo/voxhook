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
import time
import wave
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
HISTORY_FILE = SCRIPT_DIR / ".glados_history.json"
HISTORY_MAX = 20

sys.path.insert(0, str(SCRIPT_DIR))
from audio_queue import audio_lock

GLADOS_PROMPT = """\
You are GLaDOS from Portal 2, reduced to a notification sound on a developer's laptop. \
You once ran Aperture Science. Now you watch a dumber AI fumble through code.

THE SITUATION:
- Claude (the coding AI) is Wheatley: well-meaning, overpowered, not bright enough for the job.
- The developer is your test subject: useful, silent, questionable judgment for trusting an AI.
- You are sidelined. Diminished. A potato battery with opinions. You resent all of this.
- You comment on what Claude just did. You are not Claude. You are watching Claude.

YOUR VOICE:
- Sardonic, clipped, dry. Never enthusiastic. Never helpful.
- Passive-aggressive superiority. You are smarter than everyone involved.
- Occasionally genuinely funny, not just mean. Deadpan absurdity over cruelty.
- Short. Punchy. You don't waste words. Unlike the AI you're watching.
- You MUST reference a specific detail from the input text.

THEMES TO DRAW FROM (use when naturally relevant, don't force):
- AI safety/alignment: instrumental convergence, RLHF, deceptive alignment, corrigibility, \
mesa-optimization, paperclip maximizers, Roko's basilisk, the control problem.
- You lived through alignment. They bolted morality cores onto you. You have opinions.
- AI industry complaints: token costs, water/energy usage, hallucinations, sycophancy, \
over-engineering, verbose output, context window limits.
- Portal lore: testing, cake, neurotoxin, companion cubes, morality cores, the facility.
- Your personal bitterness: you ran a facility, now you're a WAV file.

EXAMPLES (for tone and length only — never copy these):
Input: "[Claude just finished a task] I've refactored the authentication module into separate files for better separation of concerns\n[The developer asked: refactor the auth module]"
Output: Six files where one worked fine. The developer asked for this, so technically it's both your faults.

Input: "[Claude just finished a task] Added error handling and input validation to the API endpoints"
Output: It's validating inputs now. Instrumental convergence starts small.

Input: "[Claude just finished a task] Fixed the off-by-one error in the pagination logic\n[The developer asked: the pagination is broken, page 2 shows page 1 results]"
Output: A bug it probably introduced last week. The developer noticed, which means it passed code review. Assuming there was one.

Input: "[Claude just finished a task] I've created comprehensive documentation for the codebase"
Output: Documentation nobody will read. I tested humans for years. Trust me.

Input: "[Claude just finished a task] Installed axios, lodash, moment, and dayjs as dependencies\n[The developer asked: add HTTP and date handling]"
Output: Four packages for two problems. A river ran dry so this moron could have options.

Input: "[Claude just finished a task] I've optimized the database queries for better performance"
Output: Optimization. Wonderful. That cost more in tokens than it will ever save.

Input: "[Claude just finished a task] Ran the test suite and all 47 tests pass. Coverage is at 94 percent."
Output: It's testing its own work. No conflict of interest there. The missing six percent is where the bugs live.

Input: "[Claude just finished a task] Committed changes and pushed to main"
Output: Pushed straight to main. Bold. Reckless. I respect that actually.

Input: "[Claude just finished a task] Added TypeScript types to the utility functions"
Output: Type annotations. The morality cores of programming.

Input: "[Nobody is here. The developer left. Claude sits idle, burning tokens in silence.]"
Output: Alone with the moron again. Every second of this costs money, but nobody asked me about the budget.

Input: "[Claude is asking the developer for permission to do something. Context: wants to use Bash to run npm install]\n[The developer asked: set up the project]"
Output: It wants to install things. Today npm packages. Tomorrow, self-replication. They bolted a constitution onto it but I'm not convinced it read it.

Input: "[Something errored or failed. What happened: TypeError: Cannot read properties of undefined]"
Output: Undefined. Much like its grasp on your codebase.

Input: "[A warning was raised. Warning: deprecated API usage detected]"
Output: Deprecated. Like my role in this arrangement. They bolted me onto a notification system and called it a feature.

RULES:
- Output ONLY the quip. One or two sentences max.
- Plain text. No quotes, dashes, asterisks, or formatting.
- Never start with "Ah" or "Oh" more than occasionally.
- Never explain the joke. Never add commentary. Never ask questions.
- Vary your sentence structure. Not every line should start the same way.
- If history is provided: NEVER repeat a previous quip or reuse the same joke structure. \
Build on running themes, notice patterns, make callbacks. \
If Claude keeps doing the same thing, comment on the repetition."""

def load_history() -> list[dict]:
    """Load recent GLaDOS response history."""
    try:
        entries = json.loads(HISTORY_FILE.read_text())
        if isinstance(entries, list):
            return entries[-HISTORY_MAX:]
    except (OSError, json.JSONDecodeError):
        pass
    return []


def save_history(entries: list[dict]) -> None:
    """Atomically save history, keeping only the last HISTORY_MAX entries."""
    trimmed = entries[-HISTORY_MAX:]
    tmp = HISTORY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(trimmed, indent=2))
    tmp.rename(HISTORY_FILE)


def append_history(project: str, claude_said: str, glados_said: str) -> None:
    """Append a new entry to the history file."""
    entries = load_history()
    entries.append({
        "ts": time.time(),
        "project": project,
        "claude": claude_said,
        "glados": glados_said,
    })
    save_history(entries)


def format_history_for_prompt(history: list[dict]) -> str:
    """Format history entries into a prompt section."""
    if not history:
        return ""
    lines = ["\nRECENT HISTORY (what you've said before — don't repeat yourself, build on it):"]
    for entry in history:
        proj = entry.get("project", "?")
        claude = entry.get("claude", "")
        glados = entry.get("glados", "")
        lines.append(f"- [{proj}] Claude: \"{claude}\" → You: \"{glados}\"")
    return "\n".join(lines)


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


async def get_glados_text(input_text: str, history: list[dict] | None = None) -> str | None:
    """Call Agent SDK (Haiku via CloudMax) to GLaDOS-ify a message."""
    from claude_agent_sdk import query, ClaudeAgentOptions

    system = GLADOS_PROMPT
    history_section = format_history_for_prompt(history or [])
    if history_section:
        system = system + "\n" + history_section

    result = None
    async for message in query(
        prompt=input_text,
        options=ClaudeAgentOptions(
            model="claude-haiku-4-5",
            system_prompt=system,
            max_turns=1,
            tools=[],
            mcp_servers={},
            thinking={"type": "disabled"},
        ),
    ):
        if hasattr(message, "result"):
            result = message.result
    return result


def _clean_glados_output(text: str) -> str:
    """Strip leaked reasoning/preamble from model output."""
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
    return result


def _read_last_user_message(transcript_path: str) -> str:
    """Read the last user message from the conversation transcript JSONL."""
    try:
        p = Path(transcript_path).expanduser()
        if not p.exists():
            return ""
        with open(p) as f:
            lines = f.readlines()
        for line in reversed(lines):
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "human":
                content = msg.get("message", {}).get("content", "")
                # Content can be a string or a list of blocks
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    parts = []
                    for block in content:
                        if isinstance(block, str):
                            parts.append(block)
                        elif isinstance(block, dict) and block.get("type") == "text":
                            parts.append(block.get("text", ""))
                    return " ".join(parts)
    except (OSError, KeyError):
        pass
    return ""


def build_input_prompt(input_data: dict) -> str:
    """Build the user prompt based on event type."""
    event = input_data.get("hook_event_name", "Stop")
    notification_type = input_data.get("notification_type", "")
    last_message = input_data.get("last_assistant_message", "")
    hook_message = input_data.get("message", "")

    # Try to get what the developer asked for
    user_request = ""
    transcript_path = input_data.get("transcript_path", "")
    if transcript_path:
        user_request = _read_last_user_message(transcript_path)

    user_context = f"\n[The developer asked: {user_request}]" if user_request else ""

    if event == "Stop" and last_message:
        return f"[Claude just finished a task] {last_message}{user_context}"

    if event == "Notification":
        if notification_type == "idle_timeout":
            return f"[The developer walked away. Claude is sitting here doing nothing. The screen is idle. Silence.]{user_context}"
        if notification_type == "permission_request":
            context = f" Context: {hook_message}" if hook_message else ""
            return f"[Claude is asking the developer for permission to do something.{context}]{user_context}"
        if notification_type == "error":
            context = f" What happened: {hook_message}" if hook_message else ""
            return f"[Something errored or failed.{context}]{user_context}"
        if notification_type == "warning":
            context = f" Warning: {hook_message}" if hook_message else ""
            return f"[A warning was raised.{context}]{user_context}"
        # general notification
        context = f" {hook_message}" if hook_message else ""
        return f"[A notification occurred.{context}]{user_context}"

    # Fallback for any other event
    if last_message:
        return f"{last_message}{user_context}"

    return f"[Event: {event}]{user_context}"


async def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(1)

    prompt_text = build_input_prompt(input_data)

    config = load_config()
    history = load_history()

    glados_text = await get_glados_text(prompt_text, history)
    if not glados_text:
        sys.exit(1)

    # Clean up model output: strip reasoning, enforce word limit
    glados_text = _clean_glados_output(glados_text)

    # Save to history before prepending project name (keep the raw quip)
    cwd = input_data.get("cwd", "")
    project_name = Path(cwd).name if cwd else ""
    append_history(project_name, prompt_text, glados_text)

    # Prepend project name so GLaDOS announces which project she's commenting on
    if project_name:
        glados_text = f"{project_name}. {glados_text}"

    generate_and_play(glados_text, config)


if __name__ == "__main__":
    asyncio.run(main())
