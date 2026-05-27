#!/usr/bin/env bash
# dicton installer — zero prerequisites.
#
# Installs everything from a bare machine: system libs + C build toolchain
# (needed to compile the `evdev` extension on Linux), `uv`, `git`, then clones
# (or updates) the repo, installs `dicton`, and launches the first-run wizard.
#
# One-liner:
#   curl -fsSL https://raw.githubusercontent.com/Asi0Flammeus/dicton/main/install.sh | bash
#
# Local:
#   ./install.sh
set -euo pipefail

REPO_URL="https://github.com/Asi0Flammeus/dicton.git"
INSTALL_DIR="${DICTON_DIR:-$HOME/dicton}"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
info() { printf '» %s\n' "$1"; }
die()  { printf '\033[31mERREUR: %s\033[0m\n' "$1" >&2; exit 1; }

need_cmd() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
# 1. System dependencies (audio capture + clipboard/paste + C build toolchain)
# ---------------------------------------------------------------------------
install_system_deps() {
    local os
    os="$(uname -s)"

    if [ "$os" = "Darwin" ]; then
        need_cmd brew || die "Homebrew requis sur macOS : https://brew.sh"
        info "Dépendances système (Homebrew)"
        brew install portaudio || true
        return
    fi

    if [ "$os" != "Linux" ]; then
        die "OS non supporté par cet installeur : $os (voir README pour Windows)"
    fi

    # Clipboard/paste tools for BOTH session types: xclip+xdotool (X11) and
    # wl-clipboard+wtype (Wayland). xdotool is X11-only and can't inject into
    # native Wayland windows, so without wtype the paste silently fails in
    # Wayland-native apps. dicton prefers wl-copy/wtype when present.
    #
    # Detect the package manager rather than the distro name.
    if need_cmd apt-get; then
        info "Dépendances système (apt)"
        sudo apt-get update
        # build-essential + python3-dev: compile the evdev C extension (Python.h).
        sudo apt-get install -y \
            git build-essential python3-dev \
            libportaudio2 xclip xdotool wl-clipboard wtype playerctl
    elif need_cmd pacman; then
        info "Dépendances système (pacman)"
        # base-devel provides gcc/make; python headers ship with the python pkg.
        sudo pacman -S --needed --noconfirm \
            git base-devel python \
            portaudio xclip xdotool wl-clipboard wtype playerctl
    elif need_cmd dnf; then
        info "Dépendances système (dnf)"
        sudo dnf install -y \
            git gcc python3-devel \
            portaudio xclip xdotool wl-clipboard wtype playerctl
    elif need_cmd zypper; then
        info "Dépendances système (zypper)"
        sudo zypper install -y \
            git gcc python3-devel \
            portaudio xclip xdotool wl-clipboard wtype playerctl
    else
        die "Gestionnaire de paquets non reconnu. Installe à la main : git, gcc/make, python3-dev, portaudio, xclip, xdotool, wl-clipboard, wtype, playerctl"
    fi
}

# ---------------------------------------------------------------------------
# 1b. evdev access — the Fn / global hotkey listener reads /dev/input/event*,
#     which is owned by root:input (mode 660). Add the user to `input` so the
#     double-tap trigger and the wizard's live key-capture work without root.
# ---------------------------------------------------------------------------
grant_input_group() {
    [ "$(uname -s)" = "Linux" ] || return 0
    if id -nG "$USER" 2>/dev/null | tr ' ' '\n' | grep -qx input; then
        info "Groupe 'input' déjà accordé"
        return 0
    fi
    info "Ajout de $USER au groupe 'input' (accès clavier global)"
    sudo usermod -aG input "$USER" \
        && bold "⚠ Déconnecte/reconnecte ta session pour activer l'accès clavier (groupe 'input')." \
        || info "usermod a échoué — la hotkey Fn pourrait nécessiter root"
}

# ---------------------------------------------------------------------------
# 2. uv (Astral Python toolchain)
# ---------------------------------------------------------------------------
install_uv() {
    if need_cmd uv; then
        info "uv déjà présent ($(uv --version))"
        return
    fi
    info "Installation de uv"
    curl -fsSL https://astral.sh/uv/install.sh | sh
    # uv lands in ~/.local/bin; make it visible for the rest of this script.
    export PATH="$HOME/.local/bin:$PATH"
    need_cmd uv || die "uv installé mais introuvable dans le PATH ($HOME/.local/bin). Rouvre un terminal et relance."
}

# ---------------------------------------------------------------------------
# 3. Clone or update the repo, then install
# ---------------------------------------------------------------------------
get_source() {
    # If we're already inside the repo, install from here.
    if [ -f "pyproject.toml" ] && grep -q '^name = "dicton"' pyproject.toml 2>/dev/null; then
        SRC_DIR="$(pwd)"
        info "Install depuis le repo courant : $SRC_DIR"
        return
    fi

    if [ -d "$INSTALL_DIR/.git" ]; then
        info "Mise à jour du repo existant : $INSTALL_DIR"
        git -C "$INSTALL_DIR" pull --ff-only origin main
    else
        info "Clone du repo : $INSTALL_DIR"
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
    SRC_DIR="$INSTALL_DIR"
}

# ---------------------------------------------------------------------------
main() {
    bold "Installation de dicton"
    need_cmd curl || die "curl requis (installe-le : apt install curl)"

    install_system_deps
    grant_input_group
    install_uv
    get_source

    info "Installation du binaire dicton"
    ( cd "$SRC_DIR" && uv tool install --force . )

    export PATH="$HOME/.local/bin:$PATH"
    need_cmd dicton || die "dicton installé mais absent du PATH ($HOME/.local/bin). Ajoute-le à ton shell rc."

    bold "Lancement du wizard de configuration"
    exec dicton
}

main "$@"
