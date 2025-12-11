# Push-to-Write (P2W) 🎤

A fast, **online-first** voice-to-text application for Linux that transcribes your speech directly at the cursor position. Simply press `Alt+T`, speak, and watch your words appear instantly!

## ✨ Features

- **🚀 Online API Mode**: Fast, accurate transcription using OpenAI Whisper API (primary method)
- **🔌 Offline Fallback**: Works offline using faster-whisper when API unavailable
- **⚡ Real-time Streaming**: Text appears as you speak (~1-2 second transcription per chunk)
- **🌍 Multilingual**: Supports English and French with auto-detection
- **🎯 System-wide**: Works in any application where you can type
- **🔧 Configurable**: Customize hotkeys, language, API key, and audio settings
- **💻 System Tray**: Convenient system tray integration with quick settings
- **🔔 Notifications**: Visual feedback for recording status
- **🔄 Smart Fallback**: Automatically switches to local model if API fails

## 📋 Requirements

- Ubuntu/Debian-based Linux distribution
- Python 3.8 or higher
- PulseAudio or ALSA audio system
- X11 window system (for keyboard/mouse automation)

## 🚀 Installation

### Quick Install

```bash
git clone https://github.com/yourusername/push-to-write.git
cd push-to-write
chmod +x install.sh
./install.sh
```

The installer will:

1. Install system dependencies (portaudio, ffmpeg, etc.)
2. Create a Python virtual environment
3. Install Python packages including Whisper
4. Download the offline speech model
5. Create desktop and command-line launchers

### Manual Installation

```bash
# Install system dependencies
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv python3-dev \
    portaudio19-dev python3-pyaudio ffmpeg libportaudio2 \
    libasound2-dev xclip xdotool python3-tk

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python packages
pip install -r requirements.txt

# Copy configuration
cp .env.example .env

# Run the application
python src/main.py
```

## 🎮 Usage

### Starting the Application

**Option 1: Command Line**

```bash
p2w
```

**Option 2: Desktop**
Search for "Push-to-Write" in your applications menu

**Option 3: Direct**

```bash
cd /path/to/push-to-write
./venv/bin/python src/main.py
```

### Using Push-to-Write

1. Start the application
2. Press `Alt+T` (default hotkey) to start recording
3. Speak clearly into your microphone
4. **Two ways to stop:**
   - Pause for 1.5 seconds (silence auto-stops)
   - Press `Alt+T` again to manually stop
5. Text appears at your cursor position!

### System Tray Menu

Right-click the system tray icon to:

- Change language:
  - 🌍 Auto-detect (English/French) - Automatically detects which language you're speaking
  - 🇬🇧 English - Force English transcription
  - 🇫🇷 French - Force French transcription
- View current hotkey
- Quit application

## ⚙️ Configuration

### Quick Start: Get Your API Key

