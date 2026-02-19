#!/usr/bin/env python3
"""
Voxhook Awareness Detection
============================

Detects user attention tier based on macOS system state to scale
notification intensity. Fail-open: returns None on any failure,
which callers treat as "fire everything."

Tiers:
  FOCUSED — terminal frontmost AND front window matches this project
  NEARBY  — at computer (terminal with different project, or non-terminal app)
  AWAY    — system idle > threshold (push only)
"""

import re
import subprocess
from enum import StrEnum


class AwarenessTier(StrEnum):
    FOCUSED = "FOCUSED"
    NEARBY = "NEARBY"
    AWAY = "AWAY"


_DEFAULT_TERMINAL_APPS = [
    "Terminal", "iTerm2", "Ghostty", "Alacritty", "kitty", "WezTerm",
    "Warp", "stable",  # Warp reports process name as "stable"
]
_DEFAULT_IDLE_THRESHOLD = 300  # seconds


def _get_frontmost_app() -> str | None:
    """Return name of the frontmost application, or None on failure."""
    try:
        result = subprocess.run(
            [
                "osascript", "-e",
                'tell application "System Events" to get name of first application process whose frontmost is true',
            ],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def _get_front_window_title(process_name: str) -> str | None:
    """Return title of the frontmost window for a process, or None on failure."""
    try:
        result = subprocess.run(
            [
                "osascript", "-e",
                f'tell application "System Events" to get title of front window of application process "{process_name}"',
            ],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def _get_idle_seconds() -> float | None:
    """Return system HID idle time in seconds, or None on failure."""
    try:
        result = subprocess.run(
            ["ioreg", "-c", "IOHIDSystem"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode != 0:
            return None
        match = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', result.stdout)
        if match:
            return int(match.group(1)) / 1_000_000_000  # nanoseconds → seconds
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def detect_awareness(config: dict, project_name: str = "") -> AwarenessTier | None:
    """Detect user awareness tier from macOS system state.

    Returns None if detection is disabled or fails (fail-open).
    """
    awareness_cfg = config.get("awareness", {})
    if not awareness_cfg.get("enabled", False):
        return None

    terminal_apps = {a.lower() for a in awareness_cfg.get("terminal_apps", _DEFAULT_TERMINAL_APPS)}
    idle_threshold = awareness_cfg.get("idle_threshold_seconds", _DEFAULT_IDLE_THRESHOLD)

    # Step 1: check frontmost app (case-insensitive — process names vary)
    frontmost = _get_frontmost_app()
    if frontmost is None:
        return None  # detection failed, fail-open

    if frontmost.lower() in terminal_apps:
        # Terminal is frontmost — check if the front window matches this project.
        # If we can't get the title or there's no project name, assume focused.
        if not project_name:
            return AwarenessTier.FOCUSED
        title = _get_front_window_title(frontmost)
        if title and project_name.lower() in title.lower():
            return AwarenessTier.FOCUSED
        # Terminal focused but different project window → NEARBY
        return AwarenessTier.NEARBY

    # Step 2: check idle time (only if not a terminal)
    idle = _get_idle_seconds()
    if idle is None:
        return None  # detection failed, fail-open
    if idle > idle_threshold:
        return AwarenessTier.AWAY

    return AwarenessTier.NEARBY
