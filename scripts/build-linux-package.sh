#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST_DIR="${PROJECT_DIR}/dist"
STAGE_DIR="${PROJECT_DIR}/build/linux-deb"
BUNDLE_DIR="${DIST_DIR}/dicton"

cd "${PROJECT_DIR}"

version="$(python3 - <<'PY'
import re
from pathlib import Path

content = Path("src/dicton/__init__.py").read_text(encoding="utf-8")
match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
if not match:
    raise SystemExit("Unable to determine Dicton version")
print(match.group(1))
PY
)"

echo "==> Building Dicton Linux bundle"
python3 -m PyInstaller --noconfirm --clean packaging/linux/dicton.spec

if [[ ! -d "${BUNDLE_DIR}" ]]; then
    echo "Expected bundle directory not found: ${BUNDLE_DIR}" >&2
    exit 1
fi

tarball_path="${DIST_DIR}/dicton-linux-x64.tar.gz"
echo "==> Creating Linux tarball: ${tarball_path}"
tar -C "${DIST_DIR}" -czf "${tarball_path}" dicton

echo "==> Creating Debian package staging area"
rm -rf "${STAGE_DIR}"
mkdir -p "${STAGE_DIR}/DEBIAN" "${STAGE_DIR}/opt/dicton" "${STAGE_DIR}/usr/bin"

cp -a "${BUNDLE_DIR}/." "${STAGE_DIR}/opt/dicton/"

cat > "${STAGE_DIR}/usr/bin/dicton" <<'EOF'
#!/bin/sh
exec /opt/dicton/dicton "$@"
EOF
chmod 0755 "${STAGE_DIR}/usr/bin/dicton"

cat > "${STAGE_DIR}/DEBIAN/control" <<EOF
Package: dicton
Version: ${version}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: asi0 flammeus <asi0@crqpt.com>
Depends: libportaudio2, xdotool, libnotify-bin, gir1.2-ayatanaappindicator3-0.1
Recommends: xclip | wl-clipboard
Description: Voice-to-text dictation with direct transcription and translation
 Dicton is a desktop dictation tool focused on direct transcription and
 translation to English, packaged here as a Linux one-folder bundle.
EOF

cat > "${STAGE_DIR}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e

TARGET_USER="${SUDO_USER:-$(logname 2>/dev/null || echo '')}"

# Check if the installing user is in the 'input' group
if [ -n "$TARGET_USER" ]; then
    if ! groups "$TARGET_USER" 2>/dev/null | grep -qw input; then
        echo ""
        echo "╔══════════════════════════════════════════════════════════════╗"
        echo "║  Dicton needs access to /dev/input/* for hotkey detection.  ║"
        echo "║  Run: sudo usermod -aG input $TARGET_USER                    ║"
        echo "║  Then log out and log back in for the change to take effect.║"
        echo "╚══════════════════════════════════════════════════════════════╝"
        echo ""
    fi
fi

# Restart any running daemon. dpkg replaces the on-disk binary, but the
# kernel keeps the previous binary mmap'd in the running process — without
# this, users keep running the old code until they kill+respawn manually.
if [ -n "$TARGET_USER" ] && [ "$TARGET_USER" != "root" ]; then
    TARGET_UID="$(id -u "$TARGET_USER" 2>/dev/null || echo '')"
    if [ -n "$TARGET_UID" ] && pgrep -u "$TARGET_USER" -f '/opt/dicton/dicton' >/dev/null 2>&1; then
        echo "Restarting Dicton daemon..."
        pkill -TERM -u "$TARGET_USER" -f '/opt/dicton/dicton' 2>/dev/null || true
        # Wait up to 5s for graceful exit, then SIGKILL stragglers
        i=0
        while [ $i -lt 5 ] && pgrep -u "$TARGET_USER" -f '/opt/dicton/dicton' >/dev/null 2>&1; do
            sleep 1
            i=$((i + 1))
        done
        pkill -KILL -u "$TARGET_USER" -f '/opt/dicton/dicton' 2>/dev/null || true

        # Respawn in the user's session. Try systemd --user first (uses the
        # xdg-autostart-generated unit if the .desktop entry is enabled);
        # fall back to a detached spawn if systemd path doesn't apply.
        USER_ENV="XDG_RUNTIME_DIR=/run/user/$TARGET_UID DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$TARGET_UID/bus"
        if runuser -u "$TARGET_USER" -- env $USER_ENV systemctl --user is-enabled app-dicton@autostart.service >/dev/null 2>&1; then
            runuser -u "$TARGET_USER" -- env $USER_ENV systemctl --user restart app-dicton@autostart.service || true
        else
            # Best-effort detached spawn; relies on DISPLAY being set in the
            # invoking shell. If missing, autostart will pick up at next login.
            runuser -u "$TARGET_USER" -- env DISPLAY="${DISPLAY:-:0}" $USER_ENV \
                setsid -f /opt/dicton/dicton </dev/null >/dev/null 2>&1 || true
        fi
    fi
fi
EOF
chmod 0755 "${STAGE_DIR}/DEBIAN/postinst"

deb_path="${DIST_DIR}/dicton_${version}_amd64.deb"
echo "==> Building Debian package: ${deb_path}"
dpkg-deb --build --root-owner-group "${STAGE_DIR}" "${deb_path}"

echo "==> Linux release assets ready:"
echo "    ${tarball_path}"
echo "    ${deb_path}"
