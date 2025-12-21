# Dicton Setup Guide

Voice transcription tool using ElevenLabs STT. Press hotkey to start recording, press again to stop and transcribe.

**Supported Platforms:** Linux (X11), Windows, macOS

## Quick Install

### Linux

```bash
# 1. Clone and enter directory
cd /path/to/dicton

# 2. Run install script
chmod +x scripts/install.sh
./scripts/install.sh

# 3. Add your API key
nano .env
# Set: ELEVENLABS_API_KEY=your_key_here

# 4. Start the service
systemctl --user start dicton
```

### Windows

```cmd
REM 1. Enter directory
cd path\to\dicton

REM 2. Run installer
install.bat

REM 3. Add your API key
copy .env.example .env
notepad .env
REM Set: ELEVENLABS_API_KEY=your_key_here

REM 4. Run
run.bat
```

### macOS

```bash
# 1. Enter directory
cd /path/to/dicton

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
brew install portaudio  # if PyAudio fails
pip install -r requirements.txt

# 4. Add your API key
cp .env.example .env
nano .env
# Set: ELEVENLABS_API_KEY=your_key_here

# 5. Run
python src/main.py
```

## Requirements

### All Platforms
- Python 3.10+
- ElevenLabs API key ([get one here](https://elevenlabs.io/app/settings/api-keys))

### Linux
- PulseAudio or ALSA (for microphone)
- X11 display server

### Windows
- Windows 10 or later
- Working microphone

### macOS
- macOS 10.15+
- Microphone permissions

### System Dependencies (Debian/Ubuntu)

```bash
sudo apt install python3-venv python3-dev portaudio19-dev xdotool libnotify-bin
```

### System Dependencies (Arch)

```bash
sudo pacman -S python portaudio xdotool libnotify
```

## Configuration

Edit `.env` to customize:

```bash
# Required
ELEVENLABS_API_KEY=your_key_here

# Optional
ELEVENLABS_MODEL=scribe_v1      # STT model
HOTKEY_MODIFIER=alt             # alt, ctrl
HOTKEY_KEY=t                    # any key
LANGUAGE=auto                   # auto, en, fr, de, etc.
MIC_DEVICE=auto                 # auto or device index
DEBUG=false                     # show debug output
```

## Usage

| Action | Result |
|--------|--------|
| Press `Alt+T` | Start recording (visualizer appears) |
| Press `Alt+T` again | Stop recording, transcribe, type text |
| `Ctrl+C` | Stop the application |

## Service Management (Linux)

```bash
# Start/stop
systemctl --user start dicton
systemctl --user stop dicton

# View status
systemctl --user status dicton

# View logs
journalctl --user -u dicton -f

# Disable auto-start
systemctl --user disable dicton

# Re-enable auto-start
systemctl --user enable dicton
```

## Manual Run (without service)

**Linux/macOS:**
```bash
cd /path/to/dicton
source .venv/bin/activate  # or: source venv/bin/activate
python src/main.py
```

**Windows:**
```cmd
cd path\to\dicton
venv\Scripts\activate.bat
python src\main.py
```

## Updating

### Local Installation (all platforms)

```bash
# 1. Stop the application/service
# Linux:
systemctl --user stop dicton
# Windows/macOS: Close the application (Ctrl+C)

# 2. Pull the latest changes
cd /path/to/dicton
git pull origin main

# 3. Activate virtual environment
# Linux/macOS:
source .venv/bin/activate  # or: source venv/bin/activate
# Windows:
venv\Scripts\activate.bat

# 4. Update dependencies
pip install -r requirements.txt --upgrade

# 5. Restart
# Linux:
systemctl --user start dicton
# Windows:
run.bat
# macOS:
python src/main.py
```

### System-wide Installation (Linux /opt/dicton)

Pour mettre à jour une installation système dans `/opt/dicton`:

```bash
# 1. Stop the service
systemctl --user stop dicton

# 2. Pull the latest changes (as root)
cd /opt/dicton
sudo git pull origin main

# 3. Update dependencies
sudo /opt/dicton/.venv/bin/pip install -r requirements.txt --upgrade

# 4. If the service file has changed, reload it
sudo cp /opt/dicton/scripts/dicton.service /etc/systemd/user/dicton.service
systemctl --user daemon-reload

# 5. Restart the service
systemctl --user start dicton
```

**Script de mise à jour rapide:**

```bash
# Create update script
sudo tee /opt/dicton/update.sh << 'EOF'
#!/bin/bash
set -e

echo "Updating Dicton..."

# Stop service
systemctl --user stop dicton 2>/dev/null || true

# Update code
cd /opt/dicton
git pull origin main

# Update dependencies
.venv/bin/pip install -r requirements.txt --upgrade --quiet

# Reload service if needed
if [ -f /etc/systemd/user/dicton.service ]; then
    cp scripts/dicton.service /etc/systemd/user/dicton.service
    systemctl --user daemon-reload
fi

# Restart
systemctl --user start dicton

echo "Update complete!"
systemctl --user status dicton --no-pager
EOF

sudo chmod +x /opt/dicton/update.sh
```

Ensuite, pour mettre à jour:
```bash
sudo /opt/dicton/update.sh
```

### Vérifier la version

```bash
# Voir les derniers commits
cd /opt/dicton  # ou le chemin de votre installation
git log --oneline -5

# Voir la branche actuelle
git branch -v
```

### Revenir à une version précédente

Si une mise à jour pose problème:

```bash
# 1. Stop the service
systemctl --user stop dicton

# 2. List available versions
cd /opt/dicton
git log --oneline -20

# 3. Revert to a specific commit
git checkout <commit_hash>

# 4. Restart
systemctl --user start dicton
```

Pour revenir à la dernière version après un rollback:
```bash
git checkout main
git pull origin main
```

## Troubleshooting

### No microphone detected

**Linux:**
```bash
# List audio devices
arecord -l

# Set specific device in .env
MIC_DEVICE=1
```

**Windows:**
- Check Windows Sound Settings > Recording devices
- Set `MIC_DEVICE=auto` or device index in `.env`

### Service won't start (Linux)

```bash
# Check logs
journalctl --user -u dicton -n 50

# Verify display
echo $DISPLAY  # Should be :0 or :1
```

### Visualizer not showing

- Linux: Ensure X11 is running (not Wayland): `echo $XDG_SESSION_TYPE`
- Check if pygame is installed: `pip show pygame`

### Permission denied for input (Linux)

```bash
# Add user to input group
sudo usermod -aG input $USER
# Log out and back in
```

### Text not inserting (Windows)

- Ensure `pyautogui` is installed: `pip install pyautogui`
- Some applications may block automated input
- Try running as administrator

### PyAudio installation fails (Windows)

```cmd
pip install pipwin
pipwin install pyaudio
```

Or download from: https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio

## Uninstall

### Local Installation

**Linux:**
```bash
systemctl --user stop dicton
systemctl --user disable dicton
rm ~/.config/systemd/user/dicton.service
systemctl --user daemon-reload
rm -rf /path/to/dicton
```

**Windows:**
```cmd
REM Just delete the folder
rmdir /s /q path\to\dicton
```

### System-wide Installation (Linux)

```bash
sudo /opt/dicton/install.sh uninstall
```

Ou manuellement:
```bash
systemctl --user stop dicton
systemctl --user disable dicton
sudo rm /usr/local/bin/dicton
sudo rm /etc/systemd/user/dicton.service
sudo rm -rf /opt/dicton
systemctl --user daemon-reload
```
