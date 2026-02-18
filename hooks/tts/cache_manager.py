"""
WAV cache manager for Voxhook TTS.

Maintains a hash-indexed cache of generated audio files with LRU eviction.
"""

import json
import time
from pathlib import Path
from typing import Optional

CACHE_DIR = Path(__file__).parent / "cache"
INDEX_FILE = CACHE_DIR / "_index.json"
DEFAULT_MAX_ENTRIES = 500


def _load_index() -> dict:
    """Load the cache index from disk."""
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {"entries": {}}
    return {"entries": {}}


def _save_index(index: dict) -> None:
    """Persist the cache index to disk."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(json.dumps(index, indent=2))


def lookup(text_hash: str) -> Optional[Path]:
    """Look up a cached WAV file by text hash.

    Returns the Path to the WAV if it exists, None otherwise.
    Also updates access time for LRU tracking.
    """
    index = _load_index()
    entry = index["entries"].get(text_hash)
    if not entry:
        return None

    wav_path = Path(entry["path"])
    if not wav_path.exists():
        # Stale entry -- remove it
        del index["entries"][text_hash]
        _save_index(index)
        return None

    # Update access time for LRU
    entry["last_access"] = time.time()
    _save_index(index)
    return wav_path


def store(text_hash: str, text: str, audio_path: Path, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
    """Store a generated WAV in the cache.

    Args:
        text_hash: Hash of the source text.
        text: Original text (for debugging/inspection).
        audio_path: Path to the WAV file to cache.
        max_entries: Maximum cache entries before LRU eviction.
    """
    index = _load_index()

    index["entries"][text_hash] = {
        "path": str(audio_path),
        "text": text,
        "created": time.time(),
        "last_access": time.time(),
    }

    # LRU eviction if over limit
    if len(index["entries"]) > max_entries:
        _evict(index, max_entries)

    _save_index(index)


def _evict(index: dict, max_entries: int) -> None:
    """Remove least-recently-accessed entries until within limit."""
    entries = index["entries"]
    sorted_keys = sorted(entries, key=lambda k: entries[k].get("last_access", 0))
    to_remove = len(entries) - max_entries

    for key in sorted_keys[:to_remove]:
        entry = entries.pop(key)
        try:
            Path(entry["path"]).unlink(missing_ok=True)
        except OSError:
            pass


def get_any_cached_file() -> Optional[Path]:
    """Return any valid cached WAV file as a fallback for cache misses."""
    index = _load_index()
    for entry in index["entries"].values():
        wav_path = Path(entry["path"])
        if wav_path.exists():
            return wav_path
    return None


def get_cache_stats() -> dict:
    """Return basic cache statistics."""
    index = _load_index()
    total = len(index["entries"])
    valid = sum(1 for e in index["entries"].values() if Path(e["path"]).exists())
    return {"total": total, "valid": valid}
