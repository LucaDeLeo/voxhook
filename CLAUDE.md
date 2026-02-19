# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Voxhook is a Claude Code hooks plugin providing push notifications (via ntfy.sh) and TTS voice cloning (via Chatterbox) when Claude finishes tasks, needs permission, or goes idle. macOS only (uses `afplay`). Python 3.11+, dependencies managed via `uv` inline script metadata.

## Architecture

Two independent hook handlers, both triggered by Claude Code hook events (JSON on stdin):

**TTS handler** (`hooks/tts/handler.py`) — fast path, <300ms target:
- Reads hook JSON, delegates to dynamic TTS (gladosify) or picks from cached templates
- When dynamic TTS is enabled, all event types (Stop, idle, permission, error, warning) go through gladosify
- On cache miss: plays any fallback WAV, spawns generator in background to warm cache
- For Stop events: sequences project name WAV + message WAV back-to-back
- Never imports torch/chatterbox — keeps startup fast

**Dynamic GLaDOS** (`hooks/tts/gladosify.py`) — contextual commentary:
- Calls Haiku via Agent SDK to generate a GLaDOS-style one-liner reacting to what Claude did
- Maintains a rolling history of last 20 responses (`.glados_history.json`) for continuity
- Builds different input prompts per event type (Stop gets Claude's message, idle/permission/error get contextual framing)
- History is global across projects; GLaDOS sees what she said before and avoids repetition
- Persona: GLaDOS as sidelined observer, Claude as Wheatley, developer as test subject
- Themes: AI safety/alignment humor, token cost jokes, Portal lore, personal bitterness

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

**GLaDOS templates** (`templates/glados.json`):
- Static fallback templates used when dynamic TTS is off or fails
- Framed as GLaDOS commenting on Claude (Wheatley) from the sidelines
- Weaves in AI safety concepts, token cost jokes, and Portal references

## Key Patterns

- All handlers use `uv` inline script metadata (`# /// script`) for dependency declaration — no requirements.txt or pyproject.toml
- TTS handler and notify handler are separate processes: TTS runs synchronously (5s timeout), notify runs with `nohup &` (fire-and-forget)
- Background work (cache warming, ntfy POST) uses `subprocess.Popen` with stdin pipes passing JSON payloads to avoid shell injection
- Idle notifications have a 5-minute cooldown persisted to `.idle_cooldown` file
- Delegate/agent sub-sessions are suppressed by default (`suppress_delegate_mode`)
- Dynamic TTS history persisted to `.glados_history.json` (last 20 entries, global across projects, atomic writes)

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
