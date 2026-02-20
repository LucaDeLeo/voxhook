"""Vox CLI — mute, suppress, install, and manage voxhook."""

import argparse
import sys
from pathlib import Path

INSTALL_DIR = Path.home() / ".claude" / "hooks" / "voxhook"
MUTE_FILE = INSTALL_DIR / ".muted"
SUPPRESS_FILE = ".voxhook-suppress"

# Colors
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
NC = "\033[0m"


def _toggle_mute() -> None:
    """Toggle global mute state."""
    if MUTE_FILE.exists():
        _unmute()
    else:
        _mute()


def _mute() -> None:
    """Enable global mute."""
    MUTE_FILE.parent.mkdir(parents=True, exist_ok=True)
    MUTE_FILE.touch()
    print(f"{RED}{BOLD}MUTED{NC} — all voxhook audio + notifications silenced")
    print(f"  Run {CYAN}vox{NC} or {CYAN}vox unmute{NC} to re-enable")


def _unmute() -> None:
    """Disable global mute."""
    try:
        MUTE_FILE.unlink()
    except FileNotFoundError:
        pass
    print(f"{GREEN}{BOLD}UNMUTED{NC} — voxhook active")


def _suppress() -> None:
    """Create per-project suppress sentinel in CWD."""
    sentinel = Path.cwd() / SUPPRESS_FILE
    sentinel.touch()
    print(f"{YELLOW}SUPPRESSED{NC} — voxhook silenced for {BOLD}{Path.cwd().name}{NC}")
    print(f"  Run {CYAN}vox unsuppress{NC} to re-enable")


def _unsuppress() -> None:
    """Remove per-project suppress sentinel from CWD."""
    sentinel = Path.cwd() / SUPPRESS_FILE
    try:
        sentinel.unlink()
    except FileNotFoundError:
        pass
    print(f"{GREEN}UNSUPPRESSED{NC} — voxhook active for {BOLD}{Path.cwd().name}{NC}")


def _status() -> None:
    """Show current mute/suppress state."""
    print(f"{BOLD}Voxhook Status{NC}")
    print()

    # Global mute
    if MUTE_FILE.exists():
        print(f"  Global:  {RED}{BOLD}MUTED{NC}")
    else:
        print(f"  Global:  {GREEN}active{NC}")

    # Per-project suppress
    sentinel = Path.cwd() / SUPPRESS_FILE
    project = Path.cwd().name
    if sentinel.exists():
        print(f"  Project: {YELLOW}SUPPRESSED{NC} ({project})")
    else:
        print(f"  Project: {GREEN}active{NC} ({project})")

    # Install state
    print()
    if INSTALL_DIR.exists():
        print(f"  Install: {INSTALL_DIR}")
        config = INSTALL_DIR / "tts" / "config.json"
        if config.exists():
            import json
            try:
                cfg = json.loads(config.read_text())
                engine = cfg.get("tts_engine", "unknown")
                dynamic = cfg.get("dynamic_tts", False)
                print(f"  Engine:  {engine}" + (" (dynamic)" if dynamic else ""))
            except (json.JSONDecodeError, OSError):
                pass
    else:
        print(f"  Install: {RED}not installed{NC}")
        print(f"  Run {CYAN}vox install{NC} to set up")


def _install() -> None:
    """Run interactive installer."""
    from voxhook.installer import run_install
    run_install()


def _uninstall() -> None:
    """Remove voxhook hooks and settings entries."""
    from voxhook.installer import run_uninstall
    run_uninstall()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="vox",
        description="Voxhook — TTS + push notifications for Claude Code",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("mute", help="Silence all voxhook output globally")
    sub.add_parser("unmute", help="Re-enable voxhook output globally")
    sub.add_parser("suppress", help="Silence voxhook for current project")
    sub.add_parser("unsuppress", help="Re-enable voxhook for current project")
    sub.add_parser("status", help="Show current mute/suppress state")
    sub.add_parser("install", help="Interactive setup (replaces install.sh)")
    sub.add_parser("uninstall", help="Remove hooks and settings entries")

    args = parser.parse_args()

    match args.command:
        case None:
            _toggle_mute()
        case "mute":
            _mute()
        case "unmute":
            _unmute()
        case "suppress":
            _suppress()
        case "unsuppress":
            _unsuppress()
        case "status":
            _status()
        case "install":
            _install()
        case "uninstall":
            _uninstall()
        case _:
            parser.print_help()
            sys.exit(1)
