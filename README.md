# Voxhook

Push notifications + TTS voice cloning for [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

Get notified when Claude finishes a task -- via your phone (ntfy.sh) and/or spoken audio cloned from any voice you provide (Chatterbox TTS).

## Quick install

```bash
git clone https://github.com/YOUR_USER/voxhook.git
cd voxhook
./install.sh
```

The installer will:
1. Check prerequisites
2. Ask for your ntfy.sh topic name
3. Optionally set up TTS with your reference voice
4. Install hooks to `~/.claude/hooks/voxhook/`
5. Patch `~/.claude/settings.json` automatically

## What it does

**Push notifications** (ntfy.sh) -- context-aware notifications sent to your phone/desktop when Claude Code:
- Completes a task (Stop)
- Needs permission (Notification)
- Goes idle (Notification)

**TTS voice cloning** (optional) -- plays spoken audio using a voice cloned from your reference WAV:
- Picks a random message from your chosen template
- Plays cached audio instantly (<300ms)
- Warms cache in background on misses
- Sequences project name + message for Stop events

## Requirements

- macOS (afplay for audio playback)
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package runner)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)

For TTS: a reference `.wav` file (5-30 seconds) of the voice you want to clone.

## Setup guides

### Push notifications only

```bash
./install.sh
# Enter your ntfy topic, skip voice path, done
```

Subscribe to your topic:
- **Web**: `https://ntfy.sh/YOUR_TOPIC`
- **Mobile**: Install [ntfy app](https://ntfy.sh), subscribe to your topic

### Full setup (push + TTS)

```bash
./install.sh
# Enter your ntfy topic
# Enter path to your reference voice .wav
# Choose a message template (default/abathur/custom)
# Optionally pre-generate audio cache
```

## Customization

### Message templates

Templates control what the TTS voice says. Located in `templates/`:

| Template | Style |
|----------|-------|
| `default.json` | Neutral professional ("Task complete. Standing by.") |
| `abathur.json` | Evolutionary/clinical ("Evolution complete. Essence preserved.") |

Create your own by copying `default.json` and modifying the message arrays. Use `--custom` during install or copy directly to `~/.claude/hooks/voxhook/tts/templates.json`.

### Voice

Place any `.wav` file (5-30s of clear speech) as your reference voice. The installer copies it to `~/.claude/hooks/voxhook/tts/reference/voice.wav`.

To change voices later:
```bash
cp /path/to/new_voice.wav ~/.claude/hooks/voxhook/tts/reference/voice.wav
rm -rf ~/.claude/hooks/voxhook/tts/cache/  # Clear cached audio
```

### Config reference

Edit `~/.claude/hooks/voxhook/tts/config.json`:

| Key | Default | Description |
|-----|---------|-------------|
| `volume` | `0.6` | Audio playback volume (0.0-1.0) |
| `enabled` | `true` | Master enable/disable |
| `sound_enabled` | `true` | Audio playback on/off |
| `ntfy_enabled` | `true` | Push notifications on/off |
| `ntfy_title` | `"Voxhook"` | Title shown in push notifications |
| `ntfy_server` | `"https://ntfy.sh"` | ntfy server URL |
| `ntfy_priority` | `3` | Notification priority (1-5) |
| `ntfy_tags` | `"brain"` | ntfy tags |
| `suppress_delegate_mode` | `true` | Suppress for agent sub-sessions |
| `tts.exaggeration` | `0.3` | Chatterbox voice expressiveness |
| `tts.cfg_weight` | `0.4` | Chatterbox classifier-free guidance |

### Push notification mapping

Edit `~/.claude/hooks/voxhook/notify/notification_mapping.json` to customize notification titles and messages for different hook events.

## Architecture

```
~/.claude/hooks/voxhook/
├── common/              # Shared enums and utilities
│   ├── __init__.py
│   ├── enums.py         # HookEvent, ToolName, etc.
│   └── utils.py         # Safe enum conversion, categorization
├── notify/              # Push notifications
│   ├── handler.py       # Main handler (reads stdin, sends ntfy)
│   ├── notification_mapping.json
│   └── test.py
└── tts/                 # Voice cloning TTS
    ├── handler.py       # Fast path: pick message, play cached WAV
    ├── generate.py      # Heavy path: Chatterbox voice cloning
    ├── message_templates.py  # Template loader
    ├── cache_manager.py # WAV cache with LRU eviction
    ├── config.json
    ├── templates.json   # Active message templates
    ├── reference/
    │   └── voice.wav    # Your reference voice
    └── cache/           # Generated WAV files
```

**Handler flow** (TTS):
1. Read hook JSON from stdin
2. Select message from templates
3. Look up WAV in cache by content hash
4. If cached: play via `afplay` (non-blocking)
5. If not cached: play any fallback, spawn `generate.py` in background
6. Optionally send ntfy push notification

**Generator flow**:
1. Load Chatterbox model (MPS/CUDA/CPU)
2. Clone reference voice to generate speech
3. Save WAV to cache with content-hash filename

## Pre-generating audio

Generate all template messages upfront for instant playback:

```bash
uv run --python 3.11 ~/.claude/hooks/voxhook/tts/generate.py --pre-generate
```

## Uninstall

```bash
cd voxhook
./uninstall.sh
```

This removes `~/.claude/hooks/voxhook/` and cleans voxhook entries from `settings.json`, leaving your other hooks untouched.

## License

MIT
