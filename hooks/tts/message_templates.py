"""
Voxhook TTS message templates.

Loads message pools from templates.json (sibling file). Falls back to
minimal built-in defaults if the file is missing or corrupt.
"""

import hashlib
import json
import random
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).parent
TEMPLATES_FILE = SCRIPT_DIR / "templates.json"

# Minimal built-in fallback (used only if templates.json is missing)
_FALLBACK_TEMPLATES: dict[str, dict[str, list[str]]] = {
    "Stop": {
        "generic": [
            "Task complete.",
            "Done. Standing by.",
            "Finished. Ready for next.",
        ],
    },
    "Notification": {
        "general": [
            "Notification.",
            "Attention required.",
        ],
    },
}


def _load_templates() -> dict[str, dict[str, list[str]]]:
    """Load templates from JSON file, falling back to built-in defaults."""
    try:
        data = json.loads(TEMPLATES_FILE.read_text())
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return _FALLBACK_TEMPLATES


# Module-level cache (loaded once per process)
TEMPLATES = _load_templates()


def get_message(
    event_type: str,
    project_name: Optional[str] = None,
    notification_type: Optional[str] = None,
) -> str:
    """Select a message for the given event context.

    Args:
        event_type: Hook event name ("Stop", "Notification")
        project_name: Project name extracted from cwd (optional)
        notification_type: Sub-category for notifications (optional)

    Returns:
        A randomly selected message string.
    """
    pool = TEMPLATES.get(event_type, {})

    if event_type == "Notification" and notification_type:
        messages = pool.get(notification_type, pool.get("general", ["Attention required."]))
        return random.choice(messages)

    if event_type == "Stop":
        messages = pool.get("generic", ["Task complete."])
        return random.choice(messages)

    # Fallback
    all_messages = [msg for msgs in pool.values() for msg in msgs]
    if all_messages:
        return random.choice(all_messages)
    return "Task complete."


def message_hash(text: str) -> str:
    """Produce a short, filesystem-safe hash of a message string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def get_all_static_messages() -> list[str]:
    """Return every unique static (non-templated) message for pre-generation."""
    messages: set[str] = set()
    for event_pool in TEMPLATES.values():
        for pool_messages in event_pool.values():
            for msg in pool_messages:
                if "{" not in msg:
                    messages.add(msg)
    return sorted(messages)
