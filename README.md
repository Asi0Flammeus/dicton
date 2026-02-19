<p align="center">
  <img src="src/dicton/assets/logo.png" alt="Dicton Logo" width="600">
</p>

<p align="center">
  <a href="https://github.com/Asi0Flammeus/dicton/actions/workflows/ci.yml"><img src="https://github.com/Asi0Flammeus/dicton/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/dicton/"><img src="https://img.shields.io/pypi/v/dicton" alt="PyPI"></a>
  <a href="https://pypi.org/project/dicton/"><img src="https://img.shields.io/pypi/pyversions/dicton" alt="Python Version"></a>
  <a href="https://github.com/Asi0Flammeus/dicton/blob/main/LICENSE"><img src="https://img.shields.io/github/license/Asi0Flammeus/dicton" alt="License"></a>
</p>

# Dicton

A fast, low-latency voice-to-text dictation tool for Linux. Press the FN key to start recording, release to transcribe directly at your cursor position.

## Features

- **FN Key Activation**: Use your laptop's FN key for seamless push-to-talk dictation
- **Multiple Processing Modes**: Basic transcription, translation, LLM reformulation
- **Real-time Visualizer**: Animated toric ring shows audio levels with mode-specific colors
- **ElevenLabs STT**: Fast, accurate transcription via ElevenLabs Scribe API
- **LLM Enhancement**: Optional text cleanup and translation via Gemini or Anthropic (with automatic fallback)
- **System-wide**: Works in any application where you can type
- **Low Latency**: Optimized pipeline for natural dictation flow

## Hotkey System

Dicton uses the **FN key** (XF86WakeUp) as the primary trigger, with modifier keys for different modes.

### Basic Mode (FN only)
| Action | Behavior |
|--------|----------|
| **Hold FN** | Push-to-talk: records while held, transcribes on release |
| **Double-tap FN** | Toggle mode: tap to start, tap again to stop |

### Processing Modes

| Hotkey | Mode | Ring Color | Description |
|--------|------|------------|-------------|
| FN | Basic | Orange | Transcribe with auto-reformulation |
| FN + Ctrl | Translation | Green | Transcribe and translate to English |
| FN + Alt | Reformulation | Purple | LLM-powered text cleanup |
| FN + Shift | Act on Text | Magenta | **(WIP)** Apply instruction to selected text |
| FN + Space | Raw | Yellow | Raw transcription, no processing |

> **Note**: Act on Text mode is experimental and still under development.

### Visual Feedback
- **Animated ring**: Recording in progress
- **Ring color**: Indicates active processing mode
- **No ring**: Idle state

## Requirements

