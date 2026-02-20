"""Voxhook installer — Python port of install.sh."""

import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

INSTALL_DIR = Path.home() / ".claude" / "hooks" / "voxhook"
SETTINGS_FILE = Path.home() / ".claude" / "settings.json"

# Colors
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
NC = "\033[0m"


def info(msg: str) -> None:
    print(f"{CYAN}[voxhook]{NC} {msg}")


def ok(msg: str) -> None:
    print(f"{GREEN}[voxhook]{NC} {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}[voxhook]{NC} {msg}")


def err(msg: str) -> None:
    print(f"{RED}[voxhook]{NC} {msg}", file=sys.stderr)


def _find_source_dir() -> Path:
    """Locate the bundled data files (hooks/, templates/, models/).

    When installed via `uv tool install`, data lives inside the package
    at voxhook/_data/.  When running from a cloned repo, it's at the
    repo root.
    """
    # Check package data first (uv tool install)
    pkg_data = Path(__file__).resolve().parent / "_data"
    if (pkg_data / "hooks" / "tts" / "handler.py").exists():
        return pkg_data

    # Fall back to repo root (development)
    repo_root = Path(__file__).resolve().parent.parent
    if (repo_root / "hooks" / "tts" / "handler.py").exists():
        return repo_root

    return None


def _check_prerequisites() -> list[str]:
    """Check for required tools. Returns list of missing items."""
    missing = []

    # Python 3.11+
    if sys.version_info < (3, 11):
        missing.append(f"Python 3.11+ (found {sys.version_info.major}.{sys.version_info.minor})")

    # uv
    if not shutil.which("uv"):
        missing.append("uv (https://docs.astral.sh/uv/)")

    # afplay (macOS)
    if sys.platform == "darwin" and not shutil.which("afplay"):
        missing.append("afplay (should be built into macOS)")

    # Claude Code directory
    if not (Path.home() / ".claude").is_dir():
        missing.append("~/.claude directory (install Claude Code first)")

    return missing


def _prompt(text: str, default: str = "") -> str:
    """Prompt user for input with optional default."""
    if default:
        result = input(f"{CYAN}{text}{NC} [{default}]: ").strip()
        return result or default
    return input(f"{CYAN}{text}{NC}: ").strip()


def _prompt_yn(text: str, default_yes: bool = True) -> bool:
    """Prompt user for yes/no."""
    hint = "Y/n" if default_yes else "y/N"
    result = input(f"{CYAN}{text}{NC} [{hint}]: ").strip().lower()
    if not result:
        return default_yes
    return result in ("y", "yes")


def _copy_tree(src: Path, dst: Path) -> None:
    """Copy directory tree, overwriting destination."""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _patch_settings(ntfy_topic: str, enable_tts: bool, enable_ntfy: bool) -> None:
    """Idempotently patch ~/.claude/settings.json with voxhook hook entries."""
    try:
        if SETTINGS_FILE.exists():
            settings = json.loads(SETTINGS_FILE.read_text())
        else:
            settings = {}
    except (json.JSONDecodeError, OSError) as e:
        warn(f"Could not parse settings.json: {e}")
        warn("Creating backup and starting fresh.")
        if SETTINGS_FILE.exists():
            SETTINGS_FILE.rename(SETTINGS_FILE.with_suffix(".json.bak"))
        settings = {}

    hooks = settings.setdefault("hooks", {})

    def remove_voxhook(entries: list) -> list:
        return [
            e for e in entries
            if not any("voxhook" in h.get("command", "") for h in e.get("hooks", []))
        ]

    # Clean existing voxhook entries (idempotent reinstall)
    stop_hooks = hooks.setdefault("Stop", [])
    stop_hooks[:] = remove_voxhook(stop_hooks)

    notif_hooks = hooks.setdefault("Notification", [])
    notif_hooks[:] = remove_voxhook(notif_hooks)

    # Push notification hook (Stop)
    if enable_ntfy and ntfy_topic:
        stop_hooks.append({
            "hooks": [{
                "type": "command",
                "command": f"nohup uv run ~/.claude/hooks/voxhook/notify/handler.py --topic={ntfy_topic} &",
            }]
        })

    if enable_tts:
        # TTS hook (Stop)
        tts_cmd = "uv run ~/.claude/hooks/voxhook/tts/handler.py"
        if enable_ntfy and ntfy_topic:
            tts_cmd += f" --ntfy-topic={ntfy_topic}"
        stop_hooks.append({
            "hooks": [{
                "type": "command",
                "command": tts_cmd,
                "timeout": 10,
            }]
        })

        # TTS hook (Notification)
        notif_hooks.append({
            "hooks": [{
                "type": "command",
                "command": "uv run ~/.claude/hooks/voxhook/tts/handler.py",
                "timeout": 10,
            }]
        })

    SETTINGS_FILE.write_text(json.dumps(settings, indent=2) + "\n")
    ok("settings.json updated.")


