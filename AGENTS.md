# CLAUDE.md - Dicton Project Guidelines

## Project Vision

**Dicton** is a Linux speech-to-text dictation tool designed for seamless, low-friction voice input:

- **Real-time audio visualization** with transparent overlay (toric ring design)
- **FN-key based activation** with push-to-talk (hold) and toggle recording (double-tap)
- **Extensible processing modes** for translation, reformulation, and context-aware output
- **Minimal latency** pipeline optimized for natural dictation flow

### Core Principles
1. **Single-key simplicity**: FN key is the universal trigger
2. **Visual mode awareness**: Ring color instantly communicates active mode
3. **Phased extensibility**: Start simple (FN only), add modifiers as features mature

---

## Visual Feedback Color Convention

The visualizer ring uses **dedicated colors per processing mode** from the [Flexoki palette](https://github.com/kepano/flexoki). Color indicates the type of processing applied, not the gesture type (hold vs double-tap).

| Mode | Trigger | Behavior | Flexoki Color | Hex (glow) |
|------|---------|----------|---------------|------------|
| Basic + Reformulation | FN (hold or double-tap) | PTT or toggle | Orange | `#DA702C` |
| Translation to EN | FN + Ctrl | Toggle only | Green | `#879A39` |
| **Act on Text** *(WIP)* | FN + Shift | Toggle only | **Magenta** | `#CE5D97` |
| Translate + Reformat | FN + Ctrl + Shift | Toggle only | Cyan | `#3AA99F` |
| LLM Reformulation | FN + Alt | Toggle only | Purple | `#8B7EC8` |
| Raw Mode (no processing) | FN + Space | Toggle only | Yellow | `#D0A215` |

### Key Principles
- **Reformulation by default**: Basic FN transcription includes automatic LLM cleanup
- **Toggle for advanced modes**: FN+modifier uses toggle (press to start, press to stop)
- **PTT only for basic**: Only plain FN supports push-to-talk (hold) mode
- **Color = mode**: Ring color instantly indicates active processing mode

### Visual States
- **Animated ring**: Active recording in progress
- **Solid ring**: Toggle mode locked (recording continues)
- **No ring**: Idle state

---

## Hotkey Behavior

### Basic Mode (FN only)
- **Hold**: Push-to-talk - recording while held, processes on release
- **Double-tap**: Toggle mode - tap to start, tap again to stop
- **Processing**: Automatic LLM reformulation (removes fillers, cleans grammar)

### Advanced Modes (FN + modifier)
All advanced modes use **toggle-only** behavior:
1. Press FN + modifier → Start recording (colored ring appears)
2. Speak your content
3. Press FN + modifier again → Stop and process

| Combo | Mode | Description |
|-------|------|-------------|
| FN + Ctrl | Translation | Transcribe and translate to English |
| FN + Shift | Act on Text *(WIP)* | Apply voice instruction to selected text |
| FN + Alt | Reformulation | LLM-powered text cleanup |
| FN + Space | Raw | No processing, raw STT output |

---

## Versioning Convention

This project uses semantic versioning tied to `.claude/TODO.md` progress:

- **## (Heading 2) completed** → Bump **minor version** (e.g., v1.0.0 → v1.1.0)
  - Push tags: `git tag -a vX.Y.0 -m "Phase description"`
  - Create GitHub release

- **### (Heading 3) completed** → Bump **patch version** (e.g., v1.0.0 → v1.0.1)
  - Push tags: `git tag -a vX.Y.Z -m "Section description"`
  - Push to GitHub

- **After ### release** → Remove that subsection from `.claude/TODO.md`
  - Keep only pending work in TODO.md
  - Completed sections are tracked via git tags/releases

## Commit Convention

This project follows [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` - New features
- `fix:` - Bug fixes
- `chore:` - Maintenance tasks (deps, configs)
- `docs:` - Documentation changes
- `refactor:` - Code refactoring without feature changes
- `test:` - Adding or updating tests
- `style:` - Code style/formatting changes

Examples:
```
feat: add visualizer color configuration
fix: skip DC component in FFT to fix first frequency spike
chore: update install script
```

## Project Structure

- `src/` - Main source code
  - `visualizer.py` - Pygame-based audio visualizer
  - `visualizer_vispy.py` - VisPy-based audio visualizer (alternative)
  - `config.py` - Configuration management
  - `speech_recognition_engine.py` - Main STT engine
  - `keyboard_handler.py` - Keyboard input handling

## Configuration

Key environment variables:
- `VISUALIZER_BACKEND` - "pygame" (default) or "vispy"
- `VISUALIZER_STYLE` - "toric", "classic", "legacy", "minimalistic", "terminal"
- `ANIMATION_POSITION` - "top-right", "top-left", "center", etc.

---

## STT Provider Architecture

Dicton uses a provider-based architecture for speech-to-text, allowing multiple backends with automatic fallback.

### Available Providers

| Provider | Module | Config Key | Cost |
|----------|--------|------------|------|
| Mistral Voxtral | `stt_mistral.py` | `MISTRAL_API_KEY` | $0.06/hr |
| ElevenLabs Scribe | `stt_elevenlabs.py` | `ELEVENLABS_API_KEY` | $0.40/hr |

### Provider Selection

The `STT_PROVIDER` environment variable controls provider selection:

```bash
# Use specific provider
STT_PROVIDER=mistral   # Use only Mistral
STT_PROVIDER=elevenlabs # Use only ElevenLabs

# Auto mode (default) - tries in order, falls back if unavailable
STT_PROVIDER=auto
```

### Architecture

```
SpeechRecognizer → STT Factory → Provider
                       ↓
              [Mistral] → [ElevenLabs] → [NullProvider]
```

- `stt_provider.py`: Base `STTProvider` protocol and `NullSTTProvider`
- `stt_factory.py`: Provider instantiation with fallback chain
- `stt_mistral.py`, `stt_elevenlabs.py`: Concrete provider implementations

### Adding New Providers

1. Create `stt_<name>.py` implementing `STTProvider` protocol
2. Register in `stt_factory.py:_register_providers()`
3. Add to `DEFAULT_FALLBACK_ORDER` if appropriate

### Troubleshooting

- **"No STT provider available"**: Check API keys in `.env`
- **Provider not switching**: Clear cache with `clear_provider_cache()` or restart
- **Fallback not working**: Verify both providers have valid API keys
