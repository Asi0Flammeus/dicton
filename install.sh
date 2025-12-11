#!/bin/bash
# Push-to-Write System Installation
set -e

INSTALL_DIR="/opt/p2w"
BIN_LINK="/usr/local/bin/p2w"
SERVICE_FILE="/etc/systemd/user/p2w.service"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

usage() {
    echo "Usage: $0 [install|update|uninstall]"
    echo "  install   - Install P2W system-wide"
    echo "  update    - Update to latest version"
    echo "  uninstall - Remove P2W from system"
    exit 1
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}Please run with sudo${NC}"
        exit 1
    fi
}

install_deps() {
    echo -e "${YELLOW}Installing system dependencies...${NC}"
    apt-get update -qq
    apt-get install -y -qq \
        python3-pip python3-venv python3-dev \
        portaudio19-dev libportaudio2 \
        xdotool libnotify-bin
    echo -e "${GREEN}✓ Dependencies installed${NC}"
}

install_p2w() {
    check_root

    echo -e "${YELLOW}Installing Push-to-Write...${NC}"

    # Install system deps
    install_deps

    # Create install directory
    mkdir -p "$INSTALL_DIR"

    # Copy source files
    cp -r src "$INSTALL_DIR/"
    cp requirements.txt "$INSTALL_DIR/"
    cp .env.example "$INSTALL_DIR/"

    # Create venv and install packages
    python3 -m venv "$INSTALL_DIR/venv"
    "$INSTALL_DIR/venv/bin/pip" install -q --upgrade pip
    "$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

    # Create config if not exists
    if [ ! -f "$INSTALL_DIR/.env" ]; then
        cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    fi

    # Create launcher script
    cat > "$BIN_LINK" <<'EOF'
#!/bin/bash
cd /opt/p2w
exec /opt/p2w/venv/bin/python src/main.py "$@"
EOF
    chmod +x "$BIN_LINK"

    # Create systemd user service
    mkdir -p "$(dirname "$SERVICE_FILE")"
    cat > "$SERVICE_FILE" <<'EOF'
[Unit]
Description=Push-to-Write Voice Transcription
After=graphical-session.target

[Service]
Type=simple
ExecStart=/opt/p2w/venv/bin/python /opt/p2w/src/main.py
Restart=on-failure
RestartSec=5
Environment=DISPLAY=:0

[Install]
WantedBy=default.target
EOF

    # Store version
    echo "$(date +%Y%m%d)" > "$INSTALL_DIR/VERSION"

    echo -e "${GREEN}✓ P2W installed${NC}"
    echo ""
    echo "Usage:"
    echo "  p2w              - Run manually"
    echo "  systemctl --user enable p2w   - Enable autostart"
    echo "  systemctl --user start p2w    - Start as service"
    echo ""
    echo "Config: $INSTALL_DIR/.env"
}

update_p2w() {
    check_root

    if [ ! -d "$INSTALL_DIR" ]; then
        echo -e "${RED}P2W not installed. Run: sudo $0 install${NC}"
        exit 1
    fi

    echo -e "${YELLOW}Updating Push-to-Write...${NC}"

    # Backup config
    cp "$INSTALL_DIR/.env" /tmp/p2w.env.bak 2>/dev/null || true

    # Update source files
    cp -r src "$INSTALL_DIR/"
    cp requirements.txt "$INSTALL_DIR/"

    # Update packages
    "$INSTALL_DIR/venv/bin/pip" install -q --upgrade -r "$INSTALL_DIR/requirements.txt"

    # Restore config
    cp /tmp/p2w.env.bak "$INSTALL_DIR/.env" 2>/dev/null || true

    # Update version
    echo "$(date +%Y%m%d)" > "$INSTALL_DIR/VERSION"

    echo -e "${GREEN}✓ P2W updated${NC}"
    echo "Restart service: systemctl --user restart p2w"
}

uninstall_p2w() {
    check_root

    echo -e "${YELLOW}Uninstalling Push-to-Write...${NC}"

    # Stop service if running
    systemctl --user stop p2w 2>/dev/null || true
    systemctl --user disable p2w 2>/dev/null || true

    # Remove files
    rm -rf "$INSTALL_DIR"
    rm -f "$BIN_LINK"
    rm -f "$SERVICE_FILE"

    echo -e "${GREEN}✓ P2W uninstalled${NC}"
}

case "${1:-install}" in
    install)  install_p2w ;;
    update)   update_p2w ;;
    uninstall) uninstall_p2w ;;
    *)        usage ;;
esac
