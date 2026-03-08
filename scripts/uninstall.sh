#!/usr/bin/env bash
# Dicton Uninstall Script — full system reset
# Usage: ./scripts/uninstall.sh [--keep-config] [--dry-run]
set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BOLD='\033[1m'
RESET='\033[0m'

# ── Flags ─────────────────────────────────────────────────────────
KEEP_CONFIG=false
DRY_RUN=false

for arg in "$@"; do
    case "$arg" in
        --keep-config) KEEP_CONFIG=true ;;
        --dry-run)     DRY_RUN=true ;;
        -h|--help)
            cat <<'EOF'
Usage: ./scripts/uninstall.sh [--keep-config] [--dry-run]

  --keep-config  Preserve ~/.config/dicton/ (API keys, dictionary, contexts)
  --dry-run      Print what would be removed without actually removing anything
EOF
            exit 0
            ;;
        *)
            echo "Unknown option: $arg" >&2
            exit 1
            ;;
    esac
done

# ── Helpers ───────────────────────────────────────────────────────
removed=()
skipped=()

info()    { echo -e "${BOLD}==> $1${RESET}"; }
ok()      { echo -e "  ${GREEN}✓ $1${RESET}"; removed+=("$1"); }
skip()    { echo -e "  ${YELLOW}· $1${RESET}"; skipped+=("$1"); }
dry()     { echo -e "  ${YELLOW}[dry-run] would: $1${RESET}"; }

run_or_dry() {
    if $DRY_RUN; then
        dry "$1"
    else
        eval "$2"
        ok "$1"
    fi
}

remove_path() {
    local label="$1" path="$2"
    if [[ -e "$path" ]]; then
        run_or_dry "remove $label ($path)" "rm -rf '$path'"
    else
        skip "$label not found ($path)"
    fi
}

# ── Banner ────────────────────────────────────────────────────────
echo ""
info "Dicton Uninstall"
$DRY_RUN && echo -e "  ${YELLOW}(dry-run mode — nothing will be removed)${RESET}"
$KEEP_CONFIG && echo -e "  ${YELLOW}(--keep-config — ~/.config/dicton/ will be preserved)${RESET}"
echo ""

# ── 1. Stop running process ──────────────────────────────────────
info "Stopping running processes"
if systemctl --user is-active --quiet dicton.service 2>/dev/null; then
    run_or_dry "stop dicton.service" "systemctl --user stop dicton.service"
else
    skip "dicton.service not active"
fi

if pgrep -f 'dicton' >/dev/null 2>&1; then
    run_or_dry "kill remaining dicton processes" "pkill -f 'dicton' || true"
else
    skip "no dicton processes running"
fi

# ── 2. Remove .deb package ───────────────────────────────────────
info "Removing .deb package"
if dpkg -s dicton &>/dev/null; then
    run_or_dry "remove dicton .deb package" "sudo dpkg -r dicton"
else
    skip ".deb package not installed"
fi

# ── 3. Remove pip/pipx install ───────────────────────────────────
info "Removing pip/pipx install"
if command -v dicton &>/dev/null; then
    # Check pipx first, then pip
    if command -v pipx &>/dev/null && pipx list 2>/dev/null | grep -q dicton; then
        run_or_dry "uninstall dicton via pipx" "pipx uninstall dicton"
    else
        run_or_dry "uninstall dicton via pip" "pip uninstall -y dicton 2>/dev/null || pip3 uninstall -y dicton 2>/dev/null || true"
    fi
else
    skip "dicton not found in PATH (pip/pipx)"
fi

# ── 4. Disable + remove systemd service ──────────────────────────
info "Removing systemd user service"
SERVICE_FILE="$HOME/.config/systemd/user/dicton.service"
if [[ -f "$SERVICE_FILE" ]]; then
    run_or_dry "disable dicton.service" "systemctl --user disable dicton.service 2>/dev/null || true"
    run_or_dry "remove $SERVICE_FILE" "rm -f '$SERVICE_FILE'"
    run_or_dry "reload systemd daemon" "systemctl --user daemon-reload"
else
    skip "systemd service file not found"
fi

# ── 5. Remove autostart desktop entry ────────────────────────────
info "Removing autostart entry"
remove_path "autostart desktop entry" "$HOME/.config/autostart/dicton.desktop"

# ── 6. Remove user directories ───────────────────────────────────
info "Removing user data"

if $KEEP_CONFIG; then
    skip "config dir preserved (--keep-config): ~/.config/dicton/"
else
    remove_path "config dir" "$HOME/.config/dicton"
fi

remove_path "data dir"  "$HOME/.local/share/dicton"
remove_path "cache dir" "$HOME/.cache/dicton"

# ── Summary ───────────────────────────────────────────────────────
echo ""
info "Summary"
if [[ ${#removed[@]} -gt 0 ]]; then
    echo -e "  ${GREEN}Removed (${#removed[@]}):${RESET}"
    for item in "${removed[@]}"; do
        echo -e "    ${GREEN}✓${RESET} $item"
    done
fi
if [[ ${#skipped[@]} -gt 0 ]]; then
    echo -e "  ${YELLOW}Skipped (${#skipped[@]}):${RESET}"
    for item in "${skipped[@]}"; do
        echo -e "    ${YELLOW}·${RESET} $item"
    done
fi
echo ""