### Linux (Primary Platform)
- Python 3.10+
- X11 or Wayland (with XWayland)
- System packages: `xdotool`, `libnotify-bin`, `xclip` (or `wl-clipboard` for Wayland)
- ElevenLabs API key ([get one here](https://elevenlabs.io/))
- LLM API key (optional, for text cleanup and translation):
  - Gemini API key ([get one here](https://aistudio.google.com/app/apikey)), or
  - Anthropic API key ([get one here](https://console.anthropic.com/settings/keys))

### Other Platforms
- Windows and macOS have basic support but FN key mode is Linux-only
- Use `Alt+G` hotkey on other platforms

## Installation

### Quick Install (System-wide)

```bash
# Clone the repository
git clone https://github.com/Asi0Flammeus/dicton.git
cd dicton

# Install system-wide (requires sudo)
sudo ./install.sh install

# Configure API keys
sudo nano /opt/dicton/.env
# Set: ELEVENLABS_API_KEY=your_key
# Set: GEMINI_API_KEY=your_key (optional, for LLM features)
# Or:  ANTHROPIC_API_KEY=your_key (alternative LLM provider)

# Add user to input group (required for FN key)
sudo usermod -aG input $USER
# Log out and back in

# Run
dicton
```

### User Install (pip)

```bash
# Install from PyPI
pip install dicton[fnkey]

# Create config directory
mkdir -p ~/.config/dicton

# Add API keys
echo "ELEVENLABS_API_KEY=your_key" > ~/.config/dicton/.env
# Add one or both LLM providers (Gemini is default, Anthropic as fallback)
echo "GEMINI_API_KEY=your_key" >> ~/.config/dicton/.env
echo "ANTHROPIC_API_KEY=your_key" >> ~/.config/dicton/.env

# Run
dicton
```

### System Dependencies

**Debian/Ubuntu:**
```bash
sudo apt install python3-venv python3-dev portaudio19-dev xdotool libnotify-bin xclip
# For Wayland:
sudo apt install wl-clipboard
```

**Arch Linux:**
```bash
sudo pacman -S python portaudio xdotool libnotify xclip
# For Wayland:
sudo pacman -S wl-clipboard
```

## Configuration

Configuration is read from (in order):
1. `./.env` (current directory)
2. `~/.config/dicton/.env` (user config)
3. `/opt/dicton/.env` (system install)

### Environment Variables

```bash
# Required
ELEVENLABS_API_KEY=your_elevenlabs_key

# Optional - LLM Features
LLM_PROVIDER=gemini             # "gemini" (default) or "anthropic"
GEMINI_API_KEY=your_gemini_key
ANTHROPIC_API_KEY=your_anthropic_key
ENABLE_REFORMULATION=true       # Enable LLM-powered text cleanup

# Hotkey Settings
HOTKEY_BASE=fn                    # "fn" for FN key, "alt+g" for legacy
HOTKEY_HOLD_THRESHOLD_MS=100      # Hold duration for PTT vs tap
HOTKEY_DOUBLE_TAP_WINDOW_MS=300   # Window for double-tap detection
HOTKEY_ACTIVATION_DELAY_MS=50     # Delay before activation (avoids double-tap confusion)

# Language
LANGUAGE=auto                     # auto, en, fr, de, es, etc.

# Visualizer
THEME_COLOR=orange                # Ring color (overridden by mode)
ANIMATION_POSITION=top-right      # top-right, top-left, center, etc.
VISUALIZER_STYLE=toric            # toric, classic, minimalistic

# Audio
MIC_DEVICE=auto                   # auto or device index
SAMPLE_RATE=16000

# Debug
DEBUG=false
```

## Usage

### Starting Dicton

```bash
# Run directly
dicton

# Or as a systemd service
systemctl --user start dicton
systemctl --user enable dicton  # Auto-start on login
```

### Dictation Workflow

1. **Position cursor** where you want text inserted
2. **Hold FN** and speak (push-to-talk)
3. **Release FN** to transcribe and insert text

Or use **double-tap** for longer recordings:
1. **Tap FN twice** to start recording (ring appears)
2. Speak your content
3. **Tap FN** again to stop and transcribe

### Translation Mode

1. **Hold FN + Ctrl** and speak in any language
2. **Release** to get English translation

### LLM Reformulation

1. **Hold FN + Alt** and speak naturally
2. **Release** to get cleaned-up text (removes fillers, fixes grammar)

## Service Management (Linux)

```bash
# Start/stop service
systemctl --user start dicton
systemctl --user stop dicton

# Enable auto-start
systemctl --user enable dicton

# View logs
journalctl --user -u dicton -f

# Check status
systemctl --user status dicton
```

## Context-Aware Dictation

Dicton can detect your active application context to adapt LLM prompts and typing behavior.

### How It Works

When you start recording, Dicton detects:
- **Active window** (class, title)
- **Widget focus** (text field, terminal, editor)
- **Terminal context** (shell, tmux session, current directory)

This context is matched against profiles that customize:
- LLM prompt preambles (e.g., "User is writing Python code")
- Typing speed (fast for messaging, slow for terminals)
- Text formatting preferences

### Configuration

Enable/disable context detection via the dashboard's **Context** tab at `http://localhost:8765`.

Custom profiles can be added to `~/.config/dicton/contexts.json`:

```json
{
  "profiles": {
    "my_editor": {
      "match": {
        "wm_class": ["my-custom-editor"],
        "window_title_contains": ["project"]
      },
      "llm_preamble": "User is coding. Use technical vocabulary.",
      "typing_speed": "fast"
    }
  }
}
```

### Platform Requirements

#### Linux (X11)
Context detection works out of the box. Optional enhanced widget detection requires:
```bash
# Debian/Ubuntu
sudo apt install python3-pyatspi at-spi2-core
```

#### Linux (Wayland/GNOME)
GNOME requires a D-Bus extension for window detection:

1. Install **[Focused Window D-Bus](https://extensions.gnome.org/extension/5592/focused-window-d-bus/)** from GNOME Extensions
2. Or install **[Window Calls Extended](https://extensions.gnome.org/extension/4974/window-calls-extended/)**
3. Enable the extension and restart Dicton

Without the extension, context detection gracefully falls back to limited information.

#### Linux (Wayland/Sway/Hyprland)
Native support via compositor CLI tools (`swaymsg`, `hyprctl`). No additional setup required.

#### Windows
Context detection uses Windows UI Automation API:
```powershell
# Usually pre-installed on Windows 10/11
# If missing, install:
pip install pywin32 comtypes
```

### Debugging

Enable context debug output:
```bash
CONTEXT_DEBUG=true dicton
```

This logs detected context and matched profiles to help troubleshoot detection issues.

---

## Troubleshooting

### FN Key Not Detected

```bash
# Check if user is in input group
groups | grep input

# If not, add and re-login
sudo usermod -aG input $USER
```

### No Audio Captured

```bash
# List audio devices
arecord -l
pactl list sources short

# Set specific device in .env
MIC_DEVICE=1
```

### Text Not Inserting

```bash
# Ensure xdotool is installed
which xdotool

# For Wayland, ensure XWayland is running
echo $XDG_SESSION_TYPE
```

### Visualizer Not Showing

- Ensure X11/XWayland is available
- Check pygame installation: `pip show pygame`
- Try: `VISUALIZER_STYLE=terminal` for terminal-based feedback

### Context Detection Not Working

**GNOME/Wayland:**
```bash
# Check if extension is installed
gnome-extensions list | grep -i focus
# Should show: focused-window-d-bus@example.com or similar

# If not installed, visit:
# https://extensions.gnome.org/extension/5592/focused-window-d-bus/
```

**X11 (Widget Focus):**
```bash
# Install AT-SPI accessibility framework
sudo apt install python3-pyatspi at-spi2-core

# Verify AT-SPI is running
dbus-send --session --print-reply \
  --dest=org.a11y.Bus /org/a11y/bus \
  org.a11y.Bus.GetAddress
```

**Windows:**
```powershell
# Verify pywin32 is installed
pip show pywin32 comtypes

# If missing:
pip install pywin32 comtypes
```

**Debug context detection:**
```bash
# Enable verbose logging
CONTEXT_DEBUG=true dicton
# Look for "Context:" and "Profile:" lines in output
```

## Project Structure

```
dicton/
├── src/dicton/
│   ├── main.py                    # Application entry point
│   ├── config.py                  # Configuration management
│   ├── fn_key_handler.py          # FN key capture via evdev
│   ├── speech_recognition_engine.py # ElevenLabs STT
│   ├── llm_processor.py           # LLM integration (Gemini/Anthropic)
│   ├── keyboard_handler.py        # Text insertion (xdotool)
│   ├── visualizer.py              # Toric ring visualizer
│   ├── selection_handler.py       # X11/Wayland selection
│   └── processing_mode.py         # Mode definitions
├── install.sh                     # Linux installer
├── pyproject.toml                 # Package configuration
└── README.md
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `elevenlabs` | Speech-to-text API |
| `mistralai` | Mistral STT API (alternative) |
| `google-genai` | Gemini LLM API |
| `anthropic` | Anthropic LLM API (alternative) |
| `evdev` | FN key capture (Linux) |
| `pyaudio` | Audio capture |
| `pygame` | Audio visualizer |
| `numpy` | Audio processing |
| `python-dotenv` | Configuration |

## STT Provider Comparison

Dicton supports multiple speech-to-text providers. Choose based on your priorities:

### Quick Comparison

| | ElevenLabs Scribe | Mistral Voxtral |
|--|-------------------|-----------------|
| **Best For** | Multi-language, streaming | Cost-sensitive, batch |
| **Cost** | $0.40/hour | $0.06/hour |
| **Accuracy (EN)** | ~4-6% WER | 1.2-5.1% WER |
| **Languages** | 90+ | 8 major |
| **Batch Speed** | ~10s/min audio | ~3s/min audio |
| **Streaming** | Yes (150ms) | No |

### When to Choose ElevenLabs

- You need **90+ language** support
- You want **real-time streaming** transcription
- You need **speaker diarization** (who said what)
- Audio files are **longer than 15 minutes**

### When to Choose Mistral

- **Cost is a priority** (85% cheaper)
- You primarily use **English, French, German, Spanish, Portuguese, Italian, Dutch, or Hindi**
- You prefer **faster batch processing** (~3x faster)
- You want **better accuracy** on major languages

### Configuration

```bash
# Use ElevenLabs (default)
STT_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=your_key

# Use Mistral Voxtral
STT_PROVIDER=mistral
MISTRAL_API_KEY=your_key
```

### Detailed Metrics

| Metric | ElevenLabs Scribe | Mistral Voxtral |
|--------|-------------------|-----------------|
| **Pricing** | $0.0067/min | $0.001/min |
| **English WER** | ~4-6% | 1.2% (LibriSpeech) |
| **Processing Speed** | 6-7x real-time | 20x real-time |
| **Max Audio Duration** | 10 hours | ~15 minutes |
| **Streaming Latency** | 150ms | N/A (batch only) |
| **Word Timestamps** | Yes | Yes (segments) |
| **Speaker Diarization** | Yes (48 speakers) | No |

> **Note**: Word Error Rate (WER) varies by audio quality, accent, and domain. Lower is better.

## Uninstall

```bash
# System-wide installation
sudo ./install.sh uninstall

# User service
systemctl --user stop dicton
systemctl --user disable dicton
rm ~/.config/systemd/user/dicton.service
pip uninstall dicton
```

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Architecture Overview

Dicton uses a small core orchestration layer with thin adapters for platform
and vendor integrations. This keeps the dictation pipeline easy to test and
extend without touching platform-specific code.

Core modules (new):
- `src/dicton/core/ports.py`: core interfaces.
- `src/dicton/core/controller.py`: record → transcribe → process → output flow.
- `src/dicton/core/state_machine.py`: explicit session state transitions.
- `src/dicton/core/cancel_token.py`: cancellation for in-flight sessions.

Adapters (new):
- `src/dicton/adapters/audio.py`: audio capture + STT adapters.
- `src/dicton/adapters/text_processing.py`: text processing/output adapters.
- `src/dicton/adapters/ui_feedback.py`: notifications.
- `src/dicton/adapters/llm.py`: LLM bridge.
- `src/dicton/adapters/config_env.py`: structured config view from env.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- [ElevenLabs](https://elevenlabs.io/) - Speech-to-text API
- [Mistral AI](https://mistral.ai/) - Alternative STT provider (Voxtral)
- [Google Gemini](https://ai.google.dev/) - LLM for text processing
- [Anthropic Claude](https://www.anthropic.com/) - Alternative LLM provider
- [Flexoki](https://github.com/kepano/flexoki) - Color palette for mode indicators
