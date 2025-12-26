#!/bin/bash
# Dicton System Installation
set -e

INSTALL_DIR="/opt/dicton"
BIN_LINK="/usr/local/bin/dicton"
SERVICE_FILE="/etc/systemd/user/dicton.service"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

usage() {
    echo "Usage: $0 [install|update|uninstall]"
    echo "  install   - Install Dicton system-wide"
    echo "  update    - Update to latest version"
    echo "  uninstall - Remove Dicton from system"
    exit 1
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}Please run with sudo${NC}"
        exit 1
    fi
}

spinner() {
    local pid=$1
    local msg=$2
    local spin='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    local i=0
    while kill -0 "$pid" 2>/dev/null; do
        printf "\r${YELLOW}${spin:$i:1} ${msg}...${NC}"
        i=$(( (i + 1) % 10 ))
        sleep 0.1
    done
    wait "$pid"
    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        printf "\r${GREEN}✓ ${msg}${NC}    \n"
    else
        printf "\r${RED}✗ ${msg} failed${NC}    \n"
        exit $exit_code
    fi
}

install_deps() {
    echo -e "${YELLOW}Installing system dependencies...${NC}"
    apt-get update
    apt-get install -y  \
        python3-pip python3-venv python3-dev \
        portaudio19-dev libportaudio2 \
        xdotool xclip libnotify-bin \
        libgtk-3-dev libcairo2-dev libgirepository1.0-dev gir1.2-gtk-3.0
    echo -e "${GREEN}✓ Dependencies installed${NC}"
}

setup_input_group() {
    # Add user to input group for FN key access via evdev
    local REAL_USER="${SUDO_USER:-$USER}"

    if [ -z "$REAL_USER" ] || [ "$REAL_USER" = "root" ]; then
        echo -e "${YELLOW}⚠ Could not determine user for input group${NC}"
        return
    fi

    if groups "$REAL_USER" | grep -q '\binput\b'; then
        echo -e "${GREEN}✓ User '$REAL_USER' already in input group${NC}"
    else
        echo -e "${YELLOW}Adding '$REAL_USER' to input group for FN key support...${NC}"
        usermod -aG input "$REAL_USER"
        echo -e "${GREEN}✓ User '$REAL_USER' added to input group${NC}"
        echo -e "${YELLOW}⚠ Log out and back in for group change to take effect${NC}"
    fi
}

install_dicton() {
    check_root

    echo -e "${YELLOW}Installing Dicton...${NC}"

    # Install system deps
    install_deps

    # Setup input group for FN key
    setup_input_group

    # Create install directory
    mkdir -p "$INSTALL_DIR"

    # Copy project files
    cp -r src "$INSTALL_DIR/"
    cp pyproject.toml "$INSTALL_DIR/"
    cp README.md "$INSTALL_DIR/"
    cp .env.example "$INSTALL_DIR/"

    # Create venv and install packages
    python3 -m venv "$INSTALL_DIR/venv"

    echo -e "${YELLOW}Upgrading pip...${NC}"
    "$INSTALL_DIR/venv/bin/pip" install --upgrade pip

    echo -e "${YELLOW}Installing Python packages...${NC}"
    "$INSTALL_DIR/venv/bin/pip" install "$INSTALL_DIR[xshape,fnkey,llm]"
    echo -e "${GREEN}✓ Python packages installed${NC}"

    # Create config if not exists
    if [ ! -f "$INSTALL_DIR/.env" ]; then
        cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    fi

    # Create launcher script
    cat > "$BIN_LINK" <<'EOF'
#!/bin/bash
cd /opt/dicton
exec /opt/dicton/venv/bin/dicton "$@"
EOF
    chmod +x "$BIN_LINK"

    # Create systemd user service
    mkdir -p "$(dirname "$SERVICE_FILE")"
    cat > "$SERVICE_FILE" <<'EOF'
[Unit]
Description=Dicton Voice Transcription
After=graphical-session.target

[Service]
Type=simple
ExecStart=/opt/dicton/venv/bin/dicton
WorkingDirectory=/opt/dicton
Restart=on-failure
RestartSec=5
Environment=DISPLAY=:0

[Install]
WantedBy=default.target
EOF

    # Store version
    echo "$(date +%Y%m%d)" > "$INSTALL_DIR/VERSION"

    echo -e "${GREEN}✓ Dicton installed${NC}"
    echo ""
    echo "Usage:"
    echo "  dicton              - Run manually"
    echo "  systemctl --user enable dicton   - Enable autostart"
    echo "  systemctl --user start dicton    - Start as service"
    echo ""
    echo "Hotkeys:"
    echo "  FN (hold)           - Push-to-talk"
    echo "  FN (double-tap)     - Toggle recording"
    echo "  FN + Space          - Act on Text (LLM)"
    echo ""
    echo "Config: $INSTALL_DIR/.env"
    echo ""
    echo -e "${YELLOW}⚠ IMPORTANT: Log out and back in for FN key to work${NC}"
}

update_dicton() {
    check_root

    if [ ! -d "$INSTALL_DIR" ]; then
        echo -e "${RED}Dicton not installed. Run: sudo $0 install${NC}"
        exit 1
    fi

    echo -e "${YELLOW}Updating Dicton...${NC}"

    # Backup config
    cp "$INSTALL_DIR/.env" /tmp/dicton.env.bak 2>/dev/null || true

    # Update source files
    cp -r src "$INSTALL_DIR/"
    cp pyproject.toml "$INSTALL_DIR/"
    cp README.md "$INSTALL_DIR/"

    # Recreate venv if missing
    if [ ! -f "$INSTALL_DIR/venv/bin/pip" ]; then
        echo -e "${YELLOW}Recreating virtual environment...${NC}"
        python3 -m venv "$INSTALL_DIR/venv"
        "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
    fi

    # Setup input group for FN key (in case it wasn't done before)
    setup_input_group

    # Update packages
    echo -e "${YELLOW}Updating Python packages...${NC}"
    "$INSTALL_DIR/venv/bin/pip" install --upgrade "$INSTALL_DIR[xshape,fnkey,llm]"
    echo -e "${GREEN}✓ Python packages updated${NC}"

    # Restore config
    cp /tmp/dicton.env.bak "$INSTALL_DIR/.env" 2>/dev/null || true

    # Update version
    echo "$(date +%Y%m%d)" > "$INSTALL_DIR/VERSION"

    echo -e "${GREEN}✓ Dicton updated${NC}"
    echo "Restart service: systemctl --user restart dicton"
}

uninstall_dicton() {
    check_root

    echo -e "${YELLOW}Uninstalling Dicton...${NC}"

    # Stop service if running
    systemctl --user stop dicton 2>/dev/null || true
    systemctl --user disable dicton 2>/dev/null || true

    # Remove files
    rm -rf "$INSTALL_DIR"
    rm -f "$BIN_LINK"
    rm -f "$SERVICE_FILE"

    echo -e "${GREEN}✓ Dicton uninstalled${NC}"
}

case "${1:-install}" in
    install)  install_dicton ;;
    update)   update_dicton ;;
    uninstall) uninstall_dicton ;;
    *)        usage ;;
esac