1. Sign up at [OpenAI Platform](https://platform.openai.com/)
2. Go to [API Keys](https://platform.openai.com/api-keys)
3. Create a new API key
4. Add it to your `.env` file

### Configuration File

Edit the `.env` file to customize:

```bash
# Language settings
DEFAULT_LANGUAGE=auto  # Options: auto (detect), en (English), fr (French)

# OpenAI API (Primary - Fast and Accurate)
OPENAI_API_KEY=your_openai_api_key_here  # Required for online mode

# Local Whisper (Fallback if API unavailable)
WHISPER_MODEL=large    # Options: tiny, base, small, medium, large (used only as fallback)

# Streaming transcription (text appears as you speak)
STREAMING_MODE=true    # true = real-time, false = batch mode
CHUNK_DURATION=3.0     # Transcribe every 3 seconds (fast with online API)

# Keyboard shortcut
HOTKEY_MODIFIER=alt    # Options: alt, ctrl, shift
HOTKEY_KEY=t

# Audio settings
AUDIO_TIMEOUT=30       # Maximum recording time in seconds
SILENCE_DURATION=1.5   # Seconds of silence to stop recording
SILENCE_THRESHOLD=300  # Lower = more sensitive to silence

# UI settings
SHOW_TRAY_ICON=false   # Set to false if tray icon causes issues
SHOW_NOTIFICATIONS=true
```

**Note**: Without an API key, the app will automatically use the local Whisper model (slower but works offline).

### Whisper Model Sizes

| Model  | Size    | Speed       | Quality   | Recommended For        |
| ------ | ------- | ----------- | --------- | ---------------------- |
| tiny   | 39 MB   | Ultra-fast  | Basic     | Quick drafts           |
| base   | 74 MB   | Very fast   | Good      | Casual use             |
| small  | 244 MB  | Fast        | Very Good | Fast transcription     |
| medium | 769 MB  | Good        | Excellent | High quality           |
| large  | 1550 MB | Medium      | **Best**  | **Default - Maximum accuracy** |

**Note**: With `faster-whisper`, even the "large" model runs reasonably fast!

## 🔧 Troubleshooting

### ALSA/JACK Warnings on Startup

**Symptom**: Console shows ALSA/JACK errors like "unable to open slave", "jack server is not running"

**Solution**: These warnings are harmless! The program works correctly. They appear because PyAudio scans multiple audio backends before finding one that works. The latest version suppresses these warnings automatically.

If you still see them, ensure you have the latest code:
```bash
git pull origin main
```

### Desktop Notifications Not Working

**Symptom**: Warning about `python-dbus` package or notification service

**Solution**: Install the DBus package for Python (optional):
```bash
sudo apt-get install python3-dbus
```

Or the program will automatically fall back to `notify-send` command (usually pre-installed).

### No Audio Input Detected

```bash
# Check audio devices
pactl list sources

# Test microphone
arecord -d 5 test.wav && aplay test.wav
```

### Permission Errors

```bash
# Add user to audio group
sudo usermod -a -G audio $USER
# Log out and back in
```

### Whisper Model Download Issues

```bash
# Manually download model
python3 -c "import whisper; whisper.load_model('base')"
```

### System Tray Icon Errors

**Symptom**: Errors about pystray, _xorg, or "Failed to dock icon"

**Solution**: Disable the system tray icon (the app works fine without it):
```bash
export SHOW_TRAY_ICON=false
p2w
```

Or edit `.env`:
```bash
SHOW_TRAY_ICON=false
```

The app will work perfectly without the tray icon. You can still change settings via environment variables.

### Keyboard Shortcuts Not Working

- Ensure you're running X11 (not Wayland)
- Check if another application is using the same hotkey
- Try running with sudo (for testing only)

## 🏗️ Project Structure

```
push-to-write/
├── src/
│   ├── main.py                 # Main application
│   ├── config.py               # Configuration management
│   ├── speech_recognition_engine.py  # Whisper integration
│   ├── keyboard_handler.py    # Hotkey and text insertion
│   └── ui_feedback.py         # System tray and notifications
├── models/                     # Whisper model cache
├── .env                        # User configuration
├── requirements.txt            # Python dependencies
├── install.sh                  # Installation script
└── README.md                   # Documentation
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit pull requests.

## 📄 License

MIT License - feel free to use this project however you'd like!

## 🙏 Acknowledgments

- [OpenAI Whisper](https://github.com/openai/whisper) for offline speech recognition
- [pynput](https://github.com/moses-palmer/pynput) for keyboard handling
- [pyaudio](https://people.csail.mit.edu/hubert/pyaudio/) for audio capture

## 💡 Tips

- **Streaming mode** (default): Text appears as you speak - great for real-time writing
- **Batch mode** (`STREAMING_MODE=false`): Transcribe all at once after you finish - better for short commands
- The `large` model offers maximum quality (default)
- For maximum speed, use `tiny` model and `CHUNK_DURATION=1.5`
- For maximum accuracy, use `medium` or `large` model
- The first run will download the Whisper model (one-time download)
- Works best in quiet environments
- Speak clearly and at a normal pace
- With streaming, text appears as you speak (every 5 seconds by default)
- Press the hotkey again to manually stop recording

## ⚙️ Performance Tuning

### With OpenAI API (Recommended - Default)

**Default settings (fast and accurate):**
```bash
OPENAI_API_KEY=your_key_here
CHUNK_DURATION=3.0
```

The API uses **OpenAI Whisper** (`whisper-1`) for quality and speed:
- **Speed**: ~2-3 seconds per chunk (much faster than local)
- **Quality**: High accuracy with smart prompting
- **Reduced hallucinations**: Built-in filtering and validation
- **Auto language detection**: Seamlessly handles English/French
- **No local GPU needed**: Works on any hardware

### Without API (Local Mode)

If you don't have an API key, the app uses local models:

**Maximum Quality (slower):**
```bash
WHISPER_MODEL=large
CHUNK_DURATION=5.0
```

**High Quality (faster):**
```bash
WHISPER_MODEL=medium
CHUNK_DURATION=4.0
```

**Fast Mode (good quality):**
```bash
WHISPER_MODEL=small
CHUNK_DURATION=3.0
```

**Quick Drafts (fastest local):**
```bash
WHISPER_MODEL=base
CHUNK_DURATION=2.5
```

**Important**: Chunk duration should match model size. Too short chunks with large models cause garbled output and hallucinations.

### Other Settings

**Disable streaming (batch mode):**
```bash
STREAMING_MODE=false
```

