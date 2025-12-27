#!/bin/bash
# Dicton System Installation
set -e

INSTALL_DIR="/opt/dicton"
BIN_LINK="/usr/local/bin/dicton"
SERVICE_FILE="/etc/systemd/user/dicton.service"

# User-level service file (takes precedence over system-level)
get_user_service_file() {
    local REAL_USER="${SUDO_USER:-$USER}"
    if [ -n "$REAL_USER" ] && [ "$REAL_USER" != "root" ]; then
        local USER_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
        echo "$USER_HOME/.config/systemd/user/dicton.service"
    fi
}

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

sync_user_service_file() {
    # If user has a local service file, update it to point to /opt/dicton
    # User-level service (~/.config/systemd/user/) takes precedence over system-level
    local USER_SERVICE=$(get_user_service_file)

    if [ -z "$USER_SERVICE" ]; then
        return
    fi

    if [ -f "$USER_SERVICE" ]; then
        echo -e "${YELLOW}Updating user service file: $USER_SERVICE${NC}"

        # Check if it points to a different location
        if grep -q "/opt/dicton" "$USER_SERVICE"; then
            echo -e "${GREEN}✓ User service already points to /opt/dicton${NC}"
        else
            # Update the service file to point to /opt/dicton
            cat > "$USER_SERVICE" <<'EOF'
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
            # Fix ownership
            local REAL_USER="${SUDO_USER:-$USER}"
            chown "$REAL_USER:$REAL_USER" "$USER_SERVICE"

            echo -e "${GREEN}✓ User service updated to use /opt/dicton${NC}"
        fi
    fi
}

reload_user_service() {
    # Run systemctl --user commands as the actual user (not root)
    local REAL_USER="${SUDO_USER:-$USER}"

    if [ -z "$REAL_USER" ] || [ "$REAL_USER" = "root" ]; then
        echo -e "${YELLOW}⚠ Run manually: systemctl --user daemon-reload && systemctl --user restart dicton${NC}"
        return
    fi

    local USER_ID=$(id -u "$REAL_USER")

    echo -e "${YELLOW}Reloading systemd user daemon...${NC}"
    if sudo -u "$REAL_USER" XDG_RUNTIME_DIR="/run/user/$USER_ID" systemctl --user daemon-reload 2>/dev/null; then
        echo -e "${GREEN}✓ Daemon reloaded${NC}"
    else
        echo -e "${YELLOW}⚠ Could not reload daemon (service may not be running)${NC}"
    fi

    echo -e "${YELLOW}Restarting dicton service...${NC}"
    if sudo -u "$REAL_USER" XDG_RUNTIME_DIR="/run/user/$USER_ID" systemctl --user restart dicton 2>/dev/null; then
        echo -e "${GREEN}✓ Service restarted${NC}"
    else
        echo -e "${YELLOW}⚠ Could not restart service (run: systemctl --user start dicton)${NC}"
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
    # Use [linux] extras for all Linux-specific features (fnkey, llm, xshape, notifications, gtk)
    # This is futureproof - new Linux dependencies added to pyproject.toml will be auto-installed
    "$INSTALL_DIR/venv/bin/pip" install "$INSTALL_DIR[linux]"
    echo -e "${GREEN}✓ Python packages installed${NC}"

    # Copy .env from source directory if it exists, otherwise use .env.example
    if [ -f ".env" ]; then
        cp ".env" "$INSTALL_DIR/.env"
        echo -e "${GREEN}✓ Copied .env from source directory${NC}"
    elif [ ! -f "$INSTALL_DIR/.env" ]; then
        cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
        echo -e "${YELLOW}Created .env from template - configure your API keys in $INSTALL_DIR/.env${NC}"
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

    # Update user-level service file if it exists (takes precedence over system-level)
    sync_user_service_file

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
    echo "  FN (hold)           - Push-to-talk (with auto-reformulation)"
    echo "  FN (double-tap)     - Toggle recording"
    echo "  FN + Ctrl           - Translate to English (toggle)"
    echo "  FN + Space          - Act on Text (toggle)"
    echo ""
    echo "Config: $INSTALL_DIR/.env"
    echo ""
    echo -e "${YELLOW}⚠ IMPORTANT: Log out and back in for FN key to work${NC}"
}

