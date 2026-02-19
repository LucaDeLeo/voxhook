"""Cross-process audio playback lock.

Uses fcntl.flock() so the lock is automatically released if the
holding process is killed — no stale lockfiles.
"""

import fcntl
from contextlib import contextmanager

LOCK_FILE = "/tmp/voxhook_audio.lock"


@contextmanager
def audio_lock():
    """Acquire exclusive audio playback lock (blocks until available)."""
    f = open(LOCK_FILE, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()
