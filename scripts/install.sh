#!/bin/bash
# Dicton Installation Script
# Usage: ./scripts/install.sh

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_FILE="$PROJECT_DIR/scripts/dicton.service"
USER_SERVICE_DIR="$HOME/.config/systemd/user"
VENV_DIR="$PROJECT_DIR/venv"

echo "=== Dicton Setup ==="
echo "Project: $PROJECT_DIR"
echo ""

# Check for .env file
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "Creating .env from example..."
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    echo ""
    echo "!! IMPORTANT: Edit $PROJECT_DIR/.env to configure:"
    echo "   - STT_PROVIDER (gladia or elevenlabs)"
    echo "   - GLADIA_API_KEY or ELEVENLABS_API_KEY"
    echo ""
fi

# Create venv if not exists or is broken (check both python and pip)
if [ ! -d "$VENV_DIR" ] || ! "$VENV_DIR/bin/python" -m pip --version &>/dev/null; then
    echo "Creating virtual environment..."
    rm -rf "$VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi

# Install/upgrade dependencies
echo "Installing dependencies..."
"$VENV_DIR/bin/python" -m pip install -q --upgrade pip
"$VENV_DIR/bin/python" -m pip install -q -e "$PROJECT_DIR"

# Setup systemd user service
echo "Setting up systemd service..."
mkdir -p "$USER_SERVICE_DIR"

# Update service file with correct project path
sed "s|__PROJECT_DIR__|$PROJECT_DIR|g" "$SERVICE_FILE" > "$USER_SERVICE_DIR/dicton.service"

# Reload systemd
systemctl --user daemon-reload

# Enable service (auto-start on login)
systemctl --user enable dicton.service 2>/dev/null || true

# Restart if already running, otherwise start
if systemctl --user is-active --quiet dicton.service; then
    echo "Restarting dicton service..."
    systemctl --user restart dicton.service
else
    echo "Starting dicton service..."
    systemctl --user start dicton.service
fi

# Brief pause for startup
sleep 1

echo ""
echo "=== Setup Complete ==="
echo ""

# Show status
if systemctl --user is-active --quiet dicton.service; then
    echo "✓ Dicton is running"
    # Show which STT provider is active
    journalctl --user -u dicton -n 20 --no-pager 2>/dev/null | grep -E "Using.*STT|STT:" | tail -1 || true
else
    echo "✗ Dicton failed to start. Check logs:"
    echo "  journalctl --user -u dicton -n 50"
fi

echo ""
echo "Commands:"
echo "  Status:   systemctl --user status dicton"
echo "  Logs:     journalctl --user -u dicton -f"
echo "  Restart:  systemctl --user restart dicton"
echo "  Stop:     systemctl --user stop dicton"
echo ""