def _remove_settings() -> None:
    """Remove all voxhook entries from ~/.claude/settings.json."""
    if not SETTINGS_FILE.exists():
        return

    try:
        settings = json.loads(SETTINGS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return

    hooks = settings.get("hooks", {})
    changed = False

    for event in list(hooks.keys()):
        entries = hooks[event]
        cleaned = [
            e for e in entries
            if not any("voxhook" in h.get("command", "") for h in e.get("hooks", []))
        ]
        if len(cleaned) != len(entries):
            hooks[event] = cleaned
            changed = True

    if changed:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2) + "\n")
        ok("Removed voxhook entries from settings.json.")


def run_install() -> None:
    """Interactive installer — Python port of install.sh."""
    source_dir = _find_source_dir()
    if source_dir is None:
        err("Cannot find voxhook source files.")
        err("Run from cloned repo or install via: uv tool install git+<url>")
        sys.exit(1)

    info(f"Source: {source_dir}")

    # Check prerequisites
    info("Checking prerequisites...")
    missing = _check_prerequisites()
    if missing:
        err("Missing prerequisites:")
        for m in missing:
            err(f"  - {m}")
        sys.exit(1)
    ok("All prerequisites met.")

    # Interactive configuration
    print()
    print(f"{BOLD}Voxhook Setup{NC}")
    print()

    # Push notifications
    print(f"{BOLD}Push Notifications{NC}")
    print("  ntfy.sh sends push notifications to your phone/desktop when")
    print("  Claude finishes a task, needs permission, or goes idle.")
    print("  Free, no account needed — just pick a topic name.")
    print()

    enable_ntfy = _prompt_yn("Enable push notifications?")
    ntfy_topic = ""
    if enable_ntfy:
        default_topic = f"voxhook-{secrets.token_hex(4)}"
        ntfy_topic = _prompt("Topic name", default_topic)
        # Sanitize
        if not all(c.isalnum() or c in "-_" for c in ntfy_topic):
            err("Topic name must contain only letters, numbers, hyphens, and underscores.")
            sys.exit(1)
        ok(f"Notifications enabled (topic: {ntfy_topic})")

    # TTS voice mode
    print()
    print(f"{BOLD}TTS Voice Mode:{NC}")
    print("  1) GLaDOS (recommended) — sardonic AI commentary on what Claude did")
    print("  2) Custom voice          — clone any voice from a reference WAV (Chatterbox)")
    print("  3) None                  — push notifications only")
    tts_choice = _prompt("Choice", "1")

    enable_tts = False
    tts_engine = ""
    use_dynamic = False
    template_file = ""
    voice_path = ""

    if tts_choice == "1":
        # GLaDOS mode
        enable_tts = True
        tts_engine = "piper"
        use_dynamic = True
        template_file = source_dir / "templates" / "glados.json"

        model_path = source_dir / "models" / "glados" / "glados_piper_medium.onnx"
        if not model_path.exists():
            err(f"GLaDOS model not found at {model_path}")
            err("Make sure model files are included.")
            sys.exit(1)
        ok("GLaDOS mode selected.")

    elif tts_choice == "2":
        # Chatterbox mode
        enable_tts = True
        tts_engine = "chatterbox"

        print()
        print(f"{BOLD}Custom Voice Setup{NC}")
        print("  Requires a reference .wav file (5-30 seconds of clear speech).")
        print()
        voice_path = _prompt("Path to reference voice WAV")
        voice_path = os.path.expanduser(voice_path)

        if not voice_path or not Path(voice_path).is_file():
            err(f"File not found: {voice_path or '<empty>'}")
            if _prompt_yn("Continue without TTS?"):
                enable_tts = False
            else:
                sys.exit(1)

        if enable_tts:
            print()
            print(f"{BOLD}Message template preset:{NC}")
            print("  1) default         - Neutral professional tone")
            print("  2) abathur         - Evolutionary/clinical Abathur style")
            print("  3) glados          - Sardonic GLaDOS tone")
            print("  4) reptilian-brain - Primal urgency")
            print("  5) custom          - Provide your own JSON file")
            tmpl_choice = _prompt("Choice", "1")

            template_map = {
                "2": "abathur.json",
                "3": "glados.json",
                "4": "reptilian-brain.json",
            }
            if tmpl_choice in template_map:
                template_file = source_dir / "templates" / template_map[tmpl_choice]
            elif tmpl_choice == "5":
                custom = os.path.expanduser(_prompt("Path to custom templates JSON"))
                if Path(custom).is_file():
                    template_file = Path(custom)
                else:
                    warn("File not found, using default template.")
                    template_file = source_dir / "templates" / "default.json"
            else:
                template_file = source_dir / "templates" / "default.json"

    elif tts_choice == "3":
        ok("Push notifications only.")
    else:
        err(f"Invalid choice: {tts_choice}")
        sys.exit(1)

    # Install files
    print()
    info(f"Installing to {INSTALL_DIR}...")

    if INSTALL_DIR.exists():
        warn("Existing installation found, replacing...")
        shutil.rmtree(INSTALL_DIR)

    INSTALL_DIR.mkdir(parents=True, exist_ok=True)

    # Copy hook files
    _copy_tree(source_dir / "hooks" / "common", INSTALL_DIR / "common")
    _copy_tree(source_dir / "hooks" / "notify", INSTALL_DIR / "notify")
    _copy_tree(source_dir / "hooks" / "tts", INSTALL_DIR / "tts")

    # Copy selected template
    if enable_tts and template_file:
        dst = INSTALL_DIR / "tts" / "templates.json"
        dst.unlink(missing_ok=True)
        shutil.copy2(str(template_file), str(dst))

    # Copy reference voice (Chatterbox)
    if enable_tts and voice_path and Path(voice_path).is_file():
        ref_dir = INSTALL_DIR / "tts" / "reference"
        ref_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(voice_path, str(ref_dir / "voice.wav"))
        ok("Voice file copied.")

    # Copy GLaDOS model (Piper)
    if tts_engine == "piper":
        model_dst = INSTALL_DIR / "tts" / "models" / "glados"
        model_dst.mkdir(parents=True, exist_ok=True)
        for ext in (".onnx", ".onnx.json"):
            src = source_dir / "models" / "glados" / f"glados_piper_medium{ext}"
            if src.exists():
                shutil.copy2(str(src), str(model_dst))
        ok("GLaDOS model installed.")

    # Create cache directory
    (INSTALL_DIR / "tts" / "cache").mkdir(parents=True, exist_ok=True)

    # Write config
    if enable_tts:
        config = {
            "volume": 0.6,
            "playback_speed": 1.0,
            "tts_engine": tts_engine,
            "dynamic_tts": use_dynamic,
            "enabled": True,
            "sound_enabled": True,
            "ntfy_enabled": enable_ntfy,
            "suppress_delegate_mode": True,
            "awareness": {
                "enabled": True,
                "terminal_apps": [
                    "Terminal", "iTerm2", "Ghostty", "Alacritty",
                    "kitty", "WezTerm", "Warp", "stable",
                ],
                "idle_threshold_seconds": 300,
            },
        }
        if tts_engine == "piper":
            config["piper_model"] = "models/glados/glados_piper_medium.onnx"

        (INSTALL_DIR / "tts" / "config.json").write_text(
            json.dumps(config, indent=2) + "\n"
        )
        ok("Config written.")

    ok("Files installed.")

    # Patch settings.json
    info("Configuring Claude Code hooks...")
    _patch_settings(ntfy_topic, enable_tts, enable_ntfy)
    ok("Hooks configured.")

    # Pre-generation
    if enable_tts:
        if tts_engine == "piper":
            print()
            info("Pre-generating TTS audio cache (Piper — this is quick)...")
            gen_script = INSTALL_DIR / "tts" / "generate_piper.py"
            result = subprocess.run(
                ["uv", "run", "--python", "3.11", str(gen_script), "--pre-generate"],
                capture_output=False,
            )
            if result.returncode == 0:
                ok("Audio cache ready.")
            else:
                warn("Pre-generation had errors. TTS will generate on-demand instead.")
        else:
            print()
            if _prompt_yn("Pre-generate TTS audio cache? (takes a few minutes)", default_yes=False):
                info("Starting pre-generation...")
                gen_script = INSTALL_DIR / "tts" / "generate.py"
                subprocess.run(
                    ["uv", "run", "--python", "3.11", str(gen_script), "--pre-generate"],
                    capture_output=False,
                )

    # Summary
    print()
    print(f"{GREEN}{BOLD}Voxhook installed successfully!{NC}")
    print()
    if enable_ntfy:
        print(f"  {BOLD}ntfy.sh topic:{NC}  {ntfy_topic}")
        print(f"  {BOLD}Subscribe:{NC}      https://ntfy.sh/{ntfy_topic}")
    if enable_tts:
        print(f"  {BOLD}TTS engine:{NC}     {tts_engine}")
        if use_dynamic:
            print(f"  {BOLD}Dynamic TTS:{NC}    enabled (GLaDOS commentary via Agent SDK)")
    print(f"  {BOLD}Install path:{NC}   {INSTALL_DIR}")
    print()

    # Usage hints
    print(f"  {BOLD}Quick mute:{NC}     {CYAN}vox{NC}            (toggle mute)")
    print(f"  {BOLD}Per-project:{NC}    {CYAN}vox suppress{NC}   (silence current project)")
    print(f"  {BOLD}Check state:{NC}    {CYAN}vox status{NC}")
    print()


def run_uninstall() -> None:
    """Remove voxhook installation."""
    if not INSTALL_DIR.exists():
        warn("Voxhook is not installed.")
        return

    info("Removing voxhook...")

    # Remove settings entries
    _remove_settings()

    # Remove install directory
    shutil.rmtree(INSTALL_DIR)
    ok("Removed installation directory.")

    # Clean up mute file (it lives inside INSTALL_DIR, so already gone)
    print()
    ok("Voxhook uninstalled.")