sync_env_config() {
    # Sync missing config fields from .env.example to .env
    local env_file="$1"
    local example_file="$2"
    local added=0
    local key=""

    if [ ! -f "$env_file" ]; then
        cp "$example_file" "$env_file"
        echo -e "${GREEN}✓ Created .env from template${NC}"
        return
    fi

    if [ ! -f "$example_file" ]; then
        return
    fi

    # Extract all KEY=value lines from .env.example (ignore comments and empty lines)
    while IFS= read -r line || [ -n "$line" ]; do
        # Skip empty lines and comments
        [[ -z "$line" ]] && continue
        [[ "$line" =~ ^[[:space:]]*# ]] && continue

        # Extract the key (everything before first =)
        key=$(echo "$line" | cut -d'=' -f1)

        # Validate key format (must start with letter or underscore)
        if [[ ! "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
            continue
        fi

        # Check if this key exists in .env (as KEY= at start of line)
        if ! grep -q "^${key}=" "$env_file" 2>/dev/null; then
            # Key is missing, append it with the default value
            echo "" >> "$env_file"
            echo "# Added by update on $(date +%Y-%m-%d)" >> "$env_file"
            echo "$line" >> "$env_file"
            echo -e "${YELLOW}  + Added missing config: ${key}${NC}"
            ((added++)) || true
        fi
    done < "$example_file"

    if [ $added -gt 0 ]; then
        echo -e "${GREEN}✓ Added $added new config option(s) to .env${NC}"
    else
        echo -e "${GREEN}✓ Config is up to date${NC}"
    fi
}

update_dicton() {
    check_root

    if [ ! -d "$INSTALL_DIR" ]; then
        echo -e "${RED}Dicton not installed. Run: sudo $0 install${NC}"
        exit 1
    fi

    echo -e "${YELLOW}Updating Dicton...${NC}"

    # Update source files
    cp -r src "$INSTALL_DIR/"
    cp pyproject.toml "$INSTALL_DIR/"
    cp README.md "$INSTALL_DIR/"
    cp .env.example "$INSTALL_DIR/"

    # Update .env: use source .env if exists, otherwise keep existing
    if [ -f ".env" ]; then
        cp ".env" "$INSTALL_DIR/.env"
        echo -e "${GREEN}✓ Updated .env from source directory${NC}"
    fi

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
    # Use [linux] extras - futureproof, picks up any new dependencies from pyproject.toml
    "$INSTALL_DIR/venv/bin/pip" install --upgrade "$INSTALL_DIR[linux]"
    echo -e "${GREEN}✓ Python packages updated${NC}"

    # Sync any new config options from .env.example
    echo -e "${YELLOW}Checking for new config options...${NC}"
    sync_env_config "$INSTALL_DIR/.env" "$INSTALL_DIR/.env.example"

    # Ensure launcher script exists
    if [ ! -f "$BIN_LINK" ]; then
        echo -e "${YELLOW}Creating launcher script...${NC}"
        cat > "$BIN_LINK" <<'EOF'
#!/bin/bash
cd /opt/dicton
exec /opt/dicton/venv/bin/dicton "$@"
EOF
        chmod +x "$BIN_LINK"
        echo -e "${GREEN}✓ Launcher created${NC}"
    fi

    # Update user-level service file if it exists
    sync_user_service_file

    # Update version
    echo "$(date +%Y%m%d)" > "$INSTALL_DIR/VERSION"

    # Reload and restart service
    reload_user_service

    echo -e "${GREEN}✓ Dicton updated${NC}"
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
