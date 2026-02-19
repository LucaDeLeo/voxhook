#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "piper-tts",
#     "numpy",
# ]
# ///
"""
Voxhook TTS Generator -- Piper (pre-trained ONNX voices).

Lightweight alternative to generate.py (Chatterbox). No torch needed.
Used for voices that have dedicated Piper ONNX models (e.g. GLaDOS).

Usage:
  uv run --python 3.11 generate_piper.py --pre-generate
  uv run --python 3.11 generate_piper.py --text "Hello world"
  uv run --python 3.11 generate_piper.py --project myproject
"""

import argparse
import json
import sys
import wave
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).parent
CACHE_DIR = SCRIPT_DIR / "cache"
CONFIG_FILE = SCRIPT_DIR / "config.json"

# Global model cache
_voice = None


def load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _get_model_path() -> Path:
    config = load_config()
    model_path = config.get("piper_model", "")
    if model_path:
        p = Path(model_path)
        if p.exists():
            return p
        # Try relative to script dir (installed location)
        p = SCRIPT_DIR / model_path
        if p.exists():
            return p
    # Default: look in models/glados/ relative to project root
    default = SCRIPT_DIR.parent.parent / "models" / "glados" / "glados_piper_medium.onnx"
    if default.exists():
        return default
    # Also check relative to script dir
    default = SCRIPT_DIR / "models" / "glados" / "glados_piper_medium.onnx"
    if default.exists():
        return default
    raise FileNotFoundError(
        f"Piper model not found. Set 'piper_model' in config.json"
    )


def _get_voice():
    global _voice
    if _voice is not None:
        return _voice

    from piper import PiperVoice

    model_path = _get_model_path()
    print(f"[voxhook-tts] Loading Piper model: {model_path}", file=sys.stderr)
    _voice = PiperVoice.load(str(model_path))
    return _voice


def generate_audio(text: str, output_path: Path) -> Path:
    voice = _get_voice()

    print(f"[voxhook-tts] Generating: {text!r}", file=sys.stderr)
    chunks = list(voice.synthesize(text))
    audio = np.concatenate([c.audio_float_array for c in chunks])
    audio_int16 = (audio * 32767).astype(np.int16)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(voice.config.sample_rate)
        wf.writeframes(audio_int16.tobytes())

    print(f"[voxhook-tts] Saved: {output_path}", file=sys.stderr)
    return output_path


def pre_generate() -> None:
    sys.path.insert(0, str(SCRIPT_DIR))
    from message_templates import get_all_static_messages, message_hash
    import cache_manager

    messages = get_all_static_messages()
    total = len(messages)
    print(f"[voxhook-tts] Pre-generating {total} phrases (Piper)...", file=sys.stderr)

    generated = 0
    skipped = 0
    failed = 0

    for i, text in enumerate(messages, 1):
        h = message_hash(text)
        if cache_manager.lookup(h) is not None:
            print(f"[voxhook-tts] ({i}/{total}) Cached: {text!r}", file=sys.stderr)
            skipped += 1
            continue

        try:
            print(f"[voxhook-tts] ({i}/{total}) Generating: {text!r}", file=sys.stderr)
            wav_path = CACHE_DIR / f"{h}.wav"
            generate_audio(text, wav_path)
            cache_manager.store(h, text, wav_path)
            print(f"[voxhook-tts] ({i}/{total}) Done: {text!r}", file=sys.stderr)
            generated += 1
        except Exception as e:
            print(f"[voxhook-tts] ({i}/{total}) FAILED: {text!r}: {e}", file=sys.stderr)
            failed += 1

    stats = cache_manager.get_cache_stats()
    print(
        f"[voxhook-tts] Pre-generation complete. Generated: {generated}, "
        f"skipped: {skipped}, failed: {failed}. "
        f"Cache: {stats['valid']} valid entries.",
        file=sys.stderr,
    )


def generate_single(text: str) -> None:
    sys.path.insert(0, str(SCRIPT_DIR))
    from message_templates import message_hash
    import cache_manager

    h = message_hash(text)
    existing = cache_manager.lookup(h)
    if existing:
        print(f"[voxhook-tts] Already cached: {existing}", file=sys.stderr)
        return

    wav_path = CACHE_DIR / f"{h}.wav"
    generate_audio(text, wav_path)
    cache_manager.store(h, text, wav_path)


def generate_project(name: str) -> None:
    sys.path.insert(0, str(SCRIPT_DIR))
    from message_templates import message_hash
    import cache_manager

    key = f"project:{name}"
    h = message_hash(key)

    existing = cache_manager.lookup(h)
    if existing:
        print(f"[voxhook-tts] Already cached: {name} -> {existing}", file=sys.stderr)
        return

    wav_path = CACHE_DIR / f"proj_{h}.wav"
    generate_audio(name, wav_path)
    cache_manager.store(h, key, wav_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Voxhook TTS generator (Piper)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pre-generate", action="store_true", help="Generate all static template messages")
    group.add_argument("--text", type=str, help="Generate a single phrase")
    group.add_argument("--project", type=str, help="Generate just a project name as audio")

    args = parser.parse_args()

    if args.pre_generate:
        pre_generate()
    elif args.text:
        generate_single(args.text)
    elif args.project:
        generate_project(args.project)


if __name__ == "__main__":
    main()
