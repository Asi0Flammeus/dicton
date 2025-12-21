#!/bin/bash
# Dicton Installation Script

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_FILE="$PROJECT_DIR/scripts/dicton.service"
USER_SERVICE_DIR="$HOME/.config/systemd/user"

echo "=== Dicton Setup ==="
echo ""

# Check for .env file
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "Creating .env from example..."
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    echo "!! Edit $PROJECT_DIR/.env and add your ELEVENLABS_API_KEY"
    echo ""
fi

# Create venv if not exists
if [ ! -d "$PROJECT_DIR/.venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$PROJECT_DIR/.venv"
fi

# Install dependencies
echo "Installing dependencies..."
"$PROJECT_DIR/.venv/bin/pip" install -q -r "$PROJECT_DIR/requirements.txt"

# Setup systemd user service
echo "Setting up systemd service..."
mkdir -p "$USER_SERVICE_DIR"

# Update service file with correct paths
sed "s|/home/asi0/asi0-repos/S2T_P2W|$PROJECT_DIR|g" "$SERVICE_FILE" > "$USER_SERVICE_DIR/dicton.service"

# Reload and enable
systemctl --user daemon-reload
systemctl --user enable dicton.service

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Commands:"
echo "  Start now:     systemctl --user start dicton"
echo "  Stop:          systemctl --user stop dicton"
echo "  Status:        systemctl --user status dicton"
echo "  Logs:          journalctl --user -u dicton -f"
echo "  Disable:       systemctl --user disable dicton"
echo ""
echo "The service will auto-start on login."
echo "Hotkey: Alt+T (hold to record, release to transcribe)"
