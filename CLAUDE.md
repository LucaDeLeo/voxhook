# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Voxhook is a Claude Code hooks plugin providing push notifications (via ntfy.sh) and TTS voice cloning (via Chatterbox) when Claude finishes tasks, needs permission, or goes idle. macOS only (uses `afplay`). Python 3.11+, dependencies managed via `uv` inline script metadata.

## Architecture

Two independent hook handlers, both triggered by Claude Code hook events (JSON on stdin):

**TTS handler** (`hooks/tts/handler.py`) — fast path, <300ms target:
- Reads hook JSON, picks random message from templates, plays cached WAV via `afplay`
- On cache miss: plays any fallback WAV, spawns `generate.py` in background to warm cache
- For Stop events: sequences project name WAV + message WAV back-to-back
- Never imports torch/chatterbox — keeps startup fast

**TTS generator** (`hooks/tts/generate.py`) — heavy path:
- Loads Chatterbox model (MPS > CUDA > CPU), clones reference voice
- `--pre-generate`: generates all template messages (each in subprocess to avoid MPS OOM)
- `--text "..."`: single phrase generation
- `--project name`: project name audio generation
- Monkey-patches `torch.load` with `map_location` for non-CUDA devices

**Notify handler** (`hooks/notify/handler.py`):
- Context-aware push notifications via ntfy.sh HTTP POST
- Maps hook events to notification messages using `notification_mapping.json`
- Categorizes by file extension, git command, bash command type

**Shared** (`hooks/common/`):
- `enums.py`: StrEnum definitions for hook events, tool names, file extensions, etc.
- `utils.py`: Safe enum conversion with case-insensitive fallback, hook data parsing

**Cache system** (`hooks/tts/cache_manager.py`):
- SHA-256 hash-indexed WAV cache with JSON index file (`cache/_index.json`)
- LRU eviction at 500 entries, atomic index writes via temp file + rename

## Key Patterns

- All handlers use `uv` inline script metadata (`# /// script`) for dependency declaration — no requirements.txt or pyproject.toml
- TTS handler and notify handler are separate processes: TTS runs synchronously (5s timeout), notify runs with `nohup &` (fire-and-forget)
- Background work (cache warming, ntfy POST) uses `subprocess.Popen` with stdin pipes passing JSON payloads to avoid shell injection
- Idle notifications have a 5-minute cooldown persisted to `.idle_cooldown` file
- Delegate/agent sub-sessions are suppressed by default (`suppress_delegate_mode`)

## Running and Testing

```bash
# Install hooks to ~/.claude/hooks/voxhook/
./install.sh

# Pre-generate all template audio (requires reference voice)
uv run --python 3.11 hooks/tts/generate.py --pre-generate

# Generate single phrase
uv run --python 3.11 hooks/tts/generate.py --text "Task complete."

# Test notify handler
echo '{"hook_event_name":"Stop"}' | uv run hooks/notify/handler.py --topic=test-topic

# Test TTS handler
echo '{"hook_event_name":"Stop","cwd":"/path/to/project"}' | uv run hooks/tts/handler.py

# Run notification tests
uv run hooks/notify/test.py
```

## Install Location

Source repo is here; `install.sh` copies to `~/.claude/hooks/voxhook/` and patches `~/.claude/settings.json`. When developing, edit files here then re-run `./install.sh` to deploy.
