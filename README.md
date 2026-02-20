# Voxhook

Push notifications + TTS for [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

Get notified when Claude finishes a task — via your phone (ntfy.sh) and/or a GLaDOS voice that delivers sardonic commentary on what Claude actually did.

No API key needed, no extra cost. Dynamic TTS uses the [Agent SDK](https://docs.anthropic.com/en/docs/claude-code/agent-sdk) which uses your Claude Code auth — the same billing you're already paying for. Requires a Claude Pro or Max plan (anything that includes Claude Code).

## Quick install

```bash
uv tool install git+https://github.com/LucaDeLeo/voxhook
vox install
```

The installer will:
1. Check prerequisites (Python 3.11+, uv, macOS)
2. Ask for your ntfy.sh topic name
3. Let you pick a TTS voice mode (GLaDOS / custom voice / none)
4. Install hooks to `~/.claude/hooks/voxhook/`
5. Patch `~/.claude/settings.json` automatically

## TTS voice modes

### GLaDOS (recommended)

The default experience. Uses a Piper ONNX model to synthesize speech with a GLaDOS voice. On every Stop event, the Agent SDK calls Haiku to generate a one-liner about what Claude actually did, then Piper speaks it aloud.

- No reference voice needed — model ships with the repo
- Fast synthesis (~5s pre-gen for all templates)
- Dynamic commentary is the killer feature: GLaDOS reacts to what Claude did, not a random canned phrase

Pick option 1 during install — model is copied, cache is pre-generated, and a smoke test plays automatically.

### Custom voice (Chatterbox)

Clone any voice from a 5-30s reference WAV using Chatterbox TTS. Picks random messages from your chosen template. Good for character voices that don't have a Piper model.

Pick option 2 during install and provide your reference WAV.

### None

Push notifications only. No audio. Pick option 3.

## What it does

**Push notifications** (ntfy.sh) — context-aware notifications sent to your phone/desktop when Claude Code:
- Completes a task (Stop)
- Needs permission (Notification)
- Goes idle (Notification)

**TTS** (GLaDOS or custom voice) — plays spoken audio:
- **Dynamic mode** (GLaDOS): Agent SDK generates a sardonic one-liner about Claude's actual output, Piper synthesizes it live
- **Template mode** (custom voice): picks a random message from your template, plays cached audio instantly (<300ms)
- Sequences project name + message for Stop events
- Warms cache in background on misses

## Requirements

- macOS (afplay for audio playback)
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package runner)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)

## Config reference

Edit `~/.claude/hooks/voxhook/tts/config.json`:

| Key | Default | Description |
|-----|---------|-------------|
| `volume` | `0.6` | Audio playback volume (0.0-1.0) |
| `playback_speed` | `1.0` | Playback speed multiplier |
| `tts_engine` | `"piper"` | TTS engine: `"piper"` or `"chatterbox"` |
| `piper_model` | `"models/glados/..."` | Path to Piper ONNX model (relative to tts/) |
| `dynamic_tts` | `true` | Enable Agent SDK dynamic commentary (piper only) |
| `enabled` | `true` | Master enable/disable |
| `sound_enabled` | `true` | Audio playback on/off |
| `ntfy_enabled` | `true` | Push notifications on/off |
| `suppress_delegate_mode` | `true` | Suppress for agent sub-sessions |

## Message templates

Templates control what the TTS voice says (used for template mode and as fallback when dynamic TTS fails). Located in `templates/`:

| Template | Style |
|----------|-------|
| `glados.json` | Sardonic GLaDOS ("Congratulations. That was adequate.") |
| `default.json` | Neutral professional ("Task complete. Standing by.") |
| `abathur.json` | Evolutionary/clinical ("Evolution complete. Essence preserved.") |
| `reptilian-brain.json` | Primal urgency |

Create your own by copying any template and modifying the message arrays.

## Architecture

```
~/.claude/hooks/voxhook/
├── common/                 # Shared enums and utilities
│   ├── __init__.py
│   ├── enums.py            # HookEvent, ToolName, etc.
│   └── utils.py            # Safe enum conversion, categorization
├── notify/                 # Push notifications
│   ├── handler.py          # Main handler (reads stdin, sends ntfy)
│   ├── notification_mapping.json
│   └── test.py
└── tts/                    # TTS audio
    ├── handler.py          # Fast path: pick message, play cached WAV
    ├── gladosify.py        # Agent SDK → Haiku → GLaDOS one-liner → Piper → play
    ├── generate_piper.py   # Piper ONNX synthesis (pre-gen + single phrase)
    ├── generate.py         # Chatterbox voice cloning (heavy path)
    ├── audio_queue.py      # Cross-process fcntl.flock playback lock
    ├── message_templates.py
    ├── cache_manager.py    # SHA-256 hash-indexed WAV cache, LRU eviction
    ├── config.json
    ├── templates.json      # Active message templates
    ├── models/
    │   └── glados/         # Piper ONNX model + config
    ├── reference/
    │   └── voice.wav       # Chatterbox reference voice (if using custom)
    └── cache/              # Generated WAV files
```

**Handler flow** (Stop event with GLaDOS):
1. Read hook JSON from stdin
2. If dynamic TTS enabled + last_assistant_message exists: spawn `gladosify.py`
3. `gladosify.py` calls Haiku via Agent SDK to generate GLaDOS one-liner
4. Piper synthesizes the line, plays via `afplay` (locked by `audio_queue.py`)

**Handler flow** (template fallback / Chatterbox):
1. Read hook JSON from stdin
2. Select message from templates
3. Look up WAV in cache by content hash
4. If cached: play via `afplay`
5. If not cached: play any fallback, spawn generator in background

## Pre-generating audio

```bash
# Piper (fast, ~5s)
uv run --python 3.11 ~/.claude/hooks/voxhook/tts/generate_piper.py --pre-generate

# Chatterbox (slow, minutes)
uv run --python 3.11 ~/.claude/hooks/voxhook/tts/generate.py --pre-generate
```

## Uninstall

```bash
vox uninstall
uv tool uninstall voxhook
```

This removes `~/.claude/hooks/voxhook/` and cleans voxhook entries from `settings.json`, leaving your other hooks untouched.

## License

MIT
