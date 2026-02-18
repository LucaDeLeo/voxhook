#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "chatterbox-tts",
#     "torchaudio",
#     "torch",
#     "numpy>=1.26",
#     "setuptools<75",
# ]
# ///
"""
Voxhook TTS Generator -- Chatterbox voice cloning.

Heavy script (loads ML model). Never called directly by the hook handler
during normal operation. Used for:
  1. Pre-generating all static template messages (--pre-generate)
  2. On-demand single phrase generation (--text "...")
  3. Background cache warming (spawned by handler on cache miss)
"""

import argparse
import gc
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
REFERENCE_WAV = SCRIPT_DIR / "reference" / "voice.wav"
CACHE_DIR = SCRIPT_DIR / "cache"
CONFIG_FILE = SCRIPT_DIR / "config.json"

# Global model cache -- loaded once, reused across calls within same process
_model = None
_model_sr = None


def load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {"tts": {"exaggeration": 0.3, "cfg_weight": 0.4}}


def get_device() -> str:
    """Pick best available device: MPS (Apple Silicon) > CUDA > CPU."""
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _patch_torch_load_for_device(device: str) -> None:
    """Monkey-patch torch.load to add map_location for non-CUDA devices.

    Chatterbox checkpoints were saved from CUDA. On MPS/CPU, torch.load
    fails without map_location. This patches it globally before model load.
    """
    import torch

    if device == "cuda":
        return

    _original_load = torch.load

    def _patched_load(*args, **kwargs):
        if "map_location" not in kwargs:
            kwargs["map_location"] = torch.device(device)
        return _original_load(*args, **kwargs)

    torch.load = _patched_load


def _get_model():
    """Load or return cached Chatterbox model."""
    global _model, _model_sr

    if _model is not None:
        return _model, _model_sr

    from chatterbox.tts import ChatterboxTTS

    device = get_device()
    _patch_torch_load_for_device(device)

    print(f"[voxhook-tts] Loading model on {device}...", file=sys.stderr)
    _model = ChatterboxTTS.from_pretrained(device=device)
    _model_sr = _model.sr
    return _model, _model_sr


def _cleanup_memory() -> None:
    """Mitigate Chatterbox memory leak on Apple Silicon."""
    import torch

    gc.collect()
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()


def generate_audio(text: str, output_path: Path) -> Path:
    """Generate a WAV file by cloning the reference voice with Chatterbox.

    Args:
        text: Text to speak.
        output_path: Where to write the WAV.

    Returns:
        The output_path on success.
    """
    import torchaudio

    config = load_config()
    tts_cfg = config.get("tts", {})
    exaggeration = tts_cfg.get("exaggeration", 0.3)
    cfg_weight = tts_cfg.get("cfg_weight", 0.4)

    model, sr = _get_model()

    print(f"[voxhook-tts] Generating: {text!r}", file=sys.stderr)
    wav = model.generate(
        text,
        audio_prompt_path=str(REFERENCE_WAV),
        exaggeration=exaggeration,
        cfg_weight=cfg_weight,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    torchaudio.save(str(output_path), wav, sr)
    print(f"[voxhook-tts] Saved: {output_path}", file=sys.stderr)

    _cleanup_memory()
    return output_path


def pre_generate() -> None:
    """Generate all static template messages and populate the cache."""
    sys.path.insert(0, str(SCRIPT_DIR))
    from message_templates import get_all_static_messages, message_hash
    import cache_manager

    messages = get_all_static_messages()
    total = len(messages)
    print(f"[voxhook-tts] Pre-generating {total} phrases...", file=sys.stderr)

    for i, text in enumerate(messages, 1):
        h = message_hash(text)
        if cache_manager.lookup(h) is not None:
            print(f"[voxhook-tts] ({i}/{total}) Cached: {text!r}", file=sys.stderr)
            continue

        wav_path = CACHE_DIR / f"{h}.wav"
        try:
            generate_audio(text, wav_path)
            cache_manager.store(h, text, wav_path)
            print(f"[voxhook-tts] ({i}/{total}) Generated: {text!r}", file=sys.stderr)
        except Exception as e:
            print(f"[voxhook-tts] ({i}/{total}) FAILED: {text!r} -- {e}", file=sys.stderr)

    stats = cache_manager.get_cache_stats()
    print(f"[voxhook-tts] Pre-generation complete. Cache: {stats['valid']} valid entries.", file=sys.stderr)


def generate_single(text: str) -> None:
    """Generate a single phrase and store in cache."""
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
    """Generate a WAV of just the project name being spoken."""
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
    parser = argparse.ArgumentParser(description="Voxhook TTS generator (Chatterbox)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pre-generate", action="store_true", help="Generate all static template messages")
    group.add_argument("--text", type=str, help="Generate a single phrase")
    group.add_argument("--project", type=str, help="Generate just a project name as audio")

    args = parser.parse_args()

    if not REFERENCE_WAV.exists():
        print(f"[voxhook-tts] ERROR: Reference voice not found at {REFERENCE_WAV}", file=sys.stderr)
        print("[voxhook-tts] Place your reference voice WAV at hooks/tts/reference/voice.wav", file=sys.stderr)
        sys.exit(1)

    if args.pre_generate:
        pre_generate()
    elif args.text:
        generate_single(args.text)
    elif args.project:
        generate_project(args.project)


if __name__ == "__main__":
    main()
