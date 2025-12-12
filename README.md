# Push-to-Write (P2W)

A fast voice-to-text application that transcribes your speech directly at the cursor position. Press `Alt+T` to start recording, press again to stop and transcribe!

**Supported Platforms:** Linux (X11), Windows, macOS

## Features

- **ElevenLabs STT**: Fast, accurate transcription using ElevenLabs Speech-to-Text API
- **System-wide**: Works in any application where you can type
- **Audio Visualizer**: Elegant circular waveform display while recording
- **Multilingual**: Supports auto language detection and manual language selection
- **Notifications**: Desktop notifications for recording status
- **Configurable**: Customize hotkeys, language, and microphone settings
- **Toggle Recording**: Press hotkey to start, press again to stop
- **Visual Feedback**: Animated donut visualizer shows audio levels in real-time

## Requirements

### All Platforms
- Python 3.10 or higher
- ElevenLabs API key ([get one here](https://elevenlabs.io/app/settings/api-keys))

### Linux
- PulseAudio or ALSA audio system
- X11 window system (for xdotool keyboard automation)
- System packages: `xdotool`, `libnotify-bin`

### Windows
- Windows 10 or later
- Working microphone
- No additional system packages required

### macOS
- macOS 10.15 or later
- Microphone access permissions

## Installation

### Windows

**Option 1: Batch Script**
```cmd
REM Clone or download the repository
cd push-to-write

REM Run installer
install.bat

REM Configure API key
copy .env.example .env
notepad .env
REM Add your ELEVENLABS_API_KEY

REM Run
run.bat
```

**Option 2: PowerShell**
```powershell
# Clone or download the repository
cd push-to-write

# Run installer
powershell -ExecutionPolicy Bypass -File scripts\install.ps1

# Configure API key
Copy-Item .env.example .env
notepad .env
# Add your ELEVENLABS_API_KEY

# Run
.\run.bat
```

**Note on PyAudio (Windows):** If PyAudio installation fails:
```cmd
pip install pipwin
pipwin install pyaudio
```
Or download a wheel from: https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio

### Linux

**Quick Install (Local)**
```bash
# Clone the repository
git clone https://github.com/yourusername/push-to-write.git
cd push-to-write

# Run the install script
chmod +x scripts/install.sh
./scripts/install.sh

# Add your API key
nano .env
# Set: ELEVENLABS_API_KEY=your_key_here

# Start the service
systemctl --user start p2w
```

**System-wide Install (with sudo)**
```bash
# Install system-wide to /opt/p2w
sudo ./install.sh install

# Edit configuration
sudo nano /opt/p2w/.env

# Run manually
p2w

# Or enable as systemd service
systemctl --user enable p2w
systemctl --user start p2w
```

**System Dependencies (Linux)**

Debian/Ubuntu:
```bash
sudo apt install python3-venv python3-dev portaudio19-dev xdotool libnotify-bin
```

Arch Linux:
```bash
sudo pacman -S python portaudio xdotool libnotify
```

### macOS

```bash
# Clone the repository
git clone https://github.com/yourusername/push-to-write.git
cd push-to-write

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# If PyAudio fails, install portaudio first:
brew install portaudio
pip install pyaudio

# Configure
cp .env.example .env
nano .env
# Add your ELEVENLABS_API_KEY

# Run
python src/main.py
```

## Usage

### Starting the Application

**Windows:**
```cmd
run.bat
```

**Linux (Service - recommended):**
```bash
systemctl --user start p2w
```

**Linux/macOS (Command Line):**
```bash
cd /path/to/push-to-write
source venv/bin/activate  # or: venv\Scripts\activate on Windows
python src/main.py
```

### Recording Workflow

1. Start the application
2. Press `Alt+T` to **start recording** (visualizer appears)
3. Speak clearly into your microphone
4. Press `Alt+T` again to **stop recording**
5. Wait briefly for transcription
6. Text appears at your cursor position!

| Action | Result |
|--------|--------|
| Press `Alt+T` | Start recording (visualizer shows) |
| Press `Alt+T` again | Stop recording, transcribe, insert text |
| `Ctrl+C` | Quit the application |

## Configuration

Edit the `.env` file to customize:

```bash
# ElevenLabs API (required)
ELEVENLABS_API_KEY=your_elevenlabs_key_here

# ElevenLabs STT model
ELEVENLABS_MODEL=scribe_v1

# Keyboard shortcut
HOTKEY_MODIFIER=alt    # Options: alt, ctrl
HOTKEY_KEY=t           # Any key

# Language: auto, en, fr, de, es, etc. (ISO-639-1 codes)
# Set to "auto" for automatic language detection
LANGUAGE=auto

# Microphone: auto or device index number
# Run with DEBUG=true to see available devices
MIC_DEVICE=auto

# Local fallback model (only used if no API key)
WHISPER_MODEL=base
USE_CUDA=false

# Debug output
DEBUG=false
```

### Getting Your API Key

1. Sign up at [ElevenLabs](https://elevenlabs.io/)
2. Go to [API Settings](https://elevenlabs.io/app/settings/api-keys)
3. Create a new API key
4. Add it to your `.env` file

## Project Structure

```
push-to-write/
├── src/
│   ├── main.py                      # Main application entry point
│   ├── config.py                    # Configuration management
│   ├── platform_utils.py            # Cross-platform detection
│   ├── speech_recognition_engine.py # ElevenLabs STT integration
│   ├── keyboard_handler.py          # Hotkey detection and text insertion
│   ├── visualizer.py                # Circular audio visualizer (pygame)
│   └── ui_feedback.py               # Desktop notifications
├── scripts/
│   ├── install.sh                   # Linux installation script
│   ├── install.ps1                  # Windows PowerShell installer
│   └── p2w.service                  # Systemd service template
├── assets/
│   └── icon.png                     # Application icon
├── .env.example                     # Configuration template
├── requirements.txt                 # Python dependencies
├── install.sh                       # Linux system-wide installer
├── install.bat                      # Windows batch installer
├── run.bat                          # Windows launcher
├── run.sh                           # Linux launcher
├── SETUP.md                         # Detailed setup guide
└── README.md                        # This file
```

## Dependencies

Core dependencies (from `requirements.txt`):

| Package | Purpose |
|---------|---------|
| `elevenlabs` | Speech-to-text API client |
| `pyaudio` | Audio capture |
| `pynput` | Keyboard hotkey detection |
| `pygame` | Audio visualizer |
| `python-dotenv` | Environment configuration |
| `numpy` | Audio processing |
| `plyer` | Cross-platform notifications |
| `pyautogui` | Cross-platform text insertion (Windows) |

## Platform-Specific Notes

### Windows
- Text insertion uses `pyautogui` (with `pynput` fallback)
- Notifications use Windows Toast via `plyer`
- No admin rights required for normal operation

### Linux
- Text insertion uses `xdotool` (with `pynput` fallback)
- Notifications use `notify-send` (with `plyer` fallback)
- X11 required for visualizer window positioning
- Wayland support is limited

### macOS
- Text insertion uses `pynput`
- Notifications use native AppleScript
- May require accessibility permissions for keyboard control

## Service Management (Linux)

```bash
# Start the service
systemctl --user start p2w

# Stop the service
systemctl --user stop p2w

# Enable auto-start on login
systemctl --user enable p2w

# Disable auto-start
systemctl --user disable p2w

# View status
systemctl --user status p2w

# View logs
journalctl --user -u p2w -f
```

## Troubleshooting

### No Microphone Detected

**Linux:**
```bash
# List available audio devices
arecord -l

# Or check with PulseAudio
pactl list sources short

# Set specific device in .env
MIC_DEVICE=1
```

**Windows:**
- Check Windows Sound Settings > Recording devices
- Set `MIC_DEVICE=auto` or specific device index in `.env`

### Visualizer Not Showing

- Linux: Ensure X11 is running (not Wayland): `echo $XDG_SESSION_TYPE`
- Check pygame installation: `pip show pygame`
- Try running with `DEBUG=true` for more info

### Keyboard Shortcuts Not Working

- Linux: Ensure you're running X11 (not Wayland)
- Check if another application uses `Alt+T`
- Try a different hotkey in `.env`
- Windows: Run as administrator if needed

### Text Not Inserting (Windows)

- Ensure `pyautogui` is installed: `pip install pyautogui`
- Some applications may block automated input
- Try clicking in the target text field first

### Permission Denied for Input (Linux)

```bash
# Add user to input group
sudo usermod -aG input $USER
# Log out and back in
```

### Service Won't Start (Linux)

```bash
# Check logs
journalctl --user -u p2w -n 50

# Verify display is set
echo $DISPLAY  # Should be :0 or :1
```

### ALSA/JACK Warnings

These are harmless! PyAudio scans multiple backends. The warnings are suppressed automatically.

## Uninstall

**Windows:**
```cmd
REM Delete the project folder
rmdir /s /q push-to-write
```

**Linux (Local installation):**
```bash
systemctl --user stop p2w
systemctl --user disable p2w
rm ~/.config/systemd/user/p2w.service
systemctl --user daemon-reload
```

**Linux (System-wide installation):**
```bash
sudo ./install.sh uninstall
```

## Contributing

Contributions are welcome! Please feel free to submit pull requests.

## License

MIT License - feel free to use this project however you'd like!

## Acknowledgments

- [ElevenLabs](https://elevenlabs.io/) for the speech-to-text API
- [pynput](https://github.com/moses-palmer/pynput) for keyboard handling
- [PyAudio](https://people.csail.mit.edu/hubert/pyaudio/) for audio capture
- [Pygame](https://www.pygame.org/) for the visualizer
- [plyer](https://github.com/kivy/plyer) for cross-platform notifications

## Tips

- Speak clearly and at a normal pace for best results
- The visualizer shows when audio is being captured
- Works best in quiet environments
- The first transcription may be slightly slower (API warmup)
- Keep recordings under 30 seconds for faster processing
